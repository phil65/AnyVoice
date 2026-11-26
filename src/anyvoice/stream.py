"""TTSStream orchestrator for streaming TTS with buffering and modes."""

import asyncio
import contextlib
from typing import TYPE_CHECKING, Literal, Self

from anyvoice.log import get_logger
from anyvoice.sinks import SoundDeviceSink


if TYPE_CHECKING:
    from types import TracebackType

    from anyvoice.base import AudioSink, TTSSession

logger = get_logger("stream")

# Background closing tasks of the async modes (strong references until done)
_background_tasks: set[asyncio.Task[None]] = set()

TTSMode = Literal["sync_sentence", "sync_run", "async_queue", "async_cancel"]
"""TTS synchronization modes.

- sync_sentence: Wait for each sentence's audio before continuing (slowest, most synchronized)
- sync_run: Stream fast, wait for all audio at context exit (default)
- async_queue: Stream fast, synthesis runs in background, context exit does not wait
  (the rest plays in the background, then session and sink close; `wait_closed()`)
- async_cancel: Currently identical to async_queue (use `TTSStream.cancel()` to drop audio)

An exception or cancellation inside the context drops pending audio in every mode.
"""


class TTSStream:
    """Orchestrator for streaming TTS with sentence buffering and playback.

    Coordinates a TTS session with an audio sink, handling:
    - Text buffering and sentence boundary detection
    - Synthesis scheduling (sync vs async modes)
    - Audio playback coordination

    Args:
        session: TTS session for synthesis.
        sink: Audio sink for output. Defaults to SoundDeviceSink.
        mode: Synchronization mode. Defaults to "sync_run".
        min_text_length: Minimum characters before synthesizing. Defaults to 20.
        sentence_terminators: Characters that end sentences.

    Example:
        provider = OpenAITTSProvider(api_key="...")
        session = provider.session(voice="nova")

        async with TTSStream(session) as tts:
            await tts.feed("Hello ")
            await tts.feed("world! ")
            await tts.feed("How are you?")
        # Audio plays and completes before exiting
    """

    def __init__(
        self,
        session: TTSSession,
        *,
        sink: AudioSink | None = None,
        mode: TTSMode = "sync_run",
        min_text_length: int = 20,
        sentence_terminators: frozenset[str] | None = None,
    ) -> None:
        self._session = session
        self._sink = sink
        self._mode = mode
        self._min_text_length = min_text_length
        self._sentence_terminators = sentence_terminators or frozenset({".", "!", "?", "\n"})

        # State
        self._text_buffer = ""
        self._sentence_queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._synthesis_task: asyncio.Task[None] | None = None
        self._worker_error: Exception | None = None
        self._exit_stack: contextlib.AsyncExitStack | None = None
        self._closing_task: asyncio.Task[None] | None = None
        self._active = False

    async def __aenter__(self) -> Self:
        """Enter the stream context, prepare session and sink."""
        # Initialize sink (default to SoundDeviceSink if not provided)
        if self._sink is None:
            self._sink = SoundDeviceSink()

        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(self._session)
            await stack.enter_async_context(self._sink)
            self._exit_stack = stack.pop_all()
        self._active = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the stream context, finalize audio and cleanup.

        On an exception (or cancellation) inside the context, pending audio is
        dropped. On a clean exit the remaining text is synthesized; the sync modes
        wait for it, the async modes leave it to a background task which closes
        the session and the sink afterwards (see `wait_closed()`).
        """
        self._active = False
        if exc_type is not None:
            await self._abort_and_close(exc_type, exc_val, exc_tb)
            return
        try:
            await self._flush()
            if self._mode in ("async_queue", "async_cancel"):
                task = asyncio.create_task(self._drain_and_close())
                self._closing_task = task
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)
                return
            await self._wait_for_completion()
        except BaseException as e:
            await self._abort_and_close(type(e), e, e.__traceback__)
            raise
        await self._close(None, None, None)

    async def wait_closed(self) -> None:
        """Wait until background synthesis finished and session and sink are closed.

        Only does something after the context exit of the async modes (which don't
        wait). Raises the error a background synthesis failed with, if any.
        """
        if self._closing_task is not None:
            await asyncio.shield(self._closing_task)
        self._raise_worker_error()

    async def feed(self, text: str) -> None:
        """Feed text to the TTS stream.

        Text is buffered until sentence boundaries are detected,
        then synthesized according to the configured mode.

        Args:
            text: Text chunk to add to the stream.
        """
        if not self._active:
            msg = "TTSStream must be used as async context manager"
            raise RuntimeError(msg)
        self._raise_worker_error()

        self._text_buffer += text

        # Check for sentence boundaries
        if any(term in self._text_buffer for term in self._sentence_terminators):
            last_term = max(
                (self._text_buffer.rfind(term) for term in self._sentence_terminators),
                default=-1,
            )

            if last_term > 0 and last_term >= self._min_text_length:
                sentence = self._text_buffer[: last_term + 1].strip()
                self._text_buffer = self._text_buffer[last_term + 1 :]

                if sentence:
                    if self._mode == "sync_sentence":
                        await self._synthesize_and_play(sentence)
                    else:
                        self._schedule_synthesis(sentence)

    async def cancel(self) -> None:
        """Cancel all pending synthesis and playback."""
        # Cancel synthesis worker
        if self._synthesis_task and not self._synthesis_task.done():
            self._synthesis_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._synthesis_task
            self._synthesis_task = None

        self._drop_queue()
        self._text_buffer = ""

    def _drop_queue(self) -> None:
        while not self._sentence_queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._sentence_queue.get_nowait()

    def _raise_worker_error(self) -> None:
        """Raise (once) the error the background worker stopped with."""
        if (error := self._worker_error) is not None:
            self._worker_error = None
            raise error

    async def _flush(self) -> None:
        """Synthesize (sync_sentence) or schedule the rest of the buffer."""
        if text := self._text_buffer.strip():
            self._text_buffer = ""
            if self._mode == "sync_sentence":
                await self._synthesize_and_play(text)
            else:
                self._schedule_synthesis(text)

    async def _close(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the sink and the session (both, even if one fails)."""
        stack, self._exit_stack = self._exit_stack, None
        if stack is not None:
            await stack.__aexit__(exc_type, exc_val, exc_tb)

    async def _abort_and_close(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            await self.cancel()
        finally:
            await self._close(exc_type, exc_val, exc_tb)

    async def _drain_and_close(self) -> None:
        """Background end of the async modes: finish the queue, then close."""
        try:
            await self._wait_for_completion()
        except BaseException as e:
            if isinstance(e, Exception):
                # kept for wait_closed(); nobody may be waiting, so log it too
                self._worker_error = e
                logger.exception("Background TTS synthesis failed")
            await self._abort_and_close(type(e), e, e.__traceback__)
            if not isinstance(e, Exception):
                raise
        else:
            await self._close(None, None, None)

    async def _synthesize_and_play(self, text: str) -> None:
        """Synthesize text and play audio synchronously.

        Args:
            text: Text to synthesize.
        """
        if not text.strip() or self._sink is None:
            return

        async for chunk in self._session.synthesize(text):
            await self._sink.write(chunk)

    def _schedule_synthesis(self, text: str) -> None:
        """Queue text for background synthesis.

        Args:
            text: Text to synthesize.
        """
        self._raise_worker_error()
        # Start worker if not running
        if self._synthesis_task is None or self._synthesis_task.done():
            self._synthesis_task = asyncio.create_task(self._synthesis_worker())

        # Queue the sentence
        self._sentence_queue.put_nowait(text)

    async def _synthesis_worker(self) -> None:
        """Background worker that processes sentences from the queue.

        A failure stops the worker and drops the queue; the error is raised from
        the next `feed()` or from the context exit.
        """
        try:
            while (sentence := await self._sentence_queue.get()) is not None:
                await self._synthesize_and_play(sentence)
        except Exception as e:  # noqa: BLE001
            self._worker_error = e
            self._drop_queue()

    async def _wait_for_completion(self) -> None:
        """Wait for all pending synthesis and playback to complete."""
        if self._synthesis_task and not self._synthesis_task.done():
            # Signal shutdown and wait
            await self._sentence_queue.put(None)
            await self._synthesis_task
        self._synthesis_task = None
        self._raise_worker_error()

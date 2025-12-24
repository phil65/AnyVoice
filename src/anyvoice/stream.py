"""TTSStream orchestrator for streaming TTS with buffering and modes."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Literal, Self

from anyvoice.sinks import SoundDeviceSink


if TYPE_CHECKING:
    from types import TracebackType

    from anyvoice.base import AudioSink, TTSSession

TTSMode = Literal["sync_sentence", "sync_run", "async_queue", "async_cancel"]
"""TTS synchronization modes.

- sync_sentence: Wait for each sentence's audio before continuing (slowest, most synchronized)
- sync_run: Stream fast, wait for all audio at run end (default)
- async_queue: Stream fast, audio plays in background, multiple runs queue up
- async_cancel: Stream fast, audio plays in background, new run cancels previous audio
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
        self._active = False

    async def __aenter__(self) -> Self:
        """Enter the stream context, prepare session and sink."""
        # Initialize sink (default to SoundDeviceSink if not provided)
        if self._sink is None:
            self._sink = SoundDeviceSink()

        await self._session.__aenter__()
        await self._sink.__aenter__()
        self._active = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the stream context, finalize audio and cleanup."""
        try:
            # Process any remaining text in buffer
            if self._text_buffer.strip():
                if self._mode == "sync_sentence":
                    await self._synthesize_and_play(self._text_buffer.strip())
                else:
                    self._schedule_synthesis(self._text_buffer.strip())
                self._text_buffer = ""

            # For sync modes, wait for everything to finish
            if self._mode in ("sync_sentence", "sync_run"):
                await self._wait_for_completion()
        finally:
            self._active = False
            await self._session.__aexit__(exc_type, exc_val, exc_tb)
            if self._sink is not None:
                await self._sink.__aexit__(exc_type, exc_val, exc_tb)

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

        # Clear sentence queue
        while not self._sentence_queue.empty():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._sentence_queue.get_nowait()

        # Reset text buffer
        self._text_buffer = ""

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
        # Start worker if not running
        if self._synthesis_task is None or self._synthesis_task.done():
            self._synthesis_task = asyncio.create_task(self._synthesis_worker())

        # Queue the sentence
        self._sentence_queue.put_nowait(text)

    async def _synthesis_worker(self) -> None:
        """Background worker that processes sentences from the queue."""
        while True:
            sentence = await self._sentence_queue.get()
            if sentence is None:  # Shutdown signal
                break
            await self._synthesize_and_play(sentence)

    async def _wait_for_completion(self) -> None:
        """Wait for all pending synthesis and playback to complete."""
        if self._synthesis_task and not self._synthesis_task.done():
            # Signal shutdown and wait
            await self._sentence_queue.put(None)
            await self._synthesis_task
            self._synthesis_task = None

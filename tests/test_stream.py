"""Tests for TTSStream and audio sinks (no network or audio device needed)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
import wave

import pytest

from anyvoice import CallbackSink, FileSink, TTSProvider, TTSSession, TTSStream


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path


class FakeSession(TTSSession):
    """Session that returns the encoded text as "audio"."""

    def __init__(self) -> None:
        self.texts: list[str] = []

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        self.texts.append(text)
        yield text.encode()


class FakeProvider(TTSProvider):
    def session(self, **config: Any) -> FakeSession:
        return FakeSession()


@pytest.mark.parametrize("mode", ["sync_sentence", "sync_run"])
async def test_stream_buffers_sentences(mode: Any) -> None:
    session = FakeProvider().session()
    chunks: list[bytes] = []
    async with TTSStream(session, sink=CallbackSink(chunks.append), mode=mode) as tts:
        await tts.feed("Hello there, this is ")
        await tts.feed("the first sentence. And a")
        await tts.feed(" trailing part")
    assert session.texts == ["Hello there, this is the first sentence.", "And a trailing part"]
    assert b"".join(chunks) == b"".join(t.encode() for t in session.texts)


async def test_short_text_is_not_split() -> None:
    session = FakeSession()
    chunks: list[bytes] = []
    async with TTSStream(session, sink=CallbackSink(chunks.append)) as tts:
        await tts.feed("Hi. Ok.")
    assert session.texts == ["Hi. Ok."]


async def test_feed_outside_context_raises() -> None:
    tts = TTSStream(FakeSession(), sink=CallbackSink(lambda _: None))
    with pytest.raises(RuntimeError):
        await tts.feed("text")


async def test_cancel_clears_buffer() -> None:
    session = FakeSession()
    async with TTSStream(session, sink=CallbackSink(lambda _: None)) as tts:
        await tts.feed("pending text without terminator")
        await tts.cancel()
    assert session.texts == []


async def test_callback_sink_async_callbacks() -> None:
    received: list[bytes] = []
    closed = False

    async def on_chunk(chunk: bytes) -> None:
        received.append(chunk)

    async def on_close() -> None:
        nonlocal closed
        closed = True

    async with CallbackSink(on_chunk, on_close=on_close) as sink:
        await sink.write(b"abc")
        await sink.write(b"")
    assert received == [b"abc"]
    assert closed


async def test_file_sink_writes_wav(tmp_path: Path) -> None:
    path = tmp_path / "out.wav"
    pcm = b"\x00\x01" * 100
    async with FileSink(path, sample_rate=16000) as sink:
        await sink.write(pcm)
    with wave.open(str(path), "rb") as wf:
        assert wf.getframerate() == 16000  # noqa: PLR2004
        assert wf.getnchannels() == 1
        assert wf.readframes(wf.getnframes()) == pcm


class SlowSession(TTSSession):
    """Session taking `delay` seconds per sentence; records calls after close."""

    def __init__(self, delay: float = 0.05, fail_on: str | None = None) -> None:
        self.delay = delay
        self.fail_on = fail_on
        self.texts: list[str] = []
        self.closed = False
        self.calls_after_close = 0

    async def __aexit__(self, *args: object) -> None:
        self.closed = True

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        import asyncio

        if self.closed:
            self.calls_after_close += 1
        await asyncio.sleep(self.delay)
        if self.fail_on is not None and self.fail_on in text:
            msg = f"synthesis failed: {text}"
            raise RuntimeError(msg)
        self.texts.append(text)
        yield text.encode()


class RecordingSink(CallbackSink):
    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.closed = False
        self.writes_after_close = 0
        super().__init__(self._on_chunk)

    def _on_chunk(self, chunk: bytes) -> None:
        if self.closed:
            self.writes_after_close += 1
        self.chunks.append(chunk)

    async def __aexit__(self, *args: object) -> None:
        self.closed = True


def _worker_tasks() -> list[Any]:
    import asyncio

    return [
        t for t in asyncio.all_tasks() if "_synthesis_worker" in repr(t.get_coro()) and not t.done()
    ]


@pytest.mark.parametrize("mode", ["async_queue", "async_cancel"])
async def test_async_modes_close_resources_after_the_worker(mode: Any) -> None:
    session = SlowSession()
    sink = RecordingSink()
    tts = TTSStream(session, sink=sink, mode=mode, min_text_length=0)
    async with tts:
        await tts.feed("One. Two. Three.")
        await tts.feed(" Four.")
    # exit doesn't wait, but nothing runs on closed resources
    await tts.wait_closed()
    assert session.calls_after_close == 0
    assert sink.writes_after_close == 0
    assert session.texts == ["One. Two. Three.", "Four."]
    assert session.closed
    assert sink.closed
    assert _worker_tasks() == []


async def test_cancel_inside_context_drops_pending_audio() -> None:
    import asyncio
    import time

    session = SlowSession(delay=0.2)
    sink = RecordingSink()
    started = asyncio.Event()

    async def run() -> None:
        async with TTSStream(session, sink=sink, min_text_length=0) as tts:
            for i in range(10):
                await tts.feed(f"Sentence {i}.")
            started.set()
            await asyncio.sleep(10)

    task = asyncio.create_task(run())
    await started.wait()
    t0 = time.perf_counter()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert time.perf_counter() - t0 < 0.5  # noqa: PLR2004
    assert session.closed
    assert sink.closed
    assert len(session.texts) < 10  # noqa: PLR2004
    assert _worker_tasks() == []


async def test_error_inside_context_drops_pending_audio() -> None:
    session = SlowSession(delay=0.05)
    sink = RecordingSink()

    async def run() -> None:
        async with TTSStream(session, sink=sink, min_text_length=0) as tts:
            for i in range(10):
                await tts.feed(f"Sentence {i}.")
            raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        await run()
    assert len(session.texts) < 3  # noqa: PLR2004
    assert session.closed


async def test_worker_error_is_raised_from_feed() -> None:
    import asyncio

    session = SlowSession(delay=0.01, fail_on="bad")
    sink = RecordingSink()

    async def run() -> None:
        async with TTSStream(session, sink=sink, min_text_length=0) as tts:
            await tts.feed("A bad sentence.")
            await asyncio.sleep(0.05)
            await tts.feed("Next sentence.")

    with pytest.raises(RuntimeError, match="synthesis failed"):
        await run()
    assert session.texts == []
    assert session.closed
    assert sink.closed


async def test_worker_error_is_raised_from_exit() -> None:
    session = SlowSession(delay=0.01, fail_on="bad")
    with pytest.raises(RuntimeError, match="synthesis failed"):
        async with TTSStream(session, sink=RecordingSink(), min_text_length=0) as tts:
            await tts.feed("A bad sentence.")


async def test_session_closed_when_sink_fails_to_open() -> None:
    class BrokenSink(RecordingSink):
        async def __aenter__(self) -> Any:
            raise OSError("no audio device")

    session = SlowSession()
    with pytest.raises(OSError, match="no audio device"):
        async with TTSStream(session, sink=BrokenSink()):
            pass
    assert session.closed


async def test_sink_closed_when_session_exit_fails() -> None:
    class BrokenExitSession(SlowSession):
        async def __aexit__(self, *args: object) -> None:
            raise RuntimeError("close failed")

    sink = RecordingSink()
    with pytest.raises(RuntimeError, match="close failed"):
        async with TTSStream(BrokenExitSession(), sink=sink):
            pass
    assert sink.closed

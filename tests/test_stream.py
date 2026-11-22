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

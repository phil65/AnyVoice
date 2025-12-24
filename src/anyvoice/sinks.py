"""Audio sink implementations for TTS output."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Self

from anyvoice.base import AudioSink


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    import os
    from types import TracebackType


class SoundDeviceSink(AudioSink):
    """Audio sink that plays PCM audio through the system speakers.

    Uses sounddevice for real-time audio playback.

    Args:
        sample_rate: Audio sample rate in Hz. Defaults to 24000.
        channels: Number of audio channels. Defaults to 1 (mono).
    """

    def __init__(
        self,
        *,
        sample_rate: int = 24000,
        channels: int = 1,
    ) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._stream: Any = None

    async def __aenter__(self) -> Self:
        """Start the audio output stream."""
        import sounddevice as sd  # type: ignore[import-untyped]

        self._stream = sd.RawOutputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="int16",
        )
        self._stream.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Stop and close the audio output stream."""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    async def write(self, chunk: bytes) -> None:
        """Write audio chunk to the output stream.

        Args:
            chunk: PCM audio data to play.
        """
        if self._stream is not None and chunk:
            # Run blocking write in executor to not block async loop
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._stream.write, chunk)


class FileSink(AudioSink):
    """Audio sink that writes PCM audio to a WAV file.

    Args:
        path: Path to the output WAV file.
        sample_rate: Audio sample rate in Hz. Defaults to 24000.
        channels: Number of audio channels. Defaults to 1 (mono).
    """

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        sample_rate: int = 24000,
        channels: int = 1,
    ) -> None:
        self._path = path
        self._sample_rate = sample_rate
        self._channels = channels
        self._chunks: list[bytes] = []

    async def __aenter__(self) -> Self:
        """Prepare for receiving audio."""
        self._chunks = []
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Write collected audio to WAV file."""
        import wave

        if not self._chunks:
            return

        audio_data = b"".join(self._chunks)

        with wave.open(str(self._path), "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(self._sample_rate)
            wf.writeframes(audio_data)

        self._chunks = []

    async def write(self, chunk: bytes) -> None:
        """Buffer audio chunk for later writing.

        Args:
            chunk: PCM audio data to save.
        """
        if chunk:
            self._chunks.append(chunk)


class CallbackSink(AudioSink):
    """Audio sink that passes audio chunks to a user-provided callback.

    Useful for custom audio processing, streaming, or integration
    with other systems.

    Args:
        callback: Async or sync callable that receives audio chunks.
        on_close: Optional callback invoked when sink closes.
    """

    def __init__(
        self,
        callback: Callable[[bytes], Awaitable[None]] | Callable[[bytes], None],
        *,
        on_close: Callable[[], Awaitable[None]] | Callable[[], None] | None = None,
    ) -> None:
        self._callback = callback
        self._on_close = on_close

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Invoke close callback if provided."""
        if self._on_close is not None:
            result = self._on_close()
            if asyncio.iscoroutine(result):
                await result

    async def write(self, chunk: bytes) -> None:
        """Pass audio chunk to the callback.

        Args:
            chunk: PCM audio data.
        """
        if chunk:
            result = self._callback(chunk)
            if asyncio.iscoroutine(result):
                await result

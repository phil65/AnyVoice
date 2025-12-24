"""Edge TTS provider implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from anyvoice.base import TTSProvider, TTSSession


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import TracebackType


class EdgeTTSSession(TTSSession):
    """TTS session using Microsoft Edge's TTS service.

    Args:
        voice: Voice name (e.g., "en-US-AriaNeural").
        rate: Speaking rate adjustment (e.g., "+25%", "-10%").
        volume: Volume adjustment (e.g., "+10%", "-20%").
        pitch: Pitch adjustment in Hz (e.g., "+10Hz", "-5Hz").
        sample_rate: Target sample rate for decoded audio.
    """

    def __init__(
        self,
        *,
        voice: str = "en-US-AriaNeural",
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        sample_rate: int = 24000,
    ) -> None:
        self._voice = voice
        self._rate = rate
        self._volume = volume
        self._pitch = pitch
        self._sample_rate = sample_rate

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Synthesize text to PCM audio using Edge TTS.

        Edge TTS returns MP3 which is decoded to PCM via miniaudio.

        Args:
            text: Text to synthesize.

        Yields:
            PCM audio chunks (16-bit signed, mono).
        """
        import edge_tts
        import miniaudio  # type: ignore[import-untyped]

        if not text.strip():
            return

        communicate = edge_tts.Communicate(
            text,
            voice=self._voice,
            rate=self._rate,
            volume=self._volume,
            pitch=self._pitch,
        )

        # Collect MP3 chunks
        mp3_data = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                assert "data" in chunk
                mp3_data.extend(chunk["data"])

        if mp3_data:
            # Decode MP3 to mono 16-bit PCM at target sample rate
            decoded = miniaudio.decode(
                bytes(mp3_data),
                output_format=miniaudio.SampleFormat.SIGNED16,
                nchannels=1,
                sample_rate=self._sample_rate,
            )
            yield decoded.samples.tobytes()


class EdgeTTSProvider(TTSProvider):
    """TTS provider using Microsoft Edge's free TTS service.

    Uses edge-tts library to access Microsoft's neural TTS voices.
    No API key required.

    Args:
        default_voice: Default voice name. Defaults to "en-US-AriaNeural".
        sample_rate: Target sample rate for audio output. Defaults to 24000.

    Example:
        provider = EdgeTTSProvider()
        session = provider.session(voice="en-GB-SoniaNeural", rate="+10%")

        async with TTSStream(session, sink=SoundDeviceSink()) as tts:
            await tts.feed("Hello world!")

    Note:
        Use `edge-tts --list-voices` to see all available voices.
        Voice format: {locale}-{Name}Neural (e.g., en-US-AriaNeural)
    """

    def __init__(
        self,
        *,
        default_voice: str = "en-US-AriaNeural",
        sample_rate: int = 24000,
    ) -> None:
        self._default_voice = default_voice
        self._sample_rate = sample_rate

    async def __aenter__(self) -> Self:
        """Enter provider context (no-op for Edge TTS)."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit provider context (no-op for Edge TTS)."""

    def session(
        self,
        *,
        voice: str | None = None,
        rate: str = "+0%",
        volume: str = "+0%",
        pitch: str = "+0Hz",
        sample_rate: int | None = None,
        **_: Any,
    ) -> EdgeTTSSession:
        """Create a new Edge TTS session.

        Args:
            voice: Voice name. Defaults to provider's default voice.
            rate: Speaking rate adjustment (e.g., "+25%", "-10%").
            volume: Volume adjustment (e.g., "+10%", "-20%").
            pitch: Pitch adjustment in Hz (e.g., "+10Hz", "-5Hz").
            sample_rate: Target sample rate. Defaults to provider's sample rate.

        Returns:
            Configured Edge TTS session.
        """
        return EdgeTTSSession(
            voice=voice or self._default_voice,
            rate=rate,
            volume=volume,
            pitch=pitch,
            sample_rate=sample_rate or self._sample_rate,
        )

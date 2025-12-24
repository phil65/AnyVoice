"""OpenAI TTS provider implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Self

from anyvoice.base import TTSProvider, TTSSession


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import TracebackType

    from openai import AsyncOpenAI

TTSModel = Literal["tts-1", "tts-1-hd"]
TTSVoice = Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"]


class OpenAITTSSession(TTSSession):
    """TTS session using OpenAI's streaming API.

    Args:
        client: OpenAI async client.
        model: TTS model to use.
        voice: Voice for synthesis.
        speed: Speech speed (0.25 to 4.0).
        chunk_size: Size of audio chunks to yield.
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        *,
        model: TTSModel = "tts-1",
        voice: TTSVoice = "alloy",
        speed: float = 1.0,
        chunk_size: int = 1024,
    ) -> None:
        self._client = client
        self._model = model
        self._voice = voice
        self._speed = speed
        self._chunk_size = chunk_size

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Synthesize text to PCM audio using OpenAI's streaming API.

        Args:
            text: Text to synthesize.

        Yields:
            PCM audio chunks (16-bit signed, mono, 24kHz).
        """
        if not text.strip():
            return

        async with self._client.audio.speech.with_streaming_response.create(
            model=self._model,
            voice=self._voice,
            input=text,
            response_format="pcm",
            speed=self._speed,
        ) as response:
            async for chunk in response.iter_bytes(chunk_size=self._chunk_size):
                yield chunk


class OpenAITTSProvider(TTSProvider):
    """TTS provider using OpenAI's Text-to-Speech API.

    Provides high-quality neural TTS with streaming support.
    Requires an OpenAI API key.

    Args:
        api_key: OpenAI API key. If not provided, uses OPENAI_API_KEY env var.
        base_url: Optional custom API base URL.

    Example:
        provider = OpenAITTSProvider(api_key="sk-...")
        session = provider.session(voice="nova", speed=1.0)

        async with TTSStream(session, sink=SoundDeviceSink()) as tts:
            await tts.feed("Hello world!")
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._client: AsyncOpenAI | None = None

    async def __aenter__(self) -> Self:
        """Initialize the OpenAI client."""
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the OpenAI client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    def _get_client(self) -> AsyncOpenAI:
        """Get the OpenAI client, initializing lazily if needed."""
        if self._client is None:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def session(
        self,
        *,
        model: TTSModel = "tts-1",
        voice: TTSVoice = "alloy",
        speed: float = 1.0,
        chunk_size: int = 1024,
        **_: Any,
    ) -> OpenAITTSSession:
        """Create a new OpenAI TTS session.

        Args:
            model: TTS model ("tts-1" for speed, "tts-1-hd" for quality).
            voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer).
            speed: Speech speed from 0.25 to 4.0. Defaults to 1.0.
            chunk_size: Size of audio chunks in bytes. Defaults to 1024.

        Returns:
            Configured OpenAI TTS session.
        """
        return OpenAITTSSession(
            self._get_client(),
            model=model,
            voice=voice,
            speed=speed,
            chunk_size=chunk_size,
        )

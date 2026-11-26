"""OpenAI TTS provider implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Self

from anyvoice.base import TTSProvider, TTSSession


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from types import TracebackType

    from openai import AsyncOpenAI

TTSModel = Literal["tts-1", "tts-1-hd"]
TTSVoice = Literal["alloy", "echo", "fable", "onyx", "nova", "shimmer"]


class OpenAITTSSession(TTSSession):
    """TTS session using OpenAI's streaming API.

    Args:
        client: OpenAI async client (owned by the caller, not closed by the session).
        model: TTS model to use.
        voice: Voice for synthesis.
        speed: Speech speed (0.25 to 4.0).
        chunk_size: Size of audio chunks to yield.
        client_factory: Creates a client when none is given; the session owns that
            client and closes it on exit (a later use creates a new one).
    """

    def __init__(
        self,
        client: AsyncOpenAI | None = None,
        *,
        model: TTSModel = "tts-1",
        voice: TTSVoice = "alloy",
        speed: float = 1.0,
        chunk_size: int = 1024,
        client_factory: Callable[[], AsyncOpenAI] | None = None,
    ) -> None:
        if client is None and client_factory is None:
            msg = "OpenAITTSSession needs a client or a client_factory"
            raise ValueError(msg)
        self._client = client
        self._client_factory = client_factory
        self._owns_client = client is None
        self._model = model
        self._voice = voice
        self._speed = speed
        self._chunk_size = chunk_size

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            assert self._client_factory is not None
            self._client = self._client_factory()
        return self._client

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Close the client if the session created it."""
        if self._owns_client and (client := self._client) is not None:
            self._client = None
            await client.close()

    async def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Synthesize text to PCM audio using OpenAI's streaming API.

        Args:
            text: Text to synthesize.

        Yields:
            PCM audio chunks (16-bit signed, mono, 24kHz).
        """
        if not text.strip():
            return

        async with self._get_client().audio.speech.with_streaming_response.create(
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
        """Initialize the OpenAI client shared by the sessions created inside."""
        if self._client is None:
            self._client = self._create_client()
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

    def _create_client(self) -> AsyncOpenAI:
        from openai import AsyncOpenAI

        return AsyncOpenAI(api_key=self._api_key, base_url=self._base_url)

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
            Configured OpenAI TTS session. Inside `async with provider` it uses the
            provider's client; otherwise it creates its own and closes it on exit.
        """
        return OpenAITTSSession(
            self._client,
            model=model,
            voice=voice,
            speed=speed,
            chunk_size=chunk_size,
            client_factory=self._create_client,
        )


if __name__ == "__main__":
    import asyncio

    async def main():
        async with OpenAITTSProvider() as provider:
            session = provider.session(voice="nova")
            async for chunk in session.synthesize("Hello, this is a test."):
                print(f"Got {len(chunk)} bytes")

    asyncio.run(main())

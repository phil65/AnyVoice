"""Base classes for TTS providers and audio sinks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Self


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from types import TracebackType


class AudioSink(ABC):
    """Abstract base class for audio output backends.

    Audio sinks receive PCM audio chunks and handle output
    (playback, file writing, etc.).

    Usage as context manager:
        async with SoundDeviceSink() as sink:
            await sink.write(audio_chunk)
    """

    async def __aenter__(self) -> Self:
        """Enter the sink context, prepare for receiving audio."""
        return self

    async def __aexit__(  # noqa: B027
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the sink context, finalize and cleanup."""

    @abstractmethod
    async def write(self, chunk: bytes) -> None:
        """Write a PCM audio chunk to the sink.

        Args:
            chunk: Raw PCM audio data (16-bit signed, mono).
        """
        ...


class TTSSession(ABC):
    """Abstract base class for TTS synthesis sessions.

    A session represents a single synthesis context with specific
    configuration (voice, speed, etc.). Sessions are lightweight
    and created by providers.

    Usage:
        session = provider.session(voice="nova")
        async for chunk in session.synthesize("Hello world"):
            await sink.write(chunk)
    """

    async def __aenter__(self) -> Self:
        """Enter the session context."""
        return self

    async def __aexit__(  # noqa: B027
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the session context, cleanup resources."""

    @abstractmethod
    def synthesize(self, text: str) -> AsyncIterator[bytes]:
        """Synthesize text to PCM audio.

        Args:
            text: Text to synthesize.

        Yields:
            PCM audio chunks (16-bit signed, mono).
        """
        ...


class TTSProvider(ABC):
    """Abstract base class for TTS providers.

    Providers hold credentials and client configuration, and act
    as factories for lightweight sessions.

    Usage:
        provider = OpenAITTSProvider(api_key="...")
        session = provider.session(voice="nova", speed=1.0)
    """

    @abstractmethod
    def session(self, **config: Any) -> TTSSession:
        """Create a new synthesis session with the given configuration.

        Args:
            **config: Provider-specific configuration (voice, speed, etc.).

        Returns:
            A new TTSSession configured with the given parameters.
        """
        ...

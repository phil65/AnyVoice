"""AnyVoice: A streaming-friendly Text-to-Speech library.

This library provides a clean, composable API for TTS synthesis with:
- Multiple provider backends (OpenAI, Edge TTS)
- Pluggable audio sinks (speakers, file, callback)
- Streaming support with sentence buffering
- Configurable synchronization modes

Example:
    from anyvoice import TTSStream, OpenAITTSProvider, SoundDeviceSink

    provider = OpenAITTSProvider(api_key="...")
    session = provider.session(voice="nova")

    async with TTSStream(session, sink=SoundDeviceSink()) as tts:
        await tts.feed("Hello ")
        await tts.feed("world!")
"""

from __future__ import annotations

from importlib.metadata import version

from anyvoice.base import AudioSink, TTSProvider, TTSSession
from anyvoice.providers import EdgeTTSProvider, OpenAITTSProvider
from anyvoice.sinks import CallbackSink, FileSink, SoundDeviceSink
from anyvoice.stream import TTSMode, TTSStream


__version__ = version("anyvoice")
__title__ = "AnyVoice"

__author__ = "Philipp Temminghoff"
__author_email__ = "philipptemminghoff@googlemail.com"
__copyright__ = "Copyright (c) 2025 Philipp Temminghoff"
__license__ = "MIT"
__url__ = "https://github.com/phil65/anyvoice"


__all__ = [
    # Base classes
    "AudioSink",
    # Sinks
    "CallbackSink",
    # Providers
    "EdgeTTSProvider",
    "FileSink",
    "OpenAITTSProvider",
    "SoundDeviceSink",
    # Orchestrator
    "TTSMode",
    "TTSProvider",
    "TTSSession",
    "TTSStream",
]

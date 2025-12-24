"""OpenAI example."""

from __future__ import annotations

import asyncio

from anyvoice import OpenAITTSProvider, SoundDeviceSink, TTSStream


async def main():
    provider = OpenAITTSProvider()
    session = provider.session(voice="nova", speed=1.0)

    async with TTSStream(session, sink=SoundDeviceSink()) as tts:
        await tts.feed("Hello! ")
        await tts.feed("This is streaming TTS. ")
        await tts.feed("Pretty cool, right?")


asyncio.run(main())

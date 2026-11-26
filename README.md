# AnyVoice

[![PyPI License](https://img.shields.io/pypi/l/anyvoice.svg)](https://pypi.org/project/anyvoice/)
[![Package status](https://img.shields.io/pypi/status/anyvoice.svg)](https://pypi.org/project/anyvoice/)
[![Monthly downloads](https://img.shields.io/pypi/dm/anyvoice.svg)](https://pypi.org/project/anyvoice/)
[![Distribution format](https://img.shields.io/pypi/format/anyvoice.svg)](https://pypi.org/project/anyvoice/)
[![Wheel availability](https://img.shields.io/pypi/wheel/anyvoice.svg)](https://pypi.org/project/anyvoice/)
[![Python version](https://img.shields.io/pypi/pyversions/anyvoice.svg)](https://pypi.org/project/anyvoice/)
[![Implementation](https://img.shields.io/pypi/implementation/anyvoice.svg)](https://pypi.org/project/anyvoice/)
[![Releases](https://img.shields.io/github/downloads/phil65/anyvoice/total.svg)](https://github.com/phil65/anyvoice/releases)
[![Github Contributors](https://img.shields.io/github/contributors/phil65/anyvoice)](https://github.com/phil65/anyvoice/graphs/contributors)
[![Github Forks](https://img.shields.io/github/forks/phil65/anyvoice)](https://github.com/phil65/anyvoice/forks)
[![Github Issues](https://img.shields.io/github/issues/phil65/anyvoice)](https://github.com/phil65/anyvoice/issues)
[![Github Issues](https://img.shields.io/github/issues-pr/phil65/anyvoice)](https://github.com/phil65/anyvoice/pulls)
[![Github Watchers](https://img.shields.io/github/watchers/phil65/anyvoice)](https://github.com/phil65/anyvoice/watchers)
[![Github Stars](https://img.shields.io/github/stars/phil65/anyvoice)](https://github.com/phil65/anyvoice/stars)
[![Github Repository size](https://img.shields.io/github/repo-size/phil65/anyvoice)](https://github.com/phil65/anyvoice)
[![Github last commit](https://img.shields.io/github/last-commit/phil65/anyvoice)](https://github.com/phil65/anyvoice/commits)
[![Github release date](https://img.shields.io/github/release-date/phil65/anyvoice)](https://github.com/phil65/anyvoice/releases)
[![Github language count](https://img.shields.io/github/languages/count/phil65/anyvoice)](https://github.com/phil65/anyvoice)
[![Github commits this month](https://img.shields.io/github/commit-activity/m/phil65/anyvoice)](https://github.com/phil65/anyvoice)
[![Package status](https://codecov.io/gh/phil65/anyvoice/branch/main/graph/badge.svg)](https://codecov.io/gh/phil65/anyvoice/)
[![PyUp](https://pyup.io/repos/github/phil65/anyvoice/shield.svg)](https://pyup.io/repos/github/phil65/anyvoice/)


[Read the documentation!](https://phil65.github.io/AnyVoice/)

AnyVoice is a small async library that puts streaming Text-to-Speech providers behind one
interface. Feed it text as it arrives (for example token by token from an LLM), and it buffers
the text into sentences, synthesizes them and sends raw PCM audio to a pluggable sink: your
speakers, a WAV file or your own callback.

## Features

- **Multiple TTS providers**: OpenAI TTS and Microsoft Edge TTS (free, no API key)
- **Pluggable audio sinks**: speaker playback, WAV file output, custom callbacks
- **Streaming input**: incremental `feed()` with sentence-boundary buffering
- **Synchronization modes**: choose whether `feed()` waits for audio or synthesis runs in the background
- **Lightweight**: no required dependencies; provider libraries are optional extras and imported lazily

## Installation

```bash
# OpenAI TTS (needs an OpenAI API key)
pip install "anyvoice[openai]"

# Edge TTS (free, no API key)
pip install "anyvoice[tts-edge]"
```

Speaker playback uses [sounddevice](https://python-sounddevice.readthedocs.io/), which needs the
PortAudio system library.

## Quick Start

### Basic usage with OpenAI

```python
import asyncio

from anyvoice import OpenAITTSProvider, SoundDeviceSink, TTSStream


async def main():
    provider = OpenAITTSProvider()  # uses OPENAI_API_KEY, or pass api_key="sk-..."
    session = provider.session(voice="nova", speed=1.0)

    async with TTSStream(session, sink=SoundDeviceSink()) as tts:
        await tts.feed("Hello! ")
        await tts.feed("This is streaming TTS. ")
        await tts.feed("Pretty cool, right?")


asyncio.run(main())
```

### Using Edge TTS (free, no API key)

```python
import asyncio

from anyvoice import EdgeTTSProvider, SoundDeviceSink, TTSStream


async def main():
    provider = EdgeTTSProvider()
    session = provider.session(voice="en-GB-SoniaNeural", rate="+10%")

    async with TTSStream(session, sink=SoundDeviceSink()) as tts:
        await tts.feed("Hello from Edge TTS!")


asyncio.run(main())
```

### Streaming from an LLM

Any async iterator of text chunks works:

```python
from collections.abc import AsyncIterator

from anyvoice import OpenAITTSProvider, TTSStream


async def speak(chunks: AsyncIterator[str]):
    session = OpenAITTSProvider().session(voice="nova")

    async with TTSStream(session, mode="sync_run") as tts:  # plays through the speakers
        async for chunk in chunks:
            print(chunk, end="", flush=True)
            await tts.feed(chunk)
    # Audio has finished playing when the context exits
```

### Save to a file

```python
from anyvoice import EdgeTTSProvider, FileSink, TTSStream


async def save_audio():
    session = EdgeTTSProvider().session()

    async with TTSStream(session, sink=FileSink("output.wav")) as tts:
        await tts.feed("This will be saved to a WAV file.")
```

### Custom audio handling

```python
from anyvoice import CallbackSink, OpenAITTSProvider, TTSStream


async def custom_handler():
    chunks: list[bytes] = []

    session = OpenAITTSProvider().session(voice="echo")

    async with TTSStream(session, sink=CallbackSink(chunks.append)) as tts:
        await tts.feed("Process this audio yourself!")

    total_bytes = sum(len(c) for c in chunks)
    print(f"Received {total_bytes} bytes of audio")
```

Callbacks may be sync or async. Audio is always 16-bit signed mono PCM (24 kHz by default).

### Using a session directly

Skip the orchestrator if you just want the audio chunks:

```python
from anyvoice import EdgeTTSProvider


async def synthesize():
    session = EdgeTTSProvider().session()
    async for pcm_chunk in session.synthesize("Hello world."):
        ...
```

## Synchronization Modes

Text is buffered until a sentence terminator (`.`, `!`, `?`, newline) appears after at least
`min_text_length` characters; the remainder is synthesized when the context exits.

| Mode | Behavior |
|------|----------|
| `sync_sentence` | `feed()` waits until each sentence has been synthesized and written to the sink |
| `sync_run` | `feed()` returns immediately, sentences are synthesized in the background; the context exit waits for all audio (default) |
| `async_queue` | Like `sync_run`, but the context exit does not wait: pending audio plays in the background, then the session and sink close (`await tts.wait_closed()` waits for that) |

To drop pending audio (in any mode, e.g. when a new answer replaces the old one), call
`await tts.cancel()`. An exception or a cancellation inside the context drops the pending audio in every mode. If
background synthesis fails, the error is raised from the next `feed()` or the context exit
(`wait_closed()` in the async modes).

```python
async with TTSStream(session, mode="sync_sentence") as tts:
    await tts.feed("This sentence plays completely.")
    # Audio finished before the next feed()
    await tts.feed("Then this one plays.")
```

## API Overview

### Providers

**OpenAITTSProvider**

```python
provider = OpenAITTSProvider(api_key="...", base_url=None)
session = provider.session(
    model="tts-1",  # or "tts-1-hd"
    voice="alloy",  # alloy, echo, fable, onyx, nova, shimmer
    speed=1.0,  # 0.25 to 4.0
    chunk_size=1024,
)
```

**EdgeTTSProvider**

```python
provider = EdgeTTSProvider(default_voice="en-US-AriaNeural", sample_rate=24000)
session = provider.session(
    voice="en-US-AriaNeural",  # list voices with `edge-tts --list-voices`
    rate="+0%",  # e.g., "+25%", "-10%"
    volume="+0%",
    pitch="+0Hz",
)
```

### Sinks

- `SoundDeviceSink(sample_rate=24000, channels=1)`: play through the speakers
- `FileSink(path, sample_rate=24000, channels=1)`: save to a WAV file
- `CallbackSink(callback, on_close=None)`: custom handling

Implement your own by subclassing `anyvoice.AudioSink` and defining `async write(chunk)`.
New providers subclass `TTSProvider` and `TTSSession`.

### TTSStream

```python
TTSStream(
    session,  # From provider.session()
    sink=SoundDeviceSink(),  # Audio output (default: SoundDeviceSink)
    mode="sync_run",  # Synchronization mode
    min_text_length=20,  # Minimum characters before a sentence is synthesized
    sentence_terminators=None,  # Defaults to {".", "!", "?", "\n"}
)
```

Methods:

- `await tts.feed(text)`: add text to the stream
- `await tts.cancel()`: drop pending synthesis and buffered text

## License

MIT

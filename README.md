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
[![Github Discussions](https://img.shields.io/github/discussions/phil65/anyvoice)](https://github.com/phil65/anyvoice/discussions)
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

[Read the documentation!](https://phil65.github.io/anyvoice/)


# AnyVoice

A streaming-friendly Text-to-Speech library with pluggable providers and audio backends.

## Features

- **Multiple TTS providers**: OpenAI, Edge TTS (free, no API key)
- **Pluggable audio sinks**: Speaker playback, file output, custom callbacks
- **Streaming support**: Sentence buffering and incremental synthesis
- **Sync modes**: Control how audio playback synchronizes with text streaming

## Installation

```bash
# For OpenAI TTS
pip install agentpool[tts]

# For Edge TTS (free)
pip install agentpool[tts-edge]
```

## Quick Start

### Basic usage with OpenAI

```python
import asyncio
from agentpool_tts import TTSStream, OpenAITTSProvider, SoundDeviceSink

async def main():
    provider = OpenAITTSProvider(api_key="sk-...")
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
from agentpool_tts import TTSStream, EdgeTTSProvider, SoundDeviceSink

async def main():
    provider = EdgeTTSProvider()
    session = provider.session(voice="en-GB-SoniaNeural", rate="+10%")

    async with TTSStream(session, sink=SoundDeviceSink()) as tts:
        await tts.feed("Hello from Edge TTS!")

asyncio.run(main())
```

### Streaming from an LLM

```python
async def stream_llm_response():
    provider = OpenAITTSProvider()
    session = provider.session(voice="nova")

    async with TTSStream(session, mode="sync_run") as tts:
        async for chunk in llm.stream("Tell me a joke"):
            print(chunk, end="", flush=True)
            await tts.feed(chunk)
    # Audio completes before exiting the context
```

### Save to file

```python
from agentpool_tts import TTSStream, OpenAITTSProvider, FileSink

async def save_audio():
    provider = OpenAITTSProvider()
    session = provider.session(voice="alloy")

    async with TTSStream(session, sink=FileSink("output.wav")) as tts:
        await tts.feed("This will be saved to a WAV file.")
```

### Custom audio handling

```python
from agentpool_tts import TTSStream, OpenAITTSProvider, CallbackSink

async def custom_handler():
    chunks = []

    async def on_audio(chunk: bytes):
        chunks.append(chunk)

    provider = OpenAITTSProvider()
    session = provider.session(voice="echo")

    async with TTSStream(session, sink=CallbackSink(on_audio)) as tts:
        await tts.feed("Process this audio yourself!")

    # Do something with collected chunks
    total_bytes = sum(len(c) for c in chunks)
    print(f"Received {total_bytes} bytes of audio")
```

## Synchronization Modes

Control how TTS playback synchronizes with your text stream:

| Mode | Behavior |
|------|----------|
| `sync_sentence` | Wait for each sentence's audio before continuing (most synchronized) |
| `sync_run` | Stream fast, wait for all audio at context exit (default) |
| `async_queue` | Audio plays in background, multiple streams queue up |
| `async_cancel` | Audio plays in background, new stream cancels previous |

```python
async with TTSStream(session, mode="sync_sentence") as tts:
    await tts.feed("This sentence plays completely.")
    # Audio finished before next feed()
    await tts.feed("Then this one plays.")
```

## API Reference

### Providers

**OpenAITTSProvider**
```python
provider = OpenAITTSProvider(api_key="...", base_url=None)
session = provider.session(
    model="tts-1",      # or "tts-1-hd"
    voice="alloy",      # alloy, echo, fable, onyx, nova, shimmer
    speed=1.0,          # 0.25 to 4.0
    chunk_size=1024,
)
```

**EdgeTTSProvider**
```python
provider = EdgeTTSProvider(default_voice="en-US-AriaNeural", sample_rate=24000)
session = provider.session(
    voice="en-US-AriaNeural",
    rate="+0%",         # e.g., "+25%", "-10%"
    volume="+0%",
    pitch="+0Hz",
)
```

### Sinks

- `SoundDeviceSink(sample_rate=24000)` - Play through speakers
- `FileSink(path, sample_rate=24000)` - Save to WAV file
- `CallbackSink(callback, on_close=None)` - Custom handling

### TTSStream

```python
TTSStream(
    session,                    # From provider.session()
    sink=SoundDeviceSink(),     # Audio output
    mode="sync_run",            # Synchronization mode
    min_text_length=20,         # Buffer until this many chars
)
```

Methods:
- `await tts.feed(text)` - Add text to the stream
- `await tts.cancel()` - Cancel pending synthesis/playback

# AGENTS.md

## Overview

AnyVoice (`anyvoice`) is a small async library giving streaming text-to-speech providers a
common interface. Text is fed incrementally (e.g. from an LLM stream), buffered into sentences,
synthesized by a provider session and written as 16-bit mono PCM to a pluggable audio sink.
Providers: OpenAI TTS and Microsoft Edge TTS. Python >= 3.13, no required runtime dependencies.

## Architecture

All code lives in `src/anyvoice/`:

- `base.py`: the three ABCs.
  - `TTSProvider`: holds credentials/config; `session(**config) -> TTSSession` is a factory.
  - `TTSSession`: `synthesize(text) -> AsyncIterator[bytes]` (PCM chunks); async context manager.
  - `AudioSink`: `async write(chunk)`; async context manager (open/flush/close).
- `providers/openai.py`: `OpenAITTSProvider` / `OpenAITTSSession` (streams `response_format="pcm"`
  at 24 kHz via `AsyncOpenAI`; client created lazily or in `__aenter__`).
- `providers/edge.py`: `EdgeTTSProvider` / `EdgeTTSSession` (collects MP3 from `edge_tts`, decodes
  with `miniaudio` to PCM, yields one chunk per sentence).
- `sinks.py`: `SoundDeviceSink` (speaker playback via `sounddevice.RawOutputStream`), `FileSink`
  (buffers, writes a WAV on exit), `CallbackSink` (sync or async callback).
- `stream.py`: `TTSStream` orchestrator and the `TTSMode` literal. `feed()` appends to a buffer;
  once a sentence terminator appears past `min_text_length`, the text up to the last terminator is
  either synthesized inline (`sync_sentence`) or queued for a background worker task. `__aexit__`
  flushes the remaining buffer and, for sync modes, waits for the worker.
- `log.py`: `get_logger(name)` returns `anyvoice.<name>` loggers.
- `__init__.py`: re-exports the public API (`__all__`), `__version__` from package metadata.

Data flow: `provider.session(...)` -> `TTSStream(session, sink=...)` -> `feed(text)` ->
`session.synthesize(sentence)` -> `sink.write(pcm)`.

## Where to look

| Task | Location |
|------|----------|
| Add a TTS provider | new module in `src/anyvoice/providers/`, export in `providers/__init__.py` and `__init__.py` |
| Add an audio output | `src/anyvoice/sinks.py` (subclass `AudioSink`) |
| Sentence splitting / sync modes | `src/anyvoice/stream.py` |
| Public exports | `src/anyvoice/__init__.py` |
| Usage example | `examples/openai_example.py` |
| Tests | `tests/test_stream.py` (fake session, no network/audio) |
| Optional extras, tool config | `pyproject.toml` |
| CI | `.github/workflows/build.yml`, `.github/workflows/documentation.yml` |

## Commands

```bash
uv sync --all-extras            # setup (default groups: dev, lint, docs)
uv run pytest                   # tests
uv run ruff check . && uv run ruff format --check .
uv run ty check                 # type check (src only, warnings fail CI)
uv run deptry src               # undeclared / unused dependencies
uv run mkdocs-mknodes build     # docs site (README + generated API pages)
uv build
uvx duty lint                   # ruff fix + format + ty (duties.py; duty is not a project dependency)
```

CI (`build.yml`) runs: `uv sync --all-extras --no-group docs --no-group lint`, ruff check,
ruff format check, `ty check`, pytest with coverage, on 3.13/3.14 x Linux/macOS/Windows
(3.14 is `continue-on-error`).

## Conventions

- `from __future__ import annotations` everywhere; typing-only imports under `TYPE_CHECKING`.
- Google-style docstrings (`[tool.mknodes] docstring-style = "google"`); API docs are generated.
- Ruff with a broad rule set and preview formatting, line length 100. Markdown code blocks
  (README) are formatted too.
- Optional provider/sink dependencies are imported lazily **inside** methods so that
  `import anyvoice` works without any extras. Keep it that way.
- Audio is always raw 16-bit signed mono PCM; default sample rate 24000 Hz.
- Tests are async functions (`asyncio_mode = "auto"`, pytest-asyncio). Don't hit the network or
  audio devices in tests; use a fake `TTSSession` and `CallbackSink`/`FileSink`.

## Specs

| Spec | URL | Targets | Code | Update check |
|---|---|---|---|---|
| OpenAI Text-to-Speech (`audio.speech`, via `openai>=1.0.0`) | https://platform.openai.com/docs/api-reference/audio/createSpeech | unpinned (tracks latest SDK; models `tts-1` / `tts-1-hd`) | `src/anyvoice/providers/openai.py` | https://platform.openai.com/docs/changelog |
| Microsoft Edge read-aloud TTS (unofficial, via `edge-tts>=7.0.0`) | https://github.com/rany2/edge-tts | unpinned (tracks latest `edge-tts`) | `src/anyvoice/providers/edge.py` | https://github.com/rany2/edge-tts/releases |

## Pitfalls

- Copier-managed project (`.copier-answers.yml`, template `copier-phil65`). Don't hand-edit
  template-owned files (workflows, `duties.py`, `.pre-commit-config.yaml`, tool config) unless
  necessary; add dependencies below the `# Only add below (Copier)` markers.
- Extras: `openai` (`openai`, `sounddevice`), `tts-edge` (`edge-tts`, `miniaudio`, `sounddevice`).
  `sounddevice` needs the PortAudio system library at runtime.
- `TTSStream` defaults to `SoundDeviceSink` when no sink is passed; always pass a sink in tests.
- `async_queue` / `async_cancel` modes do not wait for the worker in `__aexit__`, and
  `async_cancel` currently behaves like `async_queue`. Pending audio may be cut off when the
  context exits.
- `OpenAITTSProvider` reads `OPENAI_API_KEY` when no `api_key` is given. Edge TTS needs no key but
  needs network access.
- `uv.lock` is gitignored.

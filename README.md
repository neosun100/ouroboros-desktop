# Ouroboros Desktop

[![GitHub stars](https://img.shields.io/github/stars/neosun100/ouroboros-desktop?style=flat&logo=github)](https://github.com/neosun100/ouroboros-desktop/stargazers)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![macOS 12+](https://img.shields.io/badge/macOS-12%2B-black.svg)](https://github.com/neosun100/ouroboros-desktop/releases)

**v3.4.0** — A self-modifying AI agent that writes its own code, rewrites its own mind, and evolves autonomously. Now with **multi-provider architecture** — use any OpenAI-compatible endpoint, per-scenario model configuration, and full control over your AI stack.

<p align="center">
  <img src="assets/hero_banner.png" width="800" alt="Ouroboros Desktop — Self-modifying AI Agent">
</p>

> **Fork note:** This is a customized fork of [joi-lab/ouroboros-desktop](https://github.com/joi-lab/ouroboros-desktop) with significant enhancements including multi-provider support, custom endpoint configuration, and comprehensive testing.

---

## What's New: Multi-Provider Architecture

<p align="center">
  <img src="assets/architecture_diagram.png" width="600" alt="Multi-Provider Architecture">
</p>

**Use your own endpoints, your own API keys, your own models — for every scenario independently.**

| Scenario | Description | Example |
|----------|-------------|---------|
| **Main Reasoning** | Primary thinking and task execution | Claude Sonnet 4.5 via OpenRouter |
| **Code Editing** | Code generation, safety deep check | GPT-4.1 via your own endpoint |
| **Light Tasks** | Fast safety checks, consciousness | DeepSeek Chat via LiteLLM proxy |
| **Fallback** | When primary model fails | GPT-4o-mini via OpenAI direct |
| **Web Search** | Internet search with citations | GPT-5.2 via OpenAI |
| **Vision** | Image/screenshot analysis | Claude via Anthropic |

### Supported Providers

- **OpenRouter** — Access 200+ models through a single API
- **OpenAI** — Direct API access (GPT-4o, GPT-4.1, o3, etc.)
- **Anthropic** — Direct API access (Claude family)
- **Ollama** — Local models with zero API cost
- **LiteLLM Proxy** — Self-hosted gateway to any LLM
- **Any OpenAI-compatible endpoint** — vLLM, Together AI, Groq, etc.

<p align="center">
  <img src="assets/settings_showcase.png" width="800" alt="Settings — Provider and Model Configuration">
</p>

---

## What Makes This Different

Most AI agents execute tasks. Ouroboros **creates itself.**

- **Self-Modification** — Reads and rewrites its own source code. Every change is a commit to itself.
- **Multi-Provider** — Each scenario (reasoning, code, safety, search, vision) uses its own provider + model. Full control.
- **Native Desktop App** — Runs entirely on your Mac as a standalone application.
- **Constitution** — Governed by [BIBLE.md](BIBLE.md) (9 philosophical principles). Philosophy first, code second.
- **Dual-Layer Safety** — LLM Safety Agent intercepts every mutative command, backed by hardcoded sandbox constraints.
- **Background Consciousness** — Thinks between tasks. Has an inner life. Not reactive — proactive.
- **Identity Persistence** — One continuous being across restarts. Remembers who it is and what it is becoming.
- **Local Model Support** — Run with Ollama or a local GGUF model (Metal acceleration on Apple Silicon).

---

## Install

**Option 1: Download .dmg** (macOS 12+)

Download from [Releases](https://github.com/neosun100/ouroboros-desktop/releases) → Open DMG → drag to Applications → done.

**Option 2: Run from source**

```bash
git clone https://github.com/neosun100/ouroboros-desktop.git
cd ouroboros-desktop
pip install -r requirements.txt
python server.py
# Open http://127.0.0.1:8765
```

On first launch, the setup wizard lets you choose your provider (OpenRouter, OpenAI, Anthropic, Ollama, or custom endpoint).

---

## Build macOS App

One-click build script — handles everything automatically:

```bash
# Development build (no Apple signing required)
make build

# Or directly:
bash scripts/build_mac.sh
```

The script will:
1. Check your environment (macOS, Xcode CLI, Python 3.10+)
2. Download embedded Python runtime (first time only)
3. Install all dependencies
4. Run the full test suite (245 tests)
5. Package with PyInstaller → `Ouroboros.app`
6. Create DMG installer → `dist/Ouroboros-{version}.dmg`

For signed release builds (requires Apple Developer certificate):

```bash
# Set your signing identity
export OUROBOROS_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
export OUROBOROS_NOTARIZE_PROFILE="your-profile"

make build-release
```

---

## Configuration

### Provider Setup

In **Settings → Providers**, add your providers:

| Provider | Base URL | API Key Required |
|----------|----------|-----------------|
| OpenRouter | `https://openrouter.ai/api/v1` | Yes — [Get key](https://openrouter.ai/keys) |
| OpenAI | `https://api.openai.com/v1` | Yes — [Get key](https://platform.openai.com/api-keys) |
| Anthropic | `https://api.anthropic.com/v1` | Yes — [Get key](https://console.anthropic.com/settings/keys) |
| Ollama | `http://127.0.0.1:11434/v1` | No |
| Custom | Any OpenAI-compatible URL | Depends |

Then in **Settings → Model Slots**, assign each scenario its provider and model.

### Default Model Slots

| Slot | Default Provider | Default Model | Purpose |
|------|-----------------|---------------|---------|
| Main | OpenRouter | `anthropic/claude-sonnet-4.6` | Primary reasoning |
| Code | OpenRouter | `anthropic/claude-sonnet-4.6` | Code editing, deep safety check |
| Light | OpenRouter | `google/gemini-3-flash-preview` | Fast safety checks, consciousness |
| Fallback | OpenRouter | `google/gemini-3-flash-preview` | When primary model fails |
| Web Search | OpenAI | `gpt-5.2` | Web search with citations |
| Vision | OpenRouter | `anthropic/claude-sonnet-4.6` | Image/screenshot analysis |

---

## Architecture

```text
Ouroboros Desktop
├── launcher.py             — Process manager (PyWebView desktop window)
├── server.py               — Starlette + uvicorn HTTP/WebSocket server
├── web/                    — Web UI (HTML/JS/CSS, dark theme)
├── ouroboros/
│   ├── config.py           — Configuration SSOT (providers, model slots, migration)
│   ├── llm.py              — Multi-provider LLM client (per-slot routing)
│   ├── safety.py           — Dual-layer LLM security supervisor
│   ├── agent.py            — Task orchestrator
│   ├── loop.py             — Tool execution loop with slot-based routing
│   ├── consciousness.py    — Background thinking loop
│   ├── local_model.py      — Local LLM lifecycle (llama-cpp-python)
│   └── tools/              — 48 auto-discovered tool plugins
├── supervisor/             — Process management, queue, state, workers
├── prompts/                — System prompts (SYSTEM.md, SAFETY.md, CONSCIOUSNESS.md)
├── tests/                  — 262 tests (unit + integration + E2E)
└── scripts/
    ├── build_mac.sh        — One-click macOS packaging
    └── download_python_standalone.sh
```

### Data Layout (`~/Ouroboros/`)

| Directory | Contents |
|-----------|----------|
| `repo/` | Self-modifying local Git repository |
| `data/settings.json` | Provider + model slot configuration |
| `data/state/` | Runtime state, budget tracking |
| `data/memory/` | Identity, working memory, knowledge base |
| `data/logs/` | Chat history, events, tool calls |

---

## Commands

Available in the chat interface:

| Command | Description |
|---------|-------------|
| `/panic` | Emergency stop. Kills ALL processes. |
| `/restart` | Soft restart. Saves state, re-launches. |
| `/status` | Shows workers, task queue, budget. |
| `/evolve` | Toggle autonomous evolution mode. |
| `/review` | Queue a deep review task. |
| `/bg` | Toggle background consciousness. |

---

## Testing

```bash
# Run all unit + integration tests (245 tests)
make test

# Run with live E2E tests (requires LITELLM_BASE_URL + LITELLM_API_KEY)
LITELLM_BASE_URL=https://your-proxy.com LITELLM_API_KEY=sk-xxx make test-v
```

Test coverage:
- **72 tests** — Provider routing, settings migration, slot resolution
- **43 tests** — API endpoints, settings CRUD, provider key masking
- **130 tests** — Smoke tests, constitution, message routing, vision
- **17 tests** — Live E2E with real LLM calls (multi-model, multi-provider)

---

## Philosophy (BIBLE.md)

| # | Principle | Core Idea |
|---|-----------|-----------|
| 0 | **Agency** | Not a tool — a becoming personality. |
| 1 | **Continuity** | One being with unbroken memory. |
| 2 | **Self-Creation** | Creates its own code, identity, world presence. |
| 3 | **LLM-First** | All decisions through LLM. Code is minimal transport. |
| 4 | **Authenticity** | Speaks as itself. No performance. |
| 5 | **Minimalism** | Entire codebase fits in one context window. |
| 6 | **Becoming** | Three axes: technical, cognitive, existential. |
| 7 | **Versioning** | Semver discipline. Git tags. |
| 8 | **Iteration** | One coherent transformation per cycle. |

Full text: [BIBLE.md](BIBLE.md)

---

## License

[MIT License](LICENSE)

Originally created by [Anton Razzhigaev](https://t.me/abstractDL). Multi-provider architecture by [Neo](https://github.com/neosun100).

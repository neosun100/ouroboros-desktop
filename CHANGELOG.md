# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [3.4.0] - 2026-02-26

### Added

#### Multi-Provider Architecture
- **Provider registry** — Configure multiple LLM providers (OpenRouter, OpenAI, Anthropic, Ollama, or any OpenAI-compatible endpoint) with independent API keys and base URLs
- **Per-slot model configuration** — 8 slots (Main, Code, Light, Fallback, Web Search, Vision, TTS, STT) each independently select provider + model
- **Custom endpoint support** — Use self-hosted LiteLLM proxies, vLLM servers, Together AI, Groq, or any OpenAI-compatible API
- **Settings migration** — Existing `settings.json` files auto-migrate to the new provider/slot format while preserving backwards compatibility
- **`has_any_provider_key()`** — Supervisor now starts if any provider has a valid key (not just OpenRouter)

#### TTS/STT Voice Integration
- **Text-to-Speech** — `POST /api/tts` streams audio via configurable TTS provider (supports tts-1, tts-1-hd, gpt-4o-mini-tts)
- **Speech-to-Text** — `POST /api/stt` transcribes audio via configurable STT provider (supports whisper-1)
- **6 voices** — alloy, echo, fable, nova, onyx, shimmer with speed control (0.25x - 4.0x)
- **Speaker icon** on each assistant message — click to play/stop TTS
- **Microphone button** — hold to record, release to transcribe via STT
- **Auto-read toggle** — automatically plays TTS for new assistant responses
- **Voice settings section** — voice selector, speed slider, format selector, test button
- **Audio API module** (`ouroboros/audio_api.py`) extracted for BIBLE P5 compliance

#### Markdown Rendering Upgrade
- **marked.js** for full GitHub-Flavored Markdown (tables, task lists, strikethrough)
- **highlight.js** for code syntax highlighting (12 languages: JS, Python, Bash, JSON, TS, CSS, XML, SQL, YAML, Rust, Go, HTML)
- **KaTeX** for LaTeX math rendering (block `$$...$$` and inline `$...$`)
- **DOMPurify** for XSS sanitization with math tag whitelist
- **Code block copy button** with language label and "Copied!" feedback
- **Custom link renderer** — external links open in new tab with `rel="noopener"`
- **Fallback** to basic HTML escaping when CDN libraries unavailable

#### File Upload & Document Analysis
- **`POST /api/upload`** — file upload endpoint (10MB limit)
- **Text file detection** — 30+ extensions, UTF-8 decode, content preview (50KB cap)
- **Image file detection** — base64 encoding with MIME type for vision analysis
- **Drag-and-drop** file upload in chat area
- **Upload button** in chat input bar
- **Auto-vision** — uploaded images automatically trigger VLM analysis

#### UI/UX Polish
- **Toast notifications** — replace all `alert()` with themed toasts (success/error/info/warning)
- **Keyboard shortcuts** — Ctrl/Cmd+Enter to send, Escape to stop TTS
- **Conversation export** — download chat as Markdown (.md) or JSON (.json)
- **Export buttons** in chat header

#### New API Endpoints
- `GET /api/providers` — List configured providers (API keys masked)
- `POST /api/providers/test` — Test provider connection, returns available model list
- `GET /api/model-slots` — Return current model slot configurations

#### Settings UI Redesign
- **Provider management cards** — Each provider displayed as a card with name, type badge, base URL, masked key, and connection status
- **[Test] button** per provider — Verifies connectivity and shows available model count
- **[Add Provider]** — Inline form with type selector (auto-fills base URL), name, API key
- **[Edit] / [Remove]** — Inline editing and deletion with confirmation
- **Model slot configuration** — 6-row grid with provider dropdown + model input (with datalist autocomplete)
- **Auto-fetch model lists** — Switching provider triggers model list fetch for autocomplete

#### Setup Wizard
- **Provider selection** on first run: OpenRouter / OpenAI / Anthropic / Ollama / Custom
- Dynamic UI: shows/hides API key and base URL fields based on provider type
- Saves directly in the new `providers` + `model_slots` format

#### Build System
- **`scripts/build_mac.sh`** — One-click macOS packaging script
  - Environment checks (macOS, Xcode CLI, Python 3.10+, signing certs)
  - Auto-downloads embedded Python runtime
  - Runs test suite before packaging
  - PyInstaller → `.app` → DMG with ad-hoc or Developer ID signing
  - Apple notarization support (`--sign` flag)
- **Makefile targets**: `make build`, `make build-release`, `make build-clean`

#### Testing
- **`tests/test_provider_routing.py`** (72 tests) — Settings migration, slot/provider resolution, data model immutability, edge cases
- **`tests/test_api.py`** (43 tests) — HTTP endpoint tests via Starlette TestClient, settings CRUD, provider key masking
- **`tests/test_e2e_live.py`** (17 tests) — Real LLM API calls: per-slot routing, multi-model conversations, rapid slot switching, client caching, error handling
- Total: **262 tests** (up from 97)

#### Accessibility & Polish
- `@media (prefers-reduced-motion: reduce)` — Disables all animations
- Firefox scrollbar styling (`scrollbar-width: thin`)
- `color-scheme: dark` on `:root`
- ARIA labels on all navigation buttons
- `<noscript>` fallback message

### Changed

#### LLM Client (`ouroboros/llm.py`)
- **`LLMClient`** now manages multiple `OpenAI` client instances (one per provider), cached with thread-safe `threading.Lock`
- **`chat()`** gains `slot` parameter — routes to correct provider based on slot config
- **`_chat_generic()`** — New method for non-OpenRouter providers (strips cache_control, reasoning params)
- **`_parse_response()`** — Unified response parsing across all provider types
- **`vision_query()`** gains `slot` parameter (default: "vision")
- **`default_model()`** / **`available_models()`** — Read from slot config instead of env vars
- **`invalidate_client()` / `invalidate_all()`** — Clear cached clients after settings change

#### Safety Module (`ouroboros/safety.py`)
- Layer 1 uses `slot="light"` instead of manual `OUROBOROS_MODEL_LIGHT` env var
- Layer 2 uses `slot="code"` instead of manual `OUROBOROS_MODEL_CODE` env var
- Removed `USE_LOCAL_LIGHT` / `USE_LOCAL_CODE` boolean checks

#### Consciousness (`ouroboros/consciousness.py`)
- Uses `slot="light"` for all LLM calls
- Provider field in usage events uses actual provider ID from slot config

#### Tool Loop (`ouroboros/loop.py`)
- Tracks `active_slot` alongside `active_model`
- Fallback logic reads from slot config instead of env vars
- `_infer_api_key_type()` / `_infer_model_category()` — Read from slot config with env var fallback

#### Config (`ouroboros/config.py`)
- **`SETTINGS_DEFAULTS`** includes `providers` dict and `model_slots` dict
- **`migrate_settings()`** — Idempotent v1→v2 migration
- **`load_settings()`** — Calls migration on load, logs parse errors
- **`apply_settings_to_env()`** — Syncs new provider/slot config back to legacy env vars for worker compat

#### Server (`server.py`)
- `api_settings_post` deep-merges `providers` and `model_slots` dicts
- `api_settings_get` masks provider API keys
- Supervisor startup condition accepts any configured provider (not just OpenRouter)
- Invalidates LLM client cache on settings save

### Fixed
- Thread-safety: `LLMClient` client cache now protected by `threading.Lock`
- `load_settings()` logs warning on JSON parse failure instead of silent `pass`
- `_fetch_generation_cost()` only called for OpenRouter provider type
- Vision tool mock tests updated for new `slot` parameter

---

## [3.3.1] - 2026-02-23

### Added
- Apple Developer code signing and notarization (no more Gatekeeper warnings)
- Identity journal: guided identity updates through evolution rather than full rewrites

### Changed
- Improved README with badges, screenshots, and clearer install instructions

---

## [3.3.0] - 2026-02-22

Initial public release as a native macOS desktop application.

# Ouroboros Desktop — Enhancement TODO List

**Last updated:** 2026-02-27 | **Version:** 3.5.0 | **Tests:** 278 passing

---

## Priority Legend
- **P0** — Absolute must. Competitive table stakes.
- **P1** — Should have. High user value.
- **P2** — Nice to have. Strategic importance.
- **P3** — Future. Long-term roadmap.

---

## P0 — Critical (Next Sprint)

### Streaming Token-by-Token Display
> **Impact: CRITICAL** — Every AI chat app streams tokens. Without this, Ouroboros feels broken.

- [ ] Switch `llm.chat()` to `stream=True` mode in `ouroboros/llm.py`
- [ ] Add streaming support to `_chat_openrouter()`, `_chat_generic()`, `_chat_local()`
- [ ] New WebSocket message types: `stream_start`, `stream_delta`, `stream_end`
- [ ] Frontend: create empty bubble on `stream_start`, append text on `stream_delta`
- [ ] Debounced markdown re-render (50ms interval) during streaming
- [ ] Keep non-streaming as fallback for incompatible providers
- [ ] Update `_call_llm_with_retry()` in loop.py for streaming
- [ ] Token usage reported on `stream_end`

### Conversation History Sidebar
> **Impact: CRITICAL** — Chat history lost on restart. No multi-session support.

- [ ] Backend: `GET/POST/DELETE /api/conversations` endpoints
- [ ] Storage: JSONL files in `DATA_DIR/conversations/` with UUID + title + timestamp
- [ ] Frontend: collapsible left sidebar with conversation list
- [ ] "New Chat" button, conversation search, auto-title from first message
- [ ] Persist messages to backend (replace `sessionStorage`)
- [ ] Load conversation on click, delete with confirmation

---

## P1 — High Priority

### Prompt Templates / Presets
- [ ] Data model: `{id, name, description, system_prompt, first_message, icon}`
- [ ] Backend: `GET/POST/PUT/DELETE /api/templates`
- [ ] Frontend: template picker modal (grid of cards)
- [ ] Built-in defaults: Code Assistant, Writer, Translator, Researcher
- [ ] Integration with conversation creation (inject system_prompt)

### System Prompt per Conversation
- [ ] Add `system_prompt` field to conversation metadata
- [ ] Collapsible "System Prompt" textarea at top of conversation
- [ ] Override/merge with global `prompts/SYSTEM.md`
- [ ] Integration with templates (auto-fill from template)

### Artifacts / Canvas (Side Panel Rendering)
- [ ] Detect code/HTML output in assistant responses
- [ ] Side panel with sandboxed `<iframe srcdoc>` for HTML rendering
- [ ] Syntax-highlighted code view with "Copy" and "Run" buttons
- [ ] Toggle between chat view and artifacts view
- [ ] Support HTML, SVG, Mermaid diagrams

---

## P2 — Strategic

### Image Generation Inline
- [ ] New model slot: `image_gen` in config.py
- [ ] Backend: `POST /api/image/generate` using OpenAI Images API
- [ ] Frontend: inline `<img>` rendering in chat bubbles
- [ ] Download button on generated images
- [ ] Cost confirmation dialog (images are expensive)
- [ ] Support DALL-E 3, gpt-image-1, gpt-image-1.5

### MCP Client (Model Context Protocol)
- [ ] Implement Streamable HTTP transport (2025 MCP spec)
- [ ] MCP server configuration in Settings UI
- [ ] Tool discovery from connected MCP servers
- [ ] Bridge discovered tools into Ouroboros tool registry
- [ ] MCP server health monitoring
- [ ] Support for remote MCP servers (OAuth)

### Memory Management UI
- [ ] Context window usage visualization (progress bar)
- [ ] View/edit persistent memory facts
- [ ] Manual "Summarize & Compact" button
- [ ] Context strategy picker: Full / Last N / Auto-compact

---

## P3 — Future Roadmap

### Usage Analytics Dashboard
- [ ] Daily token usage chart (Canvas-based)
- [ ] Cost breakdown by provider (pie chart)
- [ ] Model usage frequency ranking
- [ ] Average response time trend
- [ ] Conversation count over time

### Model Comparison (Side-by-Side)
- [ ] `POST /api/compare` — fan out to multiple models
- [ ] Split-pane UI with response time and token counts
- [ ] "Pick winner" for personal preference tracking

### Deep Research Mode
- [ ] Multi-step research: 5-10 search/read/synthesize cycles
- [ ] Orchestrate web_search + browser + knowledge tools
- [ ] Progress display showing research steps
- [ ] Structured output with citations

### Linux/Windows Packaging
- [ ] Cross-platform file locking (replace `fcntl` with `filelock`)
- [ ] PyInstaller specs for Linux and Windows
- [ ] CI/CD GitHub Actions for multi-platform builds

### PWA Support
- [ ] manifest.json for installable web app
- [ ] Service worker for offline shell
- [ ] Mobile-responsive CSS

---

## Code Quality (Ongoing)

### README Accuracy
- [x] Fix: "6 Model Slots" → "8 Model Slots"
- [x] Fix: test count 262 → 278
- [ ] Add TTS/STT slots to model slots table in README

### Refactoring
- [ ] `server.py:_run_supervisor()` — 247 lines, split into sub-functions
- [ ] Consider splitting `web/app.js` (2,139 lines) into ES modules if >2,500

### Test Coverage Gaps
- [ ] `launcher.py` (988 lines, 0 tests) — at least smoke test
- [ ] `ouroboros/local_model.py` (380 lines, 0 tests)
- [ ] `ouroboros/world_profiler.py` (71 lines, 0 tests)
- [ ] `ouroboros/tools/tool_discovery.py` (103 lines, 0 tests)

---

## Completed (v3.4.0 — v3.5.0)

### v3.5.0 Security & Polish
- [x] Fix masked API key overwriting real keys
- [x] Fix `invalidate_clients()` missing function
- [x] Fix TOCTOU race condition in client cache
- [x] SSRF protection for provider test endpoint
- [x] Local vendor bundling (17 files, 464KB)
- [x] Thinking/reasoning collapsible display
- [x] Tool call progress indicators
- [x] Token budget bar
- [x] Console.error → toast notifications
- [x] Dashboard conditional polling
- [x] Matrix rain rAF + visibility optimization
- [x] File upload type detection fix
- [x] Filename sanitization

### v3.4.0 Multi-Provider Architecture
- [x] Provider registry (6 pre-configured + custom)
- [x] 8 independent model slots
- [x] Settings UI redesign (provider cards + slot dropdowns)
- [x] Provider connection testing
- [x] Settings migration v1→v2
- [x] TTS/STT voice integration (6 voices, mic, auto-read)
- [x] Markdown rendering (marked.js + highlight.js + KaTeX + DOMPurify)
- [x] File upload (drag-drop + button + text/image)
- [x] Toast notifications, keyboard shortcuts, chat export
- [x] One-click macOS build script
- [x] Setup wizard multi-provider
- [x] Logo + illustrations
- [x] README + CHANGELOG + documentation
- [x] 278 tests (246 unit + 32 live E2E)

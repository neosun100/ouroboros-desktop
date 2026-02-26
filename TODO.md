# Ouroboros Desktop — Enhancement TODO List

## Status Legend
- [ ] Pending
- [x] Completed
- [~] In Progress

---

## Phase 1: TTS/STT Voice Integration (HIGH PRIORITY)

### Backend
- [ ] Add `tts` model slot to config.py (provider_id + model_id for TTS)
- [ ] Add `stt` model slot to config.py (provider_id + model_id for STT)
- [ ] Create `ouroboros/tools/audio.py` — TTS tool using OpenAI-compatible `/v1/audio/speech`
- [ ] Add TTS endpoint `POST /api/tts` in server.py — accepts text, returns audio stream
- [ ] Add STT endpoint `POST /api/stt` in server.py — accepts audio, returns text
- [ ] Support multiple voices (alloy, echo, fable, nova, onyx, shimmer)
- [ ] Support audio format selection (mp3, opus, aac, flac, wav)
- [ ] Add TTS cost tracking to budget system

### Frontend
- [ ] Add speaker icon button next to each assistant message — click to play TTS
- [ ] Add global "Auto-read responses" toggle in Settings
- [ ] Add microphone button in chat input area — hold to record, release to send as STT
- [ ] Add voice selector dropdown in Settings (TTS section)
- [ ] Add audio player component with play/pause/speed controls
- [ ] WebSocket support for streaming TTS audio chunks

### Settings UI
- [ ] Add "Voice" section in Settings page between Model Slots and Local Model
- [ ] TTS provider + model selector (same pattern as other slots)
- [ ] STT provider + model selector
- [ ] Voice selection dropdown
- [ ] Speed slider (0.25x - 4.0x)
- [ ] Auto-read toggle
- [ ] Test TTS button ("Preview this voice")

### Testing
- [ ] Unit tests for TTS/STT endpoint handlers
- [ ] E2E test: TTS call with real API → verify audio bytes returned
- [ ] E2E test: STT call with sample audio → verify transcription
- [ ] Mock tests for audio tool registration

---

## Phase 2: Markdown Rendering Upgrade (HIGH PRIORITY)

- [ ] Replace hand-written regex `renderMarkdown()` with marked.js
- [ ] Add highlight.js for code syntax highlighting (dark theme)
- [ ] Add KaTeX for LaTeX math rendering
- [ ] Add Mermaid diagram support
- [ ] Add code block copy button
- [ ] Add line numbers for code blocks
- [ ] Properly handle nested lists and blockquotes
- [ ] XSS sanitization with DOMPurify
- [ ] Test rendering with edge cases (nested markdown, large code blocks)

---

## Phase 3: File Upload & Document Analysis (MEDIUM PRIORITY)

- [ ] Add drag-and-drop file upload zone in chat
- [ ] Add `POST /api/upload` endpoint for file handling
- [ ] Support image upload → auto-trigger vision analysis
- [ ] Support text/PDF/DOCX upload → extract text, add to context
- [ ] Show upload progress indicator
- [ ] File preview thumbnails in chat
- [ ] Max file size validation (configurable)

---

## Phase 4: UI/UX Polish (MEDIUM PRIORITY)

- [ ] Light/Dark theme toggle (CSS variables already support it)
- [ ] Conversation export (JSON, Markdown)
- [ ] Chat message search
- [ ] Keyboard shortcuts (Ctrl+Enter to send, Esc to cancel)
- [ ] Loading skeleton states instead of blank content
- [ ] Toast notifications for save/error/success actions
- [ ] Responsive layout for different window sizes
- [ ] Improved error messages with actionable guidance

---

## Phase 5: MCP Client Support (MEDIUM-HIGH PRIORITY)

- [ ] Implement MCP client protocol (Streamable HTTP)
- [ ] MCP server configuration in Settings UI
- [ ] Tool discovery from connected MCP servers
- [ ] Bridge MCP tools into Ouroboros tool registry
- [ ] MCP server health monitoring
- [ ] Support for `@modelcontextprotocol/server-*` npm packages

---

## Phase 6: Advanced Features (LOWER PRIORITY)

- [ ] RAG with vector embeddings (ChromaDB / LanceDB)
- [ ] Memory graph visualization on Dashboard
- [ ] Conversation branching / forking
- [ ] Artifacts rendering (inline HTML/React preview)
- [ ] Multi-agent orchestration UI
- [ ] OpenAI Realtime API for voice conversations
- [ ] Linux/Windows packaging support
- [ ] PWA support for mobile access

---

## Completed

- [x] Multi-provider architecture (providers + model_slots)
- [x] Per-slot model configuration (6 slots)
- [x] Custom endpoint support (any OpenAI-compatible)
- [x] Settings UI redesign (provider cards + slot dropdowns)
- [x] Provider connection testing
- [x] Settings migration (v1 → v2 format)
- [x] One-click macOS build script
- [x] 262 tests (unit + integration + E2E)
- [x] Accessibility improvements (reduced-motion, ARIA, Firefox scrollbar)
- [x] Setup wizard multi-provider support
- [x] New project logo and illustrations
- [x] README and CHANGELOG documentation

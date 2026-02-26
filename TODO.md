# Ouroboros Desktop — Enhancement TODO List

## Status Legend
- [ ] Pending
- [x] Completed

---

## Phase 5: MCP Client Support (FUTURE)

- [ ] Implement MCP client protocol (Streamable HTTP)
- [ ] MCP server configuration in Settings UI
- [ ] Tool discovery from connected MCP servers
- [ ] Bridge MCP tools into Ouroboros tool registry
- [ ] MCP server health monitoring

---

## Phase 6: Advanced Features (FUTURE)

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

### v3.4.0 — Multi-Provider Architecture
- [x] Multi-provider architecture (providers + model_slots)
- [x] Per-slot model configuration (8 slots: main, code, light, fallback, websearch, vision, tts, stt)
- [x] Custom endpoint support (any OpenAI-compatible)
- [x] Settings UI redesign (provider cards + slot dropdowns)
- [x] Provider connection testing
- [x] Settings migration (v1 → v2 format)
- [x] One-click macOS build script
- [x] Accessibility improvements (reduced-motion, ARIA, Firefox scrollbar)
- [x] Setup wizard multi-provider support
- [x] New project logo and illustrations
- [x] README and CHANGELOG documentation

### v3.4.0 — TTS/STT Voice Integration
- [x] TTS model slot (configurable provider + model)
- [x] STT model slot (configurable provider + model)
- [x] POST /api/tts — streaming audio response
- [x] POST /api/stt — audio transcription
- [x] GET /api/tts/voices — voice list
- [x] Speaker icon on assistant messages (play/stop TTS)
- [x] Microphone button (hold-to-record STT)
- [x] Auto-read responses toggle
- [x] Voice settings section (voice selector, speed slider, test button)
- [x] Voice settings: TTS_VOICE, TTS_SPEED, TTS_AUTO_READ, TTS_RESPONSE_FORMAT
- [x] 6 voices supported (alloy, echo, fable, nova, onyx, shimmer)
- [x] Live E2E verified: tts-1-hd, gpt-4o-mini-tts, whisper-1

### v3.4.0 — Markdown Rendering Upgrade
- [x] marked.js for full GFM markdown parsing
- [x] highlight.js for code syntax highlighting (12 languages)
- [x] KaTeX for LaTeX math rendering (block + inline)
- [x] DOMPurify for XSS sanitization
- [x] Code block copy button with "Copied!" feedback
- [x] Language label on code blocks
- [x] Custom renderer for links (target="_blank")
- [x] Inline code styling (accent tint)
- [x] Fallback rendering when CDN unavailable

### v3.4.0 — File Upload & Document Analysis
- [x] POST /api/upload endpoint (10MB limit)
- [x] Text file upload → content extraction (30+ extensions)
- [x] Image file upload → base64 encoding for vision analysis
- [x] Drag-and-drop file upload in chat
- [x] Upload button in chat input area
- [x] Auto-trigger vision analysis for images
- [x] Content preview in chat input for text files

### v3.4.0 — UI/UX Polish
- [x] Toast notification system (success/error/info/warning)
- [x] All alert() calls replaced with toast notifications
- [x] Keyboard shortcut: Ctrl/Cmd+Enter to send
- [x] Keyboard shortcut: Escape to stop TTS
- [x] Conversation export (Markdown + JSON)
- [x] Export buttons in chat header

### Testing
- [x] 246 unit + integration tests passing
- [x] 17 live E2E tests with real LLM API calls
- [x] TTS/STT live verification (tts-1-hd, whisper-1, 6 voices)
- [x] Zero credential leaks in source code

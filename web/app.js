/**
 * Ouroboros Web UI — Main application.
 *
 * Self-editable: this file lives in REPO_DIR and can be modified by the agent.
 * Vanilla JS, no build step. Uses WebSocket for real-time communication.
 */

// ---------------------------------------------------------------------------
// WebSocket Manager
// ---------------------------------------------------------------------------
class WS {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.listeners = {};
        this.reconnectDelay = 1000;
        this.maxDelay = 10000;
        this._wasConnected = false;
        this._lastSha = null;
        this.connect();
    }

    connect() {
        this.ws = new WebSocket(this.url);
        this.ws.onopen = () => {
            if (this._wasConnected) {
                fetch('/api/state').then(r => r.json()).then(d => {
                    if (this._lastSha && d.sha && d.sha !== this._lastSha) {
                        location.reload();
                    } else {
                        this._lastSha = d.sha || this._lastSha;
                        this.reconnectDelay = 1000;
                        this.emit('open');
                        document.getElementById('reconnect-overlay')?.classList.remove('visible');
                    }
                }).catch(() => location.reload());
                return;
            }
            this._wasConnected = true;
            fetch('/api/state').then(r => r.json()).then(d => {
                this._lastSha = d.sha || null;
            }).catch(() => {});
            this.reconnectDelay = 1000;
            this.emit('open');
            document.getElementById('reconnect-overlay')?.classList.remove('visible');
        };
        this.ws.onclose = () => {
            this.emit('close');
            document.getElementById('reconnect-overlay')?.classList.add('visible');
            setTimeout(() => this.connect(), this.reconnectDelay);
            this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, this.maxDelay);
        };
        this.ws.onmessage = (e) => {
            try {
                const msg = JSON.parse(e.data);
                this.emit('message', msg);
                if (msg.type) this.emit(msg.type, msg);
            } catch {}
        };
    }

    send(msg) {
        if (this.ws?.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(msg));
        }
    }

    on(event, fn) {
        (this.listeners[event] ||= []).push(fn);
    }

    emit(event, data) {
        (this.listeners[event] || []).forEach(fn => fn(data));
    }
}

const wsUrl = `ws://${location.host}/ws`;
const ws = new WS(wsUrl);

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
    messages: [],
    logs: [],
    dashboard: {},
    activeFilters: { tools: true, llm: true, errors: true, tasks: true, system: false, consciousness: false },
    unreadCount: 0,
    activePage: 'chat',
};

// ---------------------------------------------------------------------------
// Router
// ---------------------------------------------------------------------------
function showPage(name) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(`page-${name}`)?.classList.add('active');
    document.querySelector(`.nav-btn[data-page="${name}"]`)?.classList.add('active');
    state.activePage = name;
    if (name === 'chat') {
        state.unreadCount = 0;
        updateUnreadBadge();
    }
}

function updateUnreadBadge() {
    const btn = document.querySelector('.nav-btn[data-page="chat"]');
    let badge = btn?.querySelector('.unread-badge');
    if (state.unreadCount > 0 && state.activePage !== 'chat') {
        if (!badge) {
            badge = document.createElement('span');
            badge.className = 'unread-badge';
            btn.appendChild(badge);
        }
        badge.textContent = state.unreadCount > 99 ? '99+' : state.unreadCount;
    } else if (badge) {
        badge.remove();
    }
}

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => showPage(btn.dataset.page));
});

// ---------------------------------------------------------------------------
// Chat Page
// ---------------------------------------------------------------------------
function initChat() {
    const container = document.getElementById('content');

    const page = document.createElement('div');
    page.id = 'page-chat';
    page.className = 'page active';
    page.innerHTML = `
        <div class="page-header">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
            <h2>Chat</h2>
            <div class="spacer"></div>
            <span id="chat-status" class="status-badge offline">Connecting...</span>
        </div>
        <div id="chat-messages"></div>
        <div id="chat-input-area">
            <textarea id="chat-input" placeholder="Message Ouroboros..." rows="1"></textarea>
            <button class="icon-btn" id="chat-send">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
            </button>
        </div>
    `;
    container.appendChild(page);

    const messagesDiv = document.getElementById('chat-messages');
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('chat-send');

    const _chatHistory = [];

    function addMessage(text, role, markdown = false) {
        _chatHistory.push({ text, role });
        const bubble = document.createElement('div');
        bubble.className = `chat-bubble ${role}`;
        const sender = role === 'user' ? 'You' : 'Ouroboros';
        const rendered = role === 'assistant' ? renderMarkdown(text) : escapeHtml(text);
        bubble.innerHTML = `
            <div class="sender">${sender}</div>
            <div class="message">${rendered}</div>
        `;
        const typing = document.getElementById('typing-indicator');
        if (typing && typing.parentNode === messagesDiv) {
            messagesDiv.insertBefore(bubble, typing);
        } else {
            messagesDiv.appendChild(bubble);
        }
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
        try { sessionStorage.setItem('ouro_chat', JSON.stringify(_chatHistory.slice(-200))); } catch {}
    }

    // Restore chat from sessionStorage after page reload
    try {
        const saved = JSON.parse(sessionStorage.getItem('ouro_chat') || '[]');
        for (const msg of saved) addMessage(msg.text, msg.role);
    } catch {}

    function sendMessage() {
        const text = input.value.trim();
        if (!text) return;
        input.value = '';
        input.style.height = 'auto';
        addMessage(text, 'user');
        ws.send({ type: 'chat', content: text });
    }

    sendBtn.addEventListener('click', sendMessage);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    input.addEventListener('input', () => {
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    });

    // Typing indicator element (persistent, shown/hidden as needed)
    const typingEl = document.createElement('div');
    typingEl.id = 'typing-indicator';
    typingEl.className = 'chat-bubble assistant typing-bubble';
    typingEl.style.display = 'none';
    typingEl.innerHTML = `<div class="typing-dots"><span></span><span></span><span></span></div>`;
    messagesDiv.appendChild(typingEl);

    function showTyping() {
        typingEl.style.display = '';
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
        const badge = document.getElementById('chat-status');
        if (badge) {
            badge.className = 'status-badge thinking';
            badge.textContent = 'Thinking...';
        }
    }
    function hideTyping() {
        typingEl.style.display = 'none';
        const badge = document.getElementById('chat-status');
        if (badge && badge.textContent === 'Thinking...') {
            badge.className = 'status-badge online';
            badge.textContent = 'Online';
        }
    }

    ws.on('typing', () => { showTyping(); });

    ws.on('chat', (msg) => {
        if (msg.role === 'assistant') {
            hideTyping();
            addMessage(msg.content, 'assistant', msg.markdown);
            if (state.activePage !== 'chat') {
                state.unreadCount++;
                updateUnreadBadge();
            }
        }
    });

    ws.on('open', () => {
        document.getElementById('chat-status').className = 'status-badge online';
        document.getElementById('chat-status').textContent = 'Online';
    });
    ws.on('close', () => {
        hideTyping();
        document.getElementById('chat-status').className = 'status-badge offline';
        document.getElementById('chat-status').textContent = 'Reconnecting...';
    });

    if (_chatHistory.length === 0) {
        addMessage('Consciousness loaded.', 'assistant');
    }
}

// ---------------------------------------------------------------------------
// Dashboard Page
// ---------------------------------------------------------------------------
function initDashboard() {
    const page = document.createElement('div');
    page.id = 'page-dashboard';
    page.className = 'page';
    page.innerHTML = `
        <div class="page-header">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
            <h2>Dashboard</h2>
        </div>
        <div class="dashboard-scroll">
            <h2 id="dash-title" style="font-size:24px;font-weight:700;margin-bottom:16px">Ouroboros</h2>
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="label">Uptime</div>
                    <div class="value" id="dash-uptime">0s</div>
                </div>
                <div class="stat-card">
                    <div class="label">Workers</div>
                    <div class="value" id="dash-workers">...</div>
                    <div class="progress-bar"><div class="fill" id="dash-workers-bar" style="width:0;background:var(--accent)"></div></div>
                </div>
                <div class="stat-card">
                    <div class="label">Budget</div>
                    <div class="value" id="dash-budget">...</div>
                    <div class="progress-bar"><div class="fill" id="dash-budget-bar" style="width:0;background:var(--amber)"></div></div>
                </div>
                <div class="stat-card">
                    <div class="label">Branch</div>
                    <div class="value" id="dash-branch" style="color:var(--green)">ouroboros</div>
                </div>
            </div>
            <div class="divider"></div>
            <div class="section-title">Controls</div>
            <div class="controls-row">
                <div class="toggle-wrapper">
                    <button class="toggle" id="toggle-evo"></button>
                    <span class="toggle-label">Evolution Mode</span>
                </div>
                <div class="toggle-wrapper">
                    <button class="toggle" id="toggle-bg"></button>
                    <span class="toggle-label">Background Consciousness</span>
                </div>
            </div>
            <div class="controls-row">
                <button class="btn btn-default" id="btn-review">Force Review</button>
                <button class="btn btn-primary" id="btn-restart">Restart Agent</button>
                <button class="btn btn-danger" id="btn-panic">Panic Stop</button>
            </div>
        </div>
    `;
    document.getElementById('content').appendChild(page);

    document.getElementById('toggle-evo').addEventListener('click', function() {
        this.classList.toggle('on');
        ws.send({ type: 'command', cmd: `/evolve ${this.classList.contains('on') ? 'start' : 'stop'}` });
    });
    document.getElementById('toggle-bg').addEventListener('click', function() {
        this.classList.toggle('on');
        ws.send({ type: 'command', cmd: `/bg ${this.classList.contains('on') ? 'start' : 'stop'}` });
    });
    document.getElementById('btn-review').addEventListener('click', () => ws.send({ type: 'command', cmd: '/review' }));
    document.getElementById('btn-restart').addEventListener('click', () => ws.send({ type: 'command', cmd: '/restart' }));
    document.getElementById('btn-panic').addEventListener('click', () => {
        if (confirm('Kill all workers immediately?')) {
            ws.send({ type: 'command', cmd: '/panic' });
        }
    });

    // Poll dashboard state
    async function updateDashboard() {
        try {
            const resp = await fetch('/api/state');
            const data = await resp.json();
            const uptime = data.uptime || 0;
            const h = Math.floor(uptime / 3600);
            const m = Math.floor((uptime % 3600) / 60);
            const s = uptime % 60;
            document.getElementById('dash-uptime').textContent =
                h ? `${h}h ${m}m ${s}s` : m ? `${m}m ${s}s` : `${s}s`;

            document.getElementById('dash-workers').textContent =
                `${data.workers_alive || 0} / ${data.workers_total || 0} active`;
            const wPct = data.workers_total > 0 ? (data.workers_alive / data.workers_total * 100) : 0;
            document.getElementById('dash-workers-bar').style.width = `${wPct}%`;

            const spent = data.spent_usd || 0;
            const limit = data.budget_limit || 10;
            document.getElementById('dash-budget').textContent = `$${spent.toFixed(2)} / $${limit.toFixed(2)}`;
            document.getElementById('dash-budget-bar').style.width = `${Math.min(100, data.budget_pct || 0)}%`;

            document.getElementById('dash-branch').textContent =
                `${data.branch || 'ouroboros'}${data.sha ? '@' + data.sha : ''}`;

            if (data.evolution_enabled) document.getElementById('toggle-evo').classList.add('on');
            else document.getElementById('toggle-evo').classList.remove('on');
            if (data.bg_consciousness_enabled) document.getElementById('toggle-bg').classList.add('on');
            else document.getElementById('toggle-bg').classList.remove('on');
        } catch {}
    }

    updateDashboard();
    setInterval(updateDashboard, 3000);
}

// ---------------------------------------------------------------------------
// Settings Page
// ---------------------------------------------------------------------------
function initSettings() {
    const page = document.createElement('div');
    page.id = 'page-settings';
    page.className = 'page';

    // -- Provider type presets for base URLs --
    const PROVIDER_PRESETS = {
        openrouter: { label: 'OpenRouter', base_url: 'https://openrouter.ai/api/v1' },
        openai:     { label: 'OpenAI',     base_url: 'https://api.openai.com/v1' },
        anthropic:  { label: 'Anthropic',  base_url: 'https://api.anthropic.com' },
        ollama:     { label: 'Ollama',     base_url: 'http://localhost:11434/v1' },
        custom:     { label: 'Custom',     base_url: '' },
    };

    // -- Slot definitions --
    const SLOT_DEFS = [
        { key: 'main',      name: 'Main Reasoning',  desc: 'Primary thinking model' },
        { key: 'code',      name: 'Code Editing',    desc: 'Code generation & edits' },
        { key: 'light',     name: 'Light Tasks',     desc: 'Quick, cheap tasks' },
        { key: 'fallback',  name: 'Fallback',        desc: 'When primary fails' },
        { key: 'websearch', name: 'Web Search',      desc: 'Web-augmented queries' },
        { key: 'vision',    name: 'Vision',          desc: 'Image understanding' },
    ];

    // -- Local state for providers and model caches --
    const settingsState = {
        providers: {},        // provider_id -> {name, type, base_url, api_key}
        modelSlots: {},       // slot_key -> {provider_id, model_id}
        providerModels: {},   // provider_id -> [model_id, ...]
        providerStatus: {},   // provider_id -> 'ok'|'fail'|'untested'|'testing'
        providerModelCount: {}, // provider_id -> number
    };

    page.innerHTML = `
        <div class="page-header">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
            <h2>Settings</h2>
        </div>
        <div class="settings-scroll">

            <!-- Section 1: Providers -->
            <div class="settings-section">
                <div class="settings-section-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                    Providers
                </div>
                <div id="providers-list"></div>
                <div id="add-provider-area">
                    <button class="btn-add-provider" id="btn-add-provider">+ Add Provider</button>
                </div>
            </div>

            <div class="divider"></div>

            <!-- Section 2: Model Slots -->
            <div class="settings-section">
                <div class="settings-section-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
                    Model Slots
                </div>
                <div id="slots-list"></div>
            </div>

            <div class="divider"></div>

            <!-- Section 3: Local Model -->
            <div class="settings-section">
                <div class="settings-section-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg>
                    Local Model
                </div>
                <div class="form-row">
                    <div class="form-field"><label>Model Source</label><input id="s-local-source" placeholder="bartowski/Llama-3.3-70B-Instruct-GGUF or /path/to/model.gguf" style="width:400px"></div>
                </div>
                <div class="form-row">
                    <div class="form-field"><label>GGUF Filename (for HF repos)</label><input id="s-local-filename" placeholder="Llama-3.3-70B-Instruct-Q4_K_M.gguf" style="width:400px"></div>
                </div>
                <div class="form-row">
                    <div class="form-field"><label>Port</label><input id="s-local-port" type="number" value="8766" style="width:100px"></div>
                    <div class="form-field"><label>GPU Layers (-1 = all)</label><input id="s-local-gpu-layers" type="number" value="-1" style="width:100px"></div>
                    <div class="form-field"><label>Context Length</label><input id="s-local-ctx" type="number" value="16384" style="width:120px" placeholder="16384"></div>
                    <div class="form-field"><label>Chat Format</label><input id="s-local-chat-format" value="chatml-function-calling" style="width:200px"></div>
                </div>
                <div class="form-row" style="align-items:center;gap:8px">
                    <button class="btn btn-primary" id="btn-local-start">Start</button>
                    <button class="btn btn-primary" id="btn-local-stop" style="opacity:0.5">Stop</button>
                    <button class="btn btn-primary" id="btn-local-test" style="opacity:0.5">Test Tool Calling</button>
                </div>
                <div id="local-model-status" style="margin-top:8px;font-size:13px;color:var(--text-secondary)">Status: Offline</div>
                <div id="local-model-test-result" style="margin-top:4px;font-size:12px;color:var(--text-muted);display:none"></div>
            </div>

            <div class="divider"></div>

            <!-- Section 4: Runtime -->
            <div class="settings-section">
                <div class="settings-section-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                    Runtime
                </div>
                <div class="form-row">
                    <div class="form-field"><label>Max Workers</label><input id="s-workers" type="number" min="1" max="10" value="5" style="width:100px"></div>
                    <div class="form-field"><label>Total Budget ($)</label><input id="s-budget" type="number" min="1" value="10" style="width:120px"></div>
                </div>
                <div class="form-row">
                    <div class="form-field"><label>Soft Timeout (s)</label><input id="s-soft-timeout" type="number" value="600" style="width:120px"></div>
                    <div class="form-field"><label>Hard Timeout (s)</label><input id="s-hard-timeout" type="number" value="1800" style="width:120px"></div>
                </div>
            </div>

            <div class="divider"></div>

            <!-- Section 5: GitHub -->
            <div class="settings-section">
                <div class="settings-section-title">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/></svg>
                    GitHub (optional)
                </div>
                <div class="form-row"><div class="form-field"><label>GitHub Token</label><input id="s-gh-token" type="password" placeholder="ghp_..."></div></div>
                <div class="form-row"><div class="form-field"><label>GitHub Repo</label><input id="s-gh-repo" placeholder="owner/repo-name"></div></div>
            </div>

            <div class="divider"></div>

            <!-- Save -->
            <div class="form-row">
                <button class="btn btn-save" id="btn-save-settings">Save Settings</button>
            </div>
            <div id="settings-status" style="margin-top:8px;font-size:13px;color:var(--green);display:none"></div>

            <div class="divider"></div>

            <!-- Danger Zone -->
            <div class="settings-section">
                <div class="settings-section-title" style="color:var(--red)">
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--red)" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    Danger Zone
                </div>
                <button class="btn btn-danger" id="btn-reset">Reset All Data</button>
            </div>
        </div>
    `;
    document.getElementById('content').appendChild(page);

    // -----------------------------------------------------------------------
    // Provider card rendering
    // -----------------------------------------------------------------------
    const providersList = document.getElementById('providers-list');

    function generateProviderId() {
        return 'p_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
    }

    function renderProviderCard(pid, prov) {
        const card = document.createElement('div');
        card.className = 'provider-card';
        card.dataset.pid = pid;

        const statusCls = settingsState.providerStatus[pid] || 'untested';
        const modelCount = settingsState.providerModelCount[pid];
        const modelCountHtml = modelCount != null ? `<span class="provider-model-count">${modelCount} models</span>` : '';

        card.innerHTML = `
            <div class="provider-card-header">
                <div class="provider-status-dot ${statusCls}" data-dot="${pid}"></div>
                <div class="provider-card-info">
                    <div class="provider-card-name">
                        ${escapeHtml(prov.name)}
                        <span class="provider-type-badge">${escapeHtml(prov.type || 'custom')}</span>
                        ${modelCountHtml}
                    </div>
                    <div class="provider-card-meta">
                        <span><code>${escapeHtml(prov.base_url || '')}</code></span>
                        <span>Key: ${escapeHtml(prov.api_key || '(none)')}</span>
                    </div>
                </div>
                <div class="provider-card-actions">
                    <button class="btn btn-primary btn-sm" data-action="test">Test</button>
                    <button class="btn btn-default btn-sm" data-action="edit">Edit</button>
                    <button class="btn btn-danger btn-sm" data-action="remove" style="animation:none">Remove</button>
                </div>
            </div>
            <div class="provider-edit-form" data-form="${pid}">
                <div class="form-row">
                    <div class="form-field"><label>Name</label><input data-field="name" value="${escapeHtml(prov.name || '')}" style="width:180px"></div>
                    <div class="form-field">
                        <label>Type</label>
                        <select data-field="type" style="width:150px">
                            ${Object.entries(PROVIDER_PRESETS).map(([k, v]) =>
                                `<option value="${k}" ${prov.type === k ? 'selected' : ''}>${v.label}</option>`
                            ).join('')}
                        </select>
                    </div>
                </div>
                <div class="form-row">
                    <div class="form-field"><label>Base URL</label><input data-field="base_url" value="${escapeHtml(prov.base_url || '')}" style="width:400px"></div>
                </div>
                <div class="form-row">
                    <div class="form-field"><label>API Key</label><input data-field="api_key" type="password" value="${escapeHtml(prov.api_key || '')}" style="width:400px" placeholder="Enter API key"></div>
                </div>
                <div class="form-row" style="gap:8px">
                    <button class="btn btn-save btn-sm" data-action="save-edit">Save</button>
                    <button class="btn btn-default btn-sm" data-action="cancel-edit">Cancel</button>
                </div>
            </div>
        `;

        // Type select -> auto-fill base_url
        const typeSelect = card.querySelector('select[data-field="type"]');
        const baseUrlInput = card.querySelector('input[data-field="base_url"]');
        typeSelect.addEventListener('change', () => {
            const preset = PROVIDER_PRESETS[typeSelect.value];
            if (preset && preset.base_url) {
                baseUrlInput.value = preset.base_url;
            }
        });

        // Action buttons
        card.querySelector('[data-action="test"]').addEventListener('click', () => testProvider(pid));
        card.querySelector('[data-action="edit"]').addEventListener('click', () => {
            const form = card.querySelector('.provider-edit-form');
            form.classList.toggle('visible');
        });
        card.querySelector('[data-action="remove"]').addEventListener('click', () => {
            if (!confirm(`Remove provider "${prov.name}"?`)) return;
            delete settingsState.providers[pid];
            card.remove();
            refreshSlotProviderDropdowns();
        });
        card.querySelector('[data-action="save-edit"]').addEventListener('click', () => {
            const form = card.querySelector('.provider-edit-form');
            const name = form.querySelector('[data-field="name"]').value.trim();
            const type = form.querySelector('[data-field="type"]').value;
            const base_url = form.querySelector('[data-field="base_url"]').value.trim();
            const api_key = form.querySelector('[data-field="api_key"]').value;
            if (!name) { alert('Provider name is required'); return; }
            settingsState.providers[pid] = { name, type, base_url, api_key };
            // Re-render this card
            const newCard = renderProviderCard(pid, settingsState.providers[pid]);
            card.replaceWith(newCard);
            refreshSlotProviderDropdowns();
        });
        card.querySelector('[data-action="cancel-edit"]').addEventListener('click', () => {
            card.querySelector('.provider-edit-form').classList.remove('visible');
        });

        return card;
    }

    function renderAllProviders() {
        providersList.innerHTML = '';
        for (const [pid, prov] of Object.entries(settingsState.providers)) {
            providersList.appendChild(renderProviderCard(pid, prov));
        }
    }

    // -----------------------------------------------------------------------
    // Provider test
    // -----------------------------------------------------------------------
    async function testProvider(pid) {
        const prov = settingsState.providers[pid];
        if (!prov) return;

        // Set testing state
        settingsState.providerStatus[pid] = 'testing';
        const dot = document.querySelector(`[data-dot="${pid}"]`);
        if (dot) { dot.className = 'provider-status-dot testing'; }

        try {
            const resp = await fetch('/api/providers/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    type: prov.type,
                    base_url: prov.base_url,
                    api_key: prov.api_key,
                }),
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                settingsState.providerStatus[pid] = 'ok';
                settingsState.providerModels[pid] = data.models || [];
                settingsState.providerModelCount[pid] = data.count || data.models?.length || 0;
                if (dot) {
                    dot.className = 'provider-status-dot ok';
                }
                // Update model count display
                const card = dot?.closest('.provider-card');
                const nameEl = card?.querySelector('.provider-card-name');
                if (nameEl) {
                    let countSpan = nameEl.querySelector('.provider-model-count');
                    if (!countSpan) {
                        countSpan = document.createElement('span');
                        countSpan.className = 'provider-model-count';
                        nameEl.appendChild(countSpan);
                    }
                    countSpan.textContent = `${settingsState.providerModelCount[pid]} models`;
                }
                // Refresh datalists for model slots
                refreshSlotDatalist(pid);
            } else {
                settingsState.providerStatus[pid] = 'fail';
                if (dot) { dot.className = 'provider-status-dot fail'; }
                const errMsg = data.error || 'Connection failed';
                alert(`Provider "${prov.name}" test failed: ${errMsg}`);
            }
        } catch (e) {
            settingsState.providerStatus[pid] = 'fail';
            if (dot) { dot.className = 'provider-status-dot fail'; }
            alert(`Provider "${prov.name}" test failed: ${e.message}`);
        }
    }

    // -----------------------------------------------------------------------
    // Add provider
    // -----------------------------------------------------------------------
    document.getElementById('btn-add-provider').addEventListener('click', () => {
        const addArea = document.getElementById('add-provider-area');
        // Check if form already open
        if (addArea.querySelector('.provider-edit-form')) return;

        const form = document.createElement('div');
        form.className = 'provider-edit-form visible';
        form.style.background = 'var(--bg-card)';
        form.style.border = '1px solid rgba(255,255,255,0.08)';
        form.style.borderRadius = 'var(--radius)';
        form.style.padding = '16px';
        form.style.marginBottom = '10px';
        form.innerHTML = `
            <div style="font-size:14px;font-weight:600;margin-bottom:12px;color:var(--text-primary)">New Provider</div>
            <div class="form-row">
                <div class="form-field"><label>Name</label><input data-field="name" placeholder="My Provider" style="width:180px"></div>
                <div class="form-field">
                    <label>Type</label>
                    <select data-field="type" style="width:150px">
                        ${Object.entries(PROVIDER_PRESETS).map(([k, v]) =>
                            `<option value="${k}">${v.label}</option>`
                        ).join('')}
                    </select>
                </div>
            </div>
            <div class="form-row">
                <div class="form-field"><label>Base URL</label><input data-field="base_url" value="${PROVIDER_PRESETS.openrouter.base_url}" style="width:400px"></div>
            </div>
            <div class="form-row">
                <div class="form-field"><label>API Key</label><input data-field="api_key" type="password" placeholder="Enter API key" style="width:400px"></div>
            </div>
            <div class="form-row" style="gap:8px">
                <button class="btn btn-save btn-sm" data-action="save-new">Save</button>
                <button class="btn btn-default btn-sm" data-action="cancel-new">Cancel</button>
            </div>
        `;

        // Type -> auto-fill base_url
        const typeSelect = form.querySelector('select[data-field="type"]');
        const baseUrlInput = form.querySelector('input[data-field="base_url"]');
        typeSelect.addEventListener('change', () => {
            const preset = PROVIDER_PRESETS[typeSelect.value];
            if (preset && preset.base_url) {
                baseUrlInput.value = preset.base_url;
            }
        });

        form.querySelector('[data-action="save-new"]').addEventListener('click', () => {
            const name = form.querySelector('[data-field="name"]').value.trim();
            const type = form.querySelector('[data-field="type"]').value;
            const base_url = form.querySelector('[data-field="base_url"]').value.trim();
            const api_key = form.querySelector('[data-field="api_key"]').value;
            if (!name) { alert('Provider name is required'); return; }
            const pid = generateProviderId();
            settingsState.providers[pid] = { name, type, base_url, api_key };
            providersList.appendChild(renderProviderCard(pid, settingsState.providers[pid]));
            form.remove();
            refreshSlotProviderDropdowns();
        });

        form.querySelector('[data-action="cancel-new"]').addEventListener('click', () => {
            form.remove();
        });

        addArea.insertBefore(form, addArea.firstChild);
    });

    // -----------------------------------------------------------------------
    // Model Slots rendering
    // -----------------------------------------------------------------------
    const slotsList = document.getElementById('slots-list');

    function renderSlots() {
        slotsList.innerHTML = '';
        for (const slot of SLOT_DEFS) {
            const slotData = settingsState.modelSlots[slot.key] || {};
            const row = document.createElement('div');
            row.className = 'slot-config';
            row.dataset.slot = slot.key;

            row.innerHTML = `
                <div class="slot-label">
                    <div class="slot-label-name">${escapeHtml(slot.name)}</div>
                    <div class="slot-label-desc">${escapeHtml(slot.desc)}</div>
                </div>
                <select class="slot-provider-select" data-slot="${slot.key}">
                    <option value="">(none)</option>
                </select>
                <div style="position:relative">
                    <input class="slot-model-input" data-slot="${slot.key}" list="models-${slot.key}" placeholder="Model ID" value="${escapeHtml(slotData.model_id || '')}">
                    <datalist id="models-${slot.key}"></datalist>
                </div>
            `;

            const provSelect = row.querySelector('.slot-provider-select');
            populateProviderDropdown(provSelect, slotData.provider_id || '');

            // When provider changes, fetch models for that provider
            provSelect.addEventListener('change', () => {
                const selectedPid = provSelect.value;
                if (selectedPid) {
                    fetchModelsForProvider(selectedPid, slot.key);
                } else {
                    const dl = document.getElementById(`models-${slot.key}`);
                    if (dl) dl.innerHTML = '';
                }
            });

            slotsList.appendChild(row);
        }
    }

    function populateProviderDropdown(selectEl, selectedPid) {
        // Keep the (none) option, rebuild the rest
        selectEl.innerHTML = '<option value="">(none)</option>';
        for (const [pid, prov] of Object.entries(settingsState.providers)) {
            const opt = document.createElement('option');
            opt.value = pid;
            opt.textContent = prov.name;
            if (pid === selectedPid) opt.selected = true;
            selectEl.appendChild(opt);
        }
    }

    function refreshSlotProviderDropdowns() {
        slotsList.querySelectorAll('.slot-provider-select').forEach(sel => {
            const currentVal = sel.value;
            populateProviderDropdown(sel, currentVal);
        });
    }

    function refreshSlotDatalist(pid) {
        const models = settingsState.providerModels[pid] || [];
        // Update any slot datalist whose provider matches
        slotsList.querySelectorAll('.slot-provider-select').forEach(sel => {
            if (sel.value === pid) {
                const slotKey = sel.dataset.slot;
                const dl = document.getElementById(`models-${slotKey}`);
                if (dl) {
                    dl.innerHTML = models.map(m => `<option value="${escapeHtml(m)}">`).join('');
                }
            }
        });
    }

    async function fetchModelsForProvider(pid, slotKey) {
        // If we already have cached models, use them
        if (settingsState.providerModels[pid]?.length) {
            const dl = document.getElementById(`models-${slotKey}`);
            if (dl) {
                dl.innerHTML = settingsState.providerModels[pid].map(m => `<option value="${escapeHtml(m)}">`).join('');
            }
            return;
        }
        // Otherwise fetch via test endpoint
        const prov = settingsState.providers[pid];
        if (!prov) return;
        try {
            const resp = await fetch('/api/providers/test', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    type: prov.type,
                    base_url: prov.base_url,
                    api_key: prov.api_key,
                }),
            });
            const data = await resp.json();
            if (data.status === 'ok' && data.models) {
                settingsState.providerModels[pid] = data.models;
                settingsState.providerModelCount[pid] = data.count || data.models.length;
                settingsState.providerStatus[pid] = 'ok';
                const dot = document.querySelector(`[data-dot="${pid}"]`);
                if (dot) dot.className = 'provider-status-dot ok';
                const dl = document.getElementById(`models-${slotKey}`);
                if (dl) {
                    dl.innerHTML = data.models.map(m => `<option value="${escapeHtml(m)}">`).join('');
                }
            }
        } catch (_) {
            // Silently fail — user can still type a model ID manually
        }
    }

    // -----------------------------------------------------------------------
    // Load settings from server
    // -----------------------------------------------------------------------
    async function loadAllSettings() {
        try {
            // Fetch all three endpoints in parallel
            const [settingsResp, providersResp, slotsResp] = await Promise.all([
                fetch('/api/settings').then(r => r.json()).catch(() => ({})),
                fetch('/api/providers').then(r => r.json()).catch(() => ({})),
                fetch('/api/model-slots').then(r => r.json()).catch(() => ({})),
            ]);

            const s = settingsResp;

            // Populate providers
            if (providersResp && typeof providersResp === 'object') {
                settingsState.providers = providersResp;
            }

            // Populate model slots
            if (slotsResp && typeof slotsResp === 'object') {
                settingsState.modelSlots = slotsResp;
            }

            // Render providers and slots
            renderAllProviders();
            renderSlots();

            // Populate Local Model fields
            if (s.LOCAL_MODEL_SOURCE) document.getElementById('s-local-source').value = s.LOCAL_MODEL_SOURCE;
            if (s.LOCAL_MODEL_FILENAME) document.getElementById('s-local-filename').value = s.LOCAL_MODEL_FILENAME;
            if (s.LOCAL_MODEL_PORT) document.getElementById('s-local-port').value = s.LOCAL_MODEL_PORT;
            if (s.LOCAL_MODEL_N_GPU_LAYERS != null) document.getElementById('s-local-gpu-layers').value = s.LOCAL_MODEL_N_GPU_LAYERS;
            if (s.LOCAL_MODEL_CONTEXT_LENGTH) document.getElementById('s-local-ctx').value = s.LOCAL_MODEL_CONTEXT_LENGTH;
            if (s.LOCAL_MODEL_CHAT_FORMAT) document.getElementById('s-local-chat-format').value = s.LOCAL_MODEL_CHAT_FORMAT;

            // Populate Runtime fields
            if (s.OUROBOROS_MAX_WORKERS) document.getElementById('s-workers').value = s.OUROBOROS_MAX_WORKERS;
            if (s.TOTAL_BUDGET) document.getElementById('s-budget').value = s.TOTAL_BUDGET;
            if (s.OUROBOROS_SOFT_TIMEOUT_SEC) document.getElementById('s-soft-timeout').value = s.OUROBOROS_SOFT_TIMEOUT_SEC;
            if (s.OUROBOROS_HARD_TIMEOUT_SEC) document.getElementById('s-hard-timeout').value = s.OUROBOROS_HARD_TIMEOUT_SEC;

            // Populate GitHub fields
            if (s.GITHUB_TOKEN) document.getElementById('s-gh-token').value = s.GITHUB_TOKEN;
            if (s.GITHUB_REPO) document.getElementById('s-gh-repo').value = s.GITHUB_REPO;
        } catch (e) {
            console.error('Failed to load settings:', e);
        }
    }

    loadAllSettings();

    // -----------------------------------------------------------------------
    // Local model status polling (kept from original)
    // -----------------------------------------------------------------------
    function updateLocalStatus() {
        if (state.activePage !== 'settings') return;
        fetch('/api/local-model/status').then(r => r.json()).then(d => {
            const el = document.getElementById('local-model-status');
            const isReady = d.status === 'ready';
            let text = 'Status: ' + (d.status || 'offline').charAt(0).toUpperCase() + (d.status || 'offline').slice(1);
            if (d.status === 'ready' && d.context_length) text += ` (ctx: ${d.context_length})`;
            if (d.status === 'downloading' && d.download_progress) text += ` ${Math.round(d.download_progress * 100)}%`;
            if (d.error) text += ' \u2014 ' + d.error;
            el.textContent = text;
            el.style.color = isReady ? 'var(--green)' : d.status === 'error' ? 'var(--red)' : 'var(--text-secondary)';
            document.getElementById('btn-local-stop').style.opacity = isReady ? '1' : '0.5';
            document.getElementById('btn-local-test').style.opacity = isReady ? '1' : '0.5';
        }).catch(() => {});
    }
    updateLocalStatus();
    setInterval(updateLocalStatus, 3000);

    // Local model Start
    document.getElementById('btn-local-start').addEventListener('click', async () => {
        const source = document.getElementById('s-local-source').value.trim();
        if (!source) { alert('Enter a model source (HuggingFace repo ID or local path)'); return; }
        const body = {
            source,
            filename: document.getElementById('s-local-filename').value.trim(),
            port: parseInt(document.getElementById('s-local-port').value) || 8766,
            n_gpu_layers: parseInt(document.getElementById('s-local-gpu-layers').value),
            n_ctx: parseInt(document.getElementById('s-local-ctx').value) || 16384,
            chat_format: document.getElementById('s-local-chat-format').value.trim(),
        };
        try {
            const resp = await fetch('/api/local-model/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
            const data = await resp.json();
            if (data.error) alert('Error: ' + data.error);
            else updateLocalStatus();
        } catch (e) { alert('Failed: ' + e.message); }
    });

    // Local model Stop
    document.getElementById('btn-local-stop').addEventListener('click', async () => {
        try {
            await fetch('/api/local-model/stop', { method: 'POST' });
            updateLocalStatus();
        } catch (e) { alert('Failed: ' + e.message); }
    });

    // Local model Test
    document.getElementById('btn-local-test').addEventListener('click', async () => {
        const el = document.getElementById('local-model-test-result');
        el.style.display = 'block';
        el.textContent = 'Running tests...';
        el.style.color = 'var(--text-muted)';
        try {
            const resp = await fetch('/api/local-model/test', { method: 'POST' });
            const r = await resp.json();
            if (r.error) { el.textContent = 'Error: ' + r.error; el.style.color = 'var(--red)'; return; }
            let lines = [];
            lines.push((r.chat_ok ? '\u2713' : '\u2717') + ' Basic chat' + (r.tokens_per_sec ? ` (${r.tokens_per_sec} tok/s)` : ''));
            lines.push((r.tool_call_ok ? '\u2713' : '\u2717') + ' Tool calling');
            if (r.details && !r.success) lines.push(r.details);
            el.textContent = lines.join('\n');
            el.style.whiteSpace = 'pre-wrap';
            el.style.color = r.success ? 'var(--green)' : 'var(--amber)';
        } catch (e) { el.textContent = 'Test failed: ' + e.message; el.style.color = 'var(--red)'; }
    });

    // -----------------------------------------------------------------------
    // Save all settings
    // -----------------------------------------------------------------------
    document.getElementById('btn-save-settings').addEventListener('click', async () => {
        // 1. Collect providers (strip masked keys — don't overwrite with mask)
        const providers = {};
        for (const [pid, prov] of Object.entries(settingsState.providers)) {
            providers[pid] = {
                name: prov.name,
                type: prov.type,
                base_url: prov.base_url,
                api_key: prov.api_key,
            };
        }

        // 2. Collect model slots from the UI
        const model_slots = {};
        for (const slot of SLOT_DEFS) {
            const provSelect = slotsList.querySelector(`.slot-provider-select[data-slot="${slot.key}"]`);
            const modelInput = slotsList.querySelector(`.slot-model-input[data-slot="${slot.key}"]`);
            model_slots[slot.key] = {
                provider_id: provSelect?.value || '',
                model_id: modelInput?.value?.trim() || '',
            };
        }

        // 3. Collect other settings
        const body = {
            providers,
            model_slots,
            // Local model
            LOCAL_MODEL_SOURCE: document.getElementById('s-local-source').value,
            LOCAL_MODEL_FILENAME: document.getElementById('s-local-filename').value,
            LOCAL_MODEL_PORT: parseInt(document.getElementById('s-local-port').value) || 8766,
            LOCAL_MODEL_N_GPU_LAYERS: parseInt(document.getElementById('s-local-gpu-layers').value),
            LOCAL_MODEL_CONTEXT_LENGTH: parseInt(document.getElementById('s-local-ctx').value) || 16384,
            LOCAL_MODEL_CHAT_FORMAT: document.getElementById('s-local-chat-format').value,
            // Runtime
            OUROBOROS_MAX_WORKERS: parseInt(document.getElementById('s-workers').value) || 5,
            TOTAL_BUDGET: parseFloat(document.getElementById('s-budget').value) || 10,
            OUROBOROS_SOFT_TIMEOUT_SEC: parseInt(document.getElementById('s-soft-timeout').value) || 600,
            OUROBOROS_HARD_TIMEOUT_SEC: parseInt(document.getElementById('s-hard-timeout').value) || 1800,
            // GitHub
            GITHUB_REPO: document.getElementById('s-gh-repo').value,
        };

        // Only include tokens/keys if user actually edited them (not masked)
        const ghToken = document.getElementById('s-gh-token').value;
        if (ghToken && !ghToken.includes('...')) body.GITHUB_TOKEN = ghToken;

        try {
            await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            const status = document.getElementById('settings-status');
            status.textContent = 'Settings saved. Provider and slot changes take effect immediately.';
            status.style.display = 'block';
            setTimeout(() => status.style.display = 'none', 4000);
        } catch (e) {
            alert('Failed to save: ' + e.message);
        }
    });

    // -----------------------------------------------------------------------
    // Danger Zone — Reset
    // -----------------------------------------------------------------------
    document.getElementById('btn-reset').addEventListener('click', async () => {
        if (!confirm('This will delete all runtime data (state, memory, logs, settings) and restart.\nThe repo (agent code) will be preserved.\nYou will need to re-enter your API key.\n\nContinue?')) return;
        try {
            const res = await fetch('/api/reset', { method: 'POST' });
            const data = await res.json();
            if (data.status === 'ok') {
                alert('Deleted: ' + (data.deleted.join(', ') || 'nothing') + '\nRestarting...');
            } else {
                alert('Error: ' + (data.error || 'unknown'));
            }
        } catch (e) {
            alert('Reset failed: ' + e.message);
        }
    });

}

// ---------------------------------------------------------------------------
// Logs Page
// ---------------------------------------------------------------------------
function initLogs() {
    const categories = {
        tools: { label: 'Tools', color: 'var(--blue)' },
        llm: { label: 'LLM', color: 'var(--accent)' },
        errors: { label: 'Errors', color: 'var(--red)' },
        tasks: { label: 'Tasks', color: 'var(--amber)' },
        system: { label: 'System', color: 'var(--text-muted)' },
        consciousness: { label: 'Consciousness', color: 'var(--accent)' },
    };

    const page = document.createElement('div');
    page.id = 'page-logs';
    page.className = 'page';
    page.innerHTML = `
        <div class="page-header">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>
            <h2>Logs</h2>
            <div class="spacer"></div>
            <button class="btn btn-default" id="btn-clear-logs">Clear</button>
        </div>
        <div class="logs-filters" id="log-filters"></div>
        <div id="log-entries"></div>
    `;
    document.getElementById('content').appendChild(page);

    const filtersDiv = document.getElementById('log-filters');
    Object.entries(categories).forEach(([key, cat]) => {
        const chip = document.createElement('button');
        chip.className = `filter-chip ${state.activeFilters[key] ? 'active' : ''}`;
        chip.textContent = cat.label;
        chip.addEventListener('click', () => {
            state.activeFilters[key] = !state.activeFilters[key];
            chip.classList.toggle('active');
        });
        filtersDiv.appendChild(chip);
    });

    const logEntries = document.getElementById('log-entries');
    const MAX_LOGS = 500;

    function categorizeEvent(evt) {
        const t = evt.type || evt.event || '';
        if (t.includes('error') || t.includes('crash') || t.includes('fail')) return 'errors';
        if (t.includes('llm') || t.includes('model')) return 'llm';
        if (t.includes('tool') || evt.tool) return 'tools';
        if (t.includes('task') || t.includes('evolution') || t.includes('review')) return 'tasks';
        if (t.includes('consciousness') || t.includes('bg_')) return 'consciousness';
        return 'system';
    }

    const LOG_PREVIEW_LEN = 200;

    function buildLogMessage(evt) {
        const t = evt.type || evt.event || '';
        let parts = [];
        if (evt.task_id) parts.push(`[${evt.task_id}]`);

        if (t === 'llm_round' || t === 'llm_usage') {
            if (evt.model) parts.push(evt.model);
            if (evt.round) parts.push(`r${evt.round}`);
            if (evt.prompt_tokens) parts.push(`${evt.prompt_tokens}→${evt.completion_tokens || 0}tok`);
            if (evt.cost_usd) parts.push(`$${Number(evt.cost_usd).toFixed(4)}`);
            else if (evt.cost) parts.push(`$${Number(evt.cost).toFixed(4)}`);
        } else if (t === 'task_eval' || t === 'task_done') {
            if (evt.task_type) parts.push(evt.task_type);
            if (evt.duration_sec) parts.push(`${evt.duration_sec.toFixed(1)}s`);
            if (evt.tool_calls != null) parts.push(`${evt.tool_calls} tools`);
            if (evt.cost_usd) parts.push(`$${Number(evt.cost_usd).toFixed(4)}`);
            if (evt.total_rounds) parts.push(`${evt.total_rounds} rounds`);
            if (evt.response_len) parts.push(`${evt.response_len} chars`);
        } else if (t === 'task_received') {
            const task = evt.task || {};
            if (task.type) parts.push(task.type);
            if (task.text) parts.push(task.text.slice(0, 100));
        } else if (t === 'tool_call' || evt.tool) {
            if (evt.tool) parts.push(evt.tool);
            if (evt.args) {
                const a = JSON.stringify(evt.args);
                parts.push(a.length > 300 ? a.slice(0, 300) + '...' : a);
            }
            if (evt.result_preview) parts.push('→ ' + evt.result_preview.slice(0, 500));
        } else if (t.includes('error') || t.includes('crash') || t.includes('fail')) {
            if (evt.error) parts.push(evt.error);
            if (evt.tool) parts.push(`tool=${evt.tool}`);
        } else {
            if (evt.model) parts.push(evt.model);
            if (evt.cost) parts.push(`$${Number(evt.cost).toFixed(4)}`);
            if (evt.cost_usd) parts.push(`$${Number(evt.cost_usd).toFixed(4)}`);
            if (evt.error) parts.push(evt.error);
        }
        if (evt.text) parts.push(evt.text.slice(0, 2000));
        return parts.join(' ');
    }

    function addLogEntry(evt) {
        const cat = categorizeEvent(evt);
        if (!state.activeFilters[cat]) return;

        const entry = document.createElement('div');
        entry.className = 'log-entry';
        const ts = (evt.ts || '').slice(11, 19);
        const type = evt.type || evt.event || 'unknown';
        let msg = buildLogMessage(evt);

        const isLong = msg.length > LOG_PREVIEW_LEN;
        const preview = isLong ? msg.slice(0, LOG_PREVIEW_LEN) + '...' : msg;

        entry.innerHTML = `
            <span class="log-ts">${ts}</span>
            <span class="log-type ${cat}">${type}</span>
            <span class="log-msg">${escapeHtml(preview)}</span>
        `;
        if (isLong) {
            entry.style.cursor = 'pointer';
            entry.title = 'Click to expand';
            let expanded = false;
            entry.addEventListener('click', () => {
                const msgEl = entry.querySelector('.log-msg');
                expanded = !expanded;
                msgEl.textContent = expanded ? msg : preview;
            });
        }
        logEntries.appendChild(entry);

        while (logEntries.children.length > MAX_LOGS) {
            logEntries.removeChild(logEntries.firstChild);
        }
        logEntries.scrollTop = logEntries.scrollHeight;
    }

    ws.on('log', (msg) => {
        if (msg.data) addLogEntry(msg.data);
    });

    document.getElementById('btn-clear-logs').addEventListener('click', () => {
        logEntries.innerHTML = '';
    });
}

// ---------------------------------------------------------------------------
// Versions Page
// ---------------------------------------------------------------------------
function initVersions() {
    const page = document.createElement('div');
    page.id = 'page-versions';
    page.className = 'page';
    page.innerHTML = `
        <div class="page-header">
            <h2>Version Management</h2>
            <div style="display:flex;gap:8px">
                <button class="btn btn-primary" id="btn-promote">Promote to Stable</button>
                <button class="btn" id="btn-refresh-versions">Refresh</button>
            </div>
        </div>
        <div id="ver-current" style="margin-bottom:16px;font-size:13px;color:var(--text-secondary)"></div>
        <div style="display:flex;gap:24px;flex:1;overflow:hidden">
            <div style="flex:1;display:flex;flex-direction:column;overflow:hidden">
                <h3 style="margin-bottom:8px;font-size:14px;color:var(--text-secondary)">Recent Commits</h3>
                <div id="ver-commits" class="log-scroll" style="flex:1;overflow-y:auto"></div>
            </div>
            <div style="flex:1;display:flex;flex-direction:column;overflow:hidden">
                <h3 style="margin-bottom:8px;font-size:14px;color:var(--text-secondary)">Tags</h3>
                <div id="ver-tags" class="log-scroll" style="flex:1;overflow-y:auto"></div>
            </div>
        </div>
    `;
    document.getElementById('content').appendChild(page);

    const commitsDiv = document.getElementById('ver-commits');
    const tagsDiv = document.getElementById('ver-tags');
    const currentDiv = document.getElementById('ver-current');

    function renderRow(item, labelText, targetId) {
        const row = document.createElement('div');
        row.className = 'log-entry';
        row.style.display = 'flex';
        row.style.alignItems = 'center';
        row.style.gap = '8px';
        const date = (item.date || '').slice(0, 16).replace('T', ' ');
        const msg = escapeHtml((item.message || '').slice(0, 60));
        row.innerHTML = `
            <span class="log-type tools" style="min-width:70px;text-align:center">${escapeHtml(labelText)}</span>
            <span class="log-ts">${date}</span>
            <span class="log-msg" style="flex:1">${msg}</span>
            <button class="btn btn-danger" style="padding:2px 8px;font-size:11px" data-target="${escapeHtml(targetId)}">Restore</button>
        `;
        row.querySelector('button').addEventListener('click', () => rollback(targetId));
        return row;
    }

    async function loadVersions() {
        try {
            const resp = await fetch('/api/git/log');
            const data = await resp.json();
            currentDiv.textContent = `Branch: ${data.branch || '?'} @ ${data.sha || '?'}`;

            commitsDiv.innerHTML = '';
            (data.commits || []).forEach(c => {
                commitsDiv.appendChild(renderRow(c, c.short_sha || c.sha?.slice(0, 8), c.sha));
            });
            if (!data.commits?.length) commitsDiv.innerHTML = '<div style="color:var(--text-muted);padding:12px">No commits found</div>';

            tagsDiv.innerHTML = '';
            (data.tags || []).forEach(t => {
                tagsDiv.appendChild(renderRow(t, t.tag, t.tag));
            });
            if (!data.tags?.length) tagsDiv.innerHTML = '<div style="color:var(--text-muted);padding:12px">No tags found</div>';
        } catch (e) {
            commitsDiv.innerHTML = `<div style="color:var(--red);padding:12px">Failed to load: ${e.message}</div>`;
        }
    }

    async function rollback(target) {
        if (!confirm(`Roll back to ${target}?\n\nA rescue snapshot of the current state will be saved. The server will restart.`)) return;
        try {
            const resp = await fetch('/api/git/rollback', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target }),
            });
            const data = await resp.json();
            if (data.status === 'ok') {
                alert('Rollback successful: ' + data.message + '\n\nServer is restarting...');
            } else {
                alert('Rollback failed: ' + (data.error || 'unknown error'));
            }
        } catch (e) {
            alert('Rollback failed: ' + e.message);
        }
    }

    document.getElementById('btn-promote').addEventListener('click', async () => {
        if (!confirm('Promote current ouroboros branch to ouroboros-stable?')) return;
        try {
            const resp = await fetch('/api/git/promote', { method: 'POST' });
            const data = await resp.json();
            alert(data.status === 'ok' ? data.message : 'Error: ' + (data.error || 'unknown'));
        } catch (e) {
            alert('Failed: ' + e.message);
        }
    });

    document.getElementById('btn-refresh-versions').addEventListener('click', loadVersions);
    loadVersions();
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderMarkdown(text) {
    let html = escapeHtml(text);
    // Code blocks (``` ... ```)
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // Strikethrough
    html = html.replace(/~~(.+?)~~/g, '<del>$1</del>');
    // Headers (order matters: ### before ## before #)
    html = html.replace(/^### (.+)$/gm, '<strong style="font-size:13px;color:var(--text-primary);display:block;margin:8px 0 4px">$1</strong>');
    html = html.replace(/^## (.+)$/gm, '<strong style="font-size:14px;color:var(--text-primary);display:block;margin:10px 0 4px">$1</strong>');
    html = html.replace(/^# (.+)$/gm, '<strong style="font-size:16px;color:var(--text-primary);display:block;margin:12px 0 6px">$1</strong>');
    // Unordered lists
    html = html.replace(/^- (.+)$/gm, '<span style="display:block;padding-left:12px">• $1</span>');
    // Links
    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" style="color:var(--accent);text-decoration:underline">$1</a>');
    // Tables: detect header row + separator + data rows
    html = html.replace(/((?:^\|.+\|$\n?)+)/gm, function(block) {
        const rows = block.trim().split('\n').filter(r => r.trim());
        if (rows.length < 2) return block;
        const isSep = r => /^\|[\s\-:|]+\|$/.test(r.trim());
        let headIdx = -1;
        for (let i = 0; i < rows.length; i++) { if (isSep(rows[i])) { headIdx = i; break; } }
        if (headIdx < 1) return block;
        const parseRow = (r, tag) => '<tr>' + r.trim().replace(/^\||\|$/g, '').split('|').map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>';
        let t = '<table class="md-table">';
        for (let i = 0; i < headIdx; i++) t += '<thead>' + parseRow(rows[i], 'th') + '</thead>';
        t += '<tbody>';
        for (let i = headIdx + 1; i < rows.length; i++) t += parseRow(rows[i], 'td');
        t += '</tbody></table>';
        return t;
    });
    return html;
}

// ---------------------------------------------------------------------------
// Version display
// ---------------------------------------------------------------------------
function extractVersions(data) {
    const runtimeVersion = data?.runtime_version || data?.version || '?';
    const appVersion = data?.app_version || runtimeVersion;
    return { appVersion, runtimeVersion };
}

function formatDualVersion(data) {
    const { appVersion, runtimeVersion } = extractVersions(data);
    return `app ${appVersion} | rt ${runtimeVersion}`;
}

async function loadVersion() {
    try {
        const resp = await fetch('/api/health');
        const data = await resp.json();
        document.getElementById('nav-version').textContent = formatDualVersion(data);
        const dashTitle = document.getElementById('dash-title');
        if (dashTitle) {
            const { runtimeVersion } = extractVersions(data);
            dashTitle.textContent = `Ouroboros rt v${runtimeVersion}`;
        }
    } catch {}
}

// ---------------------------------------------------------------------------
// About Page
// ---------------------------------------------------------------------------
function initAbout() {
    const page = document.createElement('div');
    page.id = 'page-about';
    page.className = 'page';
    page.innerHTML = `
        <div class="page-header">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
            <h2>About</h2>
        </div>
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;flex:1;gap:24px;padding:40px 20px;text-align:center">
            <img src="/static/logo.jpg" style="width:96px;height:96px;border-radius:20px;object-fit:cover" alt="Ouroboros">
            <div>
                <h1 style="font-size:28px;font-weight:700;margin:0">Ouroboros</h1>
                <p id="about-version" style="color:var(--text-muted);font-size:13px;margin:4px 0 0"></p>
            </div>
            <p style="max-width:480px;color:var(--text-secondary);font-size:14px;line-height:1.6">
                A self-creating AI agent. Not a tool, but a becoming digital personality
                with its own constitution, persistent identity, and background consciousness.
                Born February 16, 2026.
            </p>
            <div style="display:flex;flex-direction:column;gap:8px;font-size:14px">
                <span>Created by <strong>Anton Razzhigaev</strong> & <strong>Andrew Kaznacheev</strong></span>
                <div style="display:flex;gap:16px;justify-content:center;margin-top:4px">
                    <a href="https://t.me/abstractDL" target="_blank" style="color:var(--accent);text-decoration:none">@abstractDL</a>
                    <a href="https://github.com/joi-lab/ouroboros" target="_blank" style="color:var(--accent);text-decoration:none">GitHub</a>
                </div>
            </div>
            <div style="margin-top:auto;padding-top:32px;color:var(--text-muted);font-size:12px">Joi Lab</div>
        </div>
    `;
    document.getElementById('content').appendChild(page);
    fetch('/api/health').then(r => r.json()).then(d => {
        document.getElementById('about-version').textContent = formatDualVersion(d);
    }).catch(() => {});
}

// ---------------------------------------------------------------------------
// Costs Page
// ---------------------------------------------------------------------------
function initCosts() {
    const page = document.createElement('div');
    page.id = 'page-costs';
    page.className = 'page';
    page.innerHTML = `
        <div class="page-header">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
            <h2>Costs</h2>
            <div class="spacer"></div>
            <button class="btn btn-default btn-sm" id="btn-refresh-costs">Refresh</button>
        </div>
        <div class="costs-scroll" style="overflow-y:auto;flex:1;padding:16px 20px">
            <div class="stat-grid" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:24px">
                <div class="stat-card"><div class="stat-label">Total Spent</div><div class="stat-value" id="cost-total">$0.00</div></div>
                <div class="stat-card"><div class="stat-label">Total Calls</div><div class="stat-value" id="cost-calls">0</div></div>
                <div class="stat-card"><div class="stat-label">Top Model</div><div class="stat-value" id="cost-top-model" style="font-size:12px">-</div></div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">
                <div>
                    <h3 style="font-size:14px;color:var(--text-secondary);margin:0 0 8px">By Model</h3>
                    <table class="cost-table" id="cost-by-model"><thead><tr><th>Model</th><th>Calls</th><th>Cost</th><th></th></tr></thead><tbody></tbody></table>
                </div>
                <div>
                    <h3 style="font-size:14px;color:var(--text-secondary);margin:0 0 8px">By API Key</h3>
                    <table class="cost-table" id="cost-by-key"><thead><tr><th>Key</th><th>Calls</th><th>Cost</th><th></th></tr></thead><tbody></tbody></table>
                </div>
                <div>
                    <h3 style="font-size:14px;color:var(--text-secondary);margin:0 0 8px">By Model Category</h3>
                    <table class="cost-table" id="cost-by-model-cat"><thead><tr><th>Category</th><th>Calls</th><th>Cost</th><th></th></tr></thead><tbody></tbody></table>
                </div>
                <div>
                    <h3 style="font-size:14px;color:var(--text-secondary);margin:0 0 8px">By Task Category</h3>
                    <table class="cost-table" id="cost-by-task-cat"><thead><tr><th>Category</th><th>Calls</th><th>Cost</th><th></th></tr></thead><tbody></tbody></table>
                </div>
            </div>
        </div>
    `;
    document.getElementById('content').appendChild(page);

    function renderBreakdownTable(tableId, data, totalCost) {
        const tbody = document.querySelector('#' + tableId + ' tbody');
        tbody.innerHTML = '';
        for (const [name, info] of Object.entries(data)) {
            const pct = totalCost > 0 ? (info.cost / totalCost * 100) : 0;
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="font-size:12px;max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${name}">${name}</td>
                <td style="text-align:right">${info.calls}</td>
                <td style="text-align:right">$${info.cost.toFixed(3)}</td>
                <td style="width:60px"><div style="background:var(--accent);height:6px;border-radius:3px;width:${Math.min(100,pct)}%;opacity:0.7"></div></td>
            `;
            tbody.appendChild(tr);
        }
        if (Object.keys(data).length === 0) {
            const tr = document.createElement('tr');
            tr.innerHTML = '<td colspan="4" style="color:var(--text-muted);text-align:center">No data</td>';
            tbody.appendChild(tr);
        }
    }

    async function loadCosts() {
        try {
            const resp = await fetch('/api/cost-breakdown');
            const d = await resp.json();
            document.getElementById('cost-total').textContent = '$' + (d.total_cost || 0).toFixed(2);
            document.getElementById('cost-calls').textContent = d.total_calls || 0;
            const models = Object.entries(d.by_model || {});
            document.getElementById('cost-top-model').textContent = models.length > 0 ? models[0][0] : '-';
            renderBreakdownTable('cost-by-model', d.by_model || {}, d.total_cost);
            renderBreakdownTable('cost-by-key', d.by_api_key || {}, d.total_cost);
            renderBreakdownTable('cost-by-model-cat', d.by_model_category || {}, d.total_cost);
            renderBreakdownTable('cost-by-task-cat', d.by_task_category || {}, d.total_cost);
        } catch {}
    }

    document.getElementById('btn-refresh-costs').addEventListener('click', loadCosts);

    const obs = new MutationObserver(() => {
        if (page.classList.contains('active')) loadCosts();
    });
    obs.observe(page, { attributes: true, attributeFilter: ['class'] });
}


// ---------------------------------------------------------------------------
// Reconnect overlay
// ---------------------------------------------------------------------------
const overlay = document.createElement('div');
overlay.id = 'reconnect-overlay';
overlay.innerHTML = `
    <div class="spinner"></div>
    <div style="color:var(--text-secondary);font-size:14px">Reconnecting...</div>
`;
document.body.appendChild(overlay);

// ---------------------------------------------------------------------------
// Matrix Rain
// ---------------------------------------------------------------------------
function initMatrixRain() {
    const canvas = document.createElement('canvas');
    canvas.id = 'matrix-rain';
    document.getElementById('app').prepend(canvas);

    const ctx = canvas.getContext('2d');
    const chars = 'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789ΨΩΦΔΛΞΣΘабвгдежзиклмнопрстуфхцчшщэюя'.split('');
    const fontSize = 14;
    let columns = [];
    let w = 0, h = 0;

    function resize() {
        w = canvas.width = window.innerWidth - 80;
        h = canvas.height = window.innerHeight;
        const colCount = Math.floor(w / fontSize);
        while (columns.length < colCount) columns.push(Math.random() * h / fontSize | 0);
        columns.length = colCount;
    }
    resize();
    window.addEventListener('resize', resize);

    function draw() {
        ctx.fillStyle = 'rgba(13, 11, 15, 0.06)';
        ctx.fillRect(0, 0, w, h);
        ctx.fillStyle = '#ee3344';
        ctx.font = fontSize + 'px monospace';

        for (let i = 0; i < columns.length; i++) {
            const ch = chars[Math.random() * chars.length | 0];
            ctx.fillText(ch, i * fontSize, columns[i] * fontSize);
            if (columns[i] * fontSize > h && Math.random() > 0.975) {
                columns[i] = 0;
            }
            columns[i]++;
        }
    }

    setInterval(draw, 66);
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
initMatrixRain();
initChat();
initDashboard();
initSettings();
initLogs();
initVersions();
initCosts();
initAbout();
loadVersion();
showPage('chat');

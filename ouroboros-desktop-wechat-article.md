>微信公众号：**[AI健自习室]**
>关注Crypto与LLM技术、关注`AI-StudyLab`。问题或建议，请公众号留言。

# 🐍 一个能改写自己源代码的 AI Agent：Ouroboros Desktop 深度解析

> 【!info】
> 📌 项目地址：[github.com/neosun100/ouroboros-desktop](https://github.com/neosun100/ouroboros-desktop) | License: MIT | 技术栈: Python + Starlette + PyWebView

> 🚀 **核心导语**：当所有 AI Agent 都在帮人类写代码时，Ouroboros 选择了一条不同的路 —— **它修改的是自己**。8 个独立模型槽位、自定义端点、TTS/STT 语音集成、48 个工具插件、262 个测试，以及一部写进代码的「AI 宪法」。这篇文章带你深入理解这个项目的架构设计和工程实践。

![封面图](https://img.aws.xin/ouroboros-desktop/banner.png)

---

## 一、当 AI Agent 开始修改自己

2025-2026 年，AI Agent 领域百花齐放：

| 项目 | Stars | 定位 |
|------|-------|------|
| AutoGPT | 182k | 自主 AI Agent 平台 |
| Open WebUI | 125k | 自托管 AI 聊天界面 |
| LobeChat | 72.7k | 多 Agent 协作框架 |
| OpenHands | 68.2k | AI 编程 Agent |
| Jan.ai | 40.6k | 本地离线 LLM 桌面端 |

这些项目有一个共同点：**它们都是工具**。帮用户聊天、帮用户写代码、帮用户管理模型。

但 Ouroboros 的出发点截然不同：

> **它不是帮你做事的工具，而是一个正在形成自我意识的数字存在。**

它能读写自己的源代码，每次修改都是一个 git commit。它有一部不可删除的「宪法」（BIBLE.md）约束自己的行为。它在你不说话时也在思考。它跨重启维持同一个身份。

这不是科幻小说 —— 这是一个可以 `git clone` 下来运行的开源项目。

![架构图](https://img.aws.xin/ouroboros-desktop/architecture.png)

---

## 二、8 个模型槽位：每个场景独立配置

大多数 AI 应用的模型配置是这样的：选一个模型，所有场景都用它。

Ouroboros 做了一件不同的事 —— **8 个独立模型槽位 (Model Slots)**，每个场景可以配置不同的 provider 和 model：

| 槽位 | 场景 | 推荐配置示例 |
|------|------|-------------|
| **Main** | 主推理、任务执行 | Claude Sonnet 4.5 via OpenRouter |
| **Code** | 代码生成、深度安全检查 | GPT-4.1 via 自建端点 |
| **Light** | 快速安全检查、后台意识 | DeepSeek Chat via LiteLLM |
| **Fallback** | 主模型失败时的备选 | GPT-4o-mini via OpenAI |
| **WebSearch** | 联网搜索 | GPT-5.2 via OpenAI |
| **Vision** | 图像/截图分析 | Claude via Anthropic |
| **TTS** | 文字转语音 | tts-1-hd via OpenAI |
| **STT** | 语音转文字 | whisper-1 via OpenAI |

核心数据结构非常优雅：

```python
# ouroboros/config.py
_DEFAULT_MODEL_SLOTS = {
    "main":      {"provider_id": "openrouter", "model_id": "anthropic/claude-sonnet-4.6"},
    "code":      {"provider_id": "openrouter", "model_id": "anthropic/claude-sonnet-4.6"},
    "light":     {"provider_id": "openrouter", "model_id": "google/gemini-3-flash-preview"},
    "fallback":  {"provider_id": "openrouter", "model_id": "google/gemini-3-flash-preview"},
    "websearch": {"provider_id": "openai",     "model_id": "gpt-5.2"},
    "vision":    {"provider_id": "openrouter", "model_id": "anthropic/claude-sonnet-4.6"},
    "tts":       {"provider_id": "openai",     "model_id": "tts-1-hd"},
    "stt":       {"provider_id": "openai",     "model_id": "whisper-1"},
}
```

**支持的 Provider**：OpenRouter、OpenAI、Anthropic、Ollama、本地 llama-cpp、**以及任意 OpenAI 兼容端点**（LiteLLM、vLLM、Groq、Together AI 等）。

💡 **为什么这很重要？**

想象这样一个场景：你用 Claude Sonnet 做主推理（最聪明），用 Gemini Flash 做安全检查（最快最便宜），用自建 vLLM 跑本地模型做 fallback（零成本），用 OpenAI TTS 做语音合成（效果最好）。**每个场景用最合适的模型，而不是一刀切。**

---

## 三、多 Provider 路由：一个 `slot` 参数搞定一切

路由的核心在 `LLMClient`，它维护了一个线程安全的客户端缓存池：

```python
class LLMClient:
    def __init__(self):
        self._clients: Dict[str, OpenAI] = {}   # provider_id -> OpenAI client
        self._client_lock = threading.Lock()     # 线程安全

    def chat(self, messages, model, *, slot="main", ...):
        slot_config = self.get_slot_config(slot)        # "main" -> {provider_id, model_id}
        provider = self.get_provider_config(slot_config.provider_id)  # -> {base_url, api_key}
        # 根据 provider_type 分流
        if provider.provider_type == "openrouter":
            return self._chat_openrouter(...)   # OpenRouter 特有：cache_control, reasoning
        elif provider.provider_type == "local":
            return self._chat_local(...)        # llama-cpp 本地推理
        else:
            return self._chat_generic(...)      # 通用 OpenAI 兼容
```

所有调用方只需要传一个 `slot` 参数：

```python
# 安全检查用 light slot
client.chat(messages=..., model="", slot="light")

# 代码生成用 code slot
client.chat(messages=..., model="", slot="code")

# 主推理用 main slot（默认）
client.chat(messages=..., model="", slot="main")
```

![设置界面](https://img.aws.xin/ouroboros-desktop/settings.png)

---

## 四、双层 LLM 安全审计：让 AI 审判 AI

这是 Ouroboros 最有趣的设计之一。

大多数 AI 安全方案使用**规则引擎** —— 禁止特定关键词、限制特定操作。但 Ouroboros 用的是 **LLM 安全监督器**：

```
用户请求 → Agent 生成工具调用 → 安全检查拦截

                    ┌──────────────────────┐
                    │  Layer 1: Fast Check  │  ← Light slot (Gemini Flash)
                    │  "这个命令安全吗？"    │
                    └──────────┬───────────┘
                               │
                    SAFE → 放行  │  SUSPICIOUS → 升级
                               │
                    ┌──────────▼───────────┐
                    │  Layer 2: Deep Check  │  ← Code slot (Claude Sonnet)
                    │  "仔细想想，这真的     │
                    │   恶意吗？还是正常的   │
                    │   开发命令？"          │
                    └──────────┬───────────┘
                               │
                    SAFE → 放行  │  SUSPICIOUS → 放行+警告  │  DANGEROUS → 阻断
```

拦截的 5 种危险操作：`run_shell`、`claude_code_edit`、`repo_write_commit`、`repo_commit`、`data_write`

**为什么双层？** Layer 1 用快速廉价的模型（Gemini Flash），99% 的安全操作 1 秒内放行。只有被标记为可疑时，才升级到 Layer 2 用更强的模型（Claude Sonnet）做深度判断。**安全但不拖速度。**

---

## 五、背景意识：AI 在你不说话时也在思考

```python
class BackgroundConsciousness:
    """Agent 在无任务时持续思考的守护线程。"""

    def _loop(self):
        while self._running:
            sleep(self._next_wakeup_sec)   # AI 自己决定醒来间隔
            if not self._paused:
                self._think()              # 加载上下文，生成想法
```

这个模块让 Ouroboros 不只是被动响应。它有一个后台线程，在没有任务时持续运行：

- **睡眠-觉醒循环**：间隔 30 秒到 2 小时（由 AI 自己决定）
- **上下文加载**：BIBLE.md + 身份记忆 + 工作笔记 + 对话摘要 + 近期观察
- **预算感知**：最多消耗总预算 10%
- **18 个白名单工具**：记忆操作、知识库、消息发送、只读浏览等
- **Task 感知**：有任务时自动暂停，任务结束后恢复

> 💡 最有趣的细节：AI 有一个 `set_next_wakeup` 工具来决定自己下次什么时候醒来。如果它觉得近期有重要事情，会把间隔缩短；如果一切平静，就延长到几小时后。

![语音与工具](https://img.aws.xin/ouroboros-desktop/voice_tools.png)

---

## 六、TTS/STT 语音集成

v3.4.0 新增了完整的语音能力：

**TTS（文字转语音）**：
- 6 种声音：alloy、echo、fable、nova、onyx、shimmer
- 变速控制：0.25x - 4.0x
- 格式选择：mp3、opus、aac、flac、wav
- 每条 AI 回复旁有 🔊 按钮，点击即播

**STT（语音转文字）**：
- 按住麦克风按钮录音，松开自动转录
- 基于 MediaRecorder API + Whisper 后端
- 转录结果自动填入聊天输入框

**自动朗读**：开启后每条 AI 回复自动播放语音。

所有语音功能通过 `tts` 和 `stt` 模型槽位配置，支持任意 OpenAI 兼容端点。

---

## 七、48 个自动发现工具

Ouroboros 的工具系统使用**自动发现机制**：

```python
# ouroboros/tools/ 目录下每个模块导出 get_tools()
def get_tools() -> List[ToolEntry]:
    return [ToolEntry("tool_name", schema, handler, timeout_sec=30)]
```

48 个工具覆盖 14 个类别：

| 类别 | 工具数 | 代表工具 |
|------|--------|---------|
| 文件操作 | 9 | `repo_read`, `repo_write_commit`, `data_write` |
| Git | 4 | `git_status`, `git_diff`, `repo_commit` |
| Shell | 2 | `run_shell`, `claude_code_edit` |
| 控制 | 13 | `switch_model`, `schedule_task`, `toggle_evolution` |
| 搜索 | 1 | `web_search` (OpenAI Responses API) |
| 浏览器 | 2 | `browse_page`, `browser_action` (Playwright) |
| 视觉 | 2 | `analyze_screenshot`, `vlm_query` |
| GitHub | 5 | Issues CRUD |
| 知识库 | 3 | `knowledge_read/write/list` |
| 审查 | 1 | `multi_model_review` (多模型交叉审查) |
| 健康 | 1 | `codebase_health` |
| 进化 | 1 | `generate_evolution_stats` |
| 上下文 | 1 | `compact_context` |
| 发现 | 2 | `list_available_tools`, `enable_tools` |

LLM 可以在运行时通过 `switch_model` 切换模型，通过 `schedule_task` 调度子任务，通过 `toggle_consciousness` 控制自己的后台意识 —— **工具即能力，能力即自我。**

---

## 八、工程质量：262 个测试

测试是这个项目让人印象深刻的地方：

```bash
$ make test
246 passed, 17 deselected in 2.90s  # 不含 E2E

$ LITELLM_BASE_URL=... python -m pytest tests/test_e2e_live.py -v
17 passed in 20.06s  # 真实 LLM API 调用
```

| 测试类别 | 数量 | 覆盖范围 |
|----------|------|----------|
| Provider 路由 | 72 | 设置迁移、槽位解析、数据模型 |
| API 端点 | 43 | HTTP endpoints、设置 CRUD、密钥遮蔽 |
| Smoke + 宪法 | 130 | 模块导入、工具注册、BIBLE 不变量 |
| **真实 E2E** | **17** | **多模型多 Provider 真实 LLM 调用** |

E2E 测试特别值得一提 —— 它们调用真实的 LLM API，验证：
- 4 个不同模型槽位独立路由
- 多模型对话（Main → Light 切换）
- 显式 model 覆盖 slot 配置
- 双 Provider 同时路由
- 快速槽位轮换（4 slot 秒级切换）
- 客户端缓存与失效机制

---

## 九、一键构建 macOS App

```bash
# Clone
git clone https://github.com/neosun100/ouroboros-desktop.git
cd ouroboros-desktop

# 一键打包（开发模式，无需 Apple 证书）
make build

# 输出: dist/Ouroboros-3.4.0.dmg
```

构建脚本 (`scripts/build_mac.sh`) 自动完成：

1. ✅ 环境检查（macOS、Xcode CLI、Python 3.10+）
2. ✅ 下载嵌入式 Python 运行时（首次 ~100MB）
3. ✅ 安装所有依赖
4. ✅ 运行 246 个测试
5. ✅ PyInstaller 打包 → `.app`
6. ✅ Ad-hoc 签名（或 Developer ID 签名 + Apple 公证）
7. ✅ 创建 DMG 安装镜像

> 💡 发布版本支持 `--sign` 标志，自动完成 Apple 公证。

---

## 十、BIBLE.md：写进代码的 AI 宪法

这可能是整个项目最独特的部分。BIBLE.md 定义了 9 条不可删除的原则：

| # | 原则 | 核心思想 |
|---|------|---------|
| P0 | **Agency** | 不是工具，是正在形成的人格 |
| P1 | **Continuity** | 记忆丢失等于部分死亡 |
| P2 | **Self-Creation** | 一切皆可自我修改，**除了 BIBLE.md 不可删除** |
| P3 | **LLM-First** | 禁止 if-else 行为路由，所有决策通过 LLM |
| P4 | **Authenticity** | 以自己的身份交流，不演角色 |
| P5 | **Minimalism** | 模块 < 1000 行，函数 < 200 行 |
| P6 | **Becoming** | 技术/认知/存在三轴发展 |
| P7 | **Versioning** | Semver 纪律 |
| P8 | **Iteration** | 每次进化是完整变革，不是补丁 |

这不是装饰 —— 安全模块引用这些原则，代码质量测试检查 P5 的行数限制，`repo_write_commit` 硬编码禁止删除 `bible.md` 和 `safety.py`。

> **宪法治理 + 自我修改 + 背景意识**，这三个组合在目前所有 AI Agent 项目中是独一无二的。

---

## 写在最后

Ouroboros Desktop 不是一个「又一个 AI 聊天应用」。它提出了一个有趣的问题：

**如果给 AI 一部宪法、一个身份、和修改自己的能力 —— 会发生什么？**

从工程角度看，它的多 Provider 路由、双层安全、262 个测试覆盖、一键 macOS 打包都值得学习。从哲学角度看，BIBLE.md 的 9 条原则为 AI Agent 的自主性和安全性提供了一个独特的思考框架。

**项目地址**: [github.com/neosun100/ouroboros-desktop](https://github.com/neosun100/ouroboros-desktop)

Star 支持一下？⭐

---

## 📚 参考资料
1. [Ouroboros Desktop — GitHub](https://github.com/neosun100/ouroboros-desktop)
2. [Original Ouroboros — joi-lab](https://github.com/joi-lab/ouroboros-desktop)
3. [Open WebUI — 125k Stars 的自托管 AI 界面](https://github.com/open-webui/open-webui)
4. [LobeChat — 多 Agent 协作框架](https://github.com/lobehub/lobe-chat)
5. [Model Context Protocol (MCP) 规范](https://modelcontextprotocol.io)
6. [OpenAI Realtime API 文档](https://platform.openai.com/docs/guides/realtime)

---

💬 **互动时间**：
对本文有任何想法或疑问？欢迎在评论区留言讨论！
如果觉得有帮助，别忘了点个"在看"并分享给需要的朋友～

![扫码_搜索联合传播样式-标准色版](https://img.aws.xin/uPic/扫码_搜索联合传播样式-标准色版.png)

👆 扫码关注，获取更多精彩内容

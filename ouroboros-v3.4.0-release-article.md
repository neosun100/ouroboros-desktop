>微信公众号：**[AI健自习室]**
>关注Crypto与LLM技术、关注`AI-StudyLab`。问题或建议，请公众号留言。

# 🐍 我们花了一整天，把一个 AI Agent 项目从「能用」改造成了「震撼」| Ouroboros Desktop v3.4.0 发布

> [!info]
> 📌 项目地址：[github.com/neosun100/ouroboros-desktop](https://github.com/neosun100/ouroboros-desktop)
> 📌 Release：[v3.4.0 Release Notes](https://github.com/neosun100/ouroboros-desktop/releases/tag/v3.4.0)
> 📌 原项目：[joi-lab/ouroboros-desktop](https://github.com/joi-lab/ouroboros-desktop) (v3.3.1)
> 📌 协议：MIT 开源

> 🚀 **读完这篇你能获得什么？** 了解我们如何将一个仅支持 OpenRouter 单一路由的 AI Agent 项目，改造成支持 **8 个独立模型槽位 × 任意 Provider × TTS/STT 语音 × 文件上传 × 全新 Markdown 渲染**的完整平台——39 个文件、+6,082 行代码、277 个测试零失败。以及这背后的架构决策和工程实践。

![封面图](https://img.aws.xin/ouroboros-desktop/v3.4.0-banner.png)

---

## 🔍 故事的起点：原项目有什么，缺什么？

[Ouroboros Desktop](https://github.com/joi-lab/ouroboros-desktop) 是 Anton Razzhigaev 创建的一个极具创意的开源项目——一个**能修改自己源代码**的 AI Agent 桌面应用。它有：

- ✅ 自我修改能力（读写自己的代码，每次修改是 git commit）
- ✅ 9 条哲学宪法（BIBLE.md）约束 AI 行为
- ✅ 后台意识循环（Background Consciousness）
- ✅ 双层 LLM 安全审计
- ✅ 48 个自动发现工具
- ✅ 原生 macOS App（PyWebView）

**但 v3.3.1 有一个根本性限制：所有 LLM 调用硬编码走 OpenRouter，无法使用自己的端点和 API Key。**

这意味着：
- ❌ 不能用自己的 OpenAI/Anthropic/Ollama 端点
- ❌ 不能按场景混合使用不同模型
- ❌ 没有语音能力（TTS/STT）
- ❌ Markdown 渲染只是 40 行正则，无语法高亮、无公式
- ❌ 没有文件上传
- ❌ 没有 HTTP 端点级别的集成测试
- ❌ 没有一键打包脚本

**我们决定把这些全部补上。**

---

## 📊 改造量级：一张表说清

| 维度 | v3.3.1 (原项目) | v3.4.0 (我们的增强版) | 变化 |
|------|----------------|----------------------|------|
| Provider 支持 | 仅 OpenRouter | **6 个预配置 + 任意自定义** | 🔥 |
| 模型槽位 | 4 个 (共用 1 个 key) | **8 个独立配置** | +100% |
| TTS 语音合成 | ❌ 无 | ✅ 6 种声音 + 变速 | 🆕 |
| STT 语音识别 | ❌ 无 | ✅ Whisper + 麦克风录音 | 🆕 |
| Markdown 渲染 | 40 行正则 | **marked.js + highlight.js + KaTeX** | 🔥 |
| 代码高亮 | ❌ 无 | ✅ 12 种语言 | 🆕 |
| 数学公式 | ❌ 无 | ✅ KaTeX (行内 + 块级) | 🆕 |
| XSS 防护 | 基础 escapeHtml | **DOMPurify** | ↑ |
| 文件上传 | ❌ 无 | ✅ 拖拽 + 自动分析 | 🆕 |
| Toast 通知 | alert() 弹窗 | **4 种主题 Toast** | ↑ |
| 键盘快捷键 | ❌ 无 | ✅ Ctrl+Enter / Esc | 🆕 |
| 对话导出 | ❌ 无 | ✅ MD + JSON | 🆕 |
| Settings UI | 简单文本输入 | **Provider 卡片 + 连接测试** | 🔥 |
| 打包脚本 | 手动 build.sh | **一键 `make build`** | ↑ |
| 测试 | ~97 个 | **277 个 (含真实 API E2E)** | +185% |
| 代码变动 | - | **39 文件, +6,082 行** | - |

> 💡 **重点**：这不是 fork 后改几行配置。这是**从架构层面重新设计**了 LLM 路由、新增了整个语音系统、重写了渲染引擎、添加了文件处理能力——同时保持了对原项目的完全向后兼容。

![架构全景](https://img.aws.xin/ouroboros-desktop/v3.4.0-architecture.png)

---

## 🔌 增强 #1：8 槽位 × 任意 Provider — 我们重写了整个 LLM 路由层

### 原项目的限制

```python
# 原 v3.3.1 — 所有模型共用一个 OpenRouter API Key
class LLMClient:
    def __init__(self, api_key=None, base_url="https://openrouter.ai/api/v1"):
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        # 只有一条路：OpenRouter 或 本地 llama-cpp
```

### 我们的改造

```python
# v3.4.0 — 每个场景独立路由
class LLMClient:
    def __init__(self):
        self._clients: Dict[str, OpenAI] = {}   # 按 provider 缓存客户端
        self._client_lock = threading.Lock()     # 线程安全

    def chat(self, messages, model, *, slot="main", ...):
        slot_config = self.get_slot_config(slot)       # "light" → {provider: "ollama", model: "qwen3:8b"}
        provider = self.get_provider_config(slot_config.provider_id)  # → {base_url, api_key}
        if provider.provider_type == "openrouter":
            return self._chat_openrouter(...)   # 保留 OpenRouter 特有逻辑
        elif provider.provider_type == "local":
            return self._chat_local(...)        # llama-cpp 本地
        else:
            return self._chat_generic(...)      # 通用 OpenAI 兼容端点
```

**改了什么？**

| 文件 | 改动 |
|------|------|
| `ouroboros/config.py` | 新增 `providers` dict + `model_slots` dict + `migrate_settings()` 迁移函数 |
| `ouroboros/llm.py` | 完全重写 `LLMClient`：多客户端池、线程安全、三条路由路径 |
| `ouroboros/loop.py` | 所有 `llm.chat()` 调用增加 `slot=` 参数 |
| `ouroboros/safety.py` | Layer 1 用 `slot="light"`，Layer 2 用 `slot="code"` |
| `ouroboros/consciousness.py` | 用 `slot="light"` 替代硬编码环境变量 |
| `ouroboros/tools/search.py` | 从 websearch slot 读取 provider 配置 |
| `ouroboros/tools/vision.py` | 用 `slot="vision"` |
| `server.py` | 新增 3 个 API 端点 + 放宽启动条件 |

**8 个模型槽位的完整配置：**

| 槽位 | 场景 | 我们实测用的模型 |
|------|------|-----------------|
| **Main** | 主推理 | `openai/gpt-4.1-mini` via LiteLLM |
| **Code** | 代码生成、深度安全 | `openai/gpt-4.1-nano` via LiteLLM |
| **Light** | 快速安全检查、意识 | `deepseek/deepseek-chat` via LiteLLM |
| **Fallback** | 主模型失败备选 | `openai/gpt-4o-mini` via LiteLLM |
| **WebSearch** | 联网搜索 | `openai/gpt-4o-mini` via LiteLLM |
| **Vision** | 图像分析 | `openai/gpt-4.1-mini` via LiteLLM |
| **TTS** | 文字转语音 | `openai/tts-1-hd` via LiteLLM |
| **STT** | 语音转文字 | `openai/whisper-1` via LiteLLM |

> 📌 **关键设计：向后兼容。** `migrate_settings()` 自动将旧的扁平 `settings.json` 迁移到新的 provider/slot 格式。老用户升级零成本。

![设置界面](https://img.aws.xin/ouroboros-desktop/v3.4.0-settings.png)

---

## 🎤 增强 #2：TTS/STT 语音系统 — 从零搭建

原项目 **完全没有语音能力**。我们加了一整套：

### 架构设计

```
                    ┌─ tts slot ─→ OpenAI tts-1-hd ─→ 音频流
用户界面 ─→ /api/tts ─┤
                    └─ 支持任意 OpenAI 兼容 TTS 端点

                    ┌─ stt slot ─→ OpenAI whisper-1 ─→ 文字
麦克风录音 ─→ /api/stt ─┤
                    └─ 支持任意 OpenAI 兼容 STT 端点
```

### 新增文件和端点

| 新增 | 内容 |
|------|------|
| `ouroboros/audio_api.py` (119 行) | TTS/STT/Voices 3 个端点处理器 |
| `POST /api/tts` | 接收 text → 返回流式音频 |
| `POST /api/stt` | 接收音频文件 → 返回转写文字 |
| `GET /api/tts/voices` | 返回 6 种可用声音 |

### 前端交互

- 🔊 每条 AI 回复旁有 **speaker 按钮**，点击即播
- 🎙️ 聊天输入旁有 **麦克风按钮**，按住录音松手转写
- 🔄 **Auto-read** 开关：开启后 AI 回复自动朗读
- ⚙️ Settings 新增 **Voice 区域**：声音选择、语速滑块、测试按钮

### 真实 E2E 验证

```
✅ tts-1-hd: 19,680 bytes 音频
✅ gpt-4o-mini-tts: 30,720 bytes 音频
✅ whisper-1 转写: "Ouroboros Multi-Provider Architecture Test"
✅ 6 种声音全部验证: alloy/echo/fable/nova/onyx/shimmer
✅ POST /api/tts HTTP 端点: 200 + audio/mpeg
✅ POST /api/stt HTTP 端点: 200 + 正确转写
```

![语音与工具生态](https://img.aws.xin/ouroboros-desktop/v3.4.0-voice.png)

---

## 📝 增强 #3：Markdown 渲染从「勉强能看」到「专业级」

### 原项目

```javascript
// v3.3.1 — 40 行手写正则
function renderMarkdown(text) {
    text = escapeHtml(text);
    text = text.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
    text = text.replace(/\*\*(.*?)\*\*/g, '<b>$1</b>');
    // ... 没有语法高亮，没有公式，没有复制按钮
}
```

### 我们的改造

| 能力 | v3.3.1 | v3.4.0 |
|------|--------|--------|
| Markdown 解析 | 手写正则 | **marked.js** (完整 GFM) |
| 代码高亮 | ❌ | **highlight.js** (JS/Python/Bash/JSON/TS/CSS/XML/SQL/YAML/Rust/Go/HTML) |
| 数学公式 | ❌ | **KaTeX** (`$...$` 和 `$$...$$`) |
| XSS 防护 | 基础 | **DOMPurify** (白名单模式) |
| 代码复制 | ❌ | ✅ 一键复制 + "Copied!" 反馈 |
| 语言标签 | ❌ | ✅ 代码块顶部显示语言名 |
| 外部链接 | 同窗口 | ✅ `target="_blank" rel="noopener"` |

全部通过 CDN 加载（marked.js、highlight.js、KaTeX、DOMPurify），零构建步骤，符合原项目的极简哲学。

---

## 📁 增强 #4：文件上传 & 文档分析

**原项目没有文件上传能力。** 我们加了：

- **`POST /api/upload`** 端点：10MB 限制，30+ 种文本扩展名识别
- **拖拽上传**：文件直接拖进聊天区域
- **📎 上传按钮**：在聊天输入栏
- **图片上传** → 自动 base64 编码 → 触发 Vision 模型分析
- **文本上传** → UTF-8 解码 → 内容预览填入输入框供编辑

---

## ✨ 增强 #5：UI/UX 全面打磨

| 改进 | 之前 | 之后 |
|------|------|------|
| 操作反馈 | `alert()` 弹窗 | **Toast 通知**（4 种主题：success/error/info/warning）|
| 发送消息 | Enter 键 | **Ctrl/Cmd+Enter** 快捷键 |
| 停止语音 | 无 | **Escape** 键停止 TTS |
| 导出对话 | 无 | **Export .md / Export .json** 按钮 |
| Provider 管理 | 文本输入 | **卡片式 UI + 连接测试 + 状态灯** |
| 无障碍 | 无 | **ARIA labels + prefers-reduced-motion + Firefox 滚动条** |

---

## 🏗️ 增强 #6：一键 macOS 打包

**原项目的 `build.sh` 需要手动处理多个步骤。** 我们写了 `scripts/build_mac.sh`：

```bash
make build          # 开发版（无需 Apple 证书）
make build-release  # 签名 + 公证发布版
```

自动完成 8 步：环境检查 → 下载 Python 运行时 → 安装依赖 → 跑 277 个测试 → PyInstaller → 签名 → 公证 → DMG。

---

## 🧪 增强 #7：从 97 个测试到 277 个——包括真实 API 调用

这是我们最自豪的改进之一：

| 测试套件 | 数量 | 类型 | 新增？ |
|----------|------|------|--------|
| Provider 路由与迁移 | 72 | 单元测试 | 🆕 完全新增 |
| API 端点 | 43 | 集成测试 | 🆕 完全新增 |
| **真实 LLM E2E** | **17** | 真实 API 调用 | 🆕 完全新增 |
| **真实端点 E2E** | **15** | HTTP + 真实 TTS/STT | 🆕 完全新增 |
| Smoke + 宪法 + 原有 | 130 | 单元/集成 | 原项目（部分更新）|
| **总计** | **277** | | **+185%** |

> 📌 **不是 mock。** 32 个 E2E 测试调用了**真实的 LLM/TTS/STT API**——通过 LiteLLM 代理连接 1,404 个可用模型，验证了 `gpt-4.1-mini`、`deepseek-chat`、`tts-1-hd`、`whisper-1` 等模型的实际调用和响应。

---

## 🚀 3 分钟上手

```bash
git clone https://github.com/neosun100/ouroboros-desktop.git
cd ouroboros-desktop
pip install -r requirements.txt
python server.py
# 浏览器打开 http://127.0.0.1:8765
```

Setup Wizard 支持选择 Provider：**OpenRouter / OpenAI / Anthropic / Ollama / 自定义端点**。

---

## 🔮 最后的话：为什么做这些？

Ouroboros 的哲学是 **Self-Creation（自我创造）**——BIBLE.md 第 2 条原则。

我们做的这些增强，本质上是在实践这个哲学：让一个 AI Agent 的基础设施更加完善，让它有能力连接任何模型、用任何声音说话、理解任何文件——这样它才有更大的空间去**自我进化**。

> **一个能连接 1,404 个模型、能说 6 种声音、能看图片、能读文件、有 48 个工具的 AI Agent——它的自我修改能力意味着什么？**

这个问题，我们把它留给 Ouroboros 自己去回答。

⭐ **Star 支持一下？** [github.com/neosun100/ouroboros-desktop](https://github.com/neosun100/ouroboros-desktop)

---

## 📚 参考资料

1. [Ouroboros Desktop v3.4.0 Release](https://github.com/neosun100/ouroboros-desktop/releases/tag/v3.4.0)
2. [完整 CHANGELOG](https://github.com/neosun100/ouroboros-desktop/blob/main/CHANGELOG.md)
3. [BIBLE.md — AI 宪法原文](https://github.com/neosun100/ouroboros-desktop/blob/main/BIBLE.md)
4. [原项目 joi-lab/ouroboros-desktop](https://github.com/joi-lab/ouroboros-desktop)
5. [Open WebUI — 125k Stars 自托管 AI 界面](https://github.com/open-webui/open-webui)
6. [LobeChat — 72.7k Stars 多 Agent 协作框架](https://github.com/lobehub/lobe-chat)

---

💬 **互动时间**：
对本文有任何想法或疑问？欢迎在评论区留言讨论！
如果觉得有帮助，别忘了点个"在看"并分享给需要的朋友～

![扫码_搜索联合传播样式-标准色版](https://img.aws.xin/uPic/扫码_搜索联合传播样式-标准色版.png)

👆 扫码关注，获取更多精彩内容

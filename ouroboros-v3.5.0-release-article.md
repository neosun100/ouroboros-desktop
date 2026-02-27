>微信公众号：**[AI健自习室]**
>关注Crypto与LLM技术、关注`AI-StudyLab`。问题或建议，请公众号留言。

# 🔒 从代码审计中揪出 4 个严重 Bug：Ouroboros Desktop v3.5.0 安全加固实录

> [!info]
> 📌 项目地址：[github.com/neosun100/ouroboros-desktop](https://github.com/neosun100/ouroboros-desktop)
> 📌 Release：[v3.5.0](https://github.com/neosun100/ouroboros-desktop/releases/tag/v3.5.0)
> 📌 上一版本回顾：[v3.4.0 深度解析](https://github.com/neosun100/ouroboros-desktop/blob/main/ouroboros-v3.4.0-release-article.md)

> 🚀 **读完这篇你能获得什么？** 看一次真实的代码安全审计全过程——我们在自己写的代码里发现了 4 个严重漏洞（包括一个能永久丢失 API Key 的 bug），以及如何在一天内全部修复、新增 3 个 UI 功能、消灭外部 CDN 依赖，最终 278 个测试零失败交付。对所有做 AI 应用开发的人都有参考价值。

![封面图](https://img.aws.xin/ouroboros-desktop/v3.5.0-banner.png)

---

## 💀 事情是这样的

v3.4.0 刚发布不到 24 小时，我们就做了一件事：**对自己的代码做了一次全面的安全审计。**

审计结果让人冒冷汗——在 1,050 行的 `server.py`、634 行的 `llm.py` 和 2,000+ 行的 `app.js` 中，我们发现了：

| 严重程度 | 数量 | 最危险的 |
|----------|------|---------|
| 🔴 **Critical** | **4** | API Key 可能被永久覆盖为 `***` |
| 🟡 建议修复 | 9 | CDN 供应链风险、async/threading 混用 |
| 🟢 优化 | 7 | 轮询策略、magic numbers |

今天这篇文章，我们把这 4 个 Critical 级别的 Bug 拆开讲，每一个都值得所有 AI 应用开发者引以为戒。

---

## 🔴 Bug #1：保存设置 = 永久丢失 API Key

### 问题

这是最严重的一个。Ouroboros 的设置页面有一个 Provider 管理区，每个 Provider 的 API Key 在 **GET 请求时会被遮蔽**显示：

```
真实值: sk-or-v1-abc123def456789...
显示值: sk-or-v1...
```

问题在于：**当用户点击 Save 按钮时，前端发送的是遮蔽后的值。** 后端的 `api_settings_post` 直接做了 `.update(pdata)`——把 `"sk-or-v1..."` 写回了 `settings.json`。

```python
# v3.4.0 的代码（有 Bug）
for pid, pdata in body["providers"].items():
    current["providers"][pid].update(pdata)  # 💀 masked key 覆盖了真实 key
```

**后果**：用户只要在设置页面点一次 Save（哪怕什么都没改），所有 Provider 的 API Key 就**永久变成了 `sk-or-v1...`**。下次启动时，所有 LLM 调用都会因为无效 Key 失败。

### 修复

```python
# v3.5.0 修复
for pid, pdata in body["providers"].items():
    if pid in current["providers"]:
        for k, v in pdata.items():
            if k == "api_key" and isinstance(v, str) and ("..." in v or v == "***"):
                continue  # ✅ 跳过遮蔽值，保留真实 key
            current["providers"][pid][k] = v
```

> 📌 **教训**：任何涉及「显示遮蔽 + 回写」的场景，后端必须做**回写保护**。这个 Bug 在 AWS Console、Stripe Dashboard 等产品中也曾出现过，是一个经典的安全反模式。

---

## 🔴 Bug #2：改了设置不生效，要重启才行

### 问题

`server.py` 在保存设置后尝试刷新 LLM 客户端缓存：

```python
# v3.4.0 的代码（有 Bug）
try:
    from ouroboros.llm import invalidate_clients  # 💀 这个函数不存在！
    invalidate_clients()
except ImportError:
    pass  # 静默吞掉，什么都没发生
```

`ouroboros/llm.py` 中根本**没有** `invalidate_clients` 这个模块级函数。`LLMClient` 有 `.invalidate_all()` 实例方法，但没有被任何代码调用。`except ImportError: pass` 把错误静默吞掉了。

**后果**：用户在设置页面更换 API Key 或 Provider 后，LLM 客户端继续使用**旧的凭据**，直到重启服务器。

### 修复

```python
# v3.5.0 — ouroboros/llm.py 新增模块级函数
_global_client: Optional[LLMClient] = None

def get_global_client() -> LLMClient:
    global _global_client
    if _global_client is None:
        _global_client = LLMClient()
    return _global_client

def invalidate_clients() -> None:
    global _global_client
    if _global_client is not None:
        _global_client.invalidate_all()
    _global_client = None
```

> 📌 **教训**：`except ImportError: pass` 是一个危险模式。它会隐藏真正的 bug。至少应该 `log.warning()`。

![安全审计发现](https://img.aws.xin/ouroboros-desktop/v3.5.0-audit.png)

---

## 🔴 Bug #3：多线程竞态 — 同一个 Provider 创建多个客户端

### 问题

`LLMClient._get_client_for_provider()` 使用了「检查-创建」两步操作，但锁的范围不够：

```python
# v3.4.0 的代码（有竞态）
def _get_client_for_provider(self, provider_id):
    with self._client_lock:
        if provider_id in self._clients:
            return self._clients[provider_id]
    # 💀 锁已释放！另一个线程也进到这里
    config = self.get_provider_config(provider_id)
    client = OpenAI(base_url=config.base_url, ...)
    with self._client_lock:
        self._clients[provider_id] = client  # 可能覆盖另一个线程刚创建的
    return client
```

这是经典的 **TOCTOU (Time-of-Check-Time-of-Use)** 竞态条件。当多个 Worker 线程同时请求同一个 Provider 时，会重复创建 OpenAI 客户端对象。

### 修复

```python
# v3.5.0 — 整个创建过程在锁内完成
def _get_client_for_provider(self, provider_id):
    with self._client_lock:
        if provider_id in self._clients:
            return self._clients[provider_id]
        # 还在锁内 ✅ — 不会有第二个线程进来
        config = self.get_provider_config(provider_id)
        client = OpenAI(base_url=config.base_url, ...)
        self._clients[provider_id] = client
        return client
```

> 📌 **教训**：「检查是否存在 → 不存在则创建」这个模式在多线程环境下**必须原子化**。要么整个操作在锁内，要么用 `dict.setdefault()` + `threading.Lock`。

---

## 🔴 Bug #4：SSRF — 让服务器向任意 URL 发请求

### 问题

`POST /api/providers/test` 接口允许用户传入任意 `base_url`，服务器会向该 URL 发送带 API Key 的 HTTP 请求：

```python
# v3.4.0 的代码（有 SSRF 风险）
base_url = body.get("base_url", "")  # 用户控制
api_key = body.get("api_key", "")    # 用户控制
client = OpenAI(base_url=base_url, api_key=api_key)
client.models.list()  # 💀 向任意 URL 发请求
```

虽然服务器默认绑定 `127.0.0.1`，但如果通过端口转发暴露，攻击者可以让服务器向**内网任意地址**发请求（SSRF），甚至泄露 API Key 到恶意服务器。

### 修复

```python
# v3.5.0 — URL 白名单验证
from urllib.parse import urlparse
parsed = urlparse(base_url)
is_localhost = parsed.hostname in ("127.0.0.1", "localhost", "0.0.0.0", "::1")
if parsed.scheme not in ("https",) and not is_localhost:
    return JSONResponse({"status": "error", "error": "Only HTTPS or localhost URLs allowed"})
```

> 📌 **教训**：任何接受用户输入 URL 的接口都必须做 scheme/host 验证。SSRF 是 OWASP Top 10 漏洞之一。

---

## ✨ 不只是修 Bug — 3 个新功能

修完安全问题后，我们还加了几个一直想做的功能：

### 💭 Thinking/Reasoning 展示

随着 Claude Extended Thinking、DeepSeek R1、OpenAI o-series 等推理模型的普及，展示 AI 的思考过程成为刚需。

v3.5.0 新增了可折叠的推理块：

```
💭 Thought for 3.2s          ← 折叠状态，点击展开
┌─────────────────────────────┐
│ Let me think about this...  │  ← 展开后显示完整推理
│ First, I need to consider   │
│ the security implications...│
└─────────────────────────────┘
```

### ⚙️ Tool Call 进度

当 AI 调用工具时，现在会实时显示状态：

```
⚙️ run_shell ⏳  → ⚙️ run_shell ✅
⚙️ web_search ⏳ → ⚙️ web_search ✅
```

### 📊 Token Budget 栏

每次 AI 回复后，底部显示 token 使用量和成本：

```
Tokens: 1,234 (890 in / 344 out / 156 cached)    $0.0042
```

![新功能展示](https://img.aws.xin/ouroboros-desktop/v3.5.0-features.png)

---

## 📦 消灭 CDN 依赖 — 供应链安全

v3.4.0 通过 CDN 加载了 15 个外部脚本（marked.js、highlight.js、DOMPurify、KaTeX）。这在桌面应用中是一个安全隐患——CDN 被入侵意味着恶意代码直接在你的应用上下文中执行，能读取所有 API Key。

v3.5.0 把所有依赖**打包到本地**：

```
web/vendor/
├── marked.min.js          (markdown 解析)
├── hljs-core.min.js       (代码高亮核心)
├── hljs-{12种语言}.min.js  (语法定义)
├── purify.min.js           (XSS 防护)
├── katex.min.js            (数学公式)
├── katex.min.css
└── atom-one-dark.min.css   (代码高亮主题)
→ 17 个文件，共 464KB
```

```html
<!-- v3.4.0: CDN 加载（有风险） -->
<script src="https://cdn.jsdelivr.net/npm/marked@15.0.0/marked.min.js"></script>

<!-- v3.5.0: 本地加载（安全） -->
<script src="/static/vendor/marked.min.js"></script>
```

> 📌 **原则**：桌面应用不应该依赖外部 CDN。所有代码都应该是本地可审计的。

---

## ⚡ 性能优化：两个看不见的改进

### Dashboard 轮询

```javascript
// v3.4.0: 无论用户在哪个页面，每 3 秒请求一次
setInterval(updateDashboard, 3000);

// v3.5.0: 仅在 Dashboard 页面活跃时轮询
setInterval(() => {
    if (state.activePage === 'dashboard') updateDashboard();
}, 3000);
```

### Matrix Rain 动画

```javascript
// v3.4.0: 即使标签页隐藏也在持续渲染
setInterval(draw, 66);

// v3.5.0: 使用 rAF + 可见性检查
function matrixDraw(ts) {
    if (document.hidden) { requestAnimationFrame(matrixDraw); return; }
    if (ts - lastFrame < 66) { requestAnimationFrame(matrixDraw); return; }
    // ... draw
    requestAnimationFrame(matrixDraw);
}
```

![性能与安全](https://img.aws.xin/ouroboros-desktop/v3.5.0-perf.png)

---

## 📊 v3.5.0 完整变更清单

| 类别 | 变更 | 严重程度 |
|------|------|----------|
| **安全** | Masked API key 回写保护 | 🔴 Critical |
| **安全** | `invalidate_clients()` 模块级函数 | 🔴 Critical |
| **安全** | TOCTOU 竞态修复（全锁范围） | 🔴 Critical |
| **安全** | SSRF 防护（URL scheme 白名单） | 🔴 Critical |
| **安全** | CDN 依赖本地化（17 文件 464KB） | 🟡 供应链 |
| **安全** | 上传文件名 sanitize（路径遍历防护） | 🟡 预防 |
| **功能** | Thinking/Reasoning 折叠块 | 🆕 |
| **功能** | Tool Call 进度指示 | 🆕 |
| **功能** | Token Budget 使用量栏 | 🆕 |
| **功能** | Console.error → Toast 通知 | 🆕 |
| **优化** | Dashboard 条件轮询 | ⚡ |
| **优化** | Matrix Rain rAF + visibility | ⚡ |
| **修复** | 文件上传类型检测（elif） | 🟢 |
| **测试** | 278 个测试，零失败 | ✅ |

---

## 🚀 升级方式

```bash
cd ouroboros-desktop
git pull
# 自动向后兼容，无需额外操作
```

如果你是新用户：

```bash
git clone https://github.com/neosun100/ouroboros-desktop.git
cd ouroboros-desktop
pip install -r requirements.txt
python server.py
```

---

## 💡 写在最后

这次审计给我们最大的启示是：**自信写完的代码里一定有 bug，而且 bug 往往藏在你最「确定没问题」的地方。**

API Key 遮蔽显示？"当然没问题，前端不会发回遮蔽值的。"——**会的。**

客户端缓存失效？"当然没问题，我调了 `invalidate_clients()`。"——**那个函数不存在。**

`except ImportError: pass`？"这只是个安全降级。"——**这隐藏了真正的 bug。**

如果你也在做 AI 应用，建议定期对自己的代码做一次全面审计。不用请外部团队，就用 AI 帮你审——它会找到你看不到的东西。

⭐ [github.com/neosun100/ouroboros-desktop](https://github.com/neosun100/ouroboros-desktop)

---

## 📚 参考资料

1. [Ouroboros Desktop v3.5.0 Release](https://github.com/neosun100/ouroboros-desktop/releases/tag/v3.5.0)
2. [完整 CHANGELOG](https://github.com/neosun100/ouroboros-desktop/blob/main/CHANGELOG.md)
3. [OWASP Top 10 — Server-Side Request Forgery (SSRF)](https://owasp.org/Top10/A10_2021-Server-Side_Request_Forgery_%28SSRF%29/)
4. [TOCTOU Race Condition — CWE-367](https://cwe.mitre.org/data/definitions/367.html)
5. [v3.4.0 深度解析文章](https://github.com/neosun100/ouroboros-desktop/blob/main/ouroboros-v3.4.0-release-article.md)

---

💬 **互动时间**：
对本文有任何想法或疑问？欢迎在评论区留言讨论！
如果觉得有帮助，别忘了点个"在看"并分享给需要的朋友～

![扫码_搜索联合传播样式-标准色版](https://img.aws.xin/uPic/扫码_搜索联合传播样式-标准色版.png)

👆 扫码关注，获取更多精彩内容

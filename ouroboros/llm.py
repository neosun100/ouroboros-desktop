"""
Ouroboros — LLM client (multi-provider).

The only module that communicates with LLM APIs.
Supports OpenRouter, OpenAI, Anthropic, Ollama, local llama-cpp, and any
OpenAI-compatible endpoint via the provider/slot architecture in config.py.

Contract: chat(), default_model(), available_models(), add_usage(),
          get_provider_config(), get_slot_config().
"""

from __future__ import annotations

import copy
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

DEFAULT_LIGHT_MODEL = "google/gemini-3-flash-preview"


# ---------------------------------------------------------------------------
# Dataclasses for provider/slot configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderConfig:
    """Immutable provider configuration."""
    provider_id: str
    name: str
    provider_type: str  # "openrouter"|"openai"|"anthropic"|"ollama"|"local"|"custom"
    base_url: str
    api_key: str


@dataclass(frozen=True)
class SlotConfig:
    """Which provider+model a slot uses."""
    provider_id: str
    model_id: str


# ---------------------------------------------------------------------------
# Utility functions (unchanged from original)
# ---------------------------------------------------------------------------

def normalize_reasoning_effort(value: str, default: str = "medium") -> str:
    allowed = {"none", "minimal", "low", "medium", "high", "xhigh"}
    v = str(value or "").strip().lower()
    return v if v in allowed else default


def reasoning_rank(value: str) -> int:
    order = {"none": 0, "minimal": 1, "low": 2, "medium": 3, "high": 4, "xhigh": 5}
    return int(order.get(str(value or "").strip().lower(), 3))


def add_usage(total: Dict[str, Any], usage: Dict[str, Any]) -> None:
    """Accumulate usage from one LLM call into a running total."""
    for k in ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "cache_write_tokens"):
        total[k] = int(total.get(k) or 0) + int(usage.get(k) or 0)
    if usage.get("cost"):
        total["cost"] = float(total.get("cost") or 0) + float(usage["cost"])


def fetch_openrouter_pricing() -> Dict[str, Tuple[float, float, float]]:
    """
    Fetch current pricing from OpenRouter API.

    Returns dict of {model_id: (input_per_1m, cached_per_1m, output_per_1m)}.
    Returns empty dict on failure.
    """
    try:
        import requests
    except ImportError:
        log.warning("requests not installed, cannot fetch pricing")
        return {}

    try:
        url = "https://openrouter.ai/api/v1/models"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()

        data = resp.json()
        models = data.get("data", [])

        # Prefixes we care about
        prefixes = ("anthropic/", "openai/", "google/", "meta-llama/", "x-ai/", "qwen/")

        pricing_dict = {}
        for model in models:
            model_id = model.get("id", "")
            if not model_id.startswith(prefixes):
                continue

            pricing = model.get("pricing", {})
            if not pricing or not pricing.get("prompt"):
                continue

            # OpenRouter pricing is in dollars per token (raw values)
            raw_prompt = float(pricing.get("prompt", 0))
            raw_completion = float(pricing.get("completion", 0))
            raw_cached_str = pricing.get("input_cache_read")
            raw_cached = float(raw_cached_str) if raw_cached_str else None

            # Convert to per-million tokens
            prompt_price = round(raw_prompt * 1_000_000, 4)
            completion_price = round(raw_completion * 1_000_000, 4)
            if raw_cached is not None:
                cached_price = round(raw_cached * 1_000_000, 4)
            else:
                cached_price = round(prompt_price * 0.1, 4)  # fallback: 10% of prompt

            # Sanity check: skip obviously wrong prices
            if prompt_price > 1000 or completion_price > 1000:
                log.warning(f"Skipping {model_id}: prices seem wrong (prompt={prompt_price}, completion={completion_price})")
                continue

            pricing_dict[model_id] = (prompt_price, cached_price, completion_price)

        log.info(f"Fetched pricing for {len(pricing_dict)} models from OpenRouter")
        return pricing_dict

    except Exception as e:
        log.warning(f"Failed to fetch OpenRouter pricing: {e}")
        return {}


# ---------------------------------------------------------------------------
# Multi-provider LLM Client
# ---------------------------------------------------------------------------

class LLMClient:
    """Multi-provider LLM client.

    Routes calls to the correct API endpoint based on provider/slot
    configuration. Maintains a thread-safe cache of OpenAI client instances.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://openrouter.ai/api/v1",
    ):
        # Legacy params for backwards compat — used as fallback for OpenRouter
        self._legacy_api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self._legacy_base_url = base_url
        self._clients: Dict[str, Any] = {}  # provider_id -> OpenAI client
        self._client_lock = threading.Lock()

    # --- Provider/Slot config resolution ---

    @staticmethod
    def get_provider_config(provider_id: str) -> Optional[ProviderConfig]:
        """Load provider config from settings."""
        from ouroboros.config import load_settings
        settings = load_settings()
        providers = settings.get("providers", {})
        p = providers.get(provider_id)
        if not p:
            return None
        return ProviderConfig(
            provider_id=provider_id,
            name=p.get("name", provider_id),
            provider_type=p.get("type", "custom"),
            base_url=p.get("base_url", ""),
            api_key=p.get("api_key", ""),
        )

    @staticmethod
    def get_slot_config(slot: str) -> SlotConfig:
        """Load slot configuration from settings."""
        from ouroboros.config import load_settings
        settings = load_settings()
        slots = settings.get("model_slots", {})
        s = slots.get(slot, {})
        return SlotConfig(
            provider_id=s.get("provider_id", "openrouter"),
            model_id=s.get("model_id", ""),
        )

    # --- Client management (thread-safe) ---

    def _get_client_for_provider(self, provider_id: str) -> Any:
        """Get or create an OpenAI client for a provider. Thread-safe."""
        with self._client_lock:
            if provider_id in self._clients:
                return self._clients[provider_id]

        config = self.get_provider_config(provider_id)
        if not config:
            # Fallback: try legacy OpenRouter client
            log.warning(f"Provider '{provider_id}' not configured, falling back to legacy")
            config = ProviderConfig(
                provider_id="openrouter",
                name="OpenRouter (legacy)",
                provider_type="openrouter",
                base_url=self._legacy_base_url,
                api_key=self._legacy_api_key,
            )

        from openai import OpenAI
        extra_headers = {}
        if config.provider_type == "openrouter":
            extra_headers = {
                "HTTP-Referer": "https://ouroboros.local/",
                "X-Title": "Ouroboros",
            }

        client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key or "no-key",
            default_headers=extra_headers if extra_headers else None,
        )

        with self._client_lock:
            self._clients[provider_id] = client
        return client

    def invalidate_client(self, provider_id: str) -> None:
        """Remove cached client (e.g., after settings change)."""
        with self._client_lock:
            self._clients.pop(provider_id, None)

    def invalidate_all(self) -> None:
        """Remove all cached clients."""
        with self._client_lock:
            self._clients.clear()

    # --- Legacy client accessors (for backwards compat) ---

    def _get_client(self):
        """Legacy: get OpenRouter client."""
        return self._get_client_for_provider("openrouter")

    def _get_local_client(self):
        """Legacy: get local llama-cpp client."""
        return self._get_client_for_provider("local")

    # --- Message/tool cleaning ---

    @staticmethod
    def _strip_cache_control(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Strip cache_control from message content blocks (OpenRouter/Anthropic-only)."""
        cleaned = copy.deepcopy(messages)
        for msg in cleaned:
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        block.pop("cache_control", None)
        return cleaned

    @staticmethod
    def _flatten_multipart_content(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Flatten multipart content blocks to plain strings (for local/ollama)."""
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                msg["content"] = "\n\n".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                )
        return messages

    @staticmethod
    def _clean_tools(tools: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """Remove cache_control from tools."""
        if not tools:
            return None
        return [{k: v for k, v in t.items() if k != "cache_control"} for t in tools]

    # --- Cost fetching ---

    def _fetch_generation_cost(self, generation_id: str, provider: ProviderConfig) -> Optional[float]:
        """Fetch cost from OpenRouter Generation API as fallback."""
        try:
            import requests
            base = provider.base_url.rstrip("/")
            url = f"{base}/generation?id={generation_id}"
            headers = {"Authorization": f"Bearer {provider.api_key}"}
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data") or {}
                cost = data.get("total_cost") or data.get("usage", {}).get("cost")
                if cost is not None:
                    return float(cost)
            # Generation might not be ready yet — retry once after short delay
            time.sleep(0.5)
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("data") or {}
                cost = data.get("total_cost") or data.get("usage", {}).get("cost")
                if cost is not None:
                    return float(cost)
        except Exception:
            log.debug("Failed to fetch generation cost from OpenRouter", exc_info=True)
        return None

    # --- Main chat entry point ---

    def chat(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        reasoning_effort: str = "medium",
        max_tokens: int = 16384,
        tool_choice: str = "auto",
        use_local: bool = False,
        slot: str = "main",
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Single LLM call routed through the appropriate provider.

        Args:
            messages: Conversation messages.
            model: Model ID (overrides slot config if non-empty).
            tools: Tool definitions for function calling.
            reasoning_effort: Effort level (none/low/medium/high/xhigh).
            max_tokens: Max response tokens.
            tool_choice: Tool choice strategy.
            use_local: DEPRECATED — use slot config instead.
            slot: Model slot name (main/code/light/fallback/websearch/vision).

        Returns:
            (response_message_dict, usage_dict with cost)
        """
        # Legacy use_local override
        if use_local:
            return self._chat_local(messages, tools, max_tokens, tool_choice)

        # Resolve provider from slot config
        slot_config = self.get_slot_config(slot)
        provider_config = self.get_provider_config(slot_config.provider_id)

        if not provider_config:
            # Fallback to legacy OpenRouter behavior
            log.warning(f"Provider '{slot_config.provider_id}' not found, using legacy OpenRouter")
            provider_config = ProviderConfig(
                provider_id="openrouter",
                name="OpenRouter (legacy)",
                provider_type="openrouter",
                base_url=self._legacy_base_url,
                api_key=self._legacy_api_key,
            )

        # Model: explicit arg > slot config
        effective_model = model if model else slot_config.model_id

        # Route based on provider type
        ptype = provider_config.provider_type
        if ptype == "openrouter":
            return self._chat_openrouter(
                messages, effective_model, tools, reasoning_effort,
                max_tokens, tool_choice, provider_config,
            )
        elif ptype == "local":
            return self._chat_local(messages, tools, max_tokens, tool_choice)
        else:
            # Generic OpenAI-compatible: openai, anthropic, ollama, custom
            return self._chat_generic(
                messages, effective_model, tools, reasoning_effort,
                max_tokens, tool_choice, provider_config,
            )

    # --- Provider-specific chat methods ---

    def _chat_local(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        max_tokens: int,
        tool_choice: str,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Send a chat request to the local llama-cpp-python server."""
        client = self._get_client_for_provider("local")

        clean_messages = self._strip_cache_control(messages)
        self._flatten_multipart_content(clean_messages)
        clean_tools = self._clean_tools(tools)

        # Cap max_tokens to fit within the model's context window
        local_max = min(max_tokens, 2048)
        try:
            from ouroboros.local_model import get_manager
            ctx_len = get_manager().get_context_length()
            if ctx_len > 0:
                local_max = min(max_tokens, max(256, ctx_len // 4))
        except Exception:
            pass

        kwargs: Dict[str, Any] = {
            "model": "local-model",
            "messages": clean_messages,
            "max_tokens": local_max,
        }
        if clean_tools:
            kwargs["tools"] = clean_tools
            kwargs["tool_choice"] = tool_choice

        resp = client.chat.completions.create(**kwargs)
        resp_dict = resp.model_dump()
        usage = resp_dict.get("usage") or {}
        choices = resp_dict.get("choices") or [{}]
        msg = (choices[0] if choices else {}).get("message") or {}

        usage["cost"] = 0.0
        return msg, usage

    def _chat_openrouter(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        reasoning_effort: str,
        max_tokens: int,
        tool_choice: str,
        provider: ProviderConfig,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Send a chat request to OpenRouter."""
        client = self._get_client_for_provider(provider.provider_id)
        effort = normalize_reasoning_effort(reasoning_effort)

        extra_body: Dict[str, Any] = {
            "reasoning": {"effort": effort, "exclude": True},
        }

        # Pin Anthropic models to Anthropic provider for prompt caching
        if model.startswith("anthropic/"):
            extra_body["provider"] = {
                "order": ["Anthropic"],
                "allow_fallbacks": False,
                "require_parameters": True,
            }

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "extra_body": extra_body,
        }
        if tools:
            tools_with_cache = list(tools)  # shallow copy
            if tools_with_cache:
                last_tool = {**tools_with_cache[-1]}  # copy last tool
                last_tool["cache_control"] = {"type": "ephemeral", "ttl": "1h"}
                tools_with_cache[-1] = last_tool
            kwargs["tools"] = tools_with_cache
            kwargs["tool_choice"] = tool_choice

        resp = client.chat.completions.create(**kwargs)
        return self._parse_response(resp, model, provider)

    def _chat_generic(
        self,
        messages: List[Dict[str, Any]],
        model: str,
        tools: Optional[List[Dict[str, Any]]],
        reasoning_effort: str,
        max_tokens: int,
        tool_choice: str,
        provider: ProviderConfig,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Generic OpenAI-compatible endpoint (OpenAI, Anthropic, Ollama, custom)."""
        client = self._get_client_for_provider(provider.provider_id)

        # Strip OpenRouter-specific features
        clean_messages = self._strip_cache_control(messages)

        # Ollama needs flattened content
        if provider.provider_type == "ollama":
            self._flatten_multipart_content(clean_messages)

        clean_tools = self._clean_tools(tools)

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": clean_messages,
            "max_tokens": max_tokens,
        }

        # Only OpenAI supports reasoning param natively
        if provider.provider_type == "openai":
            effort = normalize_reasoning_effort(reasoning_effort)
            kwargs["extra_body"] = {"reasoning": {"effort": effort}}

        if clean_tools:
            kwargs["tools"] = clean_tools
            kwargs["tool_choice"] = tool_choice

        resp = client.chat.completions.create(**kwargs)
        return self._parse_response(resp, model, provider)

    # --- Response parsing ---

    def _parse_response(
        self,
        resp: Any,
        model: str,
        provider: ProviderConfig,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Unified response parsing with cost extraction."""
        resp_dict = resp.model_dump()
        usage = resp_dict.get("usage") or {}
        choices = resp_dict.get("choices") or [{}]
        msg = (choices[0] if choices else {}).get("message") or {}

        # Extract cached tokens from various response formats
        if not usage.get("cached_tokens"):
            prompt_details = usage.get("prompt_tokens_details") or {}
            if isinstance(prompt_details, dict) and prompt_details.get("cached_tokens"):
                usage["cached_tokens"] = int(prompt_details["cached_tokens"])

        if not usage.get("cache_write_tokens"):
            prompt_details_for_write = usage.get("prompt_tokens_details") or {}
            if isinstance(prompt_details_for_write, dict):
                cache_write = (prompt_details_for_write.get("cache_write_tokens")
                              or prompt_details_for_write.get("cache_creation_tokens")
                              or prompt_details_for_write.get("cache_creation_input_tokens"))
                if cache_write:
                    usage["cache_write_tokens"] = int(cache_write)

        # OpenRouter: fetch generation cost if not in response
        if not usage.get("cost") and provider.provider_type == "openrouter":
            gen_id = resp_dict.get("id") or ""
            if gen_id:
                cost = self._fetch_generation_cost(gen_id, provider)
                if cost is not None:
                    usage["cost"] = cost

        # Non-OpenRouter: set cost to 0 if not provided
        if not usage.get("cost") and provider.provider_type != "openrouter":
            usage["cost"] = 0.0

        return msg, usage

    # --- Vision query ---

    def vision_query(
        self,
        prompt: str,
        images: List[Dict[str, Any]],
        model: str = "",
        max_tokens: int = 1024,
        reasoning_effort: str = "low",
        slot: str = "vision",
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Send a vision query to an LLM. Lightweight — no tools, no loop.

        Args:
            prompt: Text instruction for the model
            images: List of image dicts with {"url": ...} or {"base64": ..., "mime": ...}
            model: VLM-capable model ID (empty = use slot config)
            max_tokens: Max response tokens
            reasoning_effort: Effort level
            slot: Model slot to use (default: "vision")

        Returns:
            (text_response, usage_dict)
        """
        # Build multipart content
        content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
        for img in images:
            if "url" in img:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img["url"]},
                })
            elif "base64" in img:
                mime = img.get("mime", "image/png")
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{img['base64']}"},
                })
            else:
                log.warning("vision_query: skipping image with unknown format: %s", list(img.keys()))

        messages = [{"role": "user", "content": content}]
        response_msg, usage = self.chat(
            messages=messages,
            model=model,
            tools=None,
            reasoning_effort=reasoning_effort,
            max_tokens=max_tokens,
            slot=slot,
        )
        text = response_msg.get("content") or ""
        return text, usage

    # --- Model introspection ---

    def default_model(self) -> str:
        """Return the main model from slot config (falls back to env)."""
        try:
            slot = self.get_slot_config("main")
            if slot.model_id:
                return slot.model_id
        except Exception:
            pass
        return os.environ.get("OUROBOROS_MODEL", "anthropic/claude-sonnet-4.6")

    def available_models(self) -> List[str]:
        """Return list of unique models from all configured slots."""
        try:
            from ouroboros.config import load_settings
            settings = load_settings()
            slots = settings.get("model_slots", {})
            seen = set()
            models = []
            for slot_name in ("main", "code", "light", "fallback"):
                mid = slots.get(slot_name, {}).get("model_id", "")
                if mid and mid not in seen:
                    seen.add(mid)
                    models.append(mid)
            return models
        except Exception:
            pass
        # Fallback to legacy env vars
        main = os.environ.get("OUROBOROS_MODEL", "anthropic/claude-sonnet-4.6")
        code = os.environ.get("OUROBOROS_MODEL_CODE", "")
        light = os.environ.get("OUROBOROS_MODEL_LIGHT", "")
        models = [main]
        if code and code != main:
            models.append(code)
        if light and light != main and light != code:
            models.append(light)
        return models

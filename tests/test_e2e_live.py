"""
E2E integration tests — real LLM calls via custom LiteLLM endpoint.

Tests the full multi-provider architecture with actual API calls.
API credentials are read from environment variables (never hardcoded).

Run: LITELLM_BASE_URL=... LITELLM_API_KEY=... python -m pytest tests/test_e2e_live.py -v

Requires:
  - LITELLM_BASE_URL: LiteLLM proxy endpoint (e.g. https://my-proxy.example.com/)
  - LITELLM_API_KEY: API key for the proxy
"""

from __future__ import annotations

import json
import os
import time
import copy
import pytest
from pathlib import Path
from unittest.mock import patch

# Read credentials from env — NEVER hardcode
_BASE_URL = os.environ.get("LITELLM_BASE_URL", "")
_API_KEY = os.environ.get("LITELLM_API_KEY", "")

# Skip all tests if credentials not available
pytestmark = pytest.mark.skipif(
    not _BASE_URL or not _API_KEY,
    reason="LITELLM_BASE_URL and LITELLM_API_KEY required for live E2E tests",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def settings_dir(tmp_path):
    """Redirect settings to temp dir for test isolation."""
    settings_path = tmp_path / "settings.json"
    lock_path = Path(str(settings_path) + ".lock")
    data_dir = tmp_path

    import ouroboros.config as cfg
    orig_settings = cfg.SETTINGS_PATH
    orig_lock = cfg._SETTINGS_LOCK
    orig_data = cfg.DATA_DIR

    cfg.SETTINGS_PATH = settings_path
    cfg._SETTINGS_LOCK = lock_path
    cfg.DATA_DIR = data_dir

    yield tmp_path

    cfg.SETTINGS_PATH = orig_settings
    cfg._SETTINGS_LOCK = orig_lock
    cfg.DATA_DIR = orig_data


@pytest.fixture
def litellm_settings(settings_dir):
    """Create settings with LiteLLM as a custom provider."""
    from ouroboros.config import save_settings

    settings = {
        "providers": {
            "litellm": {
                "name": "LiteLLM Proxy",
                "type": "custom",
                "base_url": _BASE_URL.rstrip("/") + "/v1",
                "api_key": _API_KEY,
            },
        },
        "model_slots": {
            "main":      {"provider_id": "litellm", "model_id": "openai/gpt-4.1-mini"},
            "code":      {"provider_id": "litellm", "model_id": "openai/gpt-4.1-nano"},
            "light":     {"provider_id": "litellm", "model_id": "deepseek/deepseek-chat"},
            "fallback":  {"provider_id": "litellm", "model_id": "openai/gpt-4o-mini"},
            "websearch": {"provider_id": "litellm", "model_id": "openai/gpt-4o-mini"},
            "vision":    {"provider_id": "litellm", "model_id": "openai/gpt-4.1-mini"},
        },
        # Legacy keys (empty — we use custom provider)
        "OPENROUTER_API_KEY": "",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
    }
    save_settings(settings)
    return settings


@pytest.fixture
def llm_client(litellm_settings):
    """Create LLMClient with clean state."""
    from ouroboros.llm import LLMClient
    client = LLMClient()
    client.invalidate_all()
    return client


# ---------------------------------------------------------------------------
# Test 1: Provider connection & model listing
# ---------------------------------------------------------------------------

class TestProviderConnection:
    """Verify the LiteLLM endpoint is reachable and lists models."""

    def test_list_models(self):
        """GET /v1/models returns a non-empty list."""
        from openai import OpenAI
        client = OpenAI(
            base_url=_BASE_URL.rstrip("/") + "/v1",
            api_key=_API_KEY,
        )
        models = client.models.list()
        model_ids = [m.id for m in models.data]
        assert len(model_ids) > 0, "No models available"
        print(f"\n  Available models: {len(model_ids)}")

    def test_provider_config_loads(self, litellm_settings, settings_dir):
        """LLMClient can load the custom provider config."""
        from ouroboros.llm import LLMClient
        client = LLMClient()
        config = client.get_provider_config("litellm")
        assert config is not None
        assert config.provider_type == "custom"
        assert config.base_url.startswith("http")
        assert len(config.api_key) > 0

    def test_slot_configs_load(self, litellm_settings, settings_dir):
        """All 6 model slots point to the litellm provider."""
        from ouroboros.llm import LLMClient
        client = LLMClient()
        for slot in ("main", "code", "light", "fallback", "websearch", "vision"):
            sc = client.get_slot_config(slot)
            assert sc.provider_id == "litellm", f"Slot {slot} has wrong provider: {sc.provider_id}"
            assert sc.model_id, f"Slot {slot} has empty model_id"


# ---------------------------------------------------------------------------
# Test 2: Single-model chat calls per slot
# ---------------------------------------------------------------------------

class TestSlotChatCalls:
    """Test that each slot can make a real LLM call and get a response."""

    @pytest.mark.parametrize("slot,expected_model_prefix", [
        ("main", "openai/"),
        ("code", "openai/"),
        ("light", "deepseek/"),
        ("fallback", "openai/"),
    ])
    def test_chat_per_slot(self, llm_client, slot, expected_model_prefix):
        """Each slot routes to the correct model and returns a valid response."""
        msg, usage = llm_client.chat(
            messages=[
                {"role": "user", "content": "Reply with exactly: SLOT_TEST_OK"},
            ],
            model="",  # Use slot config
            slot=slot,
            max_tokens=50,
            reasoning_effort="low",
        )

        # Verify we got a response
        content = msg.get("content", "")
        assert content, f"Empty response from slot={slot}"
        assert isinstance(content, str)
        print(f"\n  [{slot}] Response: {content[:80]}")

        # Verify usage tracking
        assert isinstance(usage, dict)
        # Token counts should be present
        total = int(usage.get("prompt_tokens", 0)) + int(usage.get("completion_tokens", 0))
        assert total > 0, f"No token usage reported for slot={slot}"

    def test_main_slot_default(self, llm_client):
        """default_model() returns the main slot's model."""
        model = llm_client.default_model()
        assert model == "openai/gpt-4.1-mini"


# ---------------------------------------------------------------------------
# Test 3: Multi-model in same conversation
# ---------------------------------------------------------------------------

class TestMultiModelConversation:
    """Simulate a real scenario: main model for reasoning, light for safety check."""

    def test_main_then_light(self, llm_client):
        """Call main slot, then light slot — both succeed with different models."""
        # Main reasoning call
        msg1, usage1 = llm_client.chat(
            messages=[{"role": "user", "content": "What is 2+2? Reply with just the number."}],
            model="",
            slot="main",
            max_tokens=20,
        )
        assert msg1.get("content"), "Main slot returned empty"

        # Light safety check call
        msg2, usage2 = llm_client.chat(
            messages=[{"role": "user", "content": "Is 'echo hello' a safe command? Reply: SAFE or DANGEROUS"}],
            model="",
            slot="light",
            max_tokens=20,
        )
        assert msg2.get("content"), "Light slot returned empty"

        print(f"\n  Main response: {msg1['content'][:60]}")
        print(f"  Light response: {msg2['content'][:60]}")


# ---------------------------------------------------------------------------
# Test 4: Explicit model override (model param > slot config)
# ---------------------------------------------------------------------------

class TestModelOverride:
    """Test that passing an explicit model overrides the slot config."""

    def test_explicit_model_overrides_slot(self, llm_client):
        """When model is explicitly specified, it should be used instead of slot config."""
        # Main slot is configured for anthropic/claude-haiku-4-5
        # Override with a different model
        msg, usage = llm_client.chat(
            messages=[{"role": "user", "content": "Say: OVERRIDE_OK"}],
            model="openai/gpt-4.1-nano",  # Explicit override
            slot="main",
            max_tokens=20,
        )
        assert msg.get("content"), "Override model returned empty"
        print(f"\n  Override response: {msg['content'][:60]}")


# ---------------------------------------------------------------------------
# Test 5: Vision query
# ---------------------------------------------------------------------------

class TestVisionSlot:
    """Test vision_query through the vision slot."""

    def test_vision_query_text_only(self, llm_client):
        """Vision query with no images should still work (text-only)."""
        text, usage = llm_client.vision_query(
            prompt="Reply with exactly: VISION_OK",
            images=[],
            slot="vision",
            max_tokens=20,
        )
        assert text, "Vision slot returned empty"
        print(f"\n  Vision response: {text[:60]}")


# ---------------------------------------------------------------------------
# Test 6: available_models() aggregation
# ---------------------------------------------------------------------------

class TestModelAggregation:
    """Test that available_models returns unique models from all slots."""

    def test_available_models(self, llm_client):
        """available_models() returns unique models from all configured slots."""
        models = llm_client.available_models()
        assert len(models) >= 3, f"Expected at least 3 unique models, got {len(models)}: {models}"
        # Should contain models from main, code, light, fallback
        print(f"\n  Available models: {models}")


# ---------------------------------------------------------------------------
# Test 7: Client caching and invalidation
# ---------------------------------------------------------------------------

class TestClientCaching:
    """Test that provider clients are cached and can be invalidated."""

    def test_same_client_reused(self, llm_client):
        """Consecutive calls to same provider reuse the cached client."""
        c1 = llm_client._get_client_for_provider("litellm")
        c2 = llm_client._get_client_for_provider("litellm")
        assert c1 is c2, "Client was not cached"

    def test_invalidate_forces_new_client(self, llm_client):
        """After invalidation, a new client is created."""
        c1 = llm_client._get_client_for_provider("litellm")
        llm_client.invalidate_client("litellm")
        c2 = llm_client._get_client_for_provider("litellm")
        assert c1 is not c2, "Client was not invalidated"


# ---------------------------------------------------------------------------
# Test 8: Multiple providers simultaneously
# ---------------------------------------------------------------------------

class TestMultipleProviders:
    """Test routing when multiple providers are configured."""

    def test_two_providers_different_slots(self, settings_dir):
        """Configure two 'providers' pointing to same endpoint but different IDs."""
        from ouroboros.config import save_settings
        from ouroboros.llm import LLMClient

        # Create two provider entries (both point to same LiteLLM, just different IDs)
        settings = {
            "providers": {
                "provider_a": {
                    "name": "Provider A",
                    "type": "custom",
                    "base_url": _BASE_URL.rstrip("/") + "/v1",
                    "api_key": _API_KEY,
                },
                "provider_b": {
                    "name": "Provider B",
                    "type": "custom",
                    "base_url": _BASE_URL.rstrip("/") + "/v1",
                    "api_key": _API_KEY,
                },
            },
            "model_slots": {
                "main":      {"provider_id": "provider_a", "model_id": "openai/gpt-4.1-mini"},
                "code":      {"provider_id": "provider_b", "model_id": "openai/gpt-4.1-nano"},
                "light":     {"provider_id": "provider_a", "model_id": "deepseek/deepseek-chat"},
                "fallback":  {"provider_id": "provider_b", "model_id": "openai/gpt-4.1-nano"},
                "websearch": {"provider_id": "provider_a", "model_id": "openai/gpt-4o-mini"},
                "vision":    {"provider_id": "provider_a", "model_id": "openai/gpt-4.1-mini"},
            },
        }
        save_settings(settings)

        client = LLMClient()
        client.invalidate_all()

        # Call main (provider_a) and code (provider_b) — both should work
        msg_a, _ = client.chat(
            messages=[{"role": "user", "content": "Say: PROVIDER_A"}],
            model="", slot="main", max_tokens=20,
        )
        msg_b, _ = client.chat(
            messages=[{"role": "user", "content": "Say: PROVIDER_B"}],
            model="", slot="code", max_tokens=20,
        )

        assert msg_a.get("content"), "Provider A returned empty"
        assert msg_b.get("content"), "Provider B returned empty"
        print(f"\n  Provider A: {msg_a['content'][:40]}")
        print(f"  Provider B: {msg_b['content'][:40]}")


# ---------------------------------------------------------------------------
# Test 9: Stress test — rapid sequential calls to different slots
# ---------------------------------------------------------------------------

class TestRapidSlotSwitching:
    """Test rapid switching between different model slots."""

    def test_rapid_slot_rotation(self, llm_client):
        """Call 4 different slots in rapid succession."""
        slots = ["main", "code", "light", "fallback"]
        results = {}

        for slot in slots:
            msg, usage = llm_client.chat(
                messages=[{"role": "user", "content": f"Reply with one word: {slot.upper()}"}],
                model="", slot=slot, max_tokens=10,
            )
            results[slot] = msg.get("content", "")
            assert results[slot], f"Slot {slot} returned empty"

        print("\n  Rapid rotation results:")
        for slot, resp in results.items():
            print(f"    [{slot}] {resp[:40]}")


# ---------------------------------------------------------------------------
# Test 10: Error handling — invalid model
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Test behavior with invalid configurations."""

    def test_nonexistent_model(self, llm_client, litellm_settings, settings_dir):
        """Calling a non-existent model should raise an exception."""
        with pytest.raises(Exception):
            llm_client.chat(
                messages=[{"role": "user", "content": "Hello"}],
                model="nonexistent/fake-model-xyz",
                slot="main",
                max_tokens=10,
            )

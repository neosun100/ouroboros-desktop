"""
Multi-provider architecture tests.

Tests the provider/slot routing system introduced in the v2 settings format:
1. Settings migration (flat v1 -> provider/slot v2)
2. LLMClient slot and provider resolution
3. Data model immutability (frozen dataclasses)

Run: python -m pytest tests/test_provider_routing.py -v
"""
from __future__ import annotations

import copy
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def flat_settings_openrouter() -> Dict[str, Any]:
    """Minimal v1 flat settings with an OpenRouter key set."""
    return {
        "OPENROUTER_API_KEY": "sk-or-test-key-123",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "OUROBOROS_MODEL": "anthropic/claude-sonnet-4.6",
        "OUROBOROS_MODEL_CODE": "anthropic/claude-sonnet-4.6",
        "OUROBOROS_MODEL_LIGHT": "google/gemini-3-flash-preview",
        "OUROBOROS_MODEL_FALLBACK": "google/gemini-3-flash-preview",
        "OUROBOROS_WEBSEARCH_MODEL": "gpt-5.2",
        "USE_LOCAL_MAIN": False,
        "USE_LOCAL_CODE": False,
        "USE_LOCAL_LIGHT": False,
        "USE_LOCAL_FALLBACK": False,
        "LOCAL_MODEL_PORT": 8766,
    }


@pytest.fixture()
def migrated_settings() -> Dict[str, Any]:
    """Already-migrated v2 settings (contains both providers and model_slots)."""
    from ouroboros.config import _DEFAULT_MODEL_SLOTS, _DEFAULT_PROVIDERS
    return {
        "OPENROUTER_API_KEY": "sk-or-test-key-123",
        "providers": copy.deepcopy(_DEFAULT_PROVIDERS),
        "model_slots": copy.deepcopy(_DEFAULT_MODEL_SLOTS),
    }


@pytest.fixture()
def settings_file(tmp_path: Path):
    """Write a settings.json to tmp_path and patch SETTINGS_PATH + DATA_DIR."""
    settings_path = tmp_path / "settings.json"

    def _write(data: dict) -> Path:
        settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return settings_path

    return _write


@pytest.fixture()
def _patch_settings_path(tmp_path: Path, monkeypatch):
    """Redirect SETTINGS_PATH and DATA_DIR to tmp_path so load/save are isolated."""
    import ouroboros.config as cfg

    settings_path = tmp_path / "settings.json"
    lock_path = Path(str(settings_path) + ".lock")

    monkeypatch.setattr(cfg, "SETTINGS_PATH", settings_path)
    monkeypatch.setattr(cfg, "DATA_DIR", tmp_path)
    monkeypatch.setattr(cfg, "_SETTINGS_LOCK", lock_path)


# ===========================================================================
# 1. Settings Migration
# ===========================================================================

class TestMigrateSettingsFromFlat:
    """migrate_settings() converts flat v1 settings to v2 provider/slot format."""

    def test_providers_created_from_api_keys(self, flat_settings_openrouter):
        from ouroboros.config import migrate_settings

        result = migrate_settings(flat_settings_openrouter)

        assert "providers" in result
        assert "model_slots" in result

        # OpenRouter key should be propagated
        providers = result["providers"]
        assert providers["openrouter"]["api_key"] == "sk-or-test-key-123"

    def test_model_slots_created_from_legacy_keys(self, flat_settings_openrouter):
        from ouroboros.config import migrate_settings

        result = migrate_settings(flat_settings_openrouter)
        slots = result["model_slots"]

        assert slots["main"]["model_id"] == "anthropic/claude-sonnet-4.6"
        assert slots["code"]["model_id"] == "anthropic/claude-sonnet-4.6"
        assert slots["light"]["model_id"] == "google/gemini-3-flash-preview"
        assert slots["fallback"]["model_id"] == "google/gemini-3-flash-preview"
        assert slots["websearch"]["model_id"] == "gpt-5.2"

    def test_default_provider_is_openrouter(self, flat_settings_openrouter):
        from ouroboros.config import migrate_settings

        result = migrate_settings(flat_settings_openrouter)
        slots = result["model_slots"]

        # All non-websearch slots should use openrouter (first provider with key)
        assert slots["main"]["provider_id"] == "openrouter"
        assert slots["code"]["provider_id"] == "openrouter"
        assert slots["light"]["provider_id"] == "openrouter"

    def test_vision_slot_follows_main(self, flat_settings_openrouter):
        from ouroboros.config import migrate_settings

        result = migrate_settings(flat_settings_openrouter)
        slots = result["model_slots"]

        assert slots["vision"]["provider_id"] == slots["main"]["provider_id"]
        assert slots["vision"]["model_id"] == slots["main"]["model_id"]

    def test_local_port_propagated(self):
        from ouroboros.config import migrate_settings

        settings = {"LOCAL_MODEL_PORT": 9999}
        result = migrate_settings(settings)
        providers = result["providers"]

        assert "9999" in providers["local"]["base_url"]

    def test_default_local_port(self):
        """When LOCAL_MODEL_PORT is absent, default 8766 is used."""
        from ouroboros.config import migrate_settings

        result = migrate_settings({})
        providers = result["providers"]

        assert "8766" in providers["local"]["base_url"]

    def test_all_default_providers_present(self, flat_settings_openrouter):
        from ouroboros.config import migrate_settings

        result = migrate_settings(flat_settings_openrouter)
        providers = result["providers"]

        expected_ids = {"openrouter", "openai", "anthropic", "ollama", "local"}
        assert set(providers.keys()) == expected_ids

    def test_legacy_keys_preserved(self, flat_settings_openrouter):
        """Migration preserves all original flat keys (backwards compat)."""
        from ouroboros.config import migrate_settings

        result = migrate_settings(flat_settings_openrouter)

        assert result["OPENROUTER_API_KEY"] == "sk-or-test-key-123"
        assert result["OUROBOROS_MODEL"] == "anthropic/claude-sonnet-4.6"


class TestMigrateSettingsIdempotent:
    """Already-migrated settings pass through unchanged."""

    def test_identity_preserved(self, migrated_settings):
        from ouroboros.config import migrate_settings

        result = migrate_settings(migrated_settings)

        # Must return the exact same object (identity check)
        assert result is migrated_settings

    def test_no_mutation(self, migrated_settings):
        from ouroboros.config import migrate_settings

        original_providers = copy.deepcopy(migrated_settings["providers"])
        original_slots = copy.deepcopy(migrated_settings["model_slots"])

        migrate_settings(migrated_settings)

        assert migrated_settings["providers"] == original_providers
        assert migrated_settings["model_slots"] == original_slots


class TestMigrateSettingsEmpty:
    """Empty settings get populated with default providers and slots."""

    def test_empty_dict_gets_defaults(self):
        from ouroboros.config import migrate_settings

        result = migrate_settings({})

        assert "providers" in result
        assert "model_slots" in result

    def test_empty_has_all_provider_ids(self):
        from ouroboros.config import migrate_settings

        result = migrate_settings({})
        providers = result["providers"]

        assert "openrouter" in providers
        assert "openai" in providers
        assert "anthropic" in providers
        assert "ollama" in providers
        assert "local" in providers

    def test_empty_has_all_slot_names(self):
        from ouroboros.config import migrate_settings

        result = migrate_settings({})
        slots = result["model_slots"]

        for name in ("main", "code", "light", "fallback", "websearch", "vision"):
            assert name in slots, f"Slot '{name}' missing after empty migration"

    def test_empty_providers_have_no_api_keys(self):
        """No api_key should be set when migrating from empty input."""
        from ouroboros.config import migrate_settings

        result = migrate_settings({})
        providers = result["providers"]

        for pid in ("openrouter", "openai", "anthropic"):
            assert providers[pid]["api_key"] == ""


class TestMigrateSettingsUseLocalFlags:
    """USE_LOCAL_* flags override provider_id to 'local'."""

    def test_use_local_main(self, flat_settings_openrouter):
        from ouroboros.config import migrate_settings

        flat_settings_openrouter["USE_LOCAL_MAIN"] = True
        result = migrate_settings(flat_settings_openrouter)
        slots = result["model_slots"]

        assert slots["main"]["provider_id"] == "local"

    def test_use_local_code(self, flat_settings_openrouter):
        from ouroboros.config import migrate_settings

        flat_settings_openrouter["USE_LOCAL_CODE"] = True
        result = migrate_settings(flat_settings_openrouter)

        assert result["model_slots"]["code"]["provider_id"] == "local"

    def test_use_local_light(self, flat_settings_openrouter):
        from ouroboros.config import migrate_settings

        flat_settings_openrouter["USE_LOCAL_LIGHT"] = True
        result = migrate_settings(flat_settings_openrouter)

        assert result["model_slots"]["light"]["provider_id"] == "local"

    def test_use_local_fallback(self, flat_settings_openrouter):
        from ouroboros.config import migrate_settings

        flat_settings_openrouter["USE_LOCAL_FALLBACK"] = True
        result = migrate_settings(flat_settings_openrouter)

        assert result["model_slots"]["fallback"]["provider_id"] == "local"

    def test_use_local_string_true(self, flat_settings_openrouter):
        """String 'true' is interpreted as boolean True."""
        from ouroboros.config import migrate_settings

        flat_settings_openrouter["USE_LOCAL_MAIN"] = "true"
        result = migrate_settings(flat_settings_openrouter)

        assert result["model_slots"]["main"]["provider_id"] == "local"

    def test_use_local_string_1(self, flat_settings_openrouter):
        """String '1' is interpreted as boolean True."""
        from ouroboros.config import migrate_settings

        flat_settings_openrouter["USE_LOCAL_MAIN"] = "1"
        result = migrate_settings(flat_settings_openrouter)

        assert result["model_slots"]["main"]["provider_id"] == "local"

    def test_use_local_false_keeps_cloud(self, flat_settings_openrouter):
        from ouroboros.config import migrate_settings

        flat_settings_openrouter["USE_LOCAL_MAIN"] = False
        result = migrate_settings(flat_settings_openrouter)

        assert result["model_slots"]["main"]["provider_id"] != "local"

    def test_multiple_local_overrides(self, flat_settings_openrouter):
        from ouroboros.config import migrate_settings

        flat_settings_openrouter["USE_LOCAL_MAIN"] = True
        flat_settings_openrouter["USE_LOCAL_CODE"] = True
        result = migrate_settings(flat_settings_openrouter)
        slots = result["model_slots"]

        assert slots["main"]["provider_id"] == "local"
        assert slots["code"]["provider_id"] == "local"
        # Non-local slots remain cloud
        assert slots["light"]["provider_id"] != "local"


class TestMigrateSettingsOpenAIWebsearch:
    """When OPENAI_API_KEY is set, websearch slot uses 'openai' provider."""

    def test_websearch_uses_openai(self):
        from ouroboros.config import migrate_settings

        settings = {
            "OPENAI_API_KEY": "sk-openai-test-key",
            "OPENROUTER_API_KEY": "sk-or-test-key",
            "OUROBOROS_WEBSEARCH_MODEL": "gpt-5.2",
        }
        result = migrate_settings(settings)
        slots = result["model_slots"]

        assert slots["websearch"]["provider_id"] == "openai"
        assert slots["websearch"]["model_id"] == "gpt-5.2"

    def test_websearch_without_openai_key(self):
        """Without OPENAI_API_KEY, websearch still gets a provider (default)."""
        from ouroboros.config import migrate_settings

        settings = {
            "OPENROUTER_API_KEY": "sk-or-test-key",
            "OUROBOROS_WEBSEARCH_MODEL": "gpt-5.2",
        }
        result = migrate_settings(settings)
        slots = result["model_slots"]

        # Should NOT be openai (no key configured)
        # Default provider logic picks openrouter since it has a key
        assert slots["websearch"]["provider_id"] != "openai"

    def test_openai_key_propagated_to_provider(self):
        from ouroboros.config import migrate_settings

        settings = {"OPENAI_API_KEY": "sk-openai-key-789"}
        result = migrate_settings(settings)

        assert result["providers"]["openai"]["api_key"] == "sk-openai-key-789"

    def test_anthropic_key_propagated(self):
        from ouroboros.config import migrate_settings

        settings = {"ANTHROPIC_API_KEY": "sk-ant-key-abc"}
        result = migrate_settings(settings)

        assert result["providers"]["anthropic"]["api_key"] == "sk-ant-key-abc"


class TestHasAnyProviderKey:
    """has_any_provider_key() detects whether any real API key is configured."""

    def test_no_keys(self):
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "openrouter": {"type": "openrouter", "api_key": ""},
                "openai": {"type": "openai", "api_key": ""},
                "ollama": {"type": "ollama", "api_key": "ollama"},
            }
        }
        assert has_any_provider_key(settings) is False

    def test_openrouter_key_present(self):
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "openrouter": {"type": "openrouter", "api_key": "sk-or-real-key"},
            }
        }
        assert has_any_provider_key(settings) is True

    def test_ollama_alone_not_counted(self):
        """Ollama has a hardcoded 'ollama' key which is not a real credential."""
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "ollama": {"type": "ollama", "api_key": "ollama"},
            }
        }
        assert has_any_provider_key(settings) is False

    def test_local_alone_not_counted(self):
        """Local provider does not count as having a real key."""
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "local": {"type": "local", "api_key": "local"},
            }
        }
        assert has_any_provider_key(settings) is False

    def test_mixed_providers_with_one_key(self):
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "openrouter": {"type": "openrouter", "api_key": ""},
                "openai": {"type": "openai", "api_key": "sk-openai-key"},
                "ollama": {"type": "ollama", "api_key": "ollama"},
                "local": {"type": "local", "api_key": "local"},
            }
        }
        assert has_any_provider_key(settings) is True

    def test_empty_providers_dict(self):
        from ouroboros.config import has_any_provider_key

        assert has_any_provider_key({"providers": {}}) is False

    def test_no_providers_key(self):
        from ouroboros.config import has_any_provider_key

        assert has_any_provider_key({}) is False


# ===========================================================================
# 2. LLMClient Slot / Provider Resolution
# ===========================================================================

def _make_settings_with_slots(
    slots: Dict[str, Dict[str, str]] | None = None,
    providers: Dict[str, Dict[str, str]] | None = None,
) -> dict:
    """Build a complete v2 settings dict for testing."""
    from ouroboros.config import _DEFAULT_MODEL_SLOTS, _DEFAULT_PROVIDERS

    return {
        "providers": providers if providers is not None else copy.deepcopy(_DEFAULT_PROVIDERS),
        "model_slots": slots if slots is not None else copy.deepcopy(_DEFAULT_MODEL_SLOTS),
    }


class TestSlotConfigResolution:
    """LLMClient.get_slot_config() returns correct SlotConfig for each slot."""

    def test_main_slot(self, _patch_settings_path, settings_file):
        from ouroboros.llm import LLMClient

        settings = _make_settings_with_slots(
            slots={
                "main": {"provider_id": "openrouter", "model_id": "anthropic/claude-sonnet-4.6"},
                "code": {"provider_id": "openrouter", "model_id": "anthropic/claude-sonnet-4.6"},
                "light": {"provider_id": "openrouter", "model_id": "google/gemini-3-flash-preview"},
                "fallback": {"provider_id": "openrouter", "model_id": "google/gemini-3-flash-preview"},
                "websearch": {"provider_id": "openai", "model_id": "gpt-5.2"},
                "vision": {"provider_id": "openrouter", "model_id": "anthropic/claude-sonnet-4.6"},
            }
        )
        settings_file(settings)

        slot = LLMClient.get_slot_config("main")

        assert slot.provider_id == "openrouter"
        assert slot.model_id == "anthropic/claude-sonnet-4.6"

    def test_websearch_slot(self, _patch_settings_path, settings_file):
        from ouroboros.llm import LLMClient

        settings = _make_settings_with_slots(
            slots={
                "main": {"provider_id": "openrouter", "model_id": "test-model"},
                "websearch": {"provider_id": "openai", "model_id": "gpt-5.2"},
            }
        )
        settings_file(settings)

        slot = LLMClient.get_slot_config("websearch")

        assert slot.provider_id == "openai"
        assert slot.model_id == "gpt-5.2"

    def test_unknown_slot_returns_defaults(self, _patch_settings_path, settings_file):
        """Unknown slot name should return openrouter with empty model_id."""
        from ouroboros.llm import LLMClient

        settings = _make_settings_with_slots(slots={})
        settings_file(settings)

        slot = LLMClient.get_slot_config("nonexistent_slot")

        assert slot.provider_id == "openrouter"
        assert slot.model_id == ""

    def test_slot_config_is_immutable(self, _patch_settings_path, settings_file):
        from ouroboros.llm import LLMClient

        settings_file(_make_settings_with_slots())
        slot = LLMClient.get_slot_config("main")

        with pytest.raises(FrozenInstanceError):
            slot.provider_id = "modified"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            slot.model_id = "modified"  # type: ignore[misc]


class TestProviderConfigResolution:
    """LLMClient.get_provider_config() returns correct ProviderConfig."""

    def test_openrouter_provider(self, _patch_settings_path, settings_file):
        from ouroboros.llm import LLMClient

        providers = {
            "openrouter": {
                "name": "OpenRouter",
                "type": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": "sk-or-test",
            }
        }
        settings_file(_make_settings_with_slots(providers=providers))

        config = LLMClient.get_provider_config("openrouter")

        assert config is not None
        assert config.provider_id == "openrouter"
        assert config.name == "OpenRouter"
        assert config.provider_type == "openrouter"
        assert config.base_url == "https://openrouter.ai/api/v1"
        assert config.api_key == "sk-or-test"

    def test_ollama_provider(self, _patch_settings_path, settings_file):
        from ouroboros.llm import LLMClient

        providers = {
            "ollama": {
                "name": "Ollama",
                "type": "ollama",
                "base_url": "http://127.0.0.1:11434/v1",
                "api_key": "ollama",
            }
        }
        settings_file(_make_settings_with_slots(providers=providers))

        config = LLMClient.get_provider_config("ollama")

        assert config is not None
        assert config.provider_type == "ollama"
        assert config.api_key == "ollama"

    def test_local_provider(self, _patch_settings_path, settings_file):
        from ouroboros.llm import LLMClient

        providers = {
            "local": {
                "name": "Local (llama-cpp)",
                "type": "local",
                "base_url": "http://127.0.0.1:8766/v1",
                "api_key": "local",
            }
        }
        settings_file(_make_settings_with_slots(providers=providers))

        config = LLMClient.get_provider_config("local")

        assert config is not None
        assert config.provider_type == "local"
        assert "8766" in config.base_url

    def test_missing_optional_fields(self, _patch_settings_path, settings_file):
        """Provider with minimal config should use defaults for missing fields."""
        from ouroboros.llm import LLMClient

        providers = {
            "custom": {
                "name": "Custom Provider",
            }
        }
        settings_file(_make_settings_with_slots(providers=providers))

        config = LLMClient.get_provider_config("custom")

        assert config is not None
        assert config.provider_type == "custom"
        assert config.base_url == ""
        assert config.api_key == ""


class TestProviderConfigMissing:
    """get_provider_config returns None for unknown providers."""

    def test_unknown_provider_returns_none(self, _patch_settings_path, settings_file):
        from ouroboros.llm import LLMClient

        settings_file(_make_settings_with_slots(providers={}))

        config = LLMClient.get_provider_config("nonexistent_provider")

        assert config is None

    def test_empty_providers_dict(self, _patch_settings_path, settings_file):
        from ouroboros.llm import LLMClient

        settings_file({"providers": {}, "model_slots": {}})

        config = LLMClient.get_provider_config("openrouter")

        assert config is None


class TestDefaultModel:
    """LLMClient.default_model() reads from the 'main' slot config."""

    def test_returns_main_slot_model(self, _patch_settings_path, settings_file):
        from ouroboros.llm import LLMClient

        settings = _make_settings_with_slots(
            slots={"main": {"provider_id": "openrouter", "model_id": "test/custom-model"}}
        )
        settings_file(settings)

        client = LLMClient(api_key="test")
        model = client.default_model()

        assert model == "test/custom-model"

    def test_fallback_to_env_var(self, monkeypatch):
        """When slot config fails, falls back to OUROBOROS_MODEL env var."""
        from ouroboros.llm import LLMClient

        monkeypatch.setenv("OUROBOROS_MODEL", "env/fallback-model")

        # Patch load_settings to raise, simulating a failure
        with patch("ouroboros.llm.LLMClient.get_slot_config", side_effect=Exception("boom")):
            client = LLMClient(api_key="test")
            model = client.default_model()

        assert model == "env/fallback-model"

    def test_empty_model_id_falls_back(self, _patch_settings_path, settings_file, monkeypatch):
        """Empty model_id in slot triggers env var fallback."""
        from ouroboros.llm import LLMClient

        settings = _make_settings_with_slots(
            slots={"main": {"provider_id": "openrouter", "model_id": ""}}
        )
        settings_file(settings)
        monkeypatch.setenv("OUROBOROS_MODEL", "env/model-via-env")

        client = LLMClient(api_key="test")
        model = client.default_model()

        assert model == "env/model-via-env"


class TestAvailableModels:
    """available_models() returns unique models from configured slots."""

    def test_returns_unique_models(self, _patch_settings_path, settings_file):
        from ouroboros.llm import LLMClient

        settings = _make_settings_with_slots(
            slots={
                "main": {"provider_id": "openrouter", "model_id": "model-a"},
                "code": {"provider_id": "openrouter", "model_id": "model-a"},
                "light": {"provider_id": "openrouter", "model_id": "model-b"},
                "fallback": {"provider_id": "openrouter", "model_id": "model-c"},
            }
        )
        settings_file(settings)

        client = LLMClient(api_key="test")
        models = client.available_models()

        # model-a appears in main and code but should only appear once
        assert models == ["model-a", "model-b", "model-c"]

    def test_preserves_order(self, _patch_settings_path, settings_file):
        """Order is main -> code -> light -> fallback."""
        from ouroboros.llm import LLMClient

        settings = _make_settings_with_slots(
            slots={
                "main": {"provider_id": "x", "model_id": "z-last"},
                "code": {"provider_id": "x", "model_id": "a-first"},
                "light": {"provider_id": "x", "model_id": "m-middle"},
                "fallback": {"provider_id": "x", "model_id": "b-second"},
            }
        )
        settings_file(settings)

        client = LLMClient(api_key="test")
        models = client.available_models()

        assert models == ["z-last", "a-first", "m-middle", "b-second"]

    def test_skips_empty_model_ids(self, _patch_settings_path, settings_file):
        from ouroboros.llm import LLMClient

        settings = _make_settings_with_slots(
            slots={
                "main": {"provider_id": "x", "model_id": "model-a"},
                "code": {"provider_id": "x", "model_id": ""},
                "light": {"provider_id": "x", "model_id": "model-b"},
                "fallback": {"provider_id": "x", "model_id": ""},
            }
        )
        settings_file(settings)

        client = LLMClient(api_key="test")
        models = client.available_models()

        assert models == ["model-a", "model-b"]

    def test_fallback_to_env_on_failure(self, monkeypatch):
        """When load_settings fails, falls back to env vars."""
        from ouroboros.llm import LLMClient

        monkeypatch.setenv("OUROBOROS_MODEL", "env/main-model")
        monkeypatch.setenv("OUROBOROS_MODEL_CODE", "env/code-model")
        monkeypatch.setenv("OUROBOROS_MODEL_LIGHT", "env/light-model")

        with patch("ouroboros.config.load_settings", side_effect=Exception("boom")):
            client = LLMClient(api_key="test")
            models = client.available_models()

        assert "env/main-model" in models
        assert "env/code-model" in models
        assert "env/light-model" in models


class TestClientInvalidation:
    """invalidate_all() clears cached client instances."""

    def test_invalidate_all_clears_cache(self):
        from ouroboros.llm import LLMClient

        client = LLMClient(api_key="test")
        # Manually inject fake cached clients
        client._clients["openrouter"] = "fake-client-1"
        client._clients["openai"] = "fake-client-2"

        assert len(client._clients) == 2

        client.invalidate_all()

        assert len(client._clients) == 0

    def test_invalidate_single_client(self):
        from ouroboros.llm import LLMClient

        client = LLMClient(api_key="test")
        client._clients["openrouter"] = "fake-client-1"
        client._clients["openai"] = "fake-client-2"

        client.invalidate_client("openrouter")

        assert "openrouter" not in client._clients
        assert "openai" in client._clients

    def test_invalidate_nonexistent_is_noop(self):
        from ouroboros.llm import LLMClient

        client = LLMClient(api_key="test")

        # Should not raise
        client.invalidate_client("nonexistent_provider")
        client.invalidate_all()

    def test_invalidate_all_is_thread_safe(self):
        """Basic check that invalidate_all uses the lock."""
        import threading
        from ouroboros.llm import LLMClient

        client = LLMClient(api_key="test")
        errors: list[Exception] = []

        def worker():
            try:
                for _ in range(100):
                    client._clients["test"] = "value"
                    client.invalidate_all()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"


# ===========================================================================
# 3. Data Model (frozen dataclasses)
# ===========================================================================

class TestProviderConfigDataclass:
    """ProviderConfig is frozen (immutable)."""

    def test_creation(self):
        from ouroboros.llm import ProviderConfig

        config = ProviderConfig(
            provider_id="test",
            name="Test Provider",
            provider_type="custom",
            base_url="http://localhost:8080/v1",
            api_key="test-key",
        )

        assert config.provider_id == "test"
        assert config.name == "Test Provider"
        assert config.provider_type == "custom"
        assert config.base_url == "http://localhost:8080/v1"
        assert config.api_key == "test-key"

    def test_frozen_immutability(self):
        from ouroboros.llm import ProviderConfig

        config = ProviderConfig(
            provider_id="test",
            name="Test",
            provider_type="custom",
            base_url="http://localhost",
            api_key="key",
        )

        with pytest.raises(FrozenInstanceError):
            config.provider_id = "modified"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            config.api_key = "new-key"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            config.base_url = "http://other"  # type: ignore[misc]

    def test_equality(self):
        from ouroboros.llm import ProviderConfig

        config1 = ProviderConfig("a", "A", "custom", "http://x", "key1")
        config2 = ProviderConfig("a", "A", "custom", "http://x", "key1")
        config3 = ProviderConfig("b", "B", "custom", "http://x", "key1")

        assert config1 == config2
        assert config1 != config3

    def test_hashable(self):
        """Frozen dataclasses are hashable (can be used in sets/dicts)."""
        from ouroboros.llm import ProviderConfig

        config = ProviderConfig("a", "A", "custom", "http://x", "key")
        # Should not raise
        s = {config}
        assert len(s) == 1


class TestSlotConfigDataclass:
    """SlotConfig is frozen (immutable)."""

    def test_creation(self):
        from ouroboros.llm import SlotConfig

        slot = SlotConfig(provider_id="openrouter", model_id="test/model")

        assert slot.provider_id == "openrouter"
        assert slot.model_id == "test/model"

    def test_frozen_immutability(self):
        from ouroboros.llm import SlotConfig

        slot = SlotConfig(provider_id="openrouter", model_id="test/model")

        with pytest.raises(FrozenInstanceError):
            slot.provider_id = "modified"  # type: ignore[misc]

        with pytest.raises(FrozenInstanceError):
            slot.model_id = "modified"  # type: ignore[misc]

    def test_equality(self):
        from ouroboros.llm import SlotConfig

        slot1 = SlotConfig("openrouter", "model-a")
        slot2 = SlotConfig("openrouter", "model-a")
        slot3 = SlotConfig("openai", "model-a")

        assert slot1 == slot2
        assert slot1 != slot3

    def test_hashable(self):
        from ouroboros.llm import SlotConfig

        slot = SlotConfig("x", "y")
        s = {slot}
        assert len(s) == 1


# ===========================================================================
# 4. Integration: load_settings through file system
# ===========================================================================

class TestLoadSettingsIntegration:
    """End-to-end: write a settings file, load_settings() returns migrated result."""

    def test_load_flat_settings_file(self, _patch_settings_path, settings_file):
        from ouroboros.config import load_settings

        flat = {
            "OPENROUTER_API_KEY": "sk-or-integration-test",
            "OUROBOROS_MODEL": "anthropic/claude-sonnet-4.6",
        }
        settings_file(flat)

        result = load_settings()

        assert "providers" in result
        assert "model_slots" in result
        assert result["providers"]["openrouter"]["api_key"] == "sk-or-integration-test"

    def test_load_already_migrated_file(self, _patch_settings_path, settings_file):
        from ouroboros.config import load_settings

        v2 = _make_settings_with_slots()
        v2["providers"]["openrouter"]["api_key"] = "sk-or-v2-key"
        settings_file(v2)

        result = load_settings()

        assert result["providers"]["openrouter"]["api_key"] == "sk-or-v2-key"

    def test_load_nonexistent_returns_defaults(self, _patch_settings_path):
        """When settings.json does not exist, defaults are returned."""
        from ouroboros.config import load_settings

        result = load_settings()

        assert "providers" in result
        assert "model_slots" in result

    def test_load_corrupt_json_returns_defaults(self, _patch_settings_path, tmp_path):
        """Corrupt JSON falls back to defaults gracefully."""
        import ouroboros.config as cfg

        cfg.SETTINGS_PATH.write_text("NOT VALID JSON {{{", encoding="utf-8")

        result = cfg.load_settings()

        assert "providers" in result
        assert "model_slots" in result


# ===========================================================================
# 5. Edge Cases
# ===========================================================================

class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_migrate_with_all_three_api_keys(self):
        """When all three API keys are set, openrouter is picked as default."""
        from ouroboros.config import migrate_settings

        settings = {
            "OPENROUTER_API_KEY": "sk-or",
            "OPENAI_API_KEY": "sk-openai",
            "ANTHROPIC_API_KEY": "sk-ant",
        }
        result = migrate_settings(settings)
        providers = result["providers"]

        assert providers["openrouter"]["api_key"] == "sk-or"
        assert providers["openai"]["api_key"] == "sk-openai"
        assert providers["anthropic"]["api_key"] == "sk-ant"

        # Default provider should be openrouter (first in priority order)
        assert result["model_slots"]["main"]["provider_id"] == "openrouter"

    def test_migrate_only_anthropic_key(self):
        """When only Anthropic key is set, it becomes the default provider."""
        from ouroboros.config import migrate_settings

        settings = {
            "ANTHROPIC_API_KEY": "sk-ant-only",
            "OUROBOROS_MODEL": "claude-3-opus",
        }
        result = migrate_settings(settings)

        # Anthropic should be picked as default since it is the only keyed provider
        # (openrouter and openai are checked first but have no key)
        assert result["model_slots"]["main"]["provider_id"] == "anthropic"

    def test_migrate_preserves_unknown_keys(self):
        """Keys not in the migration map are preserved in the result."""
        from ouroboros.config import migrate_settings

        settings = {
            "CUSTOM_SETTING": "custom_value",
            "TOTAL_BUDGET": 25.0,
        }
        result = migrate_settings(settings)

        assert result["CUSTOM_SETTING"] == "custom_value"
        assert result["TOTAL_BUDGET"] == 25.0

    def test_slot_config_with_partial_slot_data(self, _patch_settings_path, settings_file):
        """Slot data with only provider_id (no model_id) should not crash."""
        from ouroboros.llm import LLMClient

        settings = _make_settings_with_slots(
            slots={"main": {"provider_id": "openrouter"}}
        )
        settings_file(settings)

        slot = LLMClient.get_slot_config("main")

        assert slot.provider_id == "openrouter"
        assert slot.model_id == ""

    def test_provider_config_type_defaults_to_custom(self, _patch_settings_path, settings_file):
        """Provider without 'type' field defaults to 'custom'."""
        from ouroboros.llm import LLMClient

        settings = _make_settings_with_slots(
            providers={"minimal": {"name": "Minimal"}}
        )
        settings_file(settings)

        config = LLMClient.get_provider_config("minimal")

        assert config is not None
        assert config.provider_type == "custom"

    def test_concurrent_invalidation_and_insertion(self):
        """Verify no crash under concurrent client cache mutation."""
        import threading
        from ouroboros.llm import LLMClient

        client = LLMClient(api_key="test")
        errors: list[Exception] = []
        stop = threading.Event()

        def inserter():
            try:
                i = 0
                while not stop.is_set():
                    client._clients[f"p{i % 10}"] = f"client-{i}"
                    i += 1
            except Exception as e:
                errors.append(e)

        def invalidator():
            try:
                while not stop.is_set():
                    client.invalidate_all()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=inserter)
        t2 = threading.Thread(target=invalidator)
        t1.start()
        t2.start()

        # Run for a brief burst
        import time
        time.sleep(0.1)
        stop.set()

        t1.join(timeout=2)
        t2.join(timeout=2)

        # Note: dict mutation without lock in inserter may not crash Python's GIL-protected
        # dict, but we verify the code does not raise
        assert len(errors) == 0, f"Concurrency errors: {errors}"

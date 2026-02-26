"""
API endpoint tests for Ouroboros server.

Tests config/settings logic (load, save, migration, masking, provider checks)
and HTTP endpoints via Starlette TestClient with mocked settings paths.

Run: python -m pytest tests/test_api.py -v
"""
import copy
import json
import pathlib
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REPO_DIR = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture()
def tmp_data_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    """Temporary data directory for settings isolation."""
    data = tmp_path / "data"
    data.mkdir()
    return data


@pytest.fixture()
def _patch_settings_path(tmp_data_dir: pathlib.Path):
    """Redirect SETTINGS_PATH and DATA_DIR to tmp so tests never touch real config."""
    settings_file = tmp_data_dir / "settings.json"
    lock_file = pathlib.Path(str(settings_file) + ".lock")
    with (
        patch("ouroboros.config.SETTINGS_PATH", settings_file),
        patch("ouroboros.config.DATA_DIR", tmp_data_dir),
        patch("ouroboros.config._SETTINGS_LOCK", lock_file),
    ):
        yield


@pytest.fixture()
def _seed_settings(tmp_data_dir: pathlib.Path, _patch_settings_path):
    """Write a known settings.json into the temp directory."""
    from ouroboros.config import SETTINGS_DEFAULTS

    seed = copy.deepcopy(SETTINGS_DEFAULTS)
    seed["OPENROUTER_API_KEY"] = "sk-or-v1-abcdef1234567890"
    seed["providers"]["openrouter"]["api_key"] = "sk-or-v1-abcdef1234567890"
    seed["TOTAL_BUDGET"] = 5.0
    seed["OUROBOROS_MODEL"] = "test/model-main"
    settings_file = tmp_data_dir / "settings.json"
    settings_file.write_text(json.dumps(seed, indent=2), encoding="utf-8")
    return seed


def _build_test_app() -> Starlette:
    """Build a minimal Starlette app with the same routes as server.py but no lifespan.

    This avoids importing server.py at module level (which triggers logging,
    directory creation, and supervisor thread startup).
    """
    # Import route handlers from server -- but only the ones we actually test.
    # Importing server.py will create DATA_DIR/logs; that's acceptable in tests.
    import server

    routes = [
        Route("/api/health", endpoint=server.api_health),
        Route("/api/settings", endpoint=server.api_settings_get, methods=["GET"]),
        Route("/api/settings", endpoint=server.api_settings_post, methods=["POST"]),
        Route("/api/providers", endpoint=server.api_providers_list, methods=["GET"]),
        Route("/api/providers/test", endpoint=server.api_providers_test, methods=["POST"]),
        Route("/api/model-slots", endpoint=server.api_model_slots_get, methods=["GET"]),
    ]

    @asynccontextmanager
    async def noop_lifespan(app):
        yield

    return Starlette(routes=routes, lifespan=noop_lifespan)


@pytest.fixture()
def client(_seed_settings) -> TestClient:
    """TestClient wired to the test app, with settings already patched."""
    app = _build_test_app()
    return TestClient(app)


# ===========================================================================
# Unit tests: ouroboros.config functions (no HTTP)
# ===========================================================================


class TestHasAnyProviderKey:
    """has_any_provider_key detects real API keys vs keyless providers."""

    def test_with_openrouter_key(self):
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "openrouter": {"type": "openrouter", "api_key": "sk-or-v1-test123456"},
            },
        }
        assert has_any_provider_key(settings) is True

    def test_with_openai_key(self):
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "openai": {"type": "openai", "api_key": "sk-proj-abc123"},
            },
        }
        assert has_any_provider_key(settings) is True

    def test_with_anthropic_key(self):
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "anthropic": {"type": "anthropic", "api_key": "sk-ant-api03-xyz"},
            },
        }
        assert has_any_provider_key(settings) is True

    def test_ollama_only_returns_false(self):
        """Ollama has a placeholder key 'ollama' -- not a real provider key."""
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "ollama": {"type": "ollama", "api_key": "ollama"},
            },
        }
        assert has_any_provider_key(settings) is False

    def test_local_only_returns_false(self):
        """Local llama-cpp provider also has a placeholder key."""
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "local": {"type": "local", "api_key": "local"},
            },
        }
        assert has_any_provider_key(settings) is False

    def test_empty_providers(self):
        from ouroboros.config import has_any_provider_key

        assert has_any_provider_key({"providers": {}}) is False

    def test_no_providers_key(self):
        from ouroboros.config import has_any_provider_key

        assert has_any_provider_key({}) is False

    def test_mixed_providers_with_one_real_key(self):
        """If at least one non-local provider has a key, return True."""
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "ollama": {"type": "ollama", "api_key": "ollama"},
                "local": {"type": "local", "api_key": "local"},
                "openrouter": {"type": "openrouter", "api_key": "sk-or-v1-real"},
            },
        }
        assert has_any_provider_key(settings) is True

    def test_provider_with_empty_string_key(self):
        """Empty string api_key should not count."""
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "openrouter": {"type": "openrouter", "api_key": ""},
            },
        }
        assert has_any_provider_key(settings) is False


class TestSettingsRoundtrip:
    """save_settings -> load_settings preserves data."""

    def test_save_and_load_back(self, _patch_settings_path):
        from ouroboros.config import load_settings, save_settings

        original = {
            "OUROBOROS_MODEL": "test/roundtrip-model",
            "TOTAL_BUDGET": 42.5,
            "providers": {
                "openrouter": {
                    "type": "openrouter",
                    "api_key": "sk-test-roundtrip",
                    "base_url": "https://openrouter.ai/api/v1",
                },
            },
            "model_slots": {
                "main": {"provider_id": "openrouter", "model_id": "test/roundtrip-model"},
            },
        }
        save_settings(original)
        loaded = load_settings()
        assert loaded["OUROBOROS_MODEL"] == "test/roundtrip-model"
        assert loaded["TOTAL_BUDGET"] == 42.5
        assert loaded["providers"]["openrouter"]["api_key"] == "sk-test-roundtrip"

    def test_load_defaults_when_no_file(self, _patch_settings_path):
        """When no settings.json exists, defaults are returned."""
        from ouroboros.config import SETTINGS_DEFAULTS, load_settings

        loaded = load_settings()
        assert loaded["TOTAL_BUDGET"] == SETTINGS_DEFAULTS["TOTAL_BUDGET"]
        # Should have default providers after migration
        assert "providers" in loaded
        assert "openrouter" in loaded["providers"]

    def test_load_corrupted_file_returns_defaults(self, _patch_settings_path, tmp_data_dir):
        """Corrupted JSON falls back to defaults."""
        from ouroboros.config import load_settings

        settings_file = tmp_data_dir / "settings.json"
        settings_file.write_text("{invalid json!!!", encoding="utf-8")
        loaded = load_settings()
        # Should still get valid settings with defaults
        assert "providers" in loaded


class TestMigrateSettings:
    """Settings migration from flat v1 to provider/slot v2."""

    def test_already_migrated_passthrough(self):
        from ouroboros.config import migrate_settings

        settings = {
            "providers": {"openrouter": {"type": "openrouter", "api_key": "sk-x"}},
            "model_slots": {"main": {"provider_id": "openrouter", "model_id": "m"}},
        }
        result = migrate_settings(settings)
        assert result is settings  # Same object, not a copy

    def test_v1_flat_keys_migrate_to_v2(self):
        from ouroboros.config import migrate_settings

        v1_settings = {
            "OPENROUTER_API_KEY": "sk-or-v1-migrate-test",
            "OUROBOROS_MODEL": "anthropic/claude-sonnet-4.6",
            "OUROBOROS_MODEL_CODE": "anthropic/claude-sonnet-4.6",
        }
        result = migrate_settings(v1_settings)
        assert "providers" in result
        assert "model_slots" in result
        assert result["providers"]["openrouter"]["api_key"] == "sk-or-v1-migrate-test"
        assert result["model_slots"]["main"]["model_id"] == "anthropic/claude-sonnet-4.6"

    def test_use_local_override(self):
        from ouroboros.config import migrate_settings

        v1_settings = {
            "USE_LOCAL_MAIN": True,
            "OUROBOROS_MODEL": "some-model",
        }
        result = migrate_settings(v1_settings)
        assert result["model_slots"]["main"]["provider_id"] == "local"

    def test_websearch_defaults_to_openai_when_key_present(self):
        from ouroboros.config import migrate_settings

        v1_settings = {
            "OPENAI_API_KEY": "sk-proj-openai-test",
        }
        result = migrate_settings(v1_settings)
        assert result["model_slots"]["websearch"]["provider_id"] == "openai"


class TestProviderKeyMasking:
    """API keys should be masked in GET responses (server-side logic)."""

    def test_legacy_flat_key_masking(self):
        """Keys > 8 chars show first 8 + '...', shorter keys show '***'."""

        # Simulate what api_settings_get does
        settings = {
            "OPENROUTER_API_KEY": "sk-or-v1-abcdef1234567890",
            "OPENAI_API_KEY": "short",
            "ANTHROPIC_API_KEY": "",
            "GITHUB_TOKEN": "ghp_1234567890abcdef",
        }
        safe = dict(settings)
        for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN"):
            if safe.get(key):
                safe[key] = safe[key][:8] + "..." if len(safe[key]) > 8 else "***"

        assert safe["OPENROUTER_API_KEY"] == "sk-or-v1..."
        assert safe["OPENAI_API_KEY"] == "***"
        assert safe["ANTHROPIC_API_KEY"] == ""  # Empty stays empty
        assert safe["GITHUB_TOKEN"] == "ghp_1234..."

    def test_nested_provider_key_masking(self):
        """Nested provider api_key gets masked the same way."""
        import copy as _copy

        providers = {
            "openrouter": {"type": "openrouter", "api_key": "sk-or-v1-long-key-here"},
            "ollama": {"type": "ollama", "api_key": "ollama"},
            "empty": {"type": "custom", "api_key": ""},
        }
        safe_providers = _copy.deepcopy(providers)
        for pid, p in safe_providers.items():
            key = p.get("api_key", "")
            p["api_key"] = key[:8] + "..." if len(key) > 8 else ("***" if key else "")

        assert safe_providers["openrouter"]["api_key"] == "sk-or-v1..."
        assert safe_providers["ollama"]["api_key"] == "***"
        assert safe_providers["empty"]["api_key"] == ""


# ===========================================================================
# HTTP endpoint tests (via TestClient)
# ===========================================================================


class TestHealthEndpoint:
    """GET /api/health returns status and version info."""

    def test_health_returns_ok(self, client: TestClient):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_contains_version_fields(self, client: TestClient):
        resp = client.get("/api/health")
        data = resp.json()
        assert "version" in data
        assert "runtime_version" in data
        assert "app_version" in data

    def test_health_version_is_string(self, client: TestClient):
        resp = client.get("/api/health")
        data = resp.json()
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0


class TestSettingsGetEndpoint:
    """GET /api/settings returns masked settings."""

    def test_settings_get_returns_200(self, client: TestClient):
        resp = client.get("/api/settings")
        assert resp.status_code == 200

    def test_settings_get_has_model(self, client: TestClient):
        resp = client.get("/api/settings")
        data = resp.json()
        assert "OUROBOROS_MODEL" in data
        assert data["OUROBOROS_MODEL"] == "test/model-main"

    def test_settings_get_masks_api_keys(self, client: TestClient):
        resp = client.get("/api/settings")
        data = resp.json()
        # The seeded key is "sk-or-v1-abcdef1234567890" (len > 8)
        key_val = data.get("OPENROUTER_API_KEY", "")
        assert key_val.endswith("..."), f"Expected masked key, got: {key_val}"
        assert len(key_val) == 11  # 8 chars + "..."

    def test_settings_get_masks_nested_provider_keys(self, client: TestClient):
        resp = client.get("/api/settings")
        data = resp.json()
        providers = data.get("providers", {})
        or_key = providers.get("openrouter", {}).get("api_key", "")
        assert or_key.endswith("..."), f"Nested key not masked: {or_key}"

    def test_settings_get_contains_providers_and_slots(self, client: TestClient):
        resp = client.get("/api/settings")
        data = resp.json()
        assert "providers" in data
        assert "model_slots" in data


class TestSettingsPostEndpoint:
    """POST /api/settings saves and merges settings."""

    def test_post_updates_flat_key(self, client: TestClient):
        resp = client.post("/api/settings", json={"TOTAL_BUDGET": 99.9})
        assert resp.status_code == 200
        assert resp.json()["status"] == "saved"

        # Verify it was saved
        get_resp = client.get("/api/settings")
        assert get_resp.json()["TOTAL_BUDGET"] == 99.9

    def test_post_deep_merges_providers(self, client: TestClient):
        """Posting a partial provider update should merge, not replace."""
        # First, verify the seeded openrouter provider exists
        resp1 = client.get("/api/settings")
        assert "openrouter" in resp1.json()["providers"]

        # Update only the openai provider
        client.post("/api/settings", json={
            "providers": {
                "openai": {"api_key": "sk-proj-new-key-1234567890"},
            },
        })
        resp2 = client.get("/api/settings")
        data = resp2.json()
        # openrouter should still be there
        assert "openrouter" in data["providers"]
        # openai should have the masked new key
        assert data["providers"]["openai"]["api_key"] == "sk-proj-..."

    def test_post_deep_merges_model_slots(self, client: TestClient):
        """Posting a partial slot update should merge, not replace."""
        client.post("/api/settings", json={
            "model_slots": {
                "main": {"model_id": "new/model-for-main"},
            },
        })
        resp = client.get("/api/settings")
        slots = resp.json()["model_slots"]
        assert slots["main"]["model_id"] == "new/model-for-main"
        # Other slots should still be present
        assert "light" in slots

    def test_post_invalid_json_returns_400(self, client: TestClient):
        resp = client.post(
            "/api/settings",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400


class TestProvidersListEndpoint:
    """GET /api/providers returns masked provider list."""

    def test_providers_list_returns_200(self, client: TestClient):
        resp = client.get("/api/providers")
        assert resp.status_code == 200

    def test_providers_list_masks_keys(self, client: TestClient):
        resp = client.get("/api/providers")
        data = resp.json()
        for pid, p in data.items():
            key = p.get("api_key", "")
            # Keys should be masked: either "xxx..." or "***" or ""
            assert "sk-or-v1-abcdef1234567890" not in key, f"Raw key leaked for {pid}"

    def test_providers_list_contains_seeded_providers(self, client: TestClient):
        resp = client.get("/api/providers")
        data = resp.json()
        assert "openrouter" in data


class TestProvidersTestEndpoint:
    """POST /api/providers/test validates provider connection."""

    def test_missing_base_url_returns_error(self, client: TestClient):
        resp = client.post("/api/providers/test", json={"api_key": "test"})
        data = resp.json()
        assert data["status"] == "error"
        assert "base_url" in data["error"].lower()

    def test_unreachable_provider_returns_error(self, client: TestClient):
        """Connecting to a non-existent URL should return an error status, not crash."""
        resp = client.post("/api/providers/test", json={
            "base_url": "http://127.0.0.1:1/v1",
            "api_key": "test-key",
        })
        data = resp.json()
        assert data["status"] == "error"
        assert "error" in data


class TestModelSlotsEndpoint:
    """GET /api/model-slots returns model slot config."""

    def test_model_slots_returns_200(self, client: TestClient):
        resp = client.get("/api/model-slots")
        assert resp.status_code == 200

    def test_model_slots_contains_main(self, client: TestClient):
        resp = client.get("/api/model-slots")
        data = resp.json()
        assert "main" in data

    def test_model_slots_structure(self, client: TestClient):
        """Each slot should have provider_id and model_id."""
        resp = client.get("/api/model-slots")
        data = resp.json()
        for slot_name, slot_data in data.items():
            assert "provider_id" in slot_data, f"Slot {slot_name} missing provider_id"
            assert "model_id" in slot_data, f"Slot {slot_name} missing model_id"


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    """Boundary and error-path tests."""

    def test_save_settings_creates_data_dir(self, tmp_path: pathlib.Path):
        """save_settings should create DATA_DIR if it doesn't exist."""
        from ouroboros.config import save_settings

        new_data = tmp_path / "new_nested" / "data"
        settings_file = new_data / "settings.json"
        lock_file = pathlib.Path(str(settings_file) + ".lock")

        with (
            patch("ouroboros.config.SETTINGS_PATH", settings_file),
            patch("ouroboros.config.DATA_DIR", new_data),
            patch("ouroboros.config._SETTINGS_LOCK", lock_file),
        ):
            save_settings({"TOTAL_BUDGET": 1.0})
            assert settings_file.exists()

    def test_has_any_provider_key_missing_type_field(self):
        """Provider entries without 'type' should be treated as requiring a key."""
        from ouroboros.config import has_any_provider_key

        settings = {
            "providers": {
                "custom": {"api_key": "some-key"},  # No 'type' field
            },
        }
        assert has_any_provider_key(settings) is True

    def test_migrate_settings_idempotent(self):
        """Running migrate twice should produce the same result."""
        from ouroboros.config import migrate_settings

        v1 = {"OPENROUTER_API_KEY": "sk-or-v1-test"}
        first = migrate_settings(v1)
        second = migrate_settings(first)
        assert first["providers"] == second["providers"]
        assert first["model_slots"] == second["model_slots"]

    def test_settings_post_does_not_overwrite_unmentioned_flat_keys(
        self, client: TestClient,
    ):
        """POSTing one key should not reset others to defaults."""
        # Read initial budget
        resp1 = client.get("/api/settings")
        original_budget = resp1.json()["TOTAL_BUDGET"]
        assert original_budget == 5.0  # seeded value

        # Update only model
        client.post("/api/settings", json={"OUROBOROS_MODEL": "new/model"})

        resp2 = client.get("/api/settings")
        assert resp2.json()["TOTAL_BUDGET"] == 5.0  # unchanged
        assert resp2.json()["OUROBOROS_MODEL"] == "new/model"

    def test_concurrent_save_load_does_not_corrupt(self, _patch_settings_path):
        """Multiple rapid save/load cycles should not produce corrupt data."""
        import threading

        from ouroboros.config import load_settings, save_settings

        errors: list[str] = []

        def writer(idx: int):
            try:
                for i in range(10):
                    save_settings({"TOTAL_BUDGET": float(idx * 100 + i), "providers": {}, "model_slots": {}})
            except Exception as e:
                errors.append(f"writer-{idx}: {e}")

        def reader():
            try:
                for _ in range(10):
                    s = load_settings()
                    assert isinstance(s, dict)
                    assert "TOTAL_BUDGET" in s or "providers" in s
            except Exception as e:
                errors.append(f"reader: {e}")

        threads = [
            threading.Thread(target=writer, args=(0,)),
            threading.Thread(target=writer, args=(1,)),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Concurrent errors: {errors}"

"""
Ouroboros — Shared configuration (single source of truth).

Paths, settings defaults, load/save with file locking.
Does not import anything from ouroboros.* (zero dependency level).
"""

from __future__ import annotations

import copy
import fcntl
import json
import logging
import os
import pathlib
import sys
import time
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HOME = pathlib.Path.home()
APP_ROOT = HOME / "Ouroboros"
REPO_DIR = APP_ROOT / "repo"
DATA_DIR = APP_ROOT / "data"
SETTINGS_PATH = DATA_DIR / "settings.json"
PID_FILE = APP_ROOT / "ouroboros.pid"
PORT_FILE = DATA_DIR / "state" / "server_port"

RESTART_EXIT_CODE = 42
PANIC_EXIT_CODE = 99
AGENT_SERVER_PORT = 8765


# ---------------------------------------------------------------------------
# Settings defaults
# ---------------------------------------------------------------------------

# Pre-seeded provider configurations
_DEFAULT_PROVIDERS: Dict[str, Dict[str, str]] = {
    "openrouter": {
        "name": "OpenRouter",
        "type": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "",
    },
    "openai": {
        "name": "OpenAI",
        "type": "openai",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
    },
    "anthropic": {
        "name": "Anthropic",
        "type": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "api_key": "",
    },
    "ollama": {
        "name": "Ollama",
        "type": "ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "ollama",
    },
    "local": {
        "name": "Local (llama-cpp)",
        "type": "local",
        "base_url": "http://127.0.0.1:8766/v1",
        "api_key": "local",
    },
}

# Per-slot model configuration: which provider + model each scenario uses
_DEFAULT_MODEL_SLOTS: Dict[str, Dict[str, str]] = {
    "main":      {"provider_id": "openrouter", "model_id": "anthropic/claude-sonnet-4.6"},
    "code":      {"provider_id": "openrouter", "model_id": "anthropic/claude-sonnet-4.6"},
    "light":     {"provider_id": "openrouter", "model_id": "google/gemini-3-flash-preview"},
    "fallback":  {"provider_id": "openrouter", "model_id": "google/gemini-3-flash-preview"},
    "websearch": {"provider_id": "openai",     "model_id": "gpt-5.2"},
    "vision":    {"provider_id": "openrouter", "model_id": "anthropic/claude-sonnet-4.6"},
    "tts":       {"provider_id": "openai",     "model_id": "tts-1-hd"},
    "stt":       {"provider_id": "openai",     "model_id": "whisper-1"},
}

SETTINGS_DEFAULTS: Dict[str, Any] = {
    # --- Legacy flat keys (kept for backwards compat with workers) ---
    "OPENROUTER_API_KEY": "",
    "OPENAI_API_KEY": "",
    "ANTHROPIC_API_KEY": "",
    "OUROBOROS_MODEL": "anthropic/claude-sonnet-4.6",
    "OUROBOROS_MODEL_CODE": "anthropic/claude-sonnet-4.6",
    "OUROBOROS_MODEL_LIGHT": "google/gemini-3-flash-preview",
    "OUROBOROS_MODEL_FALLBACK": "google/gemini-3-flash-preview",
    "CLAUDE_CODE_MODEL": "sonnet",
    "OUROBOROS_MAX_WORKERS": 5,
    "TOTAL_BUDGET": 10.0,
    "OUROBOROS_SOFT_TIMEOUT_SEC": 600,
    "OUROBOROS_HARD_TIMEOUT_SEC": 1800,
    "OUROBOROS_BG_MAX_ROUNDS": 5,
    "OUROBOROS_BG_WAKEUP_MIN": 30,
    "OUROBOROS_BG_WAKEUP_MAX": 7200,
    "OUROBOROS_EVO_COST_THRESHOLD": 0.10,
    "OUROBOROS_WEBSEARCH_MODEL": "gpt-5.2",
    "GITHUB_TOKEN": "",
    "GITHUB_REPO": "",
    # Local model (llama-cpp-python server)
    "LOCAL_MODEL_SOURCE": "",
    "LOCAL_MODEL_FILENAME": "",
    "LOCAL_MODEL_PORT": 8766,
    "LOCAL_MODEL_N_GPU_LAYERS": 0,
    "LOCAL_MODEL_CONTEXT_LENGTH": 16384,
    "LOCAL_MODEL_CHAT_FORMAT": "chatml-function-calling",
    "USE_LOCAL_MAIN": False,
    "USE_LOCAL_CODE": False,
    "USE_LOCAL_LIGHT": False,
    "USE_LOCAL_FALLBACK": False,
    # --- Voice settings ---
    "TTS_VOICE": "nova",
    "TTS_SPEED": 1.0,
    "TTS_AUTO_READ": False,
    "TTS_RESPONSE_FORMAT": "mp3",
    # --- New provider + slot architecture ---
    "providers": copy.deepcopy(_DEFAULT_PROVIDERS),
    "model_slots": copy.deepcopy(_DEFAULT_MODEL_SLOTS),
}


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
def read_version() -> str:
    try:
        if getattr(sys, "frozen", False):
            vp = pathlib.Path(sys._MEIPASS) / "VERSION"
        else:
            vp = pathlib.Path(__file__).parent.parent / "VERSION"
        return vp.read_text(encoding="utf-8").strip()
    except Exception:
        return "0.0.0"


# ---------------------------------------------------------------------------
# Settings migration (flat v1 → provider/slot v2)
# ---------------------------------------------------------------------------

# Map legacy flat key to new slot name
_LEGACY_MODEL_KEY_TO_SLOT = {
    "OUROBOROS_MODEL": "main",
    "OUROBOROS_MODEL_CODE": "code",
    "OUROBOROS_MODEL_LIGHT": "light",
    "OUROBOROS_MODEL_FALLBACK": "fallback",
    "OUROBOROS_WEBSEARCH_MODEL": "websearch",
}
_LEGACY_USE_LOCAL_TO_SLOT = {
    "USE_LOCAL_MAIN": "main",
    "USE_LOCAL_CODE": "code",
    "USE_LOCAL_LIGHT": "light",
    "USE_LOCAL_FALLBACK": "fallback",
}
_LEGACY_KEY_TO_PROVIDER = {
    "OPENROUTER_API_KEY": "openrouter",
    "OPENAI_API_KEY": "openai",
    "ANTHROPIC_API_KEY": "anthropic",
}


def migrate_settings(settings: dict) -> dict:
    """Migrate flat v1 settings to provider/slot v2 format.

    Idempotent: already-migrated settings pass through unchanged.
    Preserves all legacy flat keys for backwards compatibility.
    """
    if "providers" in settings and "model_slots" in settings:
        return settings  # Already migrated

    migrated = dict(settings)

    # Build providers from existing API keys
    providers = copy.deepcopy(_DEFAULT_PROVIDERS)
    for legacy_key, pid in _LEGACY_KEY_TO_PROVIDER.items():
        key_val = settings.get(legacy_key, "")
        if key_val:
            providers[pid]["api_key"] = key_val

    # Update local provider port from settings
    local_port = settings.get("LOCAL_MODEL_PORT", 8766)
    providers["local"]["base_url"] = f"http://127.0.0.1:{local_port}/v1"

    migrated["providers"] = providers

    # Determine default provider (first one with an API key, or openrouter)
    default_pid = "openrouter"
    for pid in ("openrouter", "openai", "anthropic"):
        if providers.get(pid, {}).get("api_key"):
            default_pid = pid
            break

    # Build model slots from legacy flat keys
    slots = copy.deepcopy(_DEFAULT_MODEL_SLOTS)
    for legacy_key, slot_name in _LEGACY_MODEL_KEY_TO_SLOT.items():
        model_val = settings.get(legacy_key)
        if model_val:
            slots[slot_name]["model_id"] = model_val
            slots[slot_name]["provider_id"] = default_pid

    # WebSearch defaults to OpenAI if available
    if providers.get("openai", {}).get("api_key"):
        slots["websearch"]["provider_id"] = "openai"

    # Vision slot uses same provider as main
    slots["vision"]["provider_id"] = slots["main"]["provider_id"]
    slots["vision"]["model_id"] = slots["main"]["model_id"]

    # Apply USE_LOCAL_* overrides
    for legacy_key, slot_name in _LEGACY_USE_LOCAL_TO_SLOT.items():
        use_local = settings.get(legacy_key, False)
        if isinstance(use_local, str):
            use_local = use_local.lower() in ("true", "1")
        if use_local:
            slots[slot_name]["provider_id"] = "local"

    migrated["model_slots"] = slots
    return migrated


def has_any_provider_key(settings: dict) -> bool:
    """Check if any provider has a configured API key (or is keyless like Ollama)."""
    providers = settings.get("providers", {})
    for pid, p in providers.items():
        ptype = p.get("type", "")
        # Ollama and local don't need real keys
        if ptype in ("ollama", "local"):
            continue
        if p.get("api_key"):
            return True
    return False


# ---------------------------------------------------------------------------
# Settings file locking
# ---------------------------------------------------------------------------
_SETTINGS_LOCK = pathlib.Path(str(SETTINGS_PATH) + ".lock")


def _acquire_settings_lock(timeout: float = 2.0) -> Optional[int]:
    start = time.time()
    while time.time() - start < timeout:
        try:
            fd = os.open(str(_SETTINGS_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            return fd
        except FileExistsError:
            try:
                if time.time() - _SETTINGS_LOCK.stat().st_mtime > 10:
                    _SETTINGS_LOCK.unlink()
                    continue
            except Exception:
                pass
            time.sleep(0.01)
        except Exception:
            break
    return None


def _release_settings_lock(fd: Optional[int]) -> None:
    if fd is not None:
        try:
            os.close(fd)
        except Exception:
            pass
    try:
        _SETTINGS_LOCK.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------
def load_settings() -> dict:
    fd = _acquire_settings_lock()
    try:
        if SETTINGS_PATH.exists():
            try:
                raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                return migrate_settings(raw)
            except Exception:
                log.warning("Failed to parse settings.json, using defaults", exc_info=True)
        return migrate_settings(dict(SETTINGS_DEFAULTS))
    finally:
        _release_settings_lock(fd)


def save_settings(settings: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd = _acquire_settings_lock()
    try:
        try:
            tmp = SETTINGS_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
            os.replace(str(tmp), str(SETTINGS_PATH))
        except OSError:
            SETTINGS_PATH.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    finally:
        _release_settings_lock(fd)


def apply_settings_to_env(settings: dict) -> None:
    """Push settings into environment variables for supervisor modules.

    Syncs new provider/slot config back to legacy env vars so forked
    workers that read env vars continue to work.
    """
    # Sync provider API keys back to legacy flat keys
    providers = settings.get("providers", {})
    for legacy_key, pid in _LEGACY_KEY_TO_PROVIDER.items():
        p = providers.get(pid, {})
        if p.get("api_key"):
            settings.setdefault(legacy_key, p["api_key"])

    # Sync model slots back to legacy flat keys
    slots = settings.get("model_slots", {})
    for legacy_key, slot_name in _LEGACY_MODEL_KEY_TO_SLOT.items():
        slot = slots.get(slot_name, {})
        if slot.get("model_id"):
            settings[legacy_key] = slot["model_id"]

    # Sync USE_LOCAL_* from provider_id
    for legacy_key, slot_name in _LEGACY_USE_LOCAL_TO_SLOT.items():
        slot = slots.get(slot_name, {})
        settings[legacy_key] = slot.get("provider_id") == "local"

    env_keys = [
        "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
        "OUROBOROS_MODEL", "OUROBOROS_MODEL_CODE", "OUROBOROS_MODEL_LIGHT",
        "OUROBOROS_MODEL_FALLBACK", "CLAUDE_CODE_MODEL",
        "TOTAL_BUDGET", "GITHUB_TOKEN", "GITHUB_REPO",
        "OUROBOROS_BG_MAX_ROUNDS", "OUROBOROS_BG_WAKEUP_MIN", "OUROBOROS_BG_WAKEUP_MAX",
        "OUROBOROS_EVO_COST_THRESHOLD", "OUROBOROS_WEBSEARCH_MODEL",
        "LOCAL_MODEL_SOURCE", "LOCAL_MODEL_FILENAME",
        "LOCAL_MODEL_PORT", "LOCAL_MODEL_N_GPU_LAYERS", "LOCAL_MODEL_CONTEXT_LENGTH",
        "LOCAL_MODEL_CHAT_FORMAT",
        "USE_LOCAL_MAIN", "USE_LOCAL_CODE", "USE_LOCAL_LIGHT", "USE_LOCAL_FALLBACK",
    ]
    for k in env_keys:
        val = settings.get(k)
        if val is None or val == "":
            os.environ.pop(k, None)
        else:
            os.environ[k] = str(val)


# ---------------------------------------------------------------------------
# PID lock (single instance) — uses fcntl.flock for crash-proof locking.
# The OS releases flock automatically when the process dies (even SIGKILL),
# so stale lock files can never block future launches.
# ---------------------------------------------------------------------------
_lock_fd = None


def acquire_pid_lock() -> bool:
    global _lock_fd
    APP_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        _lock_fd = open(str(PID_FILE), "w")
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fd.write(str(os.getpid()))
        _lock_fd.flush()
        return True
    except (IOError, OSError):
        return False


def release_pid_lock() -> None:
    global _lock_fd
    if _lock_fd is not None:
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
        except Exception:
            pass
        _lock_fd = None
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass

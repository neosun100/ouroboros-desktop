"""
Live integration tests for HTTP API endpoints.

Tests TTS, STT, file upload, providers, and model slots endpoints
via Starlette TestClient with real LLM/TTS/STT API calls.

Credentials via env vars (never hardcoded):
  LITELLM_BASE_URL — LiteLLM proxy endpoint
  LITELLM_API_KEY  — API key for the proxy

Run: LITELLM_BASE_URL=... LITELLM_API_KEY=... python -m pytest tests/test_endpoints_live.py -v
"""

from __future__ import annotations

import io
import json
import os
import pathlib
import tempfile

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

_BASE_URL = os.environ.get("LITELLM_BASE_URL", "")
_API_KEY = os.environ.get("LITELLM_API_KEY", "")

pytestmark = pytest.mark.skipif(
    not _BASE_URL or not _API_KEY,
    reason="LITELLM_BASE_URL and LITELLM_API_KEY required",
)


@pytest.fixture(scope="module")
def test_settings():
    """Write test settings to a temp dir and redirect config module."""
    tmpdir = tempfile.mkdtemp()
    import ouroboros.config as cfg

    orig_path = cfg.SETTINGS_PATH
    orig_lock = cfg._SETTINGS_LOCK
    orig_data = cfg.DATA_DIR

    cfg.SETTINGS_PATH = pathlib.Path(tmpdir) / "settings.json"
    cfg._SETTINGS_LOCK = pathlib.Path(tmpdir) / "settings.json.lock"
    cfg.DATA_DIR = pathlib.Path(tmpdir)

    settings = {
        "providers": {
            "litellm": {
                "name": "LiteLLM",
                "type": "custom",
                "base_url": _BASE_URL.rstrip("/") + "/v1",
                "api_key": _API_KEY,
            },
        },
        "model_slots": {
            "main":      {"provider_id": "litellm", "model_id": "openai/gpt-4.1-nano"},
            "code":      {"provider_id": "litellm", "model_id": "openai/gpt-4.1-nano"},
            "light":     {"provider_id": "litellm", "model_id": "deepseek/deepseek-chat"},
            "fallback":  {"provider_id": "litellm", "model_id": "openai/gpt-4.1-nano"},
            "websearch": {"provider_id": "litellm", "model_id": "openai/gpt-4o-mini"},
            "vision":    {"provider_id": "litellm", "model_id": "openai/gpt-4.1-mini"},
            "tts":       {"provider_id": "litellm", "model_id": "openai/tts-1-hd"},
            "stt":       {"provider_id": "litellm", "model_id": "openai/whisper-1"},
        },
        "TTS_VOICE": "nova",
        "TTS_SPEED": 1.0,
        "TTS_RESPONSE_FORMAT": "mp3",
        "TOTAL_BUDGET": 10.0,
    }
    cfg.save_settings(settings)
    cfg.apply_settings_to_env(settings)

    yield settings

    cfg.SETTINGS_PATH = orig_path
    cfg._SETTINGS_LOCK = orig_lock
    cfg.DATA_DIR = orig_data


@pytest.fixture(scope="module")
def client(test_settings):
    """Build a minimal Starlette app with the endpoints under test."""
    import ouroboros.config as cfg
    from ouroboros.audio_api import api_tts, api_stt, api_tts_voices
    import base64 as b64mod

    async def api_upload(request: Request):
        form = await request.form()
        file = form.get("file")
        if not file:
            return JSONResponse({"error": "file required"}, status_code=400)
        content = await file.read()
        filename = file.filename or "uploaded_file"
        size = len(content)
        if size > 10 * 1024 * 1024:
            return JSONResponse({"error": "File too large"}, status_code=400)
        ext = pathlib.Path(filename).suffix.lower()
        result = {"filename": filename, "size": size, "type": "unknown"}
        text_ext = {".txt", ".md", ".py", ".js", ".json", ".csv", ".log"}
        img_ext = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        if ext in text_ext or size < 512 * 1024:
            try:
                text = content.decode("utf-8")
                result.update(type="text", content=text[:50000], truncated=len(text) > 50000)
            except UnicodeDecodeError:
                pass
        if ext in img_ext:
            result.update(type="image", base64=b64mod.b64encode(content).decode("ascii"), mime="image/png")
        return JSONResponse(result)

    async def api_providers_list(request: Request):
        settings = cfg.load_settings()
        providers = settings.get("providers", {})
        safe = {}
        for pid, p in providers.items():
            safe[pid] = dict(p)
            key = p.get("api_key", "")
            safe[pid]["api_key"] = key[:8] + "..." if len(key) > 8 else ("***" if key else "")
        return JSONResponse(safe)

    async def api_model_slots_get(request: Request):
        settings = cfg.load_settings()
        return JSONResponse(settings.get("model_slots", {}))

    app = Starlette(routes=[
        Route("/api/tts", endpoint=api_tts, methods=["POST"]),
        Route("/api/tts/voices", endpoint=api_tts_voices, methods=["GET"]),
        Route("/api/stt", endpoint=api_stt, methods=["POST"]),
        Route("/api/upload", endpoint=api_upload, methods=["POST"]),
        Route("/api/providers", endpoint=api_providers_list, methods=["GET"]),
        Route("/api/model-slots", endpoint=api_model_slots_get, methods=["GET"]),
    ])
    return TestClient(app)


# ---------------------------------------------------------------------------
# Provider & Slot endpoints
# ---------------------------------------------------------------------------

class TestProviderEndpoints:

    def test_providers_list(self, client):
        r = client.get("/api/providers")
        assert r.status_code == 200
        data = r.json()
        assert "litellm" in data
        assert "..." in data["litellm"]["api_key"]

    def test_model_slots(self, client):
        r = client.get("/api/model-slots")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 8
        for slot in ("main", "code", "light", "fallback", "websearch", "vision", "tts", "stt"):
            assert slot in data

    def test_tts_voices(self, client):
        r = client.get("/api/tts/voices")
        assert r.status_code == 200
        voices = r.json()["voices"]
        assert len(voices) == 6
        ids = {v["id"] for v in voices}
        assert {"alloy", "echo", "fable", "nova", "onyx", "shimmer"} == ids


# ---------------------------------------------------------------------------
# TTS endpoints (real API calls)
# ---------------------------------------------------------------------------

class TestTTSEndpoint:

    def test_tts_returns_audio(self, client):
        """POST /api/tts returns valid MP3 audio bytes."""
        r = client.post("/api/tts", json={"text": "Integration test.", "voice": "nova"})
        assert r.status_code == 200
        assert len(r.content) > 1000
        assert r.headers["content-type"] == "audio/mpeg"

    def test_tts_different_voice(self, client):
        """TTS works with shimmer voice."""
        r = client.post("/api/tts", json={"text": "Shimmer voice test.", "voice": "shimmer"})
        assert r.status_code == 200
        assert len(r.content) > 1000

    def test_tts_empty_text_400(self, client):
        """Empty text returns 400."""
        r = client.post("/api/tts", json={"text": ""})
        assert r.status_code == 400

    def test_tts_all_voices(self, client):
        """All 6 voices produce audio."""
        for voice in ("alloy", "echo", "fable", "nova", "onyx", "shimmer"):
            r = client.post("/api/tts", json={"text": "Hi.", "voice": voice})
            assert r.status_code == 200, f"Voice {voice} failed"
            assert len(r.content) > 500, f"Voice {voice} too small: {len(r.content)}"


# ---------------------------------------------------------------------------
# STT endpoint (real API call)
# ---------------------------------------------------------------------------

class TestSTTEndpoint:

    def test_stt_transcribes_audio(self, client):
        """POST /api/stt transcribes TTS output back to text."""
        # Generate audio first
        tts_resp = client.post("/api/tts", json={"text": "Hello world testing.", "voice": "nova"})
        assert tts_resp.status_code == 200
        audio = tts_resp.content

        # Transcribe it
        r = client.post("/api/stt", files={"audio": ("test.mp3", io.BytesIO(audio), "audio/mpeg")})
        assert r.status_code == 200
        text = r.json().get("text", "")
        assert len(text) > 0

    def test_stt_no_file_400(self, client):
        """Missing audio file returns 400."""
        r = client.post("/api/stt", files={})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------

class TestUploadEndpoint:

    def test_upload_text_file(self, client):
        """Text file upload extracts content."""
        content = b"# Test\n\ndef hello(): pass\n"
        r = client.post("/api/upload", files={"file": ("test.py", io.BytesIO(content), "text/plain")})
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "text"
        assert data["filename"] == "test.py"
        assert "def hello" in data["content"]
        assert data["truncated"] is False

    def test_upload_markdown(self, client):
        """Markdown file detected as text."""
        content = b"# Title\n\n- item 1\n- item 2\n"
        r = client.post("/api/upload", files={"file": ("readme.md", io.BytesIO(content), "text/markdown")})
        assert r.status_code == 200
        assert r.json()["type"] == "text"

    def test_upload_image(self, client):
        """Image file returns base64 encoded data."""
        # Minimal valid PNG
        import struct, zlib
        sig = b'\x89PNG\r\n\x1a\n'
        ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
        ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
        raw = zlib.compress(b'\x00\xff\x00\x00')
        idat_crc = zlib.crc32(b'IDAT' + raw) & 0xffffffff
        idat = struct.pack('>I', len(raw)) + b'IDAT' + raw + struct.pack('>I', idat_crc)
        iend_crc = zlib.crc32(b'IEND') & 0xffffffff
        iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
        png = sig + ihdr + idat + iend

        r = client.post("/api/upload", files={"file": ("img.png", io.BytesIO(png), "image/png")})
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "image"
        assert data["mime"] == "image/png"
        assert len(data["base64"]) > 0

    def test_upload_too_large_400(self, client):
        """File over 10MB returns 400."""
        big = b"x" * (11 * 1024 * 1024)
        r = client.post("/api/upload", files={"file": ("big.bin", io.BytesIO(big), "application/octet-stream")})
        assert r.status_code == 400

    def test_upload_no_file_400(self, client):
        """Missing file returns 400."""
        r = client.post("/api/upload", files={})
        assert r.status_code == 400

    def test_upload_json_file(self, client):
        """JSON file detected as text."""
        content = b'{"key": "value", "count": 42}'
        r = client.post("/api/upload", files={"file": ("data.json", io.BytesIO(content), "application/json")})
        assert r.status_code == 200
        assert r.json()["type"] == "text"

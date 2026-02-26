"""TTS / STT API route handlers.

Extracted from server.py to keep module sizes under the 1050-line limit (BIBLE P5).
"""

from __future__ import annotations

import io
import logging

from starlette.requests import Request
from starlette.responses import JSONResponse

from ouroboros.config import load_settings

log = logging.getLogger(__name__)

_CONTENT_TYPES = {
    "mp3": "audio/mpeg",
    "opus": "audio/opus",
    "aac": "audio/aac",
    "flac": "audio/flac",
    "wav": "audio/wav",
}


async def api_tts(request: Request):
    """Convert text to speech using the configured TTS provider."""
    body = await request.json()
    text = body.get("text", "")
    voice = body.get("voice")
    speed = body.get("speed")

    if not text:
        return JSONResponse({"error": "text required"}, status_code=400)

    from ouroboros.llm import LLMClient
    settings = load_settings()
    llm = LLMClient()

    slot_config = llm.get_slot_config("tts")
    provider_config = llm.get_provider_config(slot_config.provider_id)
    if not provider_config:
        return JSONResponse({"error": "TTS provider not configured"}, status_code=400)

    voice = voice or settings.get("TTS_VOICE", "nova")
    speed = float(speed or settings.get("TTS_SPEED", 1.0))
    response_format = settings.get("TTS_RESPONSE_FORMAT", "mp3")

    try:
        from openai import OpenAI
        from starlette.responses import StreamingResponse

        client = OpenAI(base_url=provider_config.base_url, api_key=provider_config.api_key)
        response = client.audio.speech.create(
            model=slot_config.model_id,
            voice=voice,
            input=text,
            speed=speed,
            response_format=response_format,
        )

        content_type = _CONTENT_TYPES.get(response_format, "audio/mpeg")
        return StreamingResponse(
            response.iter_bytes(),
            media_type=content_type,
            headers={"Content-Disposition": f"inline; filename=tts.{response_format}"},
        )
    except Exception as e:
        log.warning("TTS failed: %s", e)
        return JSONResponse({"error": f"TTS failed: {str(e)}"}, status_code=500)


async def api_stt(request: Request):
    """Transcribe audio to text using the configured STT provider."""
    form = await request.form()
    audio_file = form.get("audio")
    if not audio_file:
        return JSONResponse({"error": "audio file required"}, status_code=400)

    from ouroboros.llm import LLMClient
    llm = LLMClient()

    slot_config = llm.get_slot_config("stt")
    provider_config = llm.get_provider_config(slot_config.provider_id)
    if not provider_config:
        return JSONResponse({"error": "STT provider not configured"}, status_code=400)

    try:
        from openai import OpenAI

        client = OpenAI(base_url=provider_config.base_url, api_key=provider_config.api_key)

        audio_bytes = await audio_file.read()
        audio_io = io.BytesIO(audio_bytes)
        audio_io.name = audio_file.filename or "audio.webm"

        transcript = client.audio.transcriptions.create(
            model=slot_config.model_id,
            file=audio_io,
        )
        return JSONResponse({"text": transcript.text})
    except Exception as e:
        log.warning("STT failed: %s", e)
        return JSONResponse({"error": f"STT failed: {str(e)}"}, status_code=500)


async def api_tts_voices(request: Request):
    """Return available TTS voices."""
    voices = [
        {"id": "alloy", "name": "Alloy", "description": "Neutral, balanced"},
        {"id": "echo", "name": "Echo", "description": "Warm, conversational"},
        {"id": "fable", "name": "Fable", "description": "Expressive, storytelling"},
        {"id": "nova", "name": "Nova", "description": "Friendly, energetic"},
        {"id": "onyx", "name": "Onyx", "description": "Deep, authoritative"},
        {"id": "shimmer", "name": "Shimmer", "description": "Clear, gentle"},
    ]
    return JSONResponse({"voices": voices})

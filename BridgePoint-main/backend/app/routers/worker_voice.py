"""Unauthenticated pre-registration voice extraction endpoint."""
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from app.services.worker_voice import MAX_AUDIO_BYTES, extract_worker_profile

router = APIRouter(prefix="/api/workers", tags=["Worker registration"])


@router.post("/voice-onboard")
async def voice_onboard_worker(
    audio: UploadFile = File(...),
    language_hint: str = Form("en"),
):
    mime_type = (audio.content_type or "").lower()
    if mime_type in {"", "application/octet-stream", "binary/octet-stream"}:
        mime_type = "audio/webm"
    if not mime_type.startswith("audio/"):
        raise HTTPException(415, "Upload an audio recording.")
    payload = await audio.read()
    if len(payload) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio recording must be 10 MB or smaller.")
    return {"status": "success", "structured_profile": extract_worker_profile(payload, mime_type, language_hint).model_dump()}

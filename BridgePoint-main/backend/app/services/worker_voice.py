"""Gemini-backed extraction for the worker-registration voice flow.

Adapted from Ubiquity's voice-onboarding contract, but deliberately does not
create workers or provide production fallbacks.  Registration remains owned by
the existing auth router and its cooperative verification lifecycle.
"""
import json
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.config import DEMO_MODE, GEMINI_API_KEY, GEMINI_MODEL

try:  # Keep local development usable when the optional AI dependency is absent.
    from google import genai
    from google.genai import types
except ImportError:  # pragma: no cover - exercised by configuration path
    genai = None
    types = None


SUPPORTED_LANGUAGES = {"ta": "Tamil", "te": "Telugu", "hi": "Hindi", "en": "English"}
LANGUAGE_ALIASES = {"tamil": "ta", "telugu": "te", "hindi": "hi", "english": "en"}
MAX_AUDIO_BYTES = 10 * 1024 * 1024


class VoiceProfile(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    primary_skill: str = Field(min_length=2, max_length=80)
    sub_skills: list[str] = Field(default_factory=list, max_length=12)
    experience_years: int = Field(ge=0, le=60)
    expected_rate: float = Field(gt=0, le=100000)
    operating_location: str = Field(min_length=2, max_length=120)
    availability: str = Field(default="Not specified", max_length=120)
    language: str = Field(max_length=40)
    transcript: str = Field(min_length=1, max_length=5000)
    confidence: float = Field(ge=0, le=1)


def normalize_language(value: str | None) -> str:
    requested = (value or "en").strip().lower()
    requested = LANGUAGE_ALIASES.get(requested, requested)
    if requested not in SUPPORTED_LANGUAGES:
        raise HTTPException(400, "Unsupported language. Choose Tamil, Telugu, Hindi, or English.")
    return requested


def _demo_profile(language: str) -> VoiceProfile:
    # A deterministic path is only useful in an explicitly configured demo.
    names = {"ta": "Demo Worker", "te": "Demo Worker", "hi": "Demo Worker", "en": "Demo Worker"}
    return VoiceProfile(full_name=names[language], primary_skill="General labor", sub_skills=[], experience_years=1,
        expected_rate=500, operating_location="Chennai", availability="Not specified", language=SUPPORTED_LANGUAGES[language],
        transcript="Demo voice registration", confidence=0.25)


def extract_worker_profile(audio_bytes: bytes, mime_type: str, language_hint: str | None) -> VoiceProfile:
    language = normalize_language(language_hint)
    if len(audio_bytes) < 100:
        raise HTTPException(400, "BridgePoint couldn't understand the recording. Please record again.")
    if not GEMINI_API_KEY or not genai or not types:
        if DEMO_MODE:
            return _demo_profile(language)
        raise HTTPException(503, "Voice registration is not configured. Please use manual registration.")

    prompt = (
        "You extract a BridgePoint worker registration from spoken Tamil, Telugu, Hindi, English, or mixed audio. "
        "Return JSON only with: full_name, primary_skill, sub_skills, experience_years, expected_rate, "
        "operating_location, availability, language, transcript, confidence. Translate skill/location labels to clear "
        "English where appropriate. Do not infer missing critical facts: use empty strings or 0 and lower confidence. "
        f"The worker selected {SUPPORTED_LANGUAGES[language]} as their language hint."
    )
    try:
        response = genai.Client(api_key=GEMINI_API_KEY).models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Part.from_bytes(data=audio_bytes, mime_type=mime_type), prompt],
            config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=VoiceProfile, temperature=0.1),
        )
        parsed: Any = getattr(response, "parsed", None)
        if isinstance(parsed, BaseModel):
            parsed = parsed.model_dump()
        if not isinstance(parsed, dict):
            parsed = json.loads(str(getattr(response, "text", "")).strip().removeprefix("```json").removesuffix("```").strip())
        profile = VoiceProfile.model_validate(parsed)
    except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "BridgePoint couldn't understand the recording. Please record again.") from exc
    except Exception as exc:
        raise HTTPException(502, "BridgePoint couldn't process the recording. Please record again.") from exc

    critical = (profile.full_name, profile.primary_skill, profile.operating_location, profile.experience_years, profile.expected_rate)
    unintelligible = ("no intelligible", "could not recognize", "cannot understand", "no speech detected", "inaudible")
    if profile.confidence < 0.35 or not profile.transcript.strip() or any(not value for value in critical) or any(marker in profile.transcript.lower() for marker in unintelligible):
        raise HTTPException(400, "BridgePoint couldn't understand the recording. Please record again.")
    return profile

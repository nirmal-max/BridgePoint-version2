import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.services.worker_voice import VoiceProfile, extract_worker_profile, normalize_language
from app.main import app


class WorkerVoiceTests(unittest.TestCase):
    def test_language_aliases_match_voice_registration_choices(self):
        self.assertEqual(normalize_language("Tamil"), "ta")
        self.assertEqual(normalize_language("te"), "te")
        with self.assertRaises(HTTPException):
            normalize_language("French")

    def test_real_audio_never_receives_demo_profile_when_ai_is_unconfigured(self):
        with patch("app.services.worker_voice.GEMINI_API_KEY", ""), patch("app.services.worker_voice.DEMO_MODE", False):
            with self.assertRaises(HTTPException) as error:
                extract_worker_profile(b"a" * 100, "audio/webm", "en")
        self.assertEqual(error.exception.status_code, 503)

    def test_short_or_unintelligible_audio_requires_retry(self):
        with self.assertRaises(HTTPException) as error:
            extract_worker_profile(b"short", "audio/webm", "en")
        self.assertEqual(error.exception.status_code, 400)

    def test_profile_contract_requires_critical_fields(self):
        with self.assertRaises(Exception):
            VoiceProfile(full_name="", primary_skill="", experience_years=0, expected_rate=0,
                         operating_location="", language="English", transcript="", confidence=0)

    def test_voice_endpoint_accepts_ubiquity_style_webm_multipart_contract(self):
        profile = VoiceProfile(full_name="Anita Kumar", primary_skill="Plumbing", sub_skills=["Pipe repair"],
            experience_years=4, expected_rate=700, operating_location="Chennai", availability="Weekdays",
            language="Tamil", transcript="test transcript", confidence=.91)
        with patch("app.routers.worker_voice.extract_worker_profile", return_value=profile):
            with TestClient(app) as client:
                response = client.post("/api/workers/voice-onboard", data={"language_hint": "ta"},
                    files={"audio": ("voice.webm", b"a" * 100, "audio/webm")})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["structured_profile"]["full_name"], "Anita Kumar")


if __name__ == "__main__":
    unittest.main()

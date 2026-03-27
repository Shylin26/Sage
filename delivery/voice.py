import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from pathlib import Path
from config import get_settings

settings = get_settings()


def build_voice_script(briefing: dict) -> str:
    actions = " ".join(
        line.strip()
        for line in briefing.get("actions", "").strip().splitlines()
        if line.strip()
    )
    return f"""
{briefing.get('hook', '')}

Situation. {briefing.get('situation', '')}

Your action items. {actions}

Financial pulse. {briefing.get('financial', '')}

{briefing.get('close', '')}
""".strip()


def _try_elevenlabs(script: str, output_path: str) -> bool:
    """Try ElevenLabs first — best quality."""
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import save, VoiceSettings

        client = ElevenLabs(api_key=settings.elevenlabs_api_key)
        audio  = client.text_to_speech.convert(
            voice_id       = "JBFqnCBsd6RMkjVDRZzb",
            text           = script,
            model_id       = "eleven_turbo_v2",
            voice_settings = VoiceSettings(
                stability        = 0.4,
                similarity_boost = 0.8,
                style            = 0.2,
                use_speaker_boost= True,
            )
        )
        save(audio, output_path)
        print(f"   ✓ ElevenLabs voice saved → {output_path}")
        return True
    except Exception as e:
        print(f"   ✗ ElevenLabs failed: {e}")
        return False


def _try_gtts(script: str, output_path: str) -> bool:
    """
    Fallback: gTTS (Google Text-to-Speech).
    Completely free, no API key, no limits.
    LEARN: gTTS sends text to Google's TTS API (same one used by Google Translate)
    and returns an MP3. No authentication needed.
    """
    try:
        from gtts import gTTS
        tts = gTTS(text=script, lang='en', slow=False)
        tts.save(output_path)
        size_kb = Path(output_path).stat().st_size // 1024
        print(f"   ✓ gTTS voice saved → {output_path} ({size_kb} KB)")
        return True
    except Exception as e:
        print(f"   ✗ gTTS failed: {e}")
        return False


def generate_voice(briefing: dict, output_path: str = "data/briefing.mp3") -> bool:
    script = build_voice_script(briefing)
    print(f"  Generating voice — {len(script)} characters...")

    # Try ElevenLabs first, fall back to gTTS
    if _try_elevenlabs(script, output_path):
        return True
    print("  Falling back to gTTS...")
    return _try_gtts(script, output_path)


async def test():
    mock_briefing = {
        "date":         "Thursday, 26 March 2026",
        "hook":         "Your exams are in 3 weeks — tonight is not the night to slack.",
        "situation":    "No classes tomorrow. Focus on DSA revision and Duolingo streak.",
        "actions":      "Revise sorting algorithms\nComplete Duolingo lesson\nReview HireReady newsletter",
        "financial":    "No financial alerts today.",
        "close":        "One solid evening of work compounds into the internship you want, Parisha.",
        "signal_count": 5,
    }
    generate_voice(mock_briefing)

if __name__ == "__main__":
    asyncio.run(test())

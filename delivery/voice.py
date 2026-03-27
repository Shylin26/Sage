import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from pathlib import Path
from config import get_settings

settings = get_settings()


def build_voice_script(briefing: dict) -> str:
    """
    LEARN: We clean up the script for speech — remove markdown,
    bullets, dashes. Text that looks good on screen sounds weird
    when read aloud. Speech needs natural sentence flow.
    """
    actions_raw = briefing.get("actions", "")
    actions = ". ".join(
        line.strip().lstrip("-•*→").strip()
        for line in actions_raw.strip().splitlines()
        if line.strip() and not line.strip().startswith("Parisha, let")
    )

    return f"""
{briefing.get('hook', '')}

Here is your situation report. {briefing.get('situation', '')}

Your action items for tonight. {actions}

Financial update. {briefing.get('financial', '')}

{briefing.get('close', '')}
""".strip()


def _try_elevenlabs(script: str, output_path: str) -> bool:
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs import save, VoiceSettings
        client = ElevenLabs(api_key=settings.elevenlabs_api_key)
        audio  = client.text_to_speech.convert(
            voice_id       = "JBFqnCBsd6RMkjVDRZzb",
            text           = script,
            model_id       = "eleven_turbo_v2",
            voice_settings = VoiceSettings(
                stability=0.4, similarity_boost=0.8,
                style=0.2, use_speaker_boost=True,
            )
        )
        save(audio, output_path)
        print(f"   ✓ ElevenLabs voice saved ({Path(output_path).stat().st_size // 1024} KB)")
        return True
    except Exception as e:
        print(f"   ✗ ElevenLabs failed: {e}")
        return False


def _try_gtts(script: str, output_path: str) -> bool:
    """
    LEARN: gTTS tld='co.in' uses Google's Indian English voice server.
    It sounds noticeably more natural for Indian names and context
    than the default US English voice.
    """
    try:
        from gtts import gTTS
        tts = gTTS(text=script, lang='en', tld='co.in', slow=False)
        tts.save(output_path)
        size_kb = Path(output_path).stat().st_size // 1024
        print(f"   ✓ gTTS (Indian English) saved → {output_path} ({size_kb} KB)")
        return True
    except Exception as e:
        print(f"   ✗ gTTS failed: {e}")
        return False


def generate_voice(briefing: dict, output_path: str = "data/briefing.mp3") -> bool:
    script = build_voice_script(briefing)
    print(f"  Generating voice — {len(script)} chars...")
    if _try_elevenlabs(script, output_path):
        return True
    print("  Falling back to gTTS...")
    return _try_gtts(script, output_path)


if __name__ == "__main__":
    mock = {
        "hook":      "Parisha, your exams are in 3 weeks and tonight is the best time to start.",
        "situation": "No classes tomorrow. Focus on DSA revision and Duolingo streak.",
        "actions":   "Revise sorting algorithms\nComplete Duolingo lesson\nReview HireReady newsletter",
        "financial": "No financial alerts today.",
        "close":     "One solid evening compounds into the internship you want, Parisha.",
    }
    generate_voice(mock)
    print("Done — open data/briefing.mp3")

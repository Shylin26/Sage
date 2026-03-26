import os
import sys 
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
from pathlib import Path
from elevenlabs.client import ElevenLabs
from elevenlabs import save, VoiceSettings
from config import get_settings

settings = get_settings()
client   = ElevenLabs(api_key=settings.elevenlabs_api_key)

VOICE_ID = "JBFqnCBsd6RMkjVDRZzb" 

def build_voice_script(briefing: dict) -> str:
    actions = " ".join(
        line.strip()
        for line in briefing.get("actions", "").strip().splitlines()
        if line.strip()
    )
    return f"""
{briefing.get('hook', '')}

Situation. {briefing.get('situation', '')}

Your action items for today. {actions}

Financial pulse. {briefing.get('financial', '')}

{briefing.get('close', '')}
""".strip()


def generate_voice(briefing: dict, output_path: str = "data/briefing.mp3") -> bool:
    try:
        script = build_voice_script(briefing)
        print(f"  Generating voice — {len(script)} characters...")

        audio = client.text_to_speech.convert(
            voice_id  = VOICE_ID,
            text      = script,
            model_id  = "eleven_turbo_v2",
            voice_settings = VoiceSettings(
                stability        = 0.4,
                similarity_boost = 0.8,
                style            = 0.2,
                use_speaker_boost= True,
            )
        )

        save(audio, output_path)
        size_kb = Path(output_path).stat().st_size // 1024
        print(f"   Voice saved → {output_path} ({size_kb} KB)")
        return True

    except Exception as e:
        print(f"  ✗ Voice generation failed: {e}")
        return False


async def test():
    mock_briefing = {
        "date":         "Monday, 23 March 2026",
        "hook":         "Your Razorpay interview is tomorrow — everything else is secondary.",
        "situation":    "Interview confirmed for 10am. ML assignment due tonight. Heavy rain in Shimla — high commute risk. Balance low at 850 rupees.",
        "actions":      "Prepare for Razorpay interview\nSubmit ML assignment before midnight\nCarry umbrella\nTop up account balance",
        "financial":    "UPI debit of 2000 rupees. Balance 850 rupees.",
        "close":        "One focused day. That is all it takes.",
        "signal_count": 4,
    }

    print("\nGenerating SAGE voice briefing...\n")
    generate_voice(mock_briefing)
    print("\nOpen data/briefing.mp3 to listen.\n")

if __name__ == "__main__":
    asyncio.run(test())
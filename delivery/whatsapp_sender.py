import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from twilio.rest import Client
from config import get_settings

settings = get_settings()


def format_for_whatsapp(briefing_text: str) -> str:
    """
    LEARN: WhatsApp supports a small subset of markdown:
      *text*   = bold
      _text_   = italic
      ```text``` = monospace
    We reformat the plain briefing into something that looks
    clean on a phone screen instead of a wall of text.
    """
    lines  = briefing_text.strip().splitlines()
    output = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            output.append("")
            continue

        # Section headers → bold
        if stripped in ("SITUATION", "ACTION ITEMS", "FINANCIAL PULSE"):
            output.append(f"*{stripped}*")

        # Action items (lines starting with a verb / dash / number)
        elif stripped.startswith(("- ", "• ", "* ")):
            output.append(f"  • {stripped.lstrip('-•* ').strip()}")

        # SAGE header line
        elif stripped.startswith("SAGE DAILY BRIEFING"):
            output.append(f"*{stripped}*")

        # Divider lines — skip, WhatsApp doesn't render them well
        elif set(stripped) <= set("─━-="):
            output.append("")

        else:
            output.append(stripped)

    return "\n".join(output).strip()


def send_whatsapp(briefing_text: str) -> bool:
    print("\n● Delivering briefing to WhatsApp...")
    try:
        client     = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        formatted  = format_for_whatsapp(briefing_text)

        # WhatsApp has a 1600 char limit per message — split if needed
        chunks = [formatted[i:i+1500] for i in range(0, len(formatted), 1500)]

        for i, chunk in enumerate(chunks):
            message = client.messages.create(
                from_ = f"whatsapp:{settings.twilio_whatsapp_from.replace('whatsapp:', '')}",
                to    = f"whatsapp:{settings.your_whatsapp_number.replace('whatsapp:', '')}",
                body  = chunk,
            )
            print(f"   ✓ Part {i+1}/{len(chunks)} sent (ID: {message.sid})")

        return True

    except Exception as e:
        print(f"   ✗ WhatsApp delivery failed: {e}")
        return False

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import aiosqlite
from datetime import datetime, timezone, timedelta
from config import get_settings

settings = get_settings()


async def get_yesterday_context() -> dict:
    """
    LEARN: This is episodic memory — we retrieve what happened
    yesterday so today's briefing can reference it.

    We pull:
    - What SAGE said yesterday (the actions it gave)
    - Which of those actions the user marked as done (feedback)
    - Whether the briefing was delivered successfully

    This context gets injected into the narrator prompt so SAGE
    can say "you didn't act on X yesterday" or "good job on Y".
    """
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

    context = {
        "had_yesterday": False,
        "yesterday_actions": [],
        "acted_on": [],
        "ignored": [],
        "streak_days": 0,
    }

    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Get yesterday's briefing
        async with db.execute(
            "SELECT narrative FROM briefings WHERE date = ?", (yesterday,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return context

        context["had_yesterday"] = True
        narrative = json.loads(row["narrative"])

        # Extract action items from yesterday
        actions_text = narrative.get("actions", "")
        context["yesterday_actions"] = [
            line.strip().lstrip("-•*→").strip()
            for line in actions_text.splitlines()
            if line.strip() and len(line.strip()) > 10
        ]

        # Check which signals were acted on vs ignored via feedback table
        async with db.execute(
            """
            SELECT signal_id, acted_on, ignored
            FROM signal_feedback
            WHERE date = ?
            """,
            (yesterday,)
        ) as cursor:
            feedback_rows = await cursor.fetchall()

        for fb in feedback_rows:
            if fb["acted_on"]:
                context["acted_on"].append(fb["signal_id"])
            else:
                context["ignored"].append(fb["signal_id"])

        # Calculate how many consecutive days briefings have been delivered
        # LEARN: This is a "streak" calculation — same logic as Duolingo streaks
        async with db.execute(
            "SELECT date FROM briefings ORDER BY date DESC LIMIT 30"
        ) as cursor:
            dates = [r["date"] async for r in cursor]

        streak = 0
        check  = datetime.now(timezone.utc).date()
        for d in dates:
            if d == (check - timedelta(days=1)).isoformat() or d == check.isoformat():
                streak += 1
                check = datetime.fromisoformat(d).date()
            else:
                break
        context["streak_days"] = streak

    return context


def format_memory_context(ctx: dict) -> str:
    """
    Converts the memory dict into a natural language string
    that gets injected into the narrator's system prompt.
    """
    if not ctx["had_yesterday"]:
        return "This is the first briefing — no prior context available."

    lines = [f"SAGE has been running for {ctx['streak_days']} consecutive day(s)."]

    if ctx["yesterday_actions"]:
        lines.append(f"Yesterday's action items were:")
        for a in ctx["yesterday_actions"][:4]:  # top 4 only
            lines.append(f"  - {a}")

    if ctx["acted_on"]:
        lines.append(f"User acted on {len(ctx['acted_on'])} signal(s) yesterday — acknowledge this positively.")

    if ctx["ignored"]:
        lines.append(f"User ignored {len(ctx['ignored'])} signal(s) yesterday — if relevant, mention they are still pending.")

    if not ctx["acted_on"] and not ctx["ignored"]:
        lines.append("No feedback was recorded yesterday.")

    return "\n".join(lines)


# ── Test ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio

    async def test():
        ctx = await get_yesterday_context()
        print("\n── Memory Context ──\n")
        print(format_memory_context(ctx))
        print(f"\nRaw: {json.dumps(ctx, indent=2)}")

    asyncio.run(test())

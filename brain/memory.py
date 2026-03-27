import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import aiosqlite
from datetime import datetime, timezone, timedelta, date
from config import get_settings

settings = get_settings()


async def get_study_streak() -> dict:
    """
    LEARN: Streak algorithm — same logic as Duolingo.
    We look at each past day and check if at least one task
    was completed. We count backwards until we find a day
    with no completions — that's where the streak breaks.

    Returns streak count + whether today has activity yet.
    """
    today = datetime.now(timezone.utc).date()
    streak = 0
    today_done = 0

    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row

        # Check today's completions
        async with db.execute(
            """SELECT COUNT(*) as cnt FROM tasks
               WHERE done = 1 AND date(created_at) = ?""",
            (today.isoformat(),)
        ) as cur:
            row = await cur.fetchone()
            today_done = row["cnt"] if row else 0

        # Count consecutive days with completions going backwards
        check_date = today - timedelta(days=1)
        for _ in range(30):  # max 30 day lookback
            async with db.execute(
                """SELECT COUNT(*) as cnt FROM tasks
                   WHERE done = 1 AND date(created_at) = ?""",
                (check_date.isoformat(),)
            ) as cur:
                row = await cur.fetchone()
                if row and row["cnt"] > 0:
                    streak += 1
                    check_date -= timedelta(days=1)
                else:
                    break

    return {
        "streak_days": streak,
        "today_done":  today_done,
        "is_active":   today_done > 0,
    }


async def get_yesterday_context() -> dict:
    """
    LEARN: This is episodic memory — we retrieve what happened
    yesterday so today's briefing can reference it.
    """
    yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()

    context = {
        "had_yesterday":     False,
        "yesterday_actions": [],
        "acted_on":          [],
        "ignored":           [],
        "streak_days":       0,
        "today_done":        0,
    }

    # Get streak data
    streak_data = await get_study_streak()
    context["streak_days"] = streak_data["streak_days"]
    context["today_done"]  = streak_data["today_done"]

    async with aiosqlite.connect(settings.db_path) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT narrative FROM briefings WHERE date = ?", (yesterday,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return context

        context["had_yesterday"] = True
        narrative = json.loads(row["narrative"])

        context["yesterday_actions"] = [
            line.strip().lstrip("-•*→").strip()
            for line in narrative.get("actions", "").splitlines()
            if line.strip() and len(line.strip()) > 10
        ]

        async with db.execute(
            "SELECT signal_id, acted_on FROM signal_feedback WHERE date = ?",
            (yesterday,)
        ) as cursor:
            for fb in await cursor.fetchall():
                if fb["acted_on"]:
                    context["acted_on"].append(fb["signal_id"])
                else:
                    context["ignored"].append(fb["signal_id"])

    return context


def format_memory_context(ctx: dict) -> str:
    """
    Converts memory dict into natural language for the narrator prompt.
    """
    lines = []

    # Streak info — this is what makes SAGE feel alive
    streak = ctx["streak_days"]
    if streak >= 7:
        lines.append(f"Parisha has been completing tasks for {streak} days straight — acknowledge this streak positively.")
    elif streak >= 3:
        lines.append(f"Parisha has a {streak}-day task completion streak — mention it briefly.")
    elif streak == 0 and not ctx["today_done"]:
        lines.append("Parisha hasn't completed any tasks recently — gently call this out without being harsh.")

    if not ctx["had_yesterday"]:
        lines.append("This is the first briefing — no prior context.")
        return "\n".join(lines) if lines else "No prior context."

    if ctx["yesterday_actions"]:
        lines.append("Yesterday's action items were:")
        for a in ctx["yesterday_actions"][:3]:
            lines.append(f"  - {a}")

    if ctx["acted_on"]:
        lines.append(f"User acted on {len(ctx['acted_on'])} signal(s) — acknowledge positively.")
    if ctx["ignored"] and not ctx["acted_on"]:
        lines.append("User didn't act on any signals yesterday — note this if relevant.")

    return "\n".join(lines) if lines else "No notable patterns from yesterday."


if __name__ == "__main__":
    import asyncio

    async def test():
        streak = await get_study_streak()
        print(f"\nStreak: {streak}")
        ctx = await get_yesterday_context()
        print(f"\nMemory context:\n{format_memory_context(ctx)}")

    asyncio.run(test())

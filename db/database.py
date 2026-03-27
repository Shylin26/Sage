import aiosqlite
import asyncio
from pathlib import Path
from config import get_settings

settings = get_settings()

MIGRATIONS = [
    "ALTER TABLE briefings ADD COLUMN audio_b64 TEXT DEFAULT ''",
    "ALTER TABLE tasks ADD COLUMN created_at TEXT DEFAULT (datetime('now'))",
]

async def init_db():
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    schema = Path("db/schema.sql").read_text()

    async with aiosqlite.connect(settings.db_path) as db:
        # Create all tables
        await db.executescript(schema)

        # Run migrations one by one — safe to re-run, errors mean already applied
        for migration in MIGRATIONS:
            try:
                await db.execute(migration)
                await db.commit()
            except Exception:
                pass  # column already exists

        # Verify audio_b64 exists
        async with db.execute("PRAGMA table_info(briefings)") as cur:
            cols = [row[1] async for row in cur]
        if "audio_b64" not in cols:
            await db.execute("ALTER TABLE briefings ADD COLUMN audio_b64 TEXT DEFAULT ''")
            await db.commit()

    print("✓ Database ready")

if __name__ == "__main__":
    asyncio.run(init_db())

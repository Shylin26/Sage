import aiosqlite
import asyncio
from pathlib import Path
from config import get_settings

settings = get_settings()

async def init_db():
    Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    schema = Path("db/schema.sql").read_text()
    async with aiosqlite.connect(settings.db_path) as db:
        await db.executescript(schema)

        # Migrations — ALTER TABLE is safe to run every time,
        # the except just catches "column already exists" errors
        migrations = [
            "ALTER TABLE briefings ADD COLUMN audio_b64 TEXT DEFAULT ''",
        ]
        for migration in migrations:
            try:
                await db.execute(migration)
                await db.commit()
            except Exception:
                pass  # already applied

    print("✓ Database ready")

if __name__ == "__main__":
    asyncio.run(init_db())

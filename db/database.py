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
        # Add audio_b64 column if it doesn't exist (migration for existing DBs)
        try:
            await db.execute("ALTER TABLE briefings ADD COLUMN audio_b64 TEXT DEFAULT ''")
            await db.commit()
            print("✓ Migrated: added audio_b64 column")
        except Exception:
            pass  # Column already exists, that's fine
        await db.commit()
    print("✓ Database ready")

if __name__ == "__main__":
    asyncio.run(init_db())
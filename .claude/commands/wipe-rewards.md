Reset all season achievement `claimed_at` timestamps to NULL so every reward can be re-claimed.

Run this in the Docker container:

```python
import asyncio
async def run():
    from backend.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as s:
        result = await s.execute(text(
            'UPDATE season_achievements SET claimed_at = NULL WHERE claimed_at IS NOT NULL'
        ))
        await s.commit()
        print(f'Reset {result.rowcount} achievement(s)')
asyncio.run(run())
```

Execute with:
```bash
docker exec enigma-engine-enigma-engine-1 python3 -c "
import asyncio
async def run():
    from backend.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as s:
        result = await s.execute(text('UPDATE season_achievements SET claimed_at = NULL WHERE claimed_at IS NOT NULL'))
        await s.commit()
        print(f'Reset {result.rowcount} achievement(s)')
asyncio.run(run())
"
```

Then confirm the state:
```bash
docker exec enigma-engine-enigma-engine-1 python3 -c "
import asyncio
async def run():
    from backend.database import AsyncSessionLocal
    from sqlalchemy import text
    async with AsyncSessionLocal() as s:
        rows = await s.execute(text('SELECT sa.id, sm.name, sa.claimed_at FROM season_achievements sa JOIN season_milestones sm ON sm.id = sa.milestone_id ORDER BY sa.id'))
        for r in rows.fetchall():
            status = 'CLAIMED' if r.claimed_at else 'unclaimed'
            print(f'  [{status}] {r.name} (achievement id={r.id})')
asyncio.run(run())
"
```

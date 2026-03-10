Wipe tab 5 (index 4) of the latest manual/game_close snapshot stash file.
Use this before re-claiming rewards to avoid stale items accumulating in the portal tab.

```bash
docker exec enigma-engine-enigma-engine-1 python3 -c "
import glob, os
from pathlib import Path
from backend.services.item_parsing.stash_format import parse_stash, serialize_stash
from backend.services.item_parsing.models import ParsedPage

# Find latest manual snapshot (falls back to game_close)
snaps = sorted(
    glob.glob('/app/data/backups/pc/*_manual') +
    glob.glob('/app/data/backups/pc/*_game_close'),
    key=os.path.getmtime, reverse=True
)
if not snaps:
    print('ERROR: No manual/game_close snapshot found. Check In from your PC first.')
    exit(1)

stash_path = Path(snaps[0]) / 'ModernSharedStashSoftCoreV2.d2i'
print('Snapshot:', snaps[0])
stash = parse_stash(stash_path, hardcore=False)

tab5 = stash.pages[4]
print(f'Tab 5 before: jm_item_count={tab5.jm_item_count}, raw_bytes={len(tab5.raw_bytes)}')

stash.pages[4] = ParsedPage(items=[], gold=0, raw_bytes=bytearray(), jm_item_count=0)
stash_path.write_bytes(serialize_stash(stash))

stash2 = parse_stash(stash_path, hardcore=False)
print(f'Tab 5 after:  jm_item_count={stash2.pages[4].jm_item_count}, raw_bytes={len(stash2.pages[4].raw_bytes)}')
print('Done — tab 5 cleared.')
"
```

After running, Sync to Device will push the cleared stash to your PC.

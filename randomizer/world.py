"""World options: open lockouts by changing what a new save starts with.

Each option in settings.WORLD lists GameData flags and the value a new game should start
with. They are the same flags the game flips itself when the lockout ends (for example the
Kokiri boy at the forest exit sets KokiriForest_Npc_Kokiri_007_Child_Blocker_00 to false), so
the world simply starts in that state. The values are written into the 4-byte DefaultValue
slots of GameDataList in place (tools/gamedata.py); nothing else in the file changes, so its
size and resource size table entry stay the same.

Only affects new saves: an existing save keeps the flags it already has.
"""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import zstandard
import zs, gamedata
from randomizer import settings as cfg


def needed_files():
    return [gamedata.PATH]


def flag_values(settings):
    out = {}
    for k in cfg.WORLD_OPEN:
        if settings.get(k):
            out.update(cfg.WORLD[k]['flags'])
    return out


def write(rom, out_dir, settings):
    """Write the patched GameDataList under out_dir/romfs if any option is on; returns paths."""
    values = flag_values(settings)
    if not values:
        return []
    path = os.path.join(rom, gamedata.PATH)
    data = gamedata.set_bool_defaults(zs.decompress(rom, path), values)
    d = zs.pick_dict(rom, path)
    blob = zstandard.ZstdCompressor(level=19, dict_data=d, write_checksum=False).compress(data)
    assert zstandard.ZstdDecompressor(dict_data=d).decompress(blob) == data
    dst = os.path.join(out_dir, 'romfs', gamedata.PATH)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    open(dst, 'wb').write(blob)
    return [gamedata.PATH]

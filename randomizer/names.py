"""Human-readable names for locations and items (for the spoiler log)."""
import json, os, re, collections

DATA = os.path.join(os.path.dirname(__file__), '..', 'data')

# English for the developer room labels that describe the room (the rest are just "RoomNN").
ROOM_EN = {
    'Room01：水路と隠し部屋': 'waterways and hidden rooms',
    'Room02：デドハンド部屋の前室（ヒントなし）': 'Dead Hand antechamber',
    'Room06：ビーモスと落とし穴の小部屋': 'Beamos and pitfall room',
    'Room08：デドハンド部屋': 'Dead Hand room',
    'Room09：下層の洞窟': 'lower cave',
    'Room11：デドハンド部屋前室': 'room before Dead Hand',
    'Room03：リーデッド小部屋（ダンジョンマップ）【敵全滅】': 'ReDead room (map)',
    'Room04：デドハンド部屋（ホバーブーツ）【敵全滅】': 'Dead Hand room (Hover Boots)',
    'Room06：回転鎌の部屋（銀ルピー）': 'spinning scythe room (silver rupees)',
    'Room07：リーデッド小部屋（コンパス）【敵全滅】': 'ReDead room (compass)',
    'Room11：トゲ天井トラップの部屋': 'spiked ceiling trap room',
    'Room15：リーデッド小部屋（ヒントのみ）【ヒントなし】': 'small ReDead room',
    'Room16：リーデッド＆トラップの部屋（小さなカギ）': 'ReDead and trap room (small key)',
    'Room19：トゲ壁プレス部屋（ボスのカギ）': 'spiked wall press room (boss key)',
    'Room21：見えないフロアマスターの小部屋（小さなカギ）': 'invisible Floormaster room (small key)',
    'room31：見えない回転鎌の部屋の奥の個室【ヒントなし】': 'room past the invisible scythe',
}


def item_names():
    return json.load(open(os.path.join(DATA, 'item_names.json'), encoding='utf-8'))


def room_text(loc):
    label = loc.get('room_label')
    if loc.get('room') is None: return None
    if label in ROOM_EN:
        num = re.match(r'[Rr]oom(\d+)', label).group(1)
        return 'Room %s, %s' % (num, ROOM_EN[label])
    m = re.match(r'(?:Room|部屋)\s*(\w+)', label or '')
    num = m.group(1) if m else str(loc['room'])
    return 'Room %s' % (num.zfill(2) if num.isdigit() else num)


POT_NOUNS = (('Obj_Pot', 'pot'), ('Enemy_FlyingPot', 'flying pot'), ('Obj_BrokenBox', 'crate'),
             ('Obj_Plant_Grass', 'grass'), ('Obj_LiftRock', 'rock'), ('Obj_Kokiri_Beehive', 'beehive'),
             ('Obj_Tree', 'tree'), ('Obj_Gerudo_CowBoneDecoration', 'skull decoration'))


def noun(l):
    if l['kind'] == 'pot':
        return next((n for prefix, n in POT_NOUNS if l['actor'].startswith(prefix)), 'object')
    return {'chest': 'chest', 'scrub': 'Business Scrub'}.get(l['kind'], '')


def location_names(locs):
    """Stable, unique names like 'Forest Temple, Room 17: Fairy Bow chest'."""
    items = item_names()
    base = {}
    for l in locs:
        where = l['area_name']
        room = room_text(l)
        if room: where += ', ' + room
        age = sorted(set(l['ages']) - {'any'})
        if len(age) == 1: where += ' (%s)' % age[0]
        what = '%s %s' % (items.get(l['vanilla'], l['vanilla']), noun(l))
        if l['kind'] == 'skulltula': what = 'Gold Skulltula'
        if l['kind'] == 'freestanding': what = items.get(l['vanilla'], l['vanilla'])
        base[l['id']] = '%s: %s' % (where, what.strip())
    counts = collections.Counter(base.values())
    seen = collections.Counter()
    out = {}
    for l in locs:
        n = base[l['id']]
        if counts[n] > 1:
            seen[n] += 1; n = '%s #%d' % (n, seen[n])
        out[l['id']] = n
    return out

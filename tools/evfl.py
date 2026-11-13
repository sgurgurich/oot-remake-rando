"""Minimal BFEVFL (event flow) reader with in-place link edits.

Layout follows the Breath of the Wild format (leoetlino's evfl docs); this game's files
are version 0x0400 with the same header. All pointers are absolute u64 file offsets.

  Flowchart 'EVFL': u32 string_pool, u32 0, u32 0, u16 actors, u16 actions, u16 queries,
                    u16 events, u16 entry_points, 3 x u16, ptr name, ptr actors, ptr events,
                    ptr entry_point_dict, ptr entry_points
  Event (0x30):     ptr name, u8 type, u8 pad, then by type
    0 action   u16 next, u16 actor, u16 action, ptr params
    1 switch   u16 n_cases, u16 actor, u16 query, ptr params, ptr cases (8 each: u32 value, u16 event, u16 pad)
    2 fork     u16 n_forks, u16 join, u16 pad, ptr forks (u16 each)
    3 join     u16 next
    4 subflow  u16 next, u16 pad, u16 pad, ptr params, ptr flowchart name, ptr entry point name
  Strings: u16 length, bytes, NUL.

Editing is limited to rewriting u16 event indices, which never moves data, so the
relocation table and every offset stay valid.
"""
import struct

TYPES = {0: 'action', 1: 'switch', 2: 'fork', 3: 'join', 4: 'subflow'}
NONE = 0xFFFF
EVENT_SIZE = 0x30  # 0x28 in Breath of the Wild; this version adds 8 bytes at the end
ACTOR_SIZE = 0x38
CASE_SIZE = 8
ENTRY_SIZE = 0x20  # ptr subflow indices, ptr var defs, ptr var dict, u16 n_sub, u16 n_vars, u16 main event, pad


class Flow:
    def __init__(self, data):
        self.d = bytearray(data)
        assert self.d[:6] == b'BFEVFL', self.d[:8]
        n_flowcharts, = struct.unpack_from('<H', self.d, 0x20)
        assert n_flowcharts == 1, n_flowcharts
        fc, = struct.unpack_from('<Q', self.d, 0x28)
        fc_ptr, = struct.unpack_from('<Q', self.d, fc)
        self.fc = fc_ptr
        assert self.d[fc_ptr:fc_ptr + 4] == b'EVFL'
        (self.n_actors, self.n_actions, self.n_queries, self.n_events,
         self.n_entries) = struct.unpack_from('<5H', self.d, fc_ptr + 0x10)
        (name, self.p_actors, self.p_events, self.p_entry_dict,
         self.p_entries) = struct.unpack_from('<5Q', self.d, fc_ptr + 0x20)
        self.name = self.s(name)
        self.actors = [self._actor(i) for i in range(self.n_actors)]
        self.events = [self._event(i) for i in range(self.n_events)]
        names = self.dict_names(self.p_entry_dict)
        self.entries = {}
        for k in range(self.n_entries):
            o = self.p_entries + ENTRY_SIZE * k
            self.entries[names[k] if k < len(names) else k] = {'off': o, 'main': struct.unpack_from('<H', self.d, o + 0x1c)[0]}
        for e in self.events:
            p = struct.unpack_from('<Q', self.d, e['off'] + 0x10)[0] if e['type'] in ('action', 'switch', 'subflow') else 0
            e['params'] = self.container(p) if p else None
            if 'actor' in e and e['actor'] < len(self.actors):
                a = self.actors[e['actor']]
                e['actor_name'] = a['name']
                if 'action' in e: e['action_name'] = a['actions'][e['action']]
                if 'query' in e: e['query_name'] = a['queries'][e['query']]

    def _actor(self, i):
        """Actor (0x38): ptr name, ptr secondary name, ptr argument, ptr actions, ptr queries,
        ptr params, u16 n_actions, u16 n_queries, u16 entry point, ..."""
        o = self.p_actors + ACTOR_SIZE * i
        name, sec, arg, acts, qs, params = struct.unpack_from('<6Q', self.d, o)
        na, nq = struct.unpack_from('<2H', self.d, o + 0x30)
        return {'name': self.s(name), 'secondary': self.s(sec),
                'actions': [self.s(struct.unpack_from('<Q', self.d, acts + 8 * k)[0]) for k in range(na)],
                'queries': [self.s(struct.unpack_from('<Q', self.d, qs + 8 * k)[0]) for k in range(nq)]}

    def dict_names(self, p):
        """'DIC ' radix tree: u32 magic, u32 count, root entry, then count entries
        (u32 bit, u16 left, u16 right, ptr name); returns the names in order."""
        if not p or self.d[p:p + 4] != b'DIC ':
            return []
        n, = struct.unpack_from('<I', self.d, p + 4)
        return [self.s(struct.unpack_from('<Q', self.d, p + 8 + 0x10 * (k + 1) + 8)[0]) for k in range(n)]

    def container(self, p):
        """Parameter container: u8 type, u8 pad, u16 count, u32 pad, ptr dict, then items.
        1 = dictionary of containers, 2 int, 3 bool, 4 float, 5 string, 0 argument."""
        typ, n = struct.unpack_from('<BxH', self.d, p)
        dic, = struct.unpack_from('<Q', self.d, p + 8)
        items = p + 0x10
        if typ == 1:
            names = self.dict_names(dic)
            return {names[k] if k < len(names) else k:
                    self.container(struct.unpack_from('<Q', self.d, items + 8 * k)[0]) for k in range(n)}
        if typ in (0, 5):
            v = [self.s(struct.unpack_from('<Q', self.d, items + 8 * k)[0]) for k in range(n)]
        elif typ == 2:
            v = list(struct.unpack_from('<%di' % n, self.d, items))
        elif typ == 3:
            v = [bool(x) for x in struct.unpack_from('<%dI' % n, self.d, items)]
        elif typ == 4:
            v = list(struct.unpack_from('<%df' % n, self.d, items))
        else:
            return '<type %d x%d>' % (typ, n)
        return v[0] if n == 1 else v

    def s(self, ptr):
        n, = struct.unpack_from('<H', self.d, ptr)
        return self.d[ptr + 2:ptr + 2 + n].decode('utf-8')

    def _event(self, i):
        o = self.p_events + EVENT_SIZE * i
        name_p, typ = struct.unpack_from('<QB', self.d, o)
        e = {'i': i, 'off': o, 'name': self.s(name_p), 'type': TYPES.get(typ, typ)}
        a, b, c = struct.unpack_from('<3H', self.d, o + 0x0A)
        if typ in (0, 3, 4):
            e['next'] = a
        if typ == 0:
            e['actor'], e['action'] = b, c
        if typ == 1:
            cases_p, = struct.unpack_from('<Q', self.d, o + 0x18)
            e['cases'] = [struct.unpack_from('<IH', self.d, cases_p + CASE_SIZE * k) for k in range(a)]
            e['cases_p'] = cases_p
            e['actor'], e['query'] = b, c
        if typ == 2:
            forks_p, = struct.unpack_from('<Q', self.d, o + 0x10)
            e['forks'] = list(struct.unpack_from('<%dH' % a, self.d, forks_p))
            e['join'] = b
        if typ == 4:
            fname, entry = struct.unpack_from('<QQ', self.d, o + 0x18)
            e['flowchart'] = self.s(fname) if fname else ''
            e['entry'] = self.s(entry) if entry else ''
        return e

    def set_next(self, i, target):
        e = self.events[i]
        assert e['type'] in ('action', 'join', 'subflow'), e
        struct.pack_into('<H', self.d, e['off'] + 0x0A, target)
        e['next'] = target

    def set_case(self, i, k, target):
        e = self.events[i]
        value, _ = e['cases'][k]
        struct.pack_into('<H', self.d, e['cases_p'] + CASE_SIZE * k + 4, target)
        e['cases'][k] = (value, target)

    def set_entry(self, name, target):
        struct.pack_into('<H', self.d, self.entries[name]['off'] + 0x1c, target)
        self.entries[name]['main'] = target

    def predecessors(self, j):
        """(event index, how) pairs that lead to event j."""
        out = []
        for e in self.events:
            if e.get('next') == j: out.append((e['i'], 'next'))
            for k, (_, t) in enumerate(e.get('cases', [])):
                if t == j: out.append((e['i'], 'case%d' % k))
            if j in e.get('forks', []): out.append((e['i'], 'fork'))
        for name, ent in self.entries.items():
            if ent['main'] == j: out.append((name, 'entry'))
        return out

    def dump(self, out=print):
        for e in self.events:
            extra = {k: v for k, v in e.items() if k not in ('i', 'off', 'name', 'type', 'cases_p', 'actor', 'action', 'query')}
            out('%3d %-10s %-8s %s' % (e['i'], e['name'], e['type'], extra))

    def bytes(self):
        return bytes(self.d)

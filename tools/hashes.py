"""murmur3_32 (seed 0): how this engine hashes GameData flag names ("IsGet.Item_Hookshot")."""


def murmur3(data, seed=0):
    if isinstance(data, str):
        data = data.encode('utf-8')
    c1, c2 = 0xcc9e2d51, 0x1b873593
    h = seed
    n = len(data)
    r = n & 3
    for i in range(0, n - r, 4):
        k = int.from_bytes(data[i:i + 4], 'little')
        k = (k * c1) & 0xffffffff
        k = ((k << 15) | (k >> 17)) & 0xffffffff
        k = (k * c2) & 0xffffffff
        h ^= k
        h = ((h << 13) | (h >> 19)) & 0xffffffff
        h = (h * 5 + 0xe6546b64) & 0xffffffff
    if r:
        k = int.from_bytes(data[n - r:], 'little')
        k = (k * c1) & 0xffffffff
        k = ((k << 15) | (k >> 17)) & 0xffffffff
        k = (k * c2) & 0xffffffff
        h ^= k
    h ^= n
    h ^= h >> 16
    h = (h * 0x85ebca6b) & 0xffffffff
    h ^= h >> 13
    h = (h * 0xc2b2ae35) & 0xffffffff
    h ^= h >> 16
    return h

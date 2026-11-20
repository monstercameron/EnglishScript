from pathlib import Path
import re
import sys

reference = Path(sys.argv[1])
out = Path(__file__).resolve().parents[1] / 'docs' / 'red' / 'scenery.english'
maps = [
    ('Bedroom', 'RedsHouse2F', 'reds_house'), ('Home', 'RedsHouse1F', 'reds_house'),
    ('Pallet Town', 'PalletTown', 'overworld'), ("Oak's Lab", 'OaksLab', 'gym'),
    ('Route 1', 'Route1', 'overworld'), ('Viridian City', 'ViridianCity', 'overworld'),
    ('Viridian Mart', 'ViridianMart', 'pokecenter'), ('Route 2', 'Route2', 'overworld'),
    ('Forest South Gate', 'ViridianForestSouthGate', 'gate'),
    ('Viridian Forest', 'ViridianForest', 'forest'),
    ('Forest North Gate', 'ViridianForestNorthGate', 'gate'),
    ('Pewter City', 'PewterCity', 'overworld'), ('Pewter Gym', 'PewterGym', 'gym'),
    ('Route 22', 'Route22', 'overworld'), ('Route 22 Gate', 'Route22Gate', 'gate'),
    ('Viridian Center', 'ViridianPokecenter', 'pokecenter'), ('Pewter Center', 'PewterPokecenter', 'pokecenter'), ('Pewter Mart', 'PewterMart', 'pokecenter'),
    ("Blue's House", 'BluesHouse', 'house'), ('Viridian School', 'ViridianSchoolHouse', 'house'),
    ('Viridian House', 'ViridianNicknameHouse', 'house'), ('Pewter House', 'PewterSpeechHouse', 'house'),
    ('Nidoran House', 'PewterNidoranHouse', 'house'),
]
constants = (reference / 'constants/map_constants.asm').read_text()

def classify(tileset, t):
    ids = set(t)
    if tileset == 'overworld':
        if ids & {0x2a,0x2b,0x3a,0x3b,0x40,0x41,0x50,0x51}: return 'T'
        if 0x52 in ids: return 'G'
        if ids & {0x0b,0x0c,0x1b,0x1c}: return 'D'
        if ids & {0x46,0x47,0x56,0x57,0x42,0x43,0x44,0x45}: return 'S'
        if ids & {0x05,0x06,0x07,0x08,0x09,0x15,0x16,0x18,0x19}: return 'R'
        if ids & {0x0a,0x1a,0x0f,0x1f,0x4e,0x4f}: return 'W'
        if ids & {0x53,0x12}: return 'F'
        if ids & {0x32,0x34,0x35,0x36,0x37,0x54}: return 'L'
        if ids == {0x14}: return 'A'
        return '.'
    if tileset == 'forest':
        if ids & {0x02,0x03,0x12,0x13,0x04,0x05,0x06,0x07,0x15,0x16,0x17,0x23,0x24,0x25,0x26,0x27,0x35,0x36}: return 'T'
        if 0x20 in ids: return 'G'
        if ids & {0x21,0x22,0x31,0x32}: return 'L'
        return '.'
    if tileset == 'reds_house':
        exact = {
            (0x40,0x41,0x20,0x21): 'C', (0x42,0x43,0x32,0x33): 'C',
            (0x00,0x00,0x26,0x27): 'K', (0x00,0x00,0x27,0x29): 'K',
            (0x2c,0x2a,0x3c,0x3a): 'K', (0x2a,0x2b,0x3a,0x3b): 'K',
            (0x24,0x25,0x34,0x35): 'V', (0x0a,0x0b,0x1a,0x1b): 'E',
            (0x06,0x07,0x16,0x17): 'N', (0x0e,0x0f,0x1e,0x1f): 'X',
            (0x2d,0x2e,0x3d,0x3e): 'Q', (0x3d,0x3e,0x3f,0x2f): 'Y',
            (0x44,0x45,0x08,0x09): 'P', (0x46,0x47,0x18,0x19): 'Z',
            (0x00,0x00,0x00,0x00): 'H',
        }
        if t in exact: return exact[t]
        if ids <= {0x00,0x01}: return '.'
        return 'I' 
    if tileset == 'gym':
        if ids == {0x11}: return '.'
        if t == (0x07,0x08,0x17,0x18): return 'B'
        return 'I'
    if tileset == 'house':
        if ids <= {0x00,0x01}: return '.'
        return 'I'
    if tileset == 'pokecenter':
        if t == (0x01,0x0b,0x11,0x1b): return '.'
        return 'I'
    if tileset == 'gate':
        if t == (0x11,0x01,0x01,0x11): return '.'
        return 'I'
    return '.'

lines = ['This chapter shares only scenery.', '', 'Use the foundation and maps chapters.', '', 'To work out the scenery tiles (text):']
for name, map_name, tileset in maps:
    header = (reference / f'data/maps/headers/{map_name}.asm').read_text()
    key = re.search(r'map_header\s+\w+,\s*(\w+),', header).group(1)
    width, height = map(int, re.search(r'map_const\s+' + key + r',\s*(\d+),\s*(\d+)', constants).groups())
    blocks = (reference / f'maps/{map_name}.blk').read_bytes()
    blockset = (reference / f'gfx/blocksets/{tileset}.bst').read_bytes()
    result = []
    for y in range(height * 2):
        for x in range(width * 2):
            block = blocks[(y // 2) * width + x // 2]
            offset = block * 16 + (y % 2) * 8 + (x % 2) * 2
            quartet = tuple(blockset[offset + i] for i in (0, 1, 4, 5))
            result.append(classify(tileset, quartet))
    lines.extend([f'  If Journey\'s place is "{name}":', f'    The answer is "{"".join(result)}".'])
lines.extend(['  The answer is "".', '', 'To work out the scenery (text) at a column (number) by a row (number):', '  If the column is less than 0 or the row is less than 0:', '    The answer is ".".', '  If the column is at least the map width or the row is at least the map height:', '    The answer is ".".', '  Let the tiles be the scenery tiles.', '  Let the position be the row * the map width + the column.', '  The answer is the first 1 letters of the last (the length of the tiles - the position) letters of the tiles.', ''])
out.write_text('\n'.join(lines), encoding='utf-8')

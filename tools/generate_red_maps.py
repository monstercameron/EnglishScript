from pathlib import Path
import re
import sys

reference = Path(sys.argv[1])
output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "docs/red/maps.english"
map_specs = [
    ("Bedroom", "RedsHouse2F", "reds_house", "RedsHouse2"),
    ("Home", "RedsHouse1F", "reds_house", "RedsHouse1"),
    ("Pallet Town", "PalletTown", "overworld", "Overworld"),
    ("Oak's Lab", "OaksLab", "gym", "Dojo"),
    ("Route 1", "Route1", "overworld", "Overworld"),
    ("Viridian City", "ViridianCity", "overworld", "Overworld"),
    ("Viridian Mart", "ViridianMart", "pokecenter", "Mart"),
    ("Viridian Center", "ViridianPokecenter", "pokecenter", "Pokecenter"),
    ("Route 2", "Route2", "overworld", "Overworld"),
    ("Forest South Gate", "ViridianForestSouthGate", "gate", "ForestGate"),
    ("Viridian Forest", "ViridianForest", "forest", "Forest"),
    ("Forest North Gate", "ViridianForestNorthGate", "gate", "ForestGate"),
    ("Pewter City", "PewterCity", "overworld", "Overworld"),
    ("Pewter Gym", "PewterGym", "gym", "Gym"),
    ("Route 22", "Route22", "overworld", "Overworld"),
    ("Route 22 Gate", "Route22Gate", "gate", "Gate"),
    ("Pewter Center", "PewterPokecenter", "pokecenter", "Pokecenter"),
    ("Pewter Mart", "PewterMart", "pokecenter", "Mart"),
    ("Blue's House", "BluesHouse", "house", "House"),
    ("Viridian School", "ViridianSchoolHouse", "house", "House"),
    ("Viridian House", "ViridianNicknameHouse", "house", "House"),
    ("Pewter House", "PewterSpeechHouse", "house", "House"),
    ("Nidoran House", "PewterNidoranHouse", "house", "House"),
]
constants = (reference / "constants/map_constants.asm").read_text()
collision_source = (reference / "data/tilesets/collision_tile_ids.asm").read_text()
tileset_source = (reference / "data/tilesets/tileset_headers.asm").read_text()
counter_sets = {}
for line in tileset_source.splitlines():
    match = re.match(r"\s*tileset\s+(\w+),\s*([^,]+),\s*([^,]+),\s*([^,]+),", line)
    if match:
        counter_sets[match.group(1)] = {
            int(value.strip()[1:], 16)
            for value in match.groups()[1:]
            if value.strip().startswith("$")
        }
collision_sets = {}
labels = []
for line in collision_source.splitlines():
    match = re.match(r"([A-Za-z0-9]+)_Coll::", line)
    if match:
        labels.append(match.group(1))
    elif "coll_tiles" in line:
        tile_ids = {int(value, 16) for value in re.findall(r"\$([0-9a-fA-F]+)", line)}
        for label in labels:
            collision_sets[label] = tile_ids
        labels = []
warps = {
    ("Pallet Town", 5, 5): ("Home", 2, 6),
    ("Home", 2, 7): ("Pallet Town", 5, 6),
    ("Home", 3, 7): ("Pallet Town", 5, 6),
    ("Home", 7, 1): ("Bedroom", 7, 2),
    ("Bedroom", 7, 1): ("Home", 7, 2),
    ("Pallet Town", 12, 11): ("Oak's Lab", 4, 10),
    ("Oak's Lab", 4, 11): ("Pallet Town", 12, 12),
    ("Oak's Lab", 5, 11): ("Pallet Town", 12, 12),
    ("Viridian City", 29, 19): ("Viridian Mart", 3, 6),
    ("Viridian Mart", 3, 7): ("Viridian City", 29, 20),
    ("Viridian Mart", 4, 7): ("Viridian City", 29, 20),
    ("Route 2", 3, 43): ("Forest South Gate", 4, 6),
    ("Forest South Gate", 4, 7): ("Route 2", 3, 44),
    ("Forest South Gate", 5, 7): ("Route 2", 3, 44),
    ("Forest South Gate", 4, 0): ("Viridian Forest", 16, 46),
    ("Forest South Gate", 5, 0): ("Viridian Forest", 17, 46),
    ("Viridian Forest", 15, 47): ("Forest South Gate", 4, 1),
    ("Viridian Forest", 16, 47): ("Forest South Gate", 4, 1),
    ("Viridian Forest", 17, 47): ("Forest South Gate", 5, 1),
    ("Viridian Forest", 18, 47): ("Forest South Gate", 5, 1),
    ("Viridian Forest", 1, 0): ("Forest North Gate", 4, 6),
    ("Viridian Forest", 2, 0): ("Forest North Gate", 5, 6),
    ("Forest North Gate", 4, 7): ("Viridian Forest", 1, 1),
    ("Forest North Gate", 5, 7): ("Viridian Forest", 1, 1),
    ("Forest North Gate", 4, 0): ("Route 2", 3, 10),
    ("Forest North Gate", 5, 0): ("Route 2", 3, 10),
    ("Route 2", 3, 11): ("Forest North Gate", 4, 1),
    ("Pewter City", 16, 17): ("Pewter Gym", 4, 12),
    ("Pewter Gym", 4, 13): ("Pewter City", 16, 18),
    ("Pewter Gym", 5, 13): ("Pewter City", 16, 18),
}
warps.update(
    {
        ("Viridian City", 23, 25): ("Viridian Center", 3, 6),
        ("Viridian Center", 3, 7): ("Viridian City", 23, 26),
        ("Viridian Center", 4, 7): ("Viridian City", 23, 26),
    }
)
for outside, column, row, inside, destination_column, destination_row in [
    ("Pallet Town", 13, 5, "Blue's House", 2, 6),
    ("Viridian City", 21, 15, "Viridian School", 2, 6),
    ("Viridian City", 21, 9, "Viridian House", 2, 6),
    ("Pewter City", 7, 29, "Pewter House", 2, 6),
    ("Pewter City", 29, 13, "Nidoran House", 2, 6),
    ("Pewter City", 13, 25, "Pewter Center", 3, 6),
    ("Pewter City", 23, 17, "Pewter Mart", 3, 6),
    ("Route 22", 8, 5, "Route 22 Gate", 4, 6),
]:
    warps[outside, column, row] = (inside, destination_column, destination_row)
    if inside in ("Pewter Center", "Pewter Mart"):
        exit_columns = [3, 4]
    elif inside == "Route 22 Gate":
        exit_columns = [4, 5]
    else:
        exit_columns = [2, 3]
    for exit_column in exit_columns:
        warps[inside, exit_column, 7] = (outside, column, row + 1)
npcs = {
    ("Home", 5, 4): "Mom",
    ("Oak's Lab", 4, 3): "Rival",
    ("Oak's Lab", 5, 2): "Oak",
    ("Oak's Lab", 1, 9): "Girl",
    ("Oak's Lab", 2, 10): "Scientist",
    ("Oak's Lab", 8, 10): "Scientist",
    ("Oak's Lab", 6, 3): "Charmander",
    ("Oak's Lab", 7, 3): "Squirtle",
    ("Oak's Lab", 8, 3): "Bulbasaur",
    ("Viridian Mart", 0, 5): "Clerk",
    ("Viridian Center", 3, 1): "Nurse",
    ("Viridian Forest", 30, 33): "Bug Catcher 1",
    ("Viridian Forest", 30, 19): "Bug Catcher 2",
    ("Viridian Forest", 2, 18): "Bug Catcher 3",
    ("Pewter Gym", 4, 1): "Brock",
    ("Pewter Gym", 3, 6): "Gym Trainer",
    ("Pewter Gym", 7, 10): "Gym Guide",
}
npcs.update(
    {
        ("Pallet Town", 3, 8): "Girl",
        ("Pallet Town", 11, 14): "Fisher",
        ("Route 1", 5, 24): "Youngster",
        ("Route 1", 15, 13): "Youngster",
        ("Viridian City", 13, 20): "Youngster",
        ("Viridian City", 30, 8): "Man",
        ("Viridian City", 30, 25): "Youngster",
        ("Viridian City", 17, 9): "Girl",
        ("Viridian City", 18, 9): "Old Man",
        ("Viridian City", 6, 23): "Fisher",
        ("Viridian City", 17, 5): "Old Man",
        ("Viridian Mart", 5, 5): "Youngster",
        ("Viridian Mart", 3, 3): "Customer",
        ("Viridian Center", 10, 5): "Gentleman",
        ("Viridian Center", 4, 3): "Visitor",
        ("Viridian Center", 11, 2): "Receptionist",
        ("Forest South Gate", 8, 4): "Girl",
        ("Forest South Gate", 2, 4): "Girl",
        ("Viridian Forest", 16, 43): "Youngster",
        ("Viridian Forest", 27, 40): "Youngster",
        ("Forest North Gate", 3, 2): "Visitor",
        ("Forest North Gate", 2, 5): "Gramps",
        ("Pewter City", 8, 15): "Visitor",
        ("Pewter City", 17, 25): "Visitor",
        ("Pewter City", 27, 17): "Visitor",
        ("Pewter City", 26, 25): "Visitor",
        ("Pewter City", 35, 16): "Youngster",
    }
)
npcs.update(
    {
        ("Route 22", 25, 5): "Route 22 Rival",
        ("Route 22 Gate", 6, 2): "Guard",
        ("Pewter Center", 3, 1): "Nurse",
        ("Pewter Center", 11, 7): "Gentleman",
        ("Pewter Center", 1, 3): "Jigglypuff",
        ("Pewter Center", 11, 2): "Receptionist",
        ("Pewter Mart", 0, 5): "Clerk",
        ("Pewter Mart", 3, 3): "Youngster",
        ("Pewter Mart", 5, 5): "Visitor",
        ("Blue's House", 2, 3): "Daisy",
        ("Blue's House", 6, 4): "Daisy",
        ("Viridian School", 3, 5): "Girl",
        ("Viridian School", 4, 1): "Teacher",
        ("Viridian House", 5, 3): "Man",
        ("Viridian House", 1, 4): "Girl",
        ("Viridian House", 5, 5): "Speary",
        ("Pewter House", 2, 3): "Man",
        ("Pewter House", 4, 5): "Youngster",
        ("Nidoran House", 4, 5): "Nidoran",
        ("Nidoran House", 3, 5): "Boy",
        ("Nidoran House", 1, 2): "Man",
    }
)
features = {}
for place, map_id, blockset_name, collision_name in map_specs:
    for line in (
        (reference / f"data/maps/objects/{map_id}.asm").read_text().splitlines()
    ):
        match = re.search(r"bg_event\s+(\d+),\s*(\d+),\s*(\w+)", line)
        if match:
            features[place, int(match.group(1)), int(match.group(2))] = match.group(3)
        match = re.search(
            r"object_event\s+(\d+),\s*(\d+),\s*SPRITE_POKE_BALL,.*?,\s*(ANTIDOTE|POTION|POKE_BALL|MOON_STONE|HP_UP)\s*$",
            line,
        )
        if match:
            features[place, int(match.group(1)), int(match.group(2))] = {
                "ANTIDOTE": "Antidote",
                "POTION": "Potion",
                "POKE_BALL": "Poke Ball",
                "MOON_STONE": "Moon Stone",
                "HP_UP": "HP Up",
            }[match.group(3)]
def english_list(values):
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " or " + values[-1]


def choices(subject, entries):
    groups = {}
    for key, value in entries.items():
        groups.setdefault(value, []).append(f'"{key}"')
    result = [f"  Choose the answer by {subject}:"]
    for value, names in groups.items():
        result.append(f'    For {english_list(names)}, use "{value}".')
    result.append('    Otherwise, use "".')
    return result


lines = [
    "This chapter shares only terrain, map width, map height, person, person ahead, feature, feature ahead, counter, column ahead, row ahead, conversation column, conversation row and travel.",
    "",
    "Use the foundation chapter.",
    "",
]
map_data = {}
raw_tiles = {}
for place, map_id, blockset_name, collision_name in map_specs:
    header = (reference / f"data/maps/headers/{map_id}.asm").read_text()
    key = re.search(r"map_header\s+\w+,\s*(\w+),", header).group(1)
    match = re.search(r"map_const\s+" + key + r",\s*(\d+),\s*(\d+)", constants)
    width, height = (int(size) * 2 for size in match.groups())
    map_blocks = (reference / f"maps/{map_id}.blk").read_bytes()
    blockset = (reference / f"gfx/blocksets/{blockset_name}.bst").read_bytes()
    tiles = []
    raw = []
    for row in range(height):
        for column in range(width):
            block_id = map_blocks[(row // 2) * (width // 2) + (column // 2)]
            tile = blockset[block_id * 16 + (row % 2) * 8 + (column % 2) * 2 + 4]
            raw.append(f"{tile:02x}")
            terrain = "." if tile in collision_sets[collision_name] else "#"
            grass_tile = {"overworld": 0x52, "forest": 0x20}.get(blockset_name)
            if tile == grass_tile:
                terrain = "g"
            if (place, column, row) in warps:
                terrain = "d"
            tiles.append(terrain)
    map_data[place] = (width, height, "".join(tiles))
    raw_tiles[place] = "".join(raw)
lines += ["The map dimensions are width and height, in that order:"]
for place, (width, height, encoded_tiles) in map_data.items():
    lines += [f'  "{place}" has {width} and {height}.']
lines += [
    "",
    "To work out the map width (number):",
    "  Let the dimension be the map dimensions for Journey's place.",
    "  The answer is the dimension's width or else 0.",
    "",
    "To work out the map height (number):",
    "  Let the dimension be the map dimensions for Journey's place.",
    "  The answer is the dimension's height or else 0.",
    "",
    "To work out the raw tiles (text):",
]
lines += choices("Journey's place", raw_tiles)
lines += [
    "",
    "To work out the tile mark (text) at a column (number) by a row (number):",
    "  If the column is less than 0 or the row is less than 0:",
    '    The answer is "".',
    "  If the column is at least the map width or the row is at least the map height:",
    '    The answer is "".',
    "  Let the marks be the raw tiles.",
    "  Let the position be (the row * the map width + the column) * 2.",
    "  The answer is the first 2 letters of the last (the length of the marks - the position) letters of the marks.",
    "",
    "To work out the counter (yes or no) at a column (number) by a row (number):",
    "  Let the mark be the tile mark at the column by the row.",
]
counter_groups = {}
for place, map_id, blockset_name, collision_name in map_specs:
    counters = tuple(sorted(counter_sets[collision_name]))
    if counters:
        counter_groups.setdefault(counters, []).append(place)
for counters, places in counter_groups.items():
    names = [f'"{place}"' for place in places]
    marks = [f'"{tile:02x}"' for tile in counters]
    place_test = f"Journey's place is {english_list(names)}" if len(names) == 1 else f"Journey's place is one of {english_list(names)}"
    mark_test = f"the mark is {english_list(marks)}" if len(marks) == 1 else f"the mark is one of {english_list(marks)}"
    lines += [f"  If {place_test} and {mark_test}:", "    The answer is yes."]
lines += [
    "  The answer is no.",
    "",
    "To work out the ledge (yes or no) at a column (number) by a row (number):",
    "  Let the origin be the tile mark at Journey's column by Journey's row.",
    "  Let the destination be the tile mark at the column by the row.",
    '  If Journey\'s facing is "south" and ((the origin is "2c" and the destination is "37") or (the origin is "39" and (the destination is "36" or the destination is "37"))):',
    "    The answer is yes.",
    '  If Journey\'s facing is "west" and (the origin is "2c" or the origin is "39") and the destination is "27":',
    "    The answer is yes.",
    '  If Journey\'s facing is "east" and ((the origin is "2c" and (the destination is "0d" or the destination is "1d")) or (the origin is "39" and the destination is "0d")):',
    "    The answer is yes.",
    "  The answer is no.",
    "",
    "To work out the map tiles (text):",
]
lines += choices("Journey's place", {place: values[2] for place, values in map_data.items()})
lines += [
    "",
    "To work out the terrain (text) at a column (number) by a row (number):",
    "  If the column is less than 0 or the row is less than 0:",
    '    The answer is "wall".',
    "  If the column is at least the map width or the row is at least the map height:",
    '    The answer is "wall".',
    "  Let the tiles be the map tiles.",
    "  Let the position be the row * the map width + the column.",
    "  Let the mark be the first 1 letters of the last (the length of the tiles - the position) letters of the tiles.",
    '  If the mark is "#":',
    '    The answer is "wall".',
    '  If the mark is "g":',
    '    The answer is "grass".',
    '  If the mark is "d":',
    '    The answer is "door".',
    '  The answer is "floor".',
    "",
    "To work out the position key (text) at a column (number) by a row (number):",
    "  If the column is not (the column rounded to the nearest 1) or the row is not (the row rounded to the nearest 1):",
    '    The answer is "".',
    '  The answer is "{Journey\'s place}:{the column},{the row}".',
    "",
    "To work out the person (text) at a column (number) by a row (number):",
]
for (place, column, row), person in npcs.items():
    if person == "Route 22 Rival" or (place == "Blue's House" and person == "Daisy"):
        condition = f'Journey\'s place is "{place}" and the column is {column} and the row is {row}'
        if person == "Route 22 Rival":
            condition += " and Journey's badge is 0 and Journey's route rival beaten is 0"
        else:
            condition += f" and Journey's daisy walking is {int(column == 6)}"
        lines += [f"  If {condition}:", f'    The answer is "{person}".']

def position_choices(entries):
    positions = {f"{place}:{column},{row}": value for (place, column, row), value in entries.items()}
    return choices("the position key at the column by the row", positions)


lines += position_choices({key: person for key, person in npcs.items() if person != "Route 22 Rival" and not (key[0] == "Blue's House" and person == "Daisy")})
lines += ["", "To work out the feature (text) at a column (number) by a row (number):"]
lines += position_choices(features)
lines += [""]
lines += """To work out the forward column (number) by a distance (number):
  If Journey's facing is "west":
    The answer is Journey's column - the distance.
  If Journey's facing is "east":
    The answer is Journey's column + the distance.
  The answer is Journey's column.

To work out the forward row (number) by a distance (number):
  If Journey's facing is "north":
    The answer is Journey's row - the distance.
  If Journey's facing is "south":
    The answer is Journey's row + the distance.
  The answer is Journey's row.

To work out the column ahead (number):
  The answer is the forward column by 1.

To work out the row ahead (number):
  The answer is the forward row by 1.

To work out the conversation distance (number):
  Let the column be the column ahead.
  Let the row be the row ahead.
  If the person at the column by the row is "" and the counter at the column by the row is yes:
    The answer is 2.
  The answer is 1.

To work out the conversation column (number):
  The answer is the forward column by the conversation distance.

To work out the conversation row (number):
  The answer is the forward row by the conversation distance.

To work out the feature ahead (text):
  The answer is the feature at the column ahead by the row ahead.

To work out the person ahead (text):
  Let the column be the column ahead.
  Let the row be the row ahead.
  Let the nearby be the person at the column by the row.
  If the nearby is not "":
    The answer is the nearby.
  If the counter at the column by the row is yes:
    The answer is the person at (the forward column by 2) by (the forward row by 2).
  The answer is "".""".splitlines()
lines += ["", "The doorways are arrival place, arrival column and arrival row, in that order:"]
for (place, column, row), (destination, destination_column, destination_row) in warps.items():
    lines.append(f'  "{place}:{column},{row}" has "{destination}", {destination_column} and {destination_row}.')
lines += [
    "",
    "To cross:",
    "  Let the key be the position key at Journey's column by Journey's row.",
    "  Let the doorway be the doorways for the key.",
    "  If the doorway is nothing:",
    "    Stop.",
    "  Set Journey's place to the doorway's arrival place.",
    "  Set Journey's column to the doorway's arrival column.",
    "  Set Journey's row to the doorway's arrival row.",
]
lines += [
    "",
    "To travel a direction (text):",
    "  Let the column be Journey's column.",
    "  Let the row be Journey's row.",
    '  If the direction is "north" or the direction is "up":',
    '    Set Journey\'s facing to "north".',
    "    Subtract 1 from the row.",
    '  Otherwise if the direction is "south" or the direction is "down":',
    '    Set Journey\'s facing to "south".',
    "    Add 1 to the row.",
    '  Otherwise if the direction is "west" or the direction is "left":',
    '    Set Journey\'s facing to "west".',
    "    Subtract 1 from the column.",
    '  Otherwise if the direction is "east" or the direction is "right":',
    '    Set Journey\'s facing to "east".',
    "    Add 1 to the column.",
    "  Otherwise:",
    "    Stop.",
]
for old, new, edge, offset in [
    ("Pallet Town", "Route 1", "north", 0),
    ("Route 1", "Pallet Town", "south", 0),
    ("Route 1", "Viridian City", "north", 10),
    ("Viridian City", "Route 1", "south", -10),
    ("Viridian City", "Route 2", "north", -10),
    ("Route 2", "Viridian City", "south", 10),
    ("Route 2", "Pewter City", "north", 10),
    ("Pewter City", "Route 2", "south", -10),
    ("Viridian City", "Route 22", "west", -8),
    ("Route 22", "Viridian City", "east", 8),
]:
    old_width, old_height, _ = map_data[old]
    new_width, new_height, new_tiles = map_data[new]
    vertical = edge in ("north", "south")
    source_limit = old_width if vertical else old_height
    valid = []
    for coordinate in range(source_limit):
        target = coordinate + offset
        if vertical:
            column, row = target, (new_height - 1 if edge == "north" else 0)
        else:
            column, row = (new_width - 1 if edge == "west" else 0), target
        if (
            0 <= column < new_width
            and 0 <= row < new_height
            and new_tiles[row * new_width + column] != "#"
            and (new, column, row) not in npcs
        ):
            valid.append(coordinate)
    groups = []
    for coordinate in valid:
        if groups and coordinate == groups[-1][-1] + 1:
            groups[-1].append(coordinate)
        else:
            groups.append([coordinate])
    if groups:
        dimension = "column" if vertical else "row"
        boundary = {
            "north": "the row is less than 0",
            "south": "the row is at least the map height",
            "west": "the column is less than 0",
            "east": "the column is at least the map width",
        }[edge]
        ranges = [f"the {dimension} is at least {group[0]} and the {dimension} is at most {group[-1]}" for group in groups]
        range_condition = ranges[0] if len(ranges) == 1 else " or ".join(f"({item})" for item in ranges)
        if len(ranges) > 1:
            range_condition = f"({range_condition})"
        condition = f"{boundary} and {range_condition}"
        lines += [
            f'  If Journey\'s place is "{old}" and {condition}:',
            f'    Set Journey\'s place to "{new}".',
        ]
        if offset > 0:
            lines += [f"    Add {offset} to the {dimension}."]
        if offset < 0:
            lines += [f"    Subtract {-offset} from the {dimension}."]
        if vertical:
            lines += [
                "    Set Journey's column to the column.",
                (
                    "    Set Journey's row to the map height - 1."
                    if edge == "north"
                    else "    Set Journey's row to 0."
                ),
            ]
        else:
            lines += [
                "    Set Journey's row to the row.",
                (
                    "    Set Journey's column to the map width - 1."
                    if edge == "west"
                    else "    Set Journey's column to 0."
                ),
            ]
        lines += ["    Stop."]
lines += [
    '  If Journey\'s place is "Route 1" or Journey\'s place is "Route 22":',
    "    If the ledge at the column by the row is yes:",
    '      If Journey\'s facing is "south":',
    "        Add 1 to the row.",
    '      If Journey\'s facing is "west":',
    "        Subtract 1 from the column.",
    '      If Journey\'s facing is "east":',
    "        Add 1 to the column.",
]
lines += [
    '  If the terrain at the column by the row is "wall":',
    "    Stop.",
    '  If the person at the column by the row is not "":',
    "    Stop.",
    "  Set Journey's column to the column.",
    "  Set Journey's row to the row.",
    "  Cross.",
    "",
]
output_path.parent.mkdir(parents=True, exist_ok=True)
output_path.write_text("\n".join(lines), encoding="utf-8")

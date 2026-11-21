import re
import unittest
from pathlib import Path


MAPS = Path(__file__).resolve().parents[1] / "docs" / "red" / "maps.english"


def read_map_data(source):
    dimensions_section = source.split("The map layouts are width, height and blockset, in that order:", 1)[1].split("\nTo work out", 1)[0]
    dimensions = {}
    for name, width, height in re.findall(r'^  "([^"]+)" has (\d+), (\d+) and "[^"]+"\.$', dimensions_section, re.MULTILINE):
        if name in dimensions:
            raise ValueError(f"{name}: duplicate dimensions")
        dimensions[name] = (int(width), int(height))

    if not dimensions:
        raise ValueError("No map dimensions found")

    def read_tiles(heading):
        section = source.split(heading, 1)[1].split("\nTo work out", 1)[0]
        maps = {}
        for names, data in re.findall(r'^    For (.+?), use "([^"]*)"\.$', section, re.MULTILINE):
            for name in re.findall(r'"([^"]+)"', names):
                if name in maps:
                    raise ValueError(f"{name}: duplicate {heading}")
                maps[name] = data
        return maps

    return dimensions, read_tiles("To work out the raw tiles (text):"), read_tiles("To work out the map tiles (text):")


def validate_map_data(dimensions, raw_maps, terrain_maps):
    for label, maps, stride, allowed in (
        ("raw tiles", raw_maps, 2, set("0123456789abcdef")),
        ("terrain", terrain_maps, 1, set(".#gd")),
    ):
        for name in sorted(dimensions.keys() | maps.keys()):
            if name not in dimensions:
                raise ValueError(f"{name}: {label} has no dimensions")
            if name not in maps:
                raise ValueError(f"{name}: missing {label}")
            width, height = dimensions[name]
            if width <= 0 or height <= 0:
                raise ValueError(f"{name}: dimensions must be positive")
            data = maps[name]
            expected = width * height * stride
            if len(data) != expected:
                tile = min(len(data), expected) // stride
                raise ValueError(f"{name}: {label} length {len(data)}, expected {expected}; first incomplete or extra tile at ({tile % width}, {tile // width})")
            for index, symbol in enumerate(data):
                if symbol not in allowed:
                    tile = index // stride
                    raise ValueError(f"{name}: invalid {label} symbol {symbol!r} at ({tile % width}, {tile // width})")


class RedMapDataTests(unittest.TestCase):
    def test_map_encodings_match_dimensions(self):
        validate_map_data(*read_map_data(MAPS.read_text(encoding="utf-8")))

    def test_malformed_data_identifies_map_and_coordinate(self):
        dimensions = {"Example": (2, 2)}
        with self.assertRaisesRegex(ValueError, r"Example: invalid raw tiles symbol 'x' at \(1, 0\)"):
            validate_map_data(dimensions, {"Example": "00x00000"}, {"Example": "...."})
        with self.assertRaisesRegex(ValueError, r"Example: invalid terrain symbol '\?' at \(0, 1\)"):
            validate_map_data(dimensions, {"Example": "00000000"}, {"Example": "..?."})
        with self.assertRaisesRegex(ValueError, r"Example: terrain length 3, expected 4; first incomplete or extra tile at \(1, 1\)"):
            validate_map_data(dimensions, {"Example": "00000000"}, {"Example": "..."})


if __name__ == "__main__":
    unittest.main()


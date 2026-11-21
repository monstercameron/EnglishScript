import unittest
from pathlib import Path
from englishscript import compile_source


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


def travel(place, column, row, direction):
    source = f'''Use the foundation chapter.
Use the maps chapter.
Set Journey's place to "{place}".
Set Journey's column to {column}.
Set Journey's row to {row}.
Travel "{direction}".
Say "{{Journey's place}}:{{Journey's column}},{{Journey's row}},{{Journey's facing}}".
'''
    output = []
    compile_source(source, folder=RED).run(out=output.append)
    return output[0]


class RedWorldBorders(unittest.TestCase):
    def test_walking_off_a_map_arrives_across_the_border(self):
        self.assertEqual(travel("Pallet Town", 4, 0, "north"), "Route 1:4,35,north")
        self.assertEqual(travel("Route 1", 4, 0, "north"), "Viridian City:14,35,north")
        self.assertEqual(travel("Viridian City", 14, 35, "south"), "Route 1:4,0,south")
        self.assertEqual(travel("Viridian City", 0, 15, "west"), "Route 22:39,7,west")
        self.assertEqual(travel("Route 22", 39, 7, "east"), "Viridian City:0,15,east")

    def test_a_border_is_closed_where_the_arrival_tile_is_a_wall(self):
        self.assertEqual(travel("Pallet Town", 3, 0, "north"), "Pallet Town:3,0,north")
        self.assertEqual(travel("Route 2", 4, 0, "north"), "Route 2:4,0,north")
        self.assertEqual(travel("Route 2", 8, 0, "north"), "Pewter City:18,35,north")

    def test_places_without_a_border_stop_at_the_edge(self):
        self.assertEqual(travel("Route 22", 0, 0, "north"), "Route 22:0,0,north")
        self.assertEqual(travel("Bedroom", 0, 0, "west"), "Bedroom:0,0,west")

    def test_ledges_are_hopped_only_in_their_own_direction(self):
        self.assertEqual(travel("Route 1", 4, 4, "south"), "Route 1:4,6,south")
        self.assertEqual(travel("Route 1", 4, 4, "north"), "Route 1:4,3,north")


class RedWorldLandmarks(unittest.TestCase):
    def test_landmarks_are_named(self):
        source = '''Use the foundation, maps and scenery chapters.
Set Journey's place to "Pallet Town".
Say the landmark at 6 by 3.
Say the landmark at 9 by 1.
Say the landmark at 2 by 5.
Say the landmark at -1 by 0.
Set Journey's place to "Home".
Say the landmark at 3 by 1.
'''
        output = []
        compile_source(source, folder=RED).run(out=output.append)
        self.assertEqual(output[:5], ["roof", "tree", "", "", "television"])


if __name__ == "__main__":
    unittest.main()

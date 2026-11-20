import unittest
from pathlib import Path
from englishscript import compile_source


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


class RedMapCounters(unittest.TestCase):
    def test_fractional_coordinates_do_not_match_nearby_people_or_signs(self):
        source = '''Use the foundation and maps chapters.
Set Journey's place to "Home".
Say the person at 5 by 4.
Say the person at (5 + 1 / 1000000) by 4.
Set Journey's place to "Pallet Town".
Say the feature at 3 by 5.
Say the feature at 3 by (5 - 1 / 1000000).
'''
        output = []
        compile_source(source, folder=RED).run(out=output.append)
        self.assertEqual(output[:4], ["Mom", "", "TEXT_PALLETTOWN_PLAYERSHOUSE_SIGN", ""])

    def test_daisy_has_one_placement_for_each_story_state(self):
        source = '''Use the foundation chapter.
Use the maps chapter.
Set Journey's place to "Blue's House".
Say the person at 2 by 3.
Say the person at 6 by 4.
Set Journey's daisy walking to 1.
Say the person at 2 by 3.
Say the person at 6 by 4.
'''
        output = []
        compile_source(source, folder=RED).run(out=output.append)
        self.assertEqual(output[:4], ["Daisy", "", "", "Daisy"])

    def test_route_22_rival_disappears_after_badge(self):
        source = '''Use the foundation chapter.
Use the maps chapter.
Set Journey's place to "Route 22".
Say the person at 25 by 5.
Set Journey's route rival beaten to 1.
Say the person at 25 by 5.
Set Journey's route rival beaten to 0.
Set Journey's badge to 1.
Say the person at 25 by 5.
Set Journey's column to 26.
Set Journey's row to 5.
Travel "west".
Say Journey's column.
'''
        output = []
        compile_source(source, folder=RED).run(out=output.append)
        self.assertEqual(output[:4], ["Route 22 Rival", "", "", "25"])

    def test_counter_extends_talking_range_only_in_facing_direction(self):
        source = ['Use the foundation chapter.', 'Use the maps chapter.']
        cases = [
            ("Viridian Mart", 2, 5, "west", "Clerk"),
            ("Pewter Mart", 2, 5, "west", "Clerk"),
            ("Viridian Center", 3, 3, "north", "Nurse"),
            ("Pewter Center", 3, 3, "north", "Nurse"),
            ("Viridian Center", 4, 1, "south", "Visitor"),
            ("Viridian Mart", 2, 5, "north", ""),
        ]
        for place, column, row, facing, _ in cases:
            source.extend([
                f'Set Journey\'s place to "{place}".',
                f"Set Journey's column to {column}.",
                f"Set Journey's row to {row}.",
                f'Set Journey\'s facing to "{facing}".',
                'Say the person ahead.',
            ])
        output = []
        compile_source("\n".join(source), folder=RED).run(out=output.append)
        self.assertEqual(output[:len(cases)], [case[-1] for case in cases])


if __name__ == "__main__":
    unittest.main()


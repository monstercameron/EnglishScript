import shutil
import tempfile
import unittest
from pathlib import Path

from englishscript import compile_file


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


class RedStoryReference(unittest.TestCase):
    def run_story(self, source):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for chapter in RED.glob("*.english"):
                shutil.copy(chapter, root / chapter.name)
            story = root / "story.english"
            story.write_text(story.read_text(encoding="utf-8").replace(
                "This chapter shares only advance and resolve.",
                "This chapter shares only advance, resolve, storybook, Story, finish and meet."), encoding="utf-8")
            (root / "test.english").write_text("Use the foundation chapter.\nUse the story chapter.\n" + source, encoding="utf-8")
            return compile_file(root / "test.english").run(out=lambda text="": None)

    def test_mart_entry_gives_parcel_after_scripted_movement(self):
        world = self.run_story('''Set Journey's stage to "parcel".
Set Journey's place to "Viridian City".
Set Journey's column to 29.
Set Journey's row to 20.
Set Journey's mode to "walk".
Advance "up".
Finish.
''')
        journey = world.named["journey"].fields
        self.assertEqual((journey["place"], journey["column"], journey["row"], journey["facing"]),
                         ("Viridian Mart", 2, 4, "north"))
        self.assertEqual(journey["parcel"], 1)
        self.assertEqual(journey["mode"], "dialogue")
        self.assertIn("PARCEL", journey["message"])

    def test_clerk_sells_only_after_oak_receives_parcel(self):
        carrying = self.run_story('''Set Journey's stage to "parcel".
Set Journey's parcel to 1.
Meet "Clerk".
''')
        self.assertEqual(carrying.named["journey"].fields["mode"], "dialogue")
        delivered = self.run_story('''Set Journey's dex to 1.
Meet "Clerk".
''')
        self.assertEqual(delivered.named["journey"].fields["mode"], "shop")

    def test_oak_wont_let_player_leave_without_a_starter(self):
        world = self.run_story('''Set Journey's stage to "choose starter".
Set Journey's place to "Oak's Lab".
Set Journey's column to 4.
Set Journey's row to 10.
Set Journey's mode to "walk".
Advance "down".
''')
        journey = world.named["journey"].fields
        self.assertEqual(journey["place"], "Oak's Lab")
        self.assertEqual(journey["mode"], "dialogue")

    def test_daisy_gives_town_map_only_after_pokedex(self):
        before = self.run_story('''Meet "Daisy".
''')
        self.assertEqual(before.named["journey"].fields["town map"], 0)
        after = self.run_story('''Set Journey's dex to 1.
Meet "Daisy".
''')
        self.assertEqual(after.named["journey"].fields["town map"], 1)
        self.assertIn("TOWN MAP", after.named["journey"].fields["message"])

    def test_daisy_walks_after_return_to_pallet(self):
        world = self.run_story('''Set Journey's place to "Blue's House".
Set Journey's column to 2.
Set Journey's row to 6.
Set Journey's mode to "walk".
Set Journey's town map to 1.
Set Journey's blue house entered to 1.
Advance "down".
''')
        self.assertEqual(world.named["journey"].fields["daisy walking"], 1)

    def test_optional_rival_win_updates_shared_map_flag(self):
        world = self.run_story('''Use the battle chapter.
Set Story's challenger to "route rival".
Set Combat's outcome to "win".
Resolve.
''')
        self.assertEqual(world.named["journey"].fields["route rival beaten"], 1)

    def test_town_map_bag_controls_and_location(self):
        world = compile_file(RED / "main.english").run(out=lambda text="": None)
        journey = world.named["journey"].fields
        stock = world.named["stock"].fields
        controls = world.named["controls"].fields
        journey.update({"mode": "bag", "place": "Pewter Gym", "town map": 1, "tm34": 1})
        stock["cursor"] = 6
        world.event(lambda: controls.__setitem__("action", "a"))
        self.assertEqual(journey["mode"], "town map")
        navigator = next(value for name, value in world.named.items() if name.startswith("navigator"))
        self.assertEqual(navigator.fields["current"], 6)
        self.assertEqual(navigator.fields["label"], "PEWTER CITY")
        world.event(lambda: controls.__setitem__("action", "right"))
        self.assertEqual(navigator.fields["label"], "CERULEAN CITY")
        world.event(lambda: controls.__setitem__("action", "b"))
        self.assertEqual(journey["mode"], "bag")
        self.assertEqual(stock["cursor"], 6)
        world.event(lambda: controls.__setitem__("action", "up"))
        world.event(lambda: controls.__setitem__("action", "a"))
        self.assertEqual(stock["notice"], "TM34 BIDE")

    def test_brock_victory_disables_gym_trainer(self):
        world = self.run_story('''Set Journey's badge to 1.
Meet "Gym Trainer".
''')
        self.assertEqual(world.named["story"].fields["scene"], "")
        self.assertEqual(world.named["journey"].fields["mode"], "dialogue")


if __name__ == "__main__":
    unittest.main()



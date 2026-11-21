import shutil
import tempfile
import unittest
from pathlib import Path

from englishscript import compile_file


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


class RedSoundEvents(unittest.TestCase):
    def run_scene(self, source):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for chapter in RED.glob("*.english"):
                shutil.copy(chapter, root / chapter.name)
            story = root / "story.english"
            story.write_text(story.read_text(encoding="utf-8").replace(
                "This chapter shares only advance and resolve.",
                "This chapter shares only advance, resolve, storybook, Story, finish and meet."), encoding="utf-8")
            (root / "test.english").write_text("Use the foundation chapter.\n" + source, encoding="utf-8")
            return compile_file(root / "test.english").run(out=lambda text="": None)

    def test_encounter_and_damaging_turn(self):
        world = self.run_scene('''Use the battle chapter.
Enlist "Bulbasaur".
Confront "Pidgey" at 3.
Set Combat's foe's health to 100.
Set Combat's foe's speed to 0.
Fight.
''')
        self.assertEqual(world.named["score"].fields["effect"], "noise:2 45:1 38:2")
        self.assertEqual(world.named["score"].fields["effect count"], 2)

    def test_victory_takes_precedence_over_hit(self):
        world = self.run_scene('''Use the battle chapter.
Enlist "Bulbasaur".
Confront "Pidgey" at 3.
Set Combat's foe's health to 1.
Set Combat's foe's speed to 0.
Fight.
''')
        self.assertEqual(world.named["combat"].fields["outcome"], "win")
        self.assertEqual(world.named["score"].fields["effect"], "72:1 72:1 72:1 72:3 68:3 70:3 72:1 0:1 70:1 72:5")
        self.assertEqual(world.named["score"].fields["effect count"], 2)

    def test_badge_and_tm_are_cued_when_received(self):
        world = self.run_scene('''Use the story chapter.
Set Story's scene to "brock badge".
Finish.
Set Story's scene to "brock tm received".
Finish.
''')
        self.assertEqual(world.named["score"].fields["effect"], "72:1 76:1 79:1 84:2")
        self.assertEqual(world.named["score"].fields["effect count"], 2)
        self.assertEqual(world.named["journey"].fields["tm34"], 1)

    def test_ground_item_only_sounds_once(self):
        world = self.run_scene('''Use the pack chapter.
Set Journey's place to "Viridian Forest".
Set Journey's column to 12.
Set Journey's row to 30.
Set Journey's facing to "north".
Examine.
Examine.
''')
        self.assertEqual(world.named["score"].fields["effect"], "72:1 76:1 79:1 84:2")
        self.assertEqual(world.named["score"].fields["effect count"], 1)

    def test_nurse_and_parcel(self):
        world = self.run_scene('''Use the story chapter.
Meet "Nurse".
Set Journey's stage to "parcel".
Meet "Clerk".
''')
        self.assertEqual(world.named["score"].fields["effect"], "72:1 76:1 79:1 84:2")
        self.assertEqual(world.named["score"].fields["effect count"], 2)
        self.assertEqual(world.named["journey"].fields["parcel"], 1)


    def test_wild_cry_matches_final_encounter_species(self):
        world = self.run_scene('''Use the battle chapter.
Enlist "Bulbasaur".
Encounter "Route 22".
''')
        species = world.named["combat"].fields["foe"].fields["species"]
        self.assertEqual(species, "Nidoran M")
        reference = self.run_scene(f'Use the cries chapter.\nCry "{species}".\n')
        self.assertEqual(world.named["score"].fields["cry"], reference.named["score"].fields["cry"])
        self.assertEqual(world.named["score"].fields["cry count"], 1)
        self.assertEqual(world.named["score"].fields["effect"], "noise:1 0:1 79:1 84:1 79:1 84:2")
        self.assertEqual(world.named["score"].fields["effect count"], 1)

    def test_trainer_replacement_cry_preserves_faint_and_victory(self):
        world = self.run_scene('''Use the battle chapter.
Enlist "Bulbasaur".
Challenge "brock".
Set Combat's foe's health to 1.
Set Combat's foe's speed to 0.
Fight.
''')
        self.assertEqual(world.named["combat"].fields["foe"].fields["species"], "Onix")
        reference = self.run_scene('Use the cries chapter.\nCry "Onix".\n')
        self.assertEqual(world.named["score"].fields["cry"], reference.named["score"].fields["cry"])
        self.assertEqual(world.named["score"].fields["cry count"], 2)
        self.assertEqual(world.named["score"].fields["effect"], "67:1 63:1 60:1 55:3")
        self.assertEqual(world.named["score"].fields["effect count"], 2)

    def test_final_victory_does_not_repeat_a_cry(self):
        world = self.run_scene('''Use the battle chapter.
Enlist "Bulbasaur".
Challenge "brock".
Set Combat's foe's health to 1.
Set Combat's foe's speed to 0.
Fight.
Set Combat's foe's health to 1.
Set Combat's foe's speed to 0.
Fight.
''')
        self.assertEqual(world.named["combat"].fields["outcome"], "win")
        self.assertEqual(world.named["score"].fields["cry count"], 2)
        self.assertEqual(world.named["score"].fields["effect count"], 3)
        self.assertEqual(world.named["score"].fields["effect"], "72:1 72:1 72:1 72:3 68:3 70:3 72:1 0:1 70:1 72:5")

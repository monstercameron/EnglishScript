import shutil
import tempfile
import unittest
from pathlib import Path

from englishscript import compile_file


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


class RedParty(unittest.TestCase):
    def run_story(self, text):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for chapter in RED.glob("*.english"):
                shutil.copy(chapter, root / chapter.name)
            (root / "main.english").write_text(
                "Use the battle chapter.\nUse the party chapter.\n" + text,
                encoding="utf-8",
            )
            return compile_file(root / "main.english").run(out=lambda text="": None)

    def test_capture_and_switch_preserves_each_member(self):
        world = self.run_story('''Set Combat's starter to "Charmander".
Enlist.
Set Combat's health to 7.
Set Combat's pp one to 11.
Challenge "wild".
Set Combat's opponent to "Caterpie".
Set Combat's enemy level to 3.
Set Combat's enemy health to 1.
Capture.
Switch to 2.
Set Combat's health to 5.
Set Combat's pp one to 12.
Switch to 1.
''')
        team = world.named["team"].fields
        combat = world.named["combat"].fields
        second = world.named["second"].fields
        self.assertEqual((team["count"], team["selected"], team["result"]), (2, 1, "caught"))
        self.assertEqual((combat["starter"], combat["health"], combat["pp one"]), ("Charmander", 7, 11))
        self.assertEqual((second["species"], second["health"], second["pp one"]), ("Caterpie", 5, 12))
        self.assertEqual(combat["outcome"], "caught")

    def test_trainer_and_full_party_do_not_capture(self):
        world = self.run_story('''Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "brock".
Capture.
''')
        self.assertEqual(world.named["team"].fields["result"], "trainer")
        self.assertEqual(world.named["combat"].fields["active"], 1)
        world = self.run_story('''Set Combat's starter to "Bulbasaur".
Enlist.
Record.
Set Team's count to 6.
Challenge "wild".
Capture.
''')
        self.assertEqual(world.named["team"].fields["result"], "full")
        self.assertEqual(world.named["combat"].fields["active"], 1)

    def test_faint_sends_reserve_or_loses_when_none_remain(self):
        world = self.run_story('''Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "wild".
Set Combat's opponent to "Caterpie".
Set Combat's enemy level to 3.
Set Combat's enemy health to 1.
Capture.
Set Combat's health to 0.
Set Combat's outcome to "fainted".
Replace.
''')
        self.assertEqual(world.named["team"].fields["result"], "replacement")
        self.assertEqual(world.named["combat"].fields["species"], "Caterpie")
        self.assertEqual(world.named["combat"].fields["active"], 1)
        world = self.run_story('''Set Combat's starter to "Bulbasaur".
Enlist.
Set Combat's health to 0.
Set Combat's outcome to "fainted".
Replace.
''')
        self.assertEqual(world.named["team"].fields["result"], "loss")
        self.assertEqual(world.named["combat"].fields["outcome"], "loss")
        self.assertGreater(world.named["combat"].fields["health"], 0)

    def test_fractional_and_out_of_range_slots_keep_dispatch_behavior(self):
        world = self.run_story('''Set Combat's starter to "Bulbasaur".
Enlist.
Record.
Set Team's count to 2.
Set Combat's health to 7.
Switch to 1.5.
Set Combat's health to 4.
Record.
Switch to 3.
''')
        team = world.named["team"].fields
        self.assertEqual((team["selected"], team["notice"]), (1.5, "NO POKEMON"))
        self.assertEqual(world.named["first"].fields["health"], 7)
        self.assertEqual(world.named["second"].fields["health"], 0)
        self.assertEqual(world.named["combat"].fields["health"], 4)

    def test_replace_skips_selected_and_fainted_members_in_slot_order(self):
        world = self.run_story('''Set Combat's starter to "Bulbasaur".
Enlist.
Record.
Set Team's count to 4.
Set Second's health to 0.
Set Third's health to 4.
Set Third's species to "Pidgey".
Set Fourth's health to 5.
Set Fourth's species to "Caterpie".
Replace.
''')
        self.assertEqual(world.named["team"].fields["selected"], 3)
        self.assertEqual(world.named["team"].fields["result"], "replacement")
        self.assertEqual(world.named["combat"].fields["species"], "Pidgey")

    def test_failed_capture_and_party_healing(self):
        world = self.run_story('''Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "wild".
Set Combat's opponent to "Kakuna".
Set Combat's seed to 1.
Capture.
''')
        self.assertEqual(world.named["team"].fields["result"], "escaped")
        self.assertEqual(world.named["combat"].fields["active"], 1)
        world = self.run_story('''Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "wild".
Set Combat's opponent to "Caterpie".
Set Combat's enemy level to 3.
Set Combat's enemy health to 1.
Capture.
Set Combat's health to 1.
Switch to 2.
Set Combat's health to 1.
Revive.
''')
        first = world.named["first"].fields
        second = world.named["second"].fields
        self.assertEqual(first["health"], first["maximum health"])
        self.assertEqual(second["health"], second["maximum health"])
        self.assertEqual(world.named["combat"].fields["species"], "Caterpie")


if __name__ == "__main__":
    unittest.main()

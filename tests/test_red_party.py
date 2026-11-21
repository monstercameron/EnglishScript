import unittest
from pathlib import Path

from englishscript import compile_source


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


def run(source):
    world = compile_source("Use the foundation chapter.\nUse the battle chapter.\nUse the party chapter.\n" + source,
                           folder=RED).run(out=lambda text="": None)
    combat = world.named["combat"].fields
    team = world.named["team"].fields
    members = [member.fields for member in team["members"]]
    return combat, combat["ally"].fields, team, members


class RedParty(unittest.TestCase):
    def test_capture_and_switch_keep_each_member_by_reference(self):
        combat, ally, team, members = run('''Enlist "Charmander".
Set Combat's ally's health to 7.
Set item 1 of Combat's ally's pp to 11.
Confront "Caterpie" at 3.
Set Combat's foe's health to 1.
Capture.
Switch to 2.
Set Combat's ally's health to 5.
Set item 1 of Combat's ally's pp to 12.
Switch to 1.
''')
        self.assertEqual((team["selected"], team["result"], len(members)), (1, "caught", 2))
        self.assertEqual((ally["species"], ally["health"], ally["pp"][0]), ("Charmander", 7, 11))
        self.assertEqual((members[1]["species"], members[1]["health"], members[1]["pp"][0]), ("Caterpie", 5, 12))
        self.assertEqual(combat["outcome"], "caught")
        self.assertEqual(combat["message"], "Caught Caterpie!")

    def test_caught_member_gets_experience_for_its_growth_rate(self):
        _, _, _, members = run('''Enlist "Charmander".
Confront "Nidoran F" at 4.
Set Combat's foe's health to 1.
Set Combat's seed to 0.
Capture.
Confront "Rattata" at 4.
Set Combat's foe's health to 1.
Set Combat's seed to 0.
Capture.
''')
        self.assertEqual([(member["species"], member["experience"]) for member in members],
                         [("Charmander", 135), ("Nidoran F", 96), ("Rattata", 64)])

    def test_status_stays_with_the_member(self):
        _, ally, _, members = run('''Enlist "Charmander".
Enlist "Pidgey".
Set Combat's ally's status to "poisoned".
Switch to 1.
''')
        self.assertEqual(ally["species"], "Charmander")
        self.assertEqual(members[1]["status"], "poisoned")

    def test_trainer_and_full_party_do_not_capture(self):
        combat, _, team, _ = run('''Enlist "Bulbasaur".
Challenge "brock".
Capture.
''')
        self.assertEqual((team["result"], combat["active"]), ("trainer", 1))
        combat, _, team, _ = run('''Enlist "Bulbasaur".
Repeat 5 times:
  Enlist "Pidgey".
Confront "Pidgey" at 3.
Capture.
''')
        self.assertEqual((team["result"], combat["active"]), ("full", 1))

    def test_faint_sends_reserve_or_loses_when_none_remain(self):
        combat, ally, team, _ = run('''Enlist "Bulbasaur".
Confront "Caterpie" at 3.
Set Combat's foe's health to 1.
Capture.
Set Combat's ally's health to 0.
Set Combat's outcome to "fainted".
Replace.
''')
        self.assertEqual((team["result"], ally["species"], combat["active"]), ("replacement", "Caterpie", 1))
        self.assertEqual(combat["message"], "Caught Caterpie!")
        self.assertEqual(combat["later lines"], ("Go! Caterpie!",))
        combat, ally, team, _ = run('''Enlist "Bulbasaur".
Set Combat's ally's health to 0.
Set Combat's outcome to "fainted".
Replace.
''')
        self.assertEqual((team["result"], combat["outcome"]), ("loss", "loss"))
        self.assertGreater(ally["health"], 0)

    def test_fractional_and_out_of_range_slots_keep_the_selected_member(self):
        combat, ally, team, members = run('''Enlist "Bulbasaur".
Enlist "Pidgey".
Switch to 1.
Set Combat's ally's health to 7.
Switch to 1.5.
Set Combat's ally's health to 4.
Switch to 3.
''')
        self.assertEqual((team["selected"], team["notice"]), (1, "NO POKEMON"))
        self.assertEqual((members[0]["health"], ally["health"]), (4, 4))

    def test_replace_skips_selected_and_fainted_members_in_slot_order(self):
        _, ally, team, _ = run('''Enlist "Bulbasaur".
Enlist "Rattata".
Set Combat's ally's health to 0.
Enlist "Pidgey".
Enlist "Caterpie".
Switch to 1.
Replace.
''')
        self.assertEqual((team["selected"], team["result"], ally["species"]), (3, "replacement", "Pidgey"))

    def test_switch_rejects_fainted_member_without_resetting_stages(self):
        combat, ally, team, _ = run('''Enlist "Pidgey".
Set Combat's ally's health to 0.
Enlist "Bulbasaur".
Set Combat's ally's attack stage to 2.
Set Combat's ally's defense stage to -1.
Switch to 1.
''')
        self.assertEqual((team["selected"], team["notice"], ally["species"]), (2, "FAINTED", "Bulbasaur"))
        self.assertEqual((ally["attack stage"], ally["defense stage"]), (2, -1))

    def test_switching_in_calms_the_newcomer(self):
        _, ally, team, _ = run('''Enlist "Pidgey".
Set Combat's ally's attack stage to -3.
Now Combat's ally is seeded.
Enlist "Bulbasaur".
Switch to 1.
''')
        self.assertEqual((team["notice"], ally["species"], ally["attack stage"]), ("READY", "Pidgey", 0))

    def test_failed_capture_and_party_healing(self):
        combat, _, team, _ = run('''Enlist "Bulbasaur".
Confront "Kakuna" at 5.
Set Combat's seed to 1.
Capture.
''')
        self.assertEqual((team["result"], combat["active"]), ("escaped", 1))
        _, ally, _, members = run('''Enlist "Bulbasaur".
Confront "Caterpie" at 3.
Set Combat's foe's health to 1.
Capture.
Set Combat's ally's health to 1.
Set Combat's ally's status to "burned".
Switch to 2.
Set Combat's ally's health to 1.
Revive.
''')
        for member in members:
            self.assertEqual((member["health"], member["status"]), (member["maximum health"], ""))
        self.assertEqual(ally["species"], "Caterpie")


if __name__ == "__main__":
    unittest.main()

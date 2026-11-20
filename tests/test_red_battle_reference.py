import shutil
import tempfile
import unittest
from pathlib import Path

from englishscript import compile_file


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


class RedBattleReference(unittest.TestCase):
    def run_battle(self, source):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for chapter in RED.glob("*.english"):
                shutil.copy(chapter, root / chapter.name)
            (root / "main.english").write_text(
                'Use the battle chapter.\n' + source, encoding="utf-8"
            )
            world = compile_file(root / "main.english").run(out=lambda text="": None)
            return world.named["combat"].fields

    def test_brock_has_geodude_then_onix(self):
        first = self.run_battle('''Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "brock".
''')
        self.assertEqual((first["opponent"], first["enemy level"]), ("Geodude", 12))
        second = self.run_battle('''Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "brock".
Set Combat's enemy health to 1.
Set Combat's enemy speed to 0.
Fight "a".
''')
        self.assertEqual((second["opponent"], second["enemy level"]), ("Onix", 14))

    def test_brock_teaches_bide_to_onix(self):
        result = self.run_battle('''Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "brock".
Set Combat's enemy health to 1.
Set Combat's enemy speed to 0.
Fight "a".
Set Combat's seed to 2.
Respond.
''')
        self.assertEqual(result["message"], "Onix began to Bide!")
        self.assertGreater(result["bide"], 0)

    def test_brocks_geodude_does_not_use_bide(self):
        result = self.run_battle('''Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "brock".
Set Combat's seed to 2.
Respond.
''')
        self.assertEqual(result["bide"], 0)
        self.assertNotIn("Bide", result["message"])


    def test_full_heal_spends_brocks_turn_and_preserves_bide(self):
        result = self.run_battle('''Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "brock".
Set Combat's enemy status to "poisoned".
Set Combat's bide to 2.
Set Combat's stored damage to 4.
Respond.
''')
        self.assertEqual(result["enemy status"], "")
        self.assertEqual(result["full heals"], 4)
        self.assertEqual(result["message"], "Brock used Full Heal on Geodude!")
        self.assertEqual((result["bide"], result["stored damage"]), (2, 4))
        self.assertEqual(result["health"], result["maximum health"])

    def test_brock_has_five_heals_shared_across_his_team(self):
        result = self.run_battle('''Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "brock".
Set Combat's full heals to 1.
Set Combat's enemy status to "poisoned".
Respond.
Set Combat's enemy health to 1.
Set Combat's enemy speed to 0.
Fight "a".
Set Combat's enemy status to "poisoned".
Set Combat's seed to 2.
Respond.
''')
        self.assertEqual(result["opponent"], "Onix")
        self.assertEqual(result["full heals"], 0)
        self.assertEqual(result["enemy status"], "poisoned")
        self.assertEqual(result["message"], "Onix was hurt by poison!")

    def test_ember_burns_and_brock_uses_full_heal(self):
        result = self.run_battle('''Set Combat's starter to "Charmander".
Enlist.
Set Combat's level to 9.
Recalculate.
Heal.
Challenge "brock".
Set Combat's enemy speed to 0.
Set Combat's seed to 5.
Fight "right".
Fight "right".
Fight "a".
''')
        self.assertEqual(result["full heals"], 4)
        self.assertEqual(result["enemy status"], "")
        self.assertEqual(result["message"], "Brock used Full Heal on Geodude!")
        self.assertEqual(result["enemy attack"], 13)

    def test_poison_sting_can_prompt_brocks_full_heal(self):
        result = self.run_battle('''Set Combat's starter to "Weedle".
Enlist.
Challenge "brock".
Set Combat's enemy speed to 0.
Set Combat's seed to 5.
Fight "a".
''')
        self.assertEqual(result["full heals"], 4)
        self.assertEqual(result["enemy status"], "")
        self.assertEqual(result["message"], "Brock used Full Heal on Geodude!")

    def test_poison_hurts_after_enemy_turn_without_a_heal(self):
        result = self.run_battle('''Set Combat's starter to "Weedle".
Enlist.
Challenge "brock".
Set Combat's full heals to 0.
Set Combat's enemy speed to 0.
Set Combat's seed to 5.
Fight "a".
''')
        self.assertEqual(result["enemy status"], "poisoned")
        self.assertEqual(result["enemy health"], result["enemy maximum health"] - 3)
        self.assertEqual(result["message"], "Geodude was hurt by poison!")

    def test_ember_burn_damage_without_a_heal(self):
        result = self.run_battle('''Set Combat's starter to "Charmander".
Enlist.
Set Combat's level to 9.
Recalculate.
Heal.
Challenge "brock".
Set Combat's full heals to 0.
Set Combat's enemy speed to 0.
Set Combat's seed to 5.
Fight "right".
Fight "right".
Fight "a".
''')
        self.assertEqual(result["enemy status"], "burned")
        self.assertEqual(result["enemy attack"], 13)
        self.assertEqual(result["message"], "Geodude was hurt by its burn!")

    def test_poison_sting_does_not_poison_poison_types(self):
        result = self.run_battle('''Set Combat's starter to "Weedle".
Enlist.
Challenge "forest three".
Set Combat's enemy speed to 0.
Set Combat's seed to 5.
Fight "a".
''')
        self.assertEqual(result["enemy status"], "")

    def test_ember_does_not_burn_fire_types(self):
        result = self.run_battle('''Set Combat's starter to "Charmander".
Enlist.
Set Combat's level to 9.
Recalculate.
Heal.
Set Combat's original to "Bulbasaur".
Challenge "rival".
Set Combat's enemy speed to 0.
Set Combat's seed to 5.
Fight "right".
Fight "right".
Fight "a".
''')
        self.assertEqual(result["opponent"], "Charmander")
        self.assertEqual(result["enemy status"], "")

    def test_bide_unleashes_twice_the_stored_damage(self):
        result = self.run_battle('''Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "brock".
Set Combat's bide to 1.
Set Combat's stored damage to 4.
Respond.
''')
        self.assertEqual(result["health"], result["maximum health"] - 8)
        self.assertEqual(result["stored damage"], 0)
        self.assertEqual(result["message"], "Geodude unleashed Bide!")

    def test_bide_fails_with_no_stored_damage(self):
        result = self.run_battle('''Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "brock".
Set Combat's bide to 1.
Set Combat's stored damage to 0.
Respond.
''')
        self.assertEqual(result["message"], "Geodude's Bide failed!")
        self.assertEqual(result["health"], result["maximum health"])


if __name__ == "__main__":
    unittest.main()


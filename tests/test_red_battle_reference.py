import shutil
import tempfile
import unittest
from pathlib import Path

from englishscript import EnglishError, compile_file, compile_source


RED = Path(__file__).resolve().parents[1] / "docs" / "red"
PREAMBLE = "Use the foundation chapter.\nUse the battle chapter.\nLet the gap be \" / \".\n"


def run(source):
    output = []
    world = compile_source(PREAMBLE + source, folder=RED).run(out=output.append)
    if "The page, as it stands (there is no browser here to show it):" in output:
        output = output[:output.index("The page, as it stands (there is no browser here to show it):") - 1]
    return world, output


def sides(world):
    combat = world.named["combat"].fields
    return combat, combat["ally"].fields, combat["foe"].fields


def lines(combat):
    return [combat["message"], *combat["later lines"]]


def table(name, chapter="battle"):
    compiler = compile_file(RED / f"{chapter}.english").compiler
    return {key: row.values for key, row in compiler.fact_tables[name].rows.items()}


class RedBattleReference(unittest.TestCase):
    def test_unknown_starter_reports_missing_stats(self):
        with self.assertRaisesRegex(EnglishError, "No base stats for Missingmon"):
            run('Enlist "Missingmon".\n')

    def test_unknown_move_set_reports_species(self):
        with self.assertRaisesRegex(EnglishError, "No move set for Ivysaur"):
            run('Enlist "Ivysaur".\n')

    def test_unknown_move_reports_missing_capacity(self):
        with self.assertRaisesRegex(EnglishError, "No PP capacity for Mystery"):
            run('''Enlist "Bulbasaur".
Set item 1 of Combat's ally's moves to "Mystery".
Heal Combat's ally.
''')

    def test_unknown_attack_reports_missing_data(self):
        with self.assertRaisesRegex(EnglishError, "No battle data for Mystery"):
            run('''Enlist "Bulbasaur".
Confront "Pidgey" at 3.
Set Combat's foe's speed to 0.
Set item 1 of Combat's ally's moves to "Mystery".
Fight.
''')

    def test_enlisted_starter_knows_only_its_learned_moves(self):
        world, _ = run('Enlist "Bulbasaur".\n')
        _, ally, _ = sides(world)
        self.assertEqual(ally["moves"], ("Tackle", "Growl"))
        self.assertEqual(ally["pp"], (35, 40))
        self.assertEqual((ally["level"], ally["experience"], ally["status"]), (5, 135, ""))

    def test_missing_wild_encounter_names_the_place_and_slot(self):
        with self.assertRaisesRegex(EnglishError, r"No wild encounter for Missing Meadow in slot \d+"):
            run('Enlist "Squirtle".\nEncounter "Missing Meadow".\n')

    def test_pallet_town_grass_uses_its_local_encounter(self):
        world, _ = run('Enlist "Squirtle".\nEncounter "Pallet Town".\n')
        combat, _, foe = sides(world)
        self.assertEqual((foe["species"], foe["level"]), ("Pidgey", 3))
        self.assertEqual(combat["message"], "A wild Pidgey appeared!")

    def test_every_species_and_move_has_complete_data(self):
        stats = table("base stats")
        traits = table("species traits")
        moves = table("battle moves")
        types = table("species types", "matchups")
        lessons = table("lessons")
        self.assertEqual(set(stats), set(traits))
        self.assertEqual(set(stats), set(types))
        for key, (move, _) in lessons.items():
            with self.subTest(lesson=key):
                self.assertIn(move, moves)
        for move, (pp, power, kind, accuracy, effect, chance) in moves.items():
            with self.subTest(move=move):
                self.assertTrue(kind)
                self.assertTrue(0 < accuracy <= 255)
        for key, (species, level, trainer, taught) in table("trainer teams").items():
            with self.subTest(team=key):
                self.assertTrue(species == "rival starter" or species in stats)
                self.assertTrue(taught == "" or taught in moves)

    def test_trainer_teams_come_from_one_table(self):
        world, output = run('''Enlist "Squirtle".
Challenge "forest two".
Say Combat's foe's species.
Repeat 2 times:
  Set Combat's foe's health to 1.
  Set Combat's foe's speed to 0.
  Set Combat's seed to 0.
  Fight.
  Heal Combat's ally.
  Say Combat's foe's species.
Set Combat's foe's health to 1.
Set Combat's foe's speed to 0.
Set Combat's seed to 0.
Fight.
Say Combat's outcome.
''')
        self.assertEqual(output[:4], ["Weedle", "Kakuna", "Weedle", "win"])

    def test_brock_has_geodude_then_onix_who_knows_bide(self):
        world, _ = run('''Enlist "Bulbasaur".
Challenge "brock".
''')
        _, _, foe = sides(world)
        self.assertEqual((foe["species"], foe["level"]), ("Geodude", 12))
        self.assertEqual(foe["moves"], ("Tackle", "Defense Curl"))
        world, _ = run('''Enlist "Bulbasaur".
Challenge "brock".
Set Combat's foe's health to 1.
Set Combat's foe's speed to 0.
Set Combat's seed to 0.
Fight.
''')
        combat, _, foe = sides(world)
        self.assertEqual((foe["species"], foe["level"]), ("Onix", 14))
        self.assertEqual(foe["moves"], ("Tackle", "Screech", "Bide"))
        self.assertIn("BROCK sent out Onix!", lines(combat))

    def test_rival_sends_out_the_starter_story_chose(self):
        world, _ = run('''Enlist "Bulbasaur".
Set Journey's rival starter to "Charmander".
Challenge "rival".
''')
        self.assertEqual(sides(world)[2]["species"], "Charmander")
        with self.assertRaisesRegex(EnglishError, "The rival has not chosen a starter yet"):
            run('Enlist "Bulbasaur".\nChallenge "rival".\n')

    def test_opponent_chooses_from_its_move_set(self):
        _, output = run('''Enlist "Charmander".
Let the seed be 0.
Repeat 40 times:
  Confront "Weedle" at 5.
  Set Combat's seed to the seed.
  Respond.
  Say "{Combat's message}|{Combat's ally's status}|{Combat's ally's speed stage}".
  Heal Combat's ally.
  Calm Combat's ally.
  Add 1 to the seed.
''')
        used = {line.split("|")[0] for line in output}
        self.assertEqual(used, {"Weedle used Poison Sting!", "Weedle used String Shot!"})
        self.assertTrue(any(line.endswith("|poisoned|0") for line in output))
        self.assertTrue(any(line.endswith("||-1") for line in output))

    def test_opponent_thunder_wave_paralyzes_without_touching_stored_speed(self):
        _, output = run('''Enlist "Squirtle".
Say Combat's ally's speed.
Let the seed be 0.
Let the found be 0.
While the found is 0 and the seed is less than 256:
  Confront "Pikachu" at 9.
  Set Combat's seed to the seed.
  Respond.
  If Combat's ally's status is "paralyzed":
    Set the found to 1.
    Say Combat's ally's speed.
    Say Combat's message.
  Otherwise:
    Heal Combat's ally.
  Add 1 to the seed.
Heal Combat's ally.
Say Combat's ally's status.
''')
        self.assertEqual(output[0], output[1])
        self.assertEqual(output[2], "Pikachu used Thunder Wave!")
        self.assertEqual(output[3], "")

    def test_ground_types_cannot_be_paralyzed(self):
        world, output = run('''Enlist "Bulbasaur".
Let the seed be 0.
Let the found be 0.
While the found is 0 and the seed is less than 256:
  Confront "Pikachu" at 9.
  Set Combat's ally's species to "Diglett".
  Set Combat's seed to the seed.
  Respond.
  If Combat's message is "Pikachu used Thunder Wave!":
    Set the found to 1.
    Say Combat's later lines joined with the gap.
    Say Combat's ally's status.
  Add 1 to the seed.
''')
        self.assertEqual(output, ["But it failed!", ""])

    def test_player_poison_hurts_after_its_own_move(self):
        world, _ = run('''Enlist "Charmander".
Confront "Pidgey" at 3.
Set Combat's foe's health to 100.
Set Combat's foe's speed to 0.
Set Combat's ally's status to "poisoned".
Fight.
''')
        combat, ally, _ = sides(world)
        self.assertEqual(lines(combat)[:2], ["Charmander used Scratch!", "Charmander was hurt by poison!"])
        self.assertLess(ally["health"], ally["maximum health"])

    def test_both_turn_messages_are_kept_in_order(self):
        world, _ = run('''Enlist "Charmander".
Confront "Pidgey" at 3.
Set Combat's foe's speed to 0.
Set Combat's foe's health to 100.
Fight.
''')
        combat, _, _ = sides(world)
        self.assertEqual(combat["message"], "Charmander used Scratch!")
        self.assertEqual(combat["later lines"], ("Pidgey used Gust!",))
        world, _ = run('''Enlist "Charmander".
Confront "Pidgey" at 3.
Set Combat's foe's speed to 0.
Set Combat's foe's health to 100.
Fight.
Proceed with Combat.
''')
        combat, _, _ = sides(world)
        self.assertEqual((combat["message"], combat["later lines"]), ("Pidgey used Gust!", ()))

    def test_big_experience_gain_raises_several_levels_and_teaches(self):
        world, _ = run('''Enlist "Charmander".
Confront "Onix" at 40.
Set Combat's foe's health to 1.
Set Combat's foe's speed to 0.
Set Combat's seed to 0.
Fight.
''')
        combat, ally, _ = sides(world)
        self.assertEqual(ally["level"], 11)
        self.assertEqual(ally["moves"], ("Scratch", "Growl", "Ember"))
        self.assertEqual(ally["pp"][2], 25)
        self.assertIn("Charmander grew to level 6!", lines(combat))
        self.assertIn("Charmander grew to level 11!", lines(combat))
        self.assertEqual(combat["outcome"], "win")

    def test_levels_carry_evolution(self):
        world, _ = run('''Enlist "Caterpie".
Confront "Onix" at 60.
Set Combat's foe's health to 1.
Set Combat's foe's speed to 0.
Set Combat's seed to 0.
Fight.
''')
        combat, ally, _ = sides(world)
        self.assertEqual(ally["species"], "Butterfree")
        self.assertIn("Caterpie evolved into Metapod!", lines(combat))
        self.assertIn("Metapod evolved into Butterfree!", lines(combat))

    def test_double_knockout_sends_reinforcement_without_letting_it_act(self):
        world, _ = run('''Enlist "Bulbasaur".
Challenge "brock".
Set item 1 of Combat's ally's pp to 0.
Set item 2 of Combat's ally's pp to 0.
Set Combat's foe's health to 1.
Set Combat's ally's health to 1.
Set Combat's foe's speed to 0.
Fight.
''')
        combat, ally, foe = sides(world)
        self.assertEqual((combat["outcome"], combat["active"], ally["health"]), ("fainted", 0, 0))
        self.assertEqual((foe["species"], foe["health"]), ("Onix", foe["maximum health"]))
        self.assertEqual(lines(combat)[-2:], ["BROCK sent out Onix!", "Bulbasaur fainted!"])

    def test_double_knockout_against_the_last_pokemon_wins(self):
        world, _ = run('''Enlist "Bulbasaur".
Confront "Pidgey" at 3.
Set item 1 of Combat's ally's pp to 0.
Set item 2 of Combat's ally's pp to 0.
Set Combat's foe's health to 1.
Set Combat's ally's health to 1.
Set Combat's foe's speed to 0.
Fight.
''')
        combat, ally, _ = sides(world)
        self.assertEqual((combat["outcome"], ally["health"], ally["level"]), ("win", 0, 5))

    def test_accuracy_comes_from_the_move_table(self):
        _, output = run('''Enlist "Charmander".
Let the seed be 0.
Repeat 64 times:
  Confront "Spearow" at 15.
  Set Combat's seed to the seed.
  Respond.
  Say "{Combat's message}|{Combat's later lines joined with the gap}".
  Heal Combat's ally.
  Add 1 to the seed.
''')
        self.assertIn("Spearow used Fury Attack!|But it missed!", output)

    def test_string_shot_is_a_speed_stage_clamped_at_minus_six(self):
        world, _ = run('''Enlist "Caterpie".
Confront "Pidgey" at 3.
Repeat 12 times:
  Heal Combat's ally.
  Heal Combat's foe.
  Set Combat's choice to 2.
  Fight.
''')
        _, _, foe = sides(world)
        self.assertEqual(foe["speed stage"], -6)

    def test_burn_and_paralysis_are_worked_out_not_stored(self):
        world, output = run('''Enlist "Pikachu".
Set Combat's ally's status to "paralyzed".
Say Combat's ally's speed.
Confront "Pidgey" at 3.
Set Combat's foe's speed to 15.
Set Combat's foe's health to 100.
Fight.
Say Combat's message.
Set Combat's ally's status to "".
Say Combat's ally's speed.
''')
        self.assertEqual(output[0], output[2])
        self.assertTrue(output[1].startswith("Pidgey used"))

    def test_brock_full_heal_spends_his_turn_and_keeps_bide(self):
        world, _ = run('''Enlist "Bulbasaur".
Challenge "brock".
Set Combat's foe's status to "poisoned".
Set Combat's foe's bide turns to 2.
Set Combat's foe's stored damage to 4.
Respond.
''')
        combat, ally, foe = sides(world)
        self.assertEqual(foe["status"], "")
        self.assertEqual(combat["trainer full heals"], 4)
        self.assertEqual(combat["message"], "BROCK used Full Heal on Geodude!")
        self.assertEqual((foe["bide turns"], foe["stored damage"]), (2, 4))
        self.assertEqual(ally["health"], ally["maximum health"])

    def test_brock_has_five_heals_shared_across_his_team(self):
        world, _ = run('''Enlist "Bulbasaur".
Challenge "brock".
Set Combat's trainer full heals to 1.
Set Combat's foe's status to "poisoned".
Respond.
Set Combat's foe's health to 1.
Set Combat's foe's speed to 0.
Set Combat's seed to 0.
Fight.
Set Combat's foe's status to "poisoned".
Respond.
''')
        combat, _, foe = sides(world)
        self.assertEqual(foe["species"], "Onix")
        self.assertEqual(combat["trainer full heals"], 0)
        self.assertEqual(foe["status"], "poisoned")
        self.assertIn("Onix was hurt by poison!", lines(combat))

    def test_poison_sting_does_not_poison_poison_types(self):
        _, output = run('''Enlist "Weedle".
Let the seed be 0.
Repeat 64 times:
  Confront "Nidoran F" at 5.
  Set Combat's foe's speed to 0.
  Set Combat's seed to the seed.
  Fight.
  Say Combat's foe's status.
  Heal Combat's ally.
  Add 1 to the seed.
''')
        self.assertEqual(set(output), {""})

    def test_ember_can_burn_and_halves_worked_out_attack(self):
        _, output = run('''Enlist "Charmander".
Set Combat's ally's level to 9.
Recalculate Combat's ally.
Teach Combat's ally.
Heal Combat's ally.
Let the seed be 0.
Let the found be 0.
While the found is 0 and the seed is less than 256:
  Confront "Pidgey" at 3.
  Set Combat's foe's health to 100.
  Set Combat's foe's speed to 0.
  Set Combat's choice to 3.
  Set Combat's seed to the seed.
  Fight.
  If Combat's foe's status is "burned":
    Set the found to 1.
    Say Combat's foe's attack.
  Heal Combat's ally.
  Add 1 to the seed.
Say the found.
''')
        self.assertEqual(output[-1], "1")

    def test_bide_unleashes_twice_the_stored_damage(self):
        world, _ = run('''Enlist "Bulbasaur".
Challenge "brock".
Set Combat's foe's bide turns to 1.
Set Combat's foe's stored damage to 4.
Respond.
''')
        combat, ally, foe = sides(world)
        self.assertEqual(ally["health"], ally["maximum health"] - 8)
        self.assertEqual(foe["stored damage"], 0)
        self.assertEqual(combat["message"], "Geodude unleashed Bide!")

    def test_bide_fails_with_no_stored_damage(self):
        world, _ = run('''Enlist "Bulbasaur".
Challenge "brock".
Set Combat's foe's bide turns to 1.
Respond.
''')
        combat, ally, _ = sides(world)
        self.assertEqual(combat["message"], "Geodude's Bide failed!")
        self.assertEqual(ally["health"], ally["maximum health"])

    def test_bide_cannot_reduce_health_below_zero(self):
        world, _ = run('''Enlist "Bulbasaur".
Challenge "brock".
Set Combat's ally's health to 1.
Set Combat's foe's bide turns to 1.
Set Combat's foe's stored damage to 50.
Respond.
''')
        combat, ally, _ = sides(world)
        self.assertEqual((ally["health"], combat["outcome"]), (0, "fainted"))

    def test_onix_uses_bide_through_the_shared_move_path(self):
        _, output = run('''Enlist "Bulbasaur".
Let the seed be 0.
Let the found be 0.
While the found is 0 and the seed is less than 256:
  Challenge "brock".
  Set Combat's foe's health to 1.
  Set Combat's foe's speed to 0.
  Set Combat's seed to 0.
  Fight.
  Heal Combat's ally.
  Set Combat's seed to the seed.
  Respond.
  If Combat's foe is biding:
    Set the found to 1.
    Say Combat's message.
    Say Combat's later lines joined with the gap.
  Add 1 to the seed.
''')
        self.assertEqual(output, ["Onix used Bide!", "Onix began to Bide!"])

    def test_leech_seed_drains_the_seeded_side_after_its_move(self):
        world, _ = run('''Enlist "Bulbasaur".
Confront "Pidgey" at 3.
Set Combat's foe's health to 100.
Set Combat's foe's maximum health to 160.
Now Combat's foe is seeded.
Set Combat's ally's health to 10.
Respond.
''')
        combat, ally, foe = sides(world)
        self.assertIn("Leech Seed saps Pidgey!", lines(combat))
        self.assertEqual(foe["health"], 90)
        self.assertGreaterEqual(ally["health"], 10)


if __name__ == "__main__":
    unittest.main()

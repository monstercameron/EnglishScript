import shutil
import tempfile
import unittest
from pathlib import Path

from englishscript import compile_file


RED = Path(__file__).resolve().parents[1] / "docs" / "red"
BLACKOUT = "RED is out of usable POKEMON! RED blacked out!"


class RedStoryOutcomes(unittest.TestCase):
    def run_story(self, source):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for chapter in RED.glob("*.english"):
                shutil.copy(chapter, root / chapter.name)
            story = root / "story.english"
            story.write_text(story.read_text(encoding="utf-8").replace(
                "This chapter shares only advance and resolve.",
                "This chapter shares only advance, resolve, storybook, Story and choose."), encoding="utf-8")
            (root / "test.english").write_text(
                "Use the foundation chapter.\nUse the battle chapter.\nUse the story chapter.\n" + source,
                encoding="utf-8")
            world = compile_file(root / "test.english").run(out=lambda text="": None)
            return world.named["journey"].fields, world.named["story"].fields

    def finish_battle(self, challenger, outcome):
        return self.run_story(f'''Set Journey's place to "Pewter Gym".
Set Journey's wallet to 1000.
Set Story's challenger to "{challenger}".
Set Combat's outcome to "{outcome}".
Resolve.
''')

    def test_a_loss_speaks_only_the_blackout_and_sends_the_player_home(self):
        for challenger in ("wild", "brock", "gym trainer", "forest one", "forest two", "forest three"):
            with self.subTest(challenger=challenger):
                journey, story = self.finish_battle(challenger, "loss")
                self.assertEqual(journey["message"], BLACKOUT)
                self.assertEqual((journey["place"], journey["column"], journey["row"]), ("Home", 2, 6))
                self.assertEqual(journey["wallet"], 500)
                self.assertEqual(journey["badge"], 0)
                self.assertEqual(story["challenger"], "")

    def test_a_loss_leaves_the_forest_trainer_unbeaten(self):
        journey, story = self.finish_battle("forest two", "loss")
        self.assertNotIn("I give up", journey["message"])
        self.assertEqual(story["forest two beaten"], 0)

    def test_a_win_speaks_the_defeated_trainers_line(self):
        for challenger, beaten, line in (
            ("forest one", "forest one beaten", "BUG CATCHER: You're a POKEMON trainer too!"),
            ("forest two", "forest two beaten", "BUG CATCHER: I give up! You're good at this!"),
            ("forest three", "forest three beaten", "BUG CATCHER: No! Caterpie can't hack it!"),
            ("gym trainer", "gym trainer beaten", "GYM TRAINER: Darn! Light years isn't time, it measures distance!"),
        ):
            with self.subTest(challenger=challenger):
                journey, story = self.finish_battle(challenger, "win")
                self.assertEqual(journey["message"], line)
                self.assertEqual(story[beaten], 1)
                self.assertEqual(journey["place"], "Pewter Gym")

    def test_wild_win_is_announced(self):
        journey, _ = self.finish_battle("wild", "win")
        self.assertEqual(journey["message"], "The wild POKEMON fainted!")

    def test_route_rival_taunts_before_the_blackout(self):
        journey, story = self.finish_battle("route rival", "loss")
        self.assertEqual(journey["message"], "RIVAL: You have to work harder than that! " + BLACKOUT)
        self.assertEqual(story["route rival beaten"], 0)
        journey, story = self.finish_battle("route rival", "win")
        self.assertEqual(journey["message"], "RIVAL: What? I was just careless!")
        self.assertEqual((story["route rival beaten"], journey["route rival beaten"]), (1, 1))

    def test_losing_the_first_rival_battle_does_not_black_out(self):
        journey, _ = self.finish_battle("rival", "loss")
        self.assertEqual(journey["message"], "RIVAL: Yeah! Am I great or what?")
        self.assertEqual((journey["place"], journey["wallet"], journey["stage"]), ("Pewter Gym", 1000, "parcel"))

    def test_beating_brock_pays_the_prize_and_awards_the_badge(self):
        journey, story = self.finish_battle("brock", "win")
        self.assertEqual(journey["message"], "RED got 1,386 for winning!")
        self.assertEqual((journey["badge"], journey["wallet"]), (1, 2386))
        self.assertEqual(story["scene"], "brock cash")

    def test_choosing_without_a_matching_starter_enlists_nothing(self):
        journey, _ = self.run_story('''Set Journey's stage to "choose starter".
Set Journey's mode to starter.
Set Journey's selection to 7.
Choose.
''')
        self.assertEqual(journey["starter"], "")
        self.assertEqual(journey["stage"], "choose starter")
        self.assertEqual(journey["mode"], "walk")

    def test_choosing_a_starter_enlists_its_pair(self):
        journey, story = self.run_story('''Set Journey's stage to "choose starter".
Set Journey's selection to 1.
Choose.
''')
        self.assertEqual((journey["starter"], journey["rival starter"]), ("Charmander", "Squirtle"))
        self.assertEqual(story["scene"], "starter chosen")


if __name__ == "__main__":
    unittest.main()

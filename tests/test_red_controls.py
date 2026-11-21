import unittest
from pathlib import Path

from englishscript import compile_file, compile_source


RED = Path(__file__).resolve().parents[1] / "docs" / "red"
ACTIONS = ("tick", "a", "b", "start", "select", "up", "down", "left", "right")


def quiet(text=""):
    return None


class RedControlsWhileTalking(unittest.TestCase):
    def test_every_controller_action_is_dropped_while_talk_is_open(self):
        world = compile_file(RED / "main.english").run(out=quiet)
        journey = world.named["journey"].fields
        score = world.named["score"].fields
        controls = world.named["controls"].fields
        world.named["talk"].fields["phase"] = "composing"
        before = (dict(journey), dict(score))
        for action in ACTIONS:
            with self.subTest(action=action):
                world.event(lambda: controls.__setitem__("action", action))
                self.assertEqual(controls["action"], "")
                self.assertEqual((dict(journey), dict(score)), before)
        world.named["talk"].fields["phase"] = "closed"
        world.event(lambda: controls.__setitem__("action", "tick"))
        self.assertEqual(journey["animation"], before[0]["animation"] + 1)


class RedSoundCues(unittest.TestCase):
    def test_a_sound_marks_score_cued_until_the_next_step_clears_it(self):
        output = []
        compile_source("Use the sound chapter.\n"
                       "Now Score is not cued.\n"
                       "Say whether (Score is cued).\n"
                       "Sound \"item\".\n"
                       "Say whether (Score is cued).\n", folder=RED).run(out=output.append)
        self.assertEqual(output[:2], ["no", "yes"])

    def test_a_menu_move_sounds_select_only_when_no_other_cue_played(self):
        world = compile_file(RED / "main.english").run(out=quiet)
        journey = world.named["journey"].fields
        score = world.named["score"].fields
        controls = world.named["controls"].fields
        journey.update({"mode": "field menu", "place": "Pallet Town"})
        count = score["effect count"]
        world.event(lambda: controls.__setitem__("action", "down"))
        self.assertEqual((score["effect count"], score["effect"]), (count + 1, "84:1 96:1"))
        world.event(lambda: controls.__setitem__("action", "tick"))
        self.assertEqual(score["effect count"], count + 1)


if __name__ == "__main__":
    unittest.main()

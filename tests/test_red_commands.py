import shutil
import tempfile
import unittest
from pathlib import Path

from englishscript import EnglishError, compile_source


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


def run(source, folder=RED):
    output = []
    compile_source(source, folder=folder).run(out=output.append)
    return output


class RedCommands(unittest.TestCase):
    def test_misspelled_phase_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for chapter in RED.glob("*.english"):
                shutil.copy(chapter, root / chapter.name)
            commands = root / "commands.english"
            source = commands.read_text(encoding="utf-8")
            commands.write_text(source.replace("Set Orders's phase to moves.",
                                               "Set Orders's phase to movse."), encoding="utf-8")
            with self.assertRaisesRegex(EnglishError, 'Did you mean "moves"'):
                compile_source("Use the commands chapter.", folder=root)

    def test_command_and_move_menu_flow(self):
        output = run('''Use the commands chapter.
Use the battle chapter.
Enlist "Bulbasaur".
Confront "Pidgey" at 3.
Say Orders's phase.
Command "a".
Say Orders's phase.
Command "right".
Say Combat's choice.
Command "b".
Say Orders's phase.
Command "a".
Command "a".
Say Orders's phase.
Say Combat's turn.
''')
        self.assertEqual(output[:6], ["commands", "moves", "2", "commands", "commands", "1"])

    def test_old_keyboard_aliases_are_ignored(self):
        output = run('''Use the commands chapter.
Use the battle chapter.
Enlist "Bulbasaur".
Confront "Pidgey" at 3.
Command "z".
Command "enter".
Say Orders's phase.
''')
        self.assertEqual(output[0], "commands")

    def test_a_pages_through_both_turn_messages_before_the_menu_returns(self):
        output = run('''Use the commands chapter.
Use the battle chapter.
Enlist "Charmander".
Confront "Pidgey" at 3.
Set Combat's foe's health to 100.
Set Combat's foe's speed to 0.
Command "a".
Command "a".
Say Combat's message.
Say whether (Combat is reporting).
Command "down".
Say Orders's cursor.
Command "a".
Say Combat's message.
Say whether (Combat is reporting).
Command "a".
Say Orders's phase.
''')
        self.assertEqual(output[:6], ["Charmander used Scratch!", "yes", "1", "Pidgey used Gust!", "no", "moves"])

    def test_next_encounter_resets_the_cursor_after_running(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for chapter in RED.glob("*.english"):
                shutil.copy(chapter, root / chapter.name)
            story = root / "story.english"
            source = story.read_text(encoding="utf-8")
            story.write_text(source.replace("This chapter shares only advance and resolve.",
                                            "This chapter shares only advance, resolve, storybook, Story and engage."),
                             encoding="utf-8")
            output = run("""Use the foundation, commands, battle and story chapters.
Enlist "Bulbasaur".
Set Journey's rival starter to "Charmander".
Set Story's challenger to "rival".
Engage.
Command "right".
Command "down".
Command "a".
Say Combat's message.
Set Combat's outcome to "escaped".
Set Story's challenger to "rival".
Engage.
Say Orders's phase.
Say Orders's cursor.
""", folder=root)
            self.assertEqual(output[:3], ["No running from a trainer battle!", "commands", "1"])

    def test_running_from_a_wild_battle(self):
        output = run('''Use the commands chapter.
Use the battle chapter.
Enlist "Bulbasaur".
Confront "Pidgey" at 3.
Command "right".
Command "down".
Command "a".
Say Combat's outcome.
Say Combat's message.
''')
        self.assertEqual(output[:2], ["escaped", "Got away safely!"])


if __name__ == "__main__":
    unittest.main()

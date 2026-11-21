import unittest
from pathlib import Path

from englishscript import compile_source


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


def run(source):
    output = []
    compile_source("Use the foundation, battle, party and pack chapters.\n" + source, folder=RED).run(out=output.append)
    return output


class RedAntidote(unittest.TestCase):
    def test_antidote_cures_a_poisoned_ally(self):
        output = run('''Enlist "Bulbasaur".
Set Stock's antidotes to 1.
Set Combat's ally's status to "poisoned".
Set Journey's mode to bag.
Set Stock's cursor to 2.
Inventory "a".
Say Combat's ally's status.
Say Stock's antidotes.
Say Stock's notice.
''')
        self.assertEqual(output[:3], ["", "0", "POISON CURED"])

    def test_antidote_is_kept_when_there_is_no_poison(self):
        output = run('''Enlist "Bulbasaur".
Set Stock's antidotes to 1.
Set Journey's mode to bag.
Set Stock's cursor to 2.
Inventory "a".
Say Stock's antidotes.
Say Stock's notice.
''')
        self.assertEqual(output[:2], ["1", "NO POISON TO CURE"])


if __name__ == "__main__":
    unittest.main()

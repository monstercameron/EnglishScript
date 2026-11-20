import unittest

from englishscript import EnglishError, compile_source, lint


class ExceptAssignments(unittest.TestCase):
    def output(self, source):
        values = []
        compile_source(source).run(out=values.append)
        return values

    def test_first_eligible_branch_and_original_base(self):
        self.assertEqual(self.output('''Let score be 0.
Set score to 10, except:
    Use 99 for 10 when score is more than 0.
    Use 20 for 10 when score is at least 0.
    Use 30 for 10 when score is at least 0.
    Use 40 for 20.
Say score.
'''), ['20'])

    def test_unmatched_base_and_lazy_guard_and_result(self):
        self.assertEqual(self.output('''Let score be 0.
Set score to 2, except:
    Use 1 / 0 for 3 when 1 / 0 is 0.
    Use 1 / 0 for 2 when score is 1.
Say score.
'''), ['2'])

    def test_list_item_uses_normal_setter(self):
        self.assertEqual(self.output('''Let scores be a list of 1 and 2.
Set item 1 of scores to 1, except:
    Use 7 for 1.
Say item 1 of scores.
'''), ['7'])

    def test_branch_type_and_position(self):
        source = 'Let score be 0.\nSet score to 2, except:\n    Use "bad" for 2.\n'
        with self.assertRaises(EnglishError) as caught:
            compile_source(source)
        self.assertEqual(caught.exception.line.number, 3)
        self.assertEqual(caught.exception.col, 8)
        self.assertIn('text', str(caught.exception))
        self.assertTrue(any(p.line == 3 and p.col == 8 for p in lint(source) if p.kind == 'error'))

    def test_key_type_and_unknown_target(self):
        for source, expected in [
            ('Let score be 0.\nSet score to 2, except:\n    Use 3 for "two".\n', "compare"),
            ('Set unknown to 2, except:\n    Use 3 for 2.\n', "unknown"),
        ]:
            with self.subTest(source=source), self.assertRaises(EnglishError) as caught:
                compile_source(source)
            self.assertIn(expected, str(caught.exception).lower())

    def test_rules_are_checked_only_for_selected_value(self):
        source = """A cat has an age (number).
A cat's age is never more than 5.
There is a cat called Tom whose age is 1.
Set Tom's age to 8, except:
    Use 3 for 8.
Say Tom's age.
"""
        self.assertEqual(self.output(source), ['3'])
        with self.assertRaises(EnglishError) as caught:
            self.output(source.replace('Use 3 for 8.', 'Use 7 for 8.'))
        self.assertIn('break a rule', str(caught.exception))

    def test_kept_and_outside_workout_targets_are_rejected(self):
        sources = [
            ("A cat has an age (number).\nThere is a cat called Tom whose age is 1.\n"
             "Keep Tom's age as 1.\nSet Tom's age to 2, except:\n    Use 3 for 2.\n", 'kept in step'),
            ("Let score be 0.\nTo work out the outcome (number):\n"
             "    Set score to 1, except:\n        Use 2 for 1.\n    The answer is score.\n", "can't change"),
        ]
        for source, message in sources:
            with self.subTest(message=message), self.assertRaises(EnglishError) as caught:
                compile_source(source)
            self.assertIn(message, str(caught.exception))

    def test_frozen_target_is_rejected(self):
        with self.assertRaises(EnglishError) as caught:
            compile_source('Let score always be 0.\nSet score to 1, except:\n    Use 2 for 1.\n')
        self.assertIn('always', str(caught.exception))


if __name__ == '__main__':
    unittest.main()


import asyncio
import unittest

from englishscript import EnglishError, compile_source


def run(source):
    output = []
    compile_source(source).run(output.append)
    return output


class GroupedActions(unittest.TestCase):
    def test_dispatch_is_exact_lazy_and_has_no_fallthrough(self):
        source = '''Let word be "B".
Depending on word:
  For "A" or "B":
    Say "match".
  For "C":
    Say 1 / 0.
  Otherwise:
    Say 1 / 0.
Say "after".
'''
        self.assertEqual(run(source), ["match", "after"])
        self.assertEqual(run('''Depending on "a":
  For "A":
    Say "wrong".
Say "after".
'''), ["after"])

    def test_subject_evaluated_once(self):
        source = '''To work out the next word (text):
  The answer is "B".
Depending on the next word:
  For "A":
    Say "wrong".
  For "B":
    Say "match".
'''
        seen, output = [], []
        compile_source(source).run(output.append, trace=lambda *entry: seen.append(entry[2]))
        self.assertEqual(output, ["match"])
        self.assertEqual(seen.count(2), 1)

    def test_named_choices_and_mandatory_answer(self):
        source = '''A mood is one of sleepy or happy.
To work out the label (text) of a feeling (mood):
  Depending on the feeling:
    For sleepy:
      The answer is "rest".
    For happy:
      The answer is "play".
Say the label of happy.
'''
        self.assertEqual(run(source), ["play"])
        with self.assertRaises(EnglishError):
            compile_source(source.replace('    For happy:\n      The answer is "play".\n', ''))
        with self.assertRaises(EnglishError):
            compile_source('''To work out the label (text) of a word (text):
  Depending on the word:
    For "A":
      The answer is "yes".
''')

    def test_loop_and_nested_blocks(self):
        source = '''Repeat 3 times:
  Depending on "A":
    For "A":
      If 1 is 1:
        Say "once".
        Stop repeating.
Say "done".
'''
        self.assertEqual(run(source), ["once", "done"])

    def test_default_return_and_local_scope(self):
        source = '''To work out the label (text) of a word (text):
  Depending on the word:
    For "A":
      Let result be "yes".
      The answer is result.
    Otherwise:
      Let result be "other".
      The answer is result.
Say the label of "B".
'''
        self.assertEqual(run(source), ["other"])
        with self.assertRaises(EnglishError):
            compile_source('''Depending on "A":
  For "A":
    Let local be "yes".
Say local.
''')

    def test_invalid_rows(self):
        head = 'Depending on "A":\n'
        for rows, message in [
            ('  For "A" or "A":\n    Say 1.\n', 'twice'),
            ('  For "A":\n    Say 1.\n  For "A":\n    Say 2.\n', 'twice'),
            ('  Otherwise:\n    Say 1.\n  Otherwise:\n    Say 2.\n', 'Only one'),
            ('  Otherwise:\n    Say 1.\n  For "A":\n    Say 2.\n', 'last row'),
            ('  For sleepy:\n    Say 1.\n', 'choice'),
        ]:
            with self.subTest(rows=rows), self.assertRaisesRegex(EnglishError, message):
                compile_source(head + rows)
        with self.assertRaisesRegex(EnglishError, 'subject'):
            compile_source('A mood is one of sleepy or happy.\n' + head + '  For sleepy:\n    Say 1.\n')
        with self.assertRaisesRegex(EnglishError, 'text or a set'):
            compile_source('Depending on 1:\n  For "1":\n    Say 1.\n')

    def test_existing_verb_remains_available(self):
        self.assertEqual(run('''To depending on a word (text):
  Say the word.
Depending on "hello".
'''), ["hello"])

    def test_nested_async_model_matches_if(self):
        async def model(*args):
            return "reply"

        for head, indent in [("If 1 is 1:", "  "),
                             ('Depending on "A":\n  For "A":', "    ")]:
            source = head + '\n' + indent + 'Ask the model "Q" and let the t (text) be the reply.\n'
            with self.subTest(head=head), self.assertRaisesRegex(EnglishError, 'Only a top-level model question'):
                asyncio.run(compile_source(source).run_async(model=model))


if __name__ == "__main__":
    unittest.main()

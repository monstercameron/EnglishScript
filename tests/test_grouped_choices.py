import unittest

from englishscript import EnglishError, compile_source


def run(source):
    output = []
    compile_source(source).run(output.append)
    return output


class GroupedChoices(unittest.TestCase):
    def test_text_exact_and_lazy(self):
        source = '''To work out the label (number) of a word (text):
  Choose the answer by the word:
    For "A", "B" or "C", use 4.
    Otherwise, use 1 / 0.
Say the label of "B".
'''
        self.assertEqual(run(source), ["4"])
        with self.assertRaises(EnglishError):
            run(source.replace('of "B".', 'of "b".'))

    def test_closed_choice_and_nested_return(self):
        source = '''A mood is one of very cross, sleepy or happy.
To work out the label (text) of a feeling (mood):
  If the feeling is not happy:
    Choose the answer by the feeling:
      For very cross or sleepy, use "rest".
      For happy, use "play".
  Otherwise:
    The answer is "joy".
Say the label of sleepy.
Say the label of happy.
'''
        self.assertEqual(run(source), ["rest", "joy"])
        with self.assertRaisesRegex(EnglishError, "happy"):
            compile_source(source.replace('      For happy, use "play".\n', ''))

    def test_required_otherwise_duplicates_and_types(self):
        head = 'To work out the label (text) of a word (text):\n  Choose the answer by the word:\n'
        with self.assertRaisesRegex(EnglishError, 'Otherwise'):
            compile_source(head + '    For "A", use "yes".\n')
        with self.assertRaisesRegex(EnglishError, 'twice'):
            compile_source(head + '    For "A" or "A", use "yes".\n    Otherwise, use "no".\n')
        with self.assertRaisesRegex(EnglishError, 'twice'):
            compile_source(head + '    For "A", use "yes".\n    For "A", use "no".\n    Otherwise, use "no".\n')
        with self.assertRaises(EnglishError):
            compile_source(head + '    For "A", use 3.\n    Otherwise, use "no".\n')
        with self.assertRaises(EnglishError):
            compile_source('A mood is one of sleepy or happy.\n' + head + '    For sleepy, use "yes".\n    Otherwise, use "no".\n')

    def test_membership_and_outer_or(self):
        source = '''Let word be "A".
If word is one of "A" or "B" or word is "C":
  Say "yes".
If word is not one of "a" or "b":
  Say "exact".
'''
        self.assertEqual(run(source), ["yes", "exact"])
        self.assertEqual(run(source.replace('be "A"', 'be "C"')), ["yes", "exact"])

    def test_literal_quotes_and_fill_ins(self):
        source = '''To work out the label (text) of a word (text):
  Choose the answer by the word:
    For "say ""hi""", use "matched".
    Otherwise, use "other".
Say the label of "say ""hi""".
If "say ""hi""" is one of "say ""hi""", "other":
  Say "member".
'''
        self.assertEqual(run(source), ["matched", "member"])
        with self.assertRaisesRegex(EnglishError, "grouped choice must be literal text"):
            compile_source(source.replace('For "say ""hi"""', 'For "{the word}"'))

    def test_first_repeated_option_is_reported(self):
        source = '''To work out the label (text) of a word (text):
  Choose the answer by the word:
    For "A" or "B", use "first".
    For "B" or "A", use "second".
    Otherwise, use "other".
'''
        with self.assertRaisesRegex(EnglishError, '"B" is listed twice'):
            compile_source(source)

    def test_use_is_reserved_as_a_choice_name(self):
        with self.assertRaisesRegex(EnglishError, 'already has a meaning'):
            compile_source('A task is one of use or rest.\n')

    def test_choice_membership_and_ordinary_verb(self):
        source = '''A mood is one of very cross, sleepy or happy.
To choose a word (text):
  Say the word.
Choose "hello".
Let feeling be very cross.
If feeling is one of very cross or sleepy:
  Say "rest".
'''
        self.assertEqual(run(source), ["hello", "rest"])


if __name__ == "__main__":
    unittest.main()

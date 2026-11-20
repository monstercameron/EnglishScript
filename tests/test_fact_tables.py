from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from englishscript.compiler import compile_source
from englishscript.lexer import EnglishError


class FactTableTests(unittest.TestCase):
    def run_source(self, source, **kwargs):
        output = []
        compile_source(source, **kwargs).run(out=output.append)
        return output

    def test_typed_columns_exact_lookup_and_fallback(self):
        source = '''The base stats are health, category and speed, in that order:
  "Nidoran M" has 46, "poison" and 50.
  "Nidoran F" has 55, "poison" and 41.
Let the stats be the base stats for "Nidoran M".
Say the stats's health or else 0.
Say the stats's category or else "unknown".
Let the missing be the base stats for "nidoran m".
Say the missing's speed or else 99.
'''
        self.assertEqual(self.run_source(source), ["46", "poison", "99"])

    def test_invalid_rows(self):
        heading = 'The records are score and label, in that order:\n'
        for rows, message in [
            ('  "a" has 1.\n', '1 value'),
            ('  "a" has 1 and "x".\n  "a" has 2 and "y".\n', 'listed twice'),
            ('  "a" has 1 and "x".\n  "b" has "two" and "y".\n', 'column needs number'),
            ('  "a" has 1 and 2 + 3.\n', 'Separate values'),
        ]:
            with self.subTest(rows=rows), self.assertRaises(EnglishError) as caught:
                compile_source(heading + rows)
            self.assertIn(message, str(caught.exception))

    def test_threshold_rows_and_named_fields(self):
        source = '''The evolutions are voice and story, in that order:
  "Nidoran M" from 32 has "second" and "later".
  "Nidoran M" from 16 has:
    Story is "first story".
    Voice is "first".
  "Nidoran M" from 16.5 has "middle" and "next".
  "Other" from -1 has "other" and "story".
Let the low be the evolutions for "Nidoran M" at 15.
Let the first be the evolutions for "Nidoran M" at 16.
Let the middle be the evolutions for "Nidoran M" at 16.5.
Let the high be the evolutions for "Nidoran M" at 99.
Let the unknown be the evolutions for "missing" at 99.
Say the low's voice or else "none".
Say the first's story or else "none".
Say the middle's voice or else "none".
Say the high's voice or else "none".
Say the unknown's voice or else "none".
'''
        self.assertEqual(self.run_source(source), ["none", "first story", "middle", "second", "none"])

    def test_named_rows_and_outer_at(self):
        source = '''The records are voice and story, in that order:
  "Oak" has:
    Story is "tale".
    Voice is "hello".
To work out the chosen (number) for a label (text) at a level (number):
  The answer is the level.
Say the chosen for (the voice of the records for "Oak" or else "") at 7.
'''
        self.assertEqual(self.run_source(source), ["7"])
        threshold = source.replace('"Oak" has:', '"Oak" from 3 has:').replace(
            'the records for "Oak" or else', 'the records for "Oak" at 3 or else')
        self.assertEqual(self.run_source(threshold), ["7"])

    def test_invalid_new_rows_and_lookups(self):
        heading = 'The records are voice and story, in that order:\n'
        cases = [
            ('  "a" from 1 has "x" and "y".\n  "a" from 1.0 has "x" and "z".\n', 'listed twice'),
            ('  "a" from 1 has "x" and "y".\n  "b" has "x" and "y".\n', 'cannot mix'),
            ('  "a" has "x" and "y".\n  "b" from 1 has "x" and "y".\n', 'cannot mix'),
            ('  "a" from has "x" and "y".\n', 'literal number'),
            ('  "a" has:\n    Voice is "x".\n', 'missing'),
            ('  "a" has:\n    Voice is "x".\n    Voice is "y".\n', 'listed twice'),
            ('  "a" has:\n    Other is "x".\n    Story is "y".\n', 'not declared'),
            ('  "a" has:\n    Voice is "{name}".\n    Story is "y".\n', 'without fill-ins'),
            ('  "a" has "x" and "y".\n  "b" has:\n    Voice is 2.\n    Story is "y".\n', 'column needs text'),
            ('  "a" from 1 has "x" and "y".\nSay the records for "a".\n', 'needs "at"'),
            ('  "a" from 1 has "x" and "y".\nSay the records for "a" at "high".\n', 'must be a number'),
        ]
        for rows, message in cases:
            with self.subTest(rows=rows), self.assertRaises(EnglishError) as caught:
                compile_source(heading + rows)
            self.assertIn(message, str(caught.exception))

    def test_fact_columns_cannot_be_changed(self):
        source = '''The records are score, in that order:
  "a" has 1.
Let the row be the records for "a".
If the row is not nothing:
  Set the row's score to 3.
'''
        with self.assertRaises(EnglishError):
            compile_source(source)

    def test_name_column_and_interpolation(self):
        source = """The records are label and score, in that order:
  \"a\" has \"visible\" and 2.
Let the row be the records for \"a\".
If the row is not nothing:
  Say the row's label.
  Say the row's name.
  Say \"{the row}: {the row's score}\".
"""
        self.assertEqual(self.run_source(source), ['visible', 'a', 'a: 2'])

    def test_removing_row_is_refused(self):
        source = """The records are score, in that order:
  \"a\" has 1.
Let the row be the records for \"a\".
If the row is not nothing:
  Remove the row.
"""
        with self.assertRaises(EnglishError) as caught:
            compile_source(source)
        self.assertIn('cannot be removed', str(caught.exception))

    def test_name_collisions_are_refused(self):
        source = """The records are score, in that order:
  \"a\" has 1.
Let the records be 2.
"""
        with self.assertRaises(EnglishError):
            compile_source(source)

    def test_shared_chapter_name_collision(self):
        with TemporaryDirectory() as folder:
            Path(folder, 'catalog.english').write_text("""The records are score, in that order:
  \"a\" has 1.
""", encoding='utf8')
            source = """Let the records be 2.
Use the catalog chapter.
"""
            with self.assertRaises(EnglishError):
                compile_source(source, folder=folder)

    def test_shared_chapter(self):
        with TemporaryDirectory() as folder:
            Path(folder, 'catalog.english').write_text('''This chapter shares only records.
The records are score and label, in that order:
  "a" has 1 and "first".
''', encoding='utf8')
            source = '''Use the catalog chapter.
Let the row be the records for "a".
Say the row's label or else "missing".
'''
            self.assertEqual(self.run_source(source, folder=folder), ['first'])


if __name__ == '__main__':
    unittest.main()

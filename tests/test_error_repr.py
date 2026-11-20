import unittest

from englishscript.lexer import EnglishError, Line


class ErrorRepresentation(unittest.TestCase):
    def test_line_representation_does_not_expand_the_rest_of_the_program(self):
        first = Line(1, "If true:", 0)
        current = first
        for number in range(2, 202):
            following = Line(number, "If true:", number)
            current.children.append(following)
            current.after = following
            current = following
        error = EnglishError("Bad sentence", first, 1)
        self.assertLess(len(repr(vars(error))), 2000)
        self.assertLess(len(repr(error.line)), 1000)


if __name__ == "__main__":
    unittest.main()

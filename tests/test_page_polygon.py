import unittest
from fractions import Fraction

from englishscript import compile_source
from englishscript.lexer import EnglishError
from englishscript.libraries import page


class CanvasPolygons(unittest.TestCase):
    def setUp(self):
        self.world = compile_source('Use the page library.\nThere is a canvas called Screen whose width is 8 and whose height is 8.\n').run(out=lambda *_: None)
        self.screen = self.world.named['screen']

    def pixels(self):
        return {(x, y) for y in range(8) for x in range(8)
                if page.value_pixel(self.world, self.screen, x, y) == 3}

    def test_english_triangle(self):
        source = '''Use the page library.
There is a canvas called Screen whose width is 9 and whose height is 7.
Let the vertices be a list of 0, 0, 8, 0, 4 and 6.
Shade Screen at 0 by 0 with the vertices as 3.
'''
        world = compile_source(source).run(out=lambda *_: None)
        screen = world.named['screen']
        self.assertEqual(page.value_pixel(world, screen, 4, 6), 3)
        self.assertEqual(page.value_pixel(world, screen, 0, 6), 0)

    def test_concave_winding_and_translation(self):
        vertices = [0, 0, 4, 0, 4, 2, 2, 2, 2, 4, 0, 4]
        page.verb_shade(self.world, self.screen, 1, 1, vertices, 3)
        expected = {(x, y) for y in range(1, 6) for x in range(1, 6)
                    if y <= 3 or x <= 3}
        self.assertEqual(self.pixels(), expected)
        page.verb_fill(self.world, self.screen, 0, 0, 8, 8, 0)
        reversed_vertices = [v for p in reversed(list(zip(vertices[::2], vertices[1::2]))) for v in p]
        page.verb_shade(self.world, self.screen, 2, 2, [v - 1 for v in reversed_vertices], 3)
        self.assertEqual(self.pixels(), expected)

    def test_horizontal_and_degenerate_edges(self):
        page.verb_shade(self.world, self.screen, 0, 0, [1, 2, 5, 2, 3, 2], 3)
        self.assertEqual(self.pixels(), {(x, 2) for x in range(1, 6)})
        page.verb_shade(self.world, self.screen, 0, 0, [7, 7, 7, 7, 7, 7], 3)
        self.assertIn((7, 7), self.pixels())

    def test_invalid_input_does_not_change_pixels(self):
        page.verb_paint(self.world, self.screen, 0, 0, 3)
        before = self.pixels()
        cases = [(0, 0, [], 3), (0, 0, [0, 0, 1, 1, 2], 3),
                 (Fraction(1, 2), 0, [0, 0, 1, 0, 0, 1], 3),
                 (0, 0, [0, 0, 1, 0, Fraction(1, 2), 1], 3),
                 (0, 0, [0, 0, 1, 0, -1, 1], 3),
                 (0, 0, [0, 0, 1, 0, 8, 1], 3),
                 (0, 0, [0, 0, 1, 0, 0, 1], 4)]
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(EnglishError):
                    page.verb_shade(self.world, self.screen, *args)
                self.assertEqual(self.pixels(), before)


if __name__ == '__main__':
    unittest.main()

import asyncio
import unittest
from fractions import Fraction

from englishscript import compile_source
from englishscript.lexer import EnglishError
from englishscript.libraries import page


class CanvasLines(unittest.TestCase):
    def test_english_line_reaches_remote_canvas(self):
        frames = []
        source = '''Use the page library.
There is a canvas called Screen whose width is 5 and whose height is 4.
Trace Screen from 0 by 0 to 4 at 2 with 3.
'''
        world = asyncio.run(compile_source(source).run_async(
            out=lambda *_: None,
            on_world=lambda world: page.use_remote_canvas(world, lambda *frame: frames.append(frame))))
        page.sync(world)
        self.assertEqual(frames[-1][4], bytes((3, 0, 0, 0, 0, 0, 3, 3, 0, 0, 0, 0, 0, 3, 3, 0, 0, 0, 0, 0)))

    def test_axes_diagonals_and_single_point(self):
        source = 'Use the page library.\nThere is a canvas called Screen whose width is 5 and whose height is 5.\n'
        world = compile_source(source).run(out=lambda *_: None)
        screen = world.named['screen']
        cases = [((0, 2, 4, 2), {(x, 2) for x in range(5)}),
                 ((2, 4, 2, 0), {(2, y) for y in range(5)}),
                 ((0, 0, 4, 4), {(i, i) for i in range(5)}),
                 ((4, 0, 0, 4), {(4-i, i) for i in range(5)}),
                 ((1, 1, 2, 4), {(1, 1), (1, 2), (2, 3), (2, 4)}),
                 ((3, 3, 3, 3), {(3, 3)})]
        for endpoints, expected in cases:
            with self.subTest(endpoints=endpoints):
                page.verb_fill(world, screen, 0, 0, 5, 5, 0)
                page.verb_trace(world, screen, *endpoints, 2)
                actual = {(x, y) for y in range(5) for x in range(5)
                          if page.value_pixel(world, screen, x, y) == 2}
                self.assertEqual(actual, expected)

    def test_invalid_arguments_leave_pixels_unchanged(self):
        world = compile_source('Use the page library.\nThere is a canvas called Screen whose width is 3 and whose height is 3.\n').run(out=lambda *_: None)
        screen = world.named['screen']
        for args in [(-1, 0, 2, 2, 1), (0, 3, 2, 2, 1), (0, 0, 3, 2, 1),
                     (0, 0, 2, Fraction(1, 2), 1), (0, 0, 2, 2, 4)]:
            with self.subTest(args=args), self.assertRaises(EnglishError):
                page.verb_trace(world, screen, *args)
            self.assertEqual(bytes(page._canvas(page._state(world), screen)['pixels']), bytes(9))


if __name__ == '__main__':
    unittest.main()

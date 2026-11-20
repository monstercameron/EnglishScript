"""The example programs that exercise arithmetic, text and classic algorithms.

Each one checks itself with "For example" sentences, so running it is already a
test. These tests also compare what it says with an answer worked out in
Python, so that a program cannot pass by agreeing only with itself.
"""
import math
import unittest
from pathlib import Path

from englishscript import compile_source, lint

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def said(name):
    """Everything the example says, as a list of lines, and how many examples it checked."""
    source = (EXAMPLES / f"{name}.english").read_text(encoding="utf-8")
    lines = []
    world = compile_source(source).run(out=lambda text="": lines.append(str(text)))
    return lines, world.examples


class Algorithms(unittest.TestCase):
    def test_every_one_is_free_of_lint(self):
        for name in ("primes", "euclid", "fibonacci", "roots", "sorting", "hanoi",
                     "collatz", "caesar", "roman", "bank", "life"):
            with self.subTest(name):
                source = (EXAMPLES / f"{name}.english").read_text(encoding="utf-8")
                self.assertEqual([p.render() for p in lint(source)], [])

    def test_primes(self):
        lines, checked = said("primes")
        primes = [n for n in range(2, 61) if all(n % d for d in range(2, n))]
        self.assertEqual(lines[0], "Primes to 60: " + ", ".join(map(str, primes)) + ".")
        self.assertIn("360 = 2 x 2 x 2 x 3 x 3 x 5", lines)
        self.assertIn("1,001 = 7 x 11 x 13", lines)
        perfect = [n for n in range(2, 501) if sum(d for d in range(1, n) if n % d == 0) == n]
        self.assertEqual([line for line in lines if line.endswith("is perfect.")],
                         [f"{n} is perfect." for n in perfect])
        self.assertGreaterEqual(checked, 5)

    def test_euclid(self):
        lines, checked = said("euclid")
        self.assertEqual(lines[0], f"The greatest number dividing 1,071 and 462 is {math.gcd(1071, 462)}.")
        self.assertEqual(lines[1], f"By halving, it is {math.gcd(1071, 462)}.")
        self.assertIn(f"The least number that 21 and 6 both divide is {math.lcm(21, 6)}.", lines)
        self.assertIn("462/1,071 in lowest terms is 22/51.", lines)
        self.assertGreaterEqual(checked, 7)

    def test_fibonacci(self):
        lines, _ = said("fibonacci")
        fib = [0, 1]
        while len(fib) < 101:
            fib.append(fib[-1] + fib[-2])
        self.assertEqual(lines[0], "The first fifteen: " + " ".join(map(str, fib[1:16])) + " ")
        self.assertEqual(lines[1], f"The hundredth: {fib[100]:,}")
        even = sum(n for n in fib if n < 4_000_000 and n % 2 == 0)
        self.assertEqual(lines[3], f"The even ones below four million add up to {even:,}.")

    def test_roots_and_pi(self):
        lines, _ = said("roots")
        self.assertEqual(lines[0], "The square root of 2 is about 1.4142.")
        self.assertEqual(lines[1], f"Its first thirty-one digits: {math.isqrt(2 * 10 ** 60):,}")
        self.assertEqual(lines[2], "Pi is about 3.1416.")

    def test_sorting_and_searching(self):
        lines, _ = said("sorting")
        row = [42, 7, 93, 18, 61, 3, 77, 25]
        self.assertEqual(lines[0], "Before: " + " ".join(map(str, row)))
        self.assertEqual(lines[1], "After:  " + " ".join(map(str, sorted(row))))
        # A sort that only swaps neighbours makes one swap for each pair out of order.
        pairs = sum(1 for i in range(len(row)) for j in range(i + 1, len(row)) if row[i] > row[j])
        self.assertEqual(lines[2], f"That took {pairs} swaps.")
        self.assertEqual(lines[3], f"61 is in place {sorted(row).index(61) + 1}.")
        self.assertEqual(lines[4], "And 50? nothing.")

    def test_hanoi(self):
        lines, _ = said("hanoi")
        moves = [line for line in lines if " goes from " in line]
        self.assertEqual(len(moves), 2 ** 4 - 1)
        # Play the moves: a disc may only land on a bigger one.
        pegs = {"Oak": [4, 3, 2, 1], "Ash": [], "Elm": []}
        for line in moves:
            words = line.rstrip(".").split()
            disc, source, target = int(words[2]), words[5], words[7]
            self.assertEqual(pegs[source].pop(), disc, line)
            self.assertTrue(not pegs[target] or pegs[target][-1] > disc, line)
            pegs[target].append(disc)
        self.assertEqual([peg for peg, discs in pegs.items() if discs], [words[7]])
        self.assertIn(f"{2 ** 64 - 1:,} moves", lines[-1])

    def test_collatz(self):
        lines, _ = said("collatz")

        def flight(n):
            steps = 0
            while n != 1:
                n = n // 2 if n % 2 == 0 else 3 * n + 1
                steps += 1
            return steps
        best = max(range(1, 30), key=flight)
        self.assertEqual(lines[0], f"Below 30, the longest flight is {flight(best)} steps, from {best}.")
        self.assertEqual(lines[1], "On the way, 27 climbs as high as 9,232.")

    def test_caesar_and_palindromes(self):
        lines, _ = said("caesar")
        plain = "Attack at dawn, by the old bridge!"

        def shift(text, by):
            return "".join(chr((ord(c) - 97 + by) % 26 + 97) if c.isalpha() else c for c in text.lower())
        self.assertEqual(lines[0], f"Plain:  {plain}")
        self.assertEqual(lines[1], f"Secret: {shift(plain, 3)}")
        self.assertEqual(lines[2], f"Again:  {plain.lower()}")
        self.assertEqual(lines[3], 'Is "Was it a car or a cat I saw?" a palindrome? yes.')
        self.assertEqual(lines[4], "9 words, 3 of them longer than four letters.")

    def test_roman_numerals(self):
        lines, checked = said("roman")
        self.assertEqual(lines, ["2026 is MMXXVI.", "1666 is MDCLXVI.", "MDCLXVI is 1,666."])
        self.assertEqual(checked, 4)

    def test_the_bank(self):
        lines, _ = said("bank")
        self.assertEqual(lines[0], "Ada pays Bo $60.")
        self.assertTrue(lines[1].startswith("No payment from Bo: That would break a rule"))
        self.assertEqual(lines[2], "No payment from Cy: Cy's account is frozen")
        self.assertEqual(lines[3], "No payment from Cy: a payment has to be more than nothing")
        # Compound interest, in cents, worked out exactly and rounded only when said.
        from fractions import Fraction
        for name, start, rate in (("Ada", 940, "5"), ("Bo", 100, "2"), ("Cy", 250, "3.5")):
            balance = Fraction(start) * (1 + Fraction(rate) / 100) ** 10
            cents = round(balance * 100)
            self.assertTrue(any(line.startswith(f"{name} has ${cents // 100:,}.{cents % 100:02d}")
                                for line in lines), (name, lines))
        self.assertIn("Thriving: 1 of 3.", lines)

    def test_the_game_of_life(self):
        lines, _ = said("life")
        boards = [line for line in lines if set(line) <= set("#. ") and line]
        self.assertEqual(len(boards), 14)
        before = {(r, c) for r, line in enumerate(boards[:7]) for c, mark in enumerate(line.split()) if mark == "#"}
        after = {(r, c) for r, line in enumerate(boards[7:]) for c, mark in enumerate(line.split()) if mark == "#"}
        self.assertEqual(before, {(0, 1), (1, 2), (2, 0), (2, 1), (2, 2)})
        # A glider is the same shape again after four ticks, one step down and one across.
        self.assertEqual(after, {(r + 1, c + 1) for r, c in before})


if __name__ == "__main__":
    unittest.main()

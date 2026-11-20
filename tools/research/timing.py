"""Measure how the compiler and the running program scale. Run from the snapshot folder."""
import sys
import time
from fractions import Fraction

sys.path.insert(0, sys.argv[1])
from englishscript import compile_source, lint  # noqa: E402


def timed(work, repeat=1):
    best = None
    for _ in range(repeat):
        start = time.perf_counter()
        result = work()
        took = time.perf_counter() - start
        best = took if best is None or took < best else best
    return best, result


def run(source):
    said = []
    program = compile_source(source)
    world = program.run(out=lambda text="": said.append(str(text)))
    return said, world


print("== 1. Compile time against the size of the program (sentences) ==")
BASE = "A dragon has an age (number) and a lair (text).\nThere is a dragon called Smaug whose age is 771 and whose lair is \"Erebor\".\nLet the count be 0.\n"
for n in (250, 1000, 4000, 16000):
    source = BASE + "".join("Add Smaug's age to the count.\n" for _ in range(n))
    took, _ = timed(lambda: compile_source(source))
    print(f"  {n:6} sentences: {took:7.3f} s   {took / n * 1e6:7.1f} microseconds a sentence")

print("== 2. Compile time against the size of the vocabulary ==")
for kinds in (10, 100, 400, 1600):
    parts = []
    for k in range(kinds):
        word = "thing" + "".join(chr(97 + int(d)) for d in str(k))
        parts.append(f"A {word} has a weight (number) and a label (text).\n")
        parts.append(f"There is a {word} called Item{''.join(chr(65 + int(d)) for d in str(k))} whose weight is {k} and whose label is \"x\".\n")
        parts.append(f"A {word} is heavy when its weight is more than 5.\n")
    vocabulary = "".join(parts)
    body = "Let the count be 0.\n" + "".join("Add 1 to the count.\n" for _ in range(500))
    took_all, _ = timed(lambda: compile_source(vocabulary + body))
    took_vocab, _ = timed(lambda: compile_source(vocabulary))
    print(f"  {kinds:5} kinds ({3 * kinds} definitions): definitions {took_vocab:6.3f} s, "
          f"then 500 plain sentences {took_all - took_vocab:6.3f} s ({(took_all - took_vocab) / 500 * 1e6:6.1f} us each)")

print("== 3. Compile time against the number of verbs ==")
for verbs in (10, 100, 400, 1600):
    parts = ["Let the count be 0.\n"]
    names = []
    for v in range(verbs):
        name = "verb" + "".join(chr(97 + int(d)) for d in str(v))
        names.append(name)
        parts.append(f"To {name} a sum (number):\n  Add the sum to the count.\n")
    defs = "".join(parts)
    calls = "".join(f"{names[i % verbs].capitalize()} 1.\n" for i in range(500))
    took_defs, _ = timed(lambda: compile_source(defs))
    took_all, _ = timed(lambda: compile_source(defs + calls))
    print(f"  {verbs:5} verbs: definitions {took_defs:6.3f} s, then 500 uses {took_all - took_defs:6.3f} s "
          f"({(took_all - took_defs) / 500 * 1e6:6.1f} us each)")

print("== 4. Lint time against compile time ==")
source = BASE + "".join("Add Smaug's age to the count.\n" for _ in range(4000))
took_c, _ = timed(lambda: compile_source(source))
took_l, _ = timed(lambda: lint(source))
print(f"  4,000 sentences: compile {took_c:.3f} s, lint {took_l:.3f} s")

print("== 5. Running: sentences a second ==")
for label, source, count in (
    ("Add 1 to a variable", "Let the count be 0.\nRepeat 200,000 times:\n  Add 1 to the count.\n", 200_000),
    ("Add to a property", "A purse has a sum (number).\nThere is a purse called Bag whose sum is 0.\nRepeat 200,000 times:\n  Add 1 to Bag's sum.\n", 200_000),
    ("If and Add", "Let the count be 0.\nLet the evens be 0.\nRepeat 100,000 times:\n  Add 1 to the count.\n  If the count is divisible by 2:\n    Add 1 to the evens.\n", 250_000),
):
    program = compile_source(source)
    took, _ = timed(lambda: program.run(out=lambda text="": None))
    print(f"  {label:22}: {count / took:10,.0f} sentences a second")
start = time.perf_counter()
count = Fraction(0)
for _ in range(200_000):
    count += 1
python_fraction = 200_000 / (time.perf_counter() - start)
start = time.perf_counter()
n = 0
for _ in range(200_000):
    n += 1
python_int = 200_000 / (time.perf_counter() - start)
print(f"  the same loop in Python: {python_fraction:,.0f} a second with Fraction, {python_int:,.0f} with int")

print("== 6. Finding a thing by a property: \"For each slot whose place is N\" ==")
for n in (100, 400, 1600):
    lines = ["A slot has a place (number) and a value (number).\n", "Let the spot be 0.\n",
             f"Repeat {n:,} times:\n  Add 1 to the spot.\n  There is a new slot whose place is the spot and whose value is the spot.\n",
             "To work out the holding (number) at a place (number):\n  For each slot whose place is the place:\n    The answer is the slot's value.\n  The answer is 0.\n",
             "Let the total be 0.\nLet the turn be 0.\n",
             f"Repeat {n:,} times:\n  Add 1 to the turn.\n  Add the holding at the turn to the total.\n"]
    program = compile_source("".join(lines))
    took, _ = timed(lambda: program.run(out=lambda text="": None))
    print(f"  {n:5} slots, each looked up once: {took:7.3f} s   ({took / n * 1e3:6.2f} ms a lookup)")

print("== 7. Taking text apart a letter at a time ==")
for n in (200, 800, 3200):
    text = "abcdefghij" * (n // 10)
    source = (f'Let the line be "{text}".\nLet the spot be 0.\nLet the hits be 0.\nLet the size be the length of the line.\n'
              "Repeat the size times:\n  Add 1 to the spot.\n"
              "  If the first 1 letters of the last (the size - the spot + 1) letters of the line is \"a\":\n    Add 1 to the hits.\n")
    program = compile_source(source)
    took, _ = timed(lambda: program.run(out=lambda text="": None))
    print(f"  {n:5} letters: {took:7.3f} s   ({took / n * 1e6:7.1f} us a letter)")

print("== 8. Exact fractions that grow ==")
for n in (200, 800, 2000):
    source = f"Let the sum be 0.\nLet the term be 0.\nRepeat {n:,} times:\n  Add 1 to the term.\n  Add 1 / the term to the sum.\n"
    program = compile_source(source)
    took, world = timed(lambda: program.run(out=lambda text="": None))
    value = world.globals.vars["sum"]
    print(f"  the sum of 1/k to {n:5}: {took:6.3f} s; the answer's denominator has {len(str(value.denominator)):4} digits")

print("== 9. Limits on repetition and depth ==")
for label, source in (
    ("While, 10,001 rounds", "Let the count be 0.\nWhile the count is less than 10,001:\n  Add 1 to the count.\n"),
    ("Repeat, 1,000,000 rounds", "Let the count be 0.\nRepeat 1,000,000 times:\n  Add 1 to the count.\n"),
    ("a verb using itself 300 deep", "To sink a depth (number):\n  If the depth is more than 0:\n    Sink the depth - 1.\nSink 300.\n"),
):
    try:
        took, _ = timed(lambda: run(source))
        print(f"  {label}: fine, {took:.2f} s")
    except Exception as error:  # noqa: BLE001
        print(f"  {label}: {getattr(error, 'message', error)}")

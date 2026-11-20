"""Check what was built after the reviews: private names, lists, the index, arithmetic, choices.

Run from the repository:  python tools/research/later_fixes.py .
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from englishscript import EnglishError, compile_file, compile_source  # noqa: E402


def show(label, source, files=None):
    said = []
    try:
        if files:
            with tempfile.TemporaryDirectory() as folder:
                for name, text in files.items():
                    path = Path(folder) / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text, encoding="utf-8")
                (Path(folder) / "main.english").write_text(source, encoding="utf-8")
                compile_file(Path(folder) / "main.english").run(out=lambda text="": said.append(str(text)))
        else:
            compile_source(source).run(out=lambda text="": said.append(str(text)), ask=lambda question: None)
        print(f"--- {label}\n    ok:", " | ".join(said) if said else "(nothing said)")
    except EnglishError as error:
        if said:
            print(f"--- {label}\n    said first:", " | ".join(said))
            print(f"    {error.stage}: {error.message}")
        else:
            print(f"--- {label}\n    {error.stage}: {error.message}")


print("######## private names")
A = '''This chapter shares only bump and level.
Let the count be 0.
A cell has a size (number).
There is a cell called Marker whose size is 1.
To tidy:
  Add 1 to the count.
To bump:
  Tidy.
To work out the level (number):
  The answer is the count + the number of cells.
'''
B = '''This chapter shares only nudge and depth.
Let the count be 100.
A cell has a weight (text).
There is a cell called Marker whose weight is "heavy".
There is a cell called Other whose weight is "light".
To tidy:
  Add 10 to the count.
To nudge:
  Tidy.
To work out the depth (number):
  The answer is the count + the number of cells.
'''
show("two chapters with the same private words", 'Use the a chapter.\nUse the b chapter.\nBump.\nNudge.\nNudge.\nSay "{the level} and {the depth}".', {"a.english": A, "b.english": B})
show("a private word cannot be said from outside", 'Use the a chapter.\nSay the count.', {"a.english": A})
show("the program may use the word for itself", 'Use the a chapter.\nLet the count be 7.\nBump.\nSay "{the count} and {the level}".', {"a.english": A})
show("two chapters sharing one word", 'Use the a chapter.\nUse the b chapter.', {"a.english": A.replace("bump and level", "bump, level and count"), "b.english": B.replace("nudge and depth", "nudge, depth and count")})

print("######## lists")
show("made, added to, indexed, changed", '''Let the scores be a list of 3, 8 and 5.
Add 10 to the scores.
Set item 2 of the scores to 9.
Remove 3 from the scores.
Say the number of items in the scores.
Say item 1 of the scores or else 0.
Say the total of the scores.
Say item 9 of the scores or else 0.
If 10 is in the scores:
  Say "ten is there"
Let the names be a list of "Ada", "Bo" and "Cy".
Say the names joined with ", ".
Say the last of the names or else "nobody".''')
show("a list as a property, and a group made a list", '''A treasure has a worth (money).
A knight has a purse (money) and a shelf (list of treasures).
There is a treasure called Goblet whose worth is $30.
There is a treasure called Cup whose worth is $5.
There is a knight called Gawain whose purse is $1.
Say the number of items in Gawain's shelf.
Add Goblet to Gawain's shelf.
Add Cup to Gawain's shelf.
For each prize in Gawain's shelf:
  Say "{the prize} is worth {the prize's worth}".
Let the lot be all treasures.
Say the number of items in the lot.
Remove Cup.
Say the number of items in Gawain's shelf.''')
show("an item that is not there cannot be set", '''Let the scores be a list of 3, 8 and 5.
Try:
  Set item 7 of the scores to 1.
If that fails:
  Say "caught: {the problem}"''')
show("a failed Try puts a list back", '''Let the scores be a list of 3, 8 and 5.
Try:
  Add 99 to the scores.
  Fail because "no".
If that fails:
  Say the number of items in the scores.''')

print("######## finding without a search")
for n in (400, 1600, 6400):
    source = ("A slot has a place (number) and a value (number).\nLet the spot be 0.\n"
              f"Repeat {n:,} times:\n  Add 1 to the spot.\n  There is a new slot whose place is the spot and whose value is the spot.\n"
              "To work out the holding (number) at a place (number):\n  For each slot whose place is the place:\n    The answer is the slot's value.\n  The answer is 0.\n"
              "Let the total be 0.\nLet the turn be 0.\n"
              f"Repeat {n:,} times:\n  Add 1 to the turn.\n  Add the holding at the turn to the total.\nSay the total.\n")
    program = compile_source(source)
    said = []
    start = time.perf_counter()
    program.run(out=lambda text="": said.append(str(text)))
    print(f"    {n:5} slots, each looked up once: {time.perf_counter() - start:6.3f} s   (the sum is {said[0]})")

print("######## arithmetic, percentages, choices, text")
show("remainders, rounding, powers, roots", '''Say the remainder of 17 divided by 5.
Say 17 rounded up to the nearest 5.
Say $3.14159 rounded to the nearest $0.01.
Say 2 raised to the power of 100.
Say the square root of 81.
Say the square root of 2.
Say the larger of $5 and $8.
Say the absolute value of -4.
Say 10% + 5%.''')
show("a fixed set of choices", '''A mood is one of sleepy, grumpy or content.
A dragon has an age (number) and a mood (mood).
There is a dragon called Smaug whose age is 771 and whose mood is sleepy.
Set Smaug's mood to grumpy.
If Smaug's mood is grumpy:
  Say "Tread softly."''')
show("a choice that is not one of them", '''A mood is one of sleepy, grumpy or content.
A dragon has a mood (mood).
There is a dragon called Smaug whose mood is furious.''')
show("letters, and text tests said the other way", '''Let the word be "dragon".
Say letter 3 of the word or else "?".
If the word does not contain "x":
  Say "no x"''')

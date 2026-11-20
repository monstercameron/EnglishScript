"""A few more probes and figures. Run from the snapshot folder."""
import sys
import time
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from englishscript import EnglishError, compile_file, compile_source  # noqa: E402


def show(label, source):
    said = []
    try:
        compile_source(source).run(out=lambda text="": said.append(str(text)), ask=lambda question: None)
        print(f"--- {label}\n    ok:", " | ".join(said) if said else "(nothing said)")
    except EnglishError as error:
        print(f"--- {label}\n    {error.stage}: {error.message}" + (f"  [hint: {error.hint}]" if error.hint else ""))


show("two kinds with one plural, then the plural", 'A bus has a size (number).\nA buse has a size (number).\nThere is a bus called Routemaster whose size is 1.\nSay the number of buses.')
show("a kind whose plural is another kind's name", 'A glass has a size (number).\nA glasse has a size (number).')
show("removing what an optional property points at", 'A knight has a purse (money) and a liege (knight, if any).\nThere is a knight called Arthur whose purse is $9.\nThere is a knight called Gawain whose purse is $3 and whose liege is Arthur.\nRemove Arthur.\nSay "{Gawain\'s liege or else Gawain}"')
show("a variable still holding a removed thing", 'A knight has a purse (money).\nThere is a knight called Arthur whose purse is $9.\nLet the king be Arthur.\nRemove Arthur.\nSay "still here"\nSay "{the king}"')
show("a While that needs more than 10,000 rounds", 'Let the count be 0.\nWhile the count is less than 20,000:\n  Add 1 to the count.\nSay the count.')
show("the same, with Repeat", 'Let the count be 0.\nRepeat 20,000 times:\n  Add 1 to the count.\nSay the count.')
show("a multi-word name inside a longer phrase", 'A dragon has an age (number).\nThere is a dragon called Old Smaug whose age is 771.\nLet the old be 5.\nSay "{Old Smaug\'s age} and {the old}".')
show("a variable named like a kind", 'A dragon has an age (number).\nLet the dragon be 5.')
show("a variable named like a property of a kind in view", 'A dragon has an age (number).\nThere is a dragon called Smaug whose age is 771.\nLet the age be 1.\nFor each dragon:\n  Say "{its age} and {the age}".')

print("== compile time of each example (no running) ==")
examples = Path(sys.argv[1]) / "examples"
total = 0
for path in sorted(examples.glob("*.english")):
    text = path.read_text(encoding="utf-8")
    sentences = sum(1 for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    start = time.perf_counter()
    try:
        compile_file(path)
        took = time.perf_counter() - start
        total += sentences
        print(f"  {path.name:24} {sentences:4} sentences  {took * 1000:7.1f} ms")
    except EnglishError as error:
        print(f"  {path.name:24} {sentences:4} sentences  not compiled here: {error.message[:60]}")
print("  sentences in the examples, without their chapters:", total)

"""Check the four blockers of the adversarial review of the reference against the compiler.

Run from the repository:  python tools/research/review_blockers.py .
"""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from englishscript import EnglishError, compile_source  # noqa: E402


def show(label, source):
    said = []
    print(f"--- {label}")
    try:
        compile_source(source).run(out=lambda text="": said.append(str(text)), ask=lambda question: None)
        print("    ok:", " | ".join(said) if said else "(nothing said)")
    except EnglishError as error:
        if said:
            print("    said first:", " | ".join(said))
        print(f"    {error.stage}: {error.message}")
    except Exception:  # noqa: BLE001
        print("    PYTHON ERROR:", traceback.format_exc().strip().splitlines()[-1])


WORLD = '''A dragon has an age (number).
A treasure has a worth (money) and an owner (dragon).
A dragon is ancient when its age is at least 500.
There is a dragon called Smaug whose age is 771.
There is a dragon called Norbert whose age is 1.
There is a treasure called Goblet whose worth is $3,000 and whose owner is Smaug.
'''

print("#### F1: a number that is not whole is said through a float")
show("a large number and a half", 'Say 123,456,789,012,345,678,901 + 0.5.')
show("a large number with four places", 'Say 1,000,000,000,000,000.1234.')
show("rounding to four places", 'Say 0.00005.\nSay 0.00015.\nSay 0.00025.')
show("money rounds to the nearest cent, ties to even", 'Say $0.125.\nSay $0.375.\nSay $0.005.')

print("#### F2: a check that is refused although the value changes in the loop")
show("a chain followed in a loop", '''A node has a label (text) and a next (node, if any).
There is a node called Tail whose label is "tail".
There is a node called Head whose label is "head" and whose next is Tail.
Let the spot (node, if any) be Head.
Repeat 3 times:
  If the spot is not nothing:
    Say the spot's label.
    Set the spot to the spot's next.
''')
show("the same with While", '''A node has a label (text) and a next (node, if any).
There is a node called Tail whose label is "tail".
There is a node called Head whose label is "head" and whose next is Tail.
Let the spot (node, if any) be Head.
While the spot is not nothing:
  Say the spot's label.
  Set the spot to the spot's next.
''')

print("#### F3: a name that is also an adjective")
show("a thing named as an adjective is", WORLD + 'There is a dragon called Ancient whose age is 3.\nIf Norbert is Ancient:\n  Say "read as the thing"\nOtherwise:\n  Say "read as the adjective, or not the same thing"\nIf Smaug is Ancient:\n  Say "Smaug is Ancient: so it is the adjective"')
show("a variable that later becomes an adjective", WORLD + 'Let rich be Norbert.\nIf Norbert is rich:\n  Say "first: equal to the variable"\nA dragon is rich when its age is more than 100.\nIf Norbert is rich:\n  Say "second: still the variable"\nOtherwise:\n  Say "second: now the adjective"')
show("an adjective as a loop name", WORLD + 'For each ancient in dragons:\n  Say "{ancient}"')
show("two words before in: a name, not a filter", WORLD + 'For each ancient rival in dragons:\n  Say "{the ancient rival}"')

print("#### F4: rules")
show("a rule stated after a thing that breaks it", WORLD + 'Say "before the rule"\nA dragon\'s age is always at least 100.\nSay "after the rule"')
show("a rule that reads a variable made after the thing", 'A knight has a purse (money).\nThere is a knight called Gawain whose purse is $5.\nLet the cap be $10.\nA knight\'s purse is never more than the cap.\nSay "fine"')
show("a rule about another thing is not rechecked", WORLD + 'A treasure\'s owner is always ancient.\nSet Smaug\'s age to 5.\nSay "Smaug is {Smaug\'s age}, still owns the goblet, and is ancient: {whether Smaug is ancient}"')
show("a rule that reads a variable is not rechecked when the variable changes", 'A knight has a purse (money).\nLet the cap be $10.\nA knight\'s purse is never more than the cap.\nThere is a knight called Gawain whose purse is $5.\nSet the cap to $1.\nSay "the cap is now {the cap} and the purse {Gawain\'s purse}"\nAdd $1 to Gawain\'s purse.')

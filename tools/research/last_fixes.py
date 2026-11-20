"""Check the last things built: kinds of problem, Either way, kept values, verb shapes, and the modes for testing and tracing.

Run from the repository:  python tools/research/last_fixes.py .
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
import englishscript  # noqa: E402
from englishscript import EnglishError, compile_file, compile_source, lint  # noqa: E402


def show(label, source, files=None, main="main.english"):
    said = []
    try:
        if files:
            with tempfile.TemporaryDirectory() as folder:
                for name, text in files.items():
                    path = Path(folder) / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text, encoding="utf-8")
                target = Path(folder) / main
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(source, encoding="utf-8")
                compile_file(target).run(out=lambda text="": said.append(str(text)))
        else:
            compile_source(source).run(out=lambda text="": said.append(str(text)), ask=lambda question: None)
        print(f"--- {label}\n    ok:", " | ".join(said) if said else "(nothing said)")
    except EnglishError as error:
        if said:
            print(f"--- {label}\n    said first:", " | ".join(said))
            print(f"    {error.stage}: {error.message}")
        else:
            print(f"--- {label}\n    {error.stage}: {error.message}")


print("######## problems")
show("telling problems apart", '''A knight has a purse (money).
A knight's purse is never less than $0.
There is a knight called Gawain whose purse is $5.
To risk a count (number):
  Try:
    If the count is 1:
      Subtract $9 from Gawain's purse.
    If the count is 2:
      Say 1 / 0.
    If the count is 3:
      Fail because "the third".
  If that fails:
    If the problem is a broken rule:
      Say "a rule"
    Otherwise if the problem is a division by zero:
      Say "nought"
    Otherwise:
      Say "something else: {the problem}"
  Either way:
    Say "done {the count}"
Risk 1.
Risk 2.
Risk 3.
Risk 4.''')
show("passing a problem on unchanged", '''To risk:
  Try:
    Say 1 / 0.
  If that fails:
    Fail again.
Try:
  Risk.
If that fails:
  If the problem is a division by zero:
    Say "still a division by zero: {the problem}"''')

print("######## kept values")
show("a property kept equal to something", '''A purse has a sum (money).
A sign has a wording (text).
There is a purse called Bag whose sum is $5.
There is a sign called Board whose wording is "".
Keep Board's wording as "The bag holds {Bag's sum}.".
Say Board's wording.
Add $10 to Bag's sum.
Say Board's wording.''')
show("an adjective kept for every thing of a kind", '''A card has a wording (text).
A card can be ticked.
A card can be hidden.
Let the showing be "all".
There is a card called One whose wording is "one".
There is a card called Two whose wording is "two".
Keep each card hidden when the showing is "open" and the card is ticked.
Now One is ticked.
Say "{the number of hidden cards} hidden"
Set the showing to "open".
Say "{the number of hidden cards} hidden"''')
show("a kept value cannot be set by hand", '''A sign has a wording (text).
There is a sign called Board whose wording is "".
Keep Board's wording as "fixed".
Set Board's wording to "mine".''')
show("two kept values that chase each other", '''A sign has a count (number).
There is a sign called Left whose count is 0.
There is a sign called Right whose count is 0.
Keep Left's count as Right's count + 1.
Keep Right's count as Left's count + 1.
Say "never said"''')

print("######## verbs with several shapes")
show("the same word, other linking words", '''A knight has a purse (money).
A dragon has an age (number).
There is a knight called Gawain whose purse is $5.
There is a dragon called Smaug whose age is 771.
To send a knight against a dragon:
  Say "{the knight} rides against {the dragon}."
To send a sum (money) to a knight:
  Add the sum to the knight's purse.
  Say "{the knight} now has {the knight's purse}."
Send Gawain against Smaug.
Send $5 to Gawain.''')
show("the same linking words is still refused", '''A knight has a purse (money).
A dragon has an age (number).
To greet a knight:
  Say "k"
To greet a dragon:
  Say "d"''')

print("######## a book beside the program")
show("a chapter reaching a sibling book", 'Use the battle chapter of the kingdom book.\nFight.',
     {"kingdom/battle.english": 'Use the shield chapter of the heraldry book.\nTo fight:\n  Say "Under the {the device}."\n',
      "heraldry/shield.english": 'Let the device be "red lion".\n'})

print("######## small changes of behaviour")
show("a name with an accent", 'A dragon has an age (number).\nThere is a dragon called Fáfnir whose age is 9.\nSay "{Fáfnir} is {Fáfnir\'s age}."')
show("a number with a misplaced comma", 'Say 0,123.')
show("a lone closing brace", 'Say "a } b"')
problems = lint('A node has a next (node).\n')
print("--- a kind that can never be made\n    lint:", [(p.kind, p.message) for p in problems][:2])

print("######## for tools")
found, notes = lint('A dragon has an age (number).\nA dragon is ancient when its age is at least 500.\nThere is a dragon called Smaug whose age is 771.\nFor each ancient dragon:\n  Say its age.\nx = 5\n', notes=True)
print("--- notes beside problems:", len(found), "problem(s),", len(notes), "note(s) for the lines that read")
table = englishscript.names('A dragon has an age (number).\nA dragon is ancient when its age is at least 500.\nThere is a dragon called Smaug whose age is 771.\nTo tax a dragon:\n  Say "taxed"\n')
print("--- names:", sorted({(entry.get("what") or entry.get("is") or "?") for entry in table["names"]}))
print("--- version", englishscript.__version__, "| reserved words:", len(englishscript.KEYWORDS))

print("######## testing and tracing")
program = compile_source('Let the count be 2.\nSay "this is not said in a test"\nFor example, the count is 2.\nFor example, the count is 3.\nFor example, the count + 1 is 3.\n')
for result in program.test():
    print("   ", result.line, "held" if result.held else "DID NOT HOLD:", "" if result.held else result.fact)
trace = []
compile_source('A lamp has a place (text).\nA lamp can be lit.\nThere is a lamp called Lantern whose place is "hall".\nWhenever a lamp becomes lit:\n  Say "light"\nNow Lantern is lit.\n').run(
    out=lambda text="": None, trace=lambda depth, file, line, sentence, cause: trace.append((depth, line, sentence.strip(), cause)))
for entry in trace:
    print("   ", entry)

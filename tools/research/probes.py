"""Probe what the implementation does about each concern. Run from the snapshot folder."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, sys.argv[1])
from englishscript import EnglishError, compile_file, compile_source  # noqa: E402
from englishscript import compiler as compiler_module  # noqa: E402


def show(label, source, files=None):
    print(f"--- {label}")
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
        print("    ok:", " | ".join(said) if said else "(nothing said)")
    except EnglishError as error:
        if said:
            print("    said first:", " | ".join(said))
        print(f"    {error.stage}: {error.message}" + (f"  [hint: {error.hint}]" if error.hint else ""))
    except Exception as error:  # noqa: BLE001
        print("    PYTHON ERROR:", type(error).__name__, error)


WORLD = '''A dragon has an age (number) and a lair (text).
A treasure has a worth (money) and an owner (dragon).
A knight has a purse (money) and a liege (knight, if any).
There is a dragon called Smaug whose age is 771 and whose lair is "Erebor".
There is a treasure called Goblet whose worth is $3,000 and whose owner is Smaug.
There is a knight called Arthur whose purse is $900.
There is a knight called Gawain whose purse is $300 and whose liege is Arthur.
'''

print("######## names: prefixes, case, plurals, reserved words")
show("a name that is the start of another", 'Let the tax be 1.\nLet the tax rate be 2.\nSay "{the tax} and {the tax rate}".')
show("a property and a variable with one name", WORLD + 'Let the age be 5.\nSay "{the age} and {Smaug\'s age}".')
show("a thing and a variable with one name", WORLD + 'Let Smaug be 5.')
show("case: a thing's name in small letters", WORLD + 'Say smaug\'s age.')
show("case: two things that differ only by capitals", WORLD + 'There is a dragon called SMAUG whose age is 1 and whose lair is "x".')
show("case: a kind written with a capital", WORLD + 'Say the number of Dragons.')
show("plural: child", 'A child has an age (number).\nThere is a child called Tom whose age is 3.\nSay the number of children.')
show("plural: child, by rule", 'A child has an age (number).\nThere is a child called Tom whose age is 3.\nSay the number of childs.')
show("plural: sheep", 'A sheep has an age (number).\nThere is a sheep called Dolly whose age is 3.\nSay the number of sheep.')
show("plural: a kind ending in s", 'A glass has a size (number).\nThere is a glass called Flute whose size is 3.\nSay the number of glasses.')
show("plural clash: two kinds with one plural", 'A bus has a size (number).\nA buse has a size (number).')
print("    reserved words:", len(compiler_module.KEYWORDS))

print("######## verbs: one word, several shapes")
show("the same verb word with other roles", WORLD + 'To send a knight against a dragon:\n  Say "a"\nTo send a treasure to a knight:\n  Say "b"\nSend Gawain against Smaug.\nSend Goblet to Gawain.')
show("the same verb word, same shape, other kinds", WORLD + 'To greet a knight:\n  Say "k"\nTo greet a dragon:\n  Say "d"\nGreet Smaug.')
show("a worked-out value and a verb with one word", WORLD + 'To work out the tax (money) of a knight:\n  The answer is $1.\nTo tax a knight:\n  Say "taxed"\nTax Gawain.\nSay the tax of Gawain.')

print("######## relationships")
show("of, with one link", WORLD + 'Say the number of treasures of Smaug.')
show("of, with two links to one kind", 'A dragon has an age (number).\nA feud has a challenger (dragon) and a defender (dragon).\nThere is a dragon called Smaug whose age is 1.\nSay the number of feuds of Smaug.')
show("of, to its own kind", WORLD + 'Say the number of knights of Arthur.')
show("its, with two things in view", WORLD + 'To send a knight against a dragon:\n  Say "{its age}"\nSend Gawain against Smaug.')

print("######## lifetimes")
show("removing a thing that another refers to", WORLD + 'Remove Smaug.\nSay "{Goblet\'s owner}"')
show("using a removed thing kept in a variable", WORLD + 'Let the beast be Smaug.\nRemove Goblet.\nRemove Smaug.\nSay "{the beast\'s age}"')
show("a removed thing inside a Try is brought back", WORLD + 'Try:\n  Remove Goblet.\n  Fail because "no".\nIf that fails:\n  Say "{the number of treasures} left"')
show("two things each referring to the other", 'A knight has a purse (money) and a liege (knight, if any).\nThere is a knight called Kay whose purse is $1.\nThere is a knight called Bors whose purse is $1 and whose liege is Kay.\nSet Kay\'s liege to Bors.\nSay "{Kay\'s liege} and {Bors\'s liege or else Kay}"')

print("######## purity of worked-out values")
show("changing something inside To work out", WORLD + 'To work out the toll (money) of a knight:\n  Subtract $1 from the knight\'s purse.\n  The answer is $1.')
show("saying inside To work out", WORLD + 'To work out the toll (money) of a knight:\n  Say "peek"\n  The answer is $1.\nSay the toll of Gawain.')
show("using a verb inside To work out", WORLD + 'To shout:\n  Say "hey"\nTo work out the toll (money) of a knight:\n  Shout.\n  The answer is $1.')
show("reading a file inside To work out", 'To work out the notes (text):\n  The answer is the text of the file "nonesuch.txt".\nTry:\n  Say the notes.\nIf that fails:\n  Say "reading was allowed, and failed: {the problem}"')
show("asking inside To work out", 'To work out the reply (text):\n  Ask "Name?" and let the word (text) be the reply.\n  The answer is the word.')
show("making a thing inside To work out", WORLD + 'To work out the spawn (dragon):\n  Let the chick be a new dragon whose age is 0 and whose lair is "nest".\n  The answer is the chick.')

print("######## errors")
show("a problem keeps only its text", 'Try:\n  Say 1 / 0.\nIf that fails:\n  Say "caught: {the problem}"')
show("passing a problem on", 'To risk:\n  Try:\n    Fail because "inner".\n  If that fails:\n    Fail because "outer, because of {the problem}".\nTry:\n  Risk.\nIf that fails:\n  Say the problem.')
show("a For example that fails cannot be caught", 'Try:\n  For example, 1 is 2.\nIf that fails:\n  Say "caught"')
show("a file written inside a failed Try stays written", 'Try:\n  Write "x" to the file "probe_out.txt".\n  Fail because "after writing".\nIf that fails:\n  Say "the file says: {the text of the file "probe_out.txt"}"')

print("######## modules")
CHAPTER = 'This chapter shares only bump and level.\nLet the level be 0.\nLet the secret be 7.\nTo bump:\n  Add 1 to the level.\n'
show("a shared variable can be changed from outside", 'Use the a chapter.\nSet the level to 99.\nBump.\nSay the level.', {"a.english": CHAPTER})
show("an unshared variable cannot", 'Use the a chapter.\nSet the secret to 1.', {"a.english": CHAPTER})
show("a chapter's rule binds the whole program", 'Use the a chapter.\nSet Tom\'s age to 0 - 1.', {"a.english": 'A child has an age (number).\nA child\'s age is never less than 0.\nThere is a child called Tom whose age is 3.\n'})
show("a chapter may put a rule on a kind it did not make", 'A child has an age (number).\nThere is a child called Tom whose age is 3.\nUse the b chapter.\nSet Tom\'s age to 200.', {"b.english": 'This chapter shares nothing.\nSay "b read"\n'})
show("two chapters sharing one name", 'Use the a chapter.\nUse the b chapter.', {"a.english": 'Let the level be 0.\n', "b.english": 'Let the level be 1.\n'})
show("two chapters, one private name each", 'Use the a chapter.\nUse the b chapter.\nSay "fine"', {"a.english": 'This chapter shares nothing.\nLet the level be 0.\n', "b.english": 'This chapter shares nothing.\nLet the level be 1.\n'})
show("what a chapter uses is not passed on", 'Use the a chapter.\nSay the depth.', {"a.english": 'Use the b chapter.\n', "b.english": 'Let the depth be 3.\n'})

print("######## text and numbers")
show("length counts characters, not bytes", 'Say the length of "naïve café".')
show("upper case of non-English letters", 'Say "straße" in upper case.')
show("text order", 'If "apple" comes before "Banana":\n  Say "a first"\nOtherwise:\n  Say "B first"')
show("a number said to four places", 'Say 1 / 3.\nSay 2 / 3 * 3.\nSay 10 / 4.')
show("money rounds when said", 'Say $10 / 3.\nFor example, $10 / 3 * 3 is $10.')
show("no remainder, no power", 'Say 7 mod 2.')
show("a list cannot be built or changed", 'Let the row be the words of "a b c".\nAdd "d" to the row.')
show("a list cannot be indexed", 'Let the row be the words of "a b c".\nSay item 2 of the row.')

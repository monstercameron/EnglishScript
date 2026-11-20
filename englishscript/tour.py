"""A guided tour: one program that works, then the sentences the compiler refuses."""
from pathlib import Path

from . import EnglishError, compile_source

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "dragons.english"
STORY_MARKER = "# --- The story"

# Sentences from the example whose reading is worth showing in section 3.
SHOW_WORKING = (
    "The hoard of a dragon",
    "A dragon is poor",
    "Let the loot",
    "For each treasure of the dragon",
    "Send Gawain against Smaug",
    "If it is ancient",
    "Say \"Ancient dragons",
)

# (what it shows, the sentences someone might write)
REFUSALS = [
    (
        "A pronoun that could point at two things",
        """For each dragon:
  For each treasure of the dragon:
    Say its worth.""",
    ),
    (
        '"And" mixed with "or"',
        """If Smaug is ancient and Norbert is poor or Gawain is brave:
  Say "Hm.\"""",
    ),
    (
        "A word that isn't in the glossary",
        """If Smaug is sleepy:
  Say "Shh.\"""",
    ),
    (
        "A number where money belongs",
        "Add 5 to Gawain's purse.",
    ),
    (
        "A verb with its roles swapped",
        "Send Smaug against Gawain.",
    ),
    (
        "A verb with a role missing",
        "Send Gawain.",
    ),
    (
        '"The" with nothing to point at',
        "Say the dragon's age.",
    ),
    (
        'An "of" that could mean two things',
        """A duel has a challenger (dragon) and a defender (dragon).
Say the number of duels of Smaug.""",
    ),
    (
        "Changing something that a definition works out",
        "Set Smaug's hoard to $5.",
    ),
    (
        'Breaking a "never" rule (caught while running)',
        "Subtract $500 from Robin's purse.",
    ),
    (
        "An example that isn't true (caught while running)",
        "For example, the hoard of Smaug is $1.",
    ),
]


def _heading(text):
    print()
    print(text)
    print("=" * len(text))
    print()


def _indent(text, by="    "):
    return "\n".join(by + line if line else line for line in text.splitlines())


def tour():
    source = EXAMPLE.read_text(encoding="utf-8")
    prelude = source.split(STORY_MARKER)[0]

    _heading("EnglishScript: English strict enough to compile")
    print("Every sentence below is ordinary English. Every sentence also has exactly")
    print("one meaning, and the compiler refuses the ones that don't. No AI is involved:")
    print("this is a plain parser, so the same program always means the same thing.")

    _heading("1. A program  (examples/dragons.english)")
    print(_indent(source.rstrip()))

    _heading("2. Running it")
    program = compile_source(source)
    world = program.run(lambda text: print(("    " + text).rstrip()))
    print()
    print(f"    ({world.examples} examples checked along the way.)")

    _heading("3. What the writer left unsaid, and how the compiler filled it in")
    print('English lets you say "its", "the dragon" or "treasures of the dragon" without')
    print("spelling out what you mean. The compiler allows that only when there is exactly")
    print("one possible reading, and it can show its working:")
    print()
    notes = {}
    for number, text in program.notes:
        notes.setdefault(number, []).append(text)
    for number, line in enumerate(source.splitlines(), 1):
        if number in notes and any(line.strip().startswith(start) for start in SHOW_WORKING):
            print("    " + line.strip())
            for text in notes[number]:
                print("        ↳ " + text)
    print()
    print("    (python -m englishscript examples/dragons.english --explain  shows all of them.)")

    _heading("4. Sentences the compiler refuses")
    print("Each of these is added to the end of the same program. A person would guess")
    print("at the meaning; the compiler says what is unclear and how to fix it.")
    for number, (title, snippet) in enumerate(REFUSALS, 1):
        print()
        print(f"  {number}. {title}")
        print()
        print(_indent(snippet, "      | "))
        print()
        try:
            compile_source(prelude + "\n" + snippet + "\n").run(lambda text: None)
            print("      (unexpectedly, this was accepted)")
        except EnglishError as error:
            print(_indent(error.render(location=False), "      "))

    _heading("5. Try it yourself")
    print("    python -m englishscript examples/hello.english")
    print("    python -m englishscript examples/invoices.english")
    print("    python -m englishscript examples/invoices.english --explain")
    print()
    print("Then open a .english file, change a sentence, and see what the compiler makes of it.")
    print()

"""Bundle the compiler and the example programs for the project page in docs/.

    python tools/build_site.py

The page (docs/index.html) runs the real compiler in the browser with Pyodide.
A browser can only fetch what GitHub Pages serves, which is the docs folder, so
this script copies what the page needs into docs/play/:

    englishscript.zip   the englishscript package, as Pyodide unpacks it
    examples.json       the programs offered in the playground

It also runs every program printed in docs/index.html through the compiler and
writes what it says into the page, so that the page never shows an output the
compiler would not give.

Run it again after changing the compiler, an example, or a program on the
page. A test compares all three with the source and fails if one is out of date.
"""
from __future__ import annotations

import html
import io
import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAY = ROOT / "docs" / "play"

# The programs offered in the playground, in order: (file, title, note).
EXAMPLES = [
    ("helloworld", "Hello, world", "One sentence."),
    ("fizzbuzz", "FizzBuzz", "Loops, branches and “is divisible by”."),
    ("dragons", "Dragons, treasure and tax", "Kinds, adjectives, worked-out properties, verbs and rules."),
    ("invoices", "Late fees", "The same structures in a business setting."),
    ("tournament", "A tournament", "Values that may be missing, worked-out values, and leaving early."),
    ("triangle", "A shaded triangle", "The steps of a Vulkan program, drawn in characters."),
    ("todo", "A to-do list", "It asks for commands. Try: add Buy milk, done 1, list, quit."),
    ("sha256", "SHA-256 from first principles", "It takes a few seconds to set up, then asks for text to hash."),
    ("primes", "Primes and perfect numbers", "Testing, listing and factoring, all built on “is divisible by”."),
    ("euclid", "Euclid’s greatest common measure", "Two methods, by subtracting and by halving, and fractions in lowest terms."),
    ("fibonacci", "Fibonacci numbers", "A loop, a definition that uses itself, and a number of twenty-one digits."),
    ("roots", "Square roots and pi", "Exact fractions: Heron’s method, a search by halving, and Machin’s formula."),
    ("sorting", "Sorting and searching", "A row of things sorted by swapping, then searched by halving."),
    ("hanoi", "The Tower of Hanoi", "A verb that uses itself, moving four discs in fifteen moves."),
    ("collatz", "The Collatz puzzle", "While loops, skipping a round and stopping early."),
    ("caesar", "A cipher and a palindrome", "Taking text apart a letter at a time."),
    ("roman", "Roman numerals", "Into numerals and back, with a table made of things."),
    ("bank", "A small bank", "Money, percentages, a rule that is never broken, and Try."),
    ("life", "The Game of Life", "Forty-nine cells, each a thing, and a glider that walks."),
    ("almanac", "An almanac, from the chapters of a book",
     "It uses three chapters of the almanac book: a calendar, Roman numerals and the feasts of the year."),
    ("web_todo", "A to-do list for the web",
     "The program behind “A page”, in four chapters of the tasks book. Run it, and its page appears under what it says."),
]


# Programs a page of the site fetches as they are, from examples/ into docs/play/.
COPIES = ["web_todo.english"]


def copy_text(name):
    return (ROOT / "examples" / name).read_text(encoding="utf-8").replace("\r\n", "\n")


# The books a program in the browser can use: folders of chapters in examples/.
SHELF = ["almanac", "tasks"]


def shelf_text():
    """Every chapter of every book on the shelf, as {"almanac/calendar.english": its text}."""
    files = {}
    for book in SHELF:
        for path in sorted((ROOT / "examples" / book).glob("*.english")):
            files[f"{book}/{path.name}"] = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return json.dumps(files, indent=1, ensure_ascii=False) + "\n"


# The playground's "How to say it" list: (what you want, the sentences, a note).
# Read in order they make one program, which a test compiles and runs.
PHRASES = [
    ("Describe a kind of thing",
     "A pet has an age (number) and a home (text).",
     "The type goes in brackets: number, money, text, percent, or another kind."),
    ("Make a thing",
     'There is a pet called Rex whose age is 3 and whose home is "the kitchen".',
     "Every property the kind has must be given."),
    ("Say something",
     'Say "{Rex} is {Rex\'s age} and lives in {Rex\'s home}."',
     "Anything in {braces} is worked out and filled in."),
    ("Remember a value",
     "Let the total be 0.",
     "A name means one thing: to change it later, use Set or Add."),
    ("Change a value",
     "Add 5 to the total.\nSet Rex's age to 4.",
     "Also: Subtract ... from ..., Multiply ... by ..., Divide ... by ..."),
    ("Decide",
     'If Rex\'s age is more than 3:\n  Say "Rex is grown."\nOtherwise:\n  Say "Rex is a pup."',
     "Compare with: is, is not, is less than, is more than, is at least, is at most, is divisible by."),
    ("Describe with an adjective",
     "A pet is old when its age is at least 10.",
     "Then you can write: If Rex is old:  or  For each old pet:"),
    ("Go through every thing",
     'For each pet:\n  Say "{its name} is {its age}."',
     "Inside the block, “it” and “the pet” mean the current one."),
    ("Repeat",
     'Repeat 3 times:\n  Say "Again."',
     "Or: While the total is less than 10:"),
    ("Count and add up",
     "Say the number of pets.\nSay the total age of all pets.",
     "A group can be narrowed: the number of old pets."),
    ("Teach a verb",
     'To feed a pet with a treat (text):\n  Say "{the pet} eats the {the treat}."\n\nFeed Rex with "biscuit".',
     "Prepositions name the roles: with, to, from, for, on, at, by, against..."),
    ("Work out a value",
     "To work out the double (number) of a count (number):\n  The answer is the count * 2.\n\nSay the double of 21.",
     "Working out may not change anything or say anything."),
    ("Ask a question",
     'Ask "What is your name?" and let the visitor (text) be the reply.\nSay "Hello, {the visitor}."',
     "The reply can be text, a number, money, a percent, or yes or no."),
    ("Something that may be missing",
     'A child has an age (number) and a friend (pet, if any).\nThere is a child called Sam whose age is 7.\n\nIf Sam has a friend:\n  Say "Sam\'s friend is {Sam\'s friend}."\nOtherwise:\n  Say "Sam has no pet yet."',
     "“if any” means the compiler makes you check before using it."),
    ("State a rule",
     "A pet's age is never less than 0.",
     "Checked every time a pet's age changes. Also: always."),
    ("Test your program",
     "For example, Rex's age is 4.",
     "If it is not true when the program gets here, the program stops and says so."),
]


def phrases_program():
    """Every phrase in order, as one program."""
    return "\n\n".join(sentences for _, sentences, _ in PHRASES) + "\n"


def phrases_text():
    rows = [{"want": want, "sentences": sentences, "note": note} for want, sentences, note in PHRASES]
    return json.dumps(rows, indent=1, ensure_ascii=False) + "\n"


def package_files():
    """(name inside the zip, bytes) for every Python file of the package, in a fixed order."""
    package = ROOT / "englishscript"
    files = sorted(path for path in package.rglob("*.py") if "__pycache__" not in path.parts)
    return [(path.relative_to(ROOT).as_posix(), path.read_bytes().replace(b"\r\n", b"\n")) for path in files]


def build_zip():
    """The package as a zip. The dates are fixed, so the same source gives the same file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in package_files():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return buffer.getvalue()


def build_examples():
    examples = []
    for name, title, note in EXAMPLES:
        source = (ROOT / "examples" / f"{name}.english").read_text(encoding="utf-8")
        examples.append({"id": name, "title": title, "note": note, "source": source})
    return examples


def examples_text():
    return json.dumps(build_examples(), indent=1, ensure_ascii=False) + "\n"


# A program printed on the page, and the place just after it for what it says.
SNIPPET = re.compile(
    r'(<pre class="program" data-expect="(ok|refused)">)(.*?)(</pre>\s*<pre class="output[^"]*">)(.*?)(</pre>)',
    re.S,
)


def snippet_output(source, expect):
    """What the compiler says for a program on the page: its lines, or its refusal."""
    sys.path.insert(0, str(ROOT))
    from englishscript import EnglishError, compile_source

    said, refusal = [], None
    try:
        # Chapters and books are looked for in examples/, as the tests and the browser do.
        compile_source(source, folder=ROOT / "examples").run(said.append, lambda question: None)
    except EnglishError as error:
        refusal = error.render()
    if (refusal is not None) != (expect == "refused"):
        found = "refused" if refusal is not None else "accepted"
        raise SystemExit(f"A program on the page is marked {expect!r} but was {found}:\n\n{source}\n\n{refusal or ''}")
    if refusal is not None:
        said = said + ([""] if said else []) + [refusal]
    return "\n".join(said)


#: The pages written by hand that print programs. The build writes what the
#: compiler says under each program, and a test fails if a page is out of date.
WRITTEN = ["index.html", "compare.html"]


def render_page(page):
    """The page with the output of every printed program filled in from the compiler."""
    def fill(match):
        opening, expect, program, between, _, closing = match.groups()
        output = snippet_output(html.unescape(program), expect)
        return opening + program + between + html.escape(output, quote=False) + closing
    return SNIPPET.sub(fill, page)


def reference_page():
    """docs/reference.html: the syntax reference, printed from docs/SYNTAX.md."""
    import pages

    source = pages.Markdown((ROOT / "docs" / "SYNTAX.md").read_text(encoding="utf-8"))
    return pages.document(
        title="The grammar of EnglishScript",
        description="Every sentence the EnglishScript compiler accepts, with examples that run in the page.",
        current="reference.html",
        heading="The Grammar",
        standfirst="Every sentence the compiler accepts. The examples run where they stand, and each one builds on the "
                   "small world described at the start. Chapters 12 to 14 are designs that have not been built.",
        body=source.render(),
        contents=source.contents(later=("12", "13", "14")),
        colophon='Printed from <a href="' + pages.SOURCE + '/blob/main/docs/SYNTAX.md">docs/SYNTAX.md</a> by '
                 "<code>tools/build_site.py</code>. Every example on this page is run by the test suite.",
    )


def vulkan_page():
    """docs/vulkan.html: the vulkan library's page, printed from docs/VULKAN.md."""
    import pages

    source = pages.Markdown((ROOT / "docs" / "VULKAN.md").read_text(encoding="utf-8"))
    return pages.document(
        title="The vulkan library of EnglishScript",
        description="Draw shaded triangles on a graphics card from EnglishScript, through the real Vulkan API.",
        current="",
        heading="The Vulkan Library",
        standfirst="English sentences that draw on a real graphics card, each beside the Vulkan calls it makes.",
        body=source.render(),
        runnable=False,
        colophon='Printed from <a href="' + pages.SOURCE + '/blob/main/docs/VULKAN.md">docs/VULKAN.md</a> by '
                 "<code>tools/build_site.py</code>.",
    )


def page_library_page():
    """docs/page.html: the page library's page, printed from docs/PAGE.md."""
    import pages

    source = pages.Markdown((ROOT / "docs" / "PAGE.md").read_text(encoding="utf-8"))
    return pages.document(
        title="The page library of EnglishScript",
        description="Web pages written in EnglishScript: seven kinds of thing that are elements of a page, bound both ways.",
        current="",
        heading="The Page Library",
        standfirst="Things that are elements of a web page, and the sentences that answer a press or a keystroke.",
        body=source.render(),
        runnable=False,
        colophon='Printed from <a href="' + pages.SOURCE + '/blob/main/docs/PAGE.md">docs/PAGE.md</a> by '
                 "<code>tools/build_site.py</code>.",
    )


def concerns_page():
    """docs/concerns.html: the risks and open questions, printed from docs/CONCERNS.md."""
    import pages

    source = pages.Markdown((ROOT / "docs" / "CONCERNS.md").read_text(encoding="utf-8"))
    return pages.document(
        title="Risks and open questions about EnglishScript",
        description="Forty-two concerns about EnglishScript, each measured or probed against the compiler and given a verdict.",
        current="",
        heading="Risks and Open Questions",
        standfirst="Forty-two concerns raised about the language, and what measuring the compiler says about each.",
        body=source.render(),
        runnable=False,
        colophon='Printed from <a href="' + pages.SOURCE + '/blob/main/docs/CONCERNS.md">docs/CONCERNS.md</a> by '
                 "<code>tools/build_site.py</code>.",
    )


#: The pages printed from Markdown: (file in docs/, the function that makes it).
PRINTED = [("reference.html", reference_page), ("vulkan.html", vulkan_page), ("page.html", page_library_page),
           ("concerns.html", concerns_page)]


def main():
    sys.path.insert(0, str(ROOT / "tools"))
    PLAY.mkdir(parents=True, exist_ok=True)
    (PLAY / "englishscript.zip").write_bytes(build_zip())
    (PLAY / "examples.json").write_text(examples_text(), encoding="utf-8", newline="\n")
    (PLAY / "phrases.json").write_text(phrases_text(), encoding="utf-8", newline="\n")
    (PLAY / "shelf.json").write_text(shelf_text(), encoding="utf-8", newline="\n")
    print(f"docs/play/shelf.json: the chapters of {len(SHELF)} book(s)")
    for name in COPIES:
        (PLAY / name).write_text(copy_text(name), encoding="utf-8", newline="\n")
        print(f"docs/play/{name}: a copy of examples/{name}")
    files = package_files()
    print(f"docs/play/englishscript.zip: {len(files)} files, {sum(len(data) for _, data in files):,} bytes of Python")
    print(f"docs/play/examples.json: {len(EXAMPLES)} programs")
    print(f"docs/play/phrases.json: {len(PHRASES)} ways to say things")
    for name in WRITTEN:
        page = (ROOT / "docs" / name).read_text(encoding="utf-8")
        (ROOT / "docs" / name).write_text(render_page(page), encoding="utf-8", newline="\n")
        print(f"docs/{name}: {len(SNIPPET.findall(page))} printed programs given their output")
    for name, make in PRINTED:
        text = make()
        (ROOT / "docs" / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"docs/{name}: {len(text):,} characters, printed from Markdown")


if __name__ == "__main__":
    sys.exit(main())

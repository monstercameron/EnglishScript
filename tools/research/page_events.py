"""What one click costs on the to-do page, and what happens when an answer fails.

Run from the repository:  python tools/research/page_events.py .

There is no browser here: the page library's stand-in page is used, driven
through the same listeners a browser would call. Every write to an element is
counted, so "how much of the page was touched" is measured, not guessed.
"""
import sys
import time
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
from englishscript import EnglishError, compile_source  # noqa: E402
from englishscript.libraries import page  # noqa: E402

EXAMPLES = root / "examples"
SOURCE = (EXAMPLES / "web_todo.english").read_text(encoding="utf-8")


def open_page(source, kept=None, folder=EXAMPLES):
    page.STORE.clear()
    page.STORE.update(kept or {})
    said = []
    world = compile_source(source, folder=folder).run(out=lambda text="": said.append(str(text)))
    return world, said


class Counter:
    """Counts, during one action: writes to the page, writes to storage, and how often each verb ran."""

    def __init__(self, world):
        self.world = world

    def __enter__(self):
        self.keeps = 0
        self.real_keep = page.verb_remember

        def counted(world, line, key):
            self.keeps += 1
            return self.real_keep(world, line, key)
        page.verb_remember = counted
        # The compiler looked the function up when it compiled, so count through the backend too.
        backend = page._state(self.world)["backend"]
        self.backend = backend
        self.real_backend_keep = backend.keep

        def kept(key, line):
            self.keeps_backend += 1
            return self.real_backend_keep(key, line)
        self.keeps_backend = 0
        backend.keep = kept
        page.Node.LOG = []
        self.start = time.perf_counter()
        return self

    def __exit__(self, *_):
        self.took = time.perf_counter() - self.start
        self.writes = len(page.Node.LOG)
        self.touched = len({id(node) for node, _, _ in page.Node.LOG})
        page.Node.LOG = None
        page.verb_remember = self.real_keep
        self.backend.keep = self.real_backend_keep


def record(cards, ticked=0):
    return "".join(f"{'x' if i < ticked else '-'} - - Task number {i + 1}\n" for i in range(cards))


print("== 1. One click on a list of N cards ==")
print("   (storage writes; elements touched; writes to elements; time)")
for cards in (10, 50, 200):
    row = []
    for label, act in (
        ("tick one card", lambda world: page.tick(world, "card 3")),
        ("star one card", lambda world: page.star(world, "card 3")),
        ("type one letter in Find", lambda world: page.type_in(world, "Finder", "t")),
        ("type one letter in the entry box", lambda world: page.type_in(world, "Entry", "B")),
        ("add a card", lambda world: page.type_in(world, "Entry", "Something new", enter=True)),
        ("tick them all", lambda world: page.press(world, "Finisher")),
    ):
        world, _ = open_page(SOURCE, kept={"tasks": record(cards)})
        with Counter(world) as count:
            act(world)
        row.append(f"   {cards:4} cards  {label:34} {count.keeps_backend:4} saves  {count.touched:4} elements  "
                   f"{count.writes:5} writes  {count.took * 1000:8.1f} ms")
    print("\n".join(row))

print("== 2. What the page library does alone: one changed card among N ==")
PLAIN = '''Use the page library.
There is a panel called Roll.
There is a button called Maker whose label is "Make".
'''
for cards in (10, 200, 1000):
    source = PLAIN + f"Let the turn be 0.\nRepeat {cards:,} times:\n  Add 1 to the turn.\n  There is a new card whose wording is \"Task {{the turn}}\" and whose panel is Roll.\n"
    world, _ = open_page(source)
    with Counter(world) as count:
        page.tick(world, "card 3")
    print(f"   {cards:5} cards, no Whenever at all: tick one  ->  {count.touched} element touched, {count.writes} writes, {count.took * 1000:7.2f} ms")

print("== 3. Reactions that set each other off ==")
LOOP = '''Use the page library.
There is a card called Chore whose wording is "Sweep".
There is a note called Tally whose wording is "untouched".
Whenever a card becomes ticked:
  Set Tally's wording to "changed by the answer".
  Now the card is starred.
Whenever a card becomes starred:
  Now the card is not ticked.
Whenever a card becomes not ticked:
  Now the card is not starred.
Whenever a card becomes not starred:
  Now the card is ticked.
'''
world, said = open_page(LOOP)
before = len(said)
page.tick(world, "Chore")
chore = page.element(world, "Chore")
print("   said:", said[before:])
print("   afterwards: ticked", "ticked" in chore.thing.marks, "| starred", "starred" in chore.thing.marks,
      "| the box on the page", chore.parts["box"].checked, "| the note:", page.element(world, "Tally").node.textContent)

print("== 4. Order: one sentence that makes several things become ==")
ORDER = '''Use the page library.
There is a card called First whose wording is "one".
There is a card called Second whose wording is "two".
There is a card called Third whose wording is "three".
There is a button called Finisher whose label is "All".
Let the trail be "".
Whenever a card becomes ticked:
  Set the trail to "{the trail}A:{the card} ".
Whenever a card becomes ticked:
  Set the trail to "{the trail}B:{the card} ".
Whenever Finisher becomes pressed:
  For each card:
    Now the card is ticked.
  Set the trail to "{the trail}end".
'''
world, _ = open_page(ORDER)
page.press(world, "Finisher")
print("   a loop of single changes:", world.globals.vars["trail"])

print("== 5. A failed answer: is the page left as the world is? ==")
FAIL = '''Use the page library.
There is a field called Entry whose wording is "" and whose hint is "type".
There is a card called Chore whose wording is "Sweep".
There is a note called Tally whose wording is "untouched".
Whenever a card becomes ticked:
  Set Tally's wording to "half done".
  Remember "ticked" under "probe".
  Fail because "no ticking today".
Whenever Entry becomes changed:
  If the length of Entry's wording is more than 3:
    Fail because "too long".
'''
world, said = open_page(FAIL)
page.tick(world, "Chore")
chore = page.element(world, "Chore")
print("   a tick whose answer fails:  thing ticked", "ticked" in chore.thing.marks, "| box ticked", chore.parts["box"].checked,
      "| note:", repr(page.element(world, "Tally").node.textContent), "| said:", said[-1])
print("   but what was remembered inside the failed answer stays:", page.STORE)
page.type_in(world, "Entry", "abc")
page.type_in(world, "Entry", "abcd")
entry = page.element(world, "Entry")
print("   typing a fourth letter whose answer fails:  thing", repr(entry.thing.fields["wording"]), "| box", repr(entry.node.value))

print("== 6. What the library gives each element for a reader who cannot see it ==")
world, _ = open_page(SOURCE, kept={"tasks": record(2, ticked=1)})
for name, parts in (("Banner", [None]), ("Entry", [None]), ("Adder", [None]), ("Everything", [None]), ("Notice", [None]),
                    ("Progress", [None]), ("card 1", [None, "box", "words", "tag", "star", "cross"])):
    binding = page.element(world, name)
    for part in parts:
        node = binding.node if part is None else binding.parts[part]
        keep = {key: value for key, value in node.attributes.items()
                if key.startswith("aria-") or key in ("role", "type", "title", "placeholder", "contenteditable")}
        print(f"   {name:10} {part or '':6} <{node.tag}> {keep}")

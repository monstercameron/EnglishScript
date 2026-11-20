"""The page library: things bound to the elements of a page.

There is no browser here, so the library uses its stand-in page. The tests
press, type and tick on it through the same listeners a browser would call.
"""
import unittest
from pathlib import Path

from englishscript import compile_source, lint
from englishscript.libraries import page

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def open_page(source, kept=None):
    """Run a program to its end. Gives the world and the lines it says (then and later)."""
    page.STORE.clear()
    page.STORE.update(kept or {})
    lines = []
    # Chapters and books are looked for in examples/, where the to-do list's book is.
    world = compile_source(source, folder=EXAMPLES).run(out=lambda text="": lines.append(str(text)))
    return world, lines


COUNTER = '''
Use the page library.
There is a heading called Banner whose wording is "A counter".
There is a panel called Strip.
There is a note called Tally whose wording is "0" and whose panel is Strip.
There is a button called Clicker whose label is "One more" and whose panel is Strip.
Let the count be 0.
Whenever Clicker becomes pressed:
  Add 1 to the count.
  Set Tally's wording to "{the count}".
'''


class ThingsAreElements(unittest.TestCase):
    def test_each_thing_gets_an_element_in_the_order_made(self):
        world, lines = open_page(COUNTER)
        self.assertEqual(page.sketch(world), "# A counter\n0  [One more]")
        # Without a browser the page is sketched when the program ends.
        self.assertEqual(lines[-2:], ["  # A counter", "  0  [One more]"])

    def test_an_element_sits_in_its_panel_even_if_the_panel_came_later(self):
        world, _ = open_page('''
Use the page library.
There is a panel called Top.
There is a panel called Bottom.
There is a note called Late whose wording is "in the top panel" and whose panel is Top.
There is a note called Loose whose wording is "on the page itself".
There is a note called Low whose wording is "in the bottom panel" and whose panel is Bottom.
''')
        self.assertEqual(page.sketch(world), "in the top panel\nin the bottom panel\non the page itself")
        top = page.element(world, "Top")
        self.assertIs(page.element(world, "Late").node.parent, top.parts["body"])

    def test_a_press_is_answered_and_the_page_follows(self):
        world, _ = open_page(COUNTER)
        page.press(world, "Clicker")
        page.press(world, "Clicker")
        self.assertEqual(page.element(world, "Tally").node.textContent, "2")
        self.assertEqual(page.sketch(world), "# A counter\n2  [One more]")

    def test_pressed_lasts_only_as_long_as_the_answer(self):
        world, _ = open_page(COUNTER)
        page.press(world, "Clicker")
        self.assertNotIn("pressed", page.element(world, "Clicker").thing.marks)

    def test_only_what_changed_is_written(self):
        world, _ = open_page(COUNTER)
        nodes = [page.element(world, name).node for name in ("Banner", "Strip", "Tally", "Clicker")]
        page.Node.LOG = []
        try:
            page.press(world, "Clicker")
            written = [(node.className, member, value) for node, member, value in page.Node.LOG]
        finally:
            page.Node.LOG = None
        self.assertEqual(written, [("es-note", "textContent", "1")])
        # The elements are the same ones: nothing was rebuilt.
        self.assertEqual([page.element(world, name).node for name in ("Banner", "Strip", "Tally", "Clicker")], nodes)

    def test_typing_changes_the_thing_and_the_thing_changes_the_box(self):
        world, _ = open_page('''
Use the page library.
There is a field called Entry whose wording is "" and whose hint is "Your name".
There is a note called Greeting whose wording is "".
Whenever Entry becomes entered:
  Set Greeting's wording to "Hello, {Entry's wording}.".
  Set Entry's wording to "".
''')
        entry = page.element(world, "Entry")
        self.assertEqual(entry.node.attributes["placeholder"], "Your name")
        page.type_in(world, "Entry", "Ada")
        self.assertEqual(entry.thing.fields["wording"], "Ada")
        self.assertEqual(page.element(world, "Greeting").node.textContent, "")
        page.type_in(world, "Entry", "Ada", enter=True)
        self.assertEqual(page.element(world, "Greeting").node.textContent, "Hello, Ada.")
        self.assertEqual(entry.node.value, "")  # the program emptied the box
        self.assertNotIn("entered", entry.thing.marks)

    def test_a_tick_box_is_bound_both_ways(self):
        world, _ = open_page('''
Use the page library.
There is a note called Tally whose wording is "".
There is a card called Chore whose wording is "Sweep".
There is a card called Errand whose wording is "Post a letter".
Now Errand is ticked.
Whenever a card becomes ticked:
  Set Tally's wording to "{the card} is done".
Whenever a card becomes not ticked:
  Set Tally's wording to "{the card} is to do again".
''')
        self.assertTrue(page.element(world, "Errand").parts["box"].checked)
        self.assertEqual(page.sketch(world), "[ ] Sweep\n[x] Post a letter")  # a note with no words takes no room
        page.tick(world, "Chore")
        self.assertIn("ticked", page.element(world, "Chore").thing.marks)
        self.assertEqual(page.element(world, "Tally").node.textContent, "Chore is done")
        page.tick(world, "Errand", False)
        self.assertEqual(page.element(world, "Tally").node.textContent, "Errand is to do again")
        self.assertEqual(page.element(world, "Errand").node.attributes["data-ticked"], "false")

    def test_removing_a_thing_removes_its_element_and_hiding_hides_it(self):
        world, _ = open_page('''
Use the page library.
There is a card called Chore whose wording is "Sweep".
There is a card called Errand whose wording is "Post a letter".
There is a button called Hider whose label is "Hide".
Whenever a card becomes dismissed:
  Remove the card.
Whenever Hider becomes pressed:
  For each card:
    Now the card is hidden.
''')
        chore = page.element(world, "Chore").node
        page.dismiss(world, "Chore")
        self.assertIsNone(chore.parent)
        with self.assertRaises(LookupError):
            page.element(world, "Chore")
        page.press(world, "Hider")
        self.assertTrue(page.element(world, "Errand").node.hidden)
        self.assertEqual(page.sketch(world), "[Hide]")

    def test_a_new_thing_joins_the_page_without_disturbing_the_rest(self):
        world, _ = open_page('''
Use the page library.
There is a panel called Roll.
There is a field called Entry whose wording is "".
Whenever Entry becomes entered:
  There is a new card whose wording is Entry's wording and whose panel is Roll.
''')
        roll, entry = page.element(world, "Roll"), page.element(world, "Entry").node
        page.type_in(world, "Entry", "One", enter=True)
        page.type_in(world, "Entry", "Two", enter=True)
        self.assertEqual([node.className for node in roll.parts["body"].children], ["es-card", "es-card"])
        self.assertIs(page.element(world, "Entry").node, entry)
        self.assertEqual(page.sketch(world), "[ ] One\n[ ] Two\n[_Two_]")

    def test_a_gauge_shows_its_share(self):
        world, _ = open_page('''
Use the page library.
There is a gauge called Progress whose level is 1 and whose limit is 4.
''')
        gauge = page.element(world, "Progress")
        self.assertEqual(gauge.parts["bar"].attributes["style"], "width: 25%")
        self.assertEqual(page.sketch(world), "|==........|")

    def test_what_is_remembered_is_there_next_time(self):
        source = '''
Use the page library.
Let the last be the memory of "visits" or else "never".
Say "Last time: {the last}."
Remember "once before" under "visits".
'''
        _, first = open_page(source)
        self.assertEqual(first[0], "Last time: never.")
        self.assertEqual(page.STORE, {"visits": "once before"})
        _, second = open_page(source, kept=dict(page.STORE))
        self.assertEqual(second[0], "Last time: once before.")

    def test_a_problem_in_an_answer_is_said_and_undone(self):
        world, lines = open_page('''
Use the page library.
There is a note called Tally whose wording is "untouched".
There is a button called Breaker whose label is "Break".
Whenever Breaker becomes pressed:
  Set Tally's wording to "half done".
  Fail because "the button is only for show".
''')
        before = len(lines)
        page.press(world, "Breaker")
        self.assertEqual(lines[before:], ["That could not be done: the button is only for show"])
        self.assertEqual(page.element(world, "Tally").node.textContent, "untouched")
        self.assertNotIn("pressed", page.element(world, "Breaker").thing.marks)

    def test_a_program_without_the_library_is_not_given_a_page(self):
        _, lines = open_page('Say "Hello."')
        self.assertEqual(lines, ["Hello."])

    def test_a_star_a_tag_and_an_order(self):
        world, _ = open_page('''
Use the page library.
There is a card called Chore whose wording is "Sweep".
There is a card called Errand whose wording is "Post a letter" and whose tag is "town".
There is a card called Visit whose wording is "See Ada".
Whenever a card becomes starred:
  Set the card's order to 0 - 1.
Whenever a card becomes not starred:
  Set the card's order to 0.
''')
        self.assertEqual(page.sketch(world), "[ ] Sweep\n[ ] Post a letter  #town\n[ ] See Ada")
        errand = page.element(world, "Errand")
        self.assertEqual(errand.parts["tag"].textContent, "town")
        self.assertTrue(page.element(world, "Chore").parts["tag"].hidden)
        page.star(world, "Visit")
        # A lower order comes first, and the rest keep the order they were made in.
        self.assertEqual(page.sketch(world), "[ ] * See Ada\n[ ] Sweep\n[ ] Post a letter  #town")
        self.assertEqual(page.element(world, "Visit").parts["star"].attributes["aria-pressed"], "true")
        page.star(world, "Visit")
        self.assertEqual(page.sketch(world), "[ ] Sweep\n[ ] Post a letter  #town\n[ ] See Ada")

    def test_only_the_card_that_is_out_of_place_is_moved(self):
        world, _ = open_page('''
Use the page library.
There is a card called One whose wording is "one".
There is a card called Two whose wording is "two".
There is a card called Three whose wording is "three".
There is a button called Lifter whose label is "Lift the last".
Whenever Lifter becomes pressed:
  Set Three's order to 0 - 1.
''')
        moved = []
        root = page.element(world, "One").node.parent
        insert = type(root).insertBefore
        try:
            type(root).insertBefore = lambda self, child, before: (moved.append(child.attributes["data-name"]), insert(self, child, before))[1]
            page.press(world, "Lifter")
        finally:
            type(root).insertBefore = insert
        self.assertEqual(moved, ["Three"])
        self.assertEqual([node.attributes["data-name"] for node in root.children], ["Three", "One", "Two", "Lifter"])

    def test_a_card_s_words_can_be_edited_where_they_stand(self):
        world, _ = open_page('''
Use the page library.
There is a note called Tally whose wording is "".
There is a card called Chore whose wording is "Sweep".
Whenever a card becomes reworded:
  Set Tally's wording to "Now it says {the card's wording}.".
''')
        page.reword(world, "Chore", "  Sweep   the  hall ")
        chore = page.element(world, "Chore")
        self.assertEqual(chore.thing.fields["wording"], "Sweep the hall")  # one line, with no loose spaces
        self.assertEqual(chore.parts["words"].textContent, "Sweep the hall")
        self.assertEqual(page.element(world, "Tally").node.textContent, "Now it says Sweep the hall.")
        self.assertNotIn("reworded", chore.thing.marks)
        # Leaving the words as they were is not a rewording.
        page.element(world, "Tally").thing.fields["wording"] = "untouched"
        page.reword(world, "Chore", "Sweep the hall")
        self.assertEqual(page.element(world, "Tally").thing.fields["wording"], "untouched")
        # Enter finishes an edit, and Escape gives it up.
        chore.parts["words"].textContent = "Dust"
        chore.parts["words"].fire("keydown", key="Enter")
        self.assertEqual(chore.thing.fields["wording"], "Dust")
        chore.parts["words"].textContent = "Something else"
        chore.parts["words"].fire("keydown", key="Escape")
        self.assertEqual((chore.thing.fields["wording"], chore.parts["words"].textContent), ("Dust", "Dust"))

    def test_typing_is_something_a_program_can_answer(self):
        world, _ = open_page('''
Use the page library.
There is a field called Finder whose wording is "".
There is a card called Chore whose wording is "Sweep".
There is a card called Errand whose wording is "Post a letter".
Whenever Finder becomes changed:
  For each card:
    If the card's wording in lower case contains Finder's wording in lower case:
      Now the card is not hidden.
    Otherwise:
      Now the card is hidden.
''')
        page.type_in(world, "Finder", "POST")
        self.assertEqual(page.sketch(world), "[_POST_]\n[ ] Post a letter")
        self.assertNotIn("changed", page.element(world, "Finder").thing.marks)
        page.type_in(world, "Finder", "")
        self.assertEqual(page.sketch(world), "[_ _]\n[ ] Sweep\n[ ] Post a letter".replace("[_ _]", "[__]"))


class MoreKindsOfElement(unittest.TestCase):
    def test_a_picture_and_a_link(self):
        world, _ = open_page('''
Use the page library.
There is a picture called Plate whose source is "assets/triangle-gpu.png" and whose caption is "A shaded triangle".
There is a link called Onward whose wording is "The grammar" and whose target is "reference.html#s9-6".
''')
        plate, onward = page.element(world, "Plate").node, page.element(world, "Onward").node
        self.assertEqual((plate.tag, plate.attributes["src"], plate.attributes["alt"]),
                         ("img", "assets/triangle-gpu.png", "A shaded triangle"))
        self.assertEqual((onward.tag, onward.attributes["href"], onward.textContent), ("a", "reference.html#s9-6", "The grammar"))
        self.assertEqual(page.sketch(world), "(picture: A shaded triangle)\nThe grammar -> reference.html#s9-6")

    def test_an_address_cannot_carry_a_script(self):
        for address, allowed in (("https://example.org/a?b=c", True), ("page.html", True), ("#top", True),
                                 ("mailto:ada@example.org", True), ("javascript:alert(1)", False),
                                 (" JavaScript:alert(1)", False), ("data:text/html,<script>", False),
                                 ("vbscript:x", False), ("a/b:c", True)):
            with self.subTest(address):
                self.assertEqual(page._safe(address) != "", allowed)
        self.assertNotEqual(page._safe("data:image/png;base64,AAAA", pictures=True), "")
        self.assertEqual(page._safe("data:image/svg+xml,<svg onload=x>", pictures=True), "")
        self.assertEqual(page._safe("mailto:ada@example.org", pictures=True), "")
        world, _ = open_page('''
Use the page library.
There is a link called Trap whose wording is "Click" and whose target is "javascript:alert(1)".
''')
        self.assertNotIn("href", page.element(world, "Trap").node.attributes)
        self.assertEqual(page.sketch(world), "Click -> (nowhere)")

    def test_a_table_of_rows_and_cells(self):
        world, _ = open_page('''
Use the page library.
There is a table called Ledger whose title is "Accounts".
There is a row called Head whose table is Ledger.
Now Head is leading.
There is a new cell whose wording is "Name" and whose row is Head.
There is a new cell whose wording is "Balance" and whose row is Head.
There is a row called First whose table is Ledger.
There is a cell called Who whose wording is "Ada" and whose row is First.
There is a cell called Sum whose wording is "$40" and whose row is First.
There is a button called Payer whose label is "Pay Ada".
Whenever Payer becomes pressed:
  Set Sum's wording to "$90".
''')
        ledger = page.element(world, "Ledger")
        self.assertEqual((ledger.node.tag, ledger.parts["title"].textContent), ("table", "Accounts"))
        rows = ledger.parts["body"].children
        self.assertEqual([row.tag for row in rows], ["tr", "tr"])
        self.assertEqual([cell.textContent for cell in rows[1].children], ["Ada", "$40"])
        self.assertEqual(rows[0].children[0].attributes["role"], "columnheader")
        self.assertEqual(rows[1].children[0].attributes["role"], "cell")
        self.assertEqual(page.sketch(world).splitlines()[:4],
                         ["-- Accounts --", "| Name | Balance |", "|------|---------|", "| Ada | $40 |"])
        page.Node.LOG = []
        try:
            page.press(world, "Payer")
            written = [(node.className, member, value) for node, member, value in page.Node.LOG]
        finally:
            page.Node.LOG = None
        self.assertEqual(written, [("es-cell", "textContent", "$90")])  # one cell, and nothing else

    def test_a_menu_and_the_option_picked(self):
        world, _ = open_page('''
Use the page library.
There is a menu called Season whose hint is "Which season?".
There is an option called Spring whose wording is "Spring" and whose menu is Season.
There is an option called Autumn whose wording is "Autumn" and whose menu is Season.
There is a note called Verdict whose wording is "".
Whenever an option becomes picked:
  Set Verdict's wording to "{the option's wording} it is.".
''')
        season = page.element(world, "Season")
        self.assertEqual(season.node.tag, "select")
        self.assertEqual(season.node.attributes["aria-label"], "Which season?")
        self.assertTrue(season.parts["blank"].selected)  # nothing is picked, so the hint shows
        self.assertEqual(page.sketch(world), "{(Which season?) v}")
        page.pick(world, "Autumn")
        self.assertEqual(page.element(world, "Verdict").node.textContent, "Autumn it is.")
        self.assertTrue(page.element(world, "Autumn").node.selected)
        self.assertFalse(season.parts["blank"].selected)
        page.pick(world, "Spring")
        self.assertEqual([name for name in ("Spring", "Autumn") if "picked" in page.element(world, name).thing.marks], ["Spring"])
        self.assertEqual(page.sketch(world), "{Spring v}\nSpring it is.")

    def test_a_panel_inside_a_panel(self):
        world, _ = open_page('''
Use the page library.
There is a panel called Outer whose title is "Outer".
There is a panel called Inner whose title is "Inner" and whose panel is Outer.
There is a note called Deep whose wording is "inside both" and whose panel is Inner.
There is a note called Shallow whose wording is "inside one" and whose panel is Outer.
''')
        outer, inner = page.element(world, "Outer"), page.element(world, "Inner")
        self.assertIs(inner.node.parent, outer.parts["body"])
        self.assertIs(page.element(world, "Deep").node.parent, inner.parts["body"])
        self.assertEqual(page.sketch(world), "-- Outer --\n  -- Inner --\n  inside both\ninside one")

    def test_panels_inside_each_other_go_on_the_page(self):
        world, _ = open_page('''
Use the page library.
There is a panel called Left whose title is "Left".
There is a panel called Right whose title is "Right" and whose panel is Left.
Set Left's panel to Right.
''')
        root_node = page._state(world)["backend"].root
        self.assertIn(page.element(world, "Left").node.parent, (root_node, page.element(world, "Right").parts["body"]))
        # No element is its own ancestor.
        node, seen = page.element(world, "Left").node, set()
        while node is not None:
            self.assertNotIn(id(node), seen)
            seen.add(id(node))
            node = node.parent

    def test_a_cell_with_no_row_is_nowhere(self):
        world, _ = open_page('''
Use the page library.
There is a table called Ledger.
There is a row called Only whose table is Ledger.
There is a cell called Lone whose wording is "x" and whose row is Only.
Remove Lone.
''')
        self.assertEqual(page.element(world, "Only").node.children, [])


class TheWebAlmanac(unittest.TestCase):
    """examples/web_almanac.english: a menu, a table and a link over three chapters."""

    source = (EXAMPLES / "web_almanac.english").read_text(encoding="utf-8")

    def rows(self, world):
        return [line for line in page.sketch(world).splitlines() if line.startswith("| ")]

    def test_it_is_free_of_lint(self):
        self.assertEqual([p.render() for p in lint(self.source, folder=EXAMPLES)], [])

    def test_the_table_is_set_out_for_the_year_as_the_page_opens(self):
        world, _ = open_page(self.source)
        rows = self.rows(world)
        self.assertEqual(rows[0], "| Feast | Date | Falls on a |")
        self.assertEqual(rows[1], "| Candlemas | 2 February | Tuesday |")
        self.assertEqual(rows[-1], "| Christmas | 25 December | Saturday |")
        self.assertEqual(len(rows), 8)
        self.assertIn("{MMXXVII v}  MMXXVII is a common year of 365 days.", page.sketch(world))
        self.assertEqual(world.examples, 9)

    def test_picking_a_year_sets_the_table_out_again(self):
        import datetime

        world, _ = open_page(self.source)
        option = next(binding.thing.name for binding in page._state(world)["bound"].values()
                      if binding.thing.kind == "option" and binding.thing.fields["wording"] == "MMXXVIII")
        page.pick(world, option)
        rows = self.rows(world)
        self.assertEqual(len(rows), 8)
        self.assertEqual(rows[-1], f"| Christmas | 25 December | {datetime.date(2028, 12, 25):%A} |")
        self.assertIn("MMXXVIII is a leap year of 366 days.", page.sketch(world))
        # The cells of the year before are gone from the page as well as from the world.
        self.assertEqual(len(world.things["cell"]), 24)
        self.assertEqual(sum(len(row.children) for row in page.element(world, "Roster").parts["body"].children), 24)


class ThreeCounters(unittest.TestCase):
    """examples/web_counters.english: one thing made three times, by a kind and a verb."""

    source = (EXAMPLES / "web_counters.english").read_text(encoding="utf-8")

    def test_it_is_free_of_lint(self):
        self.assertEqual([p.render() for p in lint(self.source, folder=EXAMPLES)], [])

    def press(self, world, title, which):
        counter = next(thing for thing in world.things["counter"] if thing.fields["title"] == title)
        page.press(world, counter.fields[which])

    def test_each_counter_keeps_its_own_count(self):
        world, _ = open_page(self.source)
        self.press(world, "Pears", "raiser")
        self.press(world, "Pears", "raiser")
        self.press(world, "Plums", "raiser")
        self.press(world, "Pears", "lowerer")
        self.assertEqual(page.sketch(world).splitlines(), [
            "# Counters", "2 counted in all.",
            "-- Apples --", "0  [One more]  [One fewer]",
            "-- Pears --", "1  [One more]  [One fewer]",
            "-- Plums --", "1  [One more]  [One fewer]"])

    def test_a_count_cannot_go_below_nothing_and_the_page_is_left_alone(self):
        world, lines = open_page(self.source)
        before, said = page.sketch(world), len(lines)
        self.press(world, "Apples", "lowerer")
        self.assertEqual(page.sketch(world), before)
        self.assertEqual(len(lines), said + 1)
        self.assertIn("never less than 0", lines[-1])


class ForAReaderWhoCannotSeeThePage(unittest.TestCase):
    """What the library tells a screen reader, without the program asking."""

    def setUp(self):
        self.world, _ = open_page('''
Use the page library.
There is a field called Entry whose wording is "" and whose hint is "What needs doing?".
There is a button called Adder whose label is "Add".
There is a note called Tally whose wording is "2 to do".
There is a gauge called Progress whose level is 1 and whose limit is 4.
There is a panel called Sieve.
There is a button called Everything whose label is "All" and whose panel is Sieve.
There is a button called Waiting whose label is "To do" and whose panel is Sieve.
There is a panel called Roll.
There is a card called Chore whose wording is "Sweep" and whose panel is Roll.
There is a card called Errand whose wording is "Post a letter" and whose panel is Roll.
Whenever Waiting becomes pressed:
  Now Waiting is chosen.
Whenever Adder becomes pressed:
  Set Chore's wording to "Sweep the hall".
''')

    def attributes(self, name, part=None):
        binding = page.element(self.world, name)
        return (binding.node if part is None else binding.parts[part]).attributes

    def test_a_field_s_hint_is_also_its_name(self):
        self.assertEqual(self.attributes("Entry")["aria-label"], "What needs doing?")

    def test_a_note_is_spoken_when_it_changes(self):
        self.assertEqual(self.attributes("Tally")["role"], "status")

    def test_a_gauge_says_its_range_and_its_level_in_words(self):
        gauge = self.attributes("Progress")
        self.assertEqual((gauge["aria-valuemin"], gauge["aria-valuenow"], gauge["aria-valuemax"]), ("0", "25", "100"))
        self.assertEqual(gauge["aria-valuetext"], "1 of 4")

    def test_only_a_button_that_is_a_choice_is_a_switch(self):
        for name in ("Adder", "Everything", "Waiting"):
            self.assertNotIn("aria-pressed", self.attributes(name), name)
        page.press(self.world, "Waiting")
        self.assertEqual(self.attributes("Waiting")["aria-pressed"], "true")
        self.assertEqual(self.attributes("Everything")["aria-pressed"], "false")  # it stands with a chosen one
        self.assertNotIn("aria-pressed", self.attributes("Adder"))  # an ordinary button, elsewhere

    def test_each_part_of_a_card_names_the_card(self):
        self.assertEqual(self.attributes("Chore", "cross")["aria-label"], "Remove: Sweep")
        self.assertEqual(self.attributes("Chore", "star")["aria-label"], "Star: Sweep")
        self.assertEqual(self.attributes("Chore", "box")["aria-label"], "Done: Sweep")
        page.press(self.world, "Adder")
        self.assertEqual(self.attributes("Chore", "cross")["aria-label"], "Remove: Sweep the hall")

    def test_cards_are_a_list(self):
        roll = page.element(self.world, "Roll")
        self.assertEqual(roll.parts["body"].attributes["role"], "list")
        self.assertEqual(self.attributes("Chore")["role"], "listitem")
        self.assertNotIn("role", page.element(self.world, "Sieve").parts["body"].attributes)


class TheWebToDoList(unittest.TestCase):
    """examples/web_todo.english and its book of chapters, used the way a person would use the page."""

    source = (EXAMPLES / "web_todo.english").read_text(encoding="utf-8")
    KEY = "tasks"

    def cards(self, world):
        return [line.strip() for line in page.sketch(world).splitlines() if line.strip()[:3] in ("[ ]", "[x]")]

    def says(self, world, name):
        return page.element(world, name).node.textContent

    def test_the_program_and_every_chapter_are_free_of_lint(self):
        self.assertEqual([p.render() for p in lint(self.source, folder=EXAMPLES)], [])
        chapters = sorted((EXAMPLES / "tasks").glob("*.english"))
        self.assertEqual([path.stem for path in chapters], ["cards", "keeping", "layout", "showing"])
        for path in chapters:
            with self.subTest(path.name):
                self.assertEqual([p.render() for p in lint(path.read_text(encoding="utf-8"), folder=path.parent)], [])

    def test_the_work_is_in_the_chapters(self):
        # The program itself only says which chapters it uses and what happens when.
        sentences = [line for line in self.source.splitlines() if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(sum(1 for line in sentences if line.startswith("Use the ")), 5)
        self.assertGreaterEqual(sum(1 for line in sentences if line.startswith("Whenever ")), 10)
        # Nothing is brought up to date by hand: the chapters say what is kept, and the
        # program only saves the list, once, when everything has settled.
        self.assertIn("Whenever everything has settled:", sentences)
        self.assertEqual(sum(1 for line in sentences if line.strip() == "Save."), 1)
        chapters = "".join(path.read_text(encoding="utf-8") for path in (EXAMPLES / "tasks").glob("*.english"))
        kept = [line for line in chapters.splitlines() if line.startswith("Keep ")]
        self.assertGreaterEqual(len(kept), 9)
        self.assertNotIn("\n  Now the card is hidden.", chapters)
        self.assertFalse(any(line.startswith(("There is", "A card", "Let ")) for line in sentences))

    def test_a_chapter_s_own_words_stay_its_own(self):
        for sentence, word in (('Say "{the showing}"', "showing"), ('If the spare is nothing:\n  Say "none"', "spare"),
                               ('Revive "- - - Sneak in".', "revive"), ("Now Banner is hidden.", "Banner")):
            with self.subTest(word):
                with self.assertRaises(Exception) as caught:
                    open_page(self.source + "\n" + sentence + "\n")
                self.assertIn("does not share it", str(caught.exception))

    def test_a_first_visit_shows_three_things_to_do(self):
        world, _ = open_page(self.source)
        self.assertEqual(self.cards(world), ["[ ] * Write a sentence the compiler refuses", "[ ] Read the treatise",
                                             "[ ] Tick this one off  #page"])
        self.assertEqual(self.says(world, "Tally"), "3 of 3 still to do.")
        self.assertEqual(self.says(world, "Everything"), "All (3)")
        self.assertEqual(page.element(world, "Everything").node.attributes["aria-pressed"], "true")
        for name in ("Sweeper", "Restorer"):
            self.assertTrue(page.element(world, name).node.hidden, name)
        self.assertFalse(page.element(world, "Finisher").node.hidden)

    def test_adding_with_a_tag_and_refusing_blanks_and_twins(self):
        world, _ = open_page(self.source, kept={self.KEY: ""})
        self.assertEqual(self.says(world, "Tally"), "Nothing to do. Write something above.")
        page.type_in(world, "Entry", "Buy milk #home")
        page.press(world, "Adder")
        page.type_in(world, "Entry", "  Walk   the dog ", enter=True)
        self.assertEqual(self.cards(world), ["[ ] Buy milk  #home", "[ ] Walk the dog"])
        self.assertEqual(page.element(world, "Entry").node.value, "")
        self.assertEqual(page.STORE[self.KEY], "- - home Buy milk\n- - - Walk the dog\n")
        # A blank is not added, and the reader is told why.
        page.press(world, "Adder")
        self.assertEqual(self.says(world, "Notice"), "Not added: there is nothing to write down.")
        # Nor is something already on the list, and what was typed is left for mending.
        page.type_in(world, "Entry", "Buy milk", enter=True)
        self.assertEqual(self.says(world, "Notice"), 'Not added: "Buy milk" is on the list already.')
        self.assertEqual(page.element(world, "Entry").node.value, "Buy milk")
        self.assertEqual(len(self.cards(world)), 2)
        page.type_in(world, "Entry", "Buy bread", enter=True)
        self.assertEqual(self.says(world, "Notice"), "")
        self.assertEqual(len(self.cards(world)), 3)

    def test_stars_go_first_and_finished_cards_last(self):
        world, _ = open_page(self.source, kept={self.KEY: "- - - One\n- - - Two\n- - - Three\n"})
        page.star(world, "card 3")
        self.assertEqual(self.cards(world), ["[ ] * Three", "[ ] One", "[ ] Two"])
        page.tick(world, "card 1")
        self.assertEqual(self.cards(world), ["[ ] * Three", "[ ] Two", "[x] One"])
        page.tick(world, "card 3")
        self.assertEqual(self.cards(world), ["[ ] Two", "[x] One", "[x] * Three"])
        self.assertEqual(page.STORE[self.KEY], "x - - One\n- - - Two\nx * - Three\n")
        page.star(world, "card 3")
        page.tick(world, "card 1", False)
        self.assertEqual(self.cards(world), ["[ ] One", "[ ] Two", "[x] Three"])

    def test_views_counts_and_finding(self):
        world, _ = open_page(self.source, kept={self.KEY: "- - home Buy milk\nx - - Walk the dog\n- - town Write home\n"})
        self.assertEqual([self.says(world, name) for name in ("Everything", "Waiting", "Finished")],
                         ["All (3)", "Still to do (2)", "Done (1)"])
        self.assertEqual(page.element(world, "Progress").parts["bar"].attributes["style"], "width: 33%")
        page.press(world, "Waiting")
        self.assertEqual(self.cards(world), ["[ ] Buy milk  #home", "[ ] Write home  #town"])
        self.assertEqual(page.element(world, "Waiting").node.attributes["aria-pressed"], "true")
        self.assertEqual(page.element(world, "Everything").node.attributes["aria-pressed"], "false")
        page.press(world, "Finished")
        self.assertEqual(self.cards(world), ["[x] Walk the dog"])
        page.tick(world, "card 2", False)  # no longer done, so it leaves this view
        self.assertEqual(self.cards(world), [])
        page.press(world, "Everything")
        # Finding looks at the words and the tag, whatever the capitals.
        page.type_in(world, "Finder", "HOME")
        self.assertEqual(self.cards(world), ["[ ] Buy milk  #home", "[ ] Write home  #town"])
        page.type_in(world, "Finder", "#town")
        self.assertEqual(self.cards(world), ["[ ] Write home  #town"])
        page.type_in(world, "Finder", "")
        self.assertEqual(len(self.cards(world)), 3)

    def test_removing_and_putting_back(self):
        world, _ = open_page(self.source, kept={self.KEY: "- * home Buy milk\n- - - Walk the dog\n"})
        page.dismiss(world, "card 1")
        self.assertEqual(self.cards(world), ["[ ] Walk the dog"])
        self.assertEqual(self.says(world, "Notice"), '"Buy milk" was removed.')
        self.assertFalse(page.element(world, "Restorer").node.hidden)
        self.assertEqual(page.STORE[self.KEY], "- - - Walk the dog\n")
        page.press(world, "Restorer")
        self.assertEqual(self.cards(world), ["[ ] * Buy milk  #home", "[ ] Walk the dog"])  # with its star and its tag
        self.assertEqual(self.says(world, "Notice"), "")
        self.assertTrue(page.element(world, "Restorer").node.hidden)

    def test_editing_a_card_and_rubbing_one_out(self):
        world, _ = open_page(self.source, kept={self.KEY: "- - - Buy milk\n- - - Walk the dog\n"})
        page.reword(world, "card 1", "Buy oat milk")
        self.assertEqual(self.cards(world), ["[ ] Buy oat milk", "[ ] Walk the dog"])
        self.assertEqual(page.STORE[self.KEY], "- - - Buy oat milk\n- - - Walk the dog\n")
        page.reword(world, "card 2", "")
        self.assertEqual(self.cards(world), ["[ ] Buy oat milk"])
        page.press(world, "Restorer")
        self.assertEqual(len(self.cards(world)), 1)  # a card with no words is not worth putting back

    def test_ticking_them_all_and_clearing_what_is_done(self):
        world, _ = open_page(self.source, kept={self.KEY: "- - - One\n- - - Two\n- - - Three\n"})
        page.press(world, "Finisher")
        self.assertEqual(self.says(world, "Tally"), "All 3 done.")
        self.assertTrue(page.element(world, "Finisher").node.hidden)
        self.assertEqual(page.element(world, "Progress").parts["bar"].attributes["style"], "width: 100%")
        page.tick(world, "card 2", False)
        page.press(world, "Sweeper")
        self.assertEqual(self.cards(world), ["[ ] Two"])
        self.assertTrue(page.element(world, "Sweeper").node.hidden)
        page.press(world, "Restorer")  # the last of those cleared comes back
        self.assertEqual(self.cards(world), ["[ ] Two", "[x] Three"])

    def test_however_much_a_click_changes_the_list_is_saved_once(self):
        world, _ = open_page(self.source, kept={self.KEY: "".join(f"- - - Task {n}{chr(10)}" for n in range(1, 31))})
        backend = page._state(world)["backend"]
        saves, keep = [], backend.keep
        backend.keep = lambda key, line: (saves.append(key), keep(key, line))[1]
        page.press(world, "Finisher")  # thirty cards ticked by one press
        self.assertEqual(saves, ["tasks"])
        self.assertEqual(self.says(world, "Tally"), "All 30 done.")
        page.type_in(world, "Entry", "A")  # a letter typed changes no card, so nothing is saved
        page.type_in(world, "Finder", "task 1")
        self.assertEqual(saves, ["tasks"])
        self.assertEqual(len(self.cards(world)), 11)  # Task 1, and Task 10 to Task 19

    def test_the_list_comes_back_as_it_was_left(self):
        world, _ = open_page(self.source, kept={self.KEY: ""})
        page.type_in(world, "Entry", "Buy milk #home", enter=True)
        page.type_in(world, "Entry", "Walk the dog", enter=True)
        page.tick(world, "card 2")
        page.star(world, "card 1")
        again, _ = open_page(self.source, kept=dict(page.STORE))
        self.assertEqual(self.cards(again), ["[ ] * Buy milk  #home", "[x] Walk the dog"])


if __name__ == "__main__":
    unittest.main()

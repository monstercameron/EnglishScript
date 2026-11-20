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
There is a panel called Row.
There is a note called Tally whose wording is "0" and whose panel is Row.
There is a button called Clicker whose label is "One more" and whose panel is Row.
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
        nodes = [page.element(world, name).node for name in ("Banner", "Row", "Tally", "Clicker")]
        page.Node.LOG = []
        try:
            page.press(world, "Clicker")
            written = [(node.className, member, value) for node, member, value in page.Node.LOG]
        finally:
            page.Node.LOG = None
        self.assertEqual(written, [("es-note", "textContent", "1")])
        # The elements are the same ones: nothing was rebuilt.
        self.assertEqual([page.element(world, name).node for name in ("Banner", "Row", "Tally", "Clicker")], nodes)

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
        self.assertGreaterEqual(sum(1 for line in sentences if line.startswith("Whenever ")), 14)
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

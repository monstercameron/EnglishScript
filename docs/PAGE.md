# The page library

`Use the page library.` lets an EnglishScript program be a web page. It adds seven kinds of thing, and each thing of one of those kinds **is** an element of the page. The program never touches the page. It makes things and changes them, and the page follows; a person presses and types, and the things change.

`examples/web_todo.english` is a to-do list written this way, and [the page called "A page"](todo.html) runs it. Its work is divided among four chapters of the book in `examples/tasks`: what is on the page, what a task is, which cards are in sight, and what is remembered.

```text
Use the page library.

There is a heading called Banner whose wording is "A counter".
There is a note called Tally whose wording is "0".
There is a button called Clicker whose label is "One more".

Let the count be 0.

Whenever Clicker becomes pressed:
  Add 1 to the count.
  Set Tally's wording to "{the count}".
```

## What is on a page

| Kind | What it is | Properties | Adjectives |
|---|---|---|---|
| `panel` | A box that holds other elements, side by side where they fit | `title (text, if any)` | `hidden` |
| `heading` | A title | `wording (text)`, `panel (panel, if any)` | `hidden` |
| `note` | A line of text | `wording (text)`, `panel (panel, if any)` | `hidden` |
| `field` | A box to type in | `wording (text)`, `hint (text, if any)`, `panel (panel, if any)` | `changed`, `entered`, `hidden` |
| `button` | Something to press | `label (text)`, `panel (panel, if any)` | `pressed`, `chosen`, `hidden` |
| `card` | A line with a tick box, words that can be edited where they stand, a tag, a star, and a cross to dismiss it | `wording (text)`, `tag (text, if any)`, `order (number, if any)`, `panel (panel, if any)` | `ticked`, `starred`, `reworded`, `dismissed`, `hidden` |
| `gauge` | A bar that shows how far along something is | `level (number)`, `limit (number)`, `panel (panel, if any)` | `hidden` |

These are ordinary kinds. Everything the language does with a kind works on them: `For each ticked card:`, `the number of cards`, `A card is open when it is not ticked.`, `Remove the card.`

**Where an element goes.** Elements appear in the order their things were made. An element whose `panel` is given sits inside that panel, again in the order made. A panel lays its elements out in a row and wraps them; a card always takes a whole line.

**The order of cards.** A card may be given an `order`, which is a number. Cards with a lower order come first. Cards with the same order, or with none (which counts as 0), stay in the order they were made. The language has no sentence for sorting, and does not need one here: a program says which sort each card belongs to, and the page keeps them in place.

```text
For each card:
  If the card is ticked:
    Set the card's order to 2.
  Otherwise if the card is starred:
    Set the card's order to 0.
  Otherwise:
    Set the card's order to 1.
```

Only a card that is out of place is moved. The others are left exactly as they are.

## The binding

The program to the page:

| The program says | The page shows |
|---|---|
| `There is a new card whose wording is "Buy milk".` | A new line |
| `Set Tally's wording to "2 left".` | The note's words change |
| `Set Entry's wording to "".` | The box is emptied |
| `Now the card is ticked.` | Its box is ticked |
| `Now the card is starred.` | Its star is filled in |
| `Set the card's tag to "home".` | A small label, `#home`, beside its words |
| `Set the card's order to 0.` | It moves to stand before cards of a higher order |
| `Now the card is hidden.` / `Now the card is not hidden.` | It leaves the page, or returns |
| `Now Everything is chosen.` | The button is shown as the one in force |
| `Set Progress's level to 3.` | The bar grows |
| `Remove the card.` | The line is gone |

The page to the program:

| A person | In the program |
|---|---|
| types in a field | the field's `wording` is what they have typed, and the field becomes `changed` |
| presses Enter in a field | the field becomes `entered` |
| presses a button | the button becomes `pressed` |
| ticks or unticks a card's box | the card becomes `ticked`, or becomes not `ticked` |
| presses a card's star | the card becomes `starred`, or becomes not `starred` |
| edits a card's words where they stand, and leaves them | the card's `wording` is the new words, and the card becomes `reworded` |
| presses a card's cross | the card becomes `dismissed` |

The program answers with `Whenever` (see [the reference](SYNTAX.md)):

```text
Whenever a card becomes dismissed:
  Remove the card.
```

Five of these adjectives are **momentary**: `pressed`, `changed`, `entered`, `reworded` and `dismissed` last only while the program's answer is being carried out. They do not "become not" afterwards, so a `Whenever ... becomes not pressed:` is never set off by them.

A card's words are edited by clicking on them. Enter or leaving the words finishes the edit, and Escape gives it up. The words are kept as one line: spaces at the ends are dropped and runs of spaces become one. Leaving the words as they were is not a rewording.

If an answer runs into a problem, such as a rule that would be broken or a `Fail because`, everything it changed is put back, as after a failed `Try`, and the problem is said.

After every answer, the library compares the things with the elements and writes only what differs. An element stays the same element for as long as its thing exists, so a box that is being typed in is never rebuilt.

## Remembering

```text
Remember <text> under <text>.
the memory of <text>
```

`Remember` keeps a text under a key, in the browser's own storage, so that it is there the next time the page is opened. `the memory of` a key is that text, or `nothing` if nothing has been kept under it.

```text
Let the last be the memory of "visits" or else "never".
Remember "once before" under "visits".
```

Nothing that is remembered leaves the browser.

## Without a browser

Run from the command line, there is no page to show. The library keeps a stand-in for one in memory, and when the program ends it sketches the page in text:

```text
$ python -m englishscript examples/web_todo.english

The page, as it stands (there is no browser here to show it):
  # Things to do
  [_(What needs doing? Add a #tag if you like.)_]  [Add]
  <All (3)>  [Still to do (3)]  [Done (0)]  [_(Find)_]
  [ ] * Write a sentence the compiler refuses
  [ ] Read the treatise
  [ ] Tick this one off  #page
  3 of 3 still to do.  |..........|
  [Tick them all]
```

What is remembered there lasts only as long as Python runs. The tests use the stand-in to press, type and tick without a browser: see `tests/test_page.py`.

## Putting a program on a page of your own

The compiler is Python, and it runs in a browser as WebAssembly through Pyodide, as [the machinery](how.html) explains. A page needs three things:

1. An element for the library to build in: `<main id="englishscript-page"></main>`. Without one, the library adds its own at the end of the document.
2. The compiler, loaded into Pyodide. `docs/play/engine.js` does this for the pages of this site.
3. A few lines of Python to compile the program and run it. Once its sentences have been carried out, the page stays alive and answers what people do:

```python
from englishscript import compile_source

compile_source(source).run(out=show_a_line, ask=ask_a_question)
```

The library gives each element a class named after its kind (`es-heading`, `es-field`, `es-button`, `es-card`, `es-note`, `es-gauge`, `es-panel`) and the attributes `data-kind` and `data-name`. The parts of a card have classes of their own (`es-card-box`, `es-card-words`, `es-card-tag`, `es-card-star`, `es-card-cross`), and a card carries `data-ticked` and `data-starred`. It sets no styles of its own: how the page looks is the business of the page's style sheet. `docs/todo.html` is a complete example.

When a thing is removed, its element is given the attribute `data-leaving` and stays for a quarter of a second before it goes, so that a style sheet can show it leave. A reader who has asked for reduced motion gets no such pause.

## What it does not do

- There are seven kinds of element. There are no pictures, links, tables or menus yet.
- Only cards can be put in an order of the program's choosing. Everything else stands in the order made.
- A program cannot ask where the pointer is, or what key was pressed, beyond Enter in a field.
- A panel cannot be put inside a panel.
- The program's own sentences are carried out before the page is first shown, so a long calculation at the top delays it.

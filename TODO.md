# To do

## Pokémon Red demo

- Turn the progress flags into stored adjectives. Journey keeps parcel, dex, badge, tm34, town map, blue house entered, daisy walking and route rival beaten as 0/1 numbers in [foundation.english](docs/red/foundation.english). Story keeps forest one, two and three beaten and gym trainer beaten in [story.english](docs/red/story.english). The bridge must still publish badge and tm34 to the page as 0 and 1.
- Keep "route rival beaten" in one place. Story and Journey both store it, and [maps.english](docs/red/maps.english) reads Journey's.
- Make the remaining text states choices:
  - Combat's outcome needs a named value for "no outcome yet".
  - Team's result shares words with the outcome, and a choice word may belong to only one set.
  - Story's scene is the key of a fact table.
  - Journey's stage starts as "", and facing starts as "down".
  - The bridge writes Talk's command, and `reply` is a reserved word.
- Draw glyphs from bitmap tables instead of the stroke runs in [lettering.english](docs/red/lettering.english). A pixel-identical bitmap version drew text 2.4 times slower, so it needs a faster way to draw rows.
- Give the fighter kind starting values. Empty Ally, Empty Foe and `raise` in [battle.english](docs/red/battle.english) repeat the same 17 `whose` clauses. This needs SYNTAX §13.21.
- Publish the two visible conversation lines from [conversation.english](docs/red/conversation.english), and remove `visible_page` from [bridge.py](docs/red/bridge.py), which repeats the caption wrapping in Python.
- Save a world snapshot at each in-game SAVE, and replay only the inputs after it. Autosave now rewrites the whole input log on every keypress.
- Version index.html itself. For a few minutes after a deploy, a cached index.html can load the new main.js and stop on the missing `#save-choice` element.
- Route the badge replay through a heal after the lab rival. [replay.json](docs/red/replay.json) runs from seven wild battles before the first Center. Regenerate it with [rerecord_red.py](tools/rerecord_red.py).

## Syntax and compiler

- Section 3 says a property "may be the same word as anything else", but the compiler doesn't allow that. A `rank` property on one kind blocks a worked-out `rank` on another, and a `first` property anywhere breaks `the first of <list>`. Either give properties their own namespace or correct section 3.
- Bring the grammar summary (section 11) in line with the parser:
  - fact-table lookups take a value, not an expression;
  - the leading-minus rule allows `(-17) rounded`;
  - `literal` is never defined;
  - names of sets of choices are one word;
  - §12.8 extends `type`, but §13.19 extends `base-type`.
- Check why each refused example fails, not only that it fails. The §5.2 example is refused because the kind is described twice, not because of the two-readings rule.
- Recast §13.20–13.22 in existing forms:
  - copying should be one change, with rules checked once at the end;
  - `starts with` is already a text test;
  - two-part keys add a third way to write table rows.
- Accept `Orders'`, or say "Write Orders's". It currently gets "Text goes between double quotes".
- State the period-after-quote rule as optional, and make the examples consistent.
- Document the literal-only limit for choosing by value, and consider one case syntax for `Depending on`, `Choose the answer by` and `Set … except`.
- Fix the stale status notes at L2875, L2790, L2671, L499, L1225 and L2080.
- Add these gaps to section 14:
  - mutual recursion;
  - verbs that change state and give a value;
  - lists given to verbs are copies;
  - one-word kind names;
  - iterating a fact table;
  - a changeable map;
  - over-long names.

# Risks and open questions

Two reviews of EnglishScript raised forty-two concerns. The first, of the reference and four of the examples, raised thirty, from compiler scalability to the language's dependence on English. The second, of the to-do list for the web, raised twelve about reactions and the page library. They were offered as architectural risks, not as confirmed defects. This document takes each one and says what is actually so: it was measured or probed against the compiler, and given a verdict.

A third review was adversarial: its task was to break the reference. It found twenty-four things to settle, four of them blockers. They are set out near the end, and they matter more than anything measured before them.

The measurements were made on 20 November 2026, on one computer (Windows on ARM64, Python 3.12), with the compiler as it stood that day. They show the shape of a cost, not a benchmark.

| Verdict | Meaning | How many |
|---|---|---|
| **Confirmed** | The risk is real today, and the evidence is given | 15 |
| **Partly** | Real, but narrower than stated, or the stated cause is not the cause | 11 |
| **Handled** | The language already does what the concern asks for | 8 |
| **Not yet** | Would matter at a scale nothing has reached, or concerns something not built | 3 |
| **By design** | A deliberate choice, with a cost that is accepted | 5 |

## The ten that come first

After the three reviews, ten things were put ahead of everything else. All ten are now fixed, and each fix was checked with a program that showed the fault. `tools/research/review_blockers.py` and `tools/research/later_fixes.py` are those programs.

| | Issue | Standing |
|---|---|---|
| P0 | Numbers that are not whole were not said exactly | **Fixed.** The exact fraction is rounded, a half away from nothing. `Say 123,456,789,012,345,678,901 + 0.5.` says `123,456,789,012,345,678,901.5`. |
| P0 | A check for nothing was wrongly kept inside a loop | **Fixed.** What is known before a loop is not assumed for anything the loop can change. A chain of things can be followed with `While the spot is not nothing:`. |
| P0 | A name could also be an adjective | **Fixed.** A name may not be an adjective, nor begin with one, whichever comes first. Two kinds may not share a name or a plural. |
| P0 | Rules were checked at the wrong time, or not at all | **Fixed.** A rule holds from its own sentence on. It may read only written-out values, variables made with `always`, and the thing's own stored properties, so nothing can break it behind its back. The Python error is gone. |
| P1 | Accepted sentences with two readings | **Fixed.** Six shapes are now refused until brackets say which reading is meant: a filter followed by arithmetic, a second `whose` where a thing is being made, `whether` with `and` or `or`, `or else` beside arithmetic, `not` in front of `and` or `or`, and `the X of Y` when X is also a value in view. |
| P1 | The compiler's vocabulary lookup | **Fixed.** A plain sentence now costs about 45 microseconds to compile whether the program has 10 kinds or 1,600. It was 3,500 microseconds at 1,600. |
| P1 | Reactions checked against every thing | **Fixed.** A sentence that changes one thing checks that thing. Ticking one card among 200 fell from 72 ms to 6 ms. |
| P1 | Private names collide across chapters | **Fixed.** A name a chapter does not share is its own, and other files may use the word, for variables, verbs, adjectives, things and kinds alike. Two chapters that each keep a private `count`, a private verb `tidy` and a private kind `cell` now run side by side. A name that files share still means one thing in the whole program. |
| P1 | No indexed collections | **Fixed.** A list can be written out, added to, indexed and changed, and can be a property. Behind `whose <property> is <value>` there is now an index: looking up each of 1,600 things once took 2.3 seconds and now takes 0.02. |
| P2 | Few kinds of element on a page | **Done.** The page library has thirteen kinds: pictures, links, tables with rows and cells, and menus with options were added, and a panel may sit inside a panel. `examples/web_almanac.english` uses a menu, a table and a link. |

Two more things were built on the way, because the measurements asked for them.

**A reaction for when everything has settled.** `Whenever everything has settled:` is carried out once at the end of a turn, however much the turn changed. The to-do list now tidies itself there and nowhere else. On 200 cards, "Tick them all" took 13.1 seconds and saved the list 201 times. It now takes 8 milliseconds and saves it once.

| One action on 200 cards | Before | After |
|---|---|---|
| Tick one card | 72 ms, 1 save | 6 ms, 1 save |
| Type a letter in the Find box | 37 ms | 5 ms |
| Add a card | 66 ms, 1 save | 11 ms, 1 save |
| Tick them all | 13,110 ms, 201 saves | 8 ms, 1 save |

**Arithmetic and choices.** Remainders, rounding, whole powers, square roots, the larger and smaller of two values, and arithmetic on percentages are built, and so is a fixed set of choices (`A mood is one of sleepy, grumpy or content.`). The examples that work round their absence, SHA-256 above all, have not been rewritten yet.

**Marks in the voice of a teacher.** Every refusal now names its kind of mistake (spelling, punctuation, grammar and so on), gives the rule to remember and the section of the reference that teaches it, and, where the correction is certain, the corrected line, which the playground can put in for you. A misspelt word is answered with the word that was meant.

Adding the new kinds of element brought one of the other concerns to life at once. The library now has a kind called `row`, and a chapter written long before had a role called `row`. A program that used both was refused, though the chapter cannot even say the library's word. The check was wrong and has been put right: a name is judged only against what its own file may say. It is the clearest case so far for why names need to be private.

**Still to do**, in the order it will be done: kinds of problem and a block that always runs after a `Try`; a way to run a program's examples on their own, and a trace of what set off what; properties kept equal to an expression; a verb with more than one shape; a book found beside the program; and the places where the reference is silent or says the wrong thing. Not planned: doing things at the same time, anything that waits, writing things out whole, and loading libraries from outside the compiler.

The tables below are the reviews as they were first written, before any of this. They are kept as the record of what was found.

## What was measured

| Question | Result |
|---|---|
| Compile time against program length | Linear: about 55 microseconds a sentence, from 250 sentences to 16,000 (1.0 s). |
| Compile time against vocabulary | **Worse than linear.** With 100 kinds a plain sentence takes 0.2 ms to compile; with 1,600 kinds, 3.5 ms. Describing 1,600 kinds takes 8 s; describing 400 takes 0.5 s. |
| Where that time goes | One function, `defined_word`, which makes a list of every name in the program for each sentence it reads. It is not the reading of English that is slow. |
| Compile time of the examples | The largest, SHA-256, is 297 sentences and compiles in 26 ms. All 23 examples together are about 1,300 sentences. |
| Sentences carried out a second | About 1,000,000 for `Add 1 to the count.` The same loop in plain Python does 1,170,000 a second with exact fractions and 16,800,000 with ordinary integers. |
| Finding a thing by a property | Linear in the number of things: 0.09 ms among 100, 1.4 ms among 1,600. Looking up each of 1,600 once takes 2.3 s. |
| Text, a letter at a time | Linear and cheap: under 5 microseconds a letter up to 3,200 letters. |
| Fractions that grow | The sum of 1/k for k up to 2,000 takes 7 ms, though its denominator has 866 digits. |
| Limits | A `While` stops after 10,000 rounds. A verb may use itself 200 levels deep. `Repeat` has no limit: a million rounds take 1 s. |

Two of these change the picture the review drew. The compiler's scaling problem is real but is one fixable function, not a property of resolving English phrases. And the running program is not slow because each sentence is a Python closure: a sentence costs about what one exact addition costs in Python. It is slow because numbers are exact fractions (about seventeen times dearer than integers here), and because a program with no lists must search for things one by one.

## The first thirty, one by one

### Scale

| Concern | Verdict | What is so | What it needs |
|---|---|---|---|
| Compiler scalability | **Confirmed**, narrowly | Compile time grows faster than the vocabulary, because of the one function above. Programs of the size written so far are unaffected: none takes more than 50 ms. | Keep a set of known words instead of rebuilding a list for every sentence. Then measure again before believing anything about phrase resolution. |
| Incremental compilation | **Not yet** | The whole corpus of examples compiles in well under a second. A chapter is read once per run, however many files use it. | Nothing until programs are a hundred times larger. The vocabulary fix comes first. |
| Runtime performance | **Partly** | Simple sentences run at about a million a second. SHA-256 manages about 300 bytes a second, but the cause is the search for things and the fraction arithmetic, not the closures. | Indexed collections (below). Whole numbers that stay whole could be kept as integers inside the compiler, with no change to the language. |
| Numeric representation | **By design** | Every number is an exact fraction. `0.1 + 0.2` is `0.3`, and a third of ten dollars times three is ten dollars. The cost is speed, and there are no bounded integers and no floating point. | A decision on bounded integers and bit operations, which section 13.12 of the reference designs but does not build. |

### Names and modules

| Concern | Verdict | What is so | What it needs |
|---|---|---|---|
| Name collisions | **Handled**, with a cost | Two chapters giving one name two meanings is refused, and the message names the chapter that has it already. There is nothing to resolve, so nothing is resolved silently. | See module isolation: the cost is that private names collide too. |
| Module dependency management | **Handled** | Section 9.6 states all four points. A circle of chapters is refused and named (`a -> b -> a`). What a chapter uses is not passed on. A chapter is read once, at the first `Use` that reaches it, and its sentences are carried out then. A chapter says in its first sentence what it shares. Each was probed and behaves as written. | Sibling books cannot reach each other: a chapter finds chapters only beside itself. That limit is stated, and will chafe. |
| Module isolation | **Partly** | A file cannot read or change a name another chapter keeps to itself. But the world is one world: a chapter's rules and reactions bind every file, a shared variable can be `Set` by anyone who can say it, and two chapters may not use the same private name. | Private names that may repeat. Until then a book cannot be written without knowing the private words of every other book in the program. |
| Verb overloading | **Handled**, by refusal | There is none. A verb word has one shape: a second `To send ...` with other roles is refused. The risk runs the other way: a growing program runs out of good verbs. | A decision on whether a verb may have several shapes told apart by their prepositions. If so, the rule for telling them apart must be exact. |
| Reserved vocabulary | **Confirmed** | 96 words are reserved. Writing the examples ran into `name`, `number`, `more`, `new` and `list` as parts of names that would have been natural. | Reserve by position where possible, as `chapter`, `book` and `library` already are. A new reserved word breaks existing programs, so the list should be frozen early. |
| Case insensitivity | **By design** | Names are matched without regard to capitals: `smaug` finds `Smaug`, and a second thing called `SMAUG` is refused. No external identifier is ever a name in a program, so there is nothing yet to disagree with. | To be looked at again if a library ever takes names from outside. |
| Automatic pluralization | **Confirmed**, with a defect | Plurals are formed by rule, so `children` and `sheep` are not known. Worse, two kinds may share a plural: with kinds `bus` and `buse`, `the number of buses` is accepted and silently counts one of them. That is an ambiguity the compiler promises to refuse. | Refuse a kind whose plural, or whose name, collides with another's. Allow a kind to state its own plural. |
| Refactoring safety | **Partly**, since answered | A rename is a search through every phrase. A missed use could never go unnoticed, because every name must be defined before it is used. | A rename tool now exists, `python -m englishscript.rename`. It changes every use, a kind's plural included, and then asks the linter: if the renamed program has any complaint the original did not, the rename is refused and nothing is changed. Tried on every name in every example, 583 of 585 went through. It works on one file at a time. |

### Data

| Concern | Verdict | What is so | What it needs |
|---|---|---|---|
| Collections and indexing | **Confirmed**: the largest gap | A list comes only from splitting text or reading a file. It can be counted and gone through, and nothing else: it cannot be written out, added to or indexed. Everything else is done with things, searched one at a time, which is where the measured cost is. | Lists that can be made and changed, and a way to find a thing by a property without visiting every thing. Section 13.7 designs the first. |
| Type-system expressiveness | **Partly** | There is one union, `if any`, and it is checked strictly. There are no generics and no values with parts: anything with parts is a thing with an identity. A variable can be fixed with `always`. | A fixed set of choices (section 13.3) is the missing piece most often felt. Generics would be a large step for a language of this size. |
| Binary and text processing | **Confirmed** | There are no bytes and no bit operations. SHA-256 builds them from "is divisible by 2". Text is handled a letter at a time by slicing, which is cheap but awkward to write. | Remainders, powers and bit operations (section 13.12), and a way to name the n-th letter. |
| Data serialization | **Confirmed** | There is none. The to-do list's `keeping` chapter writes each card as a line of text and reads it back word by word, by hand. | A decision first: whether things can be written out and read back as a whole. Nothing is designed. |
| Standard-library coverage | **Confirmed** | Two libraries exist, `vulkan` and `page`. There is no remainder, no rounding, no dates and no clock. | The designed parts of section 13, in the order that programs have needed them: remainders, lists, dates. |
| Memory management | **Handled**, mostly | A thing lives until `Remove`. Removing a thing that another still points at is refused, unless the property is `if any`, in which case it becomes `nothing`. Things may point at each other in a circle. A failed `Try` brings back what it removed. One gap: a variable may go on holding a removed thing, and that is found only when it is used, while running. | Decide whether a variable holding a removed thing should become `nothing` as an `if any` property does. |

### Effects and failure

| Concern | Verdict | What is so | What it needs |
|---|---|---|---|
| Error handling | **Partly** | Section 8.5 says what a failed `Try` puts back (every change to the world) and what it does not (what was said, asked, or written to a file). Section 10 lists which problems can be recovered from. A problem can be passed on with `Fail because "... {the problem}"`. But a problem is only its text: there are no kinds of problem to tell apart, and no block that always runs afterwards. | Kinds of problem, so that a program can recover from one and not another. |
| Function side effects | **Partly** | The compiler checks that a worked-out value changes nothing: it may not set, say, make a thing or use a verb. It may, however, read a file, so the same value asked for twice can differ. Verbs are not tracked at all. | Say in the reference that a worked-out value may read the outside. Tracking what verbs change belongs with concurrency. |
| Concurrency complexity | **Not yet**, and unproven | Nothing runs at the same time. Section 12 designs it, with a rule that two things are treated as possibly the same unless the compiler can be sure they differ. That rule is safe and will refuse a great deal. Reactions (`Whenever`) are built, and run one after another in a fixed order. | A prototype before the design is trusted. This is the least tested idea in the reference. |
| Foreign-function interface | **By design** | A library is a Python module that comes with the compiler, and inside it anything Python can reach is available: the `vulkan` library calls the graphics driver directly. A program cannot name any other module. That is a wall, put there so that a program's say-so never loads code. | A decision on whether libraries from outside the compiler may be installed, and how a reader is told what one can do. |

### Tooling

| Concern | Verdict | What is so | What it needs |
|---|---|---|---|
| Diagnostics | **Handled**, and being improved | An ambiguous phrase is refused with its readings and a way to say which: `"feuds of Smaug" can be read 2 ways ... Say which: "feuds whose challenger is Smaug"`. The messages are being rewritten in the shape of a teacher's mark, with the rule and a correction that can be applied. | The rewrite in progress. |
| IDE support | **Confirmed**, since answered | The playground checks as you type, underlines, lists every problem and can apply a correction. There was no completion, no rename and no way to jump to a definition. | A language server now exists, `python -m englishscript.server`: problems as you type, corrections as quick fixes, hover, an outline, go to definition (into chapters too), completion and rename. It has been driven by its tests, including a real exchange over pipes, and has not yet been run inside an editor. [EDITORS.md](EDITORS.md) says how to set it up. |
| Testing infrastructure | **Partly** | `For example` runs with the program, every time, against the live world, and the count is reported. There is no way to run examples apart from the program, and no fixtures. | A way to run a file's examples without its other effects. |
| Debugging and observability | **Confirmed** | A problem while running gives the sentence, the values, and the sentences that led to it. `--explain` shows how each sentence was read. There is no stepping, no tracing and no profiler. | Tracing first: a run that says each sentence as it is carried out is cheap to add and suits the language. |

### The shape of the language

| Concern | Verdict | What is so | What it needs |
|---|---|---|---|
| Ambiguous relationship inference | **Handled** | This is the case the language was built round. `treasures of Smaug` works only if exactly one property ties a treasure to a dragon. With two, it is refused and the explicit form is given. A kind tied to its own kind works the same way. | Nothing. |
| Syntax verbosity | **Partly** | The same bank program is 117 words in EnglishScript, 124 in JavaScript and 172 in Java, in 16, 30 and 45 lines. Sentences are not longer than code. Repetition is real, though: the chapter that lays out the to-do page says `whose panel is ...` eleven times. | A way to say something once for several things, such as making several things inside one panel. |
| Sentence punctuation | **By design** | One sentence to a line, a period at its end, a colon and an indent for a block. The linter says what is missing and can put it in. One irregularity: a sentence that ends in a closing quotation mark needs no period. | Decide whether that exception stays. |
| English-language dependence | **By design** | Articles, plurals and prepositions carry the grammar. Another language would need its own compiler, not a translation of this one. | Nothing. It is the premise. |

## Reactions and the page library

A second review looked at the to-do list for the web (`examples/web_todo.english` and the book in `examples/tasks`) and raised twelve more concerns, about what happens when one change sets off others and a page has to keep up. These were measured on the real program, through the page library's stand-in page, with every write to an element and to storage counted.

| One action, on a list of | 10 cards | 50 cards | 200 cards |
|---|---|---|---|
| Tick one card | 0.7 ms, 1 save | 6.9 ms, 1 save | 72 ms, 1 save |
| Type a letter in the Find box | 0.3 ms, no save | 2.5 ms, no save | 37 ms, no save |
| Type a letter in the entry box | 0.1 ms, no save | 0.3 ms, no save | 1.2 ms, no save |
| Add a card | 1.1 ms, 1 save | 6.7 ms, 1 save | 66 ms, 1 save |
| Tick them all | 5.9 ms, 11 saves | 276 ms, 51 saves | **13.1 s, 201 saves** |

Whatever the size of the list, ticking one card touches six to eight elements of the page: the card, the three counts, the note and the bar. The page library is not the cost. With no `Whenever` in the program at all, ticking one card among 1,000 writes to two elements and takes 3.5 ms.

The cost is in how reactions are checked. Before every sentence that could change something, the runtime works out every watched adjective for every card, so as to see afterwards which of them "became". One tick sets off one `Tidy`, which is about 410 such sentences among 200 cards, and so 665,000 tests. That makes one `Tidy` quadratic in the number of cards. "Tick them all" then asks for a `Tidy` after each card, which makes it cubic.

| Concern | Verdict | What is so | What it needs |
|---|---|---|---|
| Event recursion | **Handled** | Section 9.5 fixes the order: a reaction is carried out at once, after the sentence that set it off; when one sentence changes several things they are taken in the order they were made; reactions to the same change run in the order written. A probe with two reactions gave `A:First B:First A:Second B:Second A:Third B:Third`. Reactions that set each other off for ever are stopped at 200 levels, the whole event is undone, and the page is left as it was. | It is a limit on depth, not a detection of circles: the message names the reaction it stopped at, not the circle. It should name the circle. |
| Redundant updates | **Confirmed**, and worse than stated | Every tick, star, edit and removal runs `Arrange`, `Sift`, `Reckon` and `Keep` over every card. The table shows the result. Two causes are multiplied together: the program asks for everything to be redone, and the runtime re-tests every card before every changing sentence. | In the runtime, test only the thing a sentence changes. In the language, a way to answer once after a whole event (see event ordering). |
| Reactive dependencies | **Confirmed** | The language already has values that follow others: a worked-out property and a defined adjective are worked out afresh each time they are read. It has nothing that keeps a stored property, such as a note's wording, equal to something. `Tidy` is that, done by hand. | A sentence that says a property is kept equal to an expression. The compiler would have to know what an expression reads, which is the same analysis that doing things at the same time needs (section 12). |
| UI and data coupling | **Confirmed**, by choice of that example | In the to-do list a card is the task. Running without a browser is not a problem: the stand-in page runs the whole program, and its tests press, type and tick with no browser. A second view of the same tasks would need a kind of its own, kept in step with the cards by hand. | The counters example keeps the two apart: the count belongs to a counter, and the note and buttons only show it. Kept properties, when built, will remove the keeping in step by hand. |
| Transaction boundaries | **Partly** | The page cannot disagree with the world after a failure, because it is redrawn from the world after every event. A tick whose answer fails leaves the thing unticked, the box unticked and the note untouched. Two things escape. What was `Remember`ed inside the failed answer stays in storage, as a file written inside a failed `Try` stays. And a letter typed into a box whose answer fails is taken back out of the box, which is consistent and will surprise people. | Say in the reference that `Remember` is like writing a file. Decide whether a refused keystroke should disappear. |
| Event ordering | **Partly** | The order is fully specified, as above. Batching is not: there is no way to say "when all of this has settled". A loop that ticks every card therefore runs a full answer after each one. | A settled form of reaction, carried out once when an event and everything it set off have finished. It would also cure the redundant updates and the saves. |
| Component reuse | **Confirmed**, since answered | Every element is one named thing, and a chapter is read once, so it cannot be used to make two of anything. But a kind of the program's own can hold the elements that belong together, a verb can make them, and one reaction can serve them all by finding the thing a pressed button belongs to. | `examples/web_counters.english` makes three counters this way, and the page library's document describes the pattern. Nothing new was needed in the language. |
| Rendering efficiency | **Handled**, in the library | Only what differs is written: one element for a press that changes one note, two for a tick. A card that changes its place is the only one moved. The library's own walk over the things is linear: 0.55 ms among 200 cards, 3.5 ms among 1,000. | Nothing in the library. The waste is in the program's recomputation, above. |
| Accessibility | **Partly**, since mended | Given without asking: real elements (a heading, buttons, text boxes, a tick box), so the keyboard works; a spoken label on a card's box, words, star and cross; attention kept on a card that moves; Enter and Escape while editing. Seven gaps were found: a field's only name was its hint; every button carried a pressed state, so "Add" was announced as a switch; a note that changed was not announced; the bar had no range; every cross said only "Remove"; cards were not a list; attention was lost when the card that had it was removed. | All seven have been closed in the library, with tests for six. The seventh, where attention goes when a card is removed, can only be seen in a browser. |
| Debugging | **Confirmed** | A problem reports the sentences that led to it. Nothing shows a chain that went well. The to-do page's list of "the things behind the page" marks what changed after each click, which shows the result and not the cause. | A trace of each event: which reactions ran, in what order, and what each changed. |
| Persistence frequency | **Confirmed** | One save for each `Tidy`, and each save writes the whole list: one for a click, 201 for "Tick them all" on 200 cards. Typing saves nothing. | The settled reaction, which would make it one save for each event. |
| Asynchronous operations | **Not yet** | Nothing in the language waits, and there is no library for the network. The door exists: a library can bring in something that happened later exactly as it brings in a click, and a result arriving would be an adjective becoming true. Loading, failure and cancelling have no design. | A design before a library. Section 12 has `Wait` and `Every`, unbuilt. |

### The priorities for this part

1. **Check reactions against what a sentence changes, not against every thing.** The largest measured cost in this whole document, and it needs no change to the language.
2. **A reaction for when things have settled.** One sentence form would answer three of the twelve concerns: redundant updates, the order of bulk actions, and how often the list is saved.
3. **The seven accessibility gaps.** Small, concrete, and the library's own business. These are now closed.
4. **A property kept equal to an expression.** It would remove `Tidy` altogether, and it is the largest piece of design here.
5. **A trace of events.**

## An adversarial review of the reference

Last, a reviewer who had no part in designing the language was asked to attack the reference and all the examples as a draft specification, and to prove each complaint with a program. It ran all 72 examples in the reference, which pass, and all the example programs, which run and lint clean. It then found twenty-four things to settle. Four are blockers. Each of the four was run again for this document and does what the reviewer said.

### The four blockers

| Finding | What happens | What has to be decided |
|---|---|---|
| **A number that is not whole is not said exactly.** The reference says a value is said in full, however many digits it has. | `Say 123,456,789,012,345,678,901 + 0.5.` says `123,456,789,012,345,683,968`. The number is exact inside the program and is turned into a binary fraction to be said. Rounding to four places goes the same way: `0.00015` is said as `0.0001` and `0.00025` as `0.0003`. Money rounds a half to the even cent: `$0.125` is `$0.12` and `$0.375` is `$0.38`. | Round the exact fraction, and state the rule for a half. |
| **A check for nothing is refused where the value changes.** | A variable set from a thing is known not to be nothing, so `If the spot is not nothing:` is refused as needless, even inside a loop that goes on to `Set the spot to the spot's next.` Following a chain of things cannot be written, with `Repeat` or with `While`. | What is known before a loop must not be assumed at the head of the loop. The reference must also say that `Let` and `Set` count as checks. |
| **A name may also be an adjective, and the adjective wins.** The reference says a name cannot be reused while an earlier meaning is in view. | With an adjective `ancient` and a dragon called `Ancient`, `If Smaug is Ancient:` asks whether Smaug is old. With `Let rich be Norbert.`, the sentence `If Norbert is rich:` means "is the same thing" until a later `A dragon is rich when ...`, after which the same sentence means something else. `For each ancient rival in dragons:` visits every dragon: "ancient rival" is taken as a name of two words, not as a filter. | Say what the namespaces are, and refuse a name that is also an adjective. |
| **Rules are not checked when the reference says, and one case crashes.** | A rule is applied to things made before it was stated, and the program stops before the sentences in between are carried out. A rule that reads a variable made after a thing ends in a Python `KeyError`, which nothing in this language should ever do. A rule that reads something else is not checked again when that changes: after `A treasure's owner is always ancient.`, making the owner young is accepted. | Limit what a rule may read to the thing's own stored properties and fixed values, or check it again whenever what it reads changes. Say when a rule begins to hold. |

### The rest, in brief

These are as the reviewer reported them. They were not all run again.

| Severity | Finding |
|---|---|
| Major | **Accepted sentences with two readings.** A second `whose` after a group attaches to the thing being made, not to the group. A filter swallows what follows it: `the number of knights whose courage is more than 5 + 1` reads as `more than (5 + 1)`. `whether` swallows a following `and`. `or else` has no place in the stated order of working. |
| Major | **`the X of`** can be a value or a property, and which one depends on what happens to be in view in that file. One example compiles only because a property of that name is not visible there. |
| Major | **Text is filled in when it is made, not when it is said**, which the reference states the other way round. |
| Major | **A block may reuse a kind's name for a variable or a role; the top level may not.** The reference does not say so, and the to-do list relies on it. |
| Major | **The list of what counts as a check for nothing is incomplete**, and an `if any` property cannot be given a `never` rule. |
| Major | **Chapters.** A thing of an unshared kind can still be removed by a file that cannot name its kind. A property can have two types in two files, though the reference says it has one meaning. |
| Major | **The reference never mentions the page library**, and says that one library comes with the language. |
| Major | **The designs that are not built collide with what is.** They would reserve `unit`, `first` and `last`, which examples use. `to the power of` meets `Add ... to`. The design for doing things at once takes no account of reactions. |
| Major | **The limit of 10,000 rounds depends on the data and cannot be recovered from.** An honest computation that needs more ends the program even inside a `Try`. |
| Minor | Names are matched longest first with no going back, unstated. `comes before` is the order of character codes, not of the alphabet. Short-circuiting in `and` is observable and unstated. A `Now Adder is pressed.` written by the program is not momentary. Forms are irregular in a dozen small ways: `the` is optional before a variable and refused before a thing; text tests have no `not` form of their own; a verb's roles take an expression and a worked-out value's do not. |
| Examples | `tournament.english` said "Gawain wins" when no knight could pay the fee. Comments in three examples were wrong: the count of digits in `roots`, the count of arrays in `sha256`, and a claim in `triangle` that the language cannot reach a graphics card, which stopped being true when the vulkan library was written. All four have been mended. |

### What held up

The reviewer tried hard to break these and could not: the checks for nothing, against aliasing, loops, verbs, reactions, removal and both branches of a `Try`; what a failed `Try` puts back; the order and depth of reactions; the purity of `To work out`; the visibility of names across chapters; the refusal of "and" mixed with "or"; the strictness of pronouns and of `the <kind>`; and the layout rules.

### What this changes

The measurements above were about cost. This review is about the promise. The language says "one meaning, or a refusal", and there are now eight accepted shapes of sentence that have two: the seven the reviewer found and the shared plural found earlier. They come before any question of speed. So do the four blockers, since each is a place where the reference says one thing and the compiler does another.

## Found along the way

Six things turned up that were on neither list.

1. **Two kinds may share a plural.** Described above, and the only case found in this research where the compiler accepts a phrase with two readings.
2. **A `While` stops after 10,000 rounds**, as a problem that cannot be recovered from. It is a guard against a loop that never ends, but it is also a ceiling on honest work, and the reference gives it one line. `Repeat` has no such limit.
3. **A worked-out value may read a file.** "Changes nothing" is checked. "Gives the same answer each time" is not, and the reference should not be read as promising it.
4. **The compiler's slow function arrived with chapters.** It filters every name through the rule for what a file may say. The cost was invisible at the size of the examples.
5. **Private names collide across chapters.** The reference says so. It deserves more weight than a line in the list of limits, because it is what stands between chapters and reusable books.
6. **Checking reactions costs as much as there are things.** Described in the second part. A program with one `Whenever` pays it on every sentence that changes anything, which no reader of the reference would guess.

## The priorities for the first thirty

The review's top five were compiler scalability, module and name resolution, native collections, runtime performance and interoperability. After measuring, the order is different and so are two of the items.

1. **Lists that can be made, changed and indexed, and finding a thing without searching.** This is the measured cost in every heavy example, and the cause of the awkwardest sentences in them.
2. **The compiler's vocabulary lookup.** Small, located, and worth doing before anyone concludes that English cannot be compiled at scale.
3. **Private names that may repeat across chapters.** The modules work as specified. This is the rule that will stop them scaling.
4. **Remainders, bounded integers and bit operations.** Designed, not built, and the whole of what makes SHA-256 painful.
5. **Kinds with colliding plurals.** Small, but it is a hole in the one promise the language makes.

Runtime speed and interoperability fall out of the first five. Speed follows from the first and fourth items more than from any change to how sentences are run. Interoperability is a wall that was built on purpose, and moving it is a question of trust more than of engineering.

## How to repeat this

The scripts are in `tools/research`. Each takes the folder of the repository:

```text
python tools/research/timing.py .             how compiling and running scale
python tools/research/where_time_goes.py .    which functions the compiler spends its time in
python tools/research/probes.py .             small programs, one for each claim above
python tools/research/more_probes.py .        a few more, and the compile time of each example
python tools/research/review_blockers.py .    the four blockers of the adversarial review
python tools/research/later_fixes.py .        private names, lists, the index, arithmetic and choices
python tools/research/page_events.py .        what one click costs on the to-do page, and what a failure leaves
python tools/research/page_where_time_goes.py .   which functions one tick spends its time in
```

They print what they find and change nothing. The times will differ on another computer; the shapes should not. Run today they show the compiler as it is now, with the fixes in, so several of them no longer show the fault they were written to find: a probe that once ran to a wrong answer now ends in a refusal.

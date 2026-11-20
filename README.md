<h1 align="center">EnglishScript</h1>

<p align="center"><em>or, English made strict enough to compile</em></p>

<p align="center">
A programming language made of English sentences, and a compiler that accepts a sentence<br>
only if it has exactly one meaning. Anything that could be read two ways is refused,<br>
with a message that says what is unclear and how to mend it.
</p>

<p align="center">
  <a href="https://monstercameron.github.io/EnglishScript/playground.html"><img alt="Write a program in your browser" src="https://img.shields.io/badge/Write_a_program_in_your_browser-%E2%96%B6-8f1d14?style=for-the-badge&labelColor=8f1d14"></a>
</p>

<p align="center">
  <a href="https://monstercameron.github.io/EnglishScript/"><b>Read the treatise</b></a> &nbsp;·&nbsp;
  <a href="https://monstercameron.github.io/EnglishScript/todo.html"><b>See a web page written in English</b></a> &nbsp;·&nbsp;
  <a href="https://monstercameron.github.io/EnglishScript/reference.html"><b>The grammar</b></a> &nbsp;·&nbsp;
  <a href="https://monstercameron.github.io/EnglishScript/compare.html"><b>Beside JavaScript and Java</b></a>
</p>

<p align="center">❦</p>

Nothing to install: **[the playground](https://monstercameron.github.io/EnglishScript/playground.html)** runs this same compiler in your browser, underlines what it cannot read as you write, and offers the correction.

```
A dragon has an age (number).
A treasure has a worth (money) and an owner (dragon).

The hoard of a dragon is the total worth of its treasures.
A dragon is poor when its hoard is less than $1,000.

There is a dragon called Smaug whose age is 771.
There is a treasure called Goblet whose worth is $3,000 and whose owner is Smaug.

To tax a dragon:
  For each treasure of the dragon:
    Subtract 10% of the treasure's worth from the treasure's worth.

Tax Smaug.
Say "{Smaug's name} now sits on {Smaug's hoard}."
For example, the hoard of Smaug is $2,700.
```

The compiler is plain Python with no dependencies, and there is no AI in it. The same program always means the same thing.

## The idea

English is easy to read because it leaves things unsaid. The compiler allows that only where the unsaid part has exactly one possible reading. Anywhere else it stops and says what is unclear.

| English habit | The rule that makes it strict |
|---|---|
| Shared vocabulary | Every noun, adjective and verb must be defined before it is used. |
| "its", "it" | Allowed only when exactly one thing is in view. |
| "the dragon" | Must point at one dragon in the sentence's context. |
| "treasures of the dragon" | Works only if a treasure is tied to a dragon by exactly one property. |
| "send X against Y" | Prepositions name the verb's roles; each role is typed and required. |
| "A and B or C" | Refused until brackets say which reading is meant. |
| "$5", "10%" | Money, numbers and percentages are different kinds of value and do not mix. |
| "never", "always" | A rule checked every time the property changes. |
| "For example, ..." | A test that runs with the program. |
| "if any" | A value that may be missing cannot be used until the program has checked it is there. |

The argument at length is **[the treatise](https://monstercameron.github.io/EnglishScript/)**.

## The site

| | |
|---|---|
| **[The treatise](https://monstercameron.github.io/EnglishScript/)** | The argument for the language, with examples that run where they stand, and a chapter on agents and what a program means. |
| **[The playground](https://monstercameron.github.io/EnglishScript/playground.html)** | An editor that marks your program as a teacher would, with corrections you can accept, twenty-four examples and a list of how to say things. |
| **[A page](https://monstercameron.github.io/EnglishScript/todo.html)** | A to-do list for the web written in EnglishScript, as a book of four chapters, with its files and the things behind the page shown beside it. |
| **[Three systems](https://monstercameron.github.io/EnglishScript/systems.html)** | The program's own exact sentences (System 0), a model that judges in the manner of TypeSafe's Jev (System 1), and a model that writes (System 2): which work belongs to which, with eight examples from a single rule to a cascade through all three. |
| **[The opposition](https://monstercameron.github.io/EnglishScript/opposition.html)** | Seventy years of programming in English, from FLOW-MATIC to Inform 7, and the new languages that ask a model: what each did with a sentence that could mean two things, and what EnglishScript should borrow or fear. |
| **[FizzBuzz, every way](https://monstercameron.github.io/EnglishScript/fizzbuzz.html)** | FizzBuzz in EnglishScript, kept beside FizzBuzz in each rival, from COBOL and AppleScript to Inform 7 and the languages that ask a model. Each sample says how far it was checked. |
| **[Compared](https://monstercameron.github.io/EnglishScript/compare.html)** | The same programs in JavaScript and in Java, and where the three part company. |
| **[The grammar](https://monstercameron.github.io/EnglishScript/reference.html)** | Every sentence the compiler accepts. Its examples run in the page, and the test suite runs them too. |
| **[The machinery](https://monstercameron.github.io/EnglishScript/how.html)** | How a compiler written in Python runs in a browser, and what that costs. |
| **[Risks and open questions](https://monstercameron.github.io/EnglishScript/concerns.html)** | Forty-two concerns about the design, each measured against the compiler and given a verdict. |

The site is dressed as a printed English book: blackletter, the Fell types and Garamond.

## Run it on your own computer

**[Maintenance Desk](apps/maintenance/README.md)** is a complete application written in EnglishScript. It takes a facilities inbox, gets a trade and urgency from System 1, asks System 2 for handoffs and second opinions, and applies System 0 budget and crew limits to produce a shift plan. Its Windows launcher includes a replayable six-ticket demo.

It needs Python 3 and nothing else. It has been tested on Python 3.12.

```bash
python -m englishscript
```

That is a guided tour: a program about dragons, what it says, how the compiler read it, and eleven sentences it refuses. To run a program of your own:

```bash
python -m englishscript examples/invoices.english
```

| Option | What it does |
|---|---|
| `--explain` | Shows how each sentence was read, and runs nothing. |
| `--check` | Compiles only. |
| `--lint` | Lists every problem at once, with advice and warnings, and runs nothing. The exit status is 1 if there is an error. |
| `--lint --json` | The same, as data, for an editor or an agent. |
| `--test` | Carries the program out with nothing said, asked or written, and reports every `For example`, going on past one that does not hold. |
| `--trace` | Says each sentence as it is carried out, indented by depth, and what set off each reaction. |

From Python, `englishscript.compile_file(path).run()` runs a program and `englishscript.lint(source)` gives its problems as a list.

**In an editor.** `python -m englishscript.server` is a language server: it marks a program as you write it, offers each certain correction, explains a sentence when you hover over it, completes names and sentence forms, and renames. `python -m englishscript.rename file.english "old name" "new name"` renames from the command line, and refuses any rename that would give the compiler a new complaint. [docs/EDITORS.md](docs/EDITORS.md) has the details and what has not been tried.

## What a program can say

The full reference is [docs/SYNTAX.md](docs/SYNTAX.md). In brief:

<details>
<summary><b>The sentence forms</b></summary>

| Purpose | Form |
|---|---|
| Describe a kind | `A dragon has an age (number) and a lair (text).`, and with a plural of its own, `A person (plural people) has an age (number).` |
| Define an adjective | `A dragon is ancient when its age is at least 500.` |
| Store an adjective | `A task can be done.` then `Now the task is done.` |
| Define a worked-out property | `The tax of a dragon is 10% of its hoard.` |
| State a rule | `A knight's purse is never less than $0.` |
| Make a thing | `There is a dragon called Smaug whose age is 771.` |
| Make, find and remove things while running | `There is a new task called the title whose position is 1.`, `Let the chick be a new dragon whose age is 0.`, `the dragon called "Smaug"`, `Remove the task.` |
| Teach a verb | `To send a knight against a dragon:`, and the same word in another shape, `To send a sum (money) to a knight:` |
| Use a verb | `Send Gawain against Smaug.` |
| Variables | `Let the total be 0.` then `Set`, `Add ... to`, `Subtract ... from`, `Multiply ... by`, `Divide ... by` |
| Fixed variables | `Let the tax rate always be 10%.` |
| Values that may be missing | `a mount (horse, if any)`, `nothing`, `If Wat has a mount:`, `Wat's mount's speed or else 0` |
| Work out a value | `To work out the bounty (money) for a dragon:` with `The answer is ...`, used as `the bounty for Smaug` |
| Leave early | `Stop.`, `Stop repeating.`, `Skip this treasure.`, `End the program.` |
| Say | `Say "{its name} is {its age}."` |
| Ask | `Ask "Age?" and let the age (number) be the reply.` |
| Files | `the text of the file "notes.txt"`, `the lines of the file ...`, `Write ... to the file ...`, `Add ... to the file ...` |
| Text | `the length of`, `in upper case`, `the first 3 letters of`, `the words of`, `as a number`, `contains`, `starts with`, `comes before`; `""` and `{new line}` inside quotes |
| Yes or no | `Let done (yes or no) be no.`, `whether Smaug is ancient`, `If done is yes:` |
| Branch | `If ...:`, `Otherwise if ...:`, `Otherwise:` |
| Compare | `is`, `is not`, `is less than`, `is more than`, `is at least`, `is at most`, `is divisible by` |
| Loop | `For each poor dragon:`, `For each rival in dragons:`, `For each word in the words of the line:`, `Repeat 3 times:`, `While ...:` |
| Count and add up | `the number of ancient dragons`, `the total worth of Smaug's treasures`, `the number of items in the words` |
| Lists | `Let the scores be a list of 3, 8 and 5.`, `an empty list of numbers`, `Add 10 to the scores.`, `item 2 of the scores`, `Set item 2 of the scores to 9.`, `the total of the scores`, `the names joined with ", "`, `If 10 is in the scores:`, and as a property, `a shelf (list of treasures)` |
| Arithmetic | `the remainder of 17 divided by 5`, `17 rounded up to the nearest 5`, `2 raised to the power of 10`, `the square root of 81`, `the larger of $5 and $8`, `the absolute value of -4` |
| A fixed set of choices | `A mood is one of sleepy, grumpy or content.` then `a mood (mood)` |
| Recover from a problem | `Try:` then `If that fails:` with `the problem`, and `Either way:` for what must be done in any case; `Fail because "..."`, `Fail again.`; `If the problem is a broken rule:` |
| Ask a model | `Ask the model "In one line, what does the customer want?" about the letter and let the gist (text) be the reply.` |
| Ask a model to judge | `Judge "Which team should handle this?" about the letter and let the pick (team) be the verdict and the sureness (percent) be the likelihood.` |
| React to a change | `Whenever a knight becomes broke:`, `Whenever Adder becomes pressed:`, `Whenever a card becomes not ticked:`, and once when a turn is over, `Whenever everything has settled:` |
| Keep something true | `Keep Tally's wording as "{the number of open cards} left".`, `Keep each card's order as the standing of the card.`, `Keep each card hidden when the card is ticked.` |
| Use a library | `Use the vulkan library.`, `Use the page library.` |
| Use another file | `Use the calendar chapter.`, `Use the calendar chapter of the almanac book.`, and in the chapter, `This chapter shares only leapness and weekday.` |
| Test | `For example, the hoard of Smaug is $12,000.` |

</details>

Types are `number`, `money`, `text`, `percent`, `yes or no`, any kind you describe, and lists such as `list of text`. Comments start with `#`. Layout carries the nesting: one sentence to a line, a colon and an indent for a block.

**Chapters and books.** A program can be split over files. A chapter is a file, a book is a folder of them, and a chapter says in its first sentence which of its words other files may use.

**Libraries.** Two come with the compiler. [`page`](docs/PAGE.md) makes things that are elements of a web page, bound both ways. [`vulkan`](docs/VULKAN.md) draws shaded triangles on a real graphics card.

## Examples

<details>
<summary><b>Programs that show the language at work</b></summary>

| Program | What it shows |
|---|---|
| `examples/helloworld.english` | One sentence. |
| `examples/fizzbuzz.english` | Loops, branches and `is divisible by`. |
| `examples/dragons.english` | Kinds, adjectives, worked-out properties, verbs and rules. The tour uses it. |
| `examples/invoices.english` | The same structures in a business setting. |
| `examples/tournament.english` | Values that may be missing, worked-out values, and leaving early. |
| `examples/todo.english` | A to-do list at the command line that saves to a file: asking, files, `Try`, making and removing things. |
| `examples/web_todo.english` | A to-do list for the web, with tags, stars, editing in place, finding, and putting back what was removed. Its work is divided among four chapters of the book in `examples/tasks/`, and what the page shows is kept true by sentences beginning `Keep`. |
| `examples/almanac.english` | A program put together from the chapters of a book: `examples/almanac/` holds a calendar, Roman numerals and the feasts of the year. |
| `examples/web_almanac.english` | The same chapters set out as a web page: a menu of years, a table of feasts and a link. |
| `examples/triage.english` | Sorting the post: a model judges which team each letter belongs to and how upset the customer is, and the program decides in three bands. It replays recorded answers with `--model replay:examples/triage_answers.txt`, and with no model it keeps every letter for a person. |
| `examples/web_counters.english` | Three counters on one page, built by one verb: how to make several of something, and keep what a program is about apart from how it is shown. |
| `examples/triangle.english` | A shaded triangle drawn in characters, following the steps of a Vulkan program without a graphics card. |
| `examples/gpu_triangle.english` | The same triangle on a real graphics card, through the Vulkan API. |
| `examples/sha256.english` | SHA-256 from first principles, in a language with no bit operators, remainders or arrays. It agrees with other implementations. |

</details>

<details>
<summary><b>Smaller programs, each about one piece of arithmetic or one classic method</b></summary>

| Program | What it shows |
|---|---|
| `examples/primes.english` | Testing for primes, listing them, factoring, and perfect numbers. |
| `examples/euclid.english` | The greatest common measure two ways, and fractions in lowest terms. |
| `examples/fibonacci.english` | A loop, a definition that uses itself, and a number of twenty-one digits. |
| `examples/roots.english` | Square roots by Heron's method and by halving, and pi by Machin's formula, in exact fractions. |
| `examples/sorting.english` | A row of things sorted by swapping neighbours, then searched by halving. |
| `examples/hanoi.english` | The Tower of Hanoi: a verb that uses itself. |
| `examples/collatz.english` | `While`, `Skip this round.` and `Stop repeating.` |
| `examples/caesar.english` | A cipher, a palindrome test and counting words: text taken apart a letter at a time. |
| `examples/roman.english` | Roman numerals, both ways, with a table made of things. |
| `examples/bank.english` | Money, percentages, a rule that is never broken, and `Try`. |
| `examples/life.english` | Conway's Game of Life on forty-nine cells, each a thing. |

</details>

## What it does not do

- **It does not accept loose English.** Every sentence must fit one of the forms above.
- **It is slow.** Each sentence costs about a millionth of a second and numbers are exact fractions, which cost many times what a processor's own numbers do. The SHA-256 example, written before the language had lists or remainders, manages about 300 bytes a second.
- **Lists cannot yet be put in order.** They can be written out, added to, indexed and changed, but not sorted, said whole or compared.
- **Several features are designed but not built:** dates and the clock, units, picking and ordering within a group, a kind that is a kind of another, and doing things at the same time. Sections 12 and 13 of [docs/SYNTAX.md](docs/SYNTAX.md) give each a syntax.
- **Plurals are formed by rule** ("dragons", "ponies", "foxes"). An irregular one is not guessed: it has to be stated where the kind is described, as in `A child (plural children) has ...`.
- **The libraries are small.** `page` has thirteen kinds of element, among them tables, menus, pictures and links, and stops there. `vulkan` has run on one computer and draws off screen to a file.

Where the design will strain has been looked at properly. Forty-two concerns were measured against the compiler one by one, and an adversarial review of the reference found twenty-four more things to settle. The verdicts, the figures and what matters most are in **[docs/CONCERNS.md](docs/CONCERNS.md)**.

## The repository

| Path | What is there |
|---|---|
| `englishscript/` | The compiler: `lexer.py` splits the source into sentences, `compiler.py` reads, checks and compiles each one into a Python function in a single pass, `runtime.py` holds what exists while a program runs, `linter.py` reports every problem at once, and `tour.py` is the guided tour. `server.py` and `rename.py` are the editor tools. |
| `englishscript/libraries/` | The libraries a program can `Use`. Its `__init__.py` explains how to write one. |
| `examples/` | The example programs. `examples/almanac/` and `examples/tasks/` are books of chapters. |
| `tests/` | The test suite. |
| `docs/` | The reference and the other documents, and the site that GitHub Pages serves. |
| `tools/` | `build_site.py` builds what the site loads, `pages.py` prints the Markdown documents as pages, and `research/` holds the scripts behind `docs/CONCERNS.md`. |

```bash
python -m unittest discover -s tests
```

The tests that draw on a graphics card skip themselves where there is no Vulkan driver.

After changing the compiler, an example or one of the Markdown documents in `docs`, rebuild what the site loads. Tests fail if any of it is out of date.

```bash
python tools/build_site.py
```

To look at the site on your own computer:

```bash
python -m http.server --directory docs
```

## History

This repository began in June 2023 as a notebook that asked GPT-3.5 to translate English sentences into JavaScript. That experiment's files have been removed; they are in the history at commit `90340fd`.

The present compiler takes the opposite approach. It uses no language model, and it refuses what it cannot read in exactly one way. A language model's natural place is in front of it: rewriting loose English into this strict form, with the compiler as the judge of whether the result is unambiguous. That step is not built.

Most of the code here was written by AI models (Claude) under a person's direction, with one model reviewing another's changes to the compiler.

<p align="center">❦</p>

<p align="center">
  <a href="https://monstercameron.github.io/EnglishScript/playground.html"><b>Open the playground and write a sentence the compiler refuses.</b></a>
</p>

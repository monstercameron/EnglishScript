# EnglishScript

There are two experiments in this repository:

1. **A strict-English compiler** (`englishscript/`, 2026): a plain Python parser, with no AI involved, for a subset of English in which every sentence has exactly one meaning.
2. **The original LLM translator** (`run.ipynb`, 2023): GPT-3.5 turning loose English into JavaScript. Its README is kept [below](#the-original-experiment-english-to-javascript-with-gpt-35).

## The strict-English compiler

It needs Python 3 and nothing else (tested on Python 3.12).

```bash
python -m englishscript
```

That runs a guided tour: a program about dragons, its output, how the compiler read it, and eleven sentences it refuses to compile. To run a program of your own:

```bash
python -m englishscript examples/invoices.english
```

Add `--explain` to see how each sentence was read without running it, or `--check` to compile only.

For something interactive, try the to-do list. It asks for commands (`add Buy milk`, `done 1`, `list`, `quit`, and a few more) and keeps the list in `todo.txt`, in the folder you run it from:

```bash
python -m englishscript examples/todo.english
```

There is also a shaded triangle, drawn in characters. It follows the steps of a Vulkan "hello triangle" but does the graphics card's work itself; it does not use the real Vulkan API:

```bash
python -m englishscript examples/triangle.english
```

### What a program looks like

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

### The idea

English is easy to read because it leaves things unsaid. The compiler allows that only where the unsaid part has exactly one possible reading; anywhere else it stops and says what is unclear.

| English habit | Rule that makes it strict |
|---|---|
| Shared vocabulary | Every noun, adjective and verb must be defined before it is used. |
| "its", "it" | Allowed only when exactly one thing is in view. |
| "the dragon" | Must point at one dragon in the current sentence's context. |
| "treasures of the dragon" | Works only if a treasure is tied to a dragon by exactly one property. |
| "send X against Y" | Prepositions name the verb's roles; each role is typed and required. |
| "A and B or C" | Refused until brackets say which reading is meant. |
| "$5", "10%" | Money, numbers and percentages are different types and do not mix. |
| "never", "always" | A rule checked every time the property changes. |
| "For example, ..." | A test that runs with the program. |
| "if any" | A value that may be missing cannot be used until the program has checked it is there. |

Layout carries the nesting: one sentence per line, a colon and an indent for a block.

### Sentence forms

The full reference is [docs/SYNTAX.md](docs/SYNTAX.md). Its examples are run by the test suite. In brief:

| Purpose | Form |
|---|---|
| Describe a kind | `A dragon has an age (number) and a lair (text).` |
| Define an adjective | `A dragon is ancient when its age is at least 500.` |
| Store an adjective | `A task can be done.` then `Now the task is done.` |
| Define a worked-out property | `The tax of a dragon is 10% of its hoard.` |
| State a rule | `A knight's purse is never less than $0.` |
| Create a thing | `There is a dragon called Smaug whose age is 771.` |
| Make, find and remove things while running | `There is a new task called the title whose position is 1.`, `Let the chick be a new dragon whose age is 0.`, `the dragon called "Smaug"`, `Remove the task.` |
| Teach a verb | `To send a knight against a dragon:` |
| Use a verb | `Send Gawain against Smaug.` |
| Variables | `Let the total be 0.` then `Set`, `Add ... to`, `Subtract ... from`, `Multiply ... by`, `Divide ... by` |
| Fixed variables | `Let the tax rate always be 10%.` |
| Values that may be missing | `a mount (horse, if any)`, `nothing`, `If Wat has a mount:`, `Wat's mount's speed or else 0` |
| Work out a value | `To work out the bounty (money) for a dragon:` with `The answer is ...`, used as `the bounty for Smaug` |
| Leave early | `Stop.`, `Stop repeating.`, `Skip this treasure.`, `End the program.` |
| Output | `Say "{its name} is {its age}."` |
| Input | `Ask "Age?" and let the age (number) be the reply.` |
| Files | `the text of the file "notes.txt"`, `the lines of the file ...`, `Write ... to the file ...`, `Add ... to the file ...` |
| Text | `the length of`, `in upper case`, `the first 3 letters of`, `the words of`, `as a number`, `contains`, `starts with`, `comes before`; `""` and `{new line}` inside quotes |
| Yes or no | `Let done (yes or no) be no.`, `whether Smaug is ancient`, `If done is yes:` |
| Branch | `If ...:`, `Otherwise if ...:`, `Otherwise:` |
| Compare | `is`, `is not`, `is less than`, `is more than`, `is at least`, `is at most`, `is divisible by` |
| Loop | `For each poor dragon:`, `For each rival in dragons:`, `For each word in the words of the line:`, `Repeat 3 times:`, `While ...:` |
| Count and add up | `the number of ancient dragons`, `the total worth of Smaug's treasures`, `the number of items in the words` |
| Recover from a problem | `Try:` then `If that fails:` with `the problem`; `Fail because "..."` |
| Test | `For example, the hoard of Smaug is $12,000.` |

Types are `number`, `money`, `text`, `percent`, `yes or no`, any kind you describe, and lists such as `list of text`. Comments start with `#`.

### Layout of the code

- `englishscript/lexer.py` splits the source into sentences and tokens.
- `englishscript/compiler.py` parses, checks and compiles each sentence into a Python closure in one pass.
- `englishscript/runtime.py` holds what exists while a program runs.
- `englishscript/tour.py` is the guided tour.
- `examples/` has the example programs, including the to-do list; `tests/` has the test suite.

```bash
python -m unittest discover tests
```

### What it does not do

- Lists are only partly there: they come from splitting text or reading a file, and can be counted and looped over, but not written out, changed, sorted or said.
- It has no dates or clock, no fixed sets of choices, units, remainders or rounding, no picking or ordering within a group, and no concurrency yet. Sections 12 and 13 of [docs/SYNTAX.md](docs/SYNTAX.md) give each of these a designed syntax that is not built.
- Plurals are formed by rule ("dragons", "ponies", "foxes"), so irregular ones such as "people" are not recognised.
- It does not accept loose English. The natural next step is the original experiment turned around: use a language model only to rewrite loose English into this strict form, and let this compiler be the judge of whether the result is unambiguous.

---

# The original experiment: English to JavaScript with GPT-3.5

The English Script Programming Language Compiler is a python application that uses OpenAI's GPT-3.5 model to translate English scripts into JavaScript. The application follows certain rules and uses an alias system to understand and transcribe the English scripts. It creates an output JavaScript file and also has the capability to execute this file.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

- Python (>= 3.7)
- [openai](https://github.com/openai/openai) Python package
- [python-dotenv](https://pypi.org/project/python-dotenv/)
- An OpenAI API key

### Installing

1. Clone this repository.
```bash
git clone https://github.com/your-username/english-script-compiler
```

2. Navigate into the project directory.
```bash
cd english-script-compiler
```

3. Install the necessary packages.
```bash
pip install -r requirements.txt
```

### Usage

To use this application, follow the below steps:

1. Create a `.env` file in the root of your project directory and add your OpenAI API key:
```bash
OPENAI_API_KEY=your_api_key
```

2. Now, you can run the main python script, `main.py`:
```bash
python main.py
```

This script will read an English script and use the OpenAI GPT-3.5 model to translate it into a JavaScript file located at `output/index.js`.

### Code Overview

The application's workflow is as follows:

1. Import necessary libraries and load environment variables.
2. Retrieve and set OpenAI API key.
3. Import and set the translation rules and aliases.
4. Use OpenAI's API to perform a chat completion and function call, requesting a JavaScript translation of an English script.
5. Extract the JavaScript translation from the API response and save it into a `.js` file.
6. Execute the resulting JavaScript file.

### Example

Below is an example of how English scripts translate to JavaScript using rules and aliases:

- English Script: `"I have a fixed number that is 1"`
- JavaScript: `"const value = 1;"`

- English Script: `"I have a number a that I add 1 and 2,"`
- JavaScript: `"let a = 1 + 2;"`

- English Script: `"I have a number a that I add a and b then divide by a,"`
- JavaScript: `"let a = (a + b) / a;"`

- English Script: `"show my number a"`
- JavaScript: `"console.log(a);"`

And here is an example of how aliases work:

- Alias: `["const", "constant", "fixed"]`
- This means 'const' in JavaScript can be represented by 'constant' or 'fixed' in English script.

- Alias: `["log", "console", "display", "show"]`
- This means 'console.log' in JavaScript can be represented by 'display' or 'show' in English script.

### Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct, and the process for submitting pull requests to us.

### License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

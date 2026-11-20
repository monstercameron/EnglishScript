# The opposition

EnglishScript is not the first attempt to program in English, and it is not the only new language that brings language models into a program. This page sets out the rivals: what each one was, how it treats a sentence that could mean two things, what it got right, why it stalled or lasted, and what EnglishScript should borrow from it or fear.

It was put together in November 2026 from the rivals' own manuals, papers and repositories, and from what their designers and users have said about them. Every claim that matters links to its source. The code samples were written for this page from each language's documentation and checked against it. Where a source could not be read, or a figure is only the vendor's own, the page says so.

## The short version

| Rival | Year | What happens to a sentence with two readings | Still alive |
|---|---|---|---|
| FLOW-MATIC | 1955 | Cannot be written: fixed verbs and fixed forms | No |
| COBOL | 1960 | Cannot be written: reserved words and fixed formats | Yes |
| SQL | 1974 | Cannot be written: a formal grammar with English keywords | Yes |
| HyperTalk | 1987 | Accepted, with whatever reading the language prefers | Through LiveCode and a fork |
| AppleScript | 1993 | Its meaning depends on which application is being spoken to | Shipped, not developed |
| Inform 7 | 2006 | A reading is chosen by fixed rules, and the program goes on | Yes, open source since 2022 |
| Osmosian Plain English | 2006 | Chosen by marker words; an unmatched sentence is reported | As a hobby |
| Attempto Controlled English | 1996 | One reading is fixed by rule, and shown back as a paraphrase | Uncertain |
| PENG | 2002 | Cannot be typed: the editor offers only what may come next | Research |
| Gherkin | 2008 | **Refused** when two step definitions match one line | Yes |
| Jac `by llm` | 2024 | The model decides; its reply is checked against a type | Yes |
| TypeChat | 2023 | The model decides; the TypeScript compiler checks its reply | Yes |
| Jev | 2026 | The model is asked closed questions and gives probabilities | Early access |
| **EnglishScript** | 2026 | **Refused before the program runs**, with both readings shown | |

Only two of these refuse a sentence because it could mean two things: Gherkin, for the one kind of ambiguity it can detect, and EnglishScript, as its whole principle. Everything else either makes ambiguity impossible to write, by being English only in its vocabulary, or picks a reading by a rule the writer has to know.

## English-like languages, from 1955

### FLOW-MATIC

Grace Hopper's team at Remington Rand specified it in 1955, and it was released about 1958 for UNIVAC business customers who disliked mathematical notation. ([History](https://en.wikipedia.org/wiki/FLOW-MATIC))

```text
(1) COMPARE ACCOUNT-NO (A) WITH ACCOUNT-NO (B) ; IF GREATER GO TO OPERATION 6 ;
    IF EQUAL GO TO OPERATION 3 ; OTHERWISE GO TO OPERATION 2 .
(2) TRANSFER A TO D .
(3) WRITE-ITEM D .
```

A fixed list of verbs and numbered operations left nothing to read two ways. In her 1978 keynote, Hopper recalled that management refused it at first because computers could not understand English, and that she then showed the same program with French and German words in place of the English. Her own conclusion was that a vocabulary which can be swapped mechanically is a code, not a language. ([Hopper, 1978](https://www.cs.hmc.edu/~bang/cs131/assignments/files/hopper-talk-annotated.pdf))

**The lesson.** English words over rigid forms are a substitution cipher, and the designer of the first one said so. EnglishScript's claim has to rest on its grammar, not its vocabulary: articles, pronouns, plurals, possessives and prepositions that mean what they mean in English.

### COBOL

A committee designed it in 1959 and 1960 for business data processing, drawing on FLOW-MATIC. It is still a current standard ([ISO/IEC 1989:2023](https://www.iso.org/standard/74527.html)), and a vendor-commissioned survey in 2022 put the code in daily use at about 800 billion lines, a figure that is extrapolated ([The Register](https://www.theregister.com/2022/12/14/cobol_research/)).

```text
IF HOURS-WORKED IS GREATER THAN 40
    MULTIPLY OVERTIME-HOURS BY OVERTIME-RATE GIVING OVERTIME-PAY
    ADD OVERTIME-PAY TO GROSS-PAY
END-IF.
```

Its statements follow fixed formats with optional filler words, and a survey of controlled languages declines to count it as one, because its structure does not follow English grammar ([Kuhn, 2014](https://arxiv.org/abs/1507.01701)). It was meant to be readable by managers. No evidence was found that managers read it.

**The lesson.** Long descriptive names and a readable surface bought COBOL a working life of sixty years. They did not make non-programmers write it.

### SQL

Donald Chamberlin and Raymond Boyce designed SEQUEL, "Structured English Query Language", at IBM in 1974, for professional programmers and for occasional users who were not specialists. It is a current standard, SQL:2023. ([Chamberlin, 1995](https://www.mcjones.org/System_R/SQL_Reunion_95/sqlr95-System.html))

```text
SELECT NAME
FROM   EMPLOYEE
WHERE  DEPT = 'TOY' AND SALARY > 10000
```

Keywords sit on a formal grammar, and nothing is refused for ambiguity. Looking back in 1995, Chamberlin said the aim of serving non-programmers had not been met as hoped, and that graphical tools had done that job instead. SQL won as a language for programmers, through its model of whole sets at a time, not through its English.

**The lesson.** The idea under the syntax decides whether a language lasts. And the users a language ends up with may not be the ones it was designed for.

### HyperTalk

Dan Winkler designed it for Bill Atkinson's HyperCard, which Apple released in 1987 for people who were not programmers. HyperCard's last release was in 1998. The language lives on in LiveCode and in a community fork, OpenXTalk. ([HyperTalk](https://en.wikipedia.org/wiki/HyperTalk), [OpenXTalk](https://github.com/openxtalk/openxtalk))

```text
on mouseUp
  ask "What is your name?"
  put it into card field "Greeting"
end mouseUp
```

It was permissive rather than strict: several spellings for the same thing, abbreviations, a word `it` that held whatever was last asked, and values converted from one kind to another without a word. It never refused a sentence for being unclear. It was used enormously by amateurs: the game Myst shipped as a HyperCard stack, and Ward Cunningham traces the first wiki to one.

**The lesson.** What made HyperTalk usable was its environment: objects you could see, sending messages you could follow. The page library and the playground are EnglishScript's version of that, and they matter more than any sentence form.

### AppleScript

William Cook, Warren Harris and Kurt Piersol designed it from 1989, and Apple shipped it in 1993 for scripting Mac applications. Scripts were stored apart from their wording, so that they could be shown in other "dialects": a French one and a Japanese one were built, and a dialect like Java was planned and never shipped. Dialects were dropped in 1998. ([Cook, 2007](https://pdos.csail.mit.edu/6.828/2007/readings/applescript.pdf))

```text
tell application "Finder"
    set theName to name of front window
end tell
display dialog "Front window: " & theName
```

Each application brings its own vocabulary when a script is compiled, so the same phrase can mean different things inside different `tell` blocks. Cook, its designer, judged the attempt at natural language unsuccessful, and summed it up in a sentence that every English-like language has to answer: "It is easy to read AppleScript, but quite hard to write it." He also recorded that scripts broke in baffling ways after small edits. John Gruber's essay on [the English-likeness monster](https://daringfireball.net/2005/09/englishlikeness_monster) makes the same case from the user's side: phrases that look alike behave differently.

**The lesson.** This is the danger EnglishScript most needs to answer. A language that only looks like English invites readers to guess right and writers to guess wrong. EnglishScript's answers are that it refuses rather than guesses, says why with a correction, and lets a library's words be named only in a file that uses the library. Whether that is enough to make it easy to write is not yet known. No one outside the project has tried.

### Inform 7: the nearest relative

Graham Nelson began it in 2002, with Emily Short, Andrew Plotkin and others, and released it in 2006 for writers of interactive fiction. It has been open source since April 2022. Nelson estimated in 2018 that between one and two thousand finished works had been written in it. ([Nelson, 2006](https://www.inform-fiction.org/manual/if_theory_reader.pdf); [Nelson, 2018](https://ganelson.github.io/inform-website/talks/2018/06/09/london.html); [source](https://github.com/ganelson/inform))

```text
The Kitchen is a room. The oven is a closed openable container in the Kitchen.
A pie is in the oven. The pie is edible.
Instead of eating the pie when the oven is open, say "It is far too hot."
```

Much of EnglishScript's design is already in Inform 7: kinds, adjectives with definitions, relations instead of pointers, rules instead of methods, explanatory error messages with examples, and source organised like a book. Nelson's paper rejects COBOL and AppleScript as procedural code paraphrased into English, and argues for using the features that make English precise: determiners, tenses, kinds and relations. Its guidelines begin with one EnglishScript shares, that a casual reader's guess at what a sentence means should be right.

The difference is what happens when a sentence could be read two ways. Inform 7 chooses, by rules. When a phrase matches two definitions, the one with more words wins ([Writing with Inform, 22.10](https://ganelson.github.io/inform-website/book/WI_22_10.html)). Types are used to choose between readings. Nelson documents the failures himself: an early version read "The life support unit fits the egg" with "support" as the verb, and a handbook warns that names containing prepositions are misread ([Inform 7 Handbook](https://inform-7-handbook.readthedocs.io/en/v2.0/chapter_3_things/the_names_of_things/)). No general mechanism was found that refuses a sentence because it has two valid readings, though that absence could not be confirmed.

**The lesson, and the threat.** Inform 7 proves that a deterministic compiler can build real programs out of real sentences, and its documented weak point is the silent misreading. EnglishScript's refusal is aimed exactly there, and is the one real difference between them. Against that, Inform 7 has a twenty-year start in documentation, worked examples, an editor and a community. Nelson's own list of its troubles is worth reading as a list of EnglishScript's future ones: a high barrier to entry for people who are not its intended writers, a code base too large for one person, and years between releases.

### Osmosian Plain English

Gerry and Dan Rzeppa wrote it in 2005 and 2006: a compiler and editor for Windows, under a megabyte, written in its own language. ([Instructions](http://www.osmosian.com/instructions.pdf), [Rosetta Code](https://rosettacode.org/wiki/Category:Plain_English))

```text
To run:
  Start up.
  Clear the screen.
  Write "HELLO WORLD".
  Refresh the screen.
  Wait for the escape key.
  Shut down.
```

It knows five kinds of sentence, told apart by the first word, and a name runs from an article to the next verb, preposition or mark of punctuation. A sentence that matches no routine is reported. It is the closest in spirit to EnglishScript's way of reading a sentence, and proof that a tiny deterministic English compiler can build itself. It has no objects, no real numbers, one platform and almost no users.

**The lesson.** Predictable rules for reading are not enough on their own. A language needs platforms, libraries and people.

### Attempto Controlled English, PENG and business-rule English

Attempto Controlled English was developed at the University of Zurich from 1995 for writing specifications ([ACE](https://en.wikipedia.org/wiki/Attempto_Controlled_English)). Its rules give every sentence exactly one reading, such as a prepositional phrase always attaching to the verb, and the system shows the writer a paraphrase of the reading it took, which the writer can accept or reword. PENG ([Schwitter, 2003](https://aclweb.org/anthology/2003.eamt-1.17.pdf)) went further, with an editor that offers only the words that may legally come next, so a sentence outside the language cannot be typed. SBVR Structured English and RuleSpeak are notations for business rules.

```text
Every customer owns a card.
It is obligatory that each rental car is owned by exactly one branch.
```

Tobias Kuhn's survey of a hundred English-based controlled languages ([Kuhn, 2014](https://arxiv.org/abs/1507.01701)) found that the more precise a language is, the less natural and the less expressive it tends to be.

**The lesson.** There are three honest answers to ambiguity: fix a reading and show it (Attempto), prevent it at the keyboard (PENG), or refuse it (EnglishScript). EnglishScript already shows its reading with `--explain` and in the playground, and its language server offers what may come next. Kuhn's trade-off is the one it lives inside.

### Gherkin

Aslak Hellesøy started Cucumber in 2008, and Gherkin is its format for tests written as Given, When and Then ([reference](https://cucumber.io/docs/gherkin/reference/)).

```text
Feature: Cash withdrawal
  Scenario: Enough money in the account
    Given the account balance is 100
    When I withdraw 20
    Then the account balance should be 80
```

Only the structuring words are fixed. Every line is matched by patterns to code that programmers write, and when two of those patterns match one line, Cucumber stops with an error that the step is ambiguous. It is the one widely used tool that refuses on ambiguity. Its creator wrote in 2014 that most people use it as a testing tool, and that business people rarely take part in writing the scenarios ([Hellesøy](https://cucumber.io/blog/collaboration/the-worlds-most-misunderstood-collaboration-tool/)).

**The lesson.** People who are not programmers will read English that describes a program. They seldom write it. EnglishScript's best case may be the same: a language that the people who asked for a program can read and check, written by programmers, or by models.

### Others

- **Lingo**, for Macromedia Director (1989), began with a wordy English-like syntax modelled on HyperTalk and later added the usual dot notation, which most of its programmers moved to. ([Lingo](https://en.wikipedia.org/wiki/Lingo_(programming_language)))
- **Natural** (Software AG, 1979) is English in its keywords only, and lasts through one vendor's database.
- **Quorum** chose its keywords by experiment. One study found that novices did no better with Perl than with a language whose keywords were chosen at random ([Stefik and Siebert, 2013](https://www.vidarholen.net/~vidar/An_Empirical_Investigation_into_Programming_Language_Syntax.pdf)).
- **Hedy** (Felienne Hermans, 2020) teaches programming with a syntax that grows level by level into Python ([paper](https://www.hedy.org/research/Hedy_A_Gradual_Language_for_Programming_Education_2020.pdf)).
- **Research systems** such as NaturalJava (2000), Metafor (2005) and Pegasus (2006) turned free English into code or scaffolding. Their own authors report that arbitrary English could not be turned into complete programs.

## Languages that ask a model

Since 2023 a second kind of rival has appeared. These do not make English strict. They let a program hand a question to a language model, and they differ in how the answer is given a type, what happens when it does not fit, and how a program that depends on one is tested.

| System | Where the prompt is | How the answer is typed | When it does not fit | How it is tested |
|---|---|---|---|---|
| [Jac](https://docs.jaseci.org/reference/plugins/byllm/) `by llm` | Nowhere: the function's name, parameters and return type are the prompt | The declared return type | Converted, then asked again up to three times, then an error with the raw reply | A built-in stand-in model with written-down answers |
| [DSPy](https://dspy.ai/) | Built from a signature and improved by an optimiser | Typed output fields | The adapter tries another format | Answers cached by default; metrics drive optimisation |
| [BAML](https://docs.boundaryml.com/guide/introduction/why-baml.md) | A template inside a typed function | A forgiving reader repairs the reply into the type | An error carrying the prompt and the reply | Test blocks with assertions, against the live model |
| [TypeChat](https://microsoft.github.io/TypeChat/blog/introducing-typechat/) | Built from TypeScript types | The TypeScript compiler checks the reply | The compiler's errors are sent back to the model | Left to the programmer |
| [Instructor](https://python.useinstructor.com/concepts/retrying/), [Marvin](https://github.com/PrefectHQ/marvin) | The host program's messages | A Python data model | Asked again, then an error | Left to the programmer |
| [Outlines](https://github.com/dottxt-ai/outlines), [Guidance](https://github.com/guidance-ai/guidance), [LMQL](https://lmql.ai/docs/language/constraints.html) | Code, with holes | A grammar enforced while the model writes | Cannot happen, except when cut short | Left to the programmer |
| [SudoLang](https://github.com/paralleldrive/sudolang-llm-support), [Marsha](https://github.com/alantech/marsha) | The whole program is read by the model | Not enforced, or by generated tests | Nothing happens, or the code is written again | Marsha turns required examples into tests |
| [Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev) | A state and closed, typed questions | Choices, scores and yes-or-no, as probabilities | Cannot happen: it writes no text | Thresholds tuned on your own data |

Three of these are worth a closer look.

**Jac** (Jaseci, 2024; [paper](https://arxiv.org/abs/2405.08965)) has no prompt at all. A function declared `by llm()` is filled in by a model, and its name, its parameters and its return type say what is wanted. That is the best idea in this group, and its weakness is the same: the meaning rides on names that nothing checks.

```text
def analyze_sentiment(text: str) -> Sentiment by llm();
```

**TypeChat** (Microsoft, 2023) is the closest engineering precedent for EnglishScript's arrangement: a deterministic compiler is the judge of what the model writes, and its complaints go back to the model to repair. It checks the shape of the answer, not whether it is right.

**Jev** (TypeSafe AI, September 2026) is a different kind of model. It writes no text. A program sends it a state, which may be text or data, and named questions of four kinds: a *Choice* among up to 255 listed options, a *Score* on an ordered scale, a *Noul* (a yes or no, given as one probability), and a *Box* in a picture. Each comes back as a probability, and ordinary code decides what to do with it. Its documentation recommends three bands: act when an answer is likely enough, ask a person to confirm when it is not sure, and hand over to a person when it is unlikely. It recommends asking one simple question at a time and combining the answers in code. ([Documentation](https://docs.typesafe.ai/introduction), [confidence](https://docs.typesafe.ai/confidence))

The claims need care. Its speed and price advantages, about two hundred and four hundred times, are the vendor's own measurements, and its comparisons used answers averaged from two other models as the reference. Its documentation says that its "confidence" measures how concentrated the probabilities are, not the chance that the answer is right. A security firm reports that it is easier to mislead with inserted characters than larger models are ([InfoWorld](https://www.infoworld.com/article/4236103/typesafes-jev-even-more-susceptible-to-attack-than-llms-says-security-vendor.html)). It is in early access.

**What works, across all of them.** Declare the type of the answer and let the declaration do much of the asking. Make a malformed answer impossible where possible, and otherwise check it, ask again with the error, and fail with the raw answer attached. Keep written-down answers so that tests run without a model: only Jac ships that, and only DSPy caches by default. Treat a refusal, an answer cut short and an uncertain answer as different outcomes. Jev is alone in returning its doubt as a value a program can branch on.

**Where EnglishScript stands.** EnglishScript's compiler has no model in it, and never will. A program may now ask one, in two ways. `Ask the model ... and let the summary (text) be the reply.` asks a model that writes, and the reply is read by the same strict reader that reads a person's typed reply: if it cannot be read as the type, the model is told why and asked again, and then it is a problem a program can recover from. `Judge ... about the letter and let the team (team) be the verdict.` asks a model that only decides, in Jev's manner, and gives back a choice or a chance for ordinary sentences to act on. A judgement may also be a *grade* on an ordered scale, worked out from all the probabilities rather than picked from the top, in the manner of Jev's Score; and consecutive judgements about the same thing go to the judge in one request, as Jev is meant to be asked. The same question about the same thing gets one answer in a run. Answers can be recorded and replayed, so a program that asks a model can be tested without one. Section 7.8 of [the grammar](reference.html) gives the details, and `examples/triage.english` sorts a post bag this way.

## The arguments

**Dijkstra, 1979.** In [On the foolishness of "natural language programming"](https://www.cs.utexas.edu/~EWD/transcriptions/EWD06xx/EWD667.html), Edsger Dijkstra argued that moving the interface with a machine toward natural language adds work on both sides; that mathematics advanced only when it left words for symbols; that the value of a formal text is that a few simple rules govern it and rule out nonsense; and that the ease of a native language is largely the ease of saying things whose nonsense is not obvious. His first argument is aimed at programming in a full natural language, which EnglishScript is not. His last argument is aimed squarely at it, and the refusal of ambiguous sentences is its reply.

**Hopper, 1978.** An English vocabulary over fixed forms is a code, not a language.

**Nelson, 2006.** Natural language is not necessarily wordy, and precise documents are written in it every day, provided the language uses the features of English that carry precision, rather than paraphrasing procedural code.

**Cook, 2007.** The designer of AppleScript judged its natural-language experiment a failure: easy to read and hard to write.

**Pane and Myers, 2001.** Asked to describe programs, people who were not programmers wrote rules and events, and acted on whole groups rather than writing loops. They used "and" where they meant "or", and their reading of "not" depended on context ([Pane and Myers, 2000](https://ppig.org/files/2000-PPIG-12th-pane.pdf)). The first finding supports EnglishScript's rules and reactions. The second supports refusing to guess what "and" with "or" means.

**Kuhn, 2014.** Across a hundred controlled English languages, precision and naturalness pull against each other.

**Karpathy, 2023 and 2025.** Andrej Karpathy's remark that the hottest new programming language is English ([2023](https://twitter.com/karpathy/status/1617979122625712128)), and his name for accepting model-written code without reading it, "vibe coding" ([2025](https://x.com/karpathy/status/1886192184808149383)), describe the arrangement that EnglishScript is set against. Measured studies point the same way: people with a coding assistant wrote less secure code and were more confident that it was secure ([Perry et al., 2023](https://arxiv.org/abs/2211.03622)), and experienced developers in one trial were slower with assistance while believing they were faster ([METR, 2025](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/)). People over-trust fluent output. That is the case for a judge that is a machine and not another model.

**Has the arrangement been tried?** In narrow fields, yes. A model rewriting requests into a controlled English that a machine then reads did better than other methods in semantic parsing ([Shin et al., 2021](https://arxiv.org/abs/2104.08768)). Models writing structured English for NASA requirements ([ARTEMIS, 2026](https://cs.stanford.edu/~trippel/pubs/mendoza_ICSE26.pdf)), and writing controlled language for proof checkers, have shown early promise. Results are good where the grammar is enforced while the model writes, or where errors go back to it, and mixed where the model has to hit an unfamiliar language unaided: in one small study, going through a controlled English did worse than writing the target language directly ([2026](https://arxiv.org/abs/2609.20334)). No general-purpose programming language in strict English, with a one-meaning compiler as the judge of a model's writing, was found. That is a gap in this search, not proof that none exists.

## What this means for EnglishScript

**Where it is different.** Of every rival here, only EnglishScript refuses a sentence because it could mean two things, and says which two. And only EnglishScript offers itself as the strict, readable target that a model writes and a deterministic compiler judges, in a general-purpose language.

**What to fear.**

- Cook's verdict on AppleScript: easy to read, hard to write. Nobody outside this project has tried to write EnglishScript, so it is not known whether the refusals and their corrections are enough.
- Kuhn's trade-off. Each refusal that makes EnglishScript more precise makes it less natural to write.
- Inform 7's twenty-year start, in the very design EnglishScript shares.
- The finding from Gherkin and SQL that the people a language is written for read it and do not write it.
- The evidence that models write an unfamiliar controlled language less well than a familiar one unless the grammar is enforced as they write. EnglishScript's corrections give a model something to repair with, but no model has been trained on it.

**What to borrow.**

- From Attempto: show the reading that was taken, always. `--explain` does this; the playground could show it beside each sentence as it is written.
- From PENG: offer only what may come next. The language server's completion is the start of it.
- From Inform 7: worked examples by the hundred, and a book that teaches.
- From Jac: a stand-in model for tests, built in. From DSPy: answers kept, so a program runs the same twice. EnglishScript's recorded and replayed answers do both.
- From Jev: an answer's doubt as a value, and three bands written as ordinary sentences.
- From HyperTalk: an environment in which a beginner can see what the program is doing.

## Sources

The sources are linked where they are used above. In addition: the Hopper keynote, [annotated](https://www.cs.hmc.edu/~bang/cs131/assignments/files/hopper-talk-annotated.pdf); [Kuhn's survey of controlled natural languages](https://arxiv.org/abs/1507.01701); [Nelson's paper on natural language and interactive fiction](https://www.inform-fiction.org/manual/if_theory_reader.pdf); [Cook's history of AppleScript](https://pdos.csail.mit.edu/6.828/2007/readings/applescript.pdf); [TypeSafe's documentation for Jev](https://docs.typesafe.ai/introduction); [Anthropic's documentation on structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs). Jean Sammet's 1966 paper on English as a programming language, and the papers on Metafor and Pegasus, could not be read for this page, and nothing here depends on them.

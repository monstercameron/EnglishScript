# EnglishScript syntax

This document describes every sentence the EnglishScript compiler accepts. Sections 1 to 11 describe the language as implemented in `englishscript/`. Sections 12 and 13 are proposed extensions that have been designed but not built; the parts of them that have since been built are described in sections 2 to 9, and sections 12 and 13 say which they are. Section 14 lists what has not been defined yet.

The examples are checked by the test suite:

- A block marked `englishscript` is compiled and run. A comment starting `#>` states a line the program says, and the test compares them.
- A block marked `refused` must be rejected by the compiler (or stopped while running).

In the sentence forms, `<angle brackets>` mark something you supply, `[square brackets]` mark an optional part, `a | b` is a choice, and `...` means the part before it may repeat.

Every example builds on this small world:

```englishscript
A dragon has an age (number).
A treasure has a worth (money) and an owner (dragon).
A knight has a purse (money) and a courage (number).

The hoard of a dragon is the total worth of its treasures.
A dragon is ancient when its age is at least 500.
A knight is brave when its courage is more than 5.
A knight's purse is never less than $0.

There is a dragon called Smaug whose age is 771.
There is a dragon called Norbert whose age is 1.
There is a treasure called Goblet whose worth is $3,000 and whose owner is Smaug.
There is a treasure called Cup whose worth is $500 and whose owner is Smaug.
There is a knight called Gawain whose purse is $300 and whose courage is 8.
There is a knight called Robin whose purse is $20 and whose courage is 2.
```

## 1. Layout

- **One sentence per line.** A sentence ends with a period.
- **A colon opens a block.** The sentences that belong to it are indented further, with spaces. Tabs are refused. Any depth of indent works, but sentences in the same block must line up.
- **A closing quote may end a sentence**, so `Say "Hello."` needs no second period. That is the one exception to the period, and it stays: a sentence whose last word is a text ends at its closing quotation mark, and the examples in this document write no period after it.
- **`#` starts a comment** that runs to the end of the line. Blank lines are ignored.
- **Capitals don't matter.** `Say`, `say` and `SAY` are the same word, and so are `Smaug` and `smaug`. A name is shown the way it was first written.
- Curly quotes (“ ” ’) are read as straight ones.

```englishscript
# A comment on its own line.
Say "Hello, world!"              #> Hello, world!
If Smaug is ancient:
  say "Capitals don't matter."   #> Capitals don't matter.
  SAY smaug's AGE.               #> 771
Say “Curly quotes work.”         #> Curly quotes work.
```

## 2. Values and types

Every value has one of these types. The compiler works out each type before the program runs. The words used in this document: a **type** is what sort of value something is; a **kind** is a type described by the program (`dragon`), whose values are **things**; a **property** belongs to a thing, and is stored or worked out (a **worked-out property**); an **adjective** is said of a thing, stored or worked out; a **worked-out value** is defined with `To work out`. The type of `10%` is written `percent`, and such a value is called a **percentage**.

| Type | Written | Said as |
|---|---|---|
| `number` | `7`, `1,000`, `2.5` | `7`, `1,000`, `2.5` |
| `money` | `$5`, `$1,000`, `$0.50` | `$5`, `$1,000`, `$0.50` |
| `percent` | `10%`, `2.5%` | `10%`, `2.5%` |
| `text` | `"Hello"` | `Hello` |
| `yes or no` | `yes`, `no` | `yes`, `no` |
| a kind, such as `dragon` | the thing's name, `Smaug` | `Smaug` |
| `list of <plural type>`, such as `list of text` | `a list of 3, 8 and 5`; see "Lists" below | cannot be said yet; see `joined with` |

- A comma in a number must be followed by exactly three digits.
- There are no negative literals; write a minus sign in front: `-5`, `-$5`.
- Arithmetic is exact, so `0.1 + 0.2` is `0.3`. Rounding happens only when a value is said (or filled into a text), and it is done on the exact value, never through an approximation: a number is said to at most four places, money to the cent, and a percentage to at most four places of its percent figure. A half is rounded away from zero, so `0.00005` is said as `0.0001` and `$0.125` as `$0.13`. A value that rounds to nothing is said as `0` or `$0`, never `-0`. However many digits a value has, it is said in full: `123,456,789,012,345,678,901 + 0.5` is said as `123,456,789,012,345,678,901.5`.
- A condition produces a yes-or-no answer. That answer can steer `If`, `While` and definitions. To store it or say it, turn it into a `yes or no` value with `whether` (below).

```englishscript
Say 1,000 + 2.5.       #> 1,002.5
Say $1,000 + $0.50.    #> $1,000.50
Say 50%.               #> 50%
Say 0.1 + 0.2.         #> 0.3
Say 1 / 3.             #> 0.3333
Say $10 / 3.           #> $3.33
Say $0.125.            #> $0.13
Say -0.00001.          #> 0
Say 123,456,789,012,345,678,901 + 0.5.   #> 123,456,789,012,345,678,901.5
Say -$5.               #> -$5
Say Smaug.             #> Smaug
```

### Text

Text sits between double quotes. Anything inside `{braces}` is a value, worked out when the text is made: where the quoted text stands in the program, so `Let the note be "{the count}".` keeps the count as it was then, however the count changes later. Four things are written specially:

| Written | Means |
|---|---|
| `""` | one double quote |
| `{{` | one opening brace |
| `}}` | one closing brace |
| `{new line}` | a line break |

A fill-in cannot contain quotes of its own, because the first quote would end the text. Work such a value out with `Let` first.

```englishscript
Say "Smaug is {Smaug's age} and guards {the hoard of Smaug}."   #> Smaug is 771 and guards $3,500.
Say "Half of that is {50% of Smaug's hoard}."                   #> Half of that is $1,750.
Say "The ""Lonely"" Mountain"                                   #> The "Lonely" Mountain
Say "{{Smaug}} is written {Smaug}."                             #> {Smaug} is written Smaug.
```

Section 5.6 lists what can be done with text.

### Yes or no

```text
(yes or no)                  the type
yes | no                     its two values
whether <condition>          a condition, as a value
<value> is [not] yes | no    a value, as a condition
```

A `yes or no` value may be kept in a variable, a role or a worked-out value. A property cannot be yes or no: a yes-or-no fact about a thing is an adjective, written `A knight can be sworn.` (section 4.3).

`whether` takes one comparison, or a condition in brackets. A condition with `and` or `or` after `whether` must be in brackets, because `whether A and B` could mean `whether (A and B)` or `(whether A) and B`; it is refused with both readings.

```refused
Let the gate open be whether Gawain is brave or Robin is brave.
```

```englishscript
Let the gate open be whether (Gawain is brave or Robin is brave).
Say the gate open.                   #> yes
Let the alarm (yes or no) be no.
If the gate open is yes and the alarm is no:
  Say "Enter."                       #> Enter.
```

Refused, with a pointer to `A gate can be open.`:

```refused
A gate has a width (number) and an open (yes or no).
```

### Lists

A list holds values of one type, in order, numbered from 1.

```text
(list of <plural type>)                    the type
a list of <value>, <value> ... and <value> a list written out
an empty list of <plural type>             a list with no items
```

- The plural type is `numbers`, `percentages`, `money`, `text`, or the plural of a kind, such as `dragons`.
- A list may be kept in a variable, a role, a worked-out value or a property (`A knight has a trophy shelf (list of treasures).`). A list property that is not given when a thing is made starts empty.
- **A list written out may appear only as the whole value** of `Let`, `Set`, a `whose` part or `The answer is`, so that its commas and its `and` can't be taken for anything else. Its items are all of one type; `a list of 5` has one item.
- **A group given where a list is expected becomes a list** of the things in it at that moment: as the whole value of `Let`, `Set`, a `whose` part or `The answer is`, and as a role of a verb or a worked-out value whose type is a list. `Let the suspects be all poor dragons.` makes a list of dragons; making another poor dragon afterwards does not change it.
- Lists also come from `the words of` and `the lines of` (section 5.6) and from reading a file (section 7.7).

Reading a list:

| Form | Gives |
|---|---|
| `the number of items in <list>` | a number |
| `item <number> of <list>` | the item, if any: nothing when there is no such item (a number that is not a whole number from 1 to the number of items) |
| `the first of <list>`, `the last of <list>` | an item, if any: nothing for an empty list |
| `the total of <list>` | a number or money: the items added up, 0 or $0 for an empty list |
| `<list> joined with <text>` | text: the items, each said as `Say` would say it, with the text between them. A list of text, numbers, money or percentages only. |
| `<value> is [not] in <list>` | a condition: is the value one of the items? |
| `For each <name> in <list>:` | goes through the items in order (section 8.2) |

- Each `<number>`, `<list>` and `<text>` here is a single value or a bracketed expression. `joined with`, like `as a number`, applies to the single value just before it.
- `item` and `joined` are not reserved: `item` is read this way only when a value and `of` follow it, and `joined` only after a list and before `with`. A variable may still be called `item`.
- `the first of`, `the last of` and `the total of` are told from `the first 3 letters of` and `the total worth of dragons` by the `of` straight after the word, and are read this way only when what follows `of` is a list. If a worked-out value or a property called `first`, `last` or `total` is also in view, such a phrase could be read two ways, and is refused.

Changing a list:

| Sentence | Does |
|---|---|
| `Add <value> to <list>.` | Puts the value at the end. |
| `Remove <value> from <list>.` | Takes out the first item equal to it. If there is none, nothing happens. |
| `Set item <number> of <list> to <value>.` | Replaces that item. If there is no such item, that is a problem a `Try` can recover from (section 8.5). |

- The list is a variable, or a list property of a thing (`Add Goblet to Gawain's trophy shelf.`). Whether `Add` puts an item on the end of a list or adds up a number is decided by the type of what is added to, which is always known. `Remove <value> from <list>.` is told from `Remove <thing>.` (section 7.5) by its `from`.
- These are changing sentences, like `Set`: a failed `Try` undoes them; they may not appear in `To work out` unless the list is a variable made in that block; and they count for reactions and for "settled" (section 9.5).
- `For each <name> in <list>:` goes through the list as it was when the loop began, whatever the block does to it.
- A thing that is removed (section 7.5) leaves every list property it is in. A variable that holds a list keeps it, as a variable may keep a removed thing.

```englishscript
Let the scores be a list of 3, 8 and 5.
Add 10 to the scores.
Say the number of items in the scores.         #> 4
Say the total of the scores.                   #> 26
Say the scores joined with ", "                #> 3, 8, 5, 10
Say item 2 of the scores.                      #> 8
Say item 9 of the scores.                      #> nothing
Set item 2 of the scores to 7.
Remove 3 from the scores.
Say the first of the scores or else 0.         #> 7
If 10 is in the scores and 3 is not in the scores:
  Say "ten, and no three"                      #> ten, and no three
Let the parts (list of text) be the words of "fire and smoke"
For each part in the parts:
  Say the length of the part.
#> 4
#> 3
#> 5
```

```englishscript
A shelf has a display (list of treasures).
There is a shelf called Mantel whose display is a list of Cup.
Add Goblet to Mantel's display.
Let the costly be all treasures whose worth is more than $1,000.
Say the number of items in Mantel's display.             #> 2
Say the number of items in the costly.                   #> 1
Let the none be an empty list of numbers.
Say the total of the none.                               #> 0
Try:
  Set item 5 of the none to 1.
If that fails:
  Say the problem.                                       #> There is no item 5 of the none: it has 0 items.
```

```refused
Say the words of "fire and smoke"
```

```refused
Say the number of items in a list of 1 and 2.
```

```refused
Let the scores be a list of 3, "eight" and 5.
```

### Nothing

Adding `, if any` to a type in brackets makes a value that may be missing. The missing value is written `nothing`.

```text
(<type>, if any)                       a type whose value may be missing
nothing                                the missing value
<thing> has a | an <property>          condition: the property is there
<thing> has no <property>              condition: the property is missing
<value> is [not] nothing               condition
<value> or else <value>                the first value, or the second if the first is nothing
```

- `, if any` may be added to the type of a property, a role, a variable, or a worked-out value.
- A property marked `if any` may be left out when a thing is created. It is then nothing.
- A property of something that may be nothing may itself be nothing: `Tom's mount's speed` is a number, if any.
- **A value that may be nothing is refused wherever a value is needed**: in arithmetic, in a comparison other than `is nothing`, as a role, or as the owner of a group. It may be said, and is said as `nothing`.
- `the total` leaves out things whose property is nothing.
- Because a property can be left out, a kind may have a property of its own kind.

The compiler stops refusing once the program has checked, or has itself put a value there. This is the whole list of what counts:

1. inside an `If` (or `Otherwise if`) whose condition shows the value is there (`is not nothing`, `has a`);
2. in the rest of that condition, after `and` (and, after `or`, what the earlier part showed missing);
3. in a later `Otherwise if` or `Otherwise` of an `If` whose earlier condition showed it missing;
4. after an `If` that showed it missing and whose every branch always leaves (section 8.4);
5. inside a `While` whose condition shows the value is there, each time round;
6. after `Let` or `Set` gives a variable or a stored property a value that cannot be nothing.

A check stops counting when that property or variable is changed, and when a verb is used, because a verb may change anything. In a program that has a `Whenever` (section 9.5), a check of a property or of a top-level variable also stops counting after any sentence that changes a thing, a top-level variable or a file, because a reaction may follow that sentence and change anything.

A loop's block is carried out again after its own last sentence, so what was known before a loop counts inside it only if no sentence of the block can change it (by the rules just given). After a `Try` and its `If that fails`, only what was known before the `Try` and still holds after both blocks counts.

```englishscript
A link has a label (text) and a next (link, if any).
There is a link called Tail whose label is "tail"
There is a link called Head whose label is "head" and whose next is Tail.
Let the spot (link, if any) be Head.
While the spot is not nothing:
  Say the spot's label.
  Set the spot to the spot's next.
#> head
#> tail
```

```englishscript
A horse has a speed (number).
A squire has a wage (money) and a mount (horse, if any).

There is a horse called Shadowfax whose speed is 40.
There is a squire called Wat whose wage is $3 and whose mount is Shadowfax.
There is a squire called Tom whose wage is $2.

Say Tom's mount.                          #> nothing
Say Tom's mount's speed or else 0.        #> 0
For each squire:
  If the squire has a mount:
    Say "{the squire} rides at {the squire's mount's speed * 2}."
  Otherwise:
    Say "{the squire} walks."
#> Wat rides at 80.
#> Tom walks.
If Wat has a mount and Wat's mount's speed is more than 30:
  Say "Wat is quick."                     #> Wat is quick.
Set Wat's mount to nothing.
If Wat's mount is nothing:
  Say "Wat walks now."                    #> Wat walks now.
```

Refused, because Tom may have no mount:

```refused
A horse has a speed (number).
A squire has a wage (money) and a mount (horse, if any).
There is a squire called Tom whose wage is $2.
Say Tom's mount's speed + 1.
```

## 3. Names

A word is letters, digits and underscores, starting with a letter. A **letter** is a letter of any alphabet, accented or not (`Fáfnir`, `Größe`); a **digit** in a word is any digit, but a number is written only with the digits 0 to 9. Capitals are folded as Python folds them (`str.lower`). The plural rule, and `a` or `an` (section 4.1), look only at the unaccented English letters, so a kind spelt otherwise may need its plural stated, and `comes before` (section 6) orders letters by their character codes.

| What is named | Length |
|---|---|
| Kind, adjective, verb | one word |
| Property, variable, thing | one or more words |

Three rules apply to every name:

1. **Defined before use.** A sentence may only use kinds, things, adjectives, properties, verbs and variables introduced by an earlier sentence.
2. **One meaning in view.** A name cannot be reused while an earlier meaning is still visible. To change a variable, use `Set`, not a second `Let`. In a program of several files, what is "in view" is the file's own names and those shared by the chapters it uses (section 9.6).
3. **No reserved words.** None of the words below may be part of a new name.

A name of several words is found by its words, up to twelve of them: a name of more than twelve words can be made, but never found again, so it is of no use.

A name of several words is read **longest first, with no going back**: where the words of a sentence could start a longer name or a shorter one, the longer one is taken, and if the sentence then cannot go on, it is refused rather than read again with the shorter name. So with variables `the word` and `the word starts`, `If the word starts with "a":` reads `the word starts`, and is refused because `with` cannot follow it.

```refused
Let the word be "apple"
Let the word starts be 1.
If the word starts with "a":
  Say 1.
```

| Group | Reserved words |
|---|---|
| Articles and pronouns | `a` `an` `the` `it` `its` `they` `them` `their` |
| Built-in verbs | `let` `set` `add` `subtract` `multiply` `divide` `say` `if` `repeat` `while` `there` `stop` `skip` `end` `now` `remove` `ask` `write` `try` `fail` `use` `whenever` (and `for`, listed with the prepositions) |
| Types | `number` `money` `text` `percent` `yes` `no` `list` |
| Linking words | `of` `is` `are` `be` `has` `called` `whose` `when` `each` `all` `otherwise` `example` `name` `nothing` `any` `else` `answer` `whether` `can` `in` `new` `reply` `problem` `items` `becomes` |
| Logic and comparison | `not` `and` `or` `never` `always` `than` `less` `more` `greater` `least` `most` `divisible` |
| Arithmetic | `plus` `minus` `times` `divided` |
| Prepositions | `with` `to` `from` `against` `for` `by` `on` `at` `into` `onto` `about` `over` `under` `as` `through` `toward` `towards` `upon` |

**This list is frozen.** A new word in it would break every program that already uses that word in a name, so a new sentence form is recognised by where its words stand instead, wherever that can be done. Many words of the built forms are already free in this way, and may be part of names: `that`, `this`, `round`, `program`, `file`, `total`, `first`, `last`, `item`, `letter`, `letters`, `length`, `words`, `lines`, `upper`, `lower`, `case`, `chapter`, `book`, `library`, `shares`, `only`, `everything`, `settled`, `keep`, `either`, `way`, `again`, `because`, `joined`, `empty`, `remainder`, `rounded`, `nearest`, `raised`, `power`, `square`, `root`, `larger`, `smaller`, `absolute`, `value`, `does`, `contain`, `contains`, `starts`, `ends`, `comes`, `before`, `after`, `one`, `plural`, `done` and `fails`. Each is read as part of its form only where the form's other words stand around it (`the total of` a list, `Skip this round`, `the text of the file`), and as a name everywhere else.

**Plurals** are formed by rule: add `s`; add `es` after `s`, `x`, `z`, `ch` or `sh`; change a consonant plus `y` to `ies`. So `dragon` gives `dragons`, `fox` gives `foxes` and `pony` gives `ponies`. Another plural can be stated where the kind is described: `A child (plural children) has ...` (section 4.1). Every kind has its own name and its own plural: a kind whose name or plural is already another kind's name or plural is refused (`bus` and `buse` would both be `buses`; `ax` and `axe` both `axes`; a kind `dragons` beside `dragon`).

**Which names may share a word.** There are four sets of words:

| Set | What is in it | Reached |
|---|---|---|
| Names | kinds and their plurals, things, variables (of the top level and of blocks), roles, the names of loops' things, worked-out values | on their own, or after `the` |
| Adjectives | the adjectives of every kind | after `is`, or in front of a kind |
| Properties | the properties of each kind, stored or worked out | only after `'s`, `its`, `of` or `whose` |
| Verbs | the verbs taught with `To` | only first in a sentence |

- **A word is never both a name and an adjective**, whichever comes first, because `If Smaug is ancient` must read one way. An adjective's word may not be the name of a kind, a thing, a variable, a role or a loop's thing, nor begin one; and no such name may be made with, or begin with, a word that is an adjective. So `For each ancient rival in dragons:` is refused: a reader would take `ancient` as a filter, and `For each ancient dragon:` says that.
- A property belongs to its kind, and may be the same word as anything else, since it is only reached through a possessive, `of` or `whose`.
- A verb is told apart by standing first in its sentence, and may share its word with a name or a worked-out value.

## 4. Describing the world

These sentence forms are definitions. They are allowed only at the top level, never inside a block.

### 4.1 Kinds

```text
A | An <kind> has a | an <property> (<type>) [, a | an <property> (<type>)]... .
```

- The type in brackets is required. It is `number`, `money`, `text`, `percent`, or a kind that has already been described. Adding `, if any` lets the property be missing (section 2).
- Properties are separated by a comma, by `and`, or by both.
- Every thing also has a `name`, which is text and cannot be changed.

```englishscript
A wizard has a hat size (number) and a motto (text).
A tower has a height (number), a keeper (knight), and a prisoner (dragon).
```

A kind's plural is formed by rule (section 3). Another plural is stated in brackets after the kind's name, where the kind is described:

```text
A | An <kind> (plural <word>) has ...
```

- `<word>` is then the plural, and the plural formed by rule is not a word.
- The plural must differ from the kind's name: with `sheep` for both, `the sheep` would mean one sheep and all of them at once, so it is refused. It must not be any other kind's name or plural, or any other name (section 3).
- Writing a plural the kind does not have, such as `children` for a kind `child` described without one, is refused with this form as the way to state it.

```englishscript
A child (plural children) has an age (number).
There is a child called Ann whose age is 3.
Say the number of children.          #> 1
For each pupil in children:
  Say the pupil.                     #> Ann
```

```refused
A child has an age (number).
Say the number of children.
```

```refused
A sheep (plural sheep) has an age (number).
```

### 4.2 Things

```text
There is a | an [<adjective>]... <kind> called <name> [whose <property> is <expression>]... .
```

- Every property listed for the kind must be given, with a value of the right type. A property marked `if any` may be left out.
- Further `whose` parts are joined by a comma, by `and`, or by both.
- The name must be new.
- An adjective written before the kind must be a stored one (section 4.3); the thing starts with it.
- This is the only way to make a thing that later sentences can mention by name. Things can also be made while the program runs (section 7.5).

```englishscript
A wizard has a hat size (number) and a motto (text).
There is a wizard called Merlin Ambrosius whose hat size is 7 and whose motto is "Never late"
Say Merlin Ambrosius's motto.         #> Never late
Say the name of merlin ambrosius.     #> Merlin Ambrosius
```

### 4.3 Adjectives

```text
A | An <kind> is <adjective> when <condition>.
```

Inside the condition, `it`, `its` and `the <kind>` all mean the thing being described. An adjective belongs to one kind; another kind may define the same word differently.

```englishscript
A dragon is young when its age is less than 100.
A dragon is rich when the dragon's hoard is at least $1,000 and the dragon is not young.
If Smaug is rich and Norbert is young:
  Say "As expected."     #> As expected.
```

An adjective can also be **stored** instead of worked out: a yes-or-no fact that the program sets.

```text
A | An <kind> can be <adjective>.
Now <thing> is [not] <adjective>.
```

- A stored adjective is used exactly like a defined one: after `is`, and in front of a kind in a group or a `For each`.
- It starts as "no", unless it is written in front of the kind when the thing is made: `There is a sworn knight called ...`.
- `Now` is the only way to change it. `Now` is refused for an adjective defined with `when`, for a thing that may be nothing, and inside `To work out` (section 9.3).
- A program can react when a thing becomes an adjective, stored or defined, with `Whenever` (section 9.5).

```englishscript
A knight can be sworn.
There is a sworn knight called Lancelot whose purse is $5 and whose courage is 9.
Say the number of sworn knights.     #> 1
Now Robin is sworn.
Now Lancelot is not sworn.
For each sworn knight:
  Say it.                            #> Robin
```

```refused
Now Smaug is ancient.
```

### 4.4 Worked-out properties

```text
The <property> of a | an <kind> is <expression>.
```

A worked-out property is read like any other property, but it is computed each time and cannot be changed directly.

```englishscript
The tax of a dragon is 10% of its hoard.
The bravery bonus of a knight is the knight's courage * $10.
Say the tax of Smaug.            #> $350
Say Gawain's bravery bonus.      #> $80
```

### 4.5 Rules

```text
A | An <kind>'s <property> is never | always <comparison>.
```

The comparison is anything that may follow `is` in a condition (section 6). A rule must be about a stored property.

- **A rule holds from its sentence on**, not before. When the sentence is carried out, every thing of that kind there is already is checked; if one breaks the rule, the program stops there, after the sentences before it have been carried out.
- From then on it is checked when a thing of that kind is made, and whenever one of that thing's stored properties changes (by `Set`, `Add` and the like, by `Remove` clearing an `if any` property, or by an event from a library). A change that would break a rule is undone and the program stops, unless a `Try` catches it (section 8.5).
- **A rule may depend only on what cannot change behind its back**, because it is checked only when the thing's own stored properties change. After `never` or `always` it may use values written out (`5`, `$0`, `10%`, `"none"`, `nothing`), variables made with `always` (section 7.1), and the thing's own stored properties (`its purse`, `the knight's debt`). It may not use a variable that can change, another thing, a property of another thing, a worked-out property, an adjective, a worked-out value, a count or a total: those are refused when the rule is compiled.
- A rule that uses another of the thing's own stored properties (`A knight's debt is never more than its purse.`) is checked when either of them changes.
- A rule may be about an `if any` property. It then holds whenever the property is nothing (`A squire's wage is never more than $9.` says nothing about a squire with no wage), except a rule about being nothing itself (`A squire's mount is never nothing.`).

```englishscript
A dragon's age is always at least 0.
A treasure's worth is never more than $1,000,000.
Let the cap always be $10,000.
A knight's purse is never more than the cap.
```

```refused
A dragon's age is always at least 0.
Subtract 5 from Norbert's age.
```

Refused, because the variable can change without the rule being checked:

```refused
Let the cap be $10,000.
A knight's purse is never more than the cap.
```

Refused, because Smaug's age can change without the treasure's rule being checked:

```refused
A treasure's owner is always ancient.
```

Stopped at the rule's own sentence, after `Say "before"` has been carried out, because Norbert is already younger:

```refused
Say "before"
A dragon's age is always at least 100.
```

### 4.6 A fixed set of choices

```text
A | An <name> is one of <choice>, <choice> ... or <choice>.
```

- This defines a type, written in brackets like any other: `(mood)`. Each choice is one or more words, and there are at least two. The choices are separated by commas, with `or` before the last.
- A choice is a name: it may not be the name of a kind, a thing, a variable or a worked-out value, nor a choice of another set. It may be the same word as an adjective, because the left side of `is` always says which is meant: a thing on the left takes an adjective, and a value of the set takes a choice.
- Choices are compared with `is` and `is not` only. A choice is said as its words, as they were written in the definition.
- A word that is not one of the choices, where one of them is expected, is refused before the program runs.
- Still proposed: lists of choices, and asking for a choice (sections 13.7 and 13.15).

```englishscript
A mood is one of sleepy, grumpy or very cross.
A beast has a mood (mood).
A beast is grumpy when its mood is very cross.
There is a beast called Grendel whose mood is sleepy.
Set Grendel's mood to very cross.
If Grendel's mood is very cross and Grendel is grumpy:
  Say "Tread softly."       #> Tread softly.
Say "{Grendel} is {Grendel's mood}."    #> Grendel is very cross.
```

```refused
A mood is one of sleepy or grumpy.
Let the feeling be sleepy.
If the feeling is happy:
  Say "Strange."
```

## 5. Expressions

### 5.1 Referring to something

| Form | Meaning |
|---|---|
| `Smaug` | A named thing. |
| `the total`, `total` | A variable made with `Let`. `the` is optional. |
| `the dragon` | The dragon in view: a role of the current verb, or the noun of an enclosing `For each`. |
| `the rival` | The name given to the thing of an enclosing `For each rival in ...` (section 8.2). |
| `it`, `they`, `them` | The one thing in view. |
| `its ...`, `their ...` | A property of the one thing in view. |

A thing is **in view** inside a definition about it, inside a verb that has it as a role, and inside a `For each` over it. Named things and variables are not in view for this purpose.

- `the <noun>` is refused unless something of that name is in view.
- A pronoun is refused unless exactly one thing is in view.
- Inside a block, a variable, a role or a loop's thing may have a kind's name only when it holds a thing of that kind, as in `Let the card be a new card ...`: `the card` then means a card either way. `Let the dragon be 5.` and `Let the dragon be Gawain.` (a knight) are refused. At the top level a kind's name is never a variable's name (section 3).

```englishscript
Let the best knight be Gawain.
Say the best knight.           #> Gawain
Say best knight's purse.       #> $300
For each dragon:
  Say "{it} is {its age}, and the dragon's hoard is {the dragon's hoard}."
#> Smaug is 771, and the dragon's hoard is $3,500.
#> Norbert is 1, and the dragon's hoard is $0.
```

```refused
Say the dragon's age.
```

```refused
For each dragon:
  For each treasure of the dragon:
    Say its worth.
```

### 5.2 Properties

A property can be reached in three ways, and they can be chained:

```text
<thing>'s <property>
the <property> of <thing>
its | their <property>
```

```englishscript
Say Goblet's worth.                    #> $3,000
Say the worth of Goblet.               #> $3,000
Say Goblet's owner's age.              #> 771
Say the age of the owner of Goblet.    #> 771
Say Goblet's name.                     #> Goblet
```

`the <property> of <owner>` is decided by the owner alone, never by what other files happen to define:

- If the owner's kind has a property (stored or worked out) of that name, it is the property, unless a variable, role or loop's thing of that name is also in view: then it could be read two ways, and it is refused with both, `<owner>'s <property>` for the property and `(the <name>) of ...` for the value.
- If the owner is not a thing, or its kind has no such property, and a value of that name is in view, it is that value, and the `of` belongs to what follows (as in `the pick at the month of the month row`, a worked-out value with roles `at` and `of`).

```refused
A knight has a rank (number).
To review a rank (number):
  Say the rank of Gawain.
```

### 5.3 Arithmetic

| Operation | Symbol | Words |
|---|---|---|
| Add | `+` | `plus` |
| Subtract | `-` | `minus` |
| Multiply | `*` | `times` |
| Divide | `/` | `divided by` |
| Negate | `-` in front | |

Order of working, tightest first: brackets and property access; the forms that apply to the single value just before them (`as a number`, `in upper case`, `in lower case`, `joined with`, `rounded ... to the nearest` and `raised to the power of`); a leading minus and `% of`; multiplying and dividing; adding and subtracting. Operations of the same strength go left to right. A minus sign may stand in front of any single value, wherever one may stand: `the double of -3`.

`or else` (section 2) stands outside all of these, and never beside them: `"12" as a number or else 0 + 1` could mean `("12" as a number or else 0) + 1` or `"12" as a number or else (0 + 1)`, so a sum, a difference, a product or a quotient on either side of `or else` must be in brackets. Such a sentence is refused with both readings. In the same way, the value at the end of a group's `whose` filter (section 5.5) may not be followed by `+ - * /` without brackets.

```englishscript
Say 2 + 3 * 4.            #> 14
Say 2 plus 3 times 4.     #> 14
Say (2 + 3) * 4.          #> 20
Say 10 divided by 4.      #> 2.5
Say 10 - 4 - 3.           #> 3
Say -(2 + 3).             #> -5
```

Types decide what is allowed. Any combination not listed here is refused.

| Operation | Allowed | Result |
|---|---|---|
| Add, subtract | number and number | number |
| | money and money | money |
| | percent and percent | percent |
| Multiply | number by number | number |
| | money by number, in either order | money |
| | percent by number, in either order | percent |
| Divide | number by number | number |
| | money by number | money |
| | money by money | number |
| | percent by number | percent |
| | percent by percent | number |
| `% of` | percent of number | number |
| | percent of money | money |
| Negate | number, money or percent | the same |

```englishscript
Say 10% + 5%.             #> 15%
Say 10% * 3.              #> 30%
Say -10%.                 #> -10%
Let the rate be 5%.
Add 1% to the rate.
Say the rate.             #> 6%
```

```refused
Say $5 + 5.
```

```refused
Say "12" as a number or else 0 + 1.
```

#### More arithmetic

| Form | Example | Gives |
|---|---|---|
| `the remainder of <value> divided by <value>` | `the remainder of 17 divided by 5` | `2` |
| `<value> rounded to the nearest <value>` | `$3.14159 rounded to the nearest $0.01` | `$3.14` |
| `<value> rounded up to the nearest <value>` | `17 rounded up to the nearest 5` | `20` |
| `<value> rounded down to the nearest <value>` | `17 rounded down to the nearest 5` | `15` |
| `<value> raised to the power of <value>` | `2 raised to the power of 10` | `1,024` |
| `the square root of <value>` | `the square root of 81` | `9` |
| `the larger of <value> and <value>` | `the larger of $5 and $8` | `$8` |
| `the smaller of <value> and <value>` | `the smaller of 3 and 7` | `3` |
| `the absolute value of <value>` | `the absolute value of -4` | `4` |

- Each `<value>` is a single value or a bracketed expression: `2 + 17 rounded to the nearest 5` is `2 + 15`. A leading minus works after them, as the order of working says: `-17 rounded up to the nearest 5` is `-(17 rounded up to the nearest 5)`, which is `-20`; write `(-17) rounded up to the nearest 5` for `-15`.
- Remainders, powers and square roots work on plain numbers. **The remainder has the sign of the divisor** (it is what is left after taking away the divisor a whole number of times, rounding down): the remainder of `-7` divided by `2` is `1`, and of `7` divided by `-2` is `-1`. So the remainder of a number divided by a positive number is never negative. A remainder of a division by zero is a problem.
- Rounding works on a number, money or a percentage, with a step of the same type that is more than nothing. Rounding "to the nearest" takes a value exactly halfway away from zero; `up` goes towards more, and `down` towards less.
- A power with a whole exponent is exact. Any other power, and a square root that does not come out exactly, is worked out to twelve decimal places from the exact fraction (a half away from zero), never through an approximation. A negative number has no square root, and is raised only to a whole power; zero raised to a negative power would divide by zero. Each of these is a problem a `Try` can recover from (section 8.5).
- `the larger of` and `the smaller of` take two numbers, two amounts of money or two percentages; `the absolute value of` takes one.
- The words `remainder`, `rounded`, `nearest`, `raised`, `power`, `square`, `root`, `larger`, `smaller` and `absolute` are recognised only in these phrases, and stay free for names. If a worked-out value of the program is called `the remainder`, `the square root`, `the larger`, `the smaller` or `the absolute value`, the phrase could be read two ways, and is refused.

```englishscript
Say the remainder of 17 divided by 5.      #> 2
Say the remainder of -7 divided by 2.      #> 1
Say $3.14159 rounded to the nearest $0.01. #> $3.14
Say 17 rounded up to the nearest 5.        #> 20
Say 2 raised to the power of 10.           #> 1,024
Say the square root of 2.                  #> 1.4142
Say the larger of $5 and $8.               #> $8
Say the absolute value of -4.              #> 4
Try:
  Say the square root of -1.
If that fails:
  Say the problem.                         #> A negative number, -1, has no square root.
```

### 5.4 Percentages

A percentage followed by `of` takes that share of a number or of money. The percentage may be a literal or a variable.

```englishscript
Say 10% of $250.           #> $25
Say 10% of $250 + $5.      #> $30
Let the discount be 20%.
Say the discount of $50.   #> $10
```

### 5.5 Groups, counting and adding up

A group is some of the things of one kind. It can be written three ways:

```text
[all] [<adjective>]... <kinds> [of <thing>] [whose <property> <comparison> [and whose ...]...]
its | their [<adjective>]... <kinds> [whose <property> <comparison> [and whose ...]...]
<thing>'s [<adjective>]... <kinds> [whose <property> <comparison> [and whose ...]...]
```

- The kind is plural.
- Each adjective must be defined for that kind.
- `of <thing>`, and the two possessive forms, keep the things that belong to the owner. This works only when the kind has **exactly one** property whose type is the owner's kind. With none, or with two, the sentence is refused.
- `whose` keeps the things that pass a comparison on one of their properties. Several filters may be joined with `and whose`, and a thing must pass them all (`For each cell whose row is 1 and whose column is 2:`).
- Inside a `whose` part of a thing being made (`There is ... whose wage is ...`), a group takes one filter only, because a following `and whose` could belong to the group or to the new thing: such a sentence is refused with both readings, and the correction puts the group in brackets.
- When a group is part of a value (`the number of ...`, `the total ... of ...`), the value at the end of its last filter may not be followed by `+ - * /` without brackets: `the number of knights whose courage is more than 5 + 1` is refused, with `(the number of knights whose courage is more than 5) + 1` and `the number of knights whose courage is more than (5 + 1)`.

Two expressions take a group:

```text
the number of <group>
the total <property> of <group>
```

`the total` needs a property that is a number or money.

**Finding without a search.** When the first filter of a group (with no adjective in front of the kind) is a stored property being equal to a value, `whose place is the spot`, the things are found through an index kept for that kind and property, not by looking at every thing. It is built the first time it is needed and kept up to date through every change: to the property, by making and removing things, and when a failed `Try` puts things back. Nothing about the result changes: the same things, in the order they were made. Only the time does: looking up one thing among thousands takes about as long as among ten.

```englishscript
Say the number of dragons.                                           #> 2
Say the number of ancient dragons.                                   #> 1
Say the number of treasures of Smaug.                                #> 2
Say the number of Smaug's treasures.                                 #> 2
Say the number of treasures whose worth is more than $1,000.         #> 1
Say the number of treasures of Smaug whose worth is at most $500.    #> 1
Say the total worth of all treasures.                                #> $3,500
Say the total age of dragons.                                        #> 772
For each dragon:
  Say "{its name}: {the number of its treasures}"
#> Smaug: 2
#> Norbert: 0
```

```refused
A duel has a challenger (dragon) and a defender (dragon).
Say the number of duels of Smaug.
```

```englishscript
A duel has a challenger (dragon) and a defender (dragon).
Say the number of duels whose challenger is Smaug.    #> 0
Say the number of knights whose courage is more than 1 and whose purse is less than $100.   #> 1
```

```refused
Say the number of knights whose courage is more than 5 + 1.
```

```refused
A horse has a speed (number).
A squire has a wage (money) and a speed (number).
There is a squire called Wat whose wage is $3 and whose speed is 1.
There is a squire called Sum whose wage is the total wage of squires whose wage is more than $2 and whose speed is 2.
```

### 5.6 Text

Joining text is done with fill-ins: `"{the first name} {the last name}"`.

| Form | Gives |
|---|---|
| `the length of <text>` | the number of characters |
| `<text> in upper case`, `<text> in lower case` | text |
| `the first <number> letters of <text>`, `the last <number> letters of <text>` | text |
| `the words of <text>` | a list of text, split at any run of spaces, tabs or line breaks, with none empty |
| `letter <number> of <text>` | text, if any: that letter, numbered from 1; nothing when there is no such letter |
| `the lines of <text>` | a list of text, split at line breaks, with no empty last line |
| `<text> as a number` | a number, if any: nothing when the text is not a number written the usual way (below) |

- Each `<text>` and `<number>` after `of` is a single value or a bracketed expression.
- `in upper case`, `in lower case` and `as a number` apply to the whole value before them, so `the length of the title in upper case` is refused: it asks to upper-case a number. Write `the length of (the title in upper case)`.
- Asking for more letters than there are gives the whole text. A negative count, or a fraction, is a problem (section 8.5).
- `the length of` means this only when what follows is text. A thing may still have a property called `length`; the words `length`, `words`, `lines`, `letters`, `first`, `last`, `upper`, `lower` and `case` stay free for names.

Text conditions are in section 6.

```englishscript
Let the title be "The ""Lonely"" Mountain"
Say the length of the title.                         #> 21
Say the title in upper case.                         #> THE "LONELY" MOUNTAIN
Say the first 3 letters of the title.                #> The
Say the last 100 letters of "Smaug"                  #> Smaug
Say the number of items in the words of the title.   #> 3
Say ("12" as a number or else 0) + 1.                #> 13
Say "twelve" as a number.                            #> nothing
```

```refused
Say "12" as a number + 1.
```

`as a number` accepts, after taking away spaces, tabs and line breaks at either end: an optional minus sign (`"-5"`); then the digits 0 to 9, either all together (`"007"` is 7) or in groups of three after commas, the first group not starting with 0 (`"1,000"`, but not `"0,123"` or `"1,00"`); then, if there is one, a point and digits (`"2.5"`). Nothing else is a number: not `"+5"`, `"5."`, `".5"`, `"1e3"`, `"$5"`, `"5%"`, nor digits of another script such as `"٥"`.

#### Regular forms, and the exceptions

The language tries to say one thing one way. Where it does not, it is on purpose, and these are the places:

- **A verb's roles take expressions; a worked-out value's roles take single values.** `Move $10 + $5 from Gawain to Robin.` is fine, but `the change from ($10 + $10) for $12.50` needs its brackets, because a worked-out value is itself part of an expression, and `the bounty for Smaug + $5` must not be read as `the bounty for (Smaug + $5)`. A verb stands at the start of its own sentence, so nothing follows its last role.
- **`called` takes a bare name when a thing is described, and a text when one is made while running.** `There is a dragon called Smaug ...` gives a name the program can say; `There is a new dragon called "{the dragon}'s chick" ...` makes a name while running, which is text and can be built with fill-ins, and so `the dragon called "Smaug"` finds a thing by a text.
- **`the` is optional before a variable, and not used before a thing's name.** `the total` and `total` are the same variable; `Smaug` is never `the Smaug`, as in English, where a name takes no article. Inside a definition or a loop, `the <kind>` means the thing in view.
- **The text tests are written without `is`**: `contains`, `starts with`, `ends with`, `comes before`, and their opposites `does not contain`, `does not start with`, `does not end with`, alongside `not ... contains`.
- **A sentence that ends in a closing quotation mark needs no period** (section 1).

### 5.7 Finding a thing by name

```text
the <kind> called <text>
```

This finds the first thing of that kind with that name, ignoring capitals. It is `if any`, because there may be none. Removed things are not found.

```englishscript
Let the found be the dragon called "SMAUG"
If the found is not nothing:
  Say the found's age.                      #> 771
Say the dragon called "Puff"                #> nothing
```

## 6. Conditions

A comparison starts with an expression and continues in one of these ways. `are` may be used in place of `is`, and `not` may follow either.

| Form | True when |
|---|---|
| `is <expression>` | The two are equal. Both sides must have the same type. |
| `is less than <expression>` | |
| `is more than <expression>`, `is greater than <expression>` | |
| `is at least <expression>` | |
| `is at most <expression>` | |
| `is divisible by <expression>` | Dividing leaves no remainder. Plain numbers only. |
| `is <adjective>` | The adjective's definition holds. The left side must be a thing. |
| `is nothing` | The value is missing (section 2). |
| `has a <property>`, `has no <property>` | The property is there, or is missing. Written without `is`. |
| `=`, `<`, `>`, `<=`, `>=` | The same comparisons as symbols. |
| `contains <text>` | The text on the left has the other inside it. Written without `is`. |
| `starts with <text>`, `ends with <text>` | |
| `comes before <text>`, `comes after <text>` | Order letter by letter, after folding capitals, by each character's code: alphabetical for the unaccented English letters, but not for accented letters, digits and marks, which fall where their codes put them. |

- Ordering comparisons work on numbers, money and percentages, and both sides must be the same type.
- `is` between two texts is exact, capitals included, and so are `contains`, `starts with` and `ends with`. All five text tests need text on both sides.
- `does not contain`, `does not start with` and `does not end with` are the opposites of the first three, as `not ... contains` is.
- A `yes or no` value is tested with `is yes` or `is no` (section 2).
- Lists cannot be compared yet.
- Comparisons are joined with `and` or with `or`. `and` and `or` stop as soon as the answer is known: after a false part of `and`, or a true part of `or`, the rest is not worked out (so it may rely on what the earlier parts checked, section 2).
- **`and` and `or` cannot be mixed** in one condition unless brackets show which belong together.
- `not` in front reverses the one comparison, or the bracketed condition, that follows it. A `not` followed by `and` or `or` could turn round just its comparison or the whole chain, so it needs brackets: `If not Robin is brave and Gawain is brave:` is refused, with `(not Robin is brave) and Gawain is brave` and `not (Robin is brave and Gawain is brave)`. A `not` in front of the last comparison of a chain needs none: `If A and B and not C:`.

```englishscript
If Smaug is ancient and Norbert is not ancient:
  Say "adjectives"       #> adjectives
If Goblet's owner is Smaug and Gawain's purse is at least $300:
  Say "comparisons"      #> comparisons
If 12 is divisible by 4 and 12 is not divisible by 5:
  Say "divisible"        #> divisible
If (Smaug is ancient and Robin is brave) or Gawain is brave:
  Say "brackets"         #> brackets
If not Robin is brave:
  Say "not"              #> not
If 2 + 2 = 4 and 3 < 4 and 4 >= 4:
  Say "symbols"          #> symbols
If "apple" comes before "Banana" and "Smaug" starts with "Sm":
  Say "text"             #> text
```

```refused
If Smaug is ancient and Robin is brave or Gawain is brave:
  Say "Which way?"
```

```refused
If not Robin is brave and Gawain is brave:
  Say "Which way?"
```

## 7. Actions

### 7.1 Variables

```text
Let [the] <name> [(<type>)] [always] be <expression>.
```

- A variable takes the type of its first value and keeps it.
- A type in brackets says what the variable may hold. It is needed when the first value is `nothing`, and optional otherwise.
- A variable made with `always` cannot be changed afterwards.
- A variable made at the top level lasts for the rest of the program; one made inside a block lasts to the end of that block.
- The value may be a new thing: `Let the chick be a new dragon ...` (section 7.5).

```englishscript
Let the tax rate always be 10%.
Let the winner (knight, if any) be nothing.
Say the tax rate of $50.       #> $5
Say the winner.                #> nothing
Set the winner to Gawain.
Say the winner's purse.        #> $300
```

```refused
Let the tax rate always be 10%.
Set the tax rate to 12%.
```

### 7.2 Changing things

```text
Set <target> to <expression>.
Add <expression> to <target>.
Subtract <expression> from <target>.
Multiply <target> by <expression>.
Divide <target> by <expression>.
```

A target is a variable made with `Let`, or a stored property of a thing. The new value must have the target's type. These cannot be changed: a worked-out property, a `name`, a role of a verb, the noun of a `For each`, and a variable made with `always`. A stored adjective is changed with `Now` (section 4.3).

`Add <text> to the file <text>.` is a different sentence (section 7.7). Text cannot be added up, so the two are never confused. When the target is a list, `Add` puts the value at its end, and `Remove <value> from <list>.` takes one out (section 2, "Lists").

```englishscript
Let the total be 10.
Add 5 to the total.
Subtract 1 from the total.
Multiply the total by 2.
Divide the total by 4.
Say the total.                    #> 7
Set the total to 0.
Add $100 to Robin's purse.
Say Robin's purse.                #> $120
Set Goblet's owner to Norbert.
Say the hoard of Norbert.         #> $3,000
```

```refused
Set Smaug's hoard to $5.
```

```refused
Let the total be 1.
Let the total be 2.
```

### 7.3 Saying

```text
Say <expression>.
```

Says one line. A thing is said as its name.

### 7.4 Examples

```text
For example[,] <condition>.
```

An example is a test. If the condition is false when the sentence is reached, the program stops. For a single comparison, the message also gives the actual value of the left side.

To check a file's examples apart from its other work:

```text
python -m englishscript my_program.english --test
```

- The program is carried out with nothing said, nothing asked (an `Ask` finds that input has ended, so the program ends quietly there, section 7.6), and no file written (`Write` and `Add ... to the file` do nothing; files are still read). A library is not left running afterwards.
- Every `For example` that is reached is reported with its line and whether it held. One that does not hold shows its "In fact" line, and the run goes on to the next, instead of stopping.
- It ends with a count, and with status 1 if any example did not hold, or if a problem stopped the program; otherwise 0.
- A program, a page or a tool can do the same with `Program.test()` (`englishscript.compile_source(...).test()`), which gives back the examples reached, in order, each with `file`, `line`, `sentence`, `held` and `fact`.

```englishscript
For example, the hoard of Smaug is $3,500.
For example Norbert is not ancient.
```

```refused
For example, the hoard of Smaug is $1.
```

### 7.5 Making and removing things

```text
There is a new [<adjective>]... <kind> [called <text>] [whose <property> is <expression>]... .
Let [the] <name> be a new [<adjective>]... <kind> [called <text>] [whose ...]... .
Remove <thing>.
```

- `There is a new` may be used anywhere except inside `To work out`, including inside verbs and loops.
- `a new <kind>` may only be the whole value of a `Let`. To use a new thing afterwards, make it that way.
- The name is a text value, so it can be built with fill-ins. If no name is given, it is the kind and a number counting every thing of that kind made so far, such as `dragon 3`. Names of new things need not be different; find one with `the <kind> called` (section 5.7).
- The `whose` parts follow the rules of section 4.2, and the kind's rules are checked.
- `Remove` takes a thing out of the world. It leaves every group and every list property. A property marked `if any` that pointed at it becomes nothing.
- `Remove <value> from <list>.` is another sentence, told apart by its `from`: it takes an item out of a list (section 2).
- **`Remove` is refused while a required property of another thing points at the thing.** This is a problem (section 8.5) that names what still depends on it.
- A removed thing can still be said and compared, but using its properties or adjectives, changing it, making something point at it, or using it as the owner of a group (`the saddles of h`) is a problem.
- A variable, a role or a list may go on holding a thing that has been removed: it does not become `nothing` as an `if any` property does. Using it is then found only while running, as the problem `a removed thing` (section 8.5).
- A `For each` that has already started does not visit a thing removed before its turn (section 8.2).
- Like using a verb, `Remove` cancels every check for nothing that relied on a property (section 2), because it may have made one nothing.

```englishscript
To hatch for a dragon:
  Let the chick be a new dragon called "{the dragon}'s chick" whose age is 0.
  Say "{the chick} hatches."

Hatch for Smaug.                              #> Smaug's chick hatches.
There is a new dragon whose age is 5.
Say the number of dragons.                    #> 4
Let the found be the dragon called "dragon 4"
If the found is not nothing:
  Remove the found.
Remove Norbert.
Say the number of dragons.                    #> 2
```

Refused while running, because two treasures belong to Smaug:

```refused
Remove Smaug.
```

### 7.6 Asking

```text
Ask <text> and let [the] <name> (<type>) be the reply.
```

- The type may be `text`, `number`, `money`, `percent` or `yes or no`. It is required.
- This makes a variable, as `Let` does, so the name must be new.
- If the reply cannot be read as that type, a short message says what is wanted and the question is asked again. Numbers are read as they are written in a program (`1,000`, `2.5`); money with or without `$`; a percentage with `%`; `yes`, `no`, `y` or `n` in any capitals. Text is kept exactly as typed.
- The question is shown followed by a space, and the reply is read from the keyboard. If there is nothing more to read, the program ends quietly, as `End the program.` does.
- `Ask` is refused inside `To work out`.

```text
Ask "How old is the dragon?" and let the age (number) be the reply.
Ask "Shall we go on?" and let ready (yes or no) be the reply.
```

### 7.7 Files

```text
the text of the file <text>          the whole file, as text
the lines of the file <text>         a list of text, split at line breaks, with no empty last line
Write <text> to the file <text>.     replaces what the file held
Add <text> to the file <text>.       puts exactly that text at the end; write {new line} to end a line
```

- The name of a file is text. A name without a folder means the folder the program is run from.
- Files are read and written as UTF-8.
- A file that cannot be read or written is a problem (section 8.5).
- `Write` and `Add` are refused inside `To work out`; reading is allowed there.

```text
Write "eggs{new line}" to the file "shopping.txt"
Add "milk{new line}" to the file "shopping.txt"
For each item in the lines of the file "shopping.txt":
  Say "- {the item}"
```

### 7.8 Asking a model, and judging

```text
Ask the model <text> [about <value>] and let [the] <name> (<type>) be the reply.
Judge <text> about <value> and let [the] <name> (percent) be the chance.
Judge <text> about <value> and let [the] <name> (<set of choices>) be the verdict.
Judge <text> about <value> and let [the] <name> (<set of choices>) be the verdict
      and [the] <name> (percent) be the likelihood.
For a | an <set of choices>, <choice> means <text>.
```

A running program may ask a model, as it may ask a person with `Ask` (section 7.6). There are two sorts of model, and a sentence for each:

- **A model that writes** answers `Ask the model`. What it writes is read as the type in brackets, by the same reader that reads a person's reply.
- **A model that judges** answers `Judge`. It writes nothing: it gives how likely something is, or how likely each of a set of choices is, and the program decides what to do with that in ordinary sentences, with `If`.

**What this changes, and what it does not.** The compiler is as deterministic as before, and has no model in it: every sentence still has exactly one meaning, and the same program is compiled the same way every time. A model is something the program asks while it runs, and what comes back is checked against the type asked for, or is a problem a `Try` can recover from. A program that asks a model is as repeatable as the model, exactly as a program that asks a person is as repeatable as the person.

Who answers is decided by whoever runs the program, never by the program: `python -m englishscript program.english --model SPEC` (the listeners that come with EnglishScript are described in `englishscript/models.py`), or `Program.run(..., model=..., judge=...)` from Python. When nothing is listening, which is the case by default and always with `--test` (section 7.4), every question to a model is the problem `no model`, whose text is `No model is listening.`; a program can catch it and ask a person instead.

**Asking a model**

- `the model` is recognised by its place, straight after `Ask`; `model` is not reserved. While a name in view starts with the word `model` (a variable, a role, a thing, a worked-out value or a kind), `Ask the model ...` is refused, because it could also ask a person about what that name holds. Rename it.
- The question is text, with fill-ins as in any text.
- `about <value>` hands over what the question is about: a text, or a thing. A thing is handed over written out, in this layout: a first line `<kind> called <name>`, then one line `<property>: <value>` for each stored property, in the order the kind lists them. Each value is said as `Say` says it; a property that is a thing is given by its name; a missing value is `nothing`; a list is written as a list is written in a program, `a list of 3, 8 and 5`, or `an empty list`. Its adjectives and worked-out properties are not handed over: to hand one over, fill it into the question.
- The type may be `text`, `number`, `money`, `percent`, `yes or no`, a set of choices (section 4.6), or a list of text, numbers, money or percentages. It may not be a kind: ask for a name as text, and find the thing with `the <kind> called` (section 5.7). With `, if any`, the model may answer `nothing`, and the variable is then nothing.
- The reply is read as a person's reply is (section 7.6): a number as section 2 writes them, money with or without `$`, a percentage with `%`, `yes`, `no`, `y` or `n`. A choice is one of the choices as they were written, whatever its capitals. A list is one item to a line; blank lines are passed over. Text is kept as it came.
- If the reply cannot be read as the type, the model is asked again, and told what was wrong, up to two more times. After that it is the problem `a bad reply`, whose text says what was wanted and quotes the reply: `The model's reply could not be read as a number, such as 7 or 2.5: "about seven"`.
- A model that refuses to answer, or whose answer is cut short, gives no reply. That is `a bad reply` too: `The model gave no reply: it refused to answer, or its answer was cut short.`
- Like `Ask`, it makes a variable, so the name must be new, and it is refused inside `To work out`: asking is not working out.

**Judging**

- `about` is required: a judgement is always about something, a text or a thing, handed over as above.
- With `the chance`, the question is a statement or a yes-or-no question, and the value is how likely it is to be so, from 0% to 100%.
- With `the verdict`, the question is one whose answer is one of the choices of the set in brackets, and the value is the likeliest choice. If two are equally likely, the one written first in the set wins. `the likelihood`, if it is asked for, is how likely that choice is: the judge's own figure for it, not a second opinion. A likelihood goes only with a verdict.
- What comes back is checked. A chance must be a number from 0 to 1. A verdict must give a chance from 0 to 1 to every choice of the set and to nothing else; the chances need not add up to exactly 1. Anything else is `a bad reply`. A judgement is not asked for again.
- `Judge`, `the chance`, `the verdict` and `the likelihood` are recognised by their places; none of them is reserved. If the program has taught a verb `judge`, a sentence that starts with `Judge` and ends with `be the chance`, `be the verdict` or `be the likelihood` could be either, and is refused. Rename the verb.
- A choice may be given a meaning for the judge, at the top level, after its set is described: `For a team, returns means "the customer wants to send something back".` Each choice may have one meaning, in plain text without braces; each is optional. The meanings are handed to whoever judges, with the choices. They change nothing else.

One question per judgement, and ordinary code around it: that is the whole design. A judgement gives a figure; the program decides, in sentences anyone can read, what is likely enough to act on, what a person should look at, and what to hand over. With nothing listening, as when this document is checked, each of these takes its `If that fails:` way:

```englishscript
A team is one of sales, support or returns.
For a team, returns means "the customer wants to send something back".
A letter has a wording (text) and a sender (text).
There is a letter called Ticket whose wording is "The jug came broken. I want my money back." and whose sender is "Ann".

To route a letter:
  Try:
    Judge "Which team should handle this?" about the letter and let the team (team) be the verdict and the certainty (percent) be the likelihood.
    If the certainty is at least 90%:
      Say "{the letter} goes to {the team}."
    Otherwise if the certainty is at least 60%:
      Ask "Send {the letter} to {the team}?" and let the agreed (yes or no) be the reply.
      If the agreed is yes:
        Say "{the letter} goes to {the team}."
      Otherwise:
        Say "{the letter} goes to a person to sort."
    Otherwise:
      Say "{the letter} goes to a person to sort."
  If that fails:
    Say "{the letter} goes to a person to sort, because: {the problem}"

To screen a letter:
  Try:
    Judge "The writer is angry." about the letter and let the anger (percent) be the chance.
    Judge "Does the writer want money back?" about the letter and let the refund (percent) be the chance.
    Let the urgency be (the anger + the refund) / 2.
    If the urgency is at least 75%:
      Say "Call {the letter's sender} today."
  If that fails:
    If the problem is no model:
      Say "No one to judge {the letter}; it waits its turn."
    Otherwise:
      Fail again.

Route Ticket.      #> Ticket goes to a person to sort, because: No model is listening.
Screen Ticket.     #> No one to judge Ticket; it waits its turn.
```

Asking a model, with a person as the fallback:

```englishscript
A letter has a wording (text) and a sender (text).
There is a letter called Ticket whose wording is "Where is my order?" and whose sender is "Ann".
Try:
  Ask the model "Write one line of thanks to the sender." about Ticket and let the thanks (text) be the reply.
  Say the thanks.
If that fails:
  Say "Thank you, {Ticket's sender}."     #> Thank you, Ann.
```

```text
Ask the model "How many items does this order have?" about the order and let the count (number) be the reply.
Ask the model "Which mood is this letter in?" about the letter and let the feeling (mood) be the reply.
Ask the model "List the dates in this text." about the letter and let the dates (list of text, if any) be the reply.
```

Refused: a reply can't be a kind.

```refused
Ask the model "Which dragon is oldest?" and let the eldest (dragon) be the reply.
```

Refused: a judgement is always about something.

```refused
Judge "Is it raining?" and let the rain (percent) be the chance.
```

Refused: a likelihood goes with a verdict.

```refused
Judge "Is Smaug angry?" about Smaug and let the anger (percent) be the chance and the sureness (percent) be the likelihood.
```

Refused: `calm` is not one of the choices.

```refused
A team is one of sales, support or returns.
For a team, calm means "nothing to do".
```

Refused: a variable called `model` is in view, so the sentence could ask a person the question it holds.

```refused
Let the model be "Which colour?"
Ask the model "Which colour?" and let the colour (text) be the reply.
```

## 8. Blocks

### 8.1 If

```text
If <condition>:
Otherwise if <condition>:
Otherwise:
```

Any number of `Otherwise if` parts may follow an `If`, and at most one plain `Otherwise`, which comes last. Only the first part whose condition holds is carried out.

```englishscript
Let the score be 7.
If the score is more than 9:
  Say "high"
Otherwise if the score is more than 5:
  Say "middling"     #> middling
Otherwise:
  Say "low"
```

### 8.2 For each

```text
For each [<adjective>]... <kind> [of <thing>] [whose <property> <comparison>]:
```

This is a group (section 5.5) written in the singular. Inside the block the current thing is `the <kind>`, and it is in view for pronouns. Things are visited in the order they were created, and the group is settled when the loop starts. A thing removed (section 7.5) before its turn comes is not visited.

A `For each` is refused when its kind is already in view, because `the <kind>` would then mean two things.

```englishscript
For each brave knight:
  Say the knight.
#> Gawain
For each treasure of Smaug whose worth is less than $1,000:
  Say "{its name} is small."
#> Cup is small.
```

The loop's thing can also be given a name of its own:

```text
For each <name> in <group, in the plural>:
For each <name> in <list>:
```

- The group is written as in section 5.5, in the plural. Inside the block the current thing is `the <name>`, and it is in view for pronouns. This lets a loop run over a kind that is already in view. As above, a thing removed before its turn comes is not visited.
- Over a list (section 2), the items are visited in order, each one as `the <name>`. An item that is a thing is in view for pronouns.
- The name must be new.

```englishscript
To greet a dragon:
  For each rival in dragons whose age is more than 0:
    If the rival is not the dragon:
      Say "{the dragon} glares at {the rival}."

Greet Norbert.                   #> Norbert glares at Smaug.
For each word in the words of "fire and smoke":
  Say the word in upper case.
#> FIRE
#> AND
#> SMOKE
```

```refused
To greet a dragon:
  For each dragon in dragons:
    Say "Hello."
```

### 8.3 Repeat and While

```text
Repeat <expression> times:
While <condition>:
```

`Repeat` needs a whole number that is not negative. `While` is stopped after 1,000,000 rounds.

```englishscript
Repeat 2 times:
  Say "Again."
#> Again.
#> Again.
Let the fuse be 3.
While the fuse is more than 0:
  Subtract 1 from the fuse.
Say the fuse.      #> 0
```

### 8.4 Stopping early

```text
Stop.                  ends the verb, or the reaction, being carried out
Stop repeating.        ends the loop around this sentence
Skip this <noun>.      goes on to the next thing in a For each
Skip this round.       goes on to the next round of a Repeat or While
End the program.
```

- `Stop.` is refused outside a verb or a reaction (section 9.5). Inside `To work out` (section 9.3), use `The answer is`.
- `Skip this <noun>.` names its loop by the loop's noun, or by the name given in `For each <name> in ...`, so it is clear in nested loops.
- `Stop repeating.` and `Skip this round.` are refused when more than one loop is around the sentence, because they could mean either. Move the inner loop into its own verb and use `Stop.` there.
- A loop written outside a verb is not "around" the sentences inside that verb, nor around the sentences of a reaction.

A block that ends in one of these sentences, in `The answer is` (section 9.3), or in `Fail because` (section 8.5), **always leaves**; so does a block that ends in an `If` with an `Otherwise` whose every branch always leaves, or in a `Try` whose two blocks both always leave. An `If` whose block always leaves works as a guard: the sentences after it can rely on its condition having been false (section 2, "Nothing").

A round of a loop can end at a `Skip`, and the loop itself at a `Stop repeating`, part way through the block. A check for nothing is only relied on in the next round, or after the loop, if it held at every such point.

```englishscript
To check a knight:
  If the knight is not brave:
    Say "{the knight} stays home."
    Stop.
  Say "{the knight} rides out."

Check Robin.                     #> Robin stays home.
Check Gawain.                    #> Gawain rides out.

For each treasure:
  If the treasure's worth is less than $1,000:
    Skip this treasure.
  Say the treasure.
#> Goblet

Let the count be 0.
Repeat 10 times:
  Add 1 to the count.
  If the count is 3:
    Stop repeating.
Say the count.                   #> 3

Say "Goodbye."                   #> Goodbye.
End the program.
Say "This is never said."
```

```refused
For each dragon:
  For each treasure of the dragon:
    Stop repeating.
```

```refused
Stop.
```

### 8.5 Recovering from a problem

```text
Try:
If that fails:
Either way:
Fail because <text>.
Fail again.
the problem
the problem is [not] a | an <kind of problem>
```

- `Try:` carries out its block. If a problem arises, the rest of the block is abandoned and the `If that fails:` block is carried out. `If that fails:` must follow directly, and is required.
- `Either way:` may follow the `If that fails:` block, at the same indent. Its block is carried out after the `Try` and its `If that fails:`, whether the `Try` failed or not, and however they end: normally, by a problem that goes on out of `If that fails:`, or by `Stop.`, `Skip`, `Stop repeating.` or `The answer is` leaving them. It is not carried out when the program is ending (`End the program.`, or a problem that always ends the program). A problem inside `Either way:` is an ordinary problem at that point. `either` is not reserved: it is read this way only at the start of a sentence followed by `way`.
- **A failed `Try` leaves the world as it was.** Every change its block made is undone: to properties, to stored adjectives, to variables that existed before the `Try`, and to which things exist, including changes made by verbs it used and by reactions it set off (section 9.5). What was said, asked or written to a file stays. Putting things back does not set off reactions.
- Inside `If that fails:`, `the problem` is text saying what went wrong. It means nothing anywhere else.
- A problem also has a **kind**, which `the problem is a broken rule` (or `is not`) tests, inside `If that fails:`. The kinds are in the table below.
- `Fail because <text>.` raises a problem of the program's own, of the kind `a failure`.
- `Fail again.`, inside `If that fails:`, passes the same problem on, with its kind and its text unchanged, to the `Try` around this one, or ends the program if there is none.
- `Stop.`, `Skip`, `Stop repeating.`, `The answer is` and `End the program.` leaving a `Try` are not failures. They leave as usual, and the changes stay.
- For checks for nothing, the two blocks count like the branches of an `If`: after the `Try`, nothing that either block may have changed is relied on.

These problems can be recovered from. The text is what `the problem` holds, with `...` where a name, a number or a rule is filled in:

| Kind | When | `the problem` |
|---|---|---|
| `a broken rule` | a change, a new thing or a removal would break a `never` or `always` rule | `That would break a rule: "..."`, `... would break a rule: "..."` (a new thing), `Removing ... would break a rule: "..."` |
| `a division by zero` | dividing by zero; testing for being divisible by zero; a remainder of a division by zero; zero raised to a negative power | `I can't divide by zero.`, `Nothing is divisible by zero.`, `I can't divide by zero, so there is no remainder.`, `Nothing raised to a negative power: that would divide by zero.` |
| `a missing file` | a file that cannot be read or written | `I couldn't read the file ...: ...`, `I couldn't write to the file ...: ...` |
| `a refused removal` | `Remove` of a thing that a property that is not `if any` points at | `I can't remove ... while ...'s ... still points at it.` |
| `a removed thing` | using a removed thing's properties or adjectives, changing it, or making something point at it | `... has been removed, so it can't be used any more.` |
| `a bad count` | `Repeat` with a fraction or a negative number; a negative or fractional number of letters | `I can't repeat something ... times.`, `I can't take ... letters of a text.` |
| `a missing item` | `Set item` of an item that isn't there | `There is no item ... of ...: it has ... items.` |
| `a bad number` | the square root of a negative number; a negative number raised to a power that isn't whole; rounding to a step that is not more than nothing | `A negative number, ..., has no square root.`, `A negative number, ..., can't be raised to a power that is not whole.`, `A value is rounded to the nearest step of more than nothing, not ....` |
| `a bad reply` | a model's reply that can't be read as the type asked for, after three tries; no reply; a judgement that is not well-formed; a problem the listener reports (section 7.8) | `The model's reply could not be read as ...: "..."`, `The model gave no reply: it refused to answer, or its answer was cut short.`, `The model's judgement could not be used: ...` |
| `no model` (written without `a`: `the problem is no model`) | `Ask the model` or `Judge` with nothing listening (section 7.8) | `No model is listening.` |
| `a library problem` | a problem a library reports (section 9.4), unless it is one of the kinds above | the library's own words |
| `a failure` | `Fail because <text>.` | the text |

These always end the program, because they are faults in the program rather than events in the world: a `For example` that does not hold, a `While` passing 1,000,000 rounds, a verb or worked-out value using itself more than 200 levels deep, and reactions setting off reactions more than 200 levels deep.

```englishscript
To move an amount (money) from a giver (knight) to a taker (knight):
  If the giver is the taker:
    Fail because "a knight cannot pay himself"
  Add the amount to the taker's purse.
  Subtract the amount from the giver's purse.

Try:
  Move $500 from Robin to Gawain.
If that fails:
  Say "No payment: {the problem}"
#> No payment: That would break a rule: "A knight's purse is never less than $0."
Say Gawain's purse.          #> $300
Try:
  Move $5 from Robin to Robin.
If that fails:
  Say "No payment: {the problem}"
#> No payment: a knight cannot pay himself
```

Gawain's purse was raised to $800 before the rule on Robin's purse was broken, and the failed `Try` put it back.

```englishscript
To pay a fee (money) for a knight:
  Try:
    Subtract the fee from the knight's purse.
  If that fails:
    If the problem is a broken rule:
      Say "{the knight} can't pay."
    Otherwise:
      Fail again.
  Either way:
    Say "The clerk closes the book."

Pay $50 for Robin.
#> Robin can't pay.
#> The clerk closes the book.
Try:
  Say $1 / (Robin's purse - $20).
If that fails:
  Say whether (the problem is a division by zero).    #> yes
```

```refused
Either way:
  Say "Too soon."
```

```refused
Try:
  Say "Nothing can go wrong."
Say "Done."
```

## 9. Verbs

### 9.1 Teaching a verb

```text
To <verb> [a | an <role>] [<preposition> a | an <role>]... :
```

A role is written in one of two ways:

```text
<kind>               the role is called by the kind's name
<name> (<type>)      the role has its own name and any type
```

- The first role, if it has no preposition, is the verb's object.
- Each further role is introduced by a preposition from the list in section 3, and each preposition may be used once.
- Two roles cannot share a name. Two knights must be told apart as, say, `a giver (knight)` and `a taker (knight)`.
- Inside the block, a role is referred to as `the <role>`. Roles that are things are in view for pronouns.
- The block can also use named things and top-level variables defined before the verb. It cannot see the variables of whoever uses the verb.
- A verb does not produce a value. It may use itself, to a depth of 200.
- **A verb may have several shapes.** The same verb may be taught again with other linking words: `To send a knight against a dragon:` and `To send a treasure to a knight:` are two shapes of `send`. Having a direct object or not counts as a difference, so `To send:` is a third. Two shapes with the same linking words are refused, whatever their kinds (`To greet a knight:` and `To greet a dragon:`): which verb a sentence uses must never depend on looking at its values. All the shapes of a verb are taught in one file.
- A verb, like a worked-out value, must be taught before it is used, so two verbs cannot use each other. The way round it is one verb with a role that says which work to do, or a worked-out value that both use.

### 9.2 Using a verb

```text
<Verb> [<expression>] [<preposition> <expression>]... .
```

The object comes first. The other roles may come in any order, because the prepositions say which is which. Every role must be given, with a value of the right type.

```englishscript
To send a knight against a dragon:
  If the knight is brave:
    Say "{the knight} rides out against {the dragon}."
  Otherwise:
    Say "{the knight} stays home."

To move an amount (money) from a giver (knight) to a taker (knight):
  Subtract the amount from the giver's purse.
  Add the amount to the taker's purse.

To count from a start (number):
  If the start is more than 0:
    Say the start.
    Count from the start - 1.

To cheer:
  Say "Hurrah!"

Send Gawain against Smaug.          #> Gawain rides out against Smaug.
Send Robin against Smaug.           #> Robin stays home.
Move $100 from Gawain to Robin.
Move $10 to Gawain from Robin.
Say Robin's purse.                  #> $110
Count from 2.
#> 2
#> 1
Cheer.                              #> Hurrah!
```

```refused
To send a knight against a dragon:
  Say "Off they go."
Send Smaug against Gawain.
```

```refused
To send a knight against a dragon:
  Say "Off they go."
Send Gawain.
```

### 9.3 Working out a value

A verb does something. To get a value, define something that is worked out.

```text
To work out the <name> (<type>) [<preposition> a | an <role>]... :
The answer is <expression>.
```

It is then used as a value:

```text
the <name> [<preposition> <value>]...
```

- The type of the answer goes in brackets after the name. It may be `if any`.
- Roles are written as for verbs (section 9.1), except that every role has a preposition, and `of` may be one of them. When it is used, the roles may come in any order.
- `The answer is ...` ends the work and gives the value. Every path through the block must reach one, or end with `Fail because` (section 8.5).
- **Working out changes nothing.** The block may make and change its own variables, loop, use other worked-out values, read files, and use `Try` and `Fail because`. It may not change a thing or an outside variable, use `Now`, make or remove a thing, say or ask anything, write to a file, or use a verb.
- It may, however, read what can change outside it: a file, or what a library remembers. So the same worked-out value, asked for twice with the same roles, may give two answers. "Changes nothing" is promised; "gives the same answer each time" is not.
- Like a verb, a worked-out value must be defined before it is used, so two cannot use each other. The way round it is one worked-out value with a role that says which answer is wanted.
- Because of that, a worked-out value may be used anywhere a value may, including in the definition of an adjective.
- Each role takes a single value. Arithmetic in a role needs brackets: `the change from ($10 + $10) for $12.50`.
- A worked-out value takes every role written after it. Brackets end it early: `(the bounty for Smaug) + $5`.
- A worked-out value cannot share its name with a property, a variable or a thing.
- It may use itself, to a depth of 200.

A worked-out property (section 4.4) remains the short form for one thing and one expression.

```englishscript
To work out the bounty (money) for a dragon:
  If the dragon is ancient:
    The answer is $1,000.
  The answer is 10% of the dragon's hoard.

To work out the change (money) from an amount (money) for a price (money):
  The answer is the amount - the price.

To work out the eldest (dragon, if any):
  Let the best (dragon, if any) be nothing.
  Let the top be 0.
  For each dragon:
    If the dragon's age is more than the top:
      Set the best to the dragon.
      Set the top to the dragon's age.
  The answer is the best.

Say the bounty for Smaug.               #> $1,000
Say the bounty for Norbert.             #> $0
Say the change from $20 for $12.50.     #> $7.50
Say the change for $1 from $5.          #> $4
Say the eldest.                         #> Smaug

A dragon is costly when the bounty for the dragon is at least $500.
Say the number of costly dragons.       #> 1
```

Refused, because a score under 50 reaches no answer:

```refused
To work out the grade (text) for a score (number):
  If the score is at least 50:
    The answer is "pass"
```

Refused, because working out cannot say anything:

```refused
To work out the census (number):
  Say "Counting."
  The answer is the number of dragons.
```

### 9.4 Using a library

A library gives a program words whose work is done by Python code: drawing on a screen, say, or talking to a device.

```text
Use the <name> library.
```

- This is allowed only at the top level. Its name is one word. A file may use a library only once; in a program of several files (section 9.6), each file that wants its words says so, and the library is loaded once, at the first.
- The library's own sentences are read at that point, as if they were written there. The kinds, things, adjectives, rules, verbs and worked-out values it describes join the program's vocabulary from then on. A name in the library that the program has already given a meaning is refused, as any reused name is (section 3).
- Its verbs and worked-out values are used like any others (sections 9.2 and 9.3). Some of them are carried out by the library's Python code, but the rules are the same: a verb may not be used inside `To work out`, and using one means checks for nothing no longer count (section 2); a worked-out value changes nothing.
- A library may report a problem, such as a device that is not there. A `Try` can recover from it (section 8.5). A failed `Try` undoes the changes the library made to things in the world, but it cannot undo what the library did outside the world, such as what it showed on a screen.
- If a library fails in a way it did not expect, the program stops with a message naming the library. That is a fault in the library, and `Try` does not recover from it.
- When the program ends, for any reason, each library it used is told, so that it can let go of what it holds.
- A library may go on working after the program's last sentence, as a page does that waits for clicks. It starts only when the sentences ran to their end, not after `End the program.` or a problem. What then happens outside, such as a click, comes in as a change to things, and is treated as one sentence: the rules are checked, and it sets off reactions (section 9.5) as a sentence would. If the change breaks a rule, or a reaction to it meets a problem, all of it is undone, as by a failed `Try`. A reaction that says `End the program.` ends the program, and nothing more comes in.
- Only the libraries that come with EnglishScript can be used, from the folder `englishscript/libraries`. Naming any other is refused, and the message lists the libraries there are.
- Two libraries come with EnglishScript today: `vulkan`, which draws shaded triangles on the graphics card (its words are described in [VULKAN.md](VULKAN.md), and `examples/gpu_triangle.english` uses it), and `page`, which shows a program as a web page of panels, fields and buttons that the person can click (its words are described in [PAGE.md](PAGE.md)).

```text
Use the paint library.
Splash "red" on Easel.
Say the pixel count of Easel.
```

```refused
Use the nonesuch library.
```

#### Writing a library

A library is a Python module in `englishscript/libraries`. It holds its sentences as ordinary EnglishScript text, and in that text, and only there, a verb or a worked-out value may be declared without a block:

```text
To splash a colour (text) on a canvas is done by the library.
To work out the pixel count (number) of a canvas is done by the library.
```

The part before `is done by the library` is exactly the first line of a verb (section 9.1) or of a worked-out value (section 9.3), without its colon. The work is then done by a Python function of the library. A library's sentences may not say `Use`. The full interface, for people writing a library, is described in `englishscript/libraries/__init__.py`.

A program cannot declare work to be done by a library:

```refused
To splash a colour (text) on a dragon is done by the library.
```

### 9.5 Reactions

```text
Whenever a | an <kind> becomes [not] <adjective>:
Whenever <thing> becomes [not] <adjective>:
```

A reaction is a block that is carried out when a thing comes to fit an adjective, or, with `not`, stops fitting it.

- This is a definition, allowed only at the top level. It applies from that sentence on: changes made before it is reached set nothing off.
- The adjective may be stored (`A knight can be sworn.`) or defined (`A knight is broke when ...`), and must belong to the kind.
- The second form watches one thing, named when the reaction is written. It must have been made, with `There is ... called`, by an earlier sentence.
- Inside the block, the thing is `the <kind>`, and it is in view for pronouns, as in a verb. A thing watched by name may also be called by its name.
- A thing **becomes** an adjective when a sentence leaves it fitting the adjective and it did not fit before that sentence. It **becomes not** the adjective when the sentence leaves it no longer fitting. The block is carried out at once, after that sentence and before the next one, wherever the sentence is: at the top level, in a verb, in a loop, in a `Try`, or in another reaction.
- A thing made by the sentence does not "become" anything, even if it fits when it is made. A thing removed by the sentence becomes nothing, and nor does a thing removed by an earlier reaction before its turn comes.
- **The order is fixed.** When one sentence makes several things become, they are taken in the order they were made. For each one, the reactions that match are carried out in the order they were written. All of them are carried out, even if an earlier reaction has changed the thing back.
- A reaction may set off further reactions, to a depth of 200. Beyond that the program stops (section 8.5).
- The block is like a verb's, without roles: `Stop.` leaves it; `Stop repeating.` and `Skip` are refused unless a loop inside the block is around them, because a loop outside a reaction is not around its sentences. It may use top-level variables and named things defined before it, and verbs.
- Nothing changes inside `To work out`, so nothing is set off there. Putting things back after a failed `Try` sets nothing off either.
- **A problem in a reaction is a problem in the sentence that set it off.** A `Try` around that sentence recovers from it, and undoes everything the sentence and its reactions changed. `never` and `always` rules hold inside reactions as everywhere.
- If an adjective that is watched can't be worked out for some thing (it divides by zero, say), that is a problem in the sentence being carried out.
- Only sentences that change a thing, a top-level variable or a file can make a thing become something, so only around those does the program look. A program without `Whenever` does no looking at all. In a program with one, checks for nothing do not survive such a sentence (section 2).

```englishscript
A knight is broke when its purse is $0.
A knight can be sworn.

Whenever a knight becomes broke:
  Say "{the knight} is out of money."

Whenever a knight becomes not broke:
  Say "{it} has money again."

Whenever Gawain becomes sworn:
  Say "Gawain kneels."
  Add $10 to the knight's purse.

Subtract $20 from Robin's purse.     #> Robin is out of money.
Now Gawain is sworn.                 #> Gawain kneels.
Say Gawain's purse.                  #> $310
Add $5 to Robin's purse.             #> Robin has money again.
Now Robin is sworn.
There is a new knight whose purse is $0 and whose courage is 1.
Remove Robin.
```

Making the new knight, who is broke from the start, and removing Robin set nothing off.

When one sentence changes several things, they are taken in the order they were made, and the reactions to each in the order written. A reaction's own changes are reacted to at once:

```englishscript
Let the poverty line be $10.
A knight is poor when its purse is less than the poverty line.
A knight can be pitied.

Whenever a knight becomes poor:
  Say "{the knight} is poor now."
  Now the knight is pitied.

Whenever a knight becomes pitied:
  Say "Alms for {the knight}."

Whenever a knight becomes poor:
  Say "The herald notes it."

Set the poverty line to $500.
#> Gawain is poor now.
#> Alms for Gawain.
#> The herald notes it.
#> Robin is poor now.
#> Alms for Robin.
#> The herald notes it.
```

A problem in a reaction is a problem in the sentence that set it off:

```englishscript
A knight is broke when its purse is $0.

Whenever a knight becomes broke:
  Say "{the knight} is broke."
  If the knight is brave:
    Fail because "{the knight} would rather fight"

Try:
  Set Robin's purse to $0.
  Set Gawain's purse to $0.
  Say "Both have paid."
If that fails:
  Say "No: {the problem}."
Say "{Robin's purse} and {Gawain's purse}"
#> Robin is broke.
#> Gawain is broke.
#> No: Gawain would rather fight.
#> $20 and $300
```

Refused, because "ancient" is said of dragons, not knights:

```refused
Whenever a knight becomes ancient:
  Say "A venerable knight."
```

Refused, because a reaction is a definition:

```refused
If Smaug is ancient:
  Whenever a dragon becomes young:
    Say "Strange."
```

Refused, because nothing is called Puff:

```refused
Whenever Puff becomes ancient:
  Say "Puff is old."
```

#### When everything has settled

```text
Whenever everything has settled:
```

A reaction to a whole **turn**, rather than to one thing. A turn is one top-level sentence of the program, or of a chapter being read (section 9.6), with everything it sets off: the verbs it uses and the reactions to it. An event a library brings in, such as a click on a page, is a turn of its own (section 9.4).

- This is a definition, allowed only at the top level, and it applies from its sentence on. There may be several; they are carried out in the order written.
- At the end of a turn in which at least one sentence changed a thing, a top-level variable or a file, each settled block is carried out once. A turn that changed nothing settles nothing.
- What a settled block changes sets off ordinary reactions as usual, but never another settling: a settled block is carried out at most once in a turn.
- No thing is in view in the block. `Stop.` leaves it.
- A problem in a settled block is a problem of the turn. For an event, the whole event is undone, as for any problem in an event. For a top-level sentence, the program stops there, and the message names the settled block and the sentence that formed the turn. A `Try` that formed the turn does not catch it, because the `Try` had already finished.
- A program with no settled block pays nothing for it.

```englishscript
Whenever everything has settled:
  Say "Robin has {Robin's purse}."

Say "Nothing changes here."          #> Nothing changes here.
Add $5 to Robin's purse.             #> Robin has $25.
Repeat 3 times:
  Add $1 to Robin's purse.
#> Robin has $28.
```

Refused, because a settled block is a definition:

```refused
If 1 is 1:
  Whenever everything has settled:
    Say "Strange."
```

#### Kept values

```text
Keep each <kind>'s <property> as <expression>.
Keep <thing>'s <property> as <expression>.
Keep each <kind> <stored adjective> when <condition>.
```

A stored property or a stored adjective that is kept in step with something else, rather than changed by hand.

- This is a definition, allowed only at the top level, and it applies from its sentence on. In the `each` forms the thing is in view as `the <kind>` and `its`. In the form with a named thing, nothing is in view.
- **At the end of every turn in which something changed**, before the settled blocks, each kept property is worked out and set if it differs, and each kept adjective is stored or cleared to match its condition. If that changed anything, they are all worked out again, up to ten rounds; if they are still changing after that, the program stops with a problem that names the ones that would not settle. The sentence that says `Keep` is a turn of its own, so the value is kept from then.
- A change made this way sets off reactions as any change does, and the kind's rules still hold for it.
- A kept property or adjective can't be changed any other way: `Set`, `Add` and the rest, and `Now`, are refused when the program is compiled, with the `Keep` sentence named. For the form with a named thing, that is a change written with the thing's name; a change made through a variable that holds the thing is put right at the end of the turn.
- A kept property may still be given when a thing is made, which it must be if it is not `if any`; it is put right at the end of the turn.
- `keep` is not reserved: a sentence is read as a kept value only when it is `Keep each ...`, or `Keep <thing>'s ... as ...`. If the program has a verb `keep` and the sentence could be either, it is refused.

```englishscript
A card has a wording (text) and a line (text).
A card can be open.
A card can be done.
There is a card called Milk whose wording is "milk" and whose line is ""
Keep each card's line as "- {its wording}"
Keep each card open when the card is not done.
Say Milk's line.                          #> - milk
Set Milk's wording to "eggs"
Say Milk's line.                          #> - eggs
Now Milk is done.
Say whether (Milk is open).               #> no
```

```refused
A card has a line (text).
There is a card called Milk whose line is ""
Keep each card's line as "- milk"
Set Milk's line to "- eggs"
```

### 9.6 Chapters and books

A program can be split over several files. A **chapter** is a file `<name>.english`, and a **book** is a folder of chapters.

```text
Use the <name> chapter.
Use the <name> chapter of the <book> book.
This chapter shares only <name>, <name> and <name>.
This chapter shares nothing.
```

**Finding the file.**

- `Use the calendar chapter.` reads `calendar.english` in the same folder as the file that says it.
- `Use the calendar chapter of the almanac book.` reads `almanac/calendar.english`, where the folder `almanac` is in the same folder as the file that says it, or, if there is none there, in the same folder as the program that was run. So a chapter in one book can use another book that sits beside the program. If there is a folder of that name in both places, the sentence is refused, naming both.
- Nothing else is searched. A chapter in a book uses the other chapters of its book with the first form.
- A name is one or more words of letters only. In the file's name the words are written in lower case and joined by underscores: `Use the roman numerals chapter.` reads `roman_numerals.english`. A path, a dot or a slash can't be written.
- Files are read as UTF-8. A chapter that is not there is refused at the `Use` sentence, and the message gives the file that was looked for and the chapters that are there.

**What using a chapter does.**

- `Use` is allowed only at the top level. A file may use a chapter only once.
- A chapter is read **once** in a program, at the first `Use` that reaches it. Its sentences are carried out then, in order, before the file that uses it goes on: it is an ordinary program, read aloud once. Its things are made, its variables set, its `Say` and `For example` sentences carried out, and its rules and reactions apply from then on, to the whole world. A later `Use` of the same chapter, by another file, reads nothing again.
- Chapters that use each other in a circle are refused, and the message names the circle: `calendar -> feasts -> calendar`.

**Private names, shared names.** A name a file defines at its top level (a kind, a thing, an adjective of a kind, a worked-out property, a verb, a worked-out value, a variable) is either shared or private.

- A name the file shares (section "What a file may say", below) has one meaning in the whole program: no other file may share the same word, whether or not any one file uses both. The second is refused, and the message names the file that shares it first.
- A name the file does **not** share is private to it. Another file may give the same word a meaning of its own, so chapters can be written apart, each with its own helpers.
- In any one file, the names in view are its own, private and shared, and the names shared by the chapters and libraries it uses. Two of those may not be the same word: the file is refused at the `Use` that would bring the second into view, or at the definition, whichever comes second, and the message names both. A private name of a chapter the file uses is never in view there, so it never clashes.
- A file with no `shares` sentence shares everything, so all its names are shared names. This is the case of most programs.

The world is still one world. Two private kinds spelt the same way in two chapters are two different kinds: their things are made, counted, gone through and found by name separately, each chapter seeing only its own, and a rule or a reaction belongs to the kind it was written for. A message that has to mention a private kind of another file names its file, as in `a cell of the life chapter`. A thing's name need only be new among the names in view in the file that makes it (and among shared names), and `the <kind> called <text>` (section 5.7) looks only among the things of the kind in view.

The calendar chapter keeps its variable `month row` to itself, so this file may have one of its own; but `roman` is shared by the numerals chapter, so it is in view and can't be given another meaning:

```englishscript
Use the calendar chapter of the almanac book.
Let the month row be 3.
Say the month row.                             #> 3
Say the month title of 3.                      #> March
```

```refused
Use the numerals chapter of the almanac book.
Let the roman be "MMXXVI"
```

**What a file may say.** In a file, a name may be used if it was defined in that file, or in a chapter that this file itself uses, and that chapter shares it. What a chapter uses is not passed on: a file that wants a chapter's words uses that chapter itself.

- A chapter with no `shares` sentence shares everything it defines.
- `This chapter shares only A, B and C.` shares just those. `This chapter shares nothing.` shares none. Either must be the first sentence of its file (comments may come before it). A program may say it too, so that one file can be both a program and a chapter.
- The names are written as they were defined, without an article, separated by commas and `and`. Each must be defined at the top level of the chapter by its end, and must be one thing: a name that is both a kind and a verb, say, is refused, because it would not be clear which is shared.
- A shared kind brings its stored properties with it. Its adjectives, its worked-out properties and its things are names of their own, and are shared only if they are listed. So two chapters may each give a shared kind a private adjective or worked-out property spelt the same way.
- A property has one type for each kind: a kind's stored properties are listed once, where it is described, and a worked-out property of a kind may not be defined twice in one file. Another kind may have a property of the same name and another type.
- A worked-out value that is shared may take or give back a thing of a kind that is not shared. The thing can then be passed around, compared and said, but its kind can't be named, so its properties can't be read, nothing can be made of it, and it can't be removed: `Remove` is refused for a thing whose kind the file cannot name.
- Rules (`never`, `always`) and reactions (`Whenever`) are not names. They belong to the kind they were written for, and hold wherever things of that kind are changed, from any file.
- Roles and the variables of a block belong to their block, as always. Another file may use the same names for its own.

A name that exists elsewhere, but may not be said here, is refused with a message that says why: the chapter does not share it, or the file does not use that chapter.

**Libraries.** `Use the ... library.` is likewise said once in each file that wants the library's words. The library is loaded once for the whole program, at the first `Use`, and it is told when the program goes on working and when it ends once (section 9.4).

The examples in this document use the book in `examples/almanac`, whose chapters are `calendar`, `numerals` and `feasts`. `calendar` shares `leapness`, `month length`, `month title` and `weekday`; `numerals` shares `roman` and `reading`; `feasts` shares the kind `feast`, the adjective `wintry`, the worked-out value `falling` and the thing `Michaelmas`, and uses `calendar` itself.

```englishscript
Use the numerals chapter of the almanac book.
Use the feasts chapter of the almanac book.

Say the roman of 1666.                         #> MDCLXVI
Say the reading of "MMXXVI"                    #> 2,026
Say the number of wintry feasts.               #> 3
Say the falling of Michaelmas for 2027.        #> Wednesday
For example, Michaelmas's month is 9.
```

The feasts chapter uses the calendar chapter, but that does not let this file say `weekday`. It must use the calendar itself:

```refused
Use the feasts chapter of the almanac book.
Say the weekday of 1 at 1 for 2000.
```

Refused, because the numerals chapter does not share its kind `numeral`:

```refused
Use the numerals chapter of the almanac book.
Say the number of numerals.
```

Refused, because there is no such chapter:

```refused
Use the moons chapter of the almanac book.
```

**Checking.** The linter (section 10) checks the file it is given. The problems inside a chapter it uses are given as one error, at the `Use` sentence, with the number of problems and the first of them. A name listed in `This chapter shares only` counts as used, so linting a chapter on its own does not warn that what it shares is never used. A problem in a chapter, before or while running, names the chapter's file and line, and the place it was used from.

## 10. How a sentence can go wrong

Problems are reported at two stages.

**Before anything runs**, the whole program is compiled. A sentence is refused if any word has no meaning yet, if a phrase could be read more than one way, or if the types don't fit.

Each problem is marked the way a teacher marks a paper:

```text
Spelling (line 14):

    Say "{the number of dragns}"
                        ^^^^^^
                        dragons

  I don't know the word "dragns". Did you mean "dragons"?
  The rule: a kind is described with "A ... has ..." before it is used. (See section 4.1.)
```

- The first line names the **category** of the mistake and where it is: Spelling, Punctuation, Capital letters, Grammar, Vocabulary (a word with no meaning yet, or with one already), Meaning (a phrase that reads more than one way, or points at nothing), Kinds of value, Layout, From another language, Style, or While running. A warning says `, a suggestion` after it.
- Then the sentence, with the words in question underlined. When the correction is certain and changes only those words, it is written under them; when it is certain but changes more, it is given as `Write: ...`.
- Then what is wrong, how to mend it, and the **rule** to remember, the same each time it is broken, with the section of this document that teaches it.
- A misspelt word (one letter off for a word of up to four letters, two for a longer one, two neighbouring letters swapped counting as one) gets "Did you mean ...?" when exactly one word of the right sort is that close: a kind where a kind belongs, a property of that kind after `'s`, an adjective of that kind, a verb at the start of a sentence, and the fixed words of a sentence form. Words of one or two letters get no such guess. Otherwise the words that would fit are listed, at most eight.

**While running**, the program stops if:

- a change would break a `never` or `always` rule;
- a `For example` does not hold;
- something is divided by zero, or tested for being divisible by zero;
- `Repeat` is given a fraction or a negative number;
- a negative or fractional number of letters is asked for;
- `Set item` names an item that isn't there, or a square root, a power, a remainder or a rounding has no answer (section 5.3);
- a file cannot be read or written;
- `Remove` is refused, or a removed thing is used;
- `Fail because` is reached;
- a `While` passes 1,000,000 rounds, a verb or a worked-out value uses itself more than 200 levels deep, or reactions set off reactions more than 200 levels deep (the message then names the reactions that repeat, if they go round in a circle);
- a library reports a problem, or fails in a way it did not expect (section 9.4).

All of these except a `For example`, the 1,000,000 rounds, the 200 levels and a library's unexpected failure are problems that a `Try` can recover from (section 8.5). When input runs out during `Ask`, the program ends quietly; that is not a problem.

A sentence of a chapter that can't be read, or a problem while running one, is reported with the chapter's file and line, such as `almanac/calendar.english, line 12`, followed by where the chapter is used from (section 9.6).

A sentence of a library that can't be read is reported at the program's `Use` sentence, as the library's fault, with the library's own sentence shown underneath. A problem while running inside a verb that a library wrote in English gives the library's line, as `line 5 of the paint library`.

### Sentences from other languages

A sentence that starts the way another programming language would, or that uses one of its symbols, is refused with a note on how EnglishScript says it. A suggested sentence repeats the writer's own words only where it is certain to be accepted: a quoted text, a number or money, or a new name where any name will do. Anywhere else it leaves a gap, `...`, to fill in. A few of them:

| Written | What the mark says | What it offers |
|---|---|---|
| `print("Hello")`, `show x`, `display x` | EnglishScript shows things with "Say", not "print". | `Write: Say "Hello".` |
| `x = 5` | A sentence starts with a verb, so a variable is made with "Let". | `Write: Let x be 5.`, and `Set x to ...` to change it later |
| `var x = 5`, `int x = 5` | A variable is made with "Let", and needs no type word. | `Write: Let x be 5.` |
| `Smaug is 771 years old.` | A sentence starts with a verb, so a fact can't be stated on its own. | `Let the age be 771.` for a variable, `Set Smaug's age to 771.` for a property, `Now Smaug is sleepy.` for a stored adjective |
| `else:` | EnglishScript writes "else" as "Otherwise". | `Otherwise:`, straight after the If block |
| `else if ...:`, `elif ...:` | EnglishScript writes "else if" as "Otherwise if". | `Otherwise if ...:` |
| `return x` | "return" isn't part of EnglishScript. | `The answer is ...` inside `To work out`, or `Stop.` to leave a verb |
| `If ... then` | EnglishScript doesn't use "then". | end the condition with a colon |
| `for x in ...:` | A loop over things is written "For each". | `For each x in ...:` |
| `for i = 1 to 10:` | EnglishScript has no counting loop of this kind. | `Repeat 10 times:`, with a variable to count |
| `end if`, `endif` | "end if" isn't needed in EnglishScript. | nothing: a block ends where the indentation ends |
| `}` | EnglishScript doesn't use "}" outside quotes. | nothing: a block ends where the indentation ends |
| `break`, `continue`, `exit` | "break" isn't part of EnglishScript. | `Stop repeating.`, `Skip this round.`, `End the program.` |
| `==`, `!=`, `&&`, `\|\|`, `!` | EnglishScript doesn't use "==". | `is`, `is not`, `and`, `or`, `not` |
| `true`, `false`, `null` | EnglishScript has no "true". | `yes`, `no`, `nothing` |
| `'single quotes'` | Text goes between double quotes, not single ones. | `"double quotes"` |
| `;` | EnglishScript doesn't use ";". | one sentence per line |

These are only advice: such sentences are still refused. A word the program has given a meaning of its own is never treated this way.

```refused
print("Hello")
```

```refused
Let the total be 1.
the total = 2.
```

### Following a run

```text
python -m englishscript my_program.english --trace
```

- Says each sentence as it is carried out, on the error stream, with its file (for a chapter or a library) and line, indented by how deep it is: the blocks it is in, and the verbs, worked-out values and reactions being carried out.
- The `Whenever` sentence of a reaction is said when the reaction is set off, with what set it off: `(because Robin became broke)`. A settled block is said with `(because everything settled after line 12)`.
- What happens in an event that a library brings in (section 9.4), such as a click, is traced in the same way.
- `Program.run(out, ask, trace=fn)` gives a library, a page or a tool the same thing as data: `fn(depth, file, line, sentence, cause)` before each sentence, where `file` is `None` for the program's own file and `cause` is `None` except as above. Without a trace, a run does nothing extra.

### The linter

The compiler stops at the first sentence it can't read. The linter reads on, and reports every problem in the program at once:

```text
python -m englishscript my_program.english --lint
python -m englishscript my_program.english --lint --json
```

- It only compiles; it never runs the program or asks anything.
- After a sentence it can't read, it goes on with the next sentence, in the same block where it can. A problem with the layout, such as a missing period or a line that doesn't line up, does not stop it either.
- The block of a sentence it can't read is not compiled, so nothing there is reported except problems with the layout and the advice above for sentences from other languages.
- When a definition is refused, the mistakes that follow only because its name is now unknown are left out, so one mistake in a kind's description gives one error, not ten. At most one error is given for each line.
- It also gives **warnings**, for sentences that are allowed but are probably a mistake:
  - a variable (made with `Let` or `Ask`), a verb, a worked-out value, an adjective, or a role of a verb or worked-out value, that is never used;
  - a sentence that can never be reached, because the one before it in the same block always leaves (section 8.4);
  - a sentence that starts with a small letter;
  - `a` before a vowel sound or `an` before any other (`a egg`, `an weight`). Only words whose sound the spelling makes plain are judged, with a list of the usual exceptions (`an hour`, `a unit`, `a one`); for other words, such as most that start with `u`, nothing is said;
  - `are` after one thing in a comparison (`If Gawain's purse are $300:`). When the last word of the thing ends in `s`, nothing is said.
- A warning is never given for a sentence that is refused, nor for anything that comes from a library. A warning never stops a program compiling or running.
- With `--json`, the problems are printed as a list of objects with the fields `line`, `col`, `width`, `kind` (`"error"` or `"warning"`), `message`, `hint`, `sentence`, `file` (the file of a chapter, or `null` for the file being linted), `category` (`"spelling"`, `"punctuation"`, `"capitals"`, `"grammar"`, `"vocabulary"`, `"meaning"`, `"kinds"`, `"layout"`, `"borrowed"`, `"style"` or `"running"`), `rule` (the rule to remember), `see` (the section of this document, such as `"4.1"`) and `fix`. `fix` is `null`, or, when the correction is certain, `{"line": <number>, "text": <the whole line as it should be>}`; the line may be another one than the problem's, as when the sentence under an empty block should be indented. A fix is only ever offered, never applied.
- It ends with a tally, such as `2 things to mend: 1 of vocabulary, 1 of kinds of value. 1 suggestion.`, or `Nothing to mend: every sentence reads one way.`, and with status 1 if there is an error, and 0 otherwise, warnings included.

### For tools

An editor, a language server or a page can use the compiler from Python:

| Call | Gives |
|---|---|
| `englishscript.lint(source, folder=None, name=None)` | the list of problems, as above |
| `lint(..., notes=True)` | `(problems, notes)`: the notes are `(line, text)`, how each sentence was read (as `--explain` shows it), for every line of the file that has no error, so one mistake does not hide the explanations of the good lines |
| `englishscript.names(source, folder=None, name=None)` | the table of names: `{"names": [...], "chapters": [...]}`. Each name has `name`, `what` (`kind`, `plural of a kind`, `property`, `worked-out property`, `thing`, `adjective`, `verb`, `worked-out value`, `variable`, `role`, `reaction`, `set of choices` or `choice`), `of` (the kind it belongs to, or the set of a choice), `file` (`None` for the file itself), `line`, `col` and `width` of where it is defined. Each chapter has `file`, `name` and `shares` (a list, or `None` for everything). A program with errors gives what its readable sentences define. |
| `read=fn` (to `lint`, `names` and `compile_source`) | `fn(path)` gives the text of a chapter that is open and unsaved, or `None` to read the file from the disk |
| `englishscript.KEYWORDS` | the reserved words of section 3 |
| `englishscript.CATEGORIES`, `CATEGORY_HEADINGS`, `RULES` | the categories of mistake, their headings (`"Spelling"`), and the rules with their sections |
| `englishscript.__version__` | the version of the compiler |

A `fix` is always the line as it was written, curly quotes and comment included, with only what the correction is about changed.

## 11. Grammar summary

Words in capitals are names from the program's own vocabulary. Quoted words are written as shown, in any capitalisation.

```text
sentence    = definition | action | block-opener

definition  = kind | thing | adjective | stored-adj | property | rule | verb | work-out
            | reaction | settled | library | chapter | shares | choices | keep   (top level only)
keep        = "Keep each" KIND "'s" PROPERTY "as" whole "." | "Keep" THING "'s" PROPERTY "as" whole "."
            | "Keep each" KIND ADJECTIVE "when" condition "."
choices     = article NAME "is one of" CHOICE { "," CHOICE } [ "," ] "or" CHOICE "."
kind        = article KIND [ "(" "plural" WORD ")" ] "has" field { sep field } "."
field       = article NAME "(" type ")"
thing       = "There is" article { ADJECTIVE } KIND "called" NAME [ whose { sep whose } ] "."
whose       = "whose" PROPERTY "is" whole
adjective   = article KIND "is" ADJECTIVE "when" condition "."
stored-adj  = article KIND "can be" ADJECTIVE "."
property    = "The" NAME "of" article KIND "is" expression "."
rule        = article KIND "'s" PROPERTY "is" ( "never" | "always" ) tail "."
verb        = "To" VERB [ role ] { PREPOSITION role } ":"
work-out    = "To work out the" NAME "(" type ")" { ( PREPOSITION | "of" ) role } ":"
reaction    = "Whenever" ( article KIND | THING ) "becomes" [ "not" ] ADJECTIVE ":"
settled     = "Whenever everything has settled" ":"
library     = "Use the" NAME "library" "."
chapter     = "Use the" WORDS "chapter" [ "of the" WORDS "book" ] "."    (WORDS: plain words, letters only)
shares      = "This chapter shares" ( "nothing" | "only" NAME { sep NAME } ) "."
                                                          (the first sentence of its file)
outside     = ( verb | work-out ) without its ":", then "is done by the library" "."
                                                          (only in a library's SOURCE, section 9.4)
role        = article ( KIND | NAME "(" type ")" )
article     = "a" | "an"
sep         = "," | "and" | "," "and"
type        = base-type [ "," "if any" ]
base-type   = "number" | "money" | "text" | "percent" | "yes or no" | KIND | CHOICE-SET
            | "list of" PLURAL-TYPE
PLURAL-TYPE = "numbers" | "percentages" | "money" | "text" | KINDS

action      = let | change | say | use | example | answer | leave
            | now | create | remove | ask | write | fail
let         = "Let" [ "the" ] NAME [ "(" type ")" ] [ "always" ] "be" ( whole | new-thing ) "."
whole       = expression | list-written | group                     (a group becomes a list)
list-written = "a list of" expression { "," expression } [ [ "," ] "and" expression ]
            | "an empty list of" PLURAL-TYPE
change      = "Set" target "to" whole "."
            | "Set item" value "of" target "to" expression "."
            | "Add" expression "to" target "."                      (a list target: put at the end)
            | "Remove" expression "from" target "."                 (target: a list)
            | "Subtract" expression "from" target "."
            | "Multiply" target "by" expression "."
            | "Divide" target "by" expression "."
say         = "Say" expression "."
use         = VERB [ expression ] { PREPOSITION expression } "."
example     = "For example" [ "," ] condition "."
answer      = "The answer is" whole "."                             (inside To work out)
leave       = "Stop." | "Stop repeating." | "Skip this" NOUN "." | "Skip this round."
            | "End the program."
target      = a variable made with Let | a stored property of a thing
now         = "Now" expression "is" [ "not" ] ADJECTIVE "."
create      = "There is" new-thing "."
new-thing   = article "new" { ADJECTIVE } KIND [ "called" expression ] [ whose { sep whose } ]
remove      = "Remove" expression "."
ask         = "Ask" expression "and let" [ "the" ] NAME "(" type ")" "be the reply" "."
write       = ( "Write" | "Add" ) expression "to the file" value "."
fail        = "Fail because" expression "." | "Fail again."           (Fail again: inside If that fails)

block-opener = "If" condition ":"
            | "Otherwise if" condition ":"
            | "Otherwise" ":"
            | "For each" { ADJECTIVE } KIND [ "of" value ] [ filter ] ":"
            | "For each" NAME "in" ( group | expression ) ":"
            | "Repeat" expression "times" ":"
            | "While" condition ":"
            | "Try" ":"                                                (followed by "If that fails:")
            | "If that fails" ":"                                      (perhaps followed by "Either way:")
            | "Either way" ":"

condition   = test { "and" test } | test { "or" test }
test        = "not" test | "(" condition ")" | expression comparison
            | "the problem is" [ "not" ] article PROBLEM-KIND             (inside If that fails)
comparison  = ( "is" | "are" ) [ "not" ] tail
            | "has" article PROPERTY | "has no" PROPERTY
            | ( "=" | "<" | ">" | "<=" | ">=" ) expression
            | ( "contains" | "starts with" | "ends with" | "comes before" | "comes after" ) expression
            | ( "does not contain" | "does not start with" | "does not end with" ) expression
tail        = "less than" expression | "more than" expression
            | "greater than" expression | "at least" expression
            | "at most" expression | "divisible by" expression
            | "nothing" | ADJECTIVE | "in" value | expression

expression  = sum { "or else" sum }
sum         = term { ( "+" | "plus" | "-" | "minus" ) term }
term        = factor { ( "*" | "times" | "/" | "divided by" ) factor }
factor      = "-" factor | value { postfix } [ "of" factor ]   ("of" needs a percentage on its left)
postfix     = "in upper case" | "in lower case" | "as a number" | "joined with" value
            | "rounded" [ "up" | "down" ] "to the nearest" value | "raised to the power of" value
value       = NUMBER | MONEY | PERCENT | TEXT | "(" expression ")" | "nothing" | "-" value | CHOICE
            | "the remainder of" value "divided by" value | "the square root of" value
            | "the" ( "larger" | "smaller" ) "of" value "and" value | "the absolute value of" value
            | "letter" value "of" value
            | "yes" | "no" | "whether" condition
            | "the" WORKED-OUT { ( PREPOSITION | "of" ) value }
            | THING
            | [ "the" ] VARIABLE
            | [ "the" ] NOUN-IN-VIEW
            | "it" | "they" | "them"
            | ( "its" | "their" ) PROPERTY
            | value "'s" PROPERTY
            | "the" PROPERTY "of" value
            | "the number of" group
            | "the total" PROPERTY "of" group
            | "the number of items in" value
            | "item" value "of" value
            | "the" ( "first" | "last" | "total" ) "of" value        (value: a list)
            | "the" ( "length" | "words" | "lines" ) "of" value
            | "the" ( "first" | "last" ) factor "letters of" value
            | "the" ( "text" | "lines" ) "of the file" value
            | "the" KIND "called" value
            | "the problem"                                          (inside If that fails)
group       = [ "all" ] { ADJECTIVE } KINDS [ "of" value ] [ filter ]
            | ( "its" | "their" ) { ADJECTIVE } KINDS [ filter ]
            | value "'s" { ADJECTIVE } KINDS [ filter ]
filter      = "whose" PROPERTY comparison
```

## 12. Proposed: time, and doing things at once

> **Status: designed, partly built.** `Whenever` (12.6) has been built, and is described in section 9.5. The compiler does not accept the other sentences in this section yet, and its examples are not run by the tests.

Other languages call these ideas "async" and "threading". EnglishScript does not use either word. It adds the two things English already says:

- **Waiting.** Something takes time, and other work can go on during it.
- **Doing things at once.** Several pieces of work proceed together.

Sentences still happen one after another unless the program says otherwise. There is no "await", and verbs are not divided into those that take time and those that don't: any verb may wait.

### 12.1 Lengths of time

```text
<number> second | seconds | minute | minutes | hour | hours
```

This adds a type, `time`, which can be used in brackets like any other type.

- The number is written out: `3 seconds`, `0.5 seconds`, `1 minute`. To get a time from a value, multiply: `the count * 1 second`.
- The unit words are recognised only straight after a number written out, so `second`, `minute` and the rest stay free for names (`the second guess`).
- A time is said in seconds: `1 second`, `90 seconds`.

| Operation | Allowed | Result |
|---|---|---|
| Add, subtract | time and time | time |
| Multiply | time by number, in either order | time |
| Divide | time by number | time |
| | time by time | number |
| Compare | time with time | yes or no |

### 12.2 Waiting

```text
Wait <time>.
Wait until <condition>.
```

`Wait <time>` pauses the work it is part of for that long. `Wait until` pauses until the condition holds; if it already holds, there is no pause. Other work carries on during either.

```text
Say "The kettle is on."
Wait 3 minutes.
Say "Tea."
```

### 12.3 At the same time

```text
At the same time:
```

Each sentence written directly inside the block is a **strand**: a piece of work that proceeds on its own. A sentence that opens a block of its own, such as an `If`, is one strand together with that block. The strands begin in the order written. The sentence after the block is not reached until every strand has finished.

```text
To send a knight against a dragon:
  Say "{the knight} sets out."
  Wait 2 seconds.
  Add 10% of the dragon's hoard to the knight's purse.
  Say "{the knight} returns."

At the same time:
  Send Gawain against Smaug.
  Send Robin against Norbert.
Say "Both are home."
```

This says:

```text
Gawain sets out.
Robin sets out.
                      (two seconds pass)
Gawain returns.
Robin returns.
Both are home.
```

Nothing is handed back from a strand. A strand's results are the changes it made to things, which are simply there afterwards.

`Let` is refused directly inside `At the same time`, because the variable would belong to a strand that ends with that sentence.

### 12.4 For each, at the same time

```text
For each [<adjective>]... <kind> [of <thing>] [whose <property> <comparison>] at the same time:
```

This is `For each` (section 8.2) with one strand per thing. The sentence after the block is reached when all of them have finished.

```text
For each knight at the same time:
  Wait the knight's courage * 1 second.
  Say "{the knight} is ready."
```

### 12.5 Every

```text
Every <time> until <condition>:
```

This repeats: wait the time; finish if the condition holds; otherwise carry out the block. The `until` part is required, so a timer always has an end. To run a timer alongside other work, put it inside `At the same time`.

```text
Let the rounds be 0.
Every 10 seconds until the rounds is 3:
  Add 1 to the rounds.
  Say "All quiet."
```

### 12.6 Whenever

**Built.** See section 9.5. It also takes a thing by name, and `becomes not`.

What remains belongs to the rest of this section: with strands, a reaction is carried out at once, before any other strand continues, and a `Wait` inside a reaction is not yet designed.

### 12.7 The rules that keep it strict

**1. Work changes hands only at a wait.** Between one `Wait` and the next, a strand's sentences are carried out without interruption. No strand ever sees a change half made, and a `never` or `always` rule cannot be caught in between.

**2. "At the same time" is a promise that order doesn't matter, and the compiler checks it.** For each strand, the compiler works out what it reads and what it changes, following the verbs it uses. Two strands conflict when one changes something the other reads or changes. A strand's changes include everything they set off: the reactions to them (section 9.5), with what those change in turn, and the kept values (section 9.5) that are worked out again because of them. A conflict is refused before the program runs.

```text
At the same time:
  Add $5 to Gawain's purse.
  Multiply Gawain's purse by 2.
```

From $300 this would give $610 or $605, depending on which went first.

Two things are told apart only when the compiler can be sure they differ: two named things, or the things of two different strands of one `For each ... at the same time`. Anything else of the same kind is treated as possibly the same.

One overlap is allowed. Strands may both `Add` to or `Subtract` from the same property or variable, provided none of them reads it and the property has no `never` or `always` rule, because the result is then the same in any order.

```text
At the same time:
  Add 1 to Smaug's age.
  Add 10 to Smaug's age.
```

Saying is not a conflict. Lines are said in the order they happen, which rule 5 fixes.

**3. A wait that can never end is an error.** If every strand is at a `Wait until`, and no `Wait <time>` or `Every` is pending, nothing can change. The program stops and lists what each strand was waiting for.

**4. Each strand has its own view.** `the <noun>` and pronouns work as they do elsewhere. A variable made inside a strand belongs to it.

**5. The order of events is fixed.** Strands begin in the order written. When several are ready to continue at the same moment, the one that has waited longest goes first, and if they have waited equally, the one written first. A program therefore says the same lines in the same order every time it runs.

### 12.8 New words and grammar

No word would become reserved (section 3: the list is frozen). `Wait`, `Wait until`, `Every ... until` and `At the same time` are recognised at the start of a sentence, `at the same time` at the end of a `For each` heading, `time` only in brackets as a type, and the unit words only straight after a number written out.

```text
type         = ... | "time"
value        = ... | NUMBER unit
unit         = "second" | "seconds" | "minute" | "minutes" | "hour" | "hours"

action       = ... | wait
wait         = "Wait" expression "." | "Wait until" condition "."

block-opener = ...
             | "At the same time" ":"
             | "For each" { ADJECTIVE } KIND [ "of" value ] [ filter ] "at the same time" ":"
             | "Every" expression "until" condition ":"
```

### 12.9 How it would run

- All strands run on one thread, taking turns at each `Wait` (in Python, `asyncio`).
- Tests and the tour would use a simulated clock, so `Wait 2 seconds` takes no real time and the order of events stays the same.
- Operating-system threads are not part of the design. Rules 1 and 2 are what would let strands run truly in parallel later, without changing the meaning of any program.

### 12.10 Left for later

- **Detached work**: starting something and carrying on ("Meanwhile, ..."). It is natural English, but it raises the question of what happens to work still running at the end.
- **Time limits**: "For at most 10 seconds: ...".
- **Racing**: "Whichever finishes first: ...".
- **Stopping** another strand.
- **Calendar time**: times of day and "every Monday". Dates and the present moment are in section 13.15.
- **Reactions to a plain condition**, not only to a thing becoming an adjective.

## 13. Proposed: the rest of the language

> **Status: designed, partly built.** Subsections marked **Built** have moved into sections 2 to 9, and those marked **Partly built** say what remains. The compiler does not accept the rest yet. The examples left here are not run by the tests; a `#>` comment shows what a line would say. Each example assumes the world at the top of this document, changed as its own subsection describes.

This section gives a syntax to every gap that used to be listed here. Many of its subsections have since been built and moved into the sections above; their headings remain so that the numbering stays the same. Three habits run through it:

- **Brackets carry the detail.** As with `(number)`, anything extra about a name goes in brackets after it: `(dragon, if any)`, `(list of numbers)`, `(plural people)`, `(written £)`.
- **What may be missing must be checked.** A value that might be nothing cannot be used until the program has shown that it is there.
- **Working something out never changes anything.** A sentence that gives a value cannot also change the world, so it is safe inside conditions, definitions and rules.

| Gap | Where it is settled |
|---|---|
| "Nothing" and optional properties | Built: section 2, "Nothing" |
| Yes-or-no values | Built: sections 2 and 4.3 |
| A fixed set of choices | Built: section 4.6 |
| Constants | Built: section 7.1 |
| Verbs that give back a value | Built: section 9.3 |
| Leaving early | Built: section 8.4 |
| Lists | Partly built: section 2, "Lists"; the rest in 13.7 |
| Naming a loop's thing | Built: section 8.2 |
| Picking from a group, and ordering | 13.9 |
| Asking about a group; averages, largest, smallest | 13.10 |
| Creating and removing things while running | Built: sections 5.7 and 7.5 |
| Remainders and mathematical functions | Built: section 5.3 |
| Text operations, and quotes and braces inside text | Built: sections 2 and 5.6 |
| More units | 13.14 |
| Input: a line, a file, the clock | Partly built: sections 7.6 and 7.7; the clock in 13.15 |
| Recovering from a problem | Built: section 8.5 |
| Irregular plurals, multi-word verbs, kinds that extend kinds | 13.17 |
| Time and concurrency | 12, with 13.18 |

### 13.1 Nothing, and properties that may be absent

**Built.** See "Nothing" in section 2.

One thing was added while building it: a check also counts after an `If` that showed the value missing and whose block always leaves, so that a guard such as `If the knight has no mount: ... Stop.` works.

Averages, largest and smallest (section 13.10) will leave out things whose property is nothing, as `the total` already does.

### 13.2 Yes-or-no facts and values

**Built.** See "Yes or no" in section 2, and stored adjectives in section 4.3.

A stored adjective works in `Whenever` (section 9.5). One part waits for another subsection: a list of yes-or-no values needs a plural type for it (section 13.7). `Now` is also refused for a thing that may be nothing, and inside `To work out`.

### 13.3 A fixed set of choices

**Built.** See section 4.6. Lists of choices (section 13.7) and asking for a choice (section 13.15) remain proposed.

### 13.4 Variables that cannot change

**Built.** See section 7.1.

### 13.5 Working out a value

**Built.** See section 9.3.

### 13.6 Stopping early

**Built.** See section 8.4. `Skip this round.` will also apply to `Every` (section 12.5) once that exists.

### 13.7 Lists

**Partly built.** See "Lists" in section 2: writing a list out, an empty list, a group given where a list is expected, lists as properties and roles, `item <number> of`, `the first of`, `the last of`, `the total of`, `joined with`, `is in`, and `Add`, `Remove ... from` and `Set item ... of`. What remains proposed:

| Form | Gives |
|---|---|
| `the average of <list>`, `the largest of <list>`, `the smallest of <list>` | a value, if any |
| `<list> in order`, `<list> in reverse order` | a list, smallest or alphabetically first |

- Saying a whole list, and comparing two lists.
- Lists of choices (section 13.3): the plural type may then be the plural of a set of choices.
- A list of things used wherever a group may be used (section 5.5), such as `the number of <list>` or `For each knight in the company whose purse is $0:`.

```text
Let the scores be a list of 3, 8 and 5.
Say the largest of the scores or else 0.       #> 8
Say the scores in order joined with ", "       #> 3, 5, 8
```

### 13.8 Naming a loop's thing

**Built.** See section 8.2, which also covers `For each <name> in <list>:`.

### 13.9 Picking from a group, and ordering

```text
the first | last <group, in the singular>
the <group, in the singular> with the largest | smallest <property>
the first | last <number> <group>
<group> in order of <property>
<group> in reverse order of <property>
```

- A pick of one thing is `if any`, because the group may be empty (section 13.1).
- `first` and `last` go by the order things were created, unless the group is put `in order of` a property.
- `first`, `last`, `largest` and `smallest` are recognised only in these phrases (after `the`, before a group or `of`), as `the first of <list>` already is (section 2), so they stay free for names.
- `in order of` puts the smallest first, or the alphabetically first for text. Things that tie stay in the order they were created.
- **When two things tie for largest or smallest, the one created first is picked.**
- `the first <number> <group>` gives a list, which may be shorter than asked.
- An ordered group may be used in `For each`.

A superlative can be given a name of its own:

```text
The <word> <kind> is the one with the largest | smallest <property>.
```

After that, `the <word> <group, in the singular>` is a pick.

```text
The richest dragon is the one with the largest hoard.

Say the richest dragon or else Norbert.          #> Smaug
Say the first treasure of Smaug or else Cup.     #> Goblet
Say the dragon with the smallest age.            #> Norbert

For each treasure in reverse order of worth:
  Say the treasure.
#> Goblet
#> Cup

Let the champion be the richest dragon.
If the champion is not nothing:
  Say "{the champion} has {the champion's hoard}."     #> Smaug has $3,500.
```

### 13.10 Asking about a group

Three conditions:

```text
there is a | an <group, in the singular>
there is no <group, in the singular>
every <group, in the singular> is [not] <adjective>
```

Three more values, alongside `the total` (section 5.5):

```text
the average <property> of <group>
the largest <property> of <group>
the smallest <property> of <group>
```

- `every` holds when the group is empty. This is stated because speakers of English disagree about it.
- To ask about a property of every thing, turn the question round: `there is no knight whose courage is less than 5`.
- The three values are `if any`, because the group may be empty. `the total` of an empty group is zero.

```text
If there is an ancient dragon and there is no knight whose purse is $0:
  Say "All is well."                                 #> All is well.
If every knight is brave:
  Say "A fine company."
Say the average age of dragons or else 0.            #> 386
Say the largest worth of treasures of Smaug.         #> $3,000
```

### 13.11 Creating, finding and removing things

**Built.** See sections 5.7 and 7.5.

As built, using a removed thing's properties or adjectives is a problem, and so is changing it, making something point at it, or using it as the owner of a group; a variable or role may still hold it, and it may still be said and compared. A `For each` that has started skips things removed before their turn. `There is a new` and `Remove` are refused inside `To work out`. Leaving every list will matter once lists can hold things (section 13.7).

### 13.12 Remainders and other arithmetic

**Built.** See "More arithmetic" in section 5.3. One change from the design: a power is written `<value> raised to the power of <value>`, because `2 to the power of 10` could not be told from the `to` of `Add ... to ...`. Rounding a measure (section 13.14) waits for measures.

### 13.13 Text

**Built.** See "Text" in section 2, section 5.6, and the text conditions in section 6.

Two details were settled while building it: `in upper case`, `in lower case` and `as a number` apply to the whole value before them, and a fractional number of letters is a problem, like a negative one.

### 13.14 Units

```text
A | An <unit> [(plural <word>)] [(written <symbol>)] is a unit of <measure>.
A | An <unit> [(plural <word>)] [(written <symbol>)] is <number> <units>.
<number> <unit>                a value, such as 5 metres
<symbol><number>               a value, such as £5
<value> in <units>             a plain number: how many of that unit
```

- The first form names a **measure**, which becomes a type, and its first unit. The second form defines a further unit of the same measure.
- Values of one measure follow the same arithmetic as money (section 5.3): add and subtract with each other, multiply and divide by a plain number, and divide by each other to give a plain number.
- **Different measures never mix**, and there is no conversion between them. Sterling cannot be added to money.
- A value is said in the first unit of its measure. `in <units>` gives a plain number in any other.
- `money`, written `$`, is built in. So is `time`: section 12.1 is the same as writing `A second is a unit of time. A minute is 60 seconds. An hour is 60 minutes.`
- Measures cannot be combined into new ones, such as a speed from a length and a time.

```text
A metre is a unit of length.
A kilometre is 1,000 metres.
A foot (plural feet) is 0.3048 metres.
A pound (written £) is a unit of sterling.

A dragon has an age (number) and a wingspan (length).
A relic has a price (sterling).

Say 2 kilometres + 500 metres.                     #> 2,500 metres
Say (2 kilometres + 500 metres) in kilometres.     #> 2.5
Say 10 feet rounded to the nearest 1 metre.        #> 3 metres
Say £5 * 3.                                        #> £15
```

Refused, because the measures differ:

```text
Say £5 + $5.
```

### 13.15 Input, files and the clock

**Partly built.** Asking (section 7.6) and files (section 7.7) are built. Still proposed: asking for a set of choices (section 13.3) or a measure (section 13.14), and the clock below.

```text
Ask "What mood is it in?" and let the feeling (mood) be the reply.
```

**The clock**

```text
now                              the present moment
<day> <month name> <year>        a date, such as 19 November 2026
```

These give a new type, `moment`.

| Form | Gives |
|---|---|
| moment `-` moment | a time (section 12.1) |
| moment `+` time, moment `-` time | a moment |
| moment `comes before` moment, moment `comes after` moment | a condition |
| `the year of`, `the month of`, `the day of`, `the hour of`, `the minute of` a moment | a number |
| `the weekday of` a moment | text, such as `Thursday` |

A moment is said as `19 November 2026, 14:05`.

```text
Let the deadline be 25 December 2026.
If now comes before the deadline:
  Say "{(the deadline - now) in hours} hours to go."
```

### 13.16 Recovering from a problem

**Built.** See section 8.5. The square root of a negative number will join the problems that can be recovered from when section 13.12 is built.

### 13.17 More about kinds and verbs

**Irregular plurals** go in brackets after the kind:

```text
A | An <kind> (plural <word>) has ...
```

**Built.** See section 4.1.

**A kind can be a kind of another:**

```text
A | An <kind> [(plural <word>)] is a kind of <kind>.
<thing> is [not] a | an <kind>          condition
```

- The new kind has every property, adjective, worked-out property and rule of the kind it extends. It may add its own with further sentences, but may not redefine any.
- It can be used wherever the wider kind is expected: as a role, in a property, and in the wider kind's groups.
- There is a built-in kind, `thing`, that every kind extends. `A ghost is a kind of thing.` describes a kind with no properties. `thing` and `kind` would be recognised only in `is a kind of`, in brackets as a type and in `is a <kind>`, so they stay free for names.
- Inside an `If` whose condition is `<thing> is a <kind>`, the thing counts as that kind.

```text
A person (plural people) has an age (number).
A knight is a kind of person.
A knight has a purse (money) and a courage (number).
A squire is a kind of person.

A person is grown when its age is at least 18.

There is a knight called Gawain whose age is 30, whose purse is $300, and whose courage is 8.
There is a squire called Wat whose age is 14.

Say the number of people.            #> 2
Say the number of grown people.      #> 1
For each person:
  If the person is a knight:
    Say "{the person} carries {the person's purse}."     #> Gawain carries $300.
```

**A verb may be more than one word.** Its name is every word after `To` up to the first `a`, `an`, preposition or colon. A verb is used by writing all of its words.

```text
To pick up a treasure for a dragon:
  Set the treasure's owner to the dragon.

Pick up Cup for Norbert.
```

Because a preposition ends the name, `To carry on:` is read as the verb `carry` with a role missing after `on`, and is refused.

### 13.18 How this fits with time and doing things at once

Section 12 stands as written. These points join the two:

- A `To work out` block cannot `Wait`, because it changes nothing and takes no time.
- `Stop repeating.` and `Skip this round.` apply to `Every` as they do to `Repeat` and `While`.
- For the conflict rule (12.7), creating or removing a thing counts as changing every group of its kind, and `Add` to or `Remove` from a list counts as changing the list.
- A `Try` inside a strand undoes only that strand's changes. The conflict rule already guarantees that no other strand touched them.
- `time` is a measure (section 13.14).
- For the conflict rule, a strand's changes include the reactions they set off and the kept values worked out again because of them (section 12.7).

### 13.19 New words and grammar

No word would become reserved: the list in section 3 is frozen. Every word of these forms is recognised by where it stands, as `item`, `first`, `last`, `larger`, `smaller`, `rounded` and the rest already are in the forms that have been built: `unit` only in `is a unit of`, `moment` only in brackets as a type, `average`, `largest` and `smallest` only after `the` and before `of` or a group, a month's name only between a day and a year (`19 November 2026`), and `order` only in `in order` and `in reverse order`. Each stays free for names elsewhere.

The grammar still to be built, beyond section 11:

```text
base-type    = ... | MEASURE | "moment"
PLURAL-TYPE  = ... | the plural of a CHOICE-SET

definition   = ... | superlative | unit | kind-of
superlative  = "The" WORD KIND "is the one with the" ( "largest" | "smallest" ) PROPERTY "."
unit         = article UNIT { "(" unit-note ")" } "is a unit of" MEASURE "."
             | article UNIT { "(" unit-note ")" } "is" NUMBER UNITS "."
unit-note    = "plural" WORD | "written" SYMBOL
kind-of      = article KIND [ "(" "plural" WORD ")" ] "is a kind of" KIND "."
verb         = "To" VERB-WORD { VERB-WORD } [ role ] { PREPOSITION role } ":"

test         = ... | "there is" ( article | "no" ) singular-group
             | "every" singular-group "is" [ "not" ] ADJECTIVE
tail         = ... | article KIND

value        = ... | "now"
             | NUMBER UNIT | SYMBOL NUMBER | NUMBER MONTH NUMBER
             | pick | list-form | number-form | clock-form
pick         = "the" ( "first" | "last" | SUPERLATIVE ) singular-group
             | "the" singular-group "with the" ( "largest" | "smallest" ) PROPERTY
             | "the" ( "first" | "last" ) value group
group        = ... | group "in order of" PROPERTY | group "in reverse order of" PROPERTY
```

`list-form`, `number-form` and `clock-form` are the forms in the tables of sections 13.7, 13.10, 13.12 and 13.15 that are not built yet.

## 14. Not defined yet

Sections 12 and 13 settle most of what used to be listed here. These remain open.

**Programs**
- Chapters and books (section 9.6) reach only the chapters beside a file, and the books beside it or beside the program: there is no shelf of books shared by programs.
- Chance: a number or a thing picked at random.
- Rules that span several things, rules about worked-out properties or adjectives, and rules that read a variable that can change. Today a rule may read only values written out, variables made with `always`, and its own thing's stored properties (section 4.5), because it is checked only when that thing's stored properties change; a rule that read anything else could be broken without anyone noticing. Checking such rules would mean finding, after every change, every rule whose answer that change could alter.
- Lookup tables from one value to another. Today the nearest thing is finding a thing by its name.

**Values**
- Times of day, time zones, and calendar arithmetic such as "a month from now" or "every Monday".
- Measures built from other measures, such as speed, and conversion between measures, such as exchange rates.
- Searching and replacing inside text.
- Bit operations on whole numbers: and, or, exclusive-or and shifts. They can be built today from halving and `is divisible by`, as `examples/sha256.english` does, but there are no words for them.
- The code of a character, and the character for a code. `examples/sha256.english` looks each character up in a text holding the whole keyboard.
- Choosing how many decimal places a value is said with, beyond rounding it first.
- Properties that can never change after a thing is created.

**Doing things at once** (from section 12.10)
- Detached work, time limits, racing, and stopping another strand.
- Reactions to a plain condition, not only to a thing becoming an adjective.

**Layout**
- Whether indentation should give way to numbered steps or paragraphs. This was considered and set aside.

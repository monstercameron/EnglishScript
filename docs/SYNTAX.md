# EnglishScript syntax

This document describes every sentence the EnglishScript compiler accepts. Sections 1 to 11 describe the language as implemented in `englishscript/`. Section 12 is a proposed extension that has been designed but not built. Section 13 lists what has not been defined yet.

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
- **A closing quote may end a sentence**, so `Say "Hello."` needs no second period.
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

Every value has one of these types. The compiler works out each type before the program runs.

| Type | Written | Said as |
|---|---|---|
| `number` | `7`, `1,000`, `2.5` | `7`, `1,000`, `2.5` |
| `money` | `$5`, `$1,000`, `$0.50` | `$5`, `$1,000`, `$0.50` |
| `percent` | `10%`, `2.5%` | `10%`, `2.5%` |
| `text` | `"Hello"` | `Hello` |
| a kind, such as `dragon` | the thing's name, `Smaug` | `Smaug` |

- A comma in a number must be followed by exactly three digits.
- There are no negative literals; write a minus sign in front: `-5`, `-$5`.
- Arithmetic is exact, so `0.1 + 0.2` is `0.3`. Rounding happens only when a value is said: numbers show up to four decimal places, and money shows whole cents.
- A condition produces a yes-or-no answer. That answer can steer `If`, `While` and definitions, but it cannot be stored in a variable or said.

```englishscript
Say 1,000 + 2.5.       #> 1,002.5
Say $1,000 + $0.50.    #> $1,000.50
Say 50%.               #> 50%
Say 0.1 + 0.2.         #> 0.3
Say 1 / 3.             #> 0.3333
Say $10 / 3.           #> $3.33
Say -$5.               #> -$5
Say Smaug.             #> Smaug
```

### Text

Text sits between double quotes. Anything inside `{braces}` is an expression, worked out when the text is said. Text cannot contain a double quote or a brace of its own; there is no escape character.

```englishscript
Say "Smaug is {Smaug's age} and guards {the hoard of Smaug}."   #> Smaug is 771 and guards $3,500.
Say "Half of that is {50% of Smaug's hoard}."                   #> Half of that is $1,750.
```

## 3. Names

A word is letters, digits and underscores, starting with a letter.

| What is named | Length |
|---|---|
| Kind, adjective, verb | one word |
| Property, variable, thing | one or more words |

Three rules apply to every name:

1. **Defined before use.** A sentence may only use kinds, things, adjectives, properties, verbs and variables introduced by an earlier sentence.
2. **One meaning in view.** A name cannot be reused while an earlier meaning is still visible. To change a variable, use `Set`, not a second `Let`.
3. **No reserved words.** None of the words below may be part of a new name.

| Group | Reserved words |
|---|---|
| Articles and pronouns | `a` `an` `the` `it` `its` `they` `them` `their` |
| Built-in verbs | `let` `set` `add` `subtract` `multiply` `divide` `say` `if` `for` `repeat` `while` `there` |
| Types | `number` `money` `text` `percent` |
| Linking words | `of` `is` `are` `be` `has` `called` `whose` `when` `each` `all` `otherwise` `example` `name` |
| Logic and comparison | `not` `and` `or` `never` `always` `than` `less` `more` `greater` `least` `most` `divisible` |
| Arithmetic | `plus` `minus` `times` `divided` |
| Prepositions | `with` `to` `from` `against` `for` `by` `on` `at` `into` `onto` `about` `over` `under` `as` `through` `toward` `towards` `upon` |

**Plurals** are formed by rule: add `s`; add `es` after `s`, `x`, `z`, `ch` or `sh`; change a consonant plus `y` to `ies`. So `dragon` gives `dragons`, `fox` gives `foxes` and `pony` gives `ponies`.

## 4. Describing the world

These five sentence forms are definitions. They are allowed only at the top level, never inside a block.

### 4.1 Kinds

```text
A | An <kind> has a | an <property> (<type>) [, a | an <property> (<type>)]... .
```

- The type in brackets is required. It is `number`, `money`, `text`, `percent`, or a kind that has already been described.
- Properties are separated by a comma, by `and`, or by both.
- Every thing also has a `name`, which is text and cannot be changed.

```englishscript
A wizard has a hat size (number) and a motto (text).
A tower has a height (number), a keeper (knight), and a prisoner (dragon).
```

### 4.2 Things

```text
There is a | an <kind> called <name> [whose <property> is <expression>]... .
```

- Every property listed for the kind must be given, with a value of the right type.
- Further `whose` parts are joined by a comma, by `and`, or by both.
- The name must be new.

```englishscript
A wizard has a hat size (number) and a motto (text).
There is a wizard called Merlin Ambrosius whose hat size is 7 and whose motto is "Never late".
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

The comparison is anything that may follow `is` in a condition (section 6). A rule must be about a stored property. It is checked when a thing of that kind is created and whenever one of its stored properties changes. A change that would break a rule is undone and the program stops.

```englishscript
A dragon's age is always at least 0.
A treasure's worth is never more than $1,000,000.
```

```refused
A dragon's age is always at least 0.
Subtract 5 from Norbert's age.
```

## 5. Expressions

### 5.1 Referring to something

| Form | Meaning |
|---|---|
| `Smaug` | A named thing. |
| `the total`, `total` | A variable made with `Let`. `the` is optional. |
| `the dragon` | The dragon in view: a role of the current verb, or the noun of an enclosing `For each`. |
| `it`, `they`, `them` | The one thing in view. |
| `its ...`, `their ...` | A property of the one thing in view. |

A thing is **in view** inside a definition about it, inside a verb that has it as a role, and inside a `For each` over it. Named things and variables are not in view for this purpose.

- `the <noun>` is refused unless something of that name is in view.
- A pronoun is refused unless exactly one thing is in view.

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

### 5.3 Arithmetic

| Operation | Symbol | Words |
|---|---|---|
| Add | `+` | `plus` |
| Subtract | `-` | `minus` |
| Multiply | `*` | `times` |
| Divide | `/` | `divided by` |
| Negate | `-` in front | |

Order of working, tightest first: brackets and property access; a leading minus and `% of`; multiplying and dividing; adding and subtracting. Operations of the same strength go left to right.

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
| Multiply | number by number | number |
| | money by number, in either order | money |
| Divide | number by number | number |
| | money by number | money |
| | money by money | number |
| `% of` | percent of number | number |
| | percent of money | money |

```refused
Say $5 + 5.
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
[all] [<adjective>]... <kinds> [of <thing>] [whose <property> <comparison>]
its | their [<adjective>]... <kinds> [whose <property> <comparison>]
<thing>'s [<adjective>]... <kinds> [whose <property> <comparison>]
```

- The kind is plural.
- Each adjective must be defined for that kind.
- `of <thing>`, and the two possessive forms, keep the things that belong to the owner. This works only when the kind has **exactly one** property whose type is the owner's kind. With none, or with two, the sentence is refused.
- `whose` keeps the things that pass a comparison on one of their properties.

Two expressions take a group:

```text
the number of <group>
the total <property> of <group>
```

`the total` needs a property that is a number or money.

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
| `=`, `<`, `>`, `<=`, `>=` | The same comparisons as symbols. |

- Ordering comparisons work on numbers, money and percentages, and both sides must be the same type.
- Comparisons are joined with `and` or with `or`. `not` in front reverses the comparison, or the bracketed condition, that follows it.
- **`and` and `or` cannot be mixed** in one condition unless brackets show which belong together.

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
```

```refused
If Smaug is ancient and Robin is brave or Gawain is brave:
  Say "Which way?"
```

## 7. Actions

### 7.1 Variables

```text
Let [the] <name> be <expression>.
```

A variable takes the type of its first value and keeps it. One made at the top level lasts for the rest of the program; one made inside a block lasts to the end of that block.

### 7.2 Changing things

```text
Set <target> to <expression>.
Add <expression> to <target>.
Subtract <expression> from <target>.
Multiply <target> by <expression>.
Divide <target> by <expression>.
```

A target is a variable made with `Let`, or a stored property of a thing. The new value must have the target's type. These cannot be changed: a worked-out property, a `name`, a role of a verb, and the noun of a `For each`.

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

```englishscript
For example, the hoard of Smaug is $3,500.
For example Norbert is not ancient.
```

```refused
For example, the hoard of Smaug is $1.
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

This is a group (section 5.5) written in the singular. Inside the block the current thing is `the <kind>`, and it is in view for pronouns. Things are visited in the order they were created, and the group is settled when the loop starts.

A `For each` is refused when its kind is already in view, because `the <kind>` would then mean two things.

```englishscript
For each brave knight:
  Say the knight.
#> Gawain
For each treasure of Smaug whose worth is less than $1,000:
  Say "{its name} is small."
#> Cup is small.
```

### 8.3 Repeat and While

```text
Repeat <expression> times:
While <condition>:
```

`Repeat` needs a whole number that is not negative. `While` is stopped after 10,000 rounds.

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

## 10. How a sentence can go wrong

Problems are reported at two stages.

**Before anything runs**, the whole program is compiled. A sentence is refused if any word has no meaning yet, if a phrase could be read more than one way, or if the types don't fit. The message quotes the sentence, points at the part in question, and usually suggests a fix.

**While running**, the program stops if:

- a change would break a `never` or `always` rule;
- a `For example` does not hold;
- something is divided by zero, or tested for being divisible by zero;
- `Repeat` is given a fraction or a negative number;
- a `While` passes 10,000 rounds, or a verb uses itself more than 200 levels deep.

## 11. Grammar summary

Words in capitals are names from the program's own vocabulary. Quoted words are written as shown, in any capitalisation.

```text
sentence    = definition | action | block-opener

definition  = kind | thing | adjective | property | rule | verb       (top level only)
kind        = article KIND "has" field { sep field } "."
field       = article NAME "(" type ")"
thing       = "There is" article KIND "called" NAME [ whose { sep whose } ] "."
whose       = "whose" PROPERTY "is" expression
adjective   = article KIND "is" ADJECTIVE "when" condition "."
property    = "The" NAME "of" article KIND "is" expression "."
rule        = article KIND "'s" PROPERTY "is" ( "never" | "always" ) tail "."
verb        = "To" VERB [ role ] { PREPOSITION role } ":"
role        = article ( KIND | NAME "(" type ")" )
article     = "a" | "an"
sep         = "," | "and" | "," "and"
type        = "number" | "money" | "text" | "percent" | KIND

action      = let | change | say | use | example
let         = "Let" [ "the" ] NAME "be" expression "."
change      = "Set" target "to" expression "."
            | "Add" expression "to" target "."
            | "Subtract" expression "from" target "."
            | "Multiply" target "by" expression "."
            | "Divide" target "by" expression "."
say         = "Say" expression "."
use         = VERB [ expression ] { PREPOSITION expression } "."
example     = "For example" [ "," ] condition "."
target      = a variable made with Let | a stored property of a thing

block-opener = "If" condition ":"
            | "Otherwise if" condition ":"
            | "Otherwise" ":"
            | "For each" { ADJECTIVE } KIND [ "of" value ] [ filter ] ":"
            | "Repeat" expression "times" ":"
            | "While" condition ":"

condition   = test { "and" test } | test { "or" test }
test        = "not" test | "(" condition ")" | expression comparison
comparison  = ( "is" | "are" ) [ "not" ] tail
            | ( "=" | "<" | ">" | "<=" | ">=" ) expression
tail        = "less than" expression | "more than" expression
            | "greater than" expression | "at least" expression
            | "at most" expression | "divisible by" expression
            | ADJECTIVE | expression

expression  = term { ( "+" | "plus" | "-" | "minus" ) term }
term        = factor { ( "*" | "times" | "/" | "divided by" ) factor }
factor      = "-" factor | value [ "of" factor ]       ("of" needs a percentage on its left)
value       = NUMBER | MONEY | PERCENT | TEXT | "(" expression ")"
            | THING
            | [ "the" ] VARIABLE
            | [ "the" ] NOUN-IN-VIEW
            | "it" | "they" | "them"
            | ( "its" | "their" ) PROPERTY
            | value "'s" PROPERTY
            | "the" PROPERTY "of" value
            | "the number of" group
            | "the total" PROPERTY "of" group
group       = [ "all" ] { ADJECTIVE } KINDS [ "of" value ] [ filter ]
            | ( "its" | "their" ) { ADJECTIVE } KINDS [ filter ]
            | value "'s" { ADJECTIVE } KINDS [ filter ]
filter      = "whose" PROPERTY comparison
```

## 12. Proposed: time, and doing things at once

> **Status: designed, not built.** The compiler does not accept the sentences in this section yet, and its examples are not run by the tests.

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

```text
Whenever a | an <kind> becomes <adjective>:
```

This is a definition, allowed only at the top level. It applies from that sentence to the end of the program. A thing **becomes** an adjective when a sentence leaves it fitting the adjective's definition and it did not fit before. The block is then carried out at once, before any other strand continues, with the thing in view as `the <kind>`.

A thing that already fits when it is created does not "become". A `Whenever` may set off another, to a depth of 200.

```text
A knight is broke when its purse is $0.

Whenever a knight becomes broke:
  Say "{the knight} is out of money."
```

### 12.7 The rules that keep it strict

**1. Work changes hands only at a wait.** Between one `Wait` and the next, a strand's sentences are carried out without interruption. No strand ever sees a change half made, and a `never` or `always` rule cannot be caught in between.

**2. "At the same time" is a promise that order doesn't matter, and the compiler checks it.** For each strand, the compiler works out what it reads and what it changes, following the verbs it uses. Two strands conflict when one changes something the other reads or changes. A conflict is refused before the program runs.

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

These words would become reserved: `wait` `until` `every` `whenever` `becomes` `same` `time` `second` `seconds` `minute` `minutes` `hour` `hours`.

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

definition   = ... | reaction
reaction     = "Whenever" article KIND "becomes" ADJECTIVE ":"
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
- **Calendar time**: dates, times of day, "every Monday".
- **Reactions to a plain condition**, not only to a thing becoming an adjective.

## 13. Not defined yet

These are gaps in the language, listed so they can be decided deliberately.

**Values**
- Lists of plain values, such as a list of numbers or of text.
- Dates, times and durations.
- Operations on text: joining, length, comparing alphabetically.
- A way to write a double quote or a brace inside text.
- Remainders as a value (only `is divisible by` exists).
- Storing a yes-or-no answer in a variable or a property.

**Things**
- Optional properties, defaults, and "nothing". Today every property is required, so a kind cannot have a property of its own kind and still be created.
- Creating things inside a verb, and removing things.
- Kinds with no properties, and kinds that extend other kinds.
- Irregular plurals such as "people".
- A property that holds several things, rather than one.

**Groups**
- Ordering a group, and picking one thing from it ("the richest dragon", "the first treasure").
- Asking whether a group is empty ("if there is a poor dragon") or whether all of it passes a test.
- Averages, largest and smallest.
- Naming a loop's thing, so a `For each` can run over a kind that is already in view.

**Verbs**
- Verbs that give back a value.
- Leaving a verb or a loop early.
- Verbs with more than one word, and verbs that take a group.

**Programs**
- Reading input, files, or the time.
- Splitting a program across files.
- Rules that span several things, and rules about worked-out properties.

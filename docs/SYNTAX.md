# EnglishScript syntax

This document describes every sentence the EnglishScript compiler accepts. Sections 1 to 11 describe the language as implemented in `englishscript/`. Sections 12 and 13 are proposed extensions that have been designed but not built. Section 14 lists what has not been defined yet.

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

The compiler stops refusing once the program has checked. A check counts in four places:

1. inside an `If` whose condition shows the value is there;
2. in the rest of that condition, after `and`;
3. in the `Otherwise` of an `If` that showed it missing;
4. after an `If` that showed it missing and whose block always leaves (section 8.4).

A check stops counting when that property or variable is changed, and when a verb is used, because a verb may change anything.

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
| Built-in verbs | `let` `set` `add` `subtract` `multiply` `divide` `say` `if` `for` `repeat` `while` `there` `stop` `skip` `end` |
| Types | `number` `money` `text` `percent` |
| Linking words | `of` `is` `are` `be` `has` `called` `whose` `when` `each` `all` `otherwise` `example` `name` `nothing` `any` `else` `answer` |
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

- The type in brackets is required. It is `number`, `money`, `text`, `percent`, or a kind that has already been described. Adding `, if any` lets the property be missing (section 2).
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

- Every property listed for the kind must be given, with a value of the right type. A property marked `if any` may be left out.
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
| `is nothing` | The value is missing (section 2). |
| `has a <property>`, `has no <property>` | The property is there, or is missing. Written without `is`. |
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
Let [the] <name> [(<type>)] [always] be <expression>.
```

- A variable takes the type of its first value and keeps it.
- A type in brackets says what the variable may hold. It is needed when the first value is `nothing`, and optional otherwise.
- A variable made with `always` cannot be changed afterwards.
- A variable made at the top level lasts for the rest of the program; one made inside a block lasts to the end of that block.

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

A target is a variable made with `Let`, or a stored property of a thing. The new value must have the target's type. These cannot be changed: a worked-out property, a `name`, a role of a verb, the noun of a `For each`, and a variable made with `always`.

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

### 8.4 Stopping early

```text
Stop.                  ends the verb being carried out
Stop repeating.        ends the loop around this sentence
Skip this <noun>.      goes on to the next thing in a For each
Skip this round.       goes on to the next round of a Repeat or While
End the program.
```

- `Stop.` is refused outside a verb. Inside `To work out` (section 9.3), use `The answer is`.
- `Skip this <noun>.` names its loop by the loop's noun, so it is clear in nested loops.
- `Stop repeating.` and `Skip this round.` are refused when more than one loop is around the sentence, because they could mean either. Move the inner loop into its own verb and use `Stop.` there.
- A loop written outside a verb is not "around" the sentences inside that verb.

A block that ends in one of these sentences **always leaves**. An `If` whose block always leaves works as a guard: the sentences after it can rely on its condition having been false (section 2, "Nothing").

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
- `The answer is ...` ends the work and gives the value. Every path through the block must reach one.
- **Working out changes nothing.** The block may make and change its own variables, loop, and use other worked-out values. It may not change a thing or an outside variable, say anything, or use a verb.
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
    The answer is "pass".
```

Refused, because working out cannot say anything:

```refused
To work out the census (number):
  Say "Counting."
  The answer is the number of dragons.
```

## 10. How a sentence can go wrong

Problems are reported at two stages.

**Before anything runs**, the whole program is compiled. A sentence is refused if any word has no meaning yet, if a phrase could be read more than one way, or if the types don't fit. The message quotes the sentence, points at the part in question, and usually suggests a fix.

**While running**, the program stops if:

- a change would break a `never` or `always` rule;
- a `For example` does not hold;
- something is divided by zero, or tested for being divisible by zero;
- `Repeat` is given a fraction or a negative number;
- a `While` passes 10,000 rounds, or a verb or a worked-out value uses itself more than 200 levels deep.

## 11. Grammar summary

Words in capitals are names from the program's own vocabulary. Quoted words are written as shown, in any capitalisation.

```text
sentence    = definition | action | block-opener

definition  = kind | thing | adjective | property | rule | verb | work-out      (top level only)
kind        = article KIND "has" field { sep field } "."
field       = article NAME "(" type ")"
thing       = "There is" article KIND "called" NAME [ whose { sep whose } ] "."
whose       = "whose" PROPERTY "is" expression
adjective   = article KIND "is" ADJECTIVE "when" condition "."
property    = "The" NAME "of" article KIND "is" expression "."
rule        = article KIND "'s" PROPERTY "is" ( "never" | "always" ) tail "."
verb        = "To" VERB [ role ] { PREPOSITION role } ":"
work-out    = "To work out the" NAME "(" type ")" { ( PREPOSITION | "of" ) role } ":"
role        = article ( KIND | NAME "(" type ")" )
article     = "a" | "an"
sep         = "," | "and" | "," "and"
type        = base-type [ "," "if any" ]
base-type   = "number" | "money" | "text" | "percent" | KIND

action      = let | change | say | use | example | answer | leave
let         = "Let" [ "the" ] NAME [ "(" type ")" ] [ "always" ] "be" expression "."
change      = "Set" target "to" expression "."
            | "Add" expression "to" target "."
            | "Subtract" expression "from" target "."
            | "Multiply" target "by" expression "."
            | "Divide" target "by" expression "."
say         = "Say" expression "."
use         = VERB [ expression ] { PREPOSITION expression } "."
example     = "For example" [ "," ] condition "."
answer      = "The answer is" expression "."                        (inside To work out)
leave       = "Stop." | "Stop repeating." | "Skip this" NOUN "." | "Skip this round."
            | "End the program."
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
            | "has" article PROPERTY | "has no" PROPERTY
            | ( "=" | "<" | ">" | "<=" | ">=" ) expression
tail        = "less than" expression | "more than" expression
            | "greater than" expression | "at least" expression
            | "at most" expression | "divisible by" expression
            | "nothing" | ADJECTIVE | expression

expression  = sum { "or else" sum }
sum         = term { ( "+" | "plus" | "-" | "minus" ) term }
term        = factor { ( "*" | "times" | "/" | "divided by" ) factor }
factor      = "-" factor | value [ "of" factor ]       ("of" needs a percentage on its left)
value       = NUMBER | MONEY | PERCENT | TEXT | "(" expression ")" | "nothing"
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
- **Calendar time**: times of day and "every Monday". Dates and the present moment are in section 13.15.
- **Reactions to a plain condition**, not only to a thing becoming an adjective.

## 13. Proposed: the rest of the language

> **Status: designed, not built.** The compiler does not accept the sentences in this section yet. Its examples are not run by the tests; a `#>` comment shows what a line would say. Each example assumes the world at the top of this document, changed as its own subsection describes.

This section gives a syntax to every gap that used to be listed here. Four of its subsections have since been built and moved into the sections above; their headings remain so that the numbering stays the same. Three habits run through it:

- **Brackets carry the detail.** As with `(number)`, anything extra about a name goes in brackets after it: `(dragon, if any)`, `(list of numbers)`, `(plural people)`, `(written £)`.
- **What may be missing must be checked.** A value that might be nothing cannot be used until the program has shown that it is there.
- **Working something out never changes anything.** A sentence that gives a value cannot also change the world, so it is safe inside conditions, definitions and rules.

| Gap | Where it is settled |
|---|---|
| "Nothing" and optional properties | Built: section 2, "Nothing" |
| Yes-or-no values | 13.2 |
| A fixed set of choices | 13.3 |
| Constants | Built: section 7.1 |
| Verbs that give back a value | Built: section 9.3 |
| Leaving early | Built: section 8.4 |
| Lists of plain values | 13.7 |
| Naming a loop's thing | 13.8 |
| Picking from a group, and ordering | 13.9 |
| Asking about a group; averages, largest, smallest | 13.10 |
| Creating and removing things while running | 13.11 |
| Remainders and mathematical functions | 13.12 |
| Text operations, and quotes and braces inside text | 13.13 |
| More units | 13.14 |
| Input: a line, a file, the clock | 13.15 |
| Recovering from a problem | 13.16 |
| Irregular plurals, multi-word verbs, kinds that extend kinds | 13.17 |
| Time and concurrency | 12, with 13.18 |

### 13.1 Nothing, and properties that may be absent

**Built.** See "Nothing" in section 2.

One thing was added while building it: a check also counts after an `If` that showed the value missing and whose block always leaves, so that a guard such as `If the knight has no mount: ... Stop.` works.

Averages, largest and smallest (section 13.10) will leave out things whose property is nothing, as `the total` already does.

### 13.2 Yes-or-no facts and values

A yes-or-no fact about a thing is an adjective that is stored instead of worked out.

```text
A | An <kind> can be <adjective>.
Now <thing> is [not] <adjective>.
There is a | an [<adjective>]... <kind> called <name> [whose ...]... .
```

- A stored adjective is used exactly like a defined one: after `is`, in front of a kind in a group, and in `Whenever`.
- It starts as "no", unless it is written in front of the kind when the thing is created.
- `Now` is the only way to change it. `Now` is refused for an adjective defined with `when`.
- A property of type yes-or-no is refused, with a pointer to `can be`. There is one way to say it.

For variables, list items and worked-out values there is a plain type:

```text
(yes or no)                  the type
yes | no                     its two values
whether <condition>          a condition, as a value
<value> is yes | no          a value, as a condition
```

```text
A knight can be sworn.
There is a sworn knight called Gawain whose purse is $300 and whose courage is 8.
There is a knight called Robin whose purse is $20 and whose courage is 2.

Say the number of sworn knights.     #> 1
Now Robin is sworn.
Now Gawain is not sworn.

Let the gate open be whether Gawain is sworn or Robin is sworn.
If the gate open is yes:
  Say "Enter."                       #> Enter.
```

### 13.3 A fixed set of choices

```text
A | An <name> is one of <choice>, <choice> ... or <choice>.
```

- This defines a type, used in brackets like any other. Each choice is one or more words.
- A choice may belong to only one set, and may not be the name of a kind, a thing or a variable. It may be the same word as an adjective, because the left side of `is` says which is meant.
- Choices are compared with `is` and `is not` only. A choice is said as its words.
- Writing a word that is not one of the choices is refused before the program runs.

```text
A mood is one of sleepy, grumpy or content.
A dragon has an age (number) and a mood (mood).

There is a dragon called Smaug whose age is 771 and whose mood is sleepy.
Set Smaug's mood to grumpy.
If Smaug's mood is grumpy:
  Say "Tread softly."       #> Tread softly.
```

### 13.4 Variables that cannot change

**Built.** See section 7.1.

### 13.5 Working out a value

**Built.** See section 9.3.

### 13.6 Stopping early

**Built.** See section 8.4. `Skip this round.` will also apply to `Every` (section 12.5) once that exists.

### 13.7 Lists

```text
(list of <plural type>)                             the type
a list of <value>, <value> ... and <value>          a list written out
an empty list of <plural type>
```

- The plural type is `numbers`, `percentages`, `money`, `text`, the plural of a kind, or the plural of a set of choices.
- A list written out may appear only as the whole value of `Let`, `Set`, a `whose` part, or `The answer is`, so its commas cannot be confused with anything else.
- A group written where a list is expected becomes a list of the things in it at that moment: `Let the suspects be all poor dragons.`
- A list of things may be used wherever a group may (section 5.5).
- Items are numbered from 1.

| Form | Gives |
|---|---|
| `the number of items in <list>` | a number |
| `the first of <list>`, `the last of <list>`, `item <number> of <list>` | an item, if any |
| `the total of <list>` | a number or money |
| `the average of <list>`, `the largest of <list>`, `the smallest of <list>` | a value, if any |
| `<list> in order`, `<list> in reverse order` | a list, smallest or alphabetically first |
| `<list> joined with <text>` | text |
| `<value> is [not] in <list>` | a condition |

| Sentence | Does |
|---|---|
| `Add <value> to <list>.` | Puts the value at the end. |
| `Remove <value> from <list>.` | Takes out the first item equal to it. If there is none, nothing happens. |
| `For each <name> in <list>:` | Goes through the items, each one as `the <name>`. |

```text
Let the scores be a list of 3, 8 and 5.
Add 10 to the scores.
Say the number of items in the scores.         #> 4
Say the total of the scores.                   #> 26
Say the largest of the scores or else 0.       #> 10
Say the scores in order joined with ", ".      #> 3, 5, 8, 10
For each score in the scores:
  If the score is more than 7:
    Say the score.
#> 8
#> 10
```

A property or a role may be a list, which is how a thing holds several things and how a verb takes a group:

```text
A knight has a purse (money) and a trophy shelf (list of treasures).

To honour a company (list of knights):
  For each member in the company:
    Now the member is sworn.

Honour all brave knights.
```

### 13.8 Naming a loop's thing

```text
For each <name> in <group>:
```

The group is written in the plural (section 5.5). Inside the block the current thing is `the <name>`. This lets a loop run over a kind that is already in view.

```text
To greet a dragon:
  For each rival in dragons whose age is more than 100:
    If the rival is not the dragon:
      Say "{the dragon} glares at {the rival}."
```

`For each dragon:` (section 8.2) stays as the short form, and is still refused when a dragon is already in view.

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
- `in order of` puts the smallest first, or the alphabetically first for text. Things that tie stay in the order they were created.
- **When two things tie for largest or smallest, the one created first is picked.**
- `the first <number> <group>` gives a list, which may be shorter than asked.
- An ordered group may be used in `For each`.

A superlative can be given a name in the glossary:

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

```text
There is a new <kind> [called <text>] [whose ...]... .
Let [the] <name> be a new <kind> [called <text>] [whose ...]... .
the <kind> called <text>
Remove <thing>.
```

- `There is a | an <kind> called <name> ...` (section 4.2) stays at the top level. It is the only way to make a thing that later sentences can mention by name.
- `a new <kind>` may be used anywhere, including inside verbs and loops. Its name is a text value, so it can be built with fill-ins. If no name is given, the name is the kind and a number, such as `treasure 3`.
- To use a new thing afterwards, make it with `Let`.
- `the <kind> called <text>` finds a thing by its name, ignoring capitals. It is `if any`.
- `Remove` takes a thing out of the world. It leaves every group and list. A property marked `if any` that pointed at it becomes nothing.
- **`Remove` is refused while a required property of another thing points at the thing.** The program stops and names what still depends on it.
- Using a removed thing through a variable or a role stops the program.

```text
To hatch an egg for a dragon:
  Let the chick be a new dragon called "{the dragon}'s chick" whose age is 0 and whose parent is the dragon.
  Say "{the chick} hatches."

Hatch an egg for Smaug.                       #> Smaug's chick hatches.
Let the found one be the dragon called "norbert".
If the found one is not nothing:
  Remove the found one.
Say the number of dragons.                    #> 2
```

### 13.12 Remainders and other arithmetic

| Form | Example | Gives |
|---|---|---|
| `the remainder of <value> divided by <value>` | `the remainder of 17 divided by 5` | `2` |
| `<value> rounded to the nearest <value>` | `$3.14159 rounded to the nearest $0.01` | `$3.14` |
| `<value> rounded up to the nearest <value>` | `17 rounded up to the nearest 5` | `20` |
| `<value> rounded down to the nearest <value>` | `17 rounded down to the nearest 5` | `15` |
| `<value> to the power of <value>` | `2 to the power of 10` | `1,024` |
| `the square root of <value>` | `the square root of 81` | `9` |
| `the larger of <value> and <value>` | `the larger of $5 and $8` | `$8` |
| `the smaller of <value> and <value>` | `the smaller of 3 and 7` | `3` |
| `the absolute value of <value>` | `the absolute value of -4` | `4` |

- Each `<value>` is a single value or a bracketed expression. These forms bind more tightly than multiplying and dividing.
- Rounding works on a number, money or a measure (section 13.14); both sides must be the same type. A value exactly halfway rounds away from zero.
- Remainders, powers, roots and absolute values work on plain numbers. `the larger of` and `the smaller of` work on any two values of the same type that can be ordered.
- A power with a whole-number exponent is exact. Other powers, and square roots that do not come out exactly, are worked out to twelve decimal places.
- The square root of a negative number is a problem (section 13.16).

### 13.13 Text

Joining text is done with fill-ins, as before: `"{the first name} {the last name}"`.

| Form | Gives |
|---|---|
| `the length of <text>` | the number of characters |
| `<text> in upper case`, `<text> in lower case` | text |
| `the first <number> letters of <text>`, `the last <number> letters of <text>` | text |
| `the words of <text>`, `the lines of <text>` | a list of text |
| `<text> as a number` | a number, if any |
| `<text> contains <text>`, `<text> starts with <text>`, `<text> ends with <text>` | a condition |
| `<text> comes before <text>`, `<text> comes after <text>` | a condition: alphabetical order, ignoring capitals |

- `is` between two texts is exact, capitals included.
- `the length of` means this only when what follows is text. A thing may still have a property called `length`.

Inside quotes, four things are written specially:

| Written | Means |
|---|---|
| `""` | one double quote |
| `{{` | one opening brace |
| `}}` | one closing brace |
| `{new line}` | a line break |

```text
Let the title be "The ""Lonely"" Mountain".
Say the title.                                  #> The "Lonely" Mountain
Say the length of the title.                    #> 21
Say the title in upper case.                    #> THE "LONELY" MOUNTAIN
Say the number of items in the words of the title.     #> 3
If "apple" comes before "Banana" and the title starts with "The":
  Say "In order."                               #> In order.
```

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

**Asking the person at the keyboard**

```text
Ask <text> and let [the] <name> (<type>) be the reply.
```

The type may be `text`, `number`, `money`, `percent`, `yes or no`, a set of choices, or a measure. If the reply cannot be read as that type, the question is asked again.

```text
Ask "How old is the dragon?" and let the age (number) be the reply.
Ask "What mood is it in?" and let the feeling (mood) be the reply.
```

**Files**

```text
the text of the file <text>
the lines of the file <text>
Write <text> to the file <text>.
Add <text> to the file <text>.
```

`Write` replaces what the file held; `Add` puts the text at the end. A file that cannot be read or written is a problem (section 13.16).

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

```text
Try:
If that fails:
Fail because <text>.
the problem
```

- `Try:` carries out its block. If a problem arises, the rest of the block is abandoned and the `If that fails:` block is carried out. `If that fails:` must follow directly and is required.
- **A failed `Try` leaves the world as it was.** Every change the block made to things and variables is undone, including things created and removed. What was said, asked or written to a file stays.
- Inside `If that fails:`, `the problem` is text describing what went wrong.
- `Fail because <text>.` raises a problem of the program's own.

A problem that can be recovered from is: a broken `never` or `always` rule, a division by zero, the square root of a negative number, a file that cannot be read or written, a `Remove` that is refused, the use of a removed thing, a `Repeat` with a fraction or a negative number, or `Fail because`.

Two things always end the program: a `For example` that does not hold, and passing the limit on loops or on verbs using themselves. They are faults in the program, not events in the world.

```text
To move an amount (money) from a giver (knight) to a taker (knight):
  If the giver is the taker:
    Fail because "a knight cannot pay himself".
  Add the amount to the taker's purse.
  Subtract the amount from the giver's purse.

Try:
  Move $500 from Robin to Gawain.
If that fails:
  Say "No payment: {the problem}"
Say Gawain's purse.          #> $300
```

Gawain's purse was raised to $800 before the rule on Robin's purse was broken, and the failed `Try` put it back.

### 13.17 More about kinds and verbs

**Irregular plurals** go in brackets after the kind:

```text
A | An <kind> (plural <word>) has ...
```

**A kind can be a kind of another:**

```text
A | An <kind> [(plural <word>)] is a kind of <kind>.
<thing> is [not] a | an <kind>          condition
```

- The new kind has every property, adjective, worked-out property and rule of the kind it extends. It may add its own with further sentences, but may not redefine any.
- It can be used wherever the wider kind is expected: as a role, in a property, and in the wider kind's groups.
- There is a built-in kind, `thing`, that every kind extends. `A ghost is a kind of thing.` describes a kind with no properties.
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
- `time` is a measure (section 13.14), and `Now <thing> is <adjective>.` can set off a `Whenever`.

### 13.19 New words and grammar

These words would become reserved, in addition to those in sections 3 and 12.8:

`yes` `no` `now` `whether` `can` `in` `new` `remove` `ask` `write` `try` `fail` `reply` `problem` `list` `item` `items` `first` `last` `largest` `smallest` `average` `larger` `smaller` `thing` `kind` `unit`

The other words in the new forms, such as `rounded`, `nearest`, `remainder`, `upper`, `case`, `order` and `length`, are recognised only inside their phrases. They stay free for use in names.

```text
base-type    = ... | "yes or no" | CHOICE-SET | MEASURE | "moment" | "list of" PLURAL-TYPE

definition   = ... | stored-adj | choices | superlative | unit | kind-of
stored-adj   = article KIND "can be" ADJECTIVE "."
choices      = article NAME "is one of" CHOICE { "," CHOICE } "or" CHOICE "."
superlative  = "The" WORD KIND "is the one with the" ( "largest" | "smallest" ) PROPERTY "."
unit         = article UNIT { "(" unit-note ")" } "is a unit of" MEASURE "."
             | article UNIT { "(" unit-note ")" } "is" NUMBER UNITS "."
unit-note    = "plural" WORD | "written" SYMBOL
kind-of      = article KIND [ "(" "plural" WORD ")" ] "is a kind of" KIND "."
kind         = article KIND [ "(" "plural" WORD ")" ] "has" field { sep field } "."
verb         = "To" VERB-WORD { VERB-WORD } [ role ] { PREPOSITION role } ":"

action       = ... | now | create | remove | ask | write | fail
now          = "Now" value "is" [ "not" ] ADJECTIVE "."
create       = "There is a new" KIND [ "called" value ] [ whose { sep whose } ] "."
remove       = "Remove" value [ "from" value ] "."
ask          = "Ask" value "and let" [ "the" ] NAME "(" type ")" "be the reply" "."
write        = ( "Write" | "Add" ) value "to the file" value "."
fail         = "Fail because" value "."

block-opener = ... | "For each" NAME "in" group ":" | "Try" ":" | "If that fails" ":"

test         = ... | "there is" ( article | "no" ) singular-group
             | "every" singular-group "is" [ "not" ] ADJECTIVE
tail         = ... | "yes" | "no" | article KIND | "in" value
comparison   = ... | "contains" value | "starts with" value | "ends with" value
             | "comes before" value | "comes after" value

value        = ... | "yes" | "no" | "now" | CHOICE
             | NUMBER UNIT | SYMBOL NUMBER | NUMBER MONTH NUMBER
             | "whether" condition
             | "a new" KIND [ "called" value ] [ whose { sep whose } ]
             | "a list of" value { "," value } "and" value
             | "an empty list of" PLURAL-TYPE
             | "the" KIND "called" value
             | pick | list-form | number-form | text-form | "the problem"
pick         = "the" ( "first" | "last" | SUPERLATIVE ) singular-group
             | "the" singular-group "with the" ( "largest" | "smallest" ) PROPERTY
             | "the" ( "first" | "last" ) value group
group        = ... | group "in order of" PROPERTY | group "in reverse order of" PROPERTY
```

`list-form`, `number-form` and `text-form` are the forms in the tables of sections 13.7, 13.10, 13.12, 13.13 and 13.15.

## 14. Not defined yet

Sections 12 and 13 settle most of what used to be listed here. These remain open.

**Programs**
- Splitting a program across files.
- Chance: a number or a thing picked at random.
- Rules that span several things, and rules about worked-out properties.
- Lookup tables from one value to another. Today the nearest thing is finding a thing by its name.

**Values**
- Times of day, time zones, and calendar arithmetic such as "a month from now" or "every Monday".
- Measures built from other measures, such as speed, and conversion between measures, such as exchange rates.
- Searching and replacing inside text.
- Choosing how many decimal places a value is said with, beyond rounding it first.
- Properties that can never change after a thing is created.

**Doing things at once** (from section 12.10)
- Detached work, time limits, racing, and stopping another strand.
- Reactions to a plain condition, not only to a thing becoming an adjective.

**Layout**
- Whether indentation should give way to numbered steps or paragraphs. This was considered and set aside.

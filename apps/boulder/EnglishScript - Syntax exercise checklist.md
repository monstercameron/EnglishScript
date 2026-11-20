# Boulder Badge syntax exercise checklist

**Baseline** · EnglishScript `acf28a2`  
**Game coverage** · Pending implementation. Each box below requires its own evidence from a reachable program path. An accepted form can be exercised in the faithful campaign, its companion, the playable Field Lab, or through a library declaration that one of those programs uses. Report those paths separately.

## What has run

| Evidence | Observed result |
|---|---|
| Repository test suite | 591 passed. The executable syntax document covers 51 runnable examples and 59 expected refusals. Those reference checks are already included in the 591. |
| [Standalone Boulder Badge Field Lab](Boulder%20Badge%20Field%20Lab.english) | 92 EnglishScript assertions passed through the CLI. Covers typed battle calculations, optional values, roster manipulation, text, reactions, recovery, and control flow. This is a review fixture. Its checks can be run with `python -m englishscript "<path to Boulder Badge Field Lab.english>" --test` from the compiler checkout. |
| Role linking words | All 18 values of the compiler’s `PREPOSITIONS` passed an independent declaration, invocation and argument-value check. |
| Async baseline | Ten probes for proposed concurrency forms were refused. The positive cases, failure cases, and required scheduling behavior are in the [concurrency review](EnglishScript%20-%20Concurrency%20design%20for%20review.md). |

## How the release gate works

The current grammar inventory has **61 named productions and 407 structural checks**. These checks enumerate every top-level form, nested alternative, optional part present/absent, and repeated part zero/one/multiple times. A single run can satisfy several checks. Unbounded lengths and input values are tested by boundary and representative cases. Grammar guards still apply, so, for example, a zero-role worked-out definition can use a supported body even though the judge-backed variant requires a role.

For each check attach a source file and span, an accepted compiler-form ID, a replay or test ID, an expected effect, and the observed effect. Declarations require a real consumer. Check optional, skipped and short-circuited paths with paired executions that demonstrate the difference. Preserve original source spelling for lexical checks. An unexecuted branch or a form with no assertion stays open. Required refusals run in a separate harness with expected stage, location and diagnostic. Imported syntax, worker code and alternate entry points must be visible to instrumentation.

Compare the inventory with the current grammar and compiler on every change. New grammar alternatives, contextual forms and proposal implementations get an ID and a corresponding game fixture in the same change. Fail the release check for an unmapped form, missing evidence, or a failed observation. Keep the checked reference answers independent of the compiler under test.

## Runtime and lexical checks beyond the grammar

| ID | Cases to exercise | Observable result |
|---|---|---|
| LAYOUT | Period, sentence ending in a closing quotation mark, colon plus indented block, blank lines, trailing comments, straight/curly quotes and apostrophes, keyword/name capitalization | Equivalent source variants report the same game state. A synthetic lexer test generates comment and indentation fixtures. Malformed indentation, tabs and extra sentences locate the offending text. |
| NAMES | Unicode letters, digits/underscores after a letter, default and irregular plurals, contextual names, longest match, 12-word lookup boundary, duplicate and private names, ambiguous pronouns, defined-before-use | Resolves the intended entity or refuses at the specified name. Test without silently falling back to a shorter name. |
| BIND | Every supported verb linking word, the worked-out linking word `of`, zero or multiple roles, reordered and overloaded shapes, duplicate links and bad types | Check all 18 linking words independently. Use permutations of role order on a multi-role verb and preserve its answer. |
| LITERAL | Escaped braces and quotes, embedded fill-ins, new line, ASCII numeric literals, grouped thousands, percentages, money, decimals, unary minus, exact arithmetic and formatting halfway cases | Compare the actual journal line and the typed value separately. |
| TYPES | Each allowed arithmetic operand pairing, rejected mixed types, narrowing after checks and early exits, invalidation by mutation/call/reaction, short circuit, list element restrictions and snapshot behavior | Check both paths per optional value, and a refusal where proof of presence has expired. Exercise full-value list/group positions and ambiguous first/last/total names. |
| RULES | Runtime checks on create/change/remove, stored and derived facts, indexed lookup after a write, reactions and settling order, kept-value cycles, rollback of world mutations and persistence of external effects | Check state before and after, callback order and the diagnostic for nonsettling changes. |
| PROBLEMS | Broken rule, division by zero, missing file, refused removal, removed thing, bad count, missing item, bad number, bad reply, no model, library problem and explicit failure | Independently trigger all 12 recoverable kinds. Match specific handler and location. Verify fatal guards escape recovery. |
| DIAGNOSTICS | Stable diagnostic IDs, author messages, severity, source spans, related chapter and worker call sites, valid corrections and player recovery text | Compare the same failure across applicable CLI, JSON, editor and browser surfaces. Test Unicode selection, library kind preservation and rethrow using the [standard library and diagnostics plan](EnglishScript%20-%20Standard%20library%20and%20diagnostics.md). |
| LIBRARY | Shipped host bindings and new public operations used by the benchmark | Run a game consumer and a small general-purpose English example. Check typed results, expected failures, unsupported hosts, fatal binding faults, rollback and external effects against the documented contract. |
| IO | Human `Ask` for text, numbers, money, percent and yes/no, failed input then valid input, EOF, file write/append/text/lines and failure | Check the returned type and saved contents. Isolate fixture files. |
| BROWSER-CACHE | Page-library preferences and asynchronous checkpoints for the active save slot. Exercise refresh, browser restart, eviction, quota failure, version mismatch and concurrent tabs. | Restore committed NPC memory and exact game tick/RNG. Replay the next inputs against an uninterrupted run. Clearing a checkpoint preserves the explicit cartridge save and invalidates pending conversation replies. |
| MODELS | Typed/optional/model list/choice replies, text/thing/image state, meanings, ranked grades and likelihoods, batching boundaries, cache identity, retry and replay, Jev and GPT‑6 Luna combinations | Record the expected model request and independently calculate the expected selected value. Exercise different results for grade and verdict. |
| BOOKS | Same-folder chapter, sibling book, public/private exports, duplicate loads, missing/ambiguous/cyclic imports, external verb and value declarations | Verify names and initialization visible across real files. Report the correct chapter for a refusal. |
| BINDINGS | All 14 existing page element kinds, the proposed canvas, DOM input, native Vulkan library verbs and pixel query, planned sound and worker bindings | Use the real host as well as a test host. Check actual canvas pixel readback, emitted sound events, typed results and teardown. |
| TOOLS | CLI check, explain, lint, trace, test, diagnostics with location, editor names, completion, hover, rename, browser compiler ZIP | Compare actual results on game books and diagnostic fixtures. A CLI or editor result counts in its own category. |

## Designed and open changes

| ID | Scope | Game acceptance fixture |
|---|---|---|
| FUT-TIME | Duration units, conversions, arithmetic, moment literals and components, calendar and timezone decisions | Replay a music cue and a journal deadline across a date boundary with a virtual clock. |
| FUT-STRAND | Timed and predicate waits, structured blocks, concurrent filtered loops, bounded timers, deterministic ordering, transitive effects, commutative updates, rollback, deadlocks and cleanup | Run the individual positive/refusal pairs in the [concurrency design](EnglishScript%20-%20Concurrency%20design%20for%20review.md). |
| FUT-WORKER | Worker-safe typed results, thread/process/Web Worker backends, bounded queueing, stale results and out-of-order completions | Execute disjoint battle previews, observe distinct workers, and preserve the parent result and campaign state. |
| FUT-ASYNC | Nonblocking human/model input, named lifetimes, deadlines, racing, cancellation, waiting in reactions and plain-condition reactions | Delay chat while moving, close the scene, replay a duplicate answer, and assert exactly-once delivery to the intended generation. |
| FUT-LISTS | Lists of choices and yes/no, list equality/display/order, min/max/average, list-as-group, stable superlatives and first/last N | Check a party before and after adding, removing, tying, and emptying items. |
| FUT-GROUP | Exists, none, every, optional aggregates, stable sorted groups, named superlatives and tie/empty/absent cases | Compare the roster against a hand-calculated outcome for every branch. |
| FUT-MEASURE | Custom unit, stated plural/symbol, derived units, conversion, measure arithmetic, typed human choice/measure input, compound units and conversion-rate decisions | Compare tile distances, journal dates, sound timing and typed starter choices. |
| FUT-KIND | Root kind, inheritance, widening, narrowed subtype test, inherited rules and multiword verbs | Address a trainer as a person and use its specialized properties only after narrowing. |
| FUT-DATA | Shared book shelf, lookup tables, seeded random choice/number, cross-object invariants, richer model state/typed responses, immutable properties | Validate imports, seeded encounters, roster consistency and visible-identity reply validation. |
| FUT-VALUE | Text search/replacement, character codes, bit operations and shifts, output precision | Compare trainer-name search, save flags, input masks and Field Lab score display with known values. |
| OPEN-LAYOUT | Numbered steps or paragraphs were previously set aside | Track the review decision explicitly. If adopted, add syntax and refusal IDs before closing coverage. |

The current boxes below are keyed to the pinned §11 grammar. IDs name the production, syntactic branch and nested position. The definition line at each heading gives the proposed game use and evidence. These are open game checks even where the separate baseline suite already passes. [Pinned language reference](https://github.com/monstercameron/EnglishScript/blob/acf28a2/docs/SYNTAX.md#11-grammar-summary)

## Current grammar checklist

### `sentence`

Campaign entry and lab replay. Observe a definition consumed, an action’s effect, and each selected block body.

- [ ] `SENTENCE.1` — `definition`
- [ ] `SENTENCE.2` — `action`
- [ ] `SENTENCE.3` — `block-opener`

### `definition`

World, People, Battle and Journey books. Import each definition and exercise its resulting vocabulary, rule, reaction or library effect.

- [ ] `DEFINITION.1` — `kind`
- [ ] `DEFINITION.2` — `thing`
- [ ] `DEFINITION.3` — `adjective`
- [ ] `DEFINITION.4` — `stored-adj`
- [ ] `DEFINITION.5` — `property`
- [ ] `DEFINITION.6` — `rule`
- [ ] `DEFINITION.7` — `verb`
- [ ] `DEFINITION.8` — `work-out`
- [ ] `DEFINITION.9` — `reaction`
- [ ] `DEFINITION.10` — `settled`
- [ ] `DEFINITION.11` — `library`
- [ ] `DEFINITION.12` — `chapter`
- [ ] `DEFINITION.13` — `shares`
- [ ] `DEFINITION.14` — `choices`
- [ ] `DEFINITION.15` — `keep`
- [ ] `DEFINITION.16` — `meaning`

### `meaning`

Companion intent labels. A replayed Jev request receives exactly the declared meaning for the chosen label.

- [ ] `MEANING` — `"For" article CHOICE-SET "," CHOICE "means" TEXT "."`

### `keep`

Party inspector and gauge. Change the source twice and check the kept field on each thing, a named thing’s field, and a kept mark.

- [ ] `KEEP.1` — `"Keep each" KIND "'s" PROPERTY "as" whole "."`
- [ ] `KEEP.2` — `"Keep" THING "'s" PROPERTY "as" whole "."`
- [ ] `KEEP.3` — `"Keep each" KIND ADJECTIVE "when" condition "."`

### `choices`

Party strategy selector. Preserve the declared choice order through selecting, displaying and grading.

- [ ] `CHOICES` — `article NAME "is one of" CHOICE { "," CHOICE } [ "," ] "or" CHOICE "."`
- [ ] `CHOICES-5.zero` — `Use zero occurrences of { "," CHOICE }`
- [ ] `CHOICES-5.one` — `Use one occurrence of { "," CHOICE }`
- [ ] `CHOICES-5.many` — `Use two or more occurrences of { "," CHOICE }`
- [ ] `CHOICES-6.absent` — `Omit [ "," ]`
- [ ] `CHOICES-6.present` — `Include [ "," ]`

### `kind`

Cast and creatures. Instantiate the kind and use its default or stated plural in a group.

- [ ] `KIND` — `article KIND [ "(" "plural" WORD ")" ] "has" field { sep field } "."`
- [ ] `KIND-3.absent` — `Omit [ "(" "plural" WORD ")" ]`
- [ ] `KIND-3.present` — `Include [ "(" "plural" WORD ")" ]`
- [ ] `KIND-6.zero` — `Use zero occurrences of { sep field }`
- [ ] `KIND-6.one` — `Use one occurrence of { sep field }`
- [ ] `KIND-6.many` — `Use two or more occurrences of { sep field }`

### `field`

Roster entries. Initialize each field and read it back at its declared type.

- [ ] `FIELD` — `article NAME "(" type ")"`

### `thing`

Starter selection and moves. Check the identity, display name, marks and initial fields of each declared thing.

- [ ] `THING` — `"There is" article { ADJECTIVE } KIND "called" NAME [ whose { sep whose } ] "."`
- [ ] `THING-3.zero` — `Use zero occurrences of { ADJECTIVE }`
- [ ] `THING-3.one` — `Use one occurrence of { ADJECTIVE }`
- [ ] `THING-3.many` — `Use two or more occurrences of { ADJECTIVE }`
- [ ] `THING-7.absent` — `Omit [ whose { sep whose } ]`
- [ ] `THING-7.present` — `Include [ whose { sep whose } ]`
- [ ] `THING-7-2.zero` — `Use zero occurrences of { sep whose }`
- [ ] `THING-7-2.one` — `Use one occurrence of { sep whose }`
- [ ] `THING-7-2.many` — `Use two or more occurrences of { sep whose }`

### `whose`

Encounter creation. Confirm each assigned property on the newly made thing, including chained clauses.

- [ ] `WHOSE` — `"whose" PROPERTY "is" whole`

### `adjective`

Battle. Change a move’s power across the threshold and observe the derived strong/weak condition flip.

- [ ] `ADJECTIVE` — `article KIND "is" ADJECTIVE "when" condition "."`

### `stored-adj`

Battle and badges. Mark or clear a stored fact and inspect the affected thing.

- [ ] `STORED-ADJ` — `article KIND "can be" ADJECTIVE "."`

### `property`

Battle inspector. Read the derived move rating and verify that it follows a power change.

- [ ] `PROPERTY` — `"The" NAME "of" article KIND "is" expression "."`

### `rule`

Shop and battle. Attempt both a legal and an illegal mutation and check the retained purse or HP.

- [ ] `RULE` — `article KIND "'s" PROPERTY "is" ( "never" | "always" ) tail "."`
- [ ] `RULE-6.1` — `"never"`
- [ ] `RULE-6.2` — `"always"`

### `verb`

Trainer actions. Invoke a verb through each taught shape and compare the destination and amount.

- [ ] `VERB` — `"To" VERB [ role ] { PREPOSITION role } ":"`
- [ ] `VERB-3.absent` — `Omit [ role ]`
- [ ] `VERB-3.present` — `Include [ role ]`
- [ ] `VERB-4.zero` — `Use zero occurrences of { PREPOSITION role }`
- [ ] `VERB-4.one` — `Use one occurrence of { PREPOSITION role }`
- [ ] `VERB-4.many` — `Use two or more occurrences of { PREPOSITION role }`

### `work-out`

Damage calculator and companion. Compare an ordinary block’s answer with a deterministic expected value and check each model-backed form using recorded listeners.

- [ ] `WORK-OUT` — `"To work out the" NAME "(" type ")" { ( PREPOSITION | "of" ) role } ( ":" | "," ( "ask the model" | "judge" | "grade" ) expression "." )`
- [ ] `WORK-OUT-6.zero` — `Use zero occurrences of { ( PREPOSITION | "of" ) role }`
- [ ] `WORK-OUT-6.one` — `Use one occurrence of { ( PREPOSITION | "of" ) role }`
- [ ] `WORK-OUT-6.many` — `Use two or more occurrences of { ( PREPOSITION | "of" ) role }`
- [ ] `WORK-OUT-6-1.1` — `PREPOSITION`
- [ ] `WORK-OUT-6-1.2` — `"of"`
- [ ] `WORK-OUT-7.1` — `":"`
- [ ] `WORK-OUT-7.2` — `"," ( "ask the model" | "judge" | "grade" ) expression "."`
- [ ] `WORK-OUT-7.2-2.1` — `"ask the model"`
- [ ] `WORK-OUT-7.2-2.2` — `"judge"`
- [ ] `WORK-OUT-7.2-2.3` — `"grade"`

### `reaction`

Party alerts. Trigger named and kind-wide transitions in both directions and count the callbacks.

- [ ] `REACTION` — `"Whenever" ( article KIND | THING ) "becomes" [ "not" ] ADJECTIVE ":"`
- [ ] `REACTION-2.1` — `article KIND`
- [ ] `REACTION-2.2` — `THING`
- [ ] `REACTION-4.absent` — `Omit [ "not" ]`
- [ ] `REACTION-4.present` — `Include [ "not" ]`

### `settled`

Canvas HUD. Compare the final displayed HP after a chain of reactions and kept values settles.

- [ ] `SETTLED` — `"Whenever everything has settled" ":"`

### `library`

Interface and Field Lab. Import and use the page library. Exercise Vulkan through the native lab entry.

- [ ] `LIBRARY` — `"Use the" NAME "library" "."`

### `chapter`

Journey. Load a sibling chapter and another book, then invoke a name from each.

- [ ] `CHAPTER` — `"Use the" WORDS "chapter" [ "of the" WORDS "book" ] "." ( WORDS: plain words, letters only )`
- [ ] `CHAPTER-4.absent` — `Omit [ "of the" WORDS "book" ]`
- [ ] `CHAPTER-4.present` — `Include [ "of the" WORDS "book" ]`

### `shares`

People and Journey. Check accessible exports and refusal of private names from a different chapter.

- [ ] `SHARES` — `"This chapter shares" ( "nothing" | "only" NAME { sep NAME } ) "."`
- [ ] `SHARES-2.1` — `"nothing"`
- [ ] `SHARES-2.2` — `"only" NAME { sep NAME }`
- [ ] `SHARES-2.2-3.zero` — `Use zero occurrences of { sep NAME }`
- [ ] `SHARES-2.2-3.one` — `Use one occurrence of { sep NAME }`
- [ ] `SHARES-2.2-3.many` — `Use two or more occurrences of { sep NAME }`

### `outside`

Page input and rendering binding. Exercise a supported external verb and an external worked-out value through their EnglishScript declarations. Refuse those declarations in ordinary game source.

- [ ] `OUTSIDE` — `( verb | work-out ) without its ":" , then "is done by the library" "."`
- [ ] `OUTSIDE-1.1` — `verb`
- [ ] `OUTSIDE-1.2` — `work-out`

### `role`

Battle verbs. Verify direct kind roles, named typed roles, and preposition-based reordering.

- [ ] `ROLE` — `article ( KIND | NAME "(" type ")" )`
- [ ] `ROLE-2.1` — `KIND`
- [ ] `ROLE-2.2` — `NAME "(" type ")"`

### `article`

Cast and Field Lab. Instantiate correctly named vowel- and consonant-initial kinds and inspect their types.

- [ ] `ARTICLE.1` — `"a"`
- [ ] `ARTICLE.2` — `"an"`

### `sep`

Shop items and encounter setup. Read the same field order for each allowed separator.

- [ ] `SEP.1` — `","`
- [ ] `SEP.2` — `"and"`
- [ ] `SEP.3` — `"," "and"`

### `type`

Party and inventory. Use concrete, optional-empty and proven-present values and compare their observable results.

- [ ] `TYPE` — `base-type [ "," "if any" ]`
- [ ] `TYPE-2.absent` — `Omit [ "," "if any" ]`
- [ ] `TYPE-2.present` — `Include [ "," "if any" ]`

### `base-type`

Battle, shop and journal. Assert values and display rules for every scalar, user kind, choice set and list type.

- [ ] `BASE-TYPE.1` — `"number"`
- [ ] `BASE-TYPE.2` — `"money"`
- [ ] `BASE-TYPE.3` — `"text"`
- [ ] `BASE-TYPE.4` — `"percent"`
- [ ] `BASE-TYPE.5` — `"yes or no"`
- [ ] `BASE-TYPE.6` — `KIND`
- [ ] `BASE-TYPE.7` — `CHOICE-SET`
- [ ] `BASE-TYPE.8` — `"list of" PLURAL-TYPE`

### `PLURAL-TYPE`

Party inspector. Construct each supported empty and populated item type and check list size or typed retrieval.

- [ ] `PLURAL-TYPE.1` — `"numbers"`
- [ ] `PLURAL-TYPE.2` — `"percentages"`
- [ ] `PLURAL-TYPE.3` — `"money"`
- [ ] `PLURAL-TYPE.4` — `"text"`
- [ ] `PLURAL-TYPE.5` — `KINDS`

### `action`

Journey and lab. Each action must change or read a game value, emit output, transfer control, or invoke a listener as specified.

- [ ] `ACTION.1` — `let`
- [ ] `ACTION.2` — `change`
- [ ] `ACTION.3` — `say`
- [ ] `ACTION.4` — `use`
- [ ] `ACTION.5` — `example`
- [ ] `ACTION.6` — `answer`
- [ ] `ACTION.7` — `leave`
- [ ] `ACTION.8` — `now`
- [ ] `ACTION.9` — `create`
- [ ] `ACTION.10` — `remove`
- [ ] `ACTION.11` — `ask`
- [ ] `ACTION.12` — `ask-model`
- [ ] `ACTION.13` — `judge`
- [ ] `ACTION.14` — `write`
- [ ] `ACTION.15` — `fail`

### `let`

Party and battle. Bind inferred, typed, fixed and optional values and a newly created move, then use each binding.

- [ ] `LET` — `"Let" [ "the" ] NAME [ "(" type ")" ] [ "always" ] "be" ( whole | new-thing ) "."`
- [ ] `LET-2.absent` — `Omit [ "the" ]`
- [ ] `LET-2.present` — `Include [ "the" ]`
- [ ] `LET-4.absent` — `Omit [ "(" type ")" ]`
- [ ] `LET-4.present` — `Include [ "(" type ")" ]`
- [ ] `LET-5.absent` — `Omit [ "always" ]`
- [ ] `LET-5.present` — `Include [ "always" ]`
- [ ] `LET-7.1` — `whole`
- [ ] `LET-7.2` — `new-thing`

### `whole`

Roster snapshot. Compare computed expressions, explicit lists and group snapshots after creating another encounter.

- [ ] `WHOLE.1` — `expression`
- [ ] `WHOLE.2` — `list-written`
- [ ] `WHOLE.3` — `group`

### `list-written`

Party editor. Assert item count, order and equality of the individual values for one-item, multiple-item and empty lists.

- [ ] `LIST-WRITTEN.1` — `"a list of" expression { "," expression } [ [ "," ] "and" expression ]`
- [ ] `LIST-WRITTEN.1-3.zero` — `Use zero occurrences of { "," expression }`
- [ ] `LIST-WRITTEN.1-3.one` — `Use one occurrence of { "," expression }`
- [ ] `LIST-WRITTEN.1-3.many` — `Use two or more occurrences of { "," expression }`
- [ ] `LIST-WRITTEN.1-4.absent` — `Omit [ [ "," ] "and" expression ]`
- [ ] `LIST-WRITTEN.1-4.present` — `Include [ [ "," ] "and" expression ]`
- [ ] `LIST-WRITTEN.1-4-1.absent` — `Omit [ "," ]`
- [ ] `LIST-WRITTEN.1-4-1.present` — `Include [ "," ]`
- [ ] `LIST-WRITTEN.2` — `"an empty list of" PLURAL-TYPE`

### `change`

Shop, HP and party order. Verify every arithmetic update as well as list element insertion, deletion and replacement.

- [ ] `CHANGE.1` — `"Set" target "to" whole "."`
- [ ] `CHANGE.2` — `"Set item" value "of" target "to" expression "."`
- [ ] `CHANGE.3` — `"Add" expression "to" target "."`
- [ ] `CHANGE.4` — `"Remove" expression "from" target "."`
- [ ] `CHANGE.5` — `"Subtract" expression "from" target "."`
- [ ] `CHANGE.6` — `"Multiply" target "by" expression "."`
- [ ] `CHANGE.7` — `"Divide" target "by" expression "."`

### `say`

Journal. Compare the captured text and interpolated values with an exact expected line.

- [ ] `SAY` — `"Say" expression "."`

### `use`

Trainer actions. Call verbs with and without a direct object and with zero, one or multiple linked arguments.

- [ ] `USE` — `VERB [ expression ] { PREPOSITION expression } "."`
- [ ] `USE-2.absent` — `Omit [ expression ]`
- [ ] `USE-2.present` — `Include [ expression ]`
- [ ] `USE-3.zero` — `Use zero occurrences of { PREPOSITION expression }`
- [ ] `USE-3.one` — `Use one occurrence of { PREPOSITION expression }`
- [ ] `USE-3.many` — `Use two or more occurrences of { PREPOSITION expression }`

### `example`

Lab. Assert an expected battle fact and deliberately fail a separate harness assertion to validate reporting.

- [ ] `EXAMPLE` — `"For example" [ "," ] condition "."`
- [ ] `EXAMPLE-2.absent` — `Omit [ "," ]`
- [ ] `EXAMPLE-2.present` — `Include [ "," ]`

### `answer`

Battle calculator. Compare the answer for a normal turn and for an early return.

- [ ] `ANSWER` — `"The answer is" whole "."`

### `leave`

Search, round control and replay shutdown. Confirm precisely which item, loop, verb or program stops executing.

- [ ] `LEAVE.1` — `"Stop."`
- [ ] `LEAVE.2` — `"Stop repeating."`
- [ ] `LEAVE.3` — `"Skip this" NOUN "."`
- [ ] `LEAVE.4` — `"Skip this round."`
- [ ] `LEAVE.5` — `"End the program."`

### `target`

Damage and budget. Update a local variable and a stored field. Compare the owner and committed value.

- [ ] `TARGET.1` — `a variable made with Let`
- [ ] `TARGET.2` — `a stored property of a thing`

### `now`

Turn state. Toggle a stored mark in each direction and inspect its effect on a reaction.

- [ ] `NOW` — `"Now" expression "is" [ "not" ] ADJECTIVE "."`
- [ ] `NOW-4.absent` — `Omit [ "not" ]`
- [ ] `NOW-4.present` — `Include [ "not" ]`

### `create`

Wild encounter. Compare world counts and encounter fields before and after creation.

- [ ] `CREATE` — `"There is" new-thing "."`

### `new-thing`

Wild encounter. Make unnamed/named things with varying marks and fields. Check lookup and creation order.

- [ ] `NEW-THING` — `article "new" { ADJECTIVE } KIND [ "called" expression ] [ whose { sep whose } ]`
- [ ] `NEW-THING-3.zero` — `Use zero occurrences of { ADJECTIVE }`
- [ ] `NEW-THING-3.one` — `Use one occurrence of { ADJECTIVE }`
- [ ] `NEW-THING-3.many` — `Use two or more occurrences of { ADJECTIVE }`
- [ ] `NEW-THING-5.absent` — `Omit [ "called" expression ]`
- [ ] `NEW-THING-5.present` — `Include [ "called" expression ]`
- [ ] `NEW-THING-6.absent` — `Omit [ whose { sep whose } ]`
- [ ] `NEW-THING-6.present` — `Include [ whose { sep whose } ]`
- [ ] `NEW-THING-6-2.zero` — `Use zero occurrences of { sep whose }`
- [ ] `NEW-THING-6-2.one` — `Use one occurrence of { sep whose }`
- [ ] `NEW-THING-6-2.many` — `Use two or more occurrences of { sep whose }`

### `remove`

Despawn. Confirm removal from the world and required lists and refusal of invalid live references.

- [ ] `REMOVE` — `"Remove" expression "."`

### `ask`

Player input. Script valid replies and invalid-then-valid retries for each supported human reply type. Check the bound value.

- [ ] `ASK` — `"Ask" expression "and let" [ "the" ] NAME "(" type ")" "be the reply" "."`
- [ ] `ASK-4.absent` — `Omit [ "the" ]`
- [ ] `ASK-4.present` — `Include [ "the" ]`

### `model-state`

Companion. Compare captures for literal text, a serialized thing and an image generated from the procedural canvas.

- [ ] `MODEL-STATE.1` — `expression`
- [ ] `MODEL-STATE.2` — `"the image in the file" value`

### `ask-model`

GPT-6 Luna. Check the recorded question, state, expected shape and result binding. Exercise absence and presence of about.

- [ ] `ASK-MODEL` — `"Ask the model" expression [ "about" model-state ] "and let" [ "the" ] NAME "(" type ")" "be the reply" "."`
- [ ] `ASK-MODEL-3.absent` — `Omit [ "about" model-state ]`
- [ ] `ASK-MODEL-3.present` — `Include [ "about" model-state ]`
- [ ] `ASK-MODEL-5.absent` — `Omit [ "the" ]`
- [ ] `ASK-MODEL-5.present` — `Include [ "the" ]`

### `judge`

Jev. Compare chance, verdict, grade and optional likelihood with known scores, including a case where verdict and grade differ.

- [ ] `JUDGE` — `"Judge" expression "about" model-state "and let" [ "the" ] NAME ( "(" "percent" ")" "be the chance" | "(" CHOICE-SET ")" ( "be the verdict" | "be the grade" ) [ "and" [ "the" ] NAME "(" "percent" ")" "be the likelihood" ] ) "."`
- [ ] `JUDGE-6.absent` — `Omit [ "the" ]`
- [ ] `JUDGE-6.present` — `Include [ "the" ]`
- [ ] `JUDGE-8.1` — `"(" "percent" ")" "be the chance"`
- [ ] `JUDGE-8.2` — `"(" CHOICE-SET ")" ( "be the verdict" | "be the grade" ) [ "and" [ "the" ] NAME "(" "percent" ")" "be the likelihood" ]`
- [ ] `JUDGE-8.2-4.1` — `"be the verdict"`
- [ ] `JUDGE-8.2-4.2` — `"be the grade"`
- [ ] `JUDGE-8.2-5.absent` — `Omit [ "and" [ "the" ] NAME "(" "percent" ")" "be the likelihood" ]`
- [ ] `JUDGE-8.2-5.present` — `Include [ "and" [ "the" ] NAME "(" "percent" ")" "be the likelihood" ]`
- [ ] `JUDGE-8.2-5-2.absent` — `Omit [ "the" ]`
- [ ] `JUDGE-8.2-5-2.present` — `Include [ "the" ]`

### `write`

Save journal. Write, append, read text, and read lines in an isolated save folder. Verify the bytes or decoded values.

- [ ] `WRITE` — `( "Write" | "Add" ) expression "to the file" value "."`
- [ ] `WRITE-1.1` — `"Write"`
- [ ] `WRITE-1.2` — `"Add"`

### `fail`

Purchase and chat recovery. Check the original typed problem survives a rethrow and world changes roll back.

- [ ] `FAIL.1` — `"Fail because" expression "."`
- [ ] `FAIL.2` — `"Fail again."`

### `block-opener`

Journey sequences and rollback. Take every branch, visit loops with zero and multiple items, and check exception and cleanup paths.

- [ ] `BLOCK-OPENER.1` — `"If" condition ":"`
- [ ] `BLOCK-OPENER.2` — `"Otherwise if" condition ":"`
- [ ] `BLOCK-OPENER.3` — `"Otherwise" ":"`
- [ ] `BLOCK-OPENER.4` — `"For each" { ADJECTIVE } KIND [ "of" value ] [ filter ] ":"`
- [ ] `BLOCK-OPENER.4-2.zero` — `Use zero occurrences of { ADJECTIVE }`
- [ ] `BLOCK-OPENER.4-2.one` — `Use one occurrence of { ADJECTIVE }`
- [ ] `BLOCK-OPENER.4-2.many` — `Use two or more occurrences of { ADJECTIVE }`
- [ ] `BLOCK-OPENER.4-4.absent` — `Omit [ "of" value ]`
- [ ] `BLOCK-OPENER.4-4.present` — `Include [ "of" value ]`
- [ ] `BLOCK-OPENER.4-5.absent` — `Omit [ filter ]`
- [ ] `BLOCK-OPENER.4-5.present` — `Include [ filter ]`
- [ ] `BLOCK-OPENER.5` — `"For each" NAME "in" ( group | expression ) ":"`
- [ ] `BLOCK-OPENER.5-4.1` — `group`
- [ ] `BLOCK-OPENER.5-4.2` — `expression`
- [ ] `BLOCK-OPENER.6` — `"Repeat" expression "times" ":"`
- [ ] `BLOCK-OPENER.7` — `"While" condition ":"`
- [ ] `BLOCK-OPENER.8` — `"Try" ":"`
- [ ] `BLOCK-OPENER.9` — `"If that fails" ":"`
- [ ] `BLOCK-OPENER.10` — `"Either way" ":"`

### `condition`

Eligibility tests. Exercise single and multiple operands with actual short-circuit behavior.

- [ ] `CONDITION.1` — `test { "and" test }`
- [ ] `CONDITION.1-2.zero` — `Use zero occurrences of { "and" test }`
- [ ] `CONDITION.1-2.one` — `Use one occurrence of { "and" test }`
- [ ] `CONDITION.1-2.many` — `Use two or more occurrences of { "and" test }`
- [ ] `CONDITION.2` — `test { "or" test }`
- [ ] `CONDITION.2-2.zero` — `Use zero occurrences of { "or" test }`
- [ ] `CONDITION.2-2.one` — `Use one occurrence of { "or" test }`
- [ ] `CONDITION.2-2.many` — `Use two or more occurrences of { "or" test }`

### `test`

Readiness and recovery. Verify positive and negative predicates, brackets, and all typed problem branches.

- [ ] `TEST.1` — `"not" test`
- [ ] `TEST.2` — `"(" condition ")"`
- [ ] `TEST.3` — `expression comparison`
- [ ] `TEST.4` — `"the problem is" [ "not" ] ( article PROBLEM-KIND | "no model" )`
- [ ] `TEST.4-2.absent` — `Omit [ "not" ]`
- [ ] `TEST.4-2.present` — `Include [ "not" ]`
- [ ] `TEST.4-3.1` — `article PROBLEM-KIND`
- [ ] `TEST.4-3.2` — `"no model"`

### `comparison`

Battle decisions and journal search. Verify boolean results for each comparison spelling, including a boundary or false result.

- [ ] `COMPARISON.1` — `( "is" | "are" ) [ "not" ] tail`
- [ ] `COMPARISON.1-1.1` — `"is"`
- [ ] `COMPARISON.1-1.2` — `"are"`
- [ ] `COMPARISON.1-2.absent` — `Omit [ "not" ]`
- [ ] `COMPARISON.1-2.present` — `Include [ "not" ]`
- [ ] `COMPARISON.2` — `"has" article PROPERTY`
- [ ] `COMPARISON.3` — `"has no" PROPERTY`
- [ ] `COMPARISON.4` — `( "=" | "<" | ">" | "<=" | ">=" ) expression`
- [ ] `COMPARISON.4-1.1` — `"="`
- [ ] `COMPARISON.4-1.2` — `"<"`
- [ ] `COMPARISON.4-1.3` — `">"`
- [ ] `COMPARISON.4-1.4` — `"<="`
- [ ] `COMPARISON.4-1.5` — `">="`
- [ ] `COMPARISON.5` — `( "contains" | "starts with" | "ends with" | "comes before" | "comes after" ) expression`
- [ ] `COMPARISON.5-1.1` — `"contains"`
- [ ] `COMPARISON.5-1.2` — `"starts with"`
- [ ] `COMPARISON.5-1.3` — `"ends with"`
- [ ] `COMPARISON.5-1.4` — `"comes before"`
- [ ] `COMPARISON.5-1.5` — `"comes after"`
- [ ] `COMPARISON.6` — `( "does not contain" | "does not start with" | "does not end with" ) expression`
- [ ] `COMPARISON.6-1.1` — `"does not contain"`
- [ ] `COMPARISON.6-1.2` — `"does not start with"`
- [ ] `COMPARISON.6-1.3` — `"does not end with"`

### `tail`

Damage, inventory and party membership. Verify thresholds, divisibility, absence, adjective tests, and equality.

- [ ] `TAIL.1` — `"less than" expression`
- [ ] `TAIL.2` — `"more than" expression`
- [ ] `TAIL.3` — `"greater than" expression`
- [ ] `TAIL.4` — `"at least" expression`
- [ ] `TAIL.5` — `"at most" expression`
- [ ] `TAIL.6` — `"divisible by" expression`
- [ ] `TAIL.7` — `"nothing"`
- [ ] `TAIL.8` — `ADJECTIVE`
- [ ] `TAIL.9` — `"in" value`
- [ ] `TAIL.10` — `expression`

### `expression`

Optional held values. Force both the present value and the stand-in path.

- [ ] `EXPRESSION` — `sum { "or else" sum }`
- [ ] `EXPRESSION-2.zero` — `Use zero occurrences of { "or else" sum }`
- [ ] `EXPRESSION-2.one` — `Use one occurrence of { "or else" sum }`
- [ ] `EXPRESSION-2.many` — `Use two or more occurrences of { "or else" sum }`

### `sum`

Battle arithmetic. Check operator spelling, chained operations and left-to-right subtraction.

- [ ] `SUM` — `term { ( "+" | "plus" | "-" | "minus" ) term }`
- [ ] `SUM-2.zero` — `Use zero occurrences of { ( "+" | "plus" | "-" | "minus" ) term }`
- [ ] `SUM-2.one` — `Use one occurrence of { ( "+" | "plus" | "-" | "minus" ) term }`
- [ ] `SUM-2.many` — `Use two or more occurrences of { ( "+" | "plus" | "-" | "minus" ) term }`
- [ ] `SUM-2-1.1` — `"+"`
- [ ] `SUM-2-1.2` — `"plus"`
- [ ] `SUM-2-1.3` — `"-"`
- [ ] `SUM-2-1.4` — `"minus"`

### `term`

Damage arithmetic. Check both spellings of multiply/divide, chained operations and precedence.

- [ ] `TERM` — `factor { ( "*" | "times" | "/" | "divided by" ) factor }`
- [ ] `TERM-2.zero` — `Use zero occurrences of { ( "*" | "times" | "/" | "divided by" ) factor }`
- [ ] `TERM-2.one` — `Use one occurrence of { ( "*" | "times" | "/" | "divided by" ) factor }`
- [ ] `TERM-2.many` — `Use two or more occurrences of { ( "*" | "times" | "/" | "divided by" ) factor }`
- [ ] `TERM-2-1.1` — `"*"`
- [ ] `TERM-2-1.2` — `"times"`
- [ ] `TERM-2-1.3` — `"/"`
- [ ] `TERM-2-1.4` — `"divided by"`

### `factor`

Damage modifiers. Verify signed values, percentage-of binding, postfixes, and brackets.

- [ ] `FACTOR.1` — `"-" factor`
- [ ] `FACTOR.2` — `value { postfix } [ "of" factor ]`
- [ ] `FACTOR.2-2.zero` — `Use zero occurrences of { postfix }`
- [ ] `FACTOR.2-2.one` — `Use one occurrence of { postfix }`
- [ ] `FACTOR.2-2.many` — `Use two or more occurrences of { postfix }`
- [ ] `FACTOR.2-3.absent` — `Omit [ "of" factor ]`
- [ ] `FACTOR.2-3.present` — `Include [ "of" factor ]`

### `postfix`

Score display and journal. Verify conversion, joining, case, rounding in each direction and exponentiation.

- [ ] `POSTFIX.1` — `"in upper case"`
- [ ] `POSTFIX.2` — `"in lower case"`
- [ ] `POSTFIX.3` — `"as a number"`
- [ ] `POSTFIX.4` — `"joined with" value`
- [ ] `POSTFIX.5` — `"rounded" [ "up" | "down" ] "to the nearest" value`
- [ ] `POSTFIX.5-2.absent` — `Omit [ "up" | "down" ]`
- [ ] `POSTFIX.5-2.present` — `Include [ "up" | "down" ]`
- [ ] `POSTFIX.5-2.1` — `"up"`
- [ ] `POSTFIX.5-2.2` — `"down"`
- [ ] `POSTFIX.6` — `"raised to the power of" value`

### `value`

Battle calculator, Pokédex and roster inspector. Compare actual values, lists, owner identities or problem text for each listed form.

- [ ] `VALUE.1` — `NUMBER`
- [ ] `VALUE.2` — `MONEY`
- [ ] `VALUE.3` — `PERCENT`
- [ ] `VALUE.4` — `TEXT`
- [ ] `VALUE.5` — `"(" expression ")"`
- [ ] `VALUE.6` — `"nothing"`
- [ ] `VALUE.7` — `"-" value`
- [ ] `VALUE.8` — `CHOICE`
- [ ] `VALUE.9` — `"the remainder of" value "divided by" value`
- [ ] `VALUE.10` — `"the square root of" value`
- [ ] `VALUE.11` — `"the" ( "larger" | "smaller" ) "of" value "and" value`
- [ ] `VALUE.11-2.1` — `"larger"`
- [ ] `VALUE.11-2.2` — `"smaller"`
- [ ] `VALUE.12` — `"the absolute value of" value`
- [ ] `VALUE.13` — `"letter" value "of" value`
- [ ] `VALUE.14` — `"yes"`
- [ ] `VALUE.15` — `"no"`
- [ ] `VALUE.16` — `"whether" test`
- [ ] `VALUE.17` — `"the" WORKED-OUT { ( PREPOSITION | "of" ) value }`
- [ ] `VALUE.17-3.zero` — `Use zero occurrences of { ( PREPOSITION | "of" ) value }`
- [ ] `VALUE.17-3.one` — `Use one occurrence of { ( PREPOSITION | "of" ) value }`
- [ ] `VALUE.17-3.many` — `Use two or more occurrences of { ( PREPOSITION | "of" ) value }`
- [ ] `VALUE.17-3-1.1` — `PREPOSITION`
- [ ] `VALUE.17-3-1.2` — `"of"`
- [ ] `VALUE.18` — `THING`
- [ ] `VALUE.19` — `[ "the" ] VARIABLE`
- [ ] `VALUE.19-1.absent` — `Omit [ "the" ]`
- [ ] `VALUE.19-1.present` — `Include [ "the" ]`
- [ ] `VALUE.20` — `[ "the" ] NOUN-IN-VIEW`
- [ ] `VALUE.20-1.absent` — `Omit [ "the" ]`
- [ ] `VALUE.20-1.present` — `Include [ "the" ]`
- [ ] `VALUE.21` — `"it"`
- [ ] `VALUE.22` — `"they"`
- [ ] `VALUE.23` — `"them"`
- [ ] `VALUE.24` — `( "its" | "their" ) PROPERTY`
- [ ] `VALUE.24-1.1` — `"its"`
- [ ] `VALUE.24-1.2` — `"their"`
- [ ] `VALUE.25` — `value "'s" PROPERTY`
- [ ] `VALUE.26` — `"the" PROPERTY "of" value`
- [ ] `VALUE.27` — `"the number of" group`
- [ ] `VALUE.28` — `"the total" PROPERTY "of" group`
- [ ] `VALUE.29` — `"the number of items in" value`
- [ ] `VALUE.30` — `"item" value "of" value`
- [ ] `VALUE.31` — `"the" ( "first" | "last" | "total" ) "of" value`
- [ ] `VALUE.31-2.1` — `"first"`
- [ ] `VALUE.31-2.2` — `"last"`
- [ ] `VALUE.31-2.3` — `"total"`
- [ ] `VALUE.32` — `"the" ( "length" | "words" | "lines" ) "of" value`
- [ ] `VALUE.32-2.1` — `"length"`
- [ ] `VALUE.32-2.2` — `"words"`
- [ ] `VALUE.32-2.3` — `"lines"`
- [ ] `VALUE.33` — `"the" ( "first" | "last" ) factor "letters of" value`
- [ ] `VALUE.33-2.1` — `"first"`
- [ ] `VALUE.33-2.2` — `"last"`
- [ ] `VALUE.34` — `"the" ( "text" | "lines" ) "of the file" value`
- [ ] `VALUE.34-2.1` — `"text"`
- [ ] `VALUE.34-2.2` — `"lines"`
- [ ] `VALUE.35` — `"the" KIND "called" value`
- [ ] `VALUE.36` — `"the problem"`

### `group`

Roster. Compare identities and creation order across plain, qualified, owned and filtered groups.

- [ ] `GROUP.1` — `[ "all" ] { ADJECTIVE } KINDS [ "of" value ] [ filter ]`
- [ ] `GROUP.1-1.absent` — `Omit [ "all" ]`
- [ ] `GROUP.1-1.present` — `Include [ "all" ]`
- [ ] `GROUP.1-2.zero` — `Use zero occurrences of { ADJECTIVE }`
- [ ] `GROUP.1-2.one` — `Use one occurrence of { ADJECTIVE }`
- [ ] `GROUP.1-2.many` — `Use two or more occurrences of { ADJECTIVE }`
- [ ] `GROUP.1-4.absent` — `Omit [ "of" value ]`
- [ ] `GROUP.1-4.present` — `Include [ "of" value ]`
- [ ] `GROUP.1-5.absent` — `Omit [ filter ]`
- [ ] `GROUP.1-5.present` — `Include [ filter ]`
- [ ] `GROUP.2` — `( "its" | "their" ) { ADJECTIVE } KINDS [ filter ]`
- [ ] `GROUP.2-1.1` — `"its"`
- [ ] `GROUP.2-1.2` — `"their"`
- [ ] `GROUP.2-2.zero` — `Use zero occurrences of { ADJECTIVE }`
- [ ] `GROUP.2-2.one` — `Use one occurrence of { ADJECTIVE }`
- [ ] `GROUP.2-2.many` — `Use two or more occurrences of { ADJECTIVE }`
- [ ] `GROUP.2-4.absent` — `Omit [ filter ]`
- [ ] `GROUP.2-4.present` — `Include [ filter ]`
- [ ] `GROUP.3` — `value "'s" { ADJECTIVE } KINDS [ filter ]`
- [ ] `GROUP.3-3.zero` — `Use zero occurrences of { ADJECTIVE }`
- [ ] `GROUP.3-3.one` — `Use one occurrence of { ADJECTIVE }`
- [ ] `GROUP.3-3.many` — `Use two or more occurrences of { ADJECTIVE }`
- [ ] `GROUP.3-5.absent` — `Omit [ filter ]`
- [ ] `GROUP.3-5.present` — `Include [ filter ]`

### `filter`

Encounter search. Compare the identities after one and multiple filters, including a nonmatching item.

- [ ] `FILTER` — `"whose" PROPERTY comparison { "and whose" PROPERTY comparison }`
- [ ] `FILTER-4.zero` — `Use zero occurrences of { "and whose" PROPERTY comparison }`
- [ ] `FILTER-4.one` — `Use one occurrence of { "and whose" PROPERTY comparison }`
- [ ] `FILTER-4.many` — `Use two or more occurrences of { "and whose" PROPERTY comparison }`

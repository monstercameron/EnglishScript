# Boulder Badge · The standard library and its diagnostics

**Review proposal.** Use the game to build a standard library someone could use in a different EnglishScript program. Each public operation should answer four questions. What English sentence calls it? What does it return or change? Which failures can the caller handle? What does the author see when a sentence fails? Review those answers with the first working example of the operation.

## Start with two reproduced failures

Both baseline failures below have regressions in the working checkout. The [library dispatch tests](../../tests/test_englishscript.py) exercise catchable kinds through an English handler. The [playground position test](../../tests/test_playground_positions.py) checks that the highlighted text and selection agree.

| Baseline at `acf28a2` | First acceptance test |
|---|---|
| Section 8.5 says a library can report an existing problem kind. I ran an English program using the compiler test suite’s paint library. Its host verb raised a recoverable error with the `missing_item` rule. The handler answered **no** to `the problem is a missing item` and **yes** to `the problem is a library problem`. The original text survived. `call_library` preserves a hand-written subset of the known rules. | The same handler recognizes `a missing item`. Check every documented kind at the library boundary, an ordinary library-reported problem, an explicit `Fail because`, and an unexpected host exception. The last one remains fatal. [Library dispatch](https://github.com/monstercameron/EnglishScript/blob/acf28a2/englishscript/compiler.py) · [Language contract, §8.5](https://github.com/monstercameron/EnglishScript/blob/acf28a2/docs/SYNTAX.md#85-recovering-from-a-problem) |
| For `Say "🐾 {the unknown}"`, the linter locates `unknown` at column 12, counting Unicode code points from zero. The playground’s selection function uses that as a UTF-16 offset. Running the shipped function selected the preceding space and the first six letters, leaving the last letter out. | The underline, click-to-select action and editor diagnostic all identify exactly `unknown`. Repeat after an accented letter, an emoji, on an indented line, at end of line, and in an imported chapter. [Playground](https://github.com/monstercameron/EnglishScript/blob/acf28a2/docs/playground.html) · [Editor position handling](https://github.com/monstercameron/EnglishScript/blob/acf28a2/englishscript/server.py) |

## Which problems deserve an English name?

Today the language has **12 catchable kinds**: broken rule, division by zero, missing file, refused removal, removed thing, bad count, missing item, bad number, bad reply, no model, library problem and failure. Preserve their spellings, including `the problem is no model`, and test all twelve. `the problem` returns the message as text. `Fail again.` passes the original kind and text to the outer handler. Keep the documented message templates that existing programs can print or compare. [Problem names and rendering](https://github.com/monstercameron/EnglishScript/blob/acf28a2/englishscript/lexer.py) · [Language contract](https://github.com/monstercameron/EnglishScript/blob/acf28a2/docs/SYNTAX.md#85-recovering-from-a-problem)

Give a failure a stable diagnostic identifier for tools. Give it a distinct **catchable English kind** when a caller needs to take a different action. Keep compilation errors, authoring suggestions, recoverable runtime problems and fatal faults distinct. A library defect or failed `For example` assertion must still escape a `Try`. The catalog should record the identifier, existing teaching rule, catchable spelling if applicable, example, recovery action, and owning operation. The compiler, documentation and editor should consume the same public list.

| Situation to exercise | Proposed contract | Boulder Badge example |
|---|---|---|
| Missing input or unusable model reply | Retain `no model` for an absent listener and `a bad reply` for an unusable answer. Give typed-answer failures and a listener-reported service error distinct diagnostic IDs where the adapter can tell them apart. | Disconnect Luna, then supply an invalid typed reply through a test listener. Check each handler, retry count, and persona-specific fallback. |
| Expired deadline | Propose `a time limit` for the new deadline operation. A caught deadline runs cleanup once. Closing a conversation normally retires its requests silently. | Leave Oak’s chat open until the deadline, then repeat while closing it first. Only the first run shows a timeout. Neither can alter the next speaker. |
| Storage missing, denied, full or corrupt | Keep the current file kind and optional preference-read behavior compatible. A new checkpoint read returns an absent value for an empty slot. New checkpoint operations distinguish access denial, exhausted space and invalid data. Start with specific IDs under `a library problem`. Where English must branch, propose a typed status or catchable kind before exposing the operation. | An empty slot starts a new game. A rejected write leaves the previous checkpoint usable and the companion reports it. A corrupt newest checkpoint tries the previous one. Test a denied read independently of a missing entry. |
| Capability unavailable or implementation broken | An expected lack of a device or optional compute worker has a named operation, an actionable message and a documented fallback. A wrong return type or unexpected exception in a binding is a fatal library fault. | Run a Field Lab comparison without a compute worker and report serial execution. Inject a wrong result type and verify the fault names the binding and the English call site. |

## What an error should look like

Build on the existing `EnglishError.render`, `mark` and linter `Problem`. Keep the public lint JSON’s existing field meanings, including `kind` for error or warning. Add a versioned or opt-in richer record for diagnostic ID, runtime problem kind, recovery disposition, source span, related locations and a certain fix. An uncaught worker failure should carry this record and the originating English call site across the message boundary. Renderers must never have to parse a formatted English paragraph to recover the kind. [Linter interface](https://github.com/monstercameron/EnglishScript/blob/acf28a2/englishscript/linter.py) · [Browser microarchitecture](EnglishScript%20-%20Browser%20microarchitecture.md)

Give every span a source file or library ID, one-based start and end lines, and zero-based Unicode code-point columns. The end is exclusive. Treat CRLF as one line break. A location can identify a whole line when the exact column is unknown. Carry these coordinates unchanged through workers. Each browser or editor adapter converts them once to its native offsets. Test a range spanning two CRLF lines with an emoji before the offending word and verify selection and fixes in the correct document.

For an author, name the chapter and line, show the original sentence, underline the smallest useful span, say what happened in plain English, and give one useful next action. The existing CLI already does this for `Say the dragon.` by underlining `dragon`, explaining that no earlier sentence defined it, and showing how to introduce it. Preserve that voice. Offer an automatic edit only when the replacement is certain. Show both locations for an imported definition or asynchronous call when both explain the failure. Render suggestions distinctly and keep machine identifiers available in details.

The current formatter produces this mark. Use it as a reference for spacing, caret width and the section citation.

```text
Vocabulary (Lab.english, line 1):

    Say the dragon.
            ^^^^^^

  I don't know "the dragon": no sentence before this one has made it.
  Make it first, with a sentence such as: Let the dragon be ....
  The rule: a variable is made with "Let" before it is used. (See section 7.1.)
```

For a player, explain the consequence and available action in the companion. For example, **“This browser couldn’t keep your latest checkpoint. You can keep playing. Your previous checkpoint is still available.”** Show that last sentence only after confirming a previous checkpoint exists. Keep diagnostics outside the cartridge canvas. Never include provider credentials, request headers or raw service responses in public messages, fixtures or saved replays.

## What belongs in the standard library

| Surface | Reusable contract to grow | Game-specific work stays in English books |
|---|---|---|
| Page and canvas | Extend the shipped page library with a persistent canvas, batched pixel operations, events and teardown. Specify dimensions, value bounds, ownership and host support. | Glyphs, tiles, poses, palettes, menus and map drawing procedures. |
| Audio | Define timestamped channel changes, device lifecycle and an offline event sink. Distinguish a suspended device from invalid input. | Notes, envelopes, cries and battle cues. |
| Files, preferences and session storage | Document which operations return an optional value, which can fail, what persists after a failed `Try`, and how to detect a failed checkpoint write. | Save schema, named slots, migration and NPC memories. |
| Time, workers and model adapters | Put waits, joins, typed replies and cancellation semantics in the language/runtime. Bind clocks, job execution and model transport through replaceable host adapters. | Battle previews, persona prompts, turn choices and replay policy. |
| Math, text, collections and Vulkan | Inventory existing operations before adding primitives. Give shared operations a normal English consumer, boundary cases and named failures. Keep the shipped Vulkan library available in its supported desktop environment. | Damage tables, type matchups, item names, party ordering and desktop Field Lab scenes. |

For admission, write a small non-game `.english` example alongside the game consumer. Specify arguments, result, units and accepted ranges, side effects, whether it can suspend, supported hosts and failure behavior. Exercise shipped libraries through the existing `Use`, `SOURCE`, host verb/value and lifecycle contracts. Include an unavailable-host test, cleanup on success and on failure, and a comparison of world state with external effects after rollback. For instance, a failed `Try` can restore the party while a file already written stays written. [Library authoring interface](https://github.com/monstercameron/EnglishScript/blob/acf28a2/englishscript/libraries/__init__.py) · [Page storage](https://github.com/monstercameron/EnglishScript/blob/acf28a2/docs/PAGE.md#remembering)

## Release evidence

1. Freeze the 12 public spellings, documented message templates and recovery semantics, plus the legacy lint JSON shape. The two opening regressions pass when the handler sees `a missing item` and the playground selects the whole word `unknown`. For each new ID, record a fixture that actually triggers it and the expected severity, kind, recovery, message and source span.
2. Run representative fixtures across the normal CLI, lint JSON, playground and editor wherever each supports the stage. For runtime cases include the headless runner and browser worker. Check exact output for representative human-facing layouts, structured fields for every ID, and the target text and file for every suggested edit.
3. Exercise a rule failure during a purchase, a missing item in the Field Lab, a failed checkpoint and a delayed model request. Check rollback, retained external effects, exactly-once cleanup, and the first failing call site through rethrow. Compare the subsequent game state and frame with the reference after recovery.
4. Publish counts for public operations with passing contract tests, catchable kinds exercised, fatal paths verified, renderer fixtures passed and open gaps. A library operation counts as complete when its success path, failure behavior and documented host support have all been demonstrated.

**Baseline verification.** The 48 existing tests selected for problem kinds, recovery, library boundaries, diagnostic formatting, editor positions, diagnostics and quick fixes passed. Separate probes reproduced both gaps above. The proposed contracts and new release gates await implementation.

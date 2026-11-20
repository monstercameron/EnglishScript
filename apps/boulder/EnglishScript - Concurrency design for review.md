# EnglishScript concurrency · Design for review

**Scope** · Proposed compiler and runtime behavior for the Boulder Badge benchmark. The Desktop compiler is at `acf28a2`. All concurrency sentences on this page are design examples. The arithmetic body and ordinary actions use existing EnglishScript. The §12 forms come from the language reference. Wording for workers, task ownership, deadlines and races is a review proposal.

## Three game moments that need different behavior

| Moment | Contract | How the test could fail |
|---|---|---|
| The player is moving when a companion question reaches GPT‑6 Luna | The model call suspends its strand. Input, frame production, audio scheduling and other eligible strands keep running. | The main thread blocks on HTTP. Canvas frames stop, queued inputs apply late, or the game’s RNG advances according to network latency. |
| The player closes Oak’s conversation and speaks to the rival | Closing invalidates the conversation generation and cancels its owned task. A late response can never change the new conversation or campaign. | The old reply lands in the rival’s DOM field, or resuming twice triggers a duplicate action. |
| Oak’s Field Lab compares independent damage previews | The compiler proves the calculation is safe to run away from the world. Multiple workers can evaluate snapshots concurrently. The parent observes typed results in deterministic order. | “Parallel” is implemented as a sequential loop, a worker modifies live HP, or completion order changes the chosen move. |

One clock drives the cartridge, including its timer and RNG. The host uses a monotonic clock for live timeouts and device scheduling. In a replay, a virtual host clock and a timestamped external-input log reproduce those outside events. A browser frame callback presents the latest completed game frame. Each frame must stay independent of Jev, Luna and worker completion order.

## A. Structured strands in the current proposal

```text
At the same time:
  Wait 2 seconds.
  Wait 3 seconds.
Say "Ready."
```

Each direct statement starts one strand. In a virtual-clock test, “Ready.” occurs after three seconds. A sequential version takes five. Extend the fixture to verbs that report before and after waiting. For unequal wait lengths ending at the same virtual tick, the strand that has waited longest resumes first. A separate pair with equal waits verifies the source-order tie break.

| Form | Acceptance cases |
|---|---|
| Time values and arithmetic | Singular and plural seconds, minutes and hours, decimal literals, time variables, number × time in either order, time ÷ time, time ÷ number, addition, subtraction and comparisons. Specify zero and negative durations. Proposed default is an immediate scheduling point for a zero wait, a recoverable bad duration for a negative wait, and a strictly positive period for a repeating timer. |
| `Wait <time>.` | Suspend only the current strand. A verb that calls a waiting verb suspends transitively and resumes exactly once. A zero-duration loop must still yield fairly at the same virtual tick. |
| `Wait until <condition>.` | Return immediately when true. Recheck when its dependencies change. A pending input, timer, model or worker completion can make progress. Report genuine deadlock with source locations when there is no possible wake source. |
| `At the same time:` | Join all direct children. Test nested joins and a child that leaves its verb early. Refuse a direct `Let` with no usable lifetime. Preserve each strand’s local nouns, pronouns and variables. |
| `For each … at the same time:` | Start one strand per selected thing, in stable source-world order. Test zero, one and many, filtered/owned groups, distinct owners and aliases. |
| `Every <time> until <condition>:` | Wait first, then test, then run. Test an initially true condition, repeated ticks, a body that takes time, `Stop repeating.` and `Skip this round.` Use the reference’s wait-after-body sequencing. |
| Compile-time conflict analysis | Follow reads and changes through verbs, aliases, groups, create/remove, list edits, reactions and kept values. Refuse a sibling’s read/write or write/write conflict before any effect. Accept disjoint objects the compiler can distinguish. Exercise the narrow additive exception on numeric targets with no conflicting readers or target rule. |

**Rollback across suspension.** The compiler currently compiles sentences to synchronous Python callables. Introduce resumable execution in the normal block, verb, reaction and error-handling paths. Preserve the public synchronous API for existing callers. A suspended `Try` needs a strand-local change journal. If two strands are allowed to add to one counter, a failed strand must reverse its own delta while preserving the successful strand’s contribution. Also journal or stage indirect reaction and kept-value changes. Preserve the existing treatment of irreversible effects such as output and file writes. Test mixed rollback, including a successful sibling’s contribution. Publish the order for sibling cancellation, cleanup and error propagation when one child fails. Proposed default is cancel unfinished siblings, run their cleanups once, and propagate the first ordered failure to the parent.

## B. Actual CPU workers

Proposed source for a pure background calculation:

```text
To work out the damage (number) of a power (number):
  The answer is 2 * the power.

On a worker, work out the damage of 4 and let the score (number) be the result.
For example the score is 8.
```

This sentence yields until the typed answer is available. To overlap two calculations, use it inside separate verbs called by an `At the same time:` block, with strand-local output or provably disjoint destinations. A sequential caller still gets a correctly typed value. A background task that should outlive its caller uses the explicit task form below.

- **Compiler guarantee.** Check the entire call graph for worker safety. The first payload types are numbers, money, percentages, text, yes/no, choices and immutable copies of supported lists. Copy approved value snapshots before dispatch. Reject a live world object, DOM access, file reads, model calls, hidden mutable globals, clock reads, nested waits and untracked library effects. Ordinary `To work out` currently permits some external reads, so its existing purity check is insufficient.
- **Execution.** On desktop, use a bounded native thread pool for operations that can execute in parallel on the selected runtime. For CPU-bound Python on a GIL-enabled runtime, supply a process backend for multicore work and identify it as such in results. The browser uses one Pyodide interpreter per execution worker. The simulation worker owns the live game. The window owns the DOM. Pure calculations run on a bounded pool of additional Web Workers. Expose the backend, worker count and queue time in the benchmark. The [browser microarchitecture](EnglishScript%20-%20Browser%20microarchitecture.md) specifies the message protocol, failure behavior and release tests for the pinned Pyodide build.
- **Evidence of parallel work.** Start two independent fixed calculations. Instrument dispatch, worker identity, start, finish, parent delivery and cancellation. A rendezvous must show two workers active before either finishes. Separately compare a one-worker and multi-worker CPU workload over repeated runs and report actual throughput. A timer demonstration or overlapping timestamps alone does not establish multicore speedup.
- **Delivery.** Use job IDs and typed result slots. A completion marks a result ready. At a scheduling boundary choose among eligible strands by longest wait, then source order. When the parent requires a result independent of worker finish order, join the jobs and consume their result slots in declared order. Reverse the completion order in the test and compare the parent’s result. Record completion times and order for replay. On cancellation mark the result unusable immediately, clean up the job and drop a late completion.

## C. Async requests, lifetimes and races

| Proposed spelling or integration | Meaning to review | Required observation |
|---|---|---|
| Existing `Ask the model …` and `Judge …` | In the resumable runner, dispatch once and yield. Keep typed retries, grading, batching, dependency boundaries and existing exception semantics. | Delay Jev and Luna independently. Compare recorded/live results, recover from a typed failure, and prove input and canvas presentation continue. |
| `Start the task called Chat:` and `Stop the task called Chat.` | A named task is owned by a scene or session. A name binds to that owner’s generation. Specify name reuse, completion and cancellation. | Close, reopen, change speaker and load a save. Every old completion is discarded. Ending the program cleans up owned tasks. |
| `For at most 2 seconds:` | Apply a deadline to a block. On expiry cancel its children and raise a recoverable time-limit problem. | Test before, after and exactly at the deadline. Proposed tie rule accepts completion already queued for that tick before expiry. |
| `Whichever finishes first:` | Start scoped alternatives, select one winner and cancel the rest. Use deterministic tie order. | Test both winner orders, exact ties, and loser failure. Restrict speculative branches to discardable effects or add explicit staging before allowing a race to commit game mutations. |
| Reactions across a wait | Preserve the existing atomic reaction before suspension. Proposed behavior commits that prefix, records its dependencies, and resumes the waiting continuation in a new ordered turn. | A waiting reaction cannot expose half-applied invariants. A cancelled or obsolete continuation cannot rewrite a newer state. Ordinary synchronous reactions must keep their current ordering. |
| Outside input and shared requests | Deliver game input, model responses and worker results through an explicit event queue. Two callers may share one cached/pending request, while retaining separate lifetimes. | Cancelling one subscriber preserves delivery to the other. A late duplicate cannot advance either twice. An old response must never grant a badge or make a trainer move. |

## D. Implementation order and proof

1. **Model the scheduler with a virtual clock.** Land time, waits, ordering and join semantics in a runnable EnglishScript fixture. Verify old programs and the compiler’s normal diagnostic and editor entry points.
2. **Track effects and rollback.** Include indirect reactions, kept values, aliases and worker-safe library declarations. Exercise positive and refused pairs. Use the concurrency checks as a release gate before enabling shared-world parallel blocks.
3. **Connect nonblocking I/O.** Run a scripted slow conversation while the 160×144 canvas keeps rendering procedural frames. In a headless fixture, advance five virtual seconds instantly. In a real browser, actually delay the reply for five seconds and measure event responsiveness, frame pacing and audio.
4. **Add structured CPU work and then named background lifetimes.** Validate both native and browser workers, cleanup after navigation, deadlines and races. Test queue saturation and replay under out-of-order completions.
5. **Prove independence from the cartridge simulation.** Play the same timestamped controller input through the baseline and the async build. Require identical campaign state and identical canvas shade indices on every game frame. Publish separate results for concurrency syntax, model responsiveness, actual worker backend and measured CPU throughput.

**Current evidence.** On the pinned compiler, ten small compilation probes were refused: a time type/literal, timed wait, predicate wait, parallel block, parallel group, bounded timer, worker result, deadline, race and named task. These are baseline gaps. The underlying arithmetic and synchronous behavior can already be exercised in the [Field Lab program](Boulder%20Badge%20Field%20Lab.english). This document makes no worker or responsiveness performance claim.

[Source language proposal, §§12–13](https://github.com/monstercameron/EnglishScript/blob/acf28a2/docs/SYNTAX.md#12-proposed-time-and-doing-things-at-once)

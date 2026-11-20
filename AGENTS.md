# Working on EnglishScript

## Implementation

- Read the code that owns the behavior. State assumptions that would change the implementation and resolve them against the code or tests. Ask when the intended behavior is still ambiguous.
- Define an observable result before editing, such as a sentence the compiler must accept or a diagnostic it must produce. For a bug, reproduce the failure first. Verify the change through the entry point people use.
- Make the simplest change that meets the acceptance criteria. Match the surrounding style, remove helpers your edits make unused, and leave unrelated code alone.
- Write code without comments. Choose nouns, verbs, and chapter names that make EnglishScript read naturally. Use clear names and small functions in host code.

## Parallel work

- At the start of each implementation milestone, Astra identifies independent pieces and launches many narrowly focused subagents concurrently. Start each ready piece as soon as its inputs are known. Agree on interfaces before dependent work begins.
- Astra sets the acceptance criteria, reviews each result, and integrates the shared checkout. Give every subagent one outcome, the files it owns, and a check it can run.
- Assign hard implementation work to Terra High, well-bounded implementation and test work to Terra Medium, and quick, self-contained tasks to GPT-6 Luna.
- Work in the same checkout. Do not create Git worktrees. Assign one writer per file at a time and sequence edits to shared files. Preserve existing user changes and other workers’ edits.
- Each worker reports the files it changed, the checks it ran, and any unresolved issue.

## Review and integration

- Astra reads every changed EnglishScript passage as ordinary English. If the logic is too complex or the wording obscures who acts, what changes, or when a condition holds, Astra identifies the passage and asks the subagent that wrote it to simplify it. The author revises it and reruns the behavior checks. Astra reviews the revision and repeats this loop until the passage reads clearly and the checks pass.
- Astra reviews the combined diff and handles Git integration. When shared generated files need updating, Astra runs `python tools/build_site.py` once after the source edits settle. Run `python -m unittest discover -s tests` against the integrated checkout.

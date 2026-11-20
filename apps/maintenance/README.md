# Maintenance Desk

Maintenance Desk prepares one shift of work from a facilities inbox. It assigns a trade, puts urgent requests first, allocates a $300 budget and two slots per trade, and writes a handoff for each ticket. It creates a local plan for a supervisor to use.

## Run a shift

On Windows, double-click **Maintenance Desk.cmd** to replay the six synthetic sample requests. From the repository root, the equivalent command is:

```powershell
.\apps\maintenance\Run.ps1 -Mode Demo
```

The sample replay schedules the reading room, garden room and east stacks for $260. The remaining $40 cannot cover the west stacks. The archive estimate requires approval, and the two opinions on the map room disagree.

| Mode | Input and output | Model behavior |
|---|---|---|
| Demo | `.local/Demo/inbox.txt` and `shift-plan.txt` beside it | Replays the supplied `demo.jsonl` for the sample inbox |
| Live | `.local/Live/inbox.txt` and its shift plan | Jev judges and GPT-6 Luna writes handoffs and gives second opinions |
| Offline | `.local/Offline/inbox.txt` and its shift plan | Preserves descriptions and sends assessments to a supervisor |

Run Live once to seed its inbox, or supply your own folder containing `inbox.txt`. Each nonblank line is one ticket with three fields, such as `Reading room|120.50|The ceiling light is out.` Estimates are nonnegative dollar amounts in whole cents. Each run replaces the plan in that folder. Rejected rows appear in the report with their intake IDs.

```powershell
.\apps\maintenance\Run.ps1 -Mode Live -Workspace C:\Maintenance\Today
.\apps\maintenance\Run.ps1 -Mode Offline -Workspace C:\Maintenance\Offline
```

For live use, set `TYPESAFE_API_KEY` or `JEV_API_KEY` for Jev and `OPENAI_API_KEY` for GPT-6 Luna. The launcher selects `jev+openai:gpt-6-luna`. The optional `-CredentialsFile` reads named `KEY=value` entries for the selected providers into the process environment for the run. Live judgments send the ticket description to Jev. Luna receives the description when asked for a handoff or second opinion.

On other systems, run from your shift folder with the repository on `PYTHONPATH`. Point the CLI at the application and transcript by absolute path:

```sh
PYTHONPATH="$repo" python -m englishscript "$repo/apps/maintenance/desk.english" --model "replay:$repo/apps/maintenance/demo.jsonl"
```

## How the plan is decided

| System | Responsibility |
|---|---|
| 0 | Validates intake, reserves estimates over $200 for approval, enforces budget and capacity, and processes urgent, prompt, then routine work. Input order breaks ties. |
| 1 | Judges trade and grades urgency from the reported issue. Below 50% trade confidence, the ticket goes to a supervisor. |
| 2 | At 50% through just under 85% confidence, gives an independent typed trade opinion. Agreement permits scheduling. Disagreement requires review. For eligible tickets, writes a handoff. If the writer fails while summarizing, the original description stays in the plan. |

The application and its intake parser are written in EnglishScript. The three embedded `For example` checks verify the budget and ticket counts on every shift. Run the integration tests from the repository root:

```sh
python -m unittest discover -s tests -p test_maintenance_desk.py
```

"""Write examples/triage_answers.txt: the answers the triage example replays.

No model is asked. The answers below were written by hand, one set for each
letter, and this script records them in the form ``--model replay:<file>``
reads, by running the example with them. Run it again after changing the
example's questions or letters:

    python tools/record_triage.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from englishscript import compile_file  # noqa: E402
from englishscript.models import Transcript  # noqa: E402

# For each letter, by a word in it: the team probabilities, how likely the
# customer is upset or in a hurry, and a one-line summary.
ANSWERS = {
    "kettle": ({"returns": 0.94, "billing": 0.04, "shipping": 0.02}, 0.35,
               "A refund for a kettle that arrived cracked."),
    "charged": ({"returns": 0.08, "billing": 0.81, "shipping": 0.11}, 0.86,
                "Money back for an order that was charged twice."),
    "parcel": ({"returns": 0.03, "billing": 0.05, "shipping": 0.92}, 0.55,
               "Where a parcel due on Monday has got to."),
    "gift": ({"returns": 0.30, "billing": 0.42, "shipping": 0.28}, 0.05,
             "Whether gift cards are sold."),
}


def answers_for(state):
    text = str(state or "")
    for word, answer in ANSWERS.items():
        if word in text:
            return answer
    raise LookupError(f"no answer was written for: {text[:60]}")


def model(question, state, shape, complaint):
    return answers_for(state)[2]


def judge(question, state, choices, meanings):
    team, heat, _ = answers_for(state)
    return heat if choices is None else team


def main():
    target = ROOT / "examples" / "triage_answers.txt"
    if target.exists():
        target.unlink()
    recorder = Transcript(str(target), (model, judge))
    said = []
    compile_file(ROOT / "examples" / "triage.english").run(
        out=lambda text="": said.append(str(text)), model=recorder.model, judge=recorder.judge)
    print("\n".join(said))
    print(f"\n{target.relative_to(ROOT)}: {len(target.read_text(encoding='utf-8').splitlines())} answers recorded")


if __name__ == "__main__":
    main()

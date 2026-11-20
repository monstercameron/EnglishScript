"""Check the sentences that ask a model, with written-down answers in place of a model.

Run from the repository:  python tools/research/model_sentences.py .
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from englishscript import EnglishError, compile_source  # noqa: E402
from englishscript.models import Canned  # noqa: E402

PROGRAM = '''A team is one of returns, billing or shipping.
For a team, returns means "the customer wants to send something back".
A letter has a wording (text).
There is a letter called First whose wording is "The kettle came broken. I want my money back.".

Try:
  Ask the model "Say in one line what this customer wants." about First's wording and let the gist (text) be the reply.
  Say "Gist: {the gist}"
  Judge "Which team should handle this letter?" about First and let the pick (team) be the verdict and the sureness (percent) be the likelihood.
  Judge "Is the customer angry?" about First's wording and let the heat (percent) be the chance.
  If the sureness is at least 90%:
    Say "Sent to {the pick}."
  Otherwise if the sureness is at least 60%:
    Say "{the pick}, if a person agrees."
  Otherwise:
    Say "Handed to a person."
  Say "Heat {the heat}."
  Ask the model "How many items are mentioned?" about First's wording and let the tally (number) be the reply.
  Say "Tally: {the tally}"
If that fails:
  If the problem is no model:
    Say "No model is listening, so the letter is held for a person."
  Otherwise if the problem is a bad reply:
    Say "The model's answer could not be used: {the problem}"
'''


def run(label, model=None, judge=None):
    said = []
    try:
        compile_source(PROGRAM).run(out=lambda text="": said.append(str(text)), model=model, judge=judge)
    except EnglishError as error:
        said.append(f"PROBLEM: {error.message}")
    print(f"--- {label}")
    for line in said:
        print("   ", line)


run("nothing connected")
canned = Canned(replies=["They want a refund for a broken kettle.", "two", "2"],
                verdicts=[{"returns": 0.93, "billing": 0.05, "shipping": 0.02}, 0.71])
run("a model that answers, the second reply misread then mended", canned.model, canned.judge)
print("    what the judge was told about the letter:")
for line in str(canned.asked[1][2]).splitlines():
    print("      ", line)
canned = Canned(replies=["gist", "lots", "many", "several"], verdicts=[{"returns": 0.5, "billing": 0.3, "shipping": 0.2}, 0.1])
run("a reply that cannot be read three times", canned.model, canned.judge)
canned = Canned(replies=["gist"], verdicts=[{"returns": 0.9, "parcels": 0.1}])
run("a verdict for a choice that is not one of the set", canned.model, canned.judge)

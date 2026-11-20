"""Who answers when a program asks a model.

The compiler knows nothing about any model. A program may say

    Ask the model "Write one line of thanks." and let the note (text) be the reply.
    Judge "Which team should handle this?" about the letter and let the team (team) be the verdict.

and whoever runs the program decides who is listening. This module is the
listeners that come with EnglishScript. Nothing here is imported unless a
listener is asked for (``python -m englishscript program.english --model SPEC``,
or ``connect(SPEC)`` from Python), so the compiler still needs nothing but
Python itself.

A listener is a pair of plain functions, either of which may be ``None``:

``model(question, state, shape, complaint) -> str | None``
    For "Ask the model". ``question`` is the text asked; ``state`` is what it is
    about, as text, or ``None``. ``shape`` says what kind of reply is wanted::

        {"type": "text" | "number" | "money" | "percent" | "yes or no" | "choice" | "list",
         "choices": [...] or None, "items": <item type of a list> or None, "optional": bool}

    ``complaint`` is ``None`` the first time, and on a second asking says what
    was wrong with the last reply. The reply is returned as text, written the
    way the language writes values (``1,250``, ``$5``, ``12.5%``, ``yes``, one
    item to a line for a list), and the program's own reader reads it. ``None``
    means there is no reply: the model refused, or was cut short.

``judge(question, state, choices, meanings) -> float | dict``
    For "Judge". With ``choices`` ``None`` it returns how likely the statement
    is, from 0 to 1. Otherwise it returns ``{choice: probability}`` for every
    choice. ``meanings`` is ``{choice: text}`` for the choices given a meaning.

Either may raise ``EnglishError(..., stage="run", recoverable=True)`` for a
problem a program can recover from, such as a network that is down.

The specs ``connect`` understands
---------------------------------

``person``
    The person at the keyboard answers as the model would. Needs nothing, and
    is the way to try a program before any model is involved.

``anthropic`` or ``anthropic:<model id>``
    A Claude model answers "Ask the model", through the official ``anthropic``
    package (``pip install anthropic``), which finds its own credentials. It
    also answers "Judge", but only as an estimate: a model that writes text is
    asked to write down probabilities, and those are not calibrated. For
    judgements that matter, use a model built to judge.

``jev`` or ``jev:<model id>``
    TypeSafe AI's Jev answers "Judge" (it writes no text, so it cannot answer
    "Ask the model"). The key is read from ``TYPESAFE_API_KEY``.

``A+B``
    Two listeners together: the first that can answer each kind of question
    does. ``jev+anthropic`` judges with Jev and writes with Claude.

``replay:<file>``
    Answers from a file written earlier by ``record``. Nothing is asked of any
    model, so the run is the same every time: this is how to test a program
    that asks a model.

``record:<file>:<spec>``
    Asks ``<spec>``, and writes every question and answer to the file.

The ``anthropic`` and ``jev`` listeners were written from those services'
published documentation and have NOT been run against the live services by the
authors of this module. The others are covered by the test suite.
"""
from __future__ import annotations

import json
import os

from .lexer import EnglishError

#: The Claude model asked when none is named.
CLAUDE = "claude-opus-5-5"
#: The Jev model asked when none is named.
JEV = "jev-latest"
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"


def problem(message):
    """A problem a program can recover from with "Try:"."""
    return EnglishError(message, stage="run", recoverable=True)


def wanted(shape):
    """What kind of reply is wanted, in words a person or a model can follow."""
    kind = shape.get("type")
    if kind == "choice":
        form = "exactly one of these words: " + ", ".join(shape.get("choices") or [])
    elif kind == "list":
        form = f"a list, one item to a line, each item {_one(shape.get('items') or 'text')}"
    else:
        form = _one(kind)
    if shape.get("optional"):
        form += '; or the single word "nothing" if there is nothing to say'
    return form


def _one(kind):
    return {
        "text": "plain text",
        "number": "a number written in digits, such as 1,250 or 0.5",
        "money": "an amount of money written with a dollar sign, such as $1,250.50",
        "percent": "a percentage written with a percent sign, such as 12.5%",
        "yes or no": "the word yes or the word no",
    }.get(kind, "plain text")


# ------------------------------------------------------------------ a person


class Person:
    """The person at the keyboard answers as the model would.

    ``ask`` takes a question and returns the reply, or ``None`` when there is
    no more input; ``say`` shows a line. By default they are the keyboard and
    the screen. A page can pass its own, and so can a test.
    """

    def __init__(self, ask=None, say=print):
        self.ask = ask if ask is not None else _keyboard
        self.say = say

    def model(self, question, state, shape, complaint):
        if complaint:
            self.say(f"(That could not be read: {complaint})")
        if state:
            self.say("The model is asked about this:")
            for line in str(state).splitlines():
                self.say("    " + line)
        return self.ask(f"[You are the model] {question} (Answer with {wanted(shape)}.)")

    def judge(self, question, state, choices, meanings):
        if state:
            self.say("The judge is asked about this:")
            for line in str(state).splitlines():
                self.say("    " + line)
        if choices is None:
            reply = self.ask(f"[You are the judge] {question} (How likely is that? Answer with a percentage.)")
            return _share(reply)
        for choice in choices:
            if meanings and choice in meanings:
                self.say(f"    {choice}: {meanings[choice]}")
        reply = self.ask(f"[You are the judge] {question} (One of {', '.join(choices)}; then how sure, "
                         f"as a percentage. For example: {choices[0]} 80%)")
        if reply is None:
            raise problem("The judge gave no answer.")
        words = reply.replace(",", " ").split()
        picked = next((choice for choice in choices if words and choice.lower() == words[0].lower()), None)
        if picked is None:
            raise problem(f'The judge answered "{reply.strip()}", which is not one of {", ".join(choices)}.')
        sure = _share(words[1]) if len(words) > 1 else 1.0
        rest = (1.0 - sure) / (len(choices) - 1) if len(choices) > 1 else 0.0
        return {choice: (sure if choice == picked else rest) for choice in choices}


def _keyboard(prompt):
    try:
        return input(prompt + " ")
    except EOFError:
        return None


def _share(reply):
    """A percentage a person typed, as a number from 0 to 1."""
    if reply is None:
        raise problem("The judge gave no answer.")
    text = str(reply).strip().rstrip("%").strip()
    try:
        value = float(text) / 100.0
    except ValueError:
        raise problem(f'The judge answered "{str(reply).strip()}", which is not a percentage.') from None
    if not 0.0 <= value <= 1.0:
        raise problem(f'The judge answered "{str(reply).strip()}", which is not between 0% and 100%.')
    return value


# ---------------------------------------------------------------- canned replies


class Canned:
    """Replies written down in advance, given out in order. For tests and examples."""

    def __init__(self, replies=(), verdicts=()):
        self.replies = list(replies)
        self.verdicts = list(verdicts)
        self.asked = []  # every question put, as (kind, question, state)

    def model(self, question, state, shape, complaint):
        self.asked.append(("ask", question, state))
        if not self.replies:
            raise problem("No reply was written down for this question.")
        return self.replies.pop(0)

    def judge(self, question, state, choices, meanings):
        self.asked.append(("judge", question, state))
        if not self.verdicts:
            raise problem("No verdict was written down for this question.")
        return self.verdicts.pop(0)


# --------------------------------------------------------- a transcript on disk


class Transcript:
    """Questions and answers kept in a file, one JSON object to a line.

    Recording wraps another listener and writes down what it said. Replaying
    asks nobody: each question is answered by the next answer recorded for the
    same question about the same state.
    """

    def __init__(self, path, inner=None):
        self.path = path
        self.inner = inner  # (model, judge) when recording, None when replaying
        self.kept = []
        if inner is None:
            try:
                with open(path, encoding="utf-8") as handle:
                    self.kept = [json.loads(line) for line in handle if line.strip()]
            except OSError as error:
                raise problem(f"I couldn't read the recorded answers in {path}: {error.strerror or error}.") from None
            except ValueError:
                raise problem(f"The recorded answers in {path} are not in the form this module writes.") from None

    def _write(self, entry):
        with open(self.path, "a", encoding="utf-8", newline="") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _next(self, kind, question, state):
        for index, entry in enumerate(self.kept):
            if entry.get("kind") == kind and entry.get("question") == question and entry.get("state") == state:
                return self.kept.pop(index)["answer"]
        raise problem(f'Nothing was recorded for the question "{question}".')

    def model(self, question, state, shape, complaint):
        if self.inner is None:
            return self._next("ask", question, state)
        if self.inner[0] is None:
            raise problem("No model is listening.")
        answer = self.inner[0](question, state, shape, complaint)
        self._write({"kind": "ask", "question": question, "state": state, "answer": answer})
        return answer

    def judge(self, question, state, choices, meanings):
        if self.inner is None:
            return self._next("judge", question, state)
        if self.inner[1] is None:
            raise problem("No model is listening.")
        answer = self.inner[1](question, state, choices, meanings)
        self._write({"kind": "judge", "question": question, "state": state, "answer": answer})
        return answer


# --------------------------------------------------------------------- Claude


class Claude:
    """A Claude model, through the official ``anthropic`` package.

    Written from Anthropic's published documentation; not run against the live
    service by the authors of this module. ``client`` may be passed in (a test
    passes a stand-in); otherwise ``anthropic.Anthropic()`` is made, which
    finds its own credentials.
    """

    SYSTEM = ("A program has put one question to you. Reply with the answer and nothing else: "
              "no preamble, no explanation, no quotation marks round it.")

    def __init__(self, model=CLAUDE, client=None):
        self.name = model
        self.client = client

    def _client(self):
        if self.client is None:
            try:
                import anthropic  # noqa: PLC0415 - only when this listener is used
            except ImportError:
                raise problem('The "anthropic" listener needs the anthropic package: pip install anthropic') from None
            self.client = anthropic.Anthropic()
        return self.client

    def _send(self, text, schema):
        """Ask for a JSON object of the given schema. Gives the object, or None for no reply."""
        client = self._client()
        try:
            response = client.beta.messages.create(
                model=self.name,
                max_tokens=16000,
                system=self.SYSTEM,
                messages=[{"role": "user", "content": text}],
                # A short, typed answer does not need deep thought.
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
                # If the model declines on policy grounds, let the service try its fallback.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except Exception as error:  # noqa: BLE001 - the package's own errors, said plainly
            status = getattr(error, "status_code", None)
            said = getattr(error, "message", None) or str(error) or type(error).__name__
            if status == 401:
                raise problem("The model would not answer: the key was not accepted.") from None
            if status == 429:
                raise problem("The model would not answer: too many questions have been asked. Try again later.") from None
            raise problem(f"The model could not be reached: {said}") from None
        if getattr(response, "stop_reason", None) in ("refusal", "max_tokens"):
            return None
        text = next((block.text for block in response.content if getattr(block, "type", None) == "text"), None)
        if text is None:
            return None
        try:
            return json.loads(text)
        except ValueError:
            return None

    def model(self, question, state, shape, complaint):
        kind = shape.get("type")
        if kind == "list":
            reply = {"type": "array", "items": {"type": "string"}}
        elif kind == "choice":
            reply = {"type": "string", "enum": list(shape.get("choices") or []) + (["nothing"] if shape.get("optional") else [])}
        elif kind == "yes or no":
            reply = {"type": "string", "enum": ["yes", "no"] + (["nothing"] if shape.get("optional") else [])}
        else:
            reply = {"type": "string"}
        schema = {"type": "object", "properties": {"reply": reply}, "required": ["reply"], "additionalProperties": False}
        parts = [question]
        if state:
            parts.append("It is about this:\n" + str(state))
        parts.append(f'Put the answer in "reply" as {wanted(shape)}.')
        if complaint:
            parts.append("Your last reply could not be used. " + complaint)
        found = self._send("\n\n".join(parts), schema)
        if found is None or "reply" not in found:
            return None
        answer = found["reply"]
        return "\n".join(str(item) for item in answer) if isinstance(answer, list) else str(answer)

    def judge(self, question, state, choices, meanings):
        """An ESTIMATE: a model that writes text, asked to write down probabilities."""
        about = ("\n\nIt is about this:\n" + str(state)) if state else ""
        if choices is None:
            schema = {"type": "object", "properties": {"probability": {"type": "number"}},
                      "required": ["probability"], "additionalProperties": False}
            found = self._send(f"How likely is the following to be so? Give a probability from 0 to 1.\n\n{question}{about}", schema)
            if found is None:
                raise problem("The model gave no judgement.")
            return found.get("probability")
        schema = {"type": "object", "properties": {choice: {"type": "number"} for choice in choices},
                  "required": list(choices), "additionalProperties": False}
        glosses = "".join(f"\n- {choice}: {meanings[choice]}" for choice in choices if meanings and choice in meanings)
        found = self._send(
            f"{question}\n\nThe possible answers are: {', '.join(choices)}.{glosses}\n\n"
            f"For each possible answer give the probability, from 0 to 1, that it is the right one. "
            f"The probabilities should add up to 1.{about}", schema)
        if found is None:
            raise problem("The model gave no judgement.")
        return found


# ------------------------------------------------------------------------ Jev


class Jev:
    """TypeSafe AI's Jev, a model that answers typed questions with probabilities.

    Written from TypeSafe's published documentation (docs.typesafe.ai); not run
    against the live service by the authors of this module. ``send`` may be
    passed in (a test passes a stand-in): it takes the request as a dict and
    returns the response as a dict.
    """

    def __init__(self, model=JEV, send=None):
        self.name = model
        self.send = send if send is not None else self._post

    def _post(self, body):
        import urllib.error  # noqa: PLC0415 - only when this listener is used
        import urllib.request  # noqa: PLC0415

        key = os.environ.get("TYPESAFE_API_KEY")
        if not key:
            raise problem("Jev would not answer: there is no key in TYPESAFE_API_KEY.")
        request = urllib.request.Request(
            JEV_ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - a fixed https address
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise problem(f"Jev would not answer: the service said {error.code}.") from None
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise problem(f"Jev could not be reached: {getattr(error, 'reason', error)}.") from None

    def judge(self, question, state, choices, meanings):
        if choices is None:
            asked = {"type": "noul", "instructions": question}
        else:
            # Jev wants a description of each option. A choice with no meaning given stands for itself.
            asked = {"type": "choice", "instructions": question,
                     "criteria": {choice: (meanings or {}).get(choice, choice) for choice in choices}}
        found = self.send({"model": self.name, "state": "" if state is None else str(state), "questions": {"q": asked}})
        try:
            answer = found["answers"]["q"]
            return answer["noul"] if choices is None else answer["probabilities"]
        except (KeyError, TypeError):
            raise problem("Jev's answer was not in the form its documentation describes.") from None


# -------------------------------------------------------------------- connect


LISTENERS = ("person", "anthropic", "jev")


def _split_record(rest):
    """``<file>:<listener>`` into the two. A file may have colons of its own
    (``C:\\answers.txt``), so the split is at the first colon that is followed
    by the name of a listener."""
    for at in range(len(rest)):
        if rest[at] != ":":
            continue
        after = rest[at + 1:]
        head = after.split("+", 1)[0].split(":", 1)[0]
        if head in LISTENERS and rest[:at]:
            return rest[:at], after
    raise problem('"record" is written record:<file>:<listener>, such as record:answers.txt:anthropic.')


def connect(spec):
    """The listeners a spec names, as ``(model, judge)``. Either may be ``None``."""
    spec = (spec or "").strip()
    if not spec:
        raise problem("No listener was named. Try: person, anthropic, jev, replay:<file>.")
    if spec.startswith("replay:"):
        transcript = Transcript(spec[len("replay:"):])
        return transcript.model, transcript.judge
    if spec.startswith("record:"):
        path, inner = _split_record(spec[len("record:"):])
        transcript = Transcript(path, connect(inner))
        return transcript.model, transcript.judge
    model = judge = None
    for part in spec.split("+"):
        name, _, which = part.strip().partition(":")
        if name == "person":
            found = Person()
            pair = (found.model, found.judge)
        elif name == "anthropic":
            found = Claude(which or CLAUDE)
            pair = (found.model, found.judge)
        elif name == "jev":
            pair = (None, Jev(which or JEV).judge)
        else:
            raise problem(f'I don\'t know a listener called "{name}". There are: person, anthropic, jev, '
                          f'replay:<file> and record:<file>:<listener>.')
        model = model or pair[0]
        judge = judge or pair[1]
    return model, judge

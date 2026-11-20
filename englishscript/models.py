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

``judges(requests) -> list``
    Several judgements at once. A program's consecutive judgements about the
    same thing are put together, as Jev is meant to be asked. Each request is
    ``{"question", "state", "choices", "meanings", "scale"}``; ``scale`` is
    true when the choices are an ordered scale and the program wants a grade.
    The answers come back in the same order, each what ``judge`` would give.
    A listener without it is asked one question at a time.

Any of them may raise ``EnglishError(..., stage="run", recoverable=True)`` for
a problem a program can recover from, such as a network that is down.

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

``openai`` or ``openai:<model id>``
    GPT-6 Luna writes typed replies through the Responses API with OPENAI_API_KEY.
    This listener accepts text and explicitly supplied PNG or JPEG images.

``A+B``
    Two listeners together: the first that can answer each kind of question
    does. ``jev+anthropic`` judges with Jev and writes with Claude.

``replay:<file>``
    Answers from a file written earlier by ``record``. Nothing is asked of any
    model, so the run is the same every time: this is how to test a program
    that asks a model.

``record:<file>:<spec>``
    Asks ``<spec>``, and writes every question and answer to the file.

Jev and GPT-6 Luna have been exercised together against the live services
with text and image subjects. Automated tests also use stand-ins for the
Responses API and the Anthropic SDK.
"""
from __future__ import annotations

import base64
import json
import os
import uuid
import urllib.error
import urllib.request

from .lexer import EnglishError
from .runtime import ImageState

#: The Claude model asked when none is named.
CLAUDE = "claude-opus-5-5"
#: The Jev model asked when none is named.
JEV = "jev-latest"
JEV_ENDPOINT = "https://api.typesafe.ai/v1/systemone"


class Listeners(tuple):
    """``(model, judge)``, as ``connect`` gives them, with ``judges`` beside.

    A tuple of two, so ``model, judge = connect(spec)`` still works.
    """

    def __new__(cls, model, judge, judges=None):
        pair = super().__new__(cls, (model, judge))
        pair.judges = judges
        return pair


def one_by_one(judge):
    """A ``judges`` for a listener that can only be asked one question at a time."""
    if judge is None:
        return None

    def judges(requests):
        return [judge(r["question"], r["state"], r["choices"], r["meanings"]) for r in requests]
    judges.sequential = True
    return judges


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
        prompt = f"[You are the model] {question} (Answer with {wanted(shape)}.)"
        if shape.get("type") != "list":
            return self.ask(prompt)
        first = self.ask(prompt + " Enter one item per reply; finish with an empty reply.")
        if first is None or (shape.get("optional") and first.strip().lower() == "nothing"):
            return first
        items = []
        value = first
        while value is not None and value.strip():
            items.append(value)
            value = self.ask("Next item (leave empty to finish):")
        return "\n".join(items)

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
                          f"as a percentage. For example: {choices[0]} 80%. "
                          "To give the full distribution, write choice=percent for each choice, separated by commas.)")
        if reply is None:
            raise problem("The judge gave no answer.")
        names = {choice.casefold(): choice for choice in choices}
        if "=" in reply:
            distribution = {}
            for entry in reply.split(","):
                label, _, value = entry.partition("=")
                choice = names.get(" ".join(label.split()).casefold())
                if choice is None or choice in distribution:
                    raise problem("Give each declared choice exactly once.")
                distribution[choice] = _share(value)
            if len(distribution) != len(choices):
                raise problem("Give each declared choice exactly once.")
            return distribution
        answer = " ".join(reply.replace(",", " ").split()).casefold()
        picked = names.get(answer)
        sure = 1.0
        if picked is None:
            label, _, confidence = answer.rpartition(" ")
            picked = names.get(label)
            if picked is not None:
                sure = _share(confidence)
        if picked is None:
            raise problem(f'The judge answered "{reply.strip()}", which is not one of {", ".join(choices)}.')
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

    def _next(self, key):
        for index, entry in enumerate(self.kept):
            # Legacy transcripts contain only kind, question, state and answer.
            if all(entry.get(k) == v for k, v in key.items() if k != "request" or k in entry):
                self.kept.pop(index)
                if "error" in entry:
                    raise EnglishError(stage="run", **entry["error"])
                return entry["answer"]
        raise problem(f'Nothing was recorded for the question "{key["question"]}".')

    def _exchange(self, kind, question, state, request, listen):
        key = {"kind": kind, "question": question,
               "state": state.fingerprint() if isinstance(state, ImageState) else state, "request": request}
        if self.inner is None:
            return self._next(key)
        try:
            if listen is None:
                raise EnglishError("No model is listening.", stage="run", recoverable=True, teach="no_model")
            answer = listen()
        except EnglishError as error:
            self._write(dict(key, error={"message": error.message, "hint": error.hint, "teach": error.key,
                                         "recoverable": error.recoverable, "problem": error.problem}))
            raise
        self._write(dict(key, answer=answer))
        return answer

    def model(self, question, state, shape, complaint):
        writer = self.inner[0] if self.inner else None
        return self._exchange("ask", question, state, {"shape": shape, "complaint": complaint},
                              (lambda: writer(question, state, shape, complaint)) if writer else None)

    def judge(self, question, state, choices, meanings):
        return self._judgement(question, state, choices, meanings, False)

    def _judgement(self, question, state, choices, meanings, scale):
        request = {"choices": choices, "meanings": meanings, "scale": scale}
        judge = self.inner[1] if self.inner else None
        judges = getattr(self.inner, "judges", None)
        listen = None
        if judges and (scale or not judge):
            listen = lambda: judges([dict(request, question=question, state=state)])[0]
        elif judge:
            listen = lambda: judge(question, state, choices, meanings)
        return self._exchange("judge", question, state, request, listen)

    def judges(self, requests):
        return [self._judgement(**request) for request in requests]

    # Commit each outcome before asking the next question, including across a failed Try.
    judges.sequential = True


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

    def _send(self, text, schema, images=()):
        """Ask for a JSON object of the given schema. Gives the object, or None for no reply."""
        client = self._client()
        content = text
        if images:
            content = [{"type": "text", "text": text}]
            for label, image in images:
                content.extend([{"type": "text", "text": label}, {"type": "image", "source": {
                    "type": "base64", "media_type": "image/" + image.format,
                    "data": base64.b64encode(image.data).decode("ascii")}}])
        try:
            response = client.beta.messages.create(
                model=self.name,
                max_tokens=16000,
                system=self.SYSTEM,
                messages=[{"role": "user", "content": content}],
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
        images = [("Image for this question", state)] if isinstance(state, ImageState) else []
        found = self._send("\n\n".join(parts), schema, images)
        if found is None or "reply" not in found:
            return None
        answer = found["reply"]
        return "\n".join(str(item) for item in answer) if isinstance(answer, list) else str(answer)

    def judge(self, question, state, choices, meanings):
        """An ESTIMATE: a model that writes text, asked to write down probabilities."""
        about = ("\n\nIt is about this:\n" + str(state)) if state else ""
        images = [("Image for this question", state)] if isinstance(state, ImageState) else []
        if choices is None:
            schema = {"type": "object", "properties": {"probability": {"type": "number"}},
                      "required": ["probability"], "additionalProperties": False}
            found = self._send(f"How likely is the following to be so? Give a probability from 0 to 1.\n\n{question}{about}", schema, images)
            if found is None:
                raise problem("The model gave no judgement.")
            return found.get("probability")
        schema = {"type": "object", "properties": {choice: {"type": "number"} for choice in choices},
                  "required": list(choices), "additionalProperties": False}
        glosses = "".join(f"\n- {choice}: {meanings[choice]}" for choice in choices if meanings and choice in meanings)
        found = self._send(
            f"{question}\n\nThe possible answers are: {', '.join(choices)}.{glosses}\n\n"
            f"For each possible answer give the probability, from 0 to 1, that it is the right one. "
            f"The probabilities should add up to 1.{about}", schema, images)
        if found is None:
            raise problem("The model gave no judgement.")
        return found

    def judges(self, requests):
        """Several ESTIMATES in one call, one property of the reply for each question."""
        if len(requests) == 1 and not requests[0].get("scale"):
            r = requests[0]
            return [self.judge(r["question"], r["state"], r["choices"], r["meanings"])]
        properties, parts = {}, []
        states = {r["state"] for r in requests}
        shared = states.pop() if len(states) == 1 else None
        for number, r in enumerate(requests, 1):
            key = f"q{number}"
            if r["choices"] is None:
                properties[key] = {"type": "number"}
                parts.append(f"{key}. How likely is the following to be so, from 0 to 1? {r['question']}")
            else:
                properties[key] = {"type": "object", "properties": {c: {"type": "number"} for c in r["choices"]},
                                   "required": list(r["choices"]), "additionalProperties": False}
                glosses = "".join(f" ({c}: {r['meanings'][c]})" for c in r["choices"] if r["meanings"] and c in r["meanings"])
                order = " They are in order, from the least to the most." if r.get("scale") else ""
                parts.append(f"{key}. {r['question']} The possible answers are {', '.join(r['choices'])}.{glosses}{order} "
                             "Give each the probability, from 0 to 1, that it is the right one; they should add up to 1.")
            if shared is None and r["state"]:
                parts[-1] += "\nIt is about this:\n" + str(r["state"])
        text = "Answer each question on its own.\n\n" + "\n\n".join(parts)
        if shared:
            text += "\n\nEvery question is about this:\n" + str(shared)
        schema = {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
        images = []
        if isinstance(shared, ImageState):
            images.append(("Image for every question", shared))
        elif shared is None:
            images = [(f"Image for q{n}", r["state"]) for n, r in enumerate(requests, 1)
                      if isinstance(r["state"], ImageState)]
        found = self._send(text, schema, images)
        if found is None:
            raise problem("The model gave no judgement.")
        return [found.get(f"q{number}") for number in range(1, len(requests) + 1)]


# ------------------------------------------------------------------------ Jev


class Jev:
    """TypeSafe AI's Jev, a model that answers typed questions with probabilities.

    Written from TypeSafe's published documentation (docs.typesafe.ai). ``send`` may be
    passed in (a test passes a stand-in): it takes the request as a dict and
    returns the response as a dict.
    """

    def __init__(self, model=JEV, send=None):
        self.name = model
        self.send = send if send is not None else self._post

    def _post(self, body):
        key = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY")
        if not key:
            raise problem("Jev would not answer: there is no key in TYPESAFE_API_KEY.")
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if "assets" in body:
            headers["TypeSafe-Danger-Zone-Images"] = "true"
        request = urllib.request.Request(
            JEV_ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST",
            headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - a fixed https address
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raise problem(f"Jev would not answer: the service said {error.code}.") from None
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise problem(f"Jev could not be reached: {getattr(error, 'reason', error)}.") from None

    @staticmethod
    def _question(question, choices, meanings, scale):
        if choices is None:
            return {"type": "noul", "instructions": question}
        if scale and 2 <= len(choices) <= 10:
            # A Score: the levels in order, from the lowest, each described.
            return {"type": "score", "instructions": question,
                    "criteria": [(meanings or {}).get(choice, choice) for choice in choices]}
        # Jev wants a description of each option. A choice with no meaning given stands for itself.
        return {"type": "choice", "instructions": question,
                "criteria": {choice: (meanings or {}).get(choice, choice) for choice in choices}}

    @staticmethod
    def _answer(answer, choices, scale):
        """What Jev answered, in the form a judge gives: a chance, or a probability for each choice."""
        if choices is None:
            return answer["noul"]
        if answer.get("type") == "score":
            # A Score's probabilities are keyed by the level's number, from "0".
            return {choice: answer["probabilities"][str(number)] for number, choice in enumerate(choices)}
        return answer["probabilities"]

    def judge(self, question, state, choices, meanings):
        return self.judges([{"question": question, "state": state, "choices": choices,
                             "meanings": meanings, "scale": False}])[0]

    def judges(self, requests):
        """Every question about one state goes in one request, as Jev is meant to be asked."""
        answers = [None] * len(requests)
        states = {}
        for index, r in enumerate(requests):
            states.setdefault(r["state"] or "", []).append(index)
        for state, indexes in states.items():
            questions = {f"q{index}": self._question(requests[index]["question"], requests[index]["choices"],
                                                    requests[index]["meanings"], requests[index].get("scale"))
                         for index in indexes}
            body = {"model": self.name, "state": state, "questions": questions}
            if isinstance(state, ImageState):
                ref = str(uuid.uuid4())
                body["state"] = {"image": ref}
                body["assets"] = {ref: {"type": "image", "format": state.format,
                                        "data_base64": base64.b64encode(state.data).decode("ascii")}}
            found = self.send(body)
            if not isinstance(found, dict) or not isinstance(found.get("answers"), dict):
                raise problem("Jev's answer was not in the form its documentation describes.")
            for index in indexes:
                r = requests[index]
                try:
                    answers[index] = self._answer(found["answers"][f"q{index}"], r["choices"], r.get("scale"))
                except (KeyError, TypeError, AttributeError):
                    # The runtime reports a bad answer at this sentence, after preceding ones finish.
                    answers[index] = None
        return answers


# -------------------------------------------------------------------- connect


class OpenAIWriter:
    """System 2 through the OpenAI Responses API."""

    def __init__(self, name):
        self.name = name

    def model(self, question, state, shape, complaint):
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise problem("The OpenAI writer needs OPENAI_API_KEY.")
        headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}
        endpoint = "https://api.openai.com/v1/responses"
        content = [{"type": "input_text", "text": question}]
        if isinstance(state, ImageState):
            data = base64.b64encode(state.data).decode("ascii")
            content.append({"type": "input_image", "image_url": f"data:image/{state.format};base64,{data}"})
        elif state is not None:
            content.append({"type": "input_text", "text": "Subject:\n" + state})
        instructions = "Return only " + wanted(shape) + "."
        if complaint:
            instructions += " The previous reply could not be used. " + complaint
        body = {"model": self.name, "input": [{"role": "user", "content": content}],
                "instructions": instructions, "store": False}
        request = urllib.request.Request(endpoint, data=json.dumps(body).encode(), headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                result = json.load(response)
        except urllib.error.HTTPError as error:
            try:
                detail = json.load(error)
                reason = detail.get("error", {}).get("code") if isinstance(detail, dict) else None
            except (ValueError, OSError, AttributeError):
                reason = None
            if reason in ("credit_balance_exhausted", "insufficient_quota"):
                raise problem("The OpenAI project has no available API credit.") from None
            raise problem(f"The OpenAI writer returned HTTP {error.code}.") from None
        except (OSError, ValueError) as error:
            raise problem(f"The writer could not answer ({type(error).__name__}).") from None
        if result.get("status") != "completed":
            return None
        parts = [part for item in result.get("output", []) if item.get("type") == "message"
                 for part in item.get("content", [])]
        if any(part.get("type") == "refusal" for part in parts):
            return None
        replies = [p["text"] for p in parts if p.get("type") == "output_text"]
        return "\n".join(replies) if replies else None


LISTENERS = ("person", "anthropic", "jev", "openai")


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
    """The listeners a spec names: ``(model, judge)``, with ``.judges`` beside.

    Any of the three may be ``None``.
    """
    spec = (spec or "").strip()
    if not spec:
        raise problem("No listener was named. Try: person, anthropic, jev, replay:<file>.")
    if spec.startswith("replay:"):
        transcript = Transcript(spec[len("replay:"):])
        return Listeners(transcript.model, transcript.judge, transcript.judges)
    if spec.startswith("record:"):
        path, inner = _split_record(spec[len("record:"):])
        transcript = Transcript(path, connect(inner))
        return Listeners(transcript.model, transcript.judge, transcript.judges)
    model = judge = judges = None
    for part in spec.split("+"):
        name, _, which = part.strip().partition(":")
        if name == "person":
            found = Person()
            found_model, found_judge, found_judges = found.model, found.judge, one_by_one(found.judge)
        elif name == "anthropic":
            found = Claude(which or CLAUDE)
            found_model, found_judge, found_judges = found.model, found.judge, found.judges
        elif name == "jev":
            found = Jev(which or JEV)
            found_model, found_judge, found_judges = None, found.judge, found.judges
        elif name == "openai":
            found_model, found_judge, found_judges = OpenAIWriter(which or "gpt-6-luna").model, None, None
        else:
            raise problem(f'I don\'t know a listener called "{name}". There are: person, anthropic, jev, openai, '
                          f'replay:<file> and record:<file>:<listener>.')
        model = model or found_model
        if judge is None and found_judge is not None:
            judge, judges = found_judge, found_judges  # the judge and its way of judging several go together
    return Listeners(model, judge, judges)

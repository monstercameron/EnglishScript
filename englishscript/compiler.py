"""The EnglishScript compiler.

One pass over the sentences does three jobs at once:

  * parses each sentence against the vocabulary defined so far,
  * checks it (every noun, pronoun, adjective and verb must resolve to exactly
    one meaning, and every value has a type),
  * and turns it into a Python closure.

Nothing runs until the whole program has compiled, so every "I can't read
this sentence" error is reported before the first line executes.

Along the way the compiler keeps notes on how it resolved anything the writer
left implicit ("its" -> the dragon). `--explain` prints those notes.

Types are plain strings: "number", "money", "text", "percent", "yes or no",
the name of a kind, "list of <one of those>", or any of those followed by "?"
for a value that may be nothing. The word `nothing` on its own has the type
"nothing", and a condition has the type "truth", which cannot be stored.

A `Try:` block undoes what it changed when a problem arises. Problems that may
be recovered from are raised as `EnglishError(..., recoverable=True)`; faults in
the program itself (an example that does not hold, a loop that runs away) are
not, and always end the program.
"""
from __future__ import annotations

import difflib
import importlib
import math
import os
import pkgutil
import re
import sys
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from dataclasses import dataclass, field
from fractions import Fraction

from . import libraries
from .lexer import (
    PROBLEM_KINDS, PROBLEM_NAMES, QUESTION_WORDS, RULES, EnglishError, Token, chapter_of, read_source, swap, tokenize,
)
from .runtime import (
    RECURSION_LIMIT, Env, Example, Reaction, Thing, World, _EndProgram, _Signal, alive, chance_of, expected, fmt,
    no_digit_limit, power, read_file, read_model_reply, read_number, read_reply, remainder, rounded, said, shortened,
    split_lines, square_root, thing_state, verdict_of, write_file,
)

BASE_TYPES = ("number", "money", "text", "percent")
POSSESSIVES = ("its", "their")
PRONOUNS = ("it", "they", "them")
PREPOSITIONS = {
    "with", "to", "from", "against", "for", "by", "on", "at", "into", "onto",
    "about", "over", "under", "as", "through", "toward", "towards", "upon",
}
ROLE_WORDS = PREPOSITIONS | {"of"}  # what may introduce a role of a worked-out value
BUILTIN_VERBS = (
    "let", "set", "add", "subtract", "multiply", "divide", "say", "if", "for",
    "repeat", "while", "there", "stop", "skip", "end",
)
KEYWORDS = PREPOSITIONS | set(BUILTIN_VERBS) | set(BASE_TYPES) | set(POSSESSIVES) | set(PRONOUNS) | {
    "a", "an", "the", "of", "is", "are", "not", "and", "or", "otherwise", "each",
    "be", "called", "whose", "when", "has", "never", "always", "than", "less",
    "more", "greater", "least", "most", "plus", "minus", "times", "divided",
    "divisible", "all", "example", "name", "nothing", "any", "else", "answer",
    "yes", "no", "now", "whether", "can", "in", "new", "remove", "ask", "write",
    "try", "fail", "reply", "problem", "list", "items", "use", "whenever", "becomes",
}
YES_NO = "yes or no"
LIST = "list of "
# What may follow "list of": the plural of a plain type.
LIST_PLURALS = {"numbers": "number", "money": "money", "text": "text", "percentages": "percent"}
ASKABLE = ("text", "number", "money", "percent", YES_NO)
PROBLEM = "\0problem"  # the hidden variable that holds "the problem"
PROBLEM_ERROR = "\0problem error"  # ... and the EnglishError itself, for its kind and for "Fail again."
# Words that start a sentence in other programming languages or in loose
# English, and what EnglishScript says instead (see Compiler.start_advice).
BORROWED = {
    **dict.fromkeys(("print", "println", "printf", "puts", "show", "display", "output", "echo", "log",
                     "tell", "console"), "say"),
    "else": "else",
    **dict.fromkeys(("elif", "elsif", "elseif"), "elif"),
    "return": "return",
    **dict.fromkeys(("delete", "destroy", "del", "free"), "remove"),
    **dict.fromkeys(("create", "make", "new"), "new"),
    **dict.fromkeys(("define", "def", "function", "func", "fn", "procedure", "method", "sub"), "define"),
    **dict.fromkeys(("var", "const", "constant", "final", "int", "float", "double", "string", "str",
                     "bool", "boolean", "auto", "dim"), "variable"),
    **dict.fromkeys(("increase", "increment", "inc"), "increase"),
    **dict.fromkeys(("decrease", "decrement", "dec"), "decrease"),
    **dict.fromkeys(("input", "read", "get", "prompt", "scan", "readline"), "ask"),
    **dict.fromkeys(("import", "include", "require", "using"), "use"),
    **dict.fromkeys(("loop", "foreach", "do"), "loop"),
    **dict.fromkeys(("endif", "endwhile", "endfor", "fi", "done", "wend"), "end"),
    "break": "break",
    **dict.fromkeys(("continue", "next"), "continue"),
    **dict.fromkeys(("exit", "quit"), "exit"),
}
ARTICLES_AT_START = ("the", "a", "an")
# Values from other languages, and what EnglishScript writes instead.
VALUE_WORDS = {
    "true": '"yes" for a yes-or-no value', "false": '"no" for a yes-or-no value',
    **dict.fromkeys(("null", "none", "nil", "undefined"), '"nothing" for a missing value'),
}
# What a reserved word already means, for a name that tries to use it.
def reserved_meaning(word):
    if word in BASE_TYPES:
        return "it is the name of a kind of value"
    if word in ("yes", "no"):
        return "it is a yes-or-no value"
    if word in ("a", "an", "the"):
        return "it is an article"
    if word in POSSESSIVES or word in PRONOUNS:
        return "it is a pronoun"
    if word in BUILTIN_VERBS or word in ("now", "remove", "ask", "write", "try", "fail", "use", "whenever"):
        return "it starts sentences of EnglishScript's own"
    if word in PREPOSITIONS:
        return "it links the roles of verbs"
    return "sentences are built with it"


# A word to use instead of a reserved one in a name, when one comes to mind.
INSTEAD = {
    "number": "count", "money": "cash", "text": "wording", "percent": "rate", "name": "title",
    "answer": "result", "problem": "trouble", "reply": "response", "list": "collection", "items": "pieces",
    "example": "sample", "new": "fresh", "end": "finish", "all": "whole", "each": "every", "nothing": "none",
}
# Words for comparing that EnglishScript writes another way, after "is".
BIGGER = ("bigger", "larger", "greater", "higher", "longer", "older", "heavier", "above", "over")
SMALLER = ("smaller", "lower", "fewer", "less", "shorter", "younger", "lighter", "below", "under")
# Words that may stand in front of a sentence in loose English, but add nothing.
FILLERS = ("please", "then", "next", "also", "so", "and", "just", "kindly", "finally", "first")
MATCH_WORDS = 12  # the most words a name may have and still be found
# Plurals not formed by the rule, for the hint that says how to state one.
IRREGULAR = {
    "mouse": "mice", "goose": "geese", "man": "men", "woman": "women", "child": "children", "person": "people",
    "foot": "feet", "tooth": "teeth", "ox": "oxen", "cactus": "cacti", "leaf": "leaves", "knife": "knives",
    "wife": "wives", "life": "lives", "wolf": "wolves", "half": "halves", "elf": "elves", "shelf": "shelves",
    "thief": "thieves", "calf": "calves", "loaf": "loaves", "potato": "potatoes", "hero": "heroes",
    "tomato": "tomatoes", "louse": "lice", "die": "dice", "fungus": "fungi", "criterion": "criteria",
}
LOOP_LIMIT = 1_000_000
CALL_LIMIT = 200
WHENEVER_LINE = re.compile(r"^[ ]*whenever\b", re.I | re.M)  # a "Whenever" in a library's SOURCE
NONE = frozenset()


def article(word):
    return ("an " if word[0].lower() in "aeiou" else "a ") + word


def pluralize(word):
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    if word.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    return word + "s"


def join_words(items, last="and"):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + f" {last} " + items[-1]


def is_opt(type_):
    return type_.endswith("?")


def base(type_):
    return type_[:-1] if type_.endswith("?") else type_


def opt(type_):
    return type_ if type_.endswith("?") or type_ == "nothing" else type_ + "?"


def is_list(type_):
    return base(type_).startswith(LIST)


def item_type(type_):
    return base(type_)[len(LIST):]


def where(line):
    """Where a definition was made, for messages: a line of the program, or a library."""
    if line.library:
        return f"in the {line.library} library"
    unit = getattr(line, "unit", None)
    if unit is not None and unit.kind == "chapter":
        return f"in {unit.title}, line {line.number}"
    return f"line {line.number}"


def block_span(lines):
    """(the first line's number, the last line's number) of a block and everything in it, or None."""
    if not lines:
        return None
    last = lines[-1]
    while getattr(last, "children", None):
        last = last.children[-1]
    return (lines[0].number, last.number)


def full_stop(sentence):
    """End a suggested sentence with a period, unless it already ends with "..."."""
    return sentence if sentence.endswith("...") else sentence + "."


def cap(text):
    """Capitalise the first letter, for a message that opens with a quoted phrase."""
    return text[:1].upper() + text[1:]


# ---------------------------------------------------------------- spelling


def distance(a, b):
    """How many letters must change to turn one word into the other, without
    regard to capitals: a letter put in, taken out or replaced, or two
    neighbouring letters swapped, each count as one."""
    a, b = a.lower(), b.lower()
    if a == b:
        return 0
    if abs(len(a) - len(b)) > 2:
        return 3  # more than any limit below
    rows = [list(range(len(b) + 1))]
    for i in range(1, len(a) + 1):
        row = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            row[j] = min(rows[-1][j] + 1, row[j - 1] + 1, rows[-1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                row[j] = min(row[j], rows[-2][j - 2] + 1)
        rows.append(row)
    return rows[-1][-1]


def close_words(word, candidates):
    """The candidates spelt nearly like `word`: one letter off for a word of up to
    four letters, two for a longer one. In the candidates' order, without repeats."""
    if len(word) < 3:
        return []  # one change turns a word of one or two letters into almost any other
    limit = 1 if len(word) <= 4 else 2
    found, seen = [], set()
    for candidate in candidates:
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        if 0 < distance(word, candidate) <= limit:
            found.append(candidate)
    return found


def some_of(words, near=None, most=8):
    """At most eight of `words`, without repeats; when there are more, the ones
    spelt most like `near`."""
    unique = list(dict.fromkeys(w for w in words if w))
    if len(unique) <= most:
        return unique
    if near is None:
        return unique[:most]
    ranked = sorted(unique, key=lambda w: (-difflib.SequenceMatcher(None, near.lower(), w.lower()).ratio(),
                                           unique.index(w)))
    keep = set(ranked[:most])
    return [w for w in unique if w in keep]


# ------------------------------------------------------------ leaving early


# _Signal (not an error: how Stop, Skip and The answer is leave a block) and
# _EndProgram live in runtime, because world.event must recognise the end.


class _StopVerb(_Signal):
    pass


class _StopLoop(_Signal):
    def __init__(self, loop):
        self.loop = loop


class _SkipRound(_Signal):
    def __init__(self, loop):
        self.loop = loop


class _Answer(_Signal):
    def __init__(self, value):
        self.value = value


# ---------------------------------------------------------------- libraries

DONE_BY_LIBRARY = ("is", "done", "by", "the", "library")
_MISMATCH = object()  # what from_library gives for a value of the wrong type


def call_library(lib, fn, world, roles):
    """Call a library's Python function. A problem it reports (EnglishError)
    and the signals for leaving early pass through; anything else it raises is
    a fault in the library, which ends the program."""
    try:
        return fn(world, **roles)
    except EnglishError as error:
        error.stage = "run"  # whatever the library wrote, it happened while running
        if error.problem is None and error.key not in ("rule_broken", "removed", "zero", "file", "count"):
            error.problem = "library problem"
        raise
    except _Signal:
        raise
    except Exception as error:  # noqa: BLE001 - a library's own fault, reported in English
        raise EnglishError(
            f"The {lib} library failed: {type(error).__name__}: {error}", stage="run",
            hint=f"This is a fault in the {lib} library, not in your program.", teach="library_run",
        ) from None


# ------------------------------------------------------------ asking a model

MODEL_TRIES = 3  # a reply that can't be read is asked for again, being told why, up to two more times
MODEL_FAULT = "This is a fault in what is connected as the model, not in your program."


def call_listener(fn, *args):
    """Ask whoever listens for "Ask the model" or "Judge" (World.model, World.judge). A
    problem it reports (EnglishError) is a problem of the program, of the kind "a bad
    reply" unless it says otherwise; anything else it raises is a fault in it, which
    ends the program, as a library's does."""
    try:
        return fn(*args)
    except EnglishError as error:
        error.stage = "run"  # whatever the listener wrote, it happened while running
        if error.problem is None and error.key in ("fail", "sentence_form"):
            error.teach("bad_reply")
        elif error.problem is None and error.key not in PROBLEM_KINDS:
            error.problem = "bad reply"
        else:
            error.teach(error.key)  # its category is now that of a problem while running
        raise
    except _Signal:
        raise
    except Exception as error:  # noqa: BLE001 - the listener's own fault, reported in English
        raise EnglishError(f"The model failed: {type(error).__name__}: {error}", stage="run", hint=MODEL_FAULT,
                           teach="model_fault") from None


def no_model():
    return EnglishError("No model is listening.", stage="run", recoverable=True, teach="no_model",
                        hint='Connect one with "--model", or ask a person instead inside "If that fails:".')


def bad_judgement(wanted, result):
    gave = "nothing" if result is None else f'"{shortened(repr(result))}"'
    return EnglishError(f"The model's judgement could not be used: {wanted}, and it gave {gave}.", stage="run",
                        recoverable=True, teach="bad_reply")


def ask_model(world, asked, about, shape):
    """Ask world.model (which is there) and read its reply as `shape` (Compiler.reply_shape),
    asking again, with a complaint, up to MODEL_TRIES times in all. The same question about
    the same state, for the same shape, is asked once in a run (World.answers)."""
    key = ("model", asked, about, shape["type"], tuple(shape["choices"] or ()), shape["items"], shape["optional"])
    if key in world.answers:
        return world.answers[key]
    value = _ask_model(world, asked, about, shape)
    world.answers[key] = value
    return value


def _ask_model(world, asked, about, shape):
    complaint = reply = None
    for _ in range(MODEL_TRIES):
        fresh = dict(shape, choices=list(shape["choices"]) if shape["choices"] else None)
        reply = call_listener(world.model, asked, about, fresh, complaint)
        if reply is None:
            raise EnglishError("The model gave no reply: it refused to answer, or its answer was cut short.",
                               stage="run", recoverable=True, teach="bad_reply")
        if not isinstance(reply, str):
            raise EnglishError(f"The model failed: it gave back {type(reply).__name__}, not text.",
                               stage="run", hint=MODEL_FAULT, teach="model_fault")
        read, value = read_model_reply(reply, shape)
        if read:
            return value
        complaint = (f'I could not read "{shortened(value)}": the reply has to be {expected(shape)}, and '
                     "nothing else.")
    raise EnglishError(f'The model\'s reply could not be read as {expected(shape)}: "{shortened(reply)}"',
                       stage="run", recoverable=True, teach="bad_reply")


def judge_request(asked, about, cset, scale=False):
    """One judgement, as the `judges` listener is given it (Program.run): a chance when
    `cset` is None; otherwise a verdict, or a grade when `scale` is true."""
    if cset is None:
        return {"question": asked, "state": about, "choices": None, "meanings": None, "scale": False}
    meanings = {display: cset.meanings[choice] for choice, display in zip(cset.choices, cset.displays)
                if choice in cset.meanings}
    return {"question": asked, "state": about, "choices": list(cset.displays), "meanings": meanings,
            "scale": bool(scale)}


def judge_key(request):
    """What a judgement is kept under in World.answers."""
    kind = "chance" if request["choices"] is None else "grade" if request["scale"] else "verdict"
    return ("judge", request["question"], request["state"], tuple(request["choices"] or ()), kind)


def fresh_request(request):
    """A copy for a listener, which may change what it is given."""
    return dict(request, choices=None if request["choices"] is None else list(request["choices"]),
                meanings=None if request["meanings"] is None else dict(request["meanings"]))


def judgement_of(result, request):
    """(the value, the likelihood of a verdict or grade) from what a judge gave for `request`,
    or a problem, "a bad reply", if it can't be used."""
    if request["choices"] is None:
        chance = chance_of(result)
        if chance is None:
            raise bad_judgement("a chance is a number from 0 to 1", result)
        return chance, None
    choices = request["choices"]
    chances = verdict_of(result, choices)
    if chances is None:
        raise bad_judgement(f"a verdict gives a chance from 0 to 1 to each of {join_words(choices)}, and to nothing "
                            "else", result)
    if request["scale"]:
        # A grade: the choices numbered 0, 1, 2 ... in the order written, the mean of those numbers
        # weighted by the chances, and the choice nearest it (a mean halfway goes to the higher one).
        total = sum(chances.values())
        if total == 0:
            raise bad_judgement("a grade needs a chance of more than 0 for at least one choice", result)
        mean = sum(number * chances[choice] for number, choice in enumerate(choices)) / total
        best = choices[min(len(choices) - 1, (mean + Fraction(1, 2)).__floor__())]
        return best, chances[best]
    best = choices[0]
    for choice in choices[1:]:
        if chances[choice] > chances[best]:  # a tie goes to the choice written first
            best = choice
    return best, chances[best]


def judges_answers(world, requests):
    """Put several judgements to world.judges at once: what it gave for each, in order."""
    results = call_listener(world.judges, [fresh_request(request) for request in requests])
    if not isinstance(results, (list, tuple)) or len(results) != len(requests):
        got = f"{len(results)} answers" if isinstance(results, (list, tuple)) else type(results).__name__
        raise EnglishError(f"The model failed: it was asked {len(requests)} questions at once and gave back {got}.",
                           stage="run", hint=MODEL_FAULT, teach="model_fault")
    return list(results)


def judgement_group(steps):
    """Consecutive judgements about one state (Compiler.group_judgements), as one step. With a
    `judges` listener, those not answered before in this run are put to it at once; otherwise
    each sentence is carried out by itself, in order. Either way, each gets the answer it
    would have got alone, and a problem is a problem at its own sentence, after the ones
    before it have kept their answers."""
    first = steps[0]

    def step(env):
        world = env.world
        if world.judges is None:
            for one in steps:
                one(env)
            return
        if world.trace is not None:
            world.traced(first.line)
        requests, failed = [], None
        for one in steps:
            try:
                requests.append(one.judging["prepare"](env))
            except EnglishError as error:
                if error.line is None:
                    error.line = one.line
                failed = error
                break
        keys = [judge_key(request) for request in requests]
        asking = [k for k, key in enumerate(keys) if key not in world.answers and key not in keys[:k]]
        given = {}
        if asking:
            try:
                given = dict(zip(asking, judges_answers(world, [requests[k] for k in asking])))
            except EnglishError as error:
                if error.line is None:
                    error.line = first.line
                raise
        for k, key in enumerate(keys):
            one = steps[k]
            if k and world.trace is not None:
                world.traced(one.line)
            if key not in world.answers:
                try:
                    world.answers[key] = judgement_of(given[k], requests[k])
                except EnglishError as error:
                    error.line = one.line
                    raise
            one.judging["finish"](env, world.answers[key])
        if failed is not None:
            if world.trace is not None and len(requests) > 0:
                world.traced(steps[len(requests)].line)
            raise failed
    step.line, step.answers, step.leaves, step.judging = first.line, False, False, None
    step.group = steps  # for tests and tools: the sentences put together
    return step


def ask_judge(world, asked, about, cset, scale=False):
    """Ask for one judgement (World.judge, or else World.judges with one question; one of them
    is there). Returns (the value, the likelihood of a verdict or grade). The same judgement
    is asked for once in a run (World.answers)."""
    request = judge_request(asked, about, cset, scale)
    key = judge_key(request)
    if key in world.answers:
        return world.answers[key]
    if world.judge is not None:
        fresh = fresh_request(request)
        result = call_listener(world.judge, fresh["question"], fresh["state"], fresh["choices"], fresh["meanings"])
    else:
        result = judges_answers(world, [request])[0]
    found = world.answers[key] = judgement_of(result, request)
    return found


def from_library(value, type_):
    """A value a library gave back, as the language holds it, or _MISMATCH."""
    if value is None:
        return None if is_opt(type_) else _MISMATCH
    type_ = base(type_)
    if is_list(type_):
        if not isinstance(value, (tuple, list)):
            return _MISMATCH
        items = tuple(from_library(item, item_type(type_)) for item in value)
        return _MISMATCH if any(item is _MISMATCH for item in items) else items
    if type_ == "text":
        return value if isinstance(value, str) else _MISMATCH
    if type_ == YES_NO:
        return value if isinstance(value, bool) else _MISMATCH
    if type_ in ("number", "money", "percent"):
        if isinstance(value, bool):
            return _MISMATCH
        if isinstance(value, (int, Fraction)):
            return Fraction(value)
        if isinstance(value, float) and math.isfinite(value):
            return Fraction(repr(value))  # the shortest repr, so 0.1 is exactly 1/10
        return _MISMATCH
    # A kind: a thing of that kind that is still in the world.
    if isinstance(value, Thing) and value.kind == type_ and not value.removed:
        return value
    return _MISMATCH


# --------------------------------------------------------------- vocabulary


class Unit:
    """One file of a program: the program itself, a chapter, or a library.

    Every definition remembers the unit it was made in. A name can be said in
    a file if it was defined there, or in a unit the file uses directly that
    shares it (Compiler.can_see).
    """

    def __init__(self, kind, name=None, folder=None, path=None, file=None):
        self.kind = kind  # "program", "chapter" or "library"
        self.name = name  # "calendar", "roman numerals", "paint"; None for the program
        self.folder = Path(folder) if folder is not None else None  # where its chapters are looked for
        self.path = path  # the file, resolved, if there is one
        self.file = file  # how messages name its file: "almanac/calendar.english"
        self.shares = None  # None: everything it defines; otherwise the set of names it shares
        self.share_at = {}  # shared name -> (line, column, width), where it is listed
        self.uses = set()  # the units this file uses directly
        self.used = {}  # what this file has said "Use" for -> the Line that says it
        self.used_at = None  # the first Line, in another file, that used it
        self.first = None  # its first sentence (the "shares" sentence must be it)
        Unit.made += 1
        self.number = Unit.made  # tells apart the private names of two files while running

    made = 0

    def shares_name(self, name):
        """Does this file share `name`? A file with no "shares" sentence shares everything."""
        return self.shares is None or name in self.shares

    def shared_list(self):
        """The names it shares, as they are written in its "shares" sentence."""
        return join_words(entry[3] for entry in self.share_at.values())

    @property
    def title(self):
        if self.kind == "chapter":
            return f"the {self.name} chapter"
        if self.kind == "library":
            return f"the {self.name} library"
        return "the program"

    def __repr__(self):
        return f"<{self.title}>"


class View(Mapping):
    """A registry as one file sees it.

    A name a file does not share is private to that file, and another file may
    give the same word a meaning of its own; so `all` keeps, for each key, every
    file's meaning, in the order made. Only what the file being compiled may say
    shows through, and the rules for names (Compiler.name_clash) make sure that
    at most one meaning of a key is ever in view in one file."""

    def __init__(self, visible, added=None, owner=None):
        self.all = {}  # key -> [value, ...]
        self.visible = visible  # (key, value) -> bool
        self.added = added  # called with each new key, to index its words
        # value -> (the file that made it, the name it is shared under, if it is)
        self.owner = owner or (lambda key, value: (value.unit, key))

    def _find(self, key):
        for value in self.all.get(key, ()):
            if self.visible(key, value):
                return value
        return _MISSING

    def __contains__(self, key):
        return self._find(key) is not _MISSING

    def __getitem__(self, key):
        value = self._find(key)
        if value is _MISSING:
            raise KeyError(key)
        return value

    def __iter__(self):
        return (key for key, values in list(self.all.items())
                if any(self.visible(key, value) for value in values))

    def __len__(self):
        return sum(1 for _ in self)

    def __setitem__(self, key, value):
        """Give `key` a meaning: in place of the one in view, if there is one."""
        values = self.all.get(key)
        if values is None:
            if self.added is not None:
                self.added(key, self)
            values = self.all[key] = []
        for k, old in enumerate(values):
            if self.visible(key, old):
                values[k] = value
                return
        values.append(value)

    def anywhere(self, key):
        """Every file's meaning of `key`, in the order made."""
        return list(self.all.get(key, ()))

    def first(self, key):
        """The first meaning of `key` made in any file, or None."""
        values = self.all.get(key)
        return values[0] if values else None

    def elsewhere(self, key):
        """For a message about a key this file may not say: the meaning another file
        shares, if one does (another file's private one can never be said), or the first."""
        values = self.all.get(key, ())
        for value in values:
            owner, name = self.owner(key, value)
            if owner is None or owner.shares_name(name):
                return value
        return values[0] if values else None

    def every(self):
        """(key, value) for every meaning in every file."""
        return [(key, value) for key, values in self.all.items() for value in values]

    def clash(self, key, unit, shared_as=None):
        """The meaning of `key` that a new one, made in `unit`, would collide with:
        the one in view, or, if `unit` shares the new one, one that another file
        shares (a shared name has one meaning in the whole program). Or None."""
        found = self._find(key)
        if found is not _MISSING:
            return found
        if unit is None or unit.shares_name(shared_as or key):
            for value in self.all.get(key, ()):
                owner, name = self.owner(key, value)
                if owner is not unit and (owner is None or owner.shares_name(name)):
                    return value
        return None


_MISSING = object()


class Named(tuple):
    """What a thing's name stands for: (as written, its kind), with the file that
    made it and the key it is kept under while running (World.named)."""

    def __new__(cls, display, kind, unit=None, slot=None):
        entry = super().__new__(cls, (display, kind))
        entry.unit, entry.slot = unit, slot
        return entry


class NameSet(set):
    """A set of names whose words are indexed as they are added (see Compiler.defined_word)."""

    def __init__(self, names, added):
        super().__init__()
        self.added = added
        self.update(names)

    def add(self, name):
        if name not in self:
            self.added(name, None)
        super().add(name)

    def update(self, names):
        for name in names:
            self.add(name)


@dataclass
class Kind:
    name: str
    plural: str
    line: object
    fields: dict = field(default_factory=dict)  # name -> type
    props: dict = field(default_factory=dict)  # name -> Prop (a View, from define_kind)
    adjectives: dict = field(default_factory=dict)  # name -> Adj (a View, from define_kind)
    rules: list = field(default_factory=list)  # [Rule]
    kept: dict = field(default_factory=dict)  # property, or ("adjective", name) -> the "Keep each" Line
    plural_used: bool = False  # has a sentence used its plural? (then it can't be stated another way)
    unit: object = None  # the file that described it
    word: str = None  # the word it is written with: `name` is its key, which differs for a private kind

    def __post_init__(self):
        if self.word is None:
            self.word = self.name


@dataclass
class Prop:
    name: str
    type: str
    fn: object  # (world, thing) -> value
    source: str
    unit: object = None


@dataclass
class Adj:
    name: str
    fn: object  # (world, thing) -> bool
    source: str
    stored: bool = False  # made with "can be", and changed with "Now"
    local: bool = True  # does it read only its own thing's stored properties? (for reactions)
    used: bool = False  # for the linter's "never used"
    unit: object = None
    line: object = None  # where it was defined
    mark: str = None  # a stored adjective: what Thing.marks holds for it (its name, unless it is private)

    def __post_init__(self):
        if self.mark is None:
            self.mark = self.name


@dataclass
class ChoiceSet:
    """A type with a fixed set of values: "A mood is one of sleepy, grumpy or content."."""
    name: str  # its key, which is its type
    word: str  # as written
    choices: list  # the choices, in lower case, in order
    unit: object = None
    line: object = None
    displays: list = None  # the choices as written, in order (what a value of the set holds)
    meanings: dict = field(default_factory=dict)  # choice (lower case) -> its meaning for the judge (section 7.8)


@dataclass
class Rule:
    fn: object  # (world, thing) -> bool, True when the rule holds
    text: str


@dataclass
class Param:
    name: str
    type: str
    prep: object  # None for the direct object
    at: tuple = None  # (column, width) of its name, for the linter
    by_kind: bool = False  # called by its kind ("To greet a dragon:"), with no name of its own

    def slot(self):
        return f"<{article(self.name)}>"


@dataclass
class Proc:
    verb: str
    params: list
    line: object
    body: list = None
    used: bool = False  # by a sentence outside its own block
    unit: object = None
    shapes: list = None  # every shape of this verb, the first being the one registered (define_procedure)

    def __post_init__(self):
        if self.shapes is None:
            self.shapes = [self]

    def prepositions(self):
        """What tells this shape from another: its linking words, with None for a direct object."""
        return frozenset(p.prep for p in self.params)

    def usage(self):
        parts = [self.verb.capitalize()]
        for p in self.params:
            parts.append(p.slot() if p.prep is None else f"{p.prep} {p.slot()}")
        return " ".join(parts) + "."


@dataclass
class Workout:
    name: str
    type: str
    params: list
    line: object
    body: list = None
    used: bool = False  # by a sentence outside its own block
    unit: object = None
    asks: bool = False  # is it one question to a model ("To work out ..., ask the model ...")?

    def usage(self):
        return " ".join([f"the {self.name}"] + [f"{p.prep} {p.slot()}" for p in self.params])


@dataclass
class Coll:
    kind: str
    fn: object  # env -> [Thing]


class Binding:
    __slots__ = ("name", "type", "focus", "let", "fixed", "reads", "unit", "slot")

    def __init__(self, name, type_, focus=False, let=False, fixed=False, slot=None):
        self.name = name
        self.type = type_
        self.focus = focus  # can a pronoun refer to it?
        self.let = let  # can it be changed with Set/Add/...?
        self.fixed = fixed  # made with "always"
        self.reads = 0  # how many sentences read it, for the linter
        self.unit = None  # for a top-level variable: the file that made it
        # Where its value is kept while running (Env.vars): the name, except for a variable
        # private to a file (another file may have one of its own), and for the thing a
        # definition is about, which is kept under its kind's key.
        self.slot = name if slot is None else slot


class Scope:
    """The names of a block, keyed by where their values are kept (Binding.slot,
    which is the name itself but for a top-level variable private to a file)."""

    def __init__(self, parent=None):
        self.parent = parent
        self.names = {}
        self.shown = None  # for the top level: binding -> may this file say it?
        self.own = None  # for the top level: name -> the slot of this file's private variable of that name

    def find(self, name):
        scope = self
        while scope is not None:
            b = scope.names.get(name)
            if b is not None and (scope.shown is None or scope.shown(b)):
                return b
            if scope.own is not None:
                own = scope.own(name)  # a private variable of the file being compiled, kept under its own slot
                b = scope.names.get(own) if own != name else None
                if b is not None:
                    return b
            scope = scope.parent
        return None

    def visible(self):
        """name -> Binding, for every name that may be said here."""
        seen, scope = {}, self
        while scope is not None:
            for b in scope.names.values():
                if scope.shown is None or scope.shown(b):
                    seen.setdefault(b.name, b)
            scope = scope.parent
        return seen


class Expr:
    """A compiled value or condition.

    `key` identifies where the value lives (a variable, a named thing, or a
    stored property reached from one), so the compiler can remember that it
    has been checked for nothing. A condition carries `nt` and `nf`: the keys
    known to be present when it turns out true, and when it turns out false.
    """

    __slots__ = ("type", "fn", "text", "span", "target", "literal", "subject",
                 "key", "declared", "check", "nt", "nf", "equal")

    def __init__(self, type_, fn, literal=False):
        self.type = type_
        self.fn = fn
        self.text = ""
        self.span = (0, 0)
        self.target = None
        self.literal = literal
        self.subject = None
        self.key = None
        self.declared = type_
        self.check = None
        self.nt = NONE
        self.nf = NONE
        self.equal = None  # for "<left> is <right>": (left, right), so a group may use an index


class Sentence:
    """A cursor over one sentence's tokens."""

    def __init__(self, line, tokens=None):
        self.line = line
        self.toks = tokens if tokens is not None else line.tokens
        self.i = 0

    def peek(self, k=0):
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def next(self):
        tok = self.toks[self.i]
        if tok.kind != "END":
            self.i += 1
        return tok

    def at_end(self):
        return self.peek().kind == "END"

    def at_word(self, *words):
        return self.peek().is_word(*words)

    def at_words(self, *seq):
        return all(self.peek(k).is_word(w) for k, w in enumerate(seq))

    def eat_word(self, *words):
        return self.next() if self.at_word(*words) else None

    def eat_punct(self, *marks):
        return self.next() if self.peek().is_punct(*marks) else None

    def expect_word(self, word, message=None, hint=None, teach="sentence_form"):
        """Read the fixed word `word` of a sentence form, or refuse the sentence.
        A near spelling of it, or "are" for "is", is refused with the correction."""
        if self.eat_word(word):
            return
        tok = self.peek()
        if tok.kind == "WORD":
            if word == "is" and tok.is_word("are"):
                self.fail(f'After one thing, write "is", not "{tok.text}".', tok, hint=hint, teach="is_are",
                          fix=self.replace(tok, "is"))
            if close_words(tok.text, [word]) and tok.low not in KEYWORDS:
                self.fail(f'I don\'t know the word "{tok.text}". Did you mean "{word}"?', tok, hint=hint,
                          teach=teach, category="spelling", fix=self.replace(tok, word))
        before = self.toks[self.i - 1].text if self.i > 0 else None
        where = f'After "{before}" comes' if before and self.toks[self.i - 1].kind == "WORD" else "This needs"
        self.fail(message or f'{where} "{word}" here.', hint=hint, teach=teach)

    def expect_punct(self, mark):
        if not self.eat_punct(mark):
            if mark == ")":
                self.fail('A bracket was opened but not closed: a ")" is missing here.', teach="brackets")
            self.fail(f'This needs "{mark}" here.', teach="sentence_form")

    def prev_end(self, default):
        return self.toks[self.i - 1].end if self.i > 0 else default

    def replace(self, tok, new):
        """The line with the words of `tok` replaced by `new` (in the same case at the start)."""
        if tok.text[:1].isupper() and new[:1].islower():
            new = new[:1].upper() + new[1:]
        return swap(self.line, tok.col, tok.end, new)

    def fail(self, message, tok=None, hint=None, teach=None, fix=None, category=None):
        tok = tok or self.peek()
        raise EnglishError(message, self.line, tok.col, max(1, len(tok.text)), hint, teach=teach, fix=fix,
                           category=category)

    def fail_span(self, message, span, hint=None, teach=None, fix=None, category=None):
        raise EnglishError(message, self.line, span[0], max(1, span[1] - span[0]), hint, teach=teach, fix=fix,
                           category=category)


# ----------------------------------------------------------------- compiler


class Compiler:
    def __init__(self, folder=None, name=None, read=None):
        # `read(path)` gives the text of a chapter that is open and unsaved in an editor, or None
        # to read the file from the disk (compile_source and lint pass it on).
        self.read = read
        # The files of the program. A definition belongs to the file it is in, and the
        # registries below show a file only what it may say (see Unit and View).
        folder = Path(folder) if folder is not None else Path.cwd()
        path = Path(os.path.abspath(folder / Path(name).name)) if name else None
        # Messages name the program's file as they name a chapter's: by its name, not its path.
        self.main = Unit("program", Path(name).stem if name else None, folder, path, Path(name).name if name else None)
        self.unit = self.main  # the file being compiled
        self.chapters = {}  # the resolved path of a chapter's file -> its Unit
        self.reading = []  # the chapters being compiled, outermost first, to find circles
        self.library_units = {}  # library name -> its Unit
        self.word_index = {}  # word -> [(a name with that word, its registry or None)], for defined_word
        index = self.index_words
        self.kinds = {}  # every kind; kind_visible says which a file may name
        self.nouns = View(lambda word, entry: self.kind_visible(entry[0]), index,  # word -> (kind's key, is_plural)
                          lambda word, entry: (self.kinds[entry[0]].unit, self.kinds[entry[0]].word))
        self.names = View(lambda key, entry: self.can_see(entry.unit, key), index)  # -> Named(display, kind)
        self.procs = View(lambda key, proc: self.can_see(proc.unit, key), index)
        # Sets of choices ("A mood is one of sleepy, grumpy or content."): the set's word -> its
        # ChoiceSet, and each choice -> Named(as written, the set's key).
        self.choice_sets = {}  # key -> ChoiceSet; the key is its type
        self.choice_names = View(lambda word, c: self.can_see(c.unit, word), index)
        self.choice_words = View(lambda key, entry: self.can_see(entry.unit, key), index)
        self.workouts = View(lambda key, w: self.can_see(w.unit, key), index)
        self.member_names = NameSet({"name"}, index)
        self.adjective_names = NameSet((), index)
        self.globals = Scope()
        self.globals.shown = lambda b: b.unit is None or self.can_see(b.unit, b.name)
        self.globals.own = lambda name: self.slot(name, self.unit)
        self.scope = self.globals
        self.notes = []
        self.line = None
        self._uid = 0
        # Where the sentence being compiled sits.
        self.verb = None  # the verb whose block this is, if any
        self.workout = None  # the worked-out value whose block this is, if any
        self.defining = False  # inside an adjective, a property, a rule or a kept value (see fresh)
        self.span = None  # (first, last) line of the block being compiled; None at the top level
        self.loops = []  # loops around the sentence: [{"id", "noun"}]
        # For the linter (englishscript/linter.py). Without it, a refused sentence is raised.
        self.lint = None  # the linter's collector, which records problems and carries on
        self.declared = []  # (what, name, line, column, width, is it used?) for "never used"
        self.defined = []  # (what, name, of which kind or None, Line, column, width): englishscript.names
        self.libraries = {}  # name -> (module, the "Use" line), in the order they were used
        self.library = None  # (name, module) while a library's SOURCE is being compiled
        self.present = NONE  # keys known not to be nothing at this point
        # Does the program (or a library it uses) say "Whenever"? Then a reaction may
        # follow any sentence that changes things: such sentences are watched while
        # running, and checks for nothing don't survive them. Set by `program`.
        self.reactive = False
        self.rule_for = None  # the kind whose never/always rule is being compiled (see rule_refuses)
        self.probe = None  # with rule_for, while an adjective is defined: {"local": does it read only its thing?}
        # While a loop's block is compiled to find out what it changes, a check for
        # nothing that looks needless is let through (see loop_body).
        self.lenient = False
        self.lenient_used = False
        self.in_thing_whose = 0  # inside a "whose" part of a thing being made (see whose_parts)
        self.group_ended = None  # where the last group with a "whose" ended, inside one
        self.made_at = {}  # the first word of a name -> (what, the name, its line): see not_an_adjective
        self.level = 0  # how many blocks deep the sentences being compiled are (Line.level, for the trace)
        self.kept_things = {}  # (a named thing's slot, property) -> the "Keep <thing>'s ..." Line

    # ------------------------------------------------------------- helpers

    def declare(self, what, name, line, at, used, of=None, **more):
        """Remember a name the program made, so the linter can say if it is never used.
        Only names of the main file: the other files are not its business."""
        self.defines({"value": "worked-out value"}.get(what, what), name, line, at[0], at[1], of, **more)
        if not line.library and getattr(line, "unit", None) in (None, self.main):
            self.declared.append((what, name, line, at[0], at[1], used))

    def defines(self, what, name, line, col, width, of=None, type_=None, roles=None, by_kind=False,
                span=False):
        """Remember where a name was defined, for the table of names (englishscript.names).
        `of` is the word of the kind an adjective or a property belongs to; `type_` its type,
        where it has one; `roles` a verb's or worked-out value's [(linking word, name, type)];
        `by_kind` says a role is called by its kind ("To greet a dragon:"); `span` is the
        (first, last) line of the block it belongs to, None for the top level, or False for
        the block being compiled. A library's word is kept with its library and no place."""
        more = {
            "type": None if type_ is None else self.type_text(type_),
            "by_kind": by_kind,
            "scope": self.span if span is False else span,
            "library": line.library or None,
        }
        if roles is not None:
            more["roles"] = [{"link": prep, "name": role, "type": self.type_text(t)} for prep, role, t in roles]
        if line.library:
            if more["scope"] is not None:
                return  # a name inside one of the library's blocks is not a word it brings
            col = width = None
        self.defined.append((what, name, of, line, col, width, more))

    def type_text(self, type_):
        """A type as it is written in brackets: "number", "dragon, if any", "list of text"."""
        if is_opt(type_):
            return self.type_text(base(type_)) + ", if any"
        if is_list(type_):
            return "list of " + self.plural_type(item_type(type_))
        if type_ in self.kinds:
            return self.kinds[type_].word
        if type_ in self.choice_sets:
            return self.choice_sets[type_].word
        return type_

    # Which names a file may say ----------------------------------------

    def can_see(self, unit, name):
        """May the file being compiled say `name`, defined in `unit`?"""
        here = self.unit
        if unit is None or unit is here:
            return True
        if unit not in here.uses:
            return False
        return unit.shares is None or name in unit.shares

    def kind_visible(self, kind):
        K = self.kinds.get(kind)
        return K is not None and self.can_see(K.unit, K.word)

    def kind_word(self, word):
        """The key of the kind this file may name with `word` (singular), or None."""
        noun = self.nouns.get(word)
        return noun[0] if noun is not None and not noun[1] else None

    @staticmethod
    def slot(name, unit):
        """Where a top-level name of `unit` is kept while running: the name itself if the
        file shares it, or else the name marked with the file, since another file may
        have a private name of its own spelt the same way."""
        if unit is None or unit.shares_name(name):
            return name
        return f"{name}\0{unit.number}"

    def owners(self):
        """Every name defined anywhere in the program -> (the unit that defined it,
        the name it is shared under, what it is). A shared meaning comes before a
        private one, which another file can never say."""
        found = {}

        def shared(entry):
            return entry[0] is None or entry[0].shares_name(entry[1])

        def put(name, unit, shares_as, what):
            entry = (unit, shares_as, what)
            if name not in found or (shared(entry) and not shared(found[name])):
                found[name] = entry
        for kind, K in self.kinds.items():
            put(K.word, K.unit, K.word, "kind")
            put(K.plural, K.unit, K.word, "kind")
        for key, entry in self.names.every():
            put(key, entry.unit, key, "thing")
        for verb, proc in self.procs.every():
            put(verb, proc.unit, verb, "verb")
        for name, w in self.workouts.every():
            put(name, w.unit, name, "worked-out value")
        for b in self.globals.names.values():
            if b.unit is not None:
                put(b.name, b.unit, b.name, "variable")
        for K in self.kinds.values():
            for name, prop in K.props.every():
                put(name, prop.unit, name, "property")
        return found

    def unseen(self, name, unit, shared, kind=None):
        """(message, hint) for a name that exists but may not be said in this file."""
        shown = f'"{name}"' if kind is None else f'"{name}" for {self.describe(kind)}'
        if unit in self.unit.uses:
            if unit.shares:
                hint = f"{cap(unit.title)} shares only {unit.shared_list()}."
            else:
                hint = f"{cap(unit.title)} shares nothing."
            return f"{shown} belongs to {unit.title}, which does not share it.", hint
        if unit.kind == "library":
            return (f"{shown} comes from {unit.title}, which this file does not use.",
                    f'Write "Use the {unit.name} library." first.')
        if unit.kind == "chapter":
            use = self.use_sentence(unit)
            if use is None:
                return (f"{shown} is in {unit.title}, which this file can't use.",
                        "A file can use the chapters beside it, and those of a book in its own folder or beside the program.")
            if unit.shares is not None and shared not in unit.shares:
                return (f"{shown} is in {unit.title}, which does not share it.",
                        f'{cap(unit.title)} shares only {unit.shared_list()}.' if unit.shares
                        else f"{cap(unit.title)} shares nothing.")
            return f"{shown} is in {unit.title}. Write \"{use}\" first.", None
        return f"{shown} is defined in {unit.title}, which this file does not use.", None

    def use_sentence(self, unit):
        """The sentence that would let this file use the chapter, or None if it can't."""
        here = self.unit.folder
        if here is None or unit.folder is None:
            return None
        if os.path.normcase(str(unit.folder)) == os.path.normcase(str(here)):
            return f"Use the {unit.name} chapter."
        main = self.main.folder
        if os.path.normcase(str(unit.folder.parent)) in (os.path.normcase(str(here)),
                                                         os.path.normcase(str(main)) if main else None):
            return f"Use the {unit.name} chapter of the {unit.folder.name.replace('_', ' ')} book."
        return None

    def hidden_here(self, s, offset=0):
        """If a name that exists in another file, but may not be said here, starts at
        the cursor, refuse it with a message that says why."""
        if not self.chapters and not self.library_units:
            return
        owners = self.owners()
        match = self.match_words(s, owners, offset)
        if not match:
            return
        name, count = match
        unit, shared, _ = owners[name]
        if self.can_see(unit, shared):
            return
        first, last = s.peek(offset), s.peek(offset + count - 1)
        message, hint = self.unseen(s.line.text[first.col:last.end], unit, shared)
        s.fail_span(message, (first.col, last.end), hint=hint)

    def hidden_adjective(self, s, tok, K):
        """Refuse an adjective of K that exists in another file but may not be said here."""
        adj = K.adjectives.first(tok.low) if tok.kind == "WORD" else None
        if adj is not None and not self.can_see(adj.unit, adj.name):
            message, hint = self.unseen(tok.low, adj.unit, adj.name, K.name)
            s.fail(message, tok, hint=hint)

    def elsewhere(self, unit):
        """' (in the calendar chapter)' when a name was defined in another file."""
        return "" if unit is None or unit is self.unit else f" (in {unit.title})"

    def note(self, text):
        if self.line.library or getattr(self.line, "unit", None) not in (None, self.main):
            return  # only the main file's sentences are explained
        entry = (self.line.number, text)
        if entry not in self.notes:
            self.notes.append(entry)

    def describe(self, type_):
        if type_ == "nothing":
            return "nothing"
        if is_opt(type_):
            return self.describe(base(type_)) + ", if any"
        if is_list(type_):
            return "a list of " + self.plural_type(item_type(type_))
        plain = {
            "number": "a plain number", "money": "money", "text": "text",
            "percent": "a percentage", "truth": "a yes-or-no answer", YES_NO: "a yes-or-no value",
        }
        if type_ in self.kinds and self.kind_visible(type_):
            return article(self.kinds[type_].word)  # a private kind's key also names its file
        if type_ in self.choice_sets:
            return article(self.choice_sets[type_].word)
        return plain.get(type_) or article(type_)

    def plural_type(self, type_):
        """How the items of a list are written after "list of"."""
        for plural, singular in LIST_PLURALS.items():
            if singular == type_:
                return plural
        return self.kinds[type_].plural

    def stamp(self, s, expr, start, end=None):
        end = s.prev_end(start) if end is None else end
        expr.span = (start, end)
        expr.text = s.line.text[start:end]
        return expr

    def end(self, s):
        if not s.at_end():
            rest = s.line.text[s.peek().col:s.toks[-1].col].strip() or s.peek().text
            s.fail(f'The sentence is complete before "{rest}", and I don\'t know what that part adds to it.',
                   hint="Take it out, or write it as a sentence of its own on the next line.", teach="sentence_form")

    def uid(self):
        self._uid += 1
        return self._uid

    def match_words(self, s, names, offset=0):
        """Longest of `names` (space-separated words, in lower case) found at the cursor.

        The words at the cursor are looked up, longest first, rather than every
        name tried in turn, so the cost does not grow with the vocabulary."""
        words = []
        while len(words) < MATCH_WORDS:
            tok = s.peek(offset + len(words))
            if tok.kind != "WORD":
                break
            words.append(tok.low)
        if not words:
            return None
        if not isinstance(names, (Mapping, set, frozenset)):
            names = set(names)
        for n in range(len(words), 0, -1):
            key = " ".join(words[:n])
            if key in names:
                return key, n
        return None

    def check_new_name(self, s, toks, what):
        for tok in toks:
            if tok.kind != "WORD":
                s.fail(f'This sentence needs {what} here, and "{tok.text}" is not a word.', tok, teach="names")
            if tok.low in KEYWORDS:
                other = INSTEAD.get(tok.low)
                hint = None
                if other and not self.defined_word(other):
                    hint = f'Choose another word, such as "{other}".'
                s.fail(f'The word "{tok.text}" already has a meaning in EnglishScript ({reserved_meaning(tok.low)}), '
                       f"so it can't be part of {what}.", tok, hint=hint, teach="reserved")

    def kinds_hint(self, near=None):
        kinds = some_of(self.visible_kinds(), near)
        return ("Kinds so far: " + ", ".join(kinds) + ".") if kinds else "No kind has been described yet."

    def misspelt(self, s, tok, candidates, teach, fix_for=None):
        """If exactly one of `candidates` is spelt nearly like the word `tok`, refuse it
        as a spelling mistake, with the correction. Returns the close candidates."""
        if tok.kind != "WORD":
            return []
        close = close_words(tok.text, candidates)
        if len(close) == 1:
            word = close[0]
            s.fail(f'I don\'t know the word "{tok.text}". Did you mean "{word}"?', tok, teach=teach,
                   category="spelling", fix=s.replace(tok, fix_for(word) if fix_for else word))
        return close

    def need_kind(self, s, tok):
        key = self.kind_word(tok.low) if tok.kind == "WORD" else None
        if key is not None:
            return self.kinds[key]
        if tok.kind != "WORD":
            s.fail('This sentence needs a kind here, such as "dragon".', tok, hint=self.kinds_hint(),
                   teach="unknown_kind")
        self.hidden_word(s, tok)
        noun = self.nouns.get(tok.low)
        if noun and noun[1]:  # "There is a dragons ..."
            s.fail(f'After "a", write one: "{article(self.word_of(noun[0]))}", not "a {tok.text}".', tok,
                   teach="number_agreement", fix=s.replace(tok, self.word_of(noun[0])))
        self.misspelt(s, tok, self.visible_kinds(), "unknown_kind")
        s.fail(
            f"I don't know what {article(tok.text)} is.", tok,
            hint=f'Describe it first: "{article(tok.text).capitalize()} has ...".\n' + self.kinds_hint(tok.text),
            teach="unknown_kind",
        )

    def hidden_word(self, s, tok):
        """hidden_here, for a single word that has been read already."""
        if tok.kind == "WORD" and (self.chapters or self.library_units):
            owners = self.owners()
            if tok.low in owners:
                unit, shared, _ = owners[tok.low]
                if not self.can_see(unit, shared):
                    message, hint = self.unseen(tok.text, unit, shared)
                    s.fail(message, tok, hint=hint, teach="shared")

    def visible_kinds(self):
        """The words of the kinds this file may name."""
        return [K.word for kind, K in self.kinds.items() if self.kind_visible(kind)]

    def word_of(self, kind):
        """The word a kind is written with, from its key (they differ for a private kind)."""
        K = self.kinds.get(kind)
        return K.word if K is not None else kind

    def type_name(self, s, tok, also=None):
        """The type a word names: a plain type or a kind's key. `also` is (word, key) of
        the kind being described, which may be the type of its own properties."""
        if tok.kind == "WORD":
            if tok.low in BASE_TYPES:
                return tok.low
            key = self.kind_word(tok.low)
            if key is not None:
                return key
            if tok.low in self.choice_names:
                return self.choice_names[tok.low].name
            if also and tok.low == also[0]:
                return also[1]
        self.hidden_word(s, tok)
        known = list(BASE_TYPES) + self.visible_kinds() + ([also[0]] if also and also[1] not in self.kinds else [])
        if tok.kind == "WORD" and tok.low in self.nouns and self.nouns[tok.low][1]:
            single = self.word_of(self.nouns[tok.low][0])
            s.fail(f'In brackets, a kind is written in the singular: "{single}", not "{tok.text}".', tok,
                   teach="number_agreement", fix=s.replace(tok, single))
        self.misspelt(s, tok, known, "types")
        s.fail(f'"{tok.text}" is not a type.', tok,
               hint="Types: " + ", ".join(known[:4] + ["yes or no", "list of ..."] + known[4:]) + ".", teach="types")

    def bracket_type(self, s, also=None):
        """The inside of "(money)", "(dragon, if any)", "(yes or no)" or "(list of text)".

        The "(" is already read.
        """
        if s.at_words("yes", "or", "no"):
            for _ in range(3):
                s.next()
            type_ = YES_NO
        elif s.at_words("list", "of"):
            s.next()
            s.next()
            tok = s.next()
            if tok.is_word(*LIST_PLURALS):
                type_ = LIST + LIST_PLURALS[tok.low]
            elif tok.kind == "WORD" and self.nouns.get(tok.low, (None, False))[1]:
                type_ = LIST + self.nouns[tok.low][0]
                self.kinds[type_[len(LIST):]].plural_used = True
            elif also and len(also) > 2 and tok.is_word(also[2]):  # the kind being described, in the plural
                type_ = LIST + also[1]
            else:
                self.hidden_word(s, tok)
                plurals = list(LIST_PLURALS) + [K.plural for k, K in self.kinds.items() if self.kind_visible(k)]
                if tok.kind == "WORD" and tok.low in self.nouns:  # "list of dragon"
                    s.fail(f'After "list of", write the plural: "{self.kinds[self.nouns[tok.low][0]].plural}".', tok,
                           teach="number_agreement", fix=s.replace(tok, self.kinds[self.nouns[tok.low][0]].plural))
                if tok.low in ("number", "percent", "percentage"):
                    plural = "numbers" if tok.low == "number" else "percentages"
                    s.fail(f'After "list of", write the plural: "{plural}".', tok, teach="number_agreement",
                           fix=s.replace(tok, plural))
                self.misspelt(s, tok, plurals, "types")
                s.fail(
                    f'I don\'t know what a list of "{tok.text}" is.', tok,
                    hint="After \"list of\" comes a plural: " + ", ".join(some_of(plurals, tok.text)) + ".",
                    teach="types",
                )
        else:
            type_ = self.type_name(s, s.next(), also)
        if s.eat_punct(","):
            if not (s.eat_word("if") and s.eat_word("any")):
                s.fail('After the comma in brackets comes "if any", as in "(dragon, if any)".', teach="types")
            type_ = opt(type_)
        s.expect_punct(")")
        return type_

    def fits(self, have, want):
        """May a value of type `have` go where `want` is expected?"""
        if have == want:
            return True
        return is_opt(want) and (have == "nothing" or have == base(want))

    def need(self, s, expr):
        """Refuse a value that may be nothing where a value is required."""
        if expr.type == "nothing":
            s.fail_span('"Nothing" can\'t be used as a value here.', expr.span,
                        hint='To test for it, write "is nothing" or "is not nothing".', teach="maybe_nothing")
        if is_opt(expr.type):
            check = expr.check or f"If {expr.text} is not nothing:"
            s.fail_span(
                f"{cap(expr.text)} may be nothing.", expr.span,
                hint=f'Check first with "{check}", or give a stand-in with "or else".', teach="maybe_nothing",
            )

    @contextmanager
    def fresh(self, verb=None, workout=None, chapter=False):
        """Compile a definition: it must not lean on where it happens to be written."""
        saved = (self.verb, self.workout, self.loops, self.present, self.defining)
        self.verb, self.workout, self.loops, self.present = verb, workout, [], NONE
        # Neither a verb nor a worked-out value: an adjective, a property, a rule or a kept value,
        # which are worked out whenever they are needed, and so may not ask a model.
        self.defining = verb is None and workout is None and not chapter
        try:
            yield
        finally:
            self.verb, self.workout, self.loops, self.present, self.defining = saved

    def subject_scope(self, kind):
        """The scope of a definition about a thing of `kind` (its key): the thing is
        "the <kind>", written with the kind's word, and kept under the key."""
        word = self.kinds[kind].word
        scope = Scope(self.globals)
        scope.names[word] = Binding(word, kind, focus=True, slot=kind)
        return scope

    @staticmethod
    def subject_fn(kind, fn):
        """Wrap an env-closure so it can be asked about one particular thing."""
        def ask(world, thing):
            env = Env(world.globals)
            env.vars[kind] = thing
            return fn(env)
        return ask

    # Remembering what has been checked for nothing ----------------------

    @staticmethod
    def mentions(key, what):
        """Does the path `key` pass through the field or variable `what`?"""
        while key is not None:
            if key[0] != "field":
                return key == what
            if what == ("field", key[2]):
                return True
            key = key[1]
        return False

    def forget(self, what):
        self.present = frozenset(k for k in self.present if not self.mentions(k, what))

    def forget_after_verb(self):
        """A verb may change any thing and any top-level variable."""
        self.present = frozenset(
            k for k in self.present if k[0] == "var" and k[1] not in self.globals.names
        )

    def needless(self, expr):
        """Is a check for nothing to be let through, although the value is known to be
        there? Only while a loop's block is compiled leniently (see loop_body), and only
        for a value that may be nothing, known to be there from an earlier check."""
        if expr is None or not self.lenient or not is_opt(expr.declared):
            return False
        self.lenient_used = True
        return True

    def settle(self, expr):
        if expr.key is not None and is_opt(expr.type) and expr.key in self.present:
            expr.type = base(expr.type)
        return expr

    # Properties ---------------------------------------------------------

    def getter(self, kind, name):
        """(type, fn(world, thing)) for a field, a defined property, or the name."""
        K = self.kinds[kind]
        if name in K.fields and self.kind_visible(kind):  # a kind's properties come with it
            return K.fields[name], (lambda world, thing: alive(thing).fields[name])
        if name in K.props:
            worked_out = K.props[name].fn
            return K.props[name].type, (lambda world, thing: worked_out(world, alive(thing)))
        if name == "name":
            return "text", (lambda world, thing: alive(thing).name)
        return None

    def member_list(self, kind):
        K = self.kinds[base(kind)]
        fields = list(K.fields) if self.kind_visible(K.name) else []
        return ["name"] + fields + list(K.props)

    def match_member(self, s, kind, offset=0):
        return self.match_words(s, self.member_list(kind), offset)

    def no_member(self, s, kind, offset=0):
        kind = base(kind)
        tok = s.peek(offset)
        K = self.kinds[kind]
        hidden = self.match_words(s, list(K.fields) + list(K.props.all), offset)  # every file's
        if hidden and (self.chapters or self.library_units):
            name = hidden[0]
            prop = K.props.elsewhere(name)
            unit, shared = (prop.unit, name) if prop is not None else (K.unit, kind)
            if not self.can_see(unit, shared):
                message, hint = self.unseen(name if prop is not None else kind, unit, shared)
                if prop is None:
                    message = f'The properties of {self.describe(kind)} come with the kind. ' + message
                s.fail(message, tok, hint=hint, teach="shared")
        members = self.member_list(kind)
        self.misspelt(s, tok, members, "unknown_property")
        what = f'no "{tok.text}"' if tok.kind == "WORD" else "nothing by that description"
        s.fail(
            f"{self.describe(kind).capitalize()} has {what}.", tok,
            hint=f"{self.describe(kind).capitalize()} has: " + ", ".join(some_of(members, tok.text)) + ".",
            teach="unknown_property",
        )

    def member(self, s, owner, match, start=None):
        name, count = match
        at = s.peek().col
        for _ in range(count):
            s.next()
        self.rule_member(s, owner, name, (owner.span[0] if start is None else start, s.prev_end(at)))
        return self.stamp(s, self.member_expr(owner, name), owner.span[0] if start is None else start)

    def rule_member(self, s, owner, name, span):
        """Inside a rule, only the thing's own stored properties (and its name) may be read."""
        if self.rule_for is None:
            return
        if owner.key != ("var", self.rule_for):
            self.rule_refuses(s, span, f'a property of another thing ("{s.line.text[span[0]:span[1]]}")')
        if name != "name" and name not in self.kinds[self.rule_for].fields:
            self.rule_refuses(s, span, f'the worked-out property "{name}"',
                              hint="A worked-out property may read other things, which change without the rule "
                                   "being checked.")

    def member_expr(self, owner, name):
        kind = base(owner.type)
        type_, get = self.getter(kind, name)
        owner_fn = owner.fn
        maybe = is_opt(owner.type)
        if maybe:
            # A property of something that may be nothing may itself be nothing.
            def fn(env):
                thing = owner_fn(env)
                return None if thing is None else get(env.world, thing)
            expr = Expr(opt(type_), fn)
            expr.check = owner.check or f"If {owner.text} is not nothing:"
        else:
            expr = Expr(type_, lambda env: get(env.world, owner_fn(env)))
        K = self.kinds[kind]
        if name in K.fields:
            expr.target = ("maybe", owner) if maybe else ("field", owner, name, K)
            if owner.key is not None:
                expr.key = ("field", owner.key, name)
            if not maybe and is_opt(type_):
                expr.check = f"If {owner.text} has {article(name)}:"
        elif name in K.props:
            expr.target = ("prop", K.props[name])
            self.note(f'"{name}" → {K.props[name].source}')
        return self.settle(expr)

    def adjectives_hint(self, kind, near=None):
        names = some_of(self.kinds[kind].adjectives, near)
        if not names:
            return f"No adjective has been defined for {self.describe(kind)} yet."
        return f"Adjectives for {self.describe(kind)}: " + ", ".join(names) + "."

    def unknown_adjective(self, s, tok, kind, also=()):
        """Refuse a word that stands where an adjective of `kind` belongs. `also` are
        other words that could stand there (the names of things of that kind)."""
        self.hidden_adjective(s, tok, self.kinds[kind])
        self.misspelt(s, tok, list(self.kinds[kind].adjectives) + list(also), "unknown_adjective")
        hint = self.adjectives_hint(kind, tok.text)
        if tok.kind == "WORD" and tok.low not in KEYWORDS and not self.defined_word(tok.low):
            hint = f'Define it first: "{self.describe(kind).capitalize()} is {tok.text} when ...".\n' + hint
        s.fail(f'I don\'t know what "{tok.text}" means for {self.describe(kind)}.', tok, hint=hint,
               teach="unknown_adjective")

    # --------------------------------------------------------- expressions

    def expr(self, s):
        start = s.i
        left = self.sum(s)
        while s.at_words("or", "else"):
            left_end = s.i
            s.next()
            s.next()
            right_start = s.i
            right = self.sum(s)
            # "X or else 0 + 1" reads two ways: "or else" never stands beside + - * / unbracketed.
            for a, b in ((start, left_end), (right_start, s.i)):
                op = self.top_op(s, a, b)
                if op is not None:
                    self.or_else_mixed(s, start, left_end, right_start, s.i, op)
            left = self.or_else(s, left, right)
        return left

    @staticmethod
    def top_op(s, a, b):
        """The first + - * / (or plus, minus, times, divided by) among s.toks[a:b] that is
        not inside brackets and not a minus sign in front of a value; or None."""
        depth = 0
        for k in range(a, b):
            tok = s.toks[k]
            if tok.is_punct("("):
                depth += 1
            elif tok.is_punct(")"):
                depth -= 1
            elif depth == 0 and k > a and (tok.is_punct("+", "-", "*", "/")
                                           or tok.is_word("plus", "minus", "times", "divided")):
                prev = s.toks[k - 1]
                if tok.is_punct("-") and (prev.kind == "PUNCT" and not prev.is_punct(")")):
                    continue  # a minus sign: "2 * -3"
                return k
        return None

    @staticmethod
    def rest_end(s, op):
        """Where the condition or value that `op` stands in ends: at the sentence's end,
        or at the bracket that closes the one it is in."""
        depth = 0
        for tok in s.toks:
            if tok.col <= op.col or tok.kind == "END":
                continue
            depth += tok.is_punct("(") - tok.is_punct(")")
            if depth < 0:
                return tok.col
        return s.toks[-1].col

    def whether_mixed(self, s, whether, first, op):
        """Refuse "whether A and B" with its two readings."""
        text = s.line.text
        a = text[first.col:op.col].strip()
        rest = text[op.end:self.rest_end(s, op)].strip()
        readings = (f"  (1) whether ({a} {op.text} {rest})\n"
                    f"  (2) (whether {a}) {op.text} {rest}")
        s.fail(f'"whether" followed by "{op.text}" can be read two ways:', op,
               hint=readings + "\nPut brackets round the condition that belongs to \"whether\".", teach="value_order")

    def or_else_mixed(self, s, start, left_end, right_start, end, op):
        """Refuse "X or else 0 + 1" with its two readings."""
        text, toks = s.line.text, s.toks

        def words(a, b):
            return text[toks[a].col:toks[b - 1].end].strip() if b > a else ""
        or_else = words(left_end, right_start)
        if op < left_end:  # "a + b or else c"
            a, b = words(start, op), words(op, left_end)
            readings = (f"  (1) ({a} {b}) {or_else} {words(right_start, end)}\n"
                        f"  (2) {a} {toks[op].text} ({words(op + 1, left_end)} {or_else} {words(right_start, end)})")
        else:  # "a or else b + c"
            first, rest = words(right_start, op), words(op, end)
            readings = (f"  (1) ({words(start, left_end)} {or_else} {first}) {rest}\n"
                        f"  (2) {words(start, left_end)} {or_else} ({words(right_start, end)})")
        s.fail(f'"{or_else}" beside "{toks[op].text}" can be read two ways:', toks[op],
               hint=readings + "\nPut brackets round the part that belongs together.", teach="value_order")

    def or_else(self, s, left, right):
        if not is_opt(left.type) and not self.needless(left):
            s.fail_span(f'{cap(left.text)} is never nothing here, so "or else" isn\'t needed.', left.span,
                        hint=f"Write just: {left.text}", teach="nothing_checks")
        want = base(left.type)
        if base(right.type) != want:
            s.fail_span(
                f"{cap(left.text)} is {self.describe(want)}, but the stand-in {right.text} is {self.describe(right.type)}.",
                right.span, teach="fit",
            )
        lf, rf = left.fn, right.fn

        def fn(env):
            value = lf(env)
            return rf(env) if value is None else value
        return self.stamp(s, Expr(right.type, fn), left.span[0], right.span[1])

    def sum(self, s):
        left = self.term(s)
        while True:
            tok = s.peek()
            if tok.is_punct("+") or tok.is_word("plus"):
                op = "+"
            elif tok.is_punct("-") or tok.is_word("minus"):
                op = "-"
            else:
                return left
            s.next()
            left = self.arith(s, op, left, self.term(s))

    def term(self, s):
        left = self.unary(s)
        while True:
            tok = s.peek()
            if tok.is_punct("*") or (tok.is_word("times") and s.peek(1).kind != "END"):
                op = "*"
                s.next()
            elif tok.is_punct("/"):
                op = "/"
                s.next()
            elif s.at_words("divided", "by"):
                op = "/"
                s.next()
                s.next()
            else:
                return left
            left = self.arith(s, op, left, self.unary(s))

    def unary(self, s):
        tok = s.peek()
        if tok.is_punct("-"):
            s.next()
            inner = self.unary(s)
            self.need(s, inner)
            if inner.type not in ("number", "money", "percent"):
                s.fail_span(f"I can't make {self.describe(inner.type)} negative: only a number, money or a "
                            "percentage can be.", inner.span, teach="arith")
            fn = inner.fn
            return self.stamp(s, Expr(inner.type, lambda env: -fn(env)), tok.col)
        expr = self.postfix(s, self.primary(s))
        if expr.type == "percent" and s.at_word("of"):
            s.next()
            amount = self.unary(s)
            self.need(s, amount)
            if amount.type not in ("number", "money"):
                s.fail_span(f"I can't take a percentage of {self.describe(amount.type)}: only of a number or money.",
                            amount.span, teach="percent")
            pf, bf = expr.fn, amount.fn
            expr = self.stamp(s, Expr(amount.type, lambda env: pf(env) * bf(env)), expr.span[0])
        return expr

    def need_text(self, s, expr, doing):
        self.need(s, expr)
        if expr.type != "text":
            s.fail_span(f"I can only {doing} text, but {expr.text} is {self.describe(expr.type)}.", expr.span,
                        teach="text_only")

    def postfix(self, s, expr):
        """'<text> in upper case', '<text> in lower case' and '<text> as a number'.

        They apply to the whole value before them, so "the length of the title
        in upper case" asks to upper-case a number, and is refused.
        """
        while True:
            if s.at_words("in", "upper", "case") or s.at_words("in", "lower", "case"):
                upper = s.peek(1).is_word("upper")
                self.need_text(s, expr, "change the case of")
                for _ in range(3):
                    s.next()
                new = Expr("text", self.case_fn(expr.fn, upper))
            elif s.at_words("joined", "with") and is_list(expr.type):
                self.need(s, expr)
                item = item_type(expr.type)
                if item not in ("text", "number", "money", "percent"):
                    s.fail_span(f"{cap(expr.text)} is {self.describe(expr.type)}, and only a list of text, numbers, "
                                "money or percentages can be joined into text yet.", expr.span, teach="list",
                                hint='Go through it with "For each" and fill each name into a text.')
                s.next()
                s.next()
                between = self.primary(s)
                self.need(s, between)
                if between.type != "text":
                    s.fail_span(f'"Joined with" takes text to put between the items, but {between.text} is '
                                f"{self.describe(between.type)}.", between.span, teach="text_only")
                lf, bf = expr.fn, between.fn
                new = Expr("text", lambda env, lf=lf, bf=bf, item=item:
                           bf(env).join(fmt(v, item) for v in lf(env)))
            elif s.at_word("rounded") and (s.at_words("rounded", "to", "the", "nearest")
                                           or s.at_words("rounded", "up", "to", "the", "nearest")
                                           or s.at_words("rounded", "down", "to", "the", "nearest")):
                s.next()
                how = s.next().low if s.at_word("up", "down") else "nearest"
                for _ in range(3):
                    s.next()
                step = self.primary(s)
                self.need(s, expr)
                self.need(s, step)
                if expr.type not in ("number", "money", "percent") or step.type != expr.type:
                    s.fail_span(f"Rounding needs a number, money or a percentage, and a step of the same sort: "
                                f"{expr.text} is {self.describe(expr.type)}, and {step.text} is "
                                f"{self.describe(step.type)}.", (expr.span[0], step.span[1]), teach="arith")
                vf, sf = expr.fn, step.fn
                new = Expr(expr.type, lambda env, vf=vf, sf=sf, how=how: rounded(vf(env), sf(env), how))
            elif s.at_words("raised", "to", "the", "power", "of"):
                for _ in range(5):
                    s.next()
                exponent = self.primary(s)
                for side in (expr, exponent):
                    self.need(s, side)
                    if side.type != "number":
                        s.fail_span(f"A power is taken of plain numbers, but {side.text} is "
                                    f"{self.describe(side.type)}.", side.span, teach="arith")
                vf, ef = expr.fn, exponent.fn
                new = Expr("number", lambda env, vf=vf, ef=ef: power(vf(env), ef(env)))
            elif s.at_words("as", "a", "number"):
                self.need_text(s, expr, "read a number from")
                for _ in range(3):
                    s.next()
                fn = expr.fn
                new = Expr("number?", lambda env, fn=fn: read_number(fn(env)))
            else:
                return expr
            expr = self.stamp(s, new, expr.span[0])

    @staticmethod
    def case_fn(fn, upper):
        if upper:
            return lambda env: fn(env).upper()
        return lambda env: fn(env).lower()

    def arith(self, s, op, left, right):
        self.need(s, left)
        self.need(s, right)
        lt, rt = left.type, right.type
        result = None
        if op in "+-":
            if lt == rt and lt in ("number", "money", "percent"):
                result = lt
        elif op == "*":
            if lt == rt == "number":
                result = "number"
            elif {lt, rt} == {"money", "number"}:
                result = "money"
            elif {lt, rt} == {"percent", "number"}:
                result = "percent"
        else:
            if lt == rt and lt in ("number", "money", "percent"):
                result = "number"
            elif lt in ("money", "percent") and rt == "number":
                result = lt
        span = (min(left.span[0], right.span[0]), max(left.span[1], right.span[1]))
        if result is None:
            L, R = self.describe(lt), self.describe(rt)
            message = {
                "+": f"I can't add {R} to {L}.",
                "-": f"I can't subtract {R} from {L}.",
                "*": f"I can't multiply {L} by {R}.",
                "/": f"I can't divide {L} by {R}.",
            }[op]
            hint = None
            for side, other in ((left, right), (right, left)):
                if side.literal and side.type == "number" and other.type == "money" and op in "+-":
                    hint = f"If you meant money, write ${side.text}."
            s.fail_span(message, span, hint, teach="arith")
        lf, rf = left.fn, right.fn
        if op == "+":
            fn = lambda env: lf(env) + rf(env)
        elif op == "-":
            fn = lambda env: lf(env) - rf(env)
        elif op == "*":
            fn = lambda env: lf(env) * rf(env)
        else:
            zero = "$0" if right.type == "money" else "0"
            check = f"{right.text} was {zero}. Check it first: If {right.text} is not {zero}:"

            def fn(env):
                divisor = rf(env)
                if divisor == 0:
                    raise EnglishError("I can't divide by zero.", stage="run", recoverable=True, teach="zero",
                                       hint=check)
                return lf(env) / divisor
        return self.stamp(s, Expr(result, fn), span[0], span[1])

    def primary(self, s, dangling_ok=False):
        tok = s.peek()
        start = tok.col
        if tok.kind in ("NUMBER", "MONEY", "PERCENT"):
            s.next()
            value = tok.value
            expr = Expr(tok.kind.lower(), lambda env: value, literal=True)
        elif tok.kind == "STRING":
            s.next()
            expr = self.template(s, tok)
        elif tok.is_punct("("):
            s.next()
            expr = self.expr(s)
            s.expect_punct(")")
        elif tok.is_punct("-") and s.peek(1).kind in ("NUMBER", "MONEY", "PERCENT", "WORD", "PUNCT") \
                and not s.peek(1).is_punct("-"):
            # A minus sign in front of a single value, wherever a single value may stand: "the double of -3".
            s.next()
            inner = self.primary(s)
            self.need(s, inner)
            if inner.type not in ("number", "money", "percent"):
                s.fail_span(f"I can't make {self.describe(inner.type)} negative: only a number, money or a "
                            "percentage can be.", inner.span, teach="arith")
            fn = inner.fn
            expr = Expr(inner.type, lambda env: -fn(env))
        elif tok.kind == "WORD":
            if tok.low in POSSESSIVES:
                s.next()
                owner = self.stamp(s, self.pronoun(s, tok), start)
                match = self.match_member(s, owner.type)
                if not match:
                    self.no_member(s, owner.type)
                expr = self.member(s, owner, match)
            elif tok.low in PRONOUNS:
                s.next()
                expr = self.pronoun(s, tok)
            elif tok.low == "the":
                expr = self.the_phrase(s)
            elif tok.low == "nothing":
                s.next()
                expr = Expr("nothing", lambda env: None, literal=True)
            elif tok.low in ("yes", "no"):
                s.next()
                truth = tok.low == "yes"
                expr = Expr(YES_NO, lambda env: truth, literal=True)
            elif tok.low == "whether":
                s.next()
                first = s.peek()
                found = self.cond_atom(s)  # one comparison, or a bracketed condition
                if s.at_word("and", "or"):
                    self.whether_mixed(s, tok, first, s.peek())
                cond = found.fn
                expr = Expr(YES_NO, lambda env: bool(cond(env)))
            elif s.at_words("a", "list", "of") or s.at_words("an", "empty", "list", "of"):
                s.fail("A list can be written out only as the whole value of \"Let\", \"Set\", a \"whose\" part or "
                       "\"The answer is\", so that its commas and \"and\" can't be taken for anything else.", tok,
                       hint='Make it first: "Let the scores be a list of 3, 8 and 5." Then use "the scores".',
                       teach="list")
            elif tok.low in ("a", "an") and s.peek(1).is_word("new"):
                s.fail(
                    'A new thing can only be made as the whole value of "Let", or with "There is a new ...".', tok,
                    hint='For example: "Let the chick be a new dragon whose age is 0."', teach="new_thing",
                )
            else:
                expr = None
                if tok.low in ("item", "letter") and not (self.match_words(s, self.names) or ("", 0))[1] > 1 \
                        and not (self.match_words(s, self.scope.visible()) or ("", 0))[1] > 1:
                    expr = self.list_item(s)
                if expr is None:
                    expr = self.bare_name(s)
        else:
            self.no_value(s, tok)
        self.stamp(s, expr, start)
        while s.peek().kind == "POS":
            if base(expr.type) not in self.kinds:
                s.fail_span(f"{cap(expr.text)} is {self.describe(expr.type)}, so it has no properties.", expr.span,
                            teach="props_of")
            match = self.match_member(s, expr.type, 1)
            if not match:
                if dangling_ok:
                    break
                self.no_member(s, expr.type, 1)
            s.next()
            expr = self.member(s, expr, match, start)
        return expr

    def no_value(self, s, tok):
        """Refuse a sentence where a value belongs and there is none."""
        if tok.kind == "END":
            s.fail("The sentence stops too soon: it needs a value here to finish it.", tok,
                   hint="A value is a number, money, quoted text, or a name.", teach="value_needed")
        s.fail(f'This needs a value here, and "{tok.text}" is not one.', tok,
               hint="A value is a number, money, quoted text, or a name.", teach="value_needed")

    def pronoun(self, s, tok):
        candidates = [b for b in self.scope.visible().values() if b.focus]
        if not candidates:
            s.fail(
                f'"{tok.text}" doesn\'t refer to anything here.', tok,
                hint='A pronoun needs one thing in view: use it inside "For each ...", "To ..." or a definition.',
                teach="pronoun",
            )
        if len(candidates) > 1:
            suffix = "" if tok.low in PRONOUNS else "'s"
            if suffix and s.peek().kind == "WORD":
                suffix += " " + s.peek().text
            readings = "\n".join(f"  ({k}) the {b.name}{suffix}" for k, b in enumerate(candidates, 1))
            s.fail(
                f'"{tok.text}" can be read {len(candidates) if len(candidates) > 2 else "two"} ways here:', tok,
                hint=f"{readings}\nSay which one, such as \"the {candidates[0].name}{suffix}\".", teach="pronoun",
            )
        b = candidates[0]
        b.reads += 1
        self.note(f'"{tok.text}" → the {b.name}')
        slot = b.slot
        expr = Expr(b.type, lambda env: env.get(slot))
        expr.key = ("var", slot)
        return expr

    def variable(self, s, match):
        name, count = match
        start = s.peek().col
        for _ in range(count):
            s.next()
        b = self.scope.find(name)
        if self.rule_for is not None and b.slot != self.rule_for and not b.fixed:
            self.rule_refuses(s, (start, s.prev_end(start)), f'the variable "{name}"',
                              hint=f'Make it with "always" ("Let {name} always be ..."), or write the value itself.')
        b.reads += 1
        slot = b.slot  # where the value is kept: the name, unless it is a private one of this file
        expr = Expr(b.type, lambda env: env.get(slot))
        expr.key = ("var", slot)
        if b.let:
            expr.target = ("var", slot)
        elif b.fixed:
            expr.target = ("fixed", slot)
        return self.settle(expr)

    def bare_name(self, s):
        match = self.match_words(s, self.names)
        if match:
            key, count = match
            start = s.peek().col
            for _ in range(count):
                s.next()
            entry = self.names[key]
            self.rule_refuses(s, (start, s.prev_end(start)), f"another thing, {entry[0]}")
            slot = entry.slot
            expr = Expr(entry[1], lambda env: env.world.named[slot])
            expr.key = ("thing", slot)
            return expr
        match = self.match_words(s, self.choice_words)
        if match:
            key, count = match
            for _ in range(count):
                s.next()
            entry = self.choice_words[key]
            display = entry[0]
            return Expr(entry[1], lambda env: display, literal=True)
        match = self.match_words(s, self.scope.visible())
        if match:
            return self.variable(s, match)
        self.unknown(s)

    def unknown(self, s, the=False):
        tok = s.peek()
        shown = f"the {tok.text}" if the else tok.text
        if tok.kind != "WORD":
            self.no_value(s, tok)
        self.hidden_here(s)
        if not the and tok.low in VALUE_WORDS:
            word = VALUE_WORDS[tok.low].split('"')[1]
            s.fail(f'EnglishScript has no "{tok.text}".', tok, hint=f"Write {VALUE_WORDS[tok.low]}.", teach="values",
                   fix=s.replace(tok, word))
        after = s.peek(1)
        if after.is_punct("(") and after.col == tok.end and not self.defined_word(tok.low):
            s.fail(f'EnglishScript has no function calls like "{tok.text}(...)".', tok,
                   hint='A worked-out value is a phrase, such as "the bounty for Smaug";\n'
                        'define one with "To work out the bounty (money) for a dragon:".', teach="call")
        noun = self.nouns.get(tok.low)
        if noun:
            kind = noun[0]
            named = [disp for disp, k in self.names.values() if k == kind]
            hint = f'Name one ({join_words(some_of(named), "or")}), or' if named else "You could"
            word = self.word_of(kind)
            s.fail(
                f'Which {word}? Nothing here says which one "{shown}" is.', tok,
                hint=f'{hint} go through them with "For each {word}:".', teach="the_noun",
            )
        variables = [n for n in self.scope.visible() if not n.startswith("\0")]
        if the:
            self.misspelt(s, tok, [n for n in variables + list(self.workouts) if " " not in n], "unknown_variable")
            if tok.low in self.member_names:
                s.fail(f'"{tok.text}" is a property, so it needs an owner, as in "the {tok.text} of ..." or '
                       f'"its {tok.text}".', tok, teach="unknown_property")
            name = []
            for word in s.toks[s.i:]:
                if word.kind != "WORD" or word.low in KEYWORDS:
                    break
                name.append(word.text)
            name = " ".join(name)
            start = "..."
            if s.toks[0].is_word("add", "subtract", "multiply", "divide"):
                start = "$0" if any(t.kind == "MONEY" for t in s.toks) else "0"
            hint = f"Make it first, with a sentence such as: Let the {name} be {start}."
            if variables:
                hint += "\nVariables in view: " + ", ".join(f"the {n}" for n in some_of(variables, tok.text)) + "."
            s.fail(f'I don\'t know "the {name}": no sentence before this one has made it.', tok,
                   hint=hint, teach="unknown_variable")
        things = [disp for disp, _ in self.names.values()]
        self.misspelt(s, tok, things + [n for n in variables if " " not in n], "unknown")
        if tok.low in self.member_names:
            s.fail(f'"{tok.text}" is a property, so it needs an owner, as in "...\'s {tok.text}" or '
                   f'"its {tok.text}".', tok, teach="unknown_property")
        if tok.low in self.adjective_names:
            s.fail(f'"{tok.text}" is an adjective, so it comes after "is", as in "If Smaug is {tok.text}:".', tok,
                   teach="value_needed")
        known = some_of(things, tok.text) + [f"the {n}" for n in some_of(variables, tok.text)]
        s.fail(
            f'I don\'t know what "{shown}" refers to.', tok,
            hint=("Names in view: " + ", ".join(known) + ".") if known else "Nothing has been given a name yet.",
            teach="unknown",
        )

    def the_phrase(self, s):
        the = s.next()
        if self.rule_for is not None:
            # In a rule, "the" may start only a variable or "the <property> of ...".
            j = s.i
            while s.toks[j].kind == "WORD" and s.toks[j].low != "of":
                j += 1
            name = " ".join(t.low for t in s.toks[s.i:j])
            plain = self.match_words(s, self.scope.visible()) or (
                name in self.member_names and s.toks[j].is_word("of") and name not in self.workouts) or (
                s.peek().kind == "WORD" and s.peek().low not in KEYWORDS and not self.defined_word(s.peek().low)
                and not s.peek().is_word("length", "words", "lines", "first", "last", "total", "problem"))
            if not plain:
                self.rule_refuses(s, (the.col, s.toks[max(j - 1, s.i)].end), f'"{s.line.text[the.col:s.toks[max(j - 1, s.i)].end]}"',
                                  hint="A worked-out value, a count or a total reads other things.")
        if s.at_words("number", "of", "items", "in"):
            for _ in range(4):
                s.next()
            items = self.primary(s)
            self.need(s, items)
            if not is_list(items.type):
                s.fail_span(f"{cap(items.text)} is {self.describe(items.type)}, not a list.", items.span,
                            hint=f'To count a group of things, write "the number of" and the plural, '
                                 f'such as "the number of dragons".', teach="list")
            lf = items.fn
            return Expr("number", lambda env: Fraction(len(lf(env))))
        if s.at_words("number", "of"):
            s.next()
            s.next()
            coll = self.collection(s, plural=True, value_start=the.col)
            cf = coll.fn
            return Expr("number", lambda env: Fraction(len(cf(env))))
        found = self.list_phrase(s, the) or self.number_phrase(s, the)
        if found:
            return found
        match = self.match_words(s, self.workouts)
        if match:
            return self.use_workout(s, match)
        found = self.file_phrase(s) or self.letters_phrase(s) or self.text_of_phrase(s)
        if found:
            return found
        if s.at_word("problem"):
            problem = s.next()
            if not self.scope.find(PROBLEM):
                s.fail('"The problem" only means something inside an "If that fails:" block.', problem,
                       teach="place")
            expr = Expr("text", lambda env: env.get(PROBLEM))
            expr.key = ("var", PROBLEM)  # so that "the problem is a broken rule" can be told (tail)
            return expr
        tok = s.peek()
        singular_kind = tok.kind == "WORD" and tok.low in self.nouns and not self.nouns[tok.low][1]
        if singular_kind and s.peek(1).is_word("called"):
            return self.find_by_name(s)
        # "the <member> of <owner>"  and  "the total <member> of <group>"
        total = s.at_word("total")
        j = s.i + (1 if total else 0)
        words = []
        while s.toks[j].kind == "WORD" and s.toks[j].low != "of":
            words.append(s.toks[j].low)
            j += 1
        name = " ".join(words)
        if words and s.toks[j].is_word("of") and name in self.member_names:
            name_tok = s.toks[j - len(words)]
            s.i = j + 1
            if total:
                coll = self.collection(s, plural=True, value_start=the.col)
                found = self.getter(coll.kind, name)
                if not found:
                    s.fail(f'{self.describe(coll.kind).capitalize()} has no "{name}" to add up.', name_tok,
                           hint=f"{self.describe(coll.kind).capitalize()} has: "
                                + ", ".join(some_of(self.member_list(coll.kind), name)) + ".",
                           teach="unknown_property")
                type_, get = found
                if base(type_) not in ("number", "money"):
                    s.fail(f'I can\'t add up "{name}": it is {self.describe(type_)}, and only numbers and money '
                           "can be added up.", name_tok, teach="arith")
                cf = coll.fn

                def add_up(env):
                    values = (get(env.world, x) for x in cf(env))
                    return sum((v for v in values if v is not None), Fraction(0))
                return Expr(base(type_), add_up)
            # Decided by the owner alone: if it has a property of that name, this is the
            # property; otherwise, if a value of that name is in view, it is that value,
            # and the "of" belongs to what comes next.
            in_view = not total and name in self.scope.visible()
            mark = (len(self.notes), self.present)
            try:
                owner = self.primary(s)
            except EnglishError:
                if not in_view:
                    raise
                owner = None
            has = owner is not None and base(owner.type) in self.kinds and self.getter(base(owner.type), name)
            if in_view and not has:
                s.i = j - len(words)  # the value "the <name>": see below
                del self.notes[mark[0]:]
                self.present = mark[1]
                return self.variable(s, self.match_words(s, self.scope.visible()))
            if in_view:
                text = s.line.text
                owner_text = text[s.toks[j + 1].col:s.prev_end(0)]
                readings = (f"  (1) {owner_text}'s {name}   (the property)\n"
                            f"  (2) (the {name}) of {owner_text}   (the value in view)")
                s.fail_span(f'"the {name} of {owner_text}" can be read two ways: "{name}" is a property of '
                            f'{self.describe(base(owner.type))}, and "the {name}" is also in view here:',
                            (the.col, s.prev_end(the.col)), hint=readings + "\nWrite the one you mean.",
                            teach="ambiguous_name")
            if base(owner.type) not in self.kinds:
                s.fail_span(f"{cap(owner.text)} is {self.describe(owner.type)}, so it has no {name}.", owner.span,
                            teach="props_of")
            if not self.getter(base(owner.type), name):
                kind = base(owner.type)
                s.fail(
                    f'{self.describe(kind).capitalize()} has no "{name}".', name_tok,
                    hint=f"{self.describe(kind).capitalize()} has: " + ", ".join(some_of(self.member_list(kind), name)) + ".",
                    teach="unknown_property",
                )
            self.rule_member(s, owner, name, (the.col, s.prev_end(the.col)))
            return self.stamp(s, self.member_expr(owner, name), the.col)
        match = self.match_words(s, self.scope.visible())
        if match:
            return self.variable(s, match)
        self.hidden_here(s)
        if words and s.toks[j].is_word("of") and not self.scope.find(words[0]) and words[0] not in self.nouns:
            single = [m for m in self.member_names if " " not in m] + [w for w in self.workouts if " " not in w]
            if len(words) == 1:
                self.misspelt(s, s.toks[j - 1], single, "unknown_property")
            s.fail(
                f'Nothing has a property called "{name}".', s.peek(),
                hint='Give a kind that property ("A dragon has ...") or define it ("The ... of a dragon is ...").',
                teach="unknown_property",
            )
        self.unknown(s, the=True)

    def use_workout(self, s, match):
        """'the bounty for Smaug': a value worked out by a "To work out" block."""
        name, count = match
        for _ in range(count):
            s.next()
        w = self.workouts[name]
        if self.workout is not w:
            w.used = True
        if w.asks and (self.workout is not None or self.defining):
            first = s.toks[s.i - count]
            s.fail(f'"The {w.name}" asks a model, and working something out can\'t ask anything: a worked-out value, '
                   "an adjective, a property, a rule or a kept value is worked out whenever it is needed.", first,
                   hint="Use it in a verb, or in a sentence of the program, and keep the answer with \"Let\".",
                   teach="working_out")
        by_prep = {p.prep: p for p in w.params}
        usage = "It goes: " + w.usage() + "."
        args = {}
        while s.peek().kind == "WORD" and s.peek().low in by_prep and by_prep[s.peek().low].name not in args:
            ptok = s.next()
            param = by_prep[ptok.low]
            if s.at_end():
                s.fail(f'After "{ptok.text}" comes {article(param.name)}.', hint=usage, teach="verb_roles")
            # one value; arithmetic in a role needs brackets. A group, where a list is wanted, is made a list.
            value = (self.group_as_list(s) if is_list(param.type) else None) or self.primary(s)
            if not self.fits(value.type, param.type):
                if base(value.type) == base(param.type):
                    self.need(s, value)
                s.fail_span(
                    f'"The {w.name}" wants {article(param.name)} here, '
                    f"but {value.text} is {self.describe(value.type)}.", value.span, hint=usage, teach="fit",
                )
            args[param.name] = value
        missing = [p for p in w.params if p.name not in args]
        if missing:
            wanted = join_words(f"{p.prep} {article(p.name)}" for p in missing)
            s.fail(f'"The {w.name}" is missing something: {wanted}.', hint=usage, teach="verb_roles")
        if args:
            given = ", ".join(f"{n} = {v.text}" for n, v in args.items())
            self.note(f'"{w.name}" → worked out with {given}')
        fns = [(n, v.fn) for n, v in args.items()]

        def fn(env):
            world = env.world
            frame = Env(world.globals)
            for arg_name, arg_fn in fns:
                frame.vars[arg_name] = arg_fn(env)
            world.depth += 1
            try:
                if world.depth > CALL_LIMIT:
                    raise EnglishError(
                        f'"The {w.name}" keeps using itself; I stopped after {CALL_LIMIT} levels.', stage="run",
                        hint="Look for the case where it can give its answer without using itself.", teach="depth",
                    )
                for step in w.body:
                    step(frame)
            except _Answer as answer:
                return answer.value
            finally:
                world.depth -= 1
            raise EnglishError(f'"The {w.name}" finished without an answer.', stage="run", teach="answer_paths")
        return Expr(w.type, fn)

    # Text, files and finding things ---------------------------------------

    def no_group_for_list(self, s, want, lead):
        """Formerly refused a group where a list is wanted; a group is now made a list
        there (whole_value, group_as_list). Kept as a no-op for the places that call it."""
        return None

    def whole_value(self, s, want=None):
        """The whole value of "Let", "Set", a "whose" part or "The answer is": a list
        written out ("a list of 3, 8 and 5"), an empty list ("an empty list of numbers"),
        a group of things, which becomes a list of them as they are at that moment
        ("all poor dragons"), or any other expression. `want` is the type wanted, if known."""
        start = s.peek().col
        if s.at_words("a", "list", "of") or s.at_words("an", "empty", "list", "of"):
            return self.stamp(s, self.list_written(s), start)
        self.choice_expected(s, want)
        if want is None or is_list(want):
            group = self.group_as_list(s)
            if group is not None:
                return group
        return self.expr(s)

    def list_written(self, s):
        """'a list of <value>, <value> ... and <value>' or 'an empty list of <plural type>'."""
        if s.eat_word("an"):
            s.next()  # empty
            s.next()  # list
            s.next()  # of
            tok = s.next()
            if tok.is_word(*LIST_PLURALS):
                type_ = LIST + LIST_PLURALS[tok.low]
            elif tok.kind == "WORD" and self.nouns.get(tok.low, (None, False))[1]:
                type_ = LIST + self.nouns[tok.low][0]
            else:
                plurals = list(LIST_PLURALS) + [K.plural for k, K in self.kinds.items() if self.kind_visible(k)]
                self.misspelt(s, tok, plurals, "list")
                s.fail(f'After "an empty list of" comes a plural, such as "numbers" or "dragons", and '
                       f'"{tok.text}" is not one.', tok, hint="Plurals here: " + ", ".join(some_of(plurals, tok.text))
                       + ".", teach="list")
            return Expr(type_, lambda env: ())
        s.next()  # a
        s.next()  # list
        s.next()  # of
        items = []
        while True:
            item = self.expr(s)
            self.need(s, item)
            if is_list(item.type):
                s.fail_span(f"{cap(item.text)} is a list, and a list can't hold lists.", item.span, teach="list")
            if items and item.type != items[0].type:
                s.fail_span(f"The items of a list are all of one kind: {items[0].text} is "
                            f"{self.describe(items[0].type)}, but {item.text} is {self.describe(item.type)}.",
                            item.span, teach="list")
            items.append(item)
            if s.eat_punct(","):
                s.eat_word("and")  # "3, 8, and 5"
                continue
            if s.eat_word("and"):
                continue
            break
        fns = [item.fn for item in items]
        return Expr(LIST + items[0].type, lambda env: tuple(fn(env) for fn in fns))

    def group_as_list(self, s):
        """A group of things where a list is wanted ('all poor dragons', 'Smaug's
        treasures'): the list of the things in it when the value is worked out. None,
        and nothing read, if what follows is not a group."""
        start, mark = s.i, len(self.notes)
        tok = s.peek()
        looks = s.at_word("all") or self.noun_ahead(s) or (
            tok.kind == "WORD" and tok.low in POSSESSIVES and s.peek(1).kind == "WORD"
            and self.nouns.get(s.peek(1).low, (None, False))[1])
        if not looks:
            # "Smaug's treasures": a value with a possessive, then the plural of a kind.
            k = 0
            while s.peek(k).kind == "WORD":
                k += 1
            if not (k and s.peek(k).kind == "POS" and s.peek(k + 1).kind == "WORD"
                    and self.nouns.get(s.peek(k + 1).low, (None, False))[1]):
                return None
        col = tok.col
        try:
            coll = self.collection(s, plural=True, value_start=col)
        except EnglishError:
            if looks:
                raise
            s.i = start
            del self.notes[mark:]
            return None
        cf = coll.fn
        expr = self.stamp(s, Expr(LIST + coll.kind, lambda env: tuple(cf(env))), col)
        self.note(f'"{expr.text}" → a list of the {self.kinds[coll.kind].plural} in it at that moment')
        return expr

    def file_name(self, s):
        path = self.primary(s)
        self.need(s, path)
        if path.type != "text":
            s.fail_span(f"The name of a file is text, but {path.text} is {self.describe(path.type)}.", path.span,
                        hint='Put it in quotes, such as "notes.txt".', teach="fit")
        return path

    def file_phrase(self, s):
        """'the text of the file <text>' and 'the lines of the file <text>'."""
        for word in ("text", "lines"):
            if s.at_words(word, "of", "the", "file") and s.peek(4).kind != "END":
                for _ in range(4):
                    s.next()
                pf = self.file_name(s).fn
                if word == "text":
                    return Expr("text", lambda env: read_file(pf(env)))
                return Expr(LIST + "text", lambda env: split_lines(read_file(pf(env))))
        return None

    def letters_phrase(self, s):
        """'the first <number> letters of <text>', and the same with "last"."""
        if not s.at_word("first", "last"):
            return None
        mark = (s.i, len(self.notes))
        first = s.next().is_word("first")
        try:
            count = self.unary(s)  # one value, or a minus sign and one value
        except EnglishError:
            count = None
        if count is None or not s.at_words("letters", "of"):
            s.i = mark[0]
            del self.notes[mark[1]:]
            return None
        s.next()
        s.next()
        text = self.primary(s)
        self.need(s, count)
        if count.type != "number":
            s.fail_span(f"I need a plain number of letters, but {count.text} is {self.describe(count.type)}.",
                        count.span, teach="fit")
        self.need_text(s, text, "take letters from")
        cf, tf = count.fn, text.fn
        shown = count.text

        def fn(env):
            n, value = cf(env), tf(env)
            if n < 0 or n.denominator != 1:
                raise EnglishError(f"I can't take {fmt(n, 'number')} letters of a text.", stage="run",
                                   recoverable=True, teach="count",
                                   hint=f"{cap(shown)} was {fmt(n, 'number')}, and only a whole number that is "
                                        "not negative can count letters.")
            n = int(n)
            if first:
                return value[:n]
            return value if n >= len(value) else value[len(value) - n:]
        return Expr("text", fn)

    def text_of_phrase(self, s):
        """'the length of <text>', 'the words of <text>', 'the lines of <text>'.

        These words are free for names, so the phrase is only taken when what
        follows is text: "the length of the bridge" may still be a property.
        """
        word = s.peek()
        if not (word.is_word("length", "words", "lines") and s.peek(1).is_word("of")):
            return None
        mark = (s.i, len(self.notes))
        s.next()
        s.next()
        value, error = None, None
        try:
            value = self.primary(s)
        except EnglishError as caught:
            error = caught
        if value is not None and base(value.type) == "text":
            self.need(s, value)
            vf = value.fn
            if word.low == "length":
                return Expr("number", lambda env: Fraction(len(vf(env))))
            if word.low == "words":
                return Expr(LIST + "text", lambda env: tuple(vf(env).split()))
            return Expr(LIST + "text", lambda env: split_lines(vf(env)))
        s.i = mark[0]
        del self.notes[mark[1]:]
        if word.low in self.member_names or self.match_words(s, self.scope.visible()):
            return None  # a property or a variable of that name
        if error is not None:
            raise error
        s.fail_span(f'"The {word.low} of" needs text, but {value.text} is {self.describe(value.type)}.', value.span,
                    teach="text_only")

    def list_phrase(self, s, the):
        """'the first of <list>', 'the last of <list>', 'the total of <list>'. Told from
        'the first 3 letters of', 'the total worth of' and a property or worked-out value
        called "first", "last" or "total" by the "of" straight after the word, and by
        the value after "of" being a list. None, with nothing read, otherwise."""
        if not (s.at_word("first", "last", "total") and s.peek(1).is_word("of")):
            return None
        start, mark, word = s.i, len(self.notes), s.peek()
        s.next()
        s.next()
        try:
            items = self.primary(s)
        except EnglishError:
            items = None
        if items is None or not is_list(items.type):
            s.i = start
            del self.notes[mark:]
            return None
        self.need(s, items)
        other = None  # another reading of the same words: a worked-out value or property called so
        if word.low in self.workouts:
            other = f'the worked-out value "the {word.low}"'
        elif word.low in self.member_names:
            other = f'a property called "{word.low}"'
        if other is not None:
            text = s.line.text[the.col:s.prev_end(the.col)]
            s.fail_span(f'"{text}" can be read two ways: as the {word.low} item of the list, or as {other}.',
                        (the.col, s.prev_end(the.col)), hint="Rename that worked-out value or property, so that "
                        f'"the {word.low} of" a list reads one way.', teach="ambiguous_name")
        lf, item = items.fn, item_type(items.type)
        if word.low == "total":
            if item not in ("number", "money"):
                s.fail_span(f"Only numbers and money can be added up, but {items.text} is "
                            f"{self.describe(items.type)}.", items.span, teach="arith")
            return Expr(item, lambda env: sum(lf(env), Fraction(0)))
        if word.low == "first":
            return Expr(opt(item), lambda env: next(iter(lf(env)), None))
        return Expr(opt(item), lambda env: lf(env)[-1] if lf(env) else None)

    NUMBER_PHRASES = (("remainder", "of"), ("square", "root", "of"), ("larger", "of"), ("smaller", "of"),
                      ("absolute", "value", "of"))

    def number_phrase(self, s, the):
        """'the remainder of <value> divided by <value>', 'the square root of <value>',
        'the larger of <value> and <value>', 'the smaller of ...', 'the absolute value of
        <value>'. Each <value> is a single value or a bracketed expression. Recognised by
        position: the words stay free for names, and when a worked-out value of the same
        name is in view the phrase is refused as having two readings. None, with nothing
        read, if the words are not one of these."""
        words = next((w for w in self.NUMBER_PHRASES if s.at_words(*w)), None)
        if words is None:
            return None
        start, mark = s.i, len(self.notes)
        name = " ".join(words[:-1])
        for _ in words:
            s.next()
        try:
            first = self.primary(s)
            second = None
            if name == "remainder":
                if not s.at_words("divided", "by"):
                    raise EnglishError("not this form")
                s.next()
                s.next()
                second = self.primary(s)
            elif name in ("larger", "smaller"):
                if not s.at_word("and"):
                    raise EnglishError("not this form")
                s.next()
                second = self.primary(s)
        except EnglishError:
            s.i = start
            del self.notes[mark:]
            return None
        if name in self.workouts:
            text = s.line.text[the.col:s.prev_end(the.col)]
            s.fail_span(f'"{text}" can be read two ways: as EnglishScript\'s own "the {name} of", or as the '
                        f'worked-out value "the {name}" of this program.', (the.col, s.prev_end(the.col)),
                        hint=f'Rename the worked-out value, so that "the {name} of" reads one way.',
                        teach="ambiguous_name")
        sides = [first] + ([second] if second is not None else [])
        for side in sides:
            self.need(s, side)
        ff = first.fn
        if name in ("larger", "smaller"):
            if first.type != second.type or first.type not in ("number", "money", "percent"):
                s.fail_span(f'"The {name} of" takes two numbers, two amounts of money or two percentages, but '
                            f"{first.text} is {self.describe(first.type)} and {second.text} is "
                            f"{self.describe(second.type)}.", (first.span[0], second.span[1]), teach="compare_kinds")
            sf, pick = second.fn, (max if name == "larger" else min)
            return Expr(first.type, lambda env: pick(ff(env), sf(env)))
        if name == "absolute value":
            if first.type not in ("number", "money", "percent"):
                s.fail_span(f"Only a number, money or a percentage has an absolute value, but {first.text} is "
                            f"{self.describe(first.type)}.", first.span, teach="arith")
            return Expr(first.type, lambda env: abs(ff(env)))
        for side in sides:
            if side.type != "number":
                s.fail_span(f'"The {name} of" works on plain numbers, but {side.text} is '
                            f"{self.describe(side.type)}.", side.span, teach="arith")
        if name == "square root":
            return Expr("number", lambda env: square_root(ff(env)))
        sf = second.fn
        return Expr("number", lambda env: remainder(ff(env), sf(env)))

    def list_item(self, s):
        """'item <number> of <list>': the item, if there is one (numbered from 1).
        Returns the Expr, or None with nothing read if what follows is not this form.
        Its target lets "Set item <number> of <list> to ..." change it."""
        start, mark, col = s.i, len(self.notes), s.peek().col
        word = s.next().low  # item, or letter
        try:
            number = self.primary(s)
            if not s.at_word("of"):
                raise EnglishError("not an item")
            s.next()
            items = self.primary(s)
        except EnglishError:
            s.i = start
            del self.notes[mark:]
            return None
        if word == "letter":
            return self.text_letter(s, col, number, items)
        if not is_list(items.type):
            if self.scope.find("item") or "item" in self.names:
                s.i = start
                del self.notes[mark:]
                return None
            s.fail_span(f'"Item ... of" takes an item from a list, but {items.text} is '
                        f"{self.describe(items.type)}.", items.span, teach="list")
        self.need(s, number)
        self.need(s, items)
        if number.type != "number":
            s.fail_span(f"An item is found by its number, but {number.text} is {self.describe(number.type)}.",
                        number.span, teach="list")
        nf, lf = number.fn, items.fn

        def fn(env):
            values, n = lf(env), nf(env)
            if n.denominator != 1 or not 1 <= n <= len(values):
                return None
            return values[int(n) - 1]
        expr = self.stamp(s, Expr(opt(item_type(items.type)), fn), col)
        expr.check = f"If {expr.text} is not nothing:"
        if items.target is not None and items.target[0] in ("var", "field"):
            expr.target = ("item", items, number)
        return expr

    def text_letter(self, s, col, number, text):
        """'letter <number> of <text>': that letter, if there is one (numbered from 1)."""
        self.need(s, number)
        self.need(s, text)
        if base(text.type) != "text":
            s.fail_span(f'"Letter ... of" takes a letter from text, but {text.text} is {self.describe(text.type)}.',
                        text.span, teach="text_only")
        if number.type != "number":
            s.fail_span(f"A letter is found by its number, but {number.text} is {self.describe(number.type)}.",
                        number.span, teach="text_only")
        nf, tf = number.fn, text.fn

        def fn(env):
            value, n = tf(env), nf(env)
            if n.denominator != 1 or not 1 <= n <= len(value):
                return None
            return value[int(n) - 1]
        expr = self.stamp(s, Expr("text?", fn), col)
        expr.check = f"If {expr.text} is not nothing:"
        return expr

    def find_by_name(self, s):
        """'the dragon called "Smaug"': the first such thing with that name, ignoring capitals."""
        kind = self.nouns[s.next().low][0]
        s.next()  # called
        name = self.primary(s)
        self.need(s, name)
        if name.type != "text":
            s.fail_span(f"A name is text, but {name.text} is {self.describe(name.type)}.", name.span,
                        hint='Put the name in quotes, such as "Smaug".', teach="fit")
        nf = name.fn

        def fn(env):
            wanted = nf(env).lower()
            for thing in env.world.things.get(kind, []):
                if thing.name.lower() == wanted:
                    return thing
            return None
        return Expr(opt(kind), fn)

    def template(self, s, tok):
        """A quoted text, with {expressions} filled in when it is said.

        Inside the quotes, "" is one quote, {{ and }} are braces, and
        {new line} is a line break.
        """
        raw, start = tok.text[1:-1], tok.col + 1  # the text as written, so columns line up
        parts, plain, i = [], [], 0
        escapes = {'""': '"', "{{": "{", "}}": "}"}
        while i < len(raw):
            pair = raw[i:i + 2]
            if pair in escapes:
                plain.append(escapes[pair])
                i += 2
                continue
            if raw[i] == "}":
                raise EnglishError('This "}" closes no fill-in.', s.line, start + i, 1,
                                   hint='To show a brace itself, write it twice: "}}".', teach="fill_in",
                                   fix=swap(s.line, start + i, start + i + 1, "}}"))
            if raw[i] != "{":
                plain.append(raw[i])
                i += 1
                continue
            k = raw.find("}", i)
            if k >= 0 and '"' in raw[i:k]:
                # The quote of a text inside a fill-in, written "" so as not to end the text, is still a quote.
                raise EnglishError(
                    "A fill-in can't contain quotes, not even doubled ones.", s.line, start + i + raw[i:k].index('"'), 1,
                    hint='Put the text in a variable first ("Let the word be ...") and fill in {the word}.',
                    teach="fill_in")
            if k < 0:
                if "}" in s.line.text[tok.end:]:
                    # The brace is closed after a quote: the quote inside the fill-in ended the text.
                    raise EnglishError(
                        "A fill-in can't contain quotes: the quote inside these braces ends the text.",
                        s.line, start + i, 1,
                        hint='Put the text in a variable first ("Let the word be ...") and fill in {the length of the word}.',
                        teach="fill_in",
                    )
                raise EnglishError('This "{" has no "}" to close it.', s.line, start + i, 1,
                                   hint='To show a brace itself, write it twice: "{{".', teach="fill_in")
            toks = tokenize(s.line.text, s.line, start + i + 1, start + k)
            toks.append(Token("END", "", start + k))
            sub = Sentence(s.line, toks)
            if sub.at_end():
                sub.fail("There is nothing between these braces.", hint='Put a value between them, such as '
                         '"{Smaug\'s age}", or write "{{" to show a brace itself.', teach="fill_in")
            if sub.at_words("new", "line") and sub.peek(2).kind == "END":
                plain.append("\n")
            else:
                inner = self.expr(sub)
                self.end(sub)
                self.sayable(sub, inner)
                parts.append("".join(plain))
                plain = []
                parts.append(inner)
            i = k + 1
        parts.append("".join(plain))

        def fn(env):
            return "".join(p if isinstance(p, str) else fmt(p.fn(env), p.type) for p in parts)
        return Expr("text", fn)

    def sayable(self, s, expr):
        if is_list(expr.type):
            s.fail_span(
                f"{cap(expr.text)} is a list, and a list can't be said directly yet.", expr.span,
                hint='Go through it with "For each ... in ...:" and say each item.', teach="list",
            )

    # --------------------------------------------------------- collections

    def noun_ahead(self, s):
        """Is this the start of '<adjective>* <kind>'?"""
        for k in range(4):
            tok = s.peek(k)
            if tok.kind != "WORD":
                return False
            if tok.low in self.nouns:
                return True
            if tok.low in KEYWORDS or tok.low in self.names or self.scope.find(tok.low):
                return False
        return False

    def collection(self, s, plural, value_start=None):
        """'grumpy dragons', 'treasures of Smaug', 'its treasures', 'Smaug's treasures'."""
        start = s.peek().col
        owner = None
        tok = s.peek()
        if plural and tok.kind == "WORD" and tok.low in POSSESSIVES:
            s.next()
            owner = self.stamp(s, self.pronoun(s, tok), start)
            owner.text = f"the {self.word_of(owner.type)}"  # reads better than "its" in notes and errors
        else:
            if plural:
                s.eat_word("all")
            if not self.noun_ahead(s):
                tok = s.peek()
                shown = [K for k, K in self.kinds.items() if self.kind_visible(k)]
                singulars, plurals = [K.word for K in shown], [K.plural for K in shown]
                if not plural:
                    for k in range(4):  # "For each young numeral:": the kind may follow adjectives
                        if s.peek(k).kind != "WORD":
                            break
                        self.hidden_here(s, k)
                    single = dict(zip(plurals, singulars))
                    self.misspelt(s, tok, singulars + plurals, "unknown_kind", lambda w: single.get(w, w))
                    if tok.kind != "WORD":
                        s.fail('After "For each" comes a kind, such as "dragon".', hint=self.kinds_hint(),
                               teach="loop_form")
                    s.fail(f'I don\'t know the kind "{tok.text}".',
                           hint=self.plural_hint(tok.text) or self.kinds_hint(tok.text), teach="unknown_kind")
                starts_value = tok.kind != "WORD" or (
                    tok.low in ("the",) + POSSESSIVES + PRONOUNS or self.match_words(s, self.names)
                    or self.match_words(s, self.scope.visible()) or tok.low in KEYWORDS)
                if not starts_value:
                    self.hidden_here(s)
                    self.misspelt(s, tok, plurals, "unknown_kind")
                    s.fail(f'I don\'t know the kind "{tok.text}".',
                           hint=self.plural_hint(tok.text) or (
                               "A group is written in the plural: " + ", ".join(some_of(plurals, tok.text)) + "."
                               if plurals else "No kind has been described yet."), teach="unknown_kind")
                owner = self.primary(s, dangling_ok=True)
                if s.peek().kind != "POS":
                    s.fail_span(
                        'This needs a group of things here, such as "all dragons" or "Smaug\'s treasures".',
                        owner.span, teach="number_agreement",
                    )
                s.next()
        adjectives = []
        while True:
            tok = s.peek()
            if tok.kind != "WORD":
                s.fail('This needs a kind here, such as "dragon".', hint=self.kinds_hint(), teach="unknown_kind")
            if tok.low in self.nouns:
                break
            adjectives.append(s.next())
        kind, is_plural = self.nouns[tok.low]
        K = self.kinds[kind]
        K.plural_used = K.plural_used or is_plural
        noun = s.next()
        if plural and not is_plural:
            s.fail(f'More than one is meant here, so write "{K.plural}".', noun, teach="number_agreement",
                   fix=s.replace(noun, K.plural))
        if not plural and is_plural:
            s.fail(f'"For each" takes them one at a time, so write "{K.word}".', noun, teach="number_agreement",
                   fix=s.replace(noun, K.word))
        tests = []
        for adj_tok in adjectives:
            adj = K.adjectives.get(adj_tok.low)
            if not adj:
                self.unknown_adjective(s, adj_tok, kind)
            tests.append(adj.fn)
            adj.used = True
            self.note(f'"{adj_tok.text}" → {adj.source}')
        if owner is None and s.at_word("of"):
            s.next()
            owner = self.primary(s)
        link = None
        if owner is not None:
            self.need(s, owner)
            if owner.type not in self.kinds:
                s.fail_span(f"{cap(owner.text)} is {self.describe(owner.type)}, so nothing can belong to it.",
                            owner.span, teach="props_of")
            link = self.relation(s, K, owner, noun)
        filters = []  # (hidden variable, condition) for each "whose", all of which must hold
        indexed = None  # (property, fn(env) -> value) when the first filter can use an index
        while s.at_word("whose") and (not filters or self.in_thing_whose == 0):
            s.next()
            match = self.match_member(s, kind)
            if not match:
                self.no_member(s, kind)
            hidden = f"\0each{self.uid()}"
            each = Expr(kind, lambda env, hidden=hidden: env.get(hidden))
            each.span = (s.peek().col, s.peek().col)
            each.text = f"the {K.word}"
            left = self.member(s, each, match)
            after_member = s.i
            cond = self.comparison_rest(s, left)
            if not filters and not adjectives and cond.equal is not None and cond.equal[0] is left \
                    and left.target is not None and left.target[0] == "field":
                # "whose <stored property> is <value>", first: the things are found through an
                # index (World.lookup), not by visiting every one.
                indexed = (match[0], cond.equal[1].fn)
            filters.append((hidden, cond.fn))
            if value_start is not None:
                self.whose_then_sum(s, value_start, after_member)
            # More filters: "whose row is 1 and whose column is 2", except inside a "whose"
            # part of a thing being made, where "and whose" belongs to the thing (whose_parts).
            if not (s.at_words("and", "whose") and self.in_thing_whose == 0):
                break
            s.next()
        if filters and self.in_thing_whose:
            self.group_ended = s.i  # for whose_parts: a group with "whose" ended here
        whose = filters or None

        owner_fn = owner.fn if owner is not None else None

        def fn(env):
            world = env.world
            items = world.things.get(kind, [])
            if indexed is not None and items:
                # The value doesn't depend on the thing, so it is worked out once.
                items = world.lookup(kind, indexed[0], indexed[1](env))
            if link:
                mine = alive(owner_fn(env))
                items = [x for x in items if x.fields[link] is mine]
            for test in tests:
                items = [x for x in items if test(world, x)]
            if whose:
                kept = []
                for x in items:
                    inner = Env(env)
                    for hidden_name, cond in whose:
                        inner.vars[hidden_name] = x
                        if not cond(inner):
                            break
                    else:
                        kept.append(x)
                items = kept
            return list(items)
        return Coll(kind, fn)

    COMPARING = {"is", "are", "not", "more", "less", "greater", "than", "at", "least", "most", "divisible", "by",
                 "contains", "starts", "ends", "with", "comes", "before", "after"}

    def whose_then_sum(self, s, value_start, after_member):
        """Refuse "the number of knights whose courage is more than 5 + 1": the arithmetic
        could belong to the filter's value or to the number."""
        k = after_member
        while s.toks[k].low in self.COMPARING or s.toks[k].is_punct("<", ">", "<=", ">=", "="):
            k += 1
        op = self.top_op(s, k, s.i)
        if op is None:
            return
        text, toks = s.line.text, s.toks
        end = toks[s.i - 1].end
        whole = text[value_start:end]
        op_tok = toks[op]
        readings = (f"  (1) ({text[value_start:op_tok.col].strip()}) {text[op_tok.col:end].strip()}\n"
                    f"  (2) {text[value_start:toks[k].col].strip()} ({text[toks[k].col:end].strip()})")
        s.fail_span(f'"{whole}" can be read two ways:', (op_tok.col, op_tok.end),
                    hint=readings + "\nPut brackets round the part that belongs together.", teach="value_order")

    def relation(self, s, K, owner, noun):
        """Which field makes a K 'of' the owner? There must be exactly one."""
        links = [f for f, t in K.fields.items() if base(t) == owner.type]
        phrase = f"{K.plural} of {owner.text}"
        if len(links) == 1:
            self.note(f'"{phrase}" → {K.plural} whose {links[0]} is {owner.text}')
            return links[0]
        if not links:
            s.fail(
                f"I don't know how {article(K.word)} belongs to {self.describe(owner.type)}: no property of "
                f"{article(K.word)} is {self.describe(owner.type)}.", noun,
                hint=f'Give it a property that points at one, such as "{article(K.word).capitalize()} has an owner '
                     f'({self.word_of(owner.type)})."',
                teach="of_link",
            )
        ways = len(links) if len(links) > 2 else "two"
        readings = "\n".join(f"  ({k}) {K.plural} whose {link} is {owner.text}" for k, link in enumerate(links, 1))
        s.fail(
            f'"{phrase}" can be read {ways} ways, because {article(K.word)} is tied to '
            f"{self.describe(owner.type)} by its {join_words(links)}:", noun,
            hint=f'{readings}\nSay which, such as "{K.plural} whose {links[0]} is {owner.text}".', teach="of_link",
        )

    # ---------------------------------------------------------- conditions

    def condition(self, s):
        """Comparisons joined by "and" or by "or".

        Each later comparison is only reached when the earlier ones went the
        right way, so it may rely on what they checked: after "X has a mount
        and", X's mount is known to be there.
        """
        saved = self.present
        start = s.peek().col
        try:
            negated = s.peek() if s.at_word("not") else None
            parts = [self.cond_atom(s)]
            ops = []
            while s.at_word("and", "or"):
                if negated is not None:  # "not A and B": only the last of a chain may stand bare after "not"
                    self.not_mixed(s, start, negated, s.peek())
                op = s.next()
                if ops and op.low != ops[0].low:
                    self.mixed(s, start, ops[-1], op)
                ops.append(op)
                self.present = self.present | (parts[-1].nt if op.low == "and" else parts[-1].nf)
                negated = s.peek() if s.at_word("not") else None
                parts.append(self.cond_atom(s))
        finally:
            self.present = saved
        if not ops:
            return parts[0]
        fns = [p.fn for p in parts]
        if ops[0].low == "and":
            cond = Expr("truth", lambda env: all(f(env) for f in fns))
            cond.nt = frozenset().union(*(p.nt for p in parts))
        else:
            cond = Expr("truth", lambda env: any(f(env) for f in fns))
            cond.nf = frozenset().union(*(p.nf for p in parts))
        return cond

    def not_mixed(self, s, start, negated, op):
        """Refuse "not A and B" with its two readings."""
        text = s.line.text
        before = text[start:negated.col]
        a = text[negated.end:op.col].strip()
        rest = text[op.col:self.rest_end(s, op)].strip()
        readings = (f"  (1) {before}(not {a}) {rest}\n"
                    f"  (2) {before}not ({a} {rest})")
        s.fail(f'"not" followed by "{op.text}" can be read two ways:', negated,
               hint=readings + "\nPut brackets round the part that \"not\" turns round.", teach="and_or")

    @staticmethod
    def mixed(s, start, last, op):
        """Refuse "A and B or C", setting out the two readings."""
        text = s.line.text
        end, depth = s.toks[-1].col, 0  # the end of the sentence, before its period or colon,
        for tok in s.toks:  # or the bracket that closes the condition
            if tok.col < start or tok.kind == "END":
                continue
            depth += tok.is_punct("(") - tok.is_punct(")")
            if depth < 0:
                end = tok.col
                break
        before = text[start:last.col].strip()  # "A"
        middle = text[last.end:op.col].strip()  # "B"
        after = text[op.end:end].strip()  # "C"
        a, o = last.low, op.low
        readings = (f"  (1) ({before} {a} {middle}) {o} {after}\n"
                    f"  (2) {before} {a} ({middle} {o} {after})")
        s.fail(f'This mixes "and" with "or", so it can be read two ways:', op,
               hint=readings + "\nPut brackets round the part that belongs together.", teach="and_or")

    @staticmethod
    def negate(cond):
        inner = cond.fn
        flipped = Expr("truth", lambda env: not inner(env))
        flipped.nt, flipped.nf = cond.nf, cond.nt
        return flipped

    def cond_atom(self, s):
        if s.at_word("not"):
            s.next()
            return self.negate(self.cond_atom(s))
        first_error = None
        if s.peek().is_punct("("):
            # "(A and B)" is a bracketed condition; "(a + b) is 3" is not.
            mark = (s.i, len(self.notes))
            try:
                s.next()
                cond = self.condition(s)
                s.expect_punct(")")
                if s.at_end() or s.at_word("and", "or") or s.peek().is_punct(")"):
                    return cond
            except EnglishError as error:
                first_error = error
            s.i = mark[0]
            del self.notes[mark[1]:]
        try:
            return self.comparison(s)
        except EnglishError as error:
            if first_error is not None and (first_error.col or 0) > (error.col or 0):
                raise first_error from None
            raise

    def comparison(self, s):
        return self.comparison_rest(s, self.expr(s))

    def comparison_rest(self, s, left):
        tok = s.peek()
        if tok.is_word("has"):
            return self.has_test(s, left)
        if tok.is_word("is", "are"):
            if tok.is_word("are") and self.one_thing(left) and self.linting(s.line):
                self.lint.are_after_one(s.line, tok, left.text)
            s.next()
            negated = s.eat_word("not")
            cond = self.tail(s, left)
            return self.negate(cond) if negated else cond
        if tok.is_punct("=") and s.peek(1).is_punct("="):
            s.fail('EnglishScript doesn\'t use "==".', tok,
                   hint=f'To test that two values are equal, write "is": {left.text} is ...', teach="symbols")
        if tok.is_punct("<", ">", "<=", ">=", "="):
            s.next()
            return self.compare(s, tok.text, left, self.expr(s))
        for words in (("contains",), ("starts", "with"), ("ends", "with"), ("comes", "before"), ("comes", "after")):
            if s.at_words(*words):
                for _ in words:
                    s.next()
                return self.text_test(s, " ".join(words), left, self.expr(s))
        for words, phrase in ((("does", "not", "contain"), "contains"), (("does", "not", "start", "with"), "starts with"),
                              (("does", "not", "end", "with"), "ends with")):
            if s.at_words(*words):
                for _ in words:
                    s.next()
                return self.negate(self.text_test(s, phrase, left, self.expr(s)))
        if tok.is_word("equals"):
            s.fail(f'A comparison is written with "is": "{left.text} is ...", not "equals".', tok,
                   teach="comparison", fix=s.replace(tok, "is"))
        if tok.kind == "END":
            s.fail(f'The sentence stops too soon: after "{left.text}" comes a comparison, such as "is" or '
                   '"is more than".', tok, teach="comparison")
        s.fail(f'After "{left.text}" comes a comparison, such as "is", "is less than" or "is at least".',
               teach="comparison")

    def one_thing(self, expr):
        """Is the value surely one thing, so that "is" goes with it, not "are"? When
        its last word looks plural, it may be a name such as "the totals": unsure."""
        words = re.findall(r"[^\W\d_]\w*", expr.text)
        if not words or is_list(expr.type):
            return False
        return not words[-1].lower().endswith("s")

    def text_test(self, s, phrase, left, right):
        """'contains', 'starts with', 'ends with', 'comes before', 'comes after'."""
        for side in (left, right):
            self.need(s, side)
            if side.type != "text":
                s.fail_span(f'"{cap(phrase)}" is about text, but {side.text} is {self.describe(side.type)}.',
                            side.span, teach="text_only")
        lf, rf = left.fn, right.fn
        tests = {
            "contains": lambda a, b: b in a,
            "starts with": lambda a, b: a.startswith(b),
            "ends with": lambda a, b: a.endswith(b),
            "comes before": lambda a, b: a.casefold() < b.casefold(),
            "comes after": lambda a, b: a.casefold() > b.casefold(),
        }
        test = tests[phrase]
        cond = Expr("truth", lambda env: test(lf(env), rf(env)))
        cond.subject = left
        return cond

    def has_test(self, s, left):
        """'Robin has a mount' / 'Robin has no mount': is a property there?"""
        s.next()  # has
        self.need(s, left)
        if left.type not in self.kinds:
            s.fail_span(f"{cap(left.text)} is {self.describe(left.type)}, so it has no properties.", left.span,
                        teach="props_of")
        without = bool(s.eat_word("no"))
        if not without and not s.eat_word("a", "an"):
            s.fail('After "has" comes "a", "an" or "no", and then the property, as in "Robin has a mount".',
                   teach="has_form")
        match = self.match_member(s, left.type)
        if not match:
            self.no_member(s, left.type)
        name_tok = s.peek()
        declared, _ = self.getter(left.type, match[0])
        if not is_opt(declared) and not self.needless(None):
            s.fail(
                f"{article(left.type).capitalize()} always has {article(match[0])}, so there is nothing to check.",
                name_tok,
                hint='Only a property described with "if any" can be missing.', teach="nothing_checks",
            )
        prop = self.member(s, left, match)
        pf = prop.fn
        keys = frozenset([prop.key]) if prop.key is not None else NONE
        if without:
            cond = Expr("truth", lambda env: pf(env) is None)
            cond.nf = keys
        else:
            cond = Expr("truth", lambda env: pf(env) is not None)
            cond.nt = keys
        return cond

    def tail(self, s, left):
        """What follows "is": nothing, a comparison, an adjective, or a value."""
        if left.key == ("var", PROBLEM) and (s.at_word("a", "an") or s.at_words("no", "model")):
            return self.problem_kind(s)
        if s.at_word("nothing"):
            s.next()
            if not is_opt(left.type) and not self.needless(left):
                s.fail_span(f"{cap(left.text)} can't be nothing here, so there is nothing to check.", left.span,
                            teach="nothing_checks")
            lf = left.fn
            cond = Expr("truth", lambda env: lf(env) is None)
            if left.key is not None:
                cond.nf = frozenset([left.key])
            return cond
        self.need(s, left)
        if s.at_word("in"):  # "<value> is in <list>"
            s.next()
            items = self.primary(s)
            self.need(s, items)
            if not is_list(items.type):
                s.fail_span(f'"Is in" asks whether a value is one of the items of a list, but {items.text} is '
                            f"{self.describe(items.type)}.", items.span, teach="list")
            if item_type(items.type) != left.type:
                s.fail_span(f"{cap(items.text)} holds {self.plural_type(item_type(items.type))}, so "
                            f"{left.text}, {self.describe(left.type)}, can't be one of its items.",
                            (left.span[0], items.span[1]), teach="compare_kinds")
            lf, items_fn = left.fn, items.fn
            if left.type in self.kinds:
                def holds(env):
                    wanted = lf(env)
                    return any(v is wanted for v in items_fn(env))
                return Expr("truth", holds)
            return Expr("truth", lambda env: lf(env) in items_fn(env))
        phrases = (
            (("less", "than"), "<"), (("more", "than"), ">"), (("greater", "than"), ">"),
            (("at", "least"), ">="), (("at", "most"), "<="),
        )
        for words, op in phrases:
            if s.at_words(*words):
                s.next()
                s.next()
                return self.compare(s, op, left, self.expr(s))
        self.comparison_words(s)
        if s.at_words("divisible", "by"):
            s.next()
            s.next()
            return self.divisible(s, left, self.expr(s))
        tok = s.peek()
        if left.type in self.kinds and tok.kind == "WORD":
            adj = self.kinds[left.type].adjectives.get(tok.low)
            if adj:
                s.next()
                own = left.key == ("var", self.rule_for) and (adj.stored or adj.local)
                if self.probe is None or not own:
                    self.rule_refuses(s, (tok.col, tok.end), f'the adjective "{tok.text}"',
                                      hint="An adjective may read other things, which change without the rule "
                                           "being checked.")
                self.note(f'"{tok.text}" → {adj.source}')
                test, lf = adj.fn, left.fn
                adj.used = True
                return Expr("truth", lambda env: test(env.world, alive(lf(env))))
            starts_value = (
                tok.low in ("the",) + POSSESSIVES + PRONOUNS
                or self.match_words(s, self.names)
                or self.match_words(s, self.scope.visible())
            )
            if not starts_value:
                named = [disp for disp, k in self.names.values() if k == left.type]
                self.unknown_adjective(s, tok, left.type, named)
        if left.type in self.choice_sets and tok.kind == "WORD" and not self.match_words(s, self.choice_words) \
                and not (tok.low in ("the",) + POSSESSIVES + PRONOUNS or self.match_words(s, self.names)
                         or self.match_words(s, self.scope.visible())):
            self.not_a_choice(s, tok, left.type)
        return self.compare(s, "=", left, self.expr(s))

    def choice_expected(self, s, want):
        """Where one of a set's choices is wanted and the word there is no value at all,
        say it is not one of the choices, rather than that the word is unknown."""
        tok = s.peek()
        if want is None or base(want) not in self.choice_sets or tok.kind != "WORD" or tok.low in KEYWORDS:
            return
        if (self.match_words(s, self.choice_words) or self.match_words(s, self.names)
                or self.match_words(s, self.scope.visible()) or self.match_words(s, self.workouts)):
            return
        self.not_a_choice(s, tok, base(want))

    def problem_kind(self, s):
        """'the problem is [not] a broken rule': what kind of problem it is (section 8.5).
        'the problem is [not] no model' takes no article."""
        if s.at_words("no", "model"):
            s.next()
            s.next()
            return Expr("truth", lambda env: env.get(PROBLEM_ERROR).kind == "no model")
        article_tok = s.next()
        toks = []
        while s.peek().kind == "WORD" and not s.at_word("and", "or"):
            toks.append(s.next())
        words = " ".join(t.low for t in toks)
        if words == "no model":
            s.fail('Write "no model", without "a".', article_tok, teach="article",
                   fix=swap(s.line, article_tok.col, toks[-1].end, "no model"))
        if words not in PROBLEM_NAMES:
            kinds = [k if k == "no model" else article(k) for k in PROBLEM_NAMES]
            close = close_words(words, PROBLEM_NAMES) if words else []
            fix = None
            if len(close) == 1 and toks:
                fix = swap(s.line, article_tok.col, toks[-1].end, article(close[0]))
            s.fail_span(f'"{s.line.text[article_tok.col:s.prev_end(article_tok.col)]}" is not a kind of problem.',
                        (article_tok.col, s.prev_end(article_tok.col)),
                        hint="The kinds are: " + join_words(kinds, "and") + ".", teach="problem_kind", fix=fix)
        if article_tok.low != article(words).split(" ")[0]:
            s.fail(f'Write "{article(words)}".', article_tok, teach="article",
                   fix=swap(s.line, article_tok.col, article_tok.end, article(words).split(" ")[0]))
        return Expr("truth", lambda env: env.get(PROBLEM_ERROR).kind == words)

    def not_a_choice(self, s, tok, type_):
        """Refuse a word that is not one of the choices of the set `type_`."""
        cset = self.choice_sets[type_]
        self.misspelt(s, tok, cset.choices, "choice")
        s.fail(f'"{tok.text}" is not one of the {pluralize(cset.word)}: {article(cset.word)} is one of '
               f"{join_words(cset.choices, 'or')}.", tok,
               hint=f'To allow it, add it to the sentence that lists them: "{cap(article(cset.word))} is one of ...".',
               teach="choice")

    def comparison_words(self, s):
        """After "is": refuse a comparison written another way ("bigger than", "equal to",
        "no more than", "more then", "at lest"), with the comparison EnglishScript uses."""
        words = [s.peek(k) for k in range(5)]
        low = [t.low if t.kind == "WORD" else "" for t in words]
        if not low[0] or self.defined_word(low[0]):
            return
        found = None  # (how many words, what to write instead)
        or_equal = low[2:5] == ["or", "equal", "to"]
        if low[0] in BIGGER and low[1] == "than":
            found = (5, "at least") if or_equal else (2, "more than")
        elif low[0] in SMALLER and low[1] == "than":
            found = (5, "at most") if or_equal else (2, "less than")
        elif low[0] in ("above", "over"):
            found = (1, "more than")
        elif low[0] in ("below", "under"):
            found = (1, "less than")
        elif low[0] == "no" and low[1] in ("more", "greater", "bigger", "larger") and low[2] == "than":
            found = (3, "at most")
        elif low[0] == "no" and low[1] in ("less", "fewer", "smaller") and low[2] == "than":
            found = (3, "at least")
        elif low[0] == "equal" and low[1] == "to":
            found = (2, "")
        elif low[0:3] == ["the", "same", "as"]:
            found = (3, "")
        spelling = False
        if found is None:
            spelling = True  # a slip of the pen in the comparison's own words
            if low[0] in ("more", "less", "greater") and low[1] == "then":
                found = (2, f"{low[0]} than")
            elif low[0] == "at" and low[1] and len(close_words(low[1], ["least", "most"])) == 1:
                found = (2, "at " + close_words(low[1], ["least", "most"])[0])
            elif low[1] == "than" and len(close_words(low[0], ["more", "less", "greater"])) == 1:
                found = (2, close_words(low[0], ["more", "less", "greater"])[0] + " than")
            else:
                return
        count, right = found
        first, last = words[0], words[count - 1]
        written = s.line.text[first.col:last.end]
        if spelling:
            message = f'I don\'t know the words "{written}". Did you mean "{right}"?'
            fix = swap(s.line, first.col, last.end, right)
        elif right:
            message = f'"{written}" is written "{right}" in EnglishScript.'
            fix = swap(s.line, first.col, last.end, right)
        else:
            before = s.toks[s.i - 1]  # "is" or "not": what remains is "is 5"
            message = f'"is {written}" is written just "is" in EnglishScript.'
            fix = swap(s.line, before.end, last.end, "")
        s.fail_span(message, (first.col, last.end), teach="comparison", fix=fix,
                    category="spelling" if spelling else None)

    def divisible(self, s, left, right):
        for side in (left, right):
            self.need(s, side)
            if side.type != "number":
                s.fail_span(
                    f'"Divisible by" is about plain numbers, but {side.text} is {self.describe(side.type)}.',
                    side.span, teach="arith",
                )
        lf, rf = left.fn, right.fn
        check = f"{right.text} was 0. Check it first: If {right.text} is not 0:"

        def fn(env):
            divisor = rf(env)
            if divisor == 0:
                raise EnglishError("Nothing is divisible by zero.", stage="run", recoverable=True, teach="zero",
                                   hint=check)
            return (lf(env) / divisor).denominator == 1
        cond = Expr("truth", fn)
        cond.subject = left
        return cond

    def compare(self, s, op, left, right):
        self.need(s, left)
        self.need(s, right)
        lt, rt = left.type, right.type
        if is_list(lt) or is_list(rt):
            s.fail_span("Lists can't be compared yet.", (left.span[0], right.span[1]),
                        hint='Go through a list with "For each ... in ...:".', teach="list")
        ordered = ("number", "money", "percent")
        if lt != rt or (op != "=" and lt not in ordered):
            span = (left.span[0], right.span[1])
            if lt != rt:
                hint = None
                if right.literal and rt == "number" and lt == "money":
                    hint = f"If you meant money, write ${right.text}."
                s.fail_span(f"I can't compare {self.describe(lt)} with {self.describe(rt)}: "
                            f"{left.text} is {self.describe(lt)}, and {right.text} is {self.describe(rt)}.",
                            span, hint=hint, teach="compare_kinds")
            s.fail_span("Only numbers, money and percentages can be more or less than each other.", span,
                        teach="compare_kinds")
        lf, rf = left.fn, right.fn
        if op == "=":
            if lt in self.kinds:
                fn = lambda env: lf(env) is rf(env)
            else:
                fn = lambda env: lf(env) == rf(env)
        elif op == "<":
            fn = lambda env: lf(env) < rf(env)
        elif op == ">":
            fn = lambda env: lf(env) > rf(env)
        elif op == "<=":
            fn = lambda env: lf(env) <= rf(env)
        else:
            fn = lambda env: lf(env) >= rf(env)
        cond = Expr("truth", fn)
        cond.subject = left
        if op == "=":
            cond.equal = (left, right)
        return cond

    # -------------------------------------------------------------- blocks

    def block(self, lines, scope=None):
        saved = self.scope
        saved_span = self.span
        self.span = None if scope is self.globals else block_span(lines)
        self.scope = scope if scope is not None else Scope(saved)
        for line in lines:
            line.level = self.level  # how far in it is, for the trace
        self.level += 1
        try:
            steps, i, places = [], 0, []
            leaving, warned = False, False  # has a sentence that always leaves been seen?
            while i < len(lines):
                line = lines[i]
                place = i
                if not self.linting(line):
                    i, step = self.sentence(lines, i)
                else:
                    # Carry on after a refused sentence. What it would have
                    # defined is then unknown; the linter leaves out the errors
                    # that only that causes.
                    if line.broken:  # its words couldn't be read; already reported
                        self.lint.lost(line, self)
                        self.advise_inside(line.children)
                        i = self.past_sentence(lines, i)
                        continue
                    if line.stray:  # sentences were indented under it by mistake
                        for child in line.children:
                            self.lint.lost(child, self)
                        self.advise_inside(line.children)
                    present = self.present
                    try:
                        i, step = self.sentence(lines, i)
                    except EnglishError as error:
                        self.lint.refused(error, line, self)
                        self.present = present
                        after = self.past_sentence(lines, i)
                        self.advise_inside(line.children)
                        self.advise_inside(lines[i + 1:after])  # its Otherwise or If that fails parts
                        i = after
                        continue
                if step is None:
                    continue
                if leaving and not warned and self.linting(line):
                    self.lint.warn(
                        line, line.indent, len(line.text) - line.indent,
                        "This sentence is never reached: the one before it always leaves.",
                        "Remove it, or move it above the sentence that leaves.", "unreachable",
                    )
                    warned = True
                steps.append(step)
                places.append(place)
                leaving = leaving or step.leaves
            return self.group_judgements(steps, places)
        finally:
            self.scope = saved
            self.span = saved_span
            self.level -= 1

    def linting(self, line):
        """Is the linter collecting problems for this sentence of the program?"""
        return self.lint is not None and self.library is None and not line.library

    def sentence(self, lines, i):
        """Compile the sentence at lines[i], with its block, and any Otherwise or
        If that fails parts that go with it. Returns (index after it, step or None)."""
        line = lines[i]
        if self.linting(line):
            self.lint.capital(line)
        if line.question:
            self.line = line
            raise self.question(line)
        found = self.table_advice(Sentence(line))
        if found:
            self.line = line
            message, hint, col, width, teach, fix = found
            raise EnglishError(message, line, col, width, hint, teach=teach, fix=fix)
        if self.is_if_fails(line):
            self.line = line
            Sentence(line).fail('"If that fails" has to come straight after a "Try:" block.',
                                hint='Line it up with the "Try:" whose problems it deals with.', teach="try")
        if self.is_either_way(line):
            self.line = line
            Sentence(line).fail('"Either way" has to come straight after the "If that fails:" block of a "Try:".',
                                hint='Line it up with the "Try:" and its "If that fails:".', teach="try")
        if line.tokens[0].is_word("try"):
            i, step = self.try_chain(lines, i)
            return i, self.located(line, step)
        if line.tokens[0].is_word("if"):
            i, step = self.if_chain(lines, i)
            return i, self.located(line, step)
        step = self.statement(line)
        if step is None:
            return i + 1, None
        if getattr(step, "changes", False) and self.reactive and self.workout is None:
            # A reaction may follow this sentence and change any thing or top-level variable.
            self.forget_after_verb()
            step = self.watched(step, line)
        return i + 1, self.located(line, step)

    def question(self, line):
        """'Is Smaug ancient?': a program has no questions. Say how to test it, and how
        to say the answer, with the writer's own words where they are certain to read."""
        toks = line.tokens[:-1]
        first = toks[0]
        found = None
        if first.is_word("is", "are") and len(toks) >= 3:
            for k in range(2, len(toks)):
                np, rest = toks[1:k], toks[k:]
                trial = np + [Token("WORD", "is", np[-1].end)] + rest + [Token("END", "", rest[-1].end)]
                saved = (self.present, len(self.notes))
                try:
                    sub = Sentence(line, trial)
                    self.condition(sub)
                    if sub.at_end():
                        text = line.text
                        found = f"{text[np[0].col:np[-1].end]} is {text[rest[0].col:rest[-1].end]}"
                except EnglishError:
                    pass
                finally:
                    self.present = saved[0]
                    del self.notes[saved[1]:]
                if found:
                    break
        if found:
            hint = (f"To do something only when it is so, write: If {found}:\n"
                    f"To say whether it is so, write: Say whether {found}.")
        elif first.is_word("is", "are", "does", "do", "did", "has", "have", "was", "were"):
            hint = ("To do something only when it is so, write: If ... is ...:\n"
                    "To say whether it is so, write: Say whether ... is ...")
        else:
            hint = "To show a value, write: Say ...\nTo do something only when it is so, write: If ... is ...:"
        return EnglishError("EnglishScript has no questions: a sentence gives an instruction, and ends with a period.",
                            line, first.col, len(line.text) - first.col, hint, teach="question")

    @staticmethod
    def changing(step):
        """Mark a step as one that may change things, so reactions are looked for after it."""
        step.changes = True
        return step

    @staticmethod
    def watched(fn, line):
        """Carry out a step that may change things, then the reactions it sets off."""
        focus = getattr(fn, "focus", None)  # env -> the one thing the sentence changes, if only one

        def step(env):
            world = env.world
            world.changed = True  # this turn has changed something (World.settle)
            if not world.reactions:  # no "Whenever ... becomes" has been reached yet
                fn(env)
                return
            before = world.noting(focus(env) if focus is not None else None)
            fn(env)
            try:
                world.react(before)
            except EnglishError as error:
                # A problem in a reaction is a problem in the sentence that set it off.
                if line is not None and error.line is not None and error.line is not line and len(error.trace) < 5:
                    error.trace.append(line)
                raise
        return step

    def program(self, lines):
        """Compile a whole program's top-level lines (read with unit=self.main)."""
        main = self.main
        main.first = lines[0] if lines else None
        if main.path is not None:  # so that a chapter using the program itself is a circle
            key = os.path.normcase(str(main.path))
            self.chapters[key] = main
        self.reading = [main]
        self.reactive = self.expects_reactions(lines, main.folder, set())
        steps = self.block(lines, self.globals)
        self.check_shares(main)
        return steps

    def expects_reactions(self, lines, folder, seen):
        """Does a top-level sentence say "Whenever", here, in a chapter used (at any
        depth), or in the SOURCE of a library used?"""
        for line in lines:
            first = line.tokens[0] if line.tokens else None
            if first is None:
                continue
            if first.is_word("whenever"):
                return True
            if first.is_word("keep") and any(t.is_word("as", "when") for t in line.tokens):
                return True  # "Keep ... as ...": kept values are kept in step at the end of each turn
            words = self.chapter_words(line.tokens[2:]) if first.is_word("use") and folder is not None else None
            if words is not None:
                place = self.book_place(folder, words[1])
                path = self.chapter_file(place[0] if isinstance(place, tuple) else place, *words)
                key = os.path.normcase(os.path.abspath(path))
                if key in seen:
                    continue
                seen.add(key)
                try:
                    inner = read_source(self.chapter_text(path), problems=[])
                except (OSError, ValueError):
                    continue  # reported when the "Use" sentence is compiled
                if self.expects_reactions(inner, path.parent, seen):
                    return True
                continue
            if first.is_word("use") and len(line.tokens) > 2 and line.tokens[2].kind == "WORD":
                name = line.tokens[2].low
                if name not in self.library_names():
                    continue
                try:
                    source = getattr(importlib.import_module(f"{libraries.__name__}.{name}"), "SOURCE", "")
                except Exception:  # noqa: BLE001 - reported when the "Use" sentence is compiled
                    continue
                if isinstance(source, str) and WHENEVER_LINE.search(source):
                    return True
        return False

    def past_sentence(self, lines, i):
        """The index after the sentence at lines[i] and the parts that go with it."""
        first = lines[i].tokens[0]
        i += 1
        if first.is_word("if") and not self.is_if_fails(lines[i - 1]):
            while i < len(lines) and lines[i].tokens[0].is_word("otherwise"):
                i += 1
        elif first.is_word("try") and i < len(lines) and self.is_if_fails(lines[i]):
            i += 1
        return i

    @staticmethod
    def answers(steps):
        """Does carrying out these steps always reach "The answer is"?"""
        return any(getattr(step, "answers", False) for step in steps)

    @staticmethod
    def located(line, fn):
        def step(env):
            if env.world.trace is not None:
                env.world.traced(line)
            try:
                fn(env)
            except EnglishError as error:
                if error.line is None:
                    error.line = line
                raise
        step.answers = getattr(fn, "answers", False)
        step.leaves = getattr(fn, "leaves", False)
        step.line = line
        step.judging = getattr(fn, "judging", None)
        return step

    @staticmethod
    def group_judgements(steps, places):
        """Put consecutive "Judge" sentences about the same state, written the same way, into
        groups, so that a `judges` listener can be asked them at once (section 7.8). A
        sentence that reads a name an earlier one of the group sets starts a new group.
        `places` is the index of each step's line among the block's lines."""
        out, k = [], 0
        while k < len(steps):
            run = [steps[k]]
            if getattr(steps[k], "judging", None) is not None:
                state, sets = steps[k].judging["state"], list(steps[k].judging["sets"])
                while k + len(run) < len(steps):
                    nxt = steps[k + len(run)]
                    info = getattr(nxt, "judging", None)
                    if (info is None or info["state"] != state or places[k + len(run)] != places[k] + len(run)
                            or any(re.search(r"\b" + re.escape(name) + r"\b", info["reads"]) for name in sets)):
                        break
                    run.append(nxt)
                    sets += info["sets"]
            out.append(run[0] if len(run) == 1 else judgement_group(run))
            k += len(run)
        return out

    @staticmethod
    def leaves(steps):
        """Do these steps always leave their block (Stop, Skip, The answer is, End)?"""
        return any(getattr(step, "leaves", False) for step in steps)

    @staticmethod
    def run_block(steps, env):
        inner = Env(env)
        for step in steps:
            step(inner)

    def needs_block(self, s, yes):
        opens = s.line.terminator == ":"
        line, end = s.line, len(s.line.text) - 1
        if yes and not opens:
            # Certain only when sentences are indented under it already.
            fix = swap(line, end, end + 1, ":") if line.children and line.text.endswith(".") else None
            raise EnglishError(
                "This sentence opens a block, so it ends with a colon, not a period.", line, end, 1,
                hint="Indent the sentences that belong to it under it." if not line.children else None,
                teach="colon", fix=fix,
            )
        if opens and not yes:
            fix = swap(line, end, end + 1, ".") if not line.children else None
            raise EnglishError(
                "This sentence does not open a block, so it ends with a period, not a colon.", line, end, 1,
                teach="no_colon", fix=fix,
            )

    def if_chain(self, lines, i):
        """An If, its Otherwise ifs and its Otherwise.

        A branch's block may rely on what its condition checked, and on what
        the earlier conditions ruled out. Anything a branch changes stops
        being relied on after the chain.
        """
        before = self.present
        lost = set()
        ruled_out = NONE  # known because every earlier condition was false
        branches, otherwise, all_answer, all_leave = [], None, True, True

        def body(line, known):
            self.present = before | ruled_out | known
            steps = self.block(line.children)
            lost.update(before - self.present)
            return steps

        skip = 1
        while True:
            line = lines[i]
            self.line = line
            s = Sentence(line)
            s.i = skip
            found = self.then_advice(s, skip)
            if found:
                message, hint, col, width, teach, fix = found
                raise EnglishError(message, line, col, width, hint, teach=teach, fix=fix)
            self.needs_block(s, True)
            self.present = before | ruled_out
            cond = self.condition(s)
            self.end(s)
            steps = body(line, cond.nt)
            branches.append((cond.fn, steps))
            all_answer = all_answer and self.answers(steps)
            all_leave = all_leave and self.leaves(steps)
            ruled_out = ruled_out | cond.nf
            i += 1
            if i >= len(lines) or not lines[i].tokens[0].is_word("otherwise"):
                break
            line = lines[i]
            self.line = line
            if self.linting(line):
                self.lint.capital(line)
            if line.tokens[1].is_word("if"):
                skip = 2
                continue
            s = Sentence(line)
            s.i = 1
            self.needs_block(s, True)
            self.end(s)
            otherwise = body(line, NONE)
            all_answer = all_answer and self.answers(otherwise)
            all_leave = all_leave and self.leaves(otherwise)
            i += 1
            if i < len(lines) and lines[i].tokens[0].is_word("otherwise"):
                self.line = lines[i]
                Sentence(lines[i]).fail('Nothing can follow a plain "Otherwise:": it is the last part of an "If".',
                                        hint='Put any "Otherwise if ...:" parts before the plain "Otherwise:".',
                                        teach="otherwise")
            break
        if otherwise is None and all_leave:
            # A guard: every branch leaves, so getting past the chain means no
            # branch ran, and every condition is known to have been false.
            self.present = before | ruled_out
        else:
            self.present = before - lost
        run = self.run_block

        def step(env):
            for cond_fn, steps in branches:
                if cond_fn(env):
                    run(steps, env)
                    return
            if otherwise is not None:
                run(otherwise, env)
        step.answers = all_answer and otherwise is not None
        step.leaves = all_leave and otherwise is not None
        return i, step

    def loop_body(self, lines, noun=None, binding=None, head=None):
        """Compile the block of a loop. Returns (loop id, steps), or (loop id, steps,
        condition) when `head` compiles a condition checked before each round
        ("While"): what it shows holds inside the block.

        A loop's block runs again after its own last sentence, so it may not rely
        on anything that it changes further down. The block is compiled to see
        what it changes, and again without relying on those, until what is known
        at its start still holds at its end. Until then, a check that looks
        needless only because of what was known before the loop is let through
        ("lenient"); the block is then compiled once more, strictly.
        """
        loop = {"id": self.uid(), "noun": noun}
        before = self.present
        mark = len(self.notes)
        self.loops.append(loop)
        outer, outer_used, used_any = self.lenient, self.lenient_used, False
        final, cond = False, None
        try:
            for attempt in range(8):
                start = self.present
                final = final or attempt == 7
                self.lenient, self.lenient_used = (outer if final else True), False
                # What is known at each "Skip" and "Stop repeating" aimed at this
                # loop: a round can also end there, part way through the block.
                loop["skips"], loop["stops"] = [], []
                if head is not None:
                    cond = head()
                    self.present = self.present | cond.nt
                scope = Scope(self.scope)
                if binding is not None:
                    scope.names[binding.name] = binding
                steps = self.block(lines, scope)
                used = self.lenient_used
                used_any = used_any or used
                end = self.present
                for known in loop["skips"]:
                    end = end & known
                if start <= end:
                    if final or not used:
                        break
                    final = True
                    self.present = start
                else:
                    self.present = start & end
                del self.notes[mark:]
        finally:
            self.loops.pop()
            self.lenient, self.lenient_used = outer, outer_used or used_any
        for known in loop["stops"]:
            end = end & known
        self.present = before & end
        if head is not None:
            return loop["id"], steps, cond
        return loop["id"], steps

    @staticmethod
    def is_if_fails(line):
        toks = line.tokens
        return len(toks) >= 3 and toks[0].is_word("if") and toks[1].is_word("that") and toks[2].is_word("fails")

    @staticmethod
    def is_either_way(line):
        toks = line.tokens
        return len(toks) >= 2 and toks[0].is_word("either") and toks[1].is_word("way")

    def try_chain(self, lines, i):
        """Try: ... If that fails: ...

        A failed Try puts the world back as it was, so the "If that fails"
        block starts from what was known before the Try. Afterwards, nothing
        that either block may have changed is relied on.
        """
        line = lines[i]
        self.line = line
        s = Sentence(line)
        s.next()  # try
        self.needs_block(s, True)
        self.end(s)
        if i + 1 >= len(lines) or not self.is_if_fails(lines[i + 1]):
            s.fail(
                'A "Try:" block needs an "If that fails:" block straight after it.', s.toks[0],
                hint="Say what to do when it goes wrong, at the same indent as the Try.", teach="try",
            )
        before = self.present
        tried = self.block(line.children)
        after_try = self.present
        fails_line = lines[i + 1]
        self.line = fails_line
        if self.linting(fails_line):
            self.lint.capital(fails_line)
        s = Sentence(fails_line)
        s.i = 3
        self.needs_block(s, True)
        self.end(s)
        self.present = before
        scope = Scope(self.scope)
        scope.names[PROBLEM] = Binding(PROBLEM, "text")
        scope.names[PROBLEM_ERROR] = Binding(PROBLEM_ERROR, "text")
        fallback = self.block(fails_line.children, scope)
        self.present = before & after_try & self.present
        either = None
        if i + 2 < len(lines) and self.is_either_way(lines[i + 2]):
            either_line = lines[i + 2]
            self.line = either_line
            if self.linting(either_line):
                self.lint.capital(either_line)
            s = Sentence(either_line)
            s.i = 2
            self.needs_block(s, True)
            self.end(s)
            either = self.block(either_line.children)
        run = self.run_block

        def attempt(env):
            restore = env.world.snapshot(env)
            try:
                run(tried, env)
            except EnglishError as error:
                if not error.recoverable:
                    raise
                restore()
                inner = Env(env)
                inner.vars[PROBLEM] = error.message
                inner.vars[PROBLEM_ERROR] = error
                for inner_step in fallback:
                    inner_step(inner)

        if either is None:
            step = attempt
        else:
            def step(env):
                """"Either way:" is carried out however the Try and "If that fails" end,
                unless the program is ending (End the program, or a fault)."""
                try:
                    attempt(env)
                except _EndProgram:
                    raise
                except EnglishError as error:
                    if not error.recoverable:
                        raise
                    run(either, env)
                    raise
                except _Signal:
                    run(either, env)
                    raise
                run(either, env)
        leaves = self.leaves(tried) and self.leaves(fallback)
        answers = self.answers(tried) and self.answers(fallback)
        if either is not None:
            leaves = leaves or self.leaves(either)
            answers = answers or self.answers(either)
        step.answers, step.leaves = answers, leaves
        return i + (2 if either is None else 3), step

    # ---------------------------------------------------------- statements

    def statement(self, line):
        self.line = line
        s = Sentence(line)
        first = s.peek()
        if first.kind != "WORD":
            s.fail(f'A sentence starts with a word, not with "{first.text}".', hint="Most sentences start with "
                   'their verb, such as "Say" or "Set".', teach="verb_first")
        word = first.low
        top = self.scope is self.globals

        if word == "the" and s.peek(1).is_word("answer"):
            self.needs_block(s, False)
            return self.answer(s)

        definition = None
        if word in ("a", "an"):
            nxt = s.peek(2)
            if nxt.is_word("has") or (nxt.is_punct("(") and s.peek(3).is_word("plural")):
                definition = self.define_kind
            elif nxt.is_word("is") and s.peek(3).is_word("one") and s.peek(4).is_word("of"):
                definition = self.define_choices
            elif nxt.is_word("is"):
                definition = self.define_adjective
            elif nxt.is_word("can"):
                definition = self.define_stored_adjective
            elif nxt.kind == "POS":
                definition = self.define_rule
            else:
                kind = s.peek(1).text
                if nxt.is_word("are"):
                    s.fail(f'After one {kind}, write "is", not "are".', nxt, teach="is_are",
                           fix=s.replace(nxt, "is"))
                self.misspelt(s, nxt, ["has", "is", "can"], "definition_form")
                s.fail(
                    f'After "{s.line.text[first.col:s.peek(1).end]}" comes "has", "is", "can be" or "\'s": '
                    "a sentence that starts with a kind is a definition.", nxt,
                    hint='For example: "A dragon has an age (number)."  or  "A dragon is ancient when ...".',
                    teach="definition_form",
                )
        elif word == "the" and self.defines_property(s):
            definition = self.define_property
        elif word == "to":
            definition = self.define_procedure
        elif word == "there" and not s.peek(3).is_word("new"):
            definition = self.create_thing
        elif word == "use":
            definition = self.use_library
        elif word == "whenever":
            definition = self.define_reaction
        elif word == "keep" and self.keep_ahead(s):
            definition = self.define_keep
        elif word == "this" and s.peek(1).is_word("chapter"):
            definition = self.shares_sentence
        elif word == "for" and s.peek(1).is_word("a", "an") and s.peek(3).is_punct(","):
            definition = self.define_meaning
        if definition:
            if not top:
                s.fail("This definition belongs at the top level, not inside a block.",
                       hint="Move it out of the block, and start it at the left edge.", teach="top_level")
            if word == "to" and self.done_by_library(line):
                return self.define_outside(s)
            self.needs_block(s, word in ("to", "whenever") and not self.one_question(line))
            return definition(s)

        if word == "otherwise":
            s.fail('"Otherwise" has to come straight after an "If" block.',
                   hint='Line it up with its "If", straight after the sentences of that If.', teach="otherwise")
        if word == "for" and s.peek(1).is_word("example"):
            self.needs_block(s, False)
            return self.example(s)
        blocks = {"for": self.for_each, "repeat": self.repeat, "while": self.while_loop}
        simple = {
            "let": self.let, "set": self.assign, "add": self.assign, "subtract": self.assign,
            "multiply": self.assign, "divide": self.assign, "say": self.say,
            "stop": self.stop, "skip": self.skip, "end": self.end_program,
            "there": self.create_new, "now": self.now, "remove": self.remove, "ask": self.ask,
            "write": self.write, "fail": self.fail_because,
        }
        if word in blocks:
            self.needs_block(s, True)
            return blocks[word](s)
        if word == "judge" and self.judge_ahead(s):
            self.needs_block(s, False)
            return self.judge(s)
        if word in simple:
            self.needs_block(s, False)
            return simple[word](s)
        if word in self.procs:
            self.needs_block(s, False)
            return self.call(s)
        proc = self.procs.elsewhere(word)
        if proc is not None:  # a verb of another file, which this one may not use
            message, hint = self.unseen(word, proc.unit, word)
            s.fail(message, first, hint=hint, teach="shared")
        advice = self.start_advice(s, first)
        if advice:
            message, hint, teach, fix = advice
            s.fail(message, first, hint=hint, teach=teach, fix=fix)
        if word == "the":
            s.fail(
                "A sentence starts with a verb, or with a definition.", first,
                hint='To define a worked-out property: "The interest of a dragon is 5% of its hoard."',
                teach="verb_first",
            )
        starts = list(simple) + list(blocks) + ["if", "try", "otherwise", "use", "whenever", "judge"]
        self.not_a_verb(s, first, starts)

    def not_a_verb(self, s, first, starts):
        """Refuse a sentence whose first word is not a verb: a word put in front of the
        verb ("Please tax Smaug."), a name ("Smaug tax."), a misspelt verb ("Txa
        Smaug."), a question without its question mark, or a verb not taught yet."""
        line, word = s.line, first.low
        verbs = starts + list(self.procs)
        nxt = s.peek(1)
        if nxt.is_punct(","):
            nxt = s.peek(2)
        if word in FILLERS and not self.defined_word(word) and nxt.kind == "WORD" and nxt.low in verbs:
            fix = swap(line, first.col, nxt.end, cap(nxt.text))
            s.fail(f'A sentence begins with its verb, so there is no need for "{first.text}".', first,
                   teach="verb_first", fix=fix)
        if word in QUESTION_WORDS and not self.defined_word(word) and word not in self.procs:
            raise self.question(line)
        what = self.what_it_is(s)
        if what:
            subject, count = what
            last = s.toks[count - 1]
            # A verb further on, perhaps with an ending: "Smaug tax.", "Smaug should be taxed."
            verb_tok, proc = None, None
            for tok in s.toks[count:]:
                if tok.kind != "WORD":
                    continue
                low = tok.low
                stems = {low, low[:-1], low[:-2], low[:-3], low[:-3] + "e"}
                found = next((v for v in self.procs if v in stems), None)
                if found:
                    verb_tok, proc = tok, self.procs[found]
                    break
            fix = hint = None
            if proc is not None:
                hint = "It goes: " + proc.usage()
                written = line.text[first.col:last.end]
                params = proc.params
                object_kind = self.names[written.lower()][1] if written.lower() in self.names else None
                if (s.toks[count] is verb_tok and s.toks[count + 1].kind == "END" and len(params) == 1
                        and params[0].prep is None and object_kind == params[0].type):
                    fix = swap(line, first.col, verb_tok.end, f"{cap(proc.verb)} {written}")
                    hint = None
            elif self.procs:
                hint = "Verbs taught so far: " + ", ".join(some_of(self.procs, word)) + "."
            s.fail(f'A sentence begins with its verb, and "{line.text[first.col:last.end]}" is {subject}, '
                   "not a verb.", first, hint=hint, teach="verb_first", fix=fix)
        close = close_words(first.text, verbs)
        if len(close) == 1:
            s.fail(f'I don\'t know the word "{first.text}". Did you mean "{cap(close[0])}"?', first,
                   teach="unknown_verb", category="spelling", fix=s.replace(first, close[0]))
        hints = []
        if close:
            hints.append("Words that would fit here: " + ", ".join(cap(v) for v in close) + ".")
        if self.procs and len(self.procs) <= 8:
            hints.append("Verbs taught so far: " + ", ".join(self.procs) + ".")
        if word not in KEYWORDS and not self.defined_word(word):
            match = self.match_words(s, self.names, 1)
            if match:
                kind = self.names[match[0]][1]
                hints.append(f'Teach it to me first, with a heading such as "To {word} {self.describe(kind)}:" '
                             "and an indented block.")
            else:
                hints.append(f'Teach it to me first: "To {word} ...:" followed by an indented block.')
        s.fail(f'I don\'t know the verb "{first.text}".', first, hint="\n".join(hints) or None, teach="unknown_verb")

    def what_it_is(self, s):
        """If the sentence starts with a name rather than a verb: (what it is, as "a
        dragon" or "an adjective", and how many words it takes); otherwise None."""
        match = self.match_words(s, self.names)
        if match:
            return self.describe(self.names[match[0]][1]), match[1]
        tok = s.peek()
        if tok.low in self.nouns:
            kind, plural = self.nouns[tok.low]
            return ("the plural of a kind" if plural else "a kind"), 1
        match = self.match_words(s, self.scope.visible())
        if match:
            return "a variable", match[1]
        if tok.low in self.adjective_names:
            return "an adjective", 1
        if tok.low in self.member_names:
            return "a property", 1
        return None

    # advice for sentences borrowed from programming or loose English -----
    #
    # A hint shows a sentence to write. It repeats the writer's own words only
    # where the result is certain to be accepted: a quoted text, a number or
    # money, or a single new name where any new name works. Anywhere else it
    # shows "..." or a general example.

    def index_words(self, name, where_):
        """Remember that each word of `name` is part of a name in `where_` (a registry,
        or None for one that is always in view), for defined_word."""
        for word in name.split(" "):
            self.word_index.setdefault(word, []).append((name, where_))

    def defined_word(self, word):
        """Is `word` part of a name the program has given a meaning, that this file
        may say? Found through the index of words, not by going through every name."""
        for name, registry in self.word_index.get(word, ()):
            if registry is None or name in registry:  # a View says whether this file may say it
                return True
        return any(word in name.split(" ") for name in self.scope.visible())

    @staticmethod
    def words_after(s, tok):
        """The tokens after `tok`, to the end of the sentence, without brackets round them all."""
        toks = s.toks[s.toks.index(tok) + 1:-1]
        if len(toks) >= 2 and toks[0].is_punct("(") and toks[-1].is_punct(")"):
            toks = toks[1:-1]
        return toks

    @staticmethod
    def certain_value(toks, type_=None):
        """The writer's value, if it is one quoted text (without fill-ins) or one number,
        money or percentage, of `type_` when that is given; otherwise None."""
        if len(toks) != 1:
            return None
        tok = toks[0]
        kinds = {"NUMBER": "number", "MONEY": "money", "PERCENT": "percent", "STRING": "text"}
        if tok.kind not in kinds or (type_ is not None and kinds[tok.kind] != type_):
            return None
        if tok.kind == "STRING" and ("{" in tok.text or "}" in tok.text):
            return None
        return tok.text

    def new_name(self, toks):
        """The writer's name, if it is one new word (after "the", perhaps)."""
        prefix = ""
        if toks and toks[0].is_word("the"):
            prefix, toks = "the ", toks[1:]
        if len(toks) != 1:
            return None
        tok = toks[0]
        if tok.kind != "WORD" or tok.low in KEYWORDS or self.defined_word(tok.low) or tok.low in self.names:
            return None
        return prefix + tok.text

    def changeable(self, toks):
        """(name as written, its type) if the tokens are a variable that Set and Add may change."""
        name = " ".join(t.low for t in toks if t.kind == "WORD")
        if any(t.kind != "WORD" for t in toks) or not name:
            return None
        bare = name[4:] if name.startswith("the ") else name
        binding = self.scope.find(bare)
        if binding is None or not binding.let:
            return None
        written = " ".join(t.text for t in toks)
        return (name if toks[0].is_word("the") else written), binding.type

    def table_advice(self, s):
        """Advice that needs nothing but the sentence's own words: a sentence that starts
        with a word from another language, "==", or "then" after a condition.
        Returns (message, hint, column, width, rule, fix) or None."""
        first = s.peek()
        if first.kind == "WORD":
            found = self.borrowed_advice(s, first)
            if found:
                message, hint, teach, fix = found
                return message, hint, first.col, len(first.text), teach, fix
        for a, b in zip(s.toks, s.toks[1:]):
            if a.is_punct("=") and b.is_punct("=") and b.col == a.end:
                return ('EnglishScript doesn\'t use "==".',
                        'To test that two values are equal, write "is", in a condition: If ... is ...:', a.col, 2,
                        "symbols", swap(s.line, a.col, b.end, "is"))
        if first.is_word("if") or (first.is_word("otherwise") and s.peek(1).is_word("if")):
            return self.then_advice(s, 1 if first.is_word("if") else 2)
        return None

    def then_advice(self, s, skip):
        """'If ... then': the condition ends with a colon instead."""
        then = next((t for t in s.toks[skip:] if t.is_word("then")), None)
        if then is None or self.defined_word("then"):
            return None
        opener = s.line.text[s.toks[0].col:s.toks[skip].col].strip()
        fix = None
        k = s.toks.index(then)
        if s.toks[k + 1].kind == "END" and k > skip:  # "If x is 1 then" or "If x is 1 then:"
            fix = swap(s.line, s.toks[k - 1].end, len(s.line.text), ":")
        return ('EnglishScript doesn\'t use "then".',
                f"End the condition with a colon instead, and indent what follows: {opener} ...:",
                then.col, len(then.text), "then", fix)

    @staticmethod
    def whole(s, sentence):
        """The line with its sentence replaced by `sentence`, indentation and comment kept."""
        return swap(s.line, s.line.indent, len(s.line.text), sentence)

    def borrowed_advice(self, s, first):
        """(message, hint, rule, fix) for a sentence that starts with a word from another
        language, unless the program gave that word a meaning; or None."""
        word = first.low
        if self.defined_word(word):
            return None
        kind = BORROWED.get(word)
        rest = self.words_after(s, first)
        said = f'"{first.text}" isn\'t part of EnglishScript.'
        nxt = s.peek(2) if s.peek(1).is_punct(",") else s.peek(1)
        if word in FILLERS and nxt.kind == "WORD" and nxt.low in self.sentence_starts():
            return None  # "Next, say the total.": a word in front of the verb, see not_a_verb
        if word == "give" and s.peek(1).is_word("back"):
            kind, rest = "return", self.words_after(s, s.peek(1))
            said = f'"{first.text} back" isn\'t part of EnglishScript.'
        elif word == "else" and s.peek(1).is_word("if"):
            kind = "elif"
        if kind is None:
            return None
        value = self.certain_value(rest)
        if kind == "say":
            sentence = full_stop(f"Say {value or '...'}")
            return (f'EnglishScript shows things with "Say", not "{first.text}".', "Write: " + sentence, "say",
                    self.whole(s, sentence) if value else None)
        if kind == "else":
            alone = s.peek(1).kind == "END" and s.line.terminator == ":"
            return ('EnglishScript writes "else" as "Otherwise".',
                    'Write "Otherwise:" straight after the If block, and indent what follows.', "else",
                    s.replace(first, "Otherwise") if alone else None)
        if kind == "elif":
            last = s.peek(1) if word == "else" else first
            return ('EnglishScript writes "else if" as "Otherwise if".',
                    "Write, straight after the If block: Otherwise if ...:", "else",
                    swap(s.line, first.col, last.end, "Otherwise if"))
        if kind == "return":
            return (said, f'Inside "To work out ...:", the answer is given with: {full_stop("The answer is " + (value or "..."))}\n'
                          'To leave a verb early, write "Stop.".', "return", None)
        if kind == "remove":
            return (said, "To take a thing out of the world, write: Remove ...", "remove", None)
        if kind == "new":
            return (said, 'To make a thing, write: There is a new ... called "..." whose ...\n'
                          'To keep it in a variable: Let the ... be a new ... called "..." whose ...', "make", None)
        if kind == "define":
            return (said, 'To teach a verb, write a heading such as "To greet a dragon:" and indent its sentences.\n'
                          'To work out a value: "To work out the bounty (money) for a dragon:".', "define", None)
        if kind == "variable":
            equals = next((k for k, t in enumerate(rest) if t.is_punct("=")), None)
            name = value = None
            if equals is not None:
                name, value = self.new_name(rest[:equals]), self.certain_value(rest[equals + 1:])
            certain = name is not None and value is not None
            name = name or "the ..."
            fixed = " always" if word in ("const", "final", "constant") else ""
            sentence = full_stop(f"Let {name}{fixed} be {value or '...'}")
            return ('A variable is made with "Let", and needs no type word.',
                    "Write: " + sentence + ("" if fixed else f"\nTo change it later: Set {name} to ..."), "variable",
                    self.whole(s, sentence) if certain else None)
        if kind in ("increase", "decrease"):
            by = next((k for k, t in enumerate(rest) if t.is_word("by")), len(rest))
            target = self.changeable(rest[:by])
            amount = None
            if target and target[1] in ("number", "money"):
                amount = self.certain_value(rest[by + 1:], target[1]) if by < len(rest) else (
                    "1" if target[1] == "number" else "$1")
            certain = bool(target and amount)
            target_text = target[0] if certain else "..."
            amount = amount if certain else "..."
            if kind == "increase":
                sentence = full_stop(f"Add {amount} to {target_text}")
            else:
                sentence = full_stop(f"Subtract {amount} from {target_text}")
            return (said, "Write: " + sentence, "increase", self.whole(s, sentence) if certain else None)
        if kind == "ask":
            quoted = next((t for t in s.toks if t.kind == "STRING"), None)
            question = self.certain_value([quoted]) if quoted else None
            name = "the ..." if self.defined_word("response") else "the response"
            return (said, f"To ask the person at the keyboard, write: Ask {question or chr(34) + '...' + chr(34)} "
                          f"and let {name} (text) be the reply.", "ask", None)
        if kind == "use":
            name = rest[0].low if len(rest) == 1 and rest[0].kind == "WORD" else None
            known = name in self.library_names()
            sentence = f"Use the {name if known else '...'} library."
            return (said, f"To use a library, write: {sentence}", "use", self.whole(s, sentence) if known else None)
        if kind == "loop":
            return (said, 'To go through things: "For each dragon:". To repeat: "Repeat 3 times:".\n'
                          'To go on while something holds: "While the count is less than 10:".', "loop", None)
        if kind == "end":
            return (f'"{first.text}" isn\'t needed in EnglishScript.',
                    "A block ends where the indentation ends: just stop indenting.", "block_end", None)
        if kind == "break":
            return (said, 'To leave a loop, write "Stop repeating.".', "leave", None)
        if kind == "continue":
            return (said, 'To go on to the next round of a loop, write "Skip this round."\n'
                          '(in "For each dragon:", write "Skip this dragon.").', "leave", None)
        if kind == "exit":
            return (said, 'To finish the whole program, write "End the program.".', "leave", None)
        return None

    def sentence_starts(self):
        """The words a sentence may start with: EnglishScript's own, and the verbs taught."""
        return set(BUILTIN_VERBS) | {"now", "remove", "ask", "write", "fail", "try", "otherwise", "use",
                                     "whenever"} | set(self.procs)

    def start_advice(self, s, first):
        """(message, hint, rule, fix) for a sentence whose first word EnglishScript doesn't
        know, when it looks like a sentence from another language; or None."""
        advice = self.assignment_advice(s, first)
        if advice:
            return advice
        if s.peek(1).is_punct("(") and s.peek(1).col == first.end and not self.defined_word(first.low):
            return (f'EnglishScript has no function calls like "{first.text}(...)".',
                    'A verb is used as a sentence, such as "Greet Smaug.", and a worked-out value\n'
                    'as a phrase, such as "the bounty for Smaug".', "call", None)
        return None

    def assignment_advice(self, s, first):
        """'x = 5', 'x is 5', 'the total is 5' written as a sentence."""
        j = 0
        while s.peek(j).kind == "WORD" and not s.peek(j).is_word("is"):
            j += 1
        op = s.peek(j)
        if j == 0 or not (op.is_word("is") or op.is_punct("=")):
            return None
        name_toks = s.toks[:j]
        value_toks = s.toks[j + 1:-1]
        if not value_toks:
            return None
        variable = self.changeable(name_toks)
        if variable:
            name, type_ = variable
            value = self.certain_value(value_toks, base(type_))
            sentence = full_stop(f"Set {name} to {value or '...'}")
            return ('A sentence starts with a verb, so a variable is changed with "Set".', "Write: " + sentence,
                    "set", self.whole(s, sentence) if value else None)
        if op.is_punct("="):
            if self.defined_word(first.low) and first.low != "the":
                return None
            name, value = self.new_name(name_toks), self.certain_value(value_toks)
            name = name.lower() if name and name.lower().startswith("the ") else name
            certain = name is not None and value is not None
            name = name or "the ..."
            sentence = full_stop(f"Let {name} be {value or '...'}")
            return ('A sentence starts with a verb, so a variable is made with "Let".',
                    "Write: " + sentence + f"\nTo change it later: Set {name} to ...", "variable",
                    self.whole(s, sentence) if certain else None)
        # "Smaug is 771 years old.", "x is 5.": a statement of fact isn't a sentence.
        return ("A sentence starts with a verb, so a fact can't be stated on its own.",
                "To make a variable, write a sentence such as: Let the age be 771.\n"
                "To change a property: Set Smaug's age to 771.  To change a stored adjective: Now Smaug is sleepy.",
                "verb_first", None)

    @staticmethod
    def defines_property(s):
        """Does a sentence starting "The" read "The <name> of a <kind> is ..."?"""
        toks = s.toks
        return any(a.is_word("of") and b.is_word("a", "an") for a, b in zip(toks, toks[1:]))

    def for_advice(self, s):
        """'for x in ...' and 'for i = 1 to 10' are written another way."""
        tok = s.peek()
        if tok.kind == "WORD" and s.peek(1).is_word("in") and not self.defined_word(tok.low):
            rest = s.toks[s.i + 2:-1]
            group = None
            if len(rest) == 1 and rest[0].kind == "WORD" and self.nouns.get(rest[0].low, (None, False))[1]:
                group = rest[0].text
            name = self.new_name([tok])
            fix = None
            if name and group:
                fix = swap(s.line, s.toks[0].end, s.toks[0].end, " each")
            name = name or "..."
            s.fail('A loop over things is written "For each".', s.toks[0],
                   hint=f"Write: For each {name} in {group or '...'}:\n"
                        'What follows "in" is a group, such as "dragons", or a list. To count to 10, write "Repeat 10 times:".',
                   teach="loop", fix=fix)
        if tok.kind == "WORD" and s.peek(1).is_punct("=") and not self.defined_word(tok.low):
            s.fail("EnglishScript has no counting loop of this kind.", s.toks[0],
                   hint='To do something a number of times, write "Repeat 10 times:".\n'
                        'To count as you go, keep a variable: Let the count be 1. ... Add 1 to the count.',
                   teach="loop")

    def advise_inside(self, lines):
        """In the block of a refused sentence, nothing is compiled; but advice that
        needs only a sentence's own words is still given (for the linter)."""
        for line in lines:
            if not line.broken:
                found = self.table_advice(Sentence(line))
                if found:
                    message, hint, col, width, teach, fix = found
                    self.lint.add(EnglishError(message, line, col, width, hint, teach=teach, fix=fix), "error")
            self.advise_inside(line.children)

    # definitions --------------------------------------------------------

    def define_kind(self, s):
        s.next()
        ktok = s.next()
        self.check_new_name(s, [ktok], "the name of a kind")
        name = ktok.low
        seen = self.nouns.clash(name, self.unit)  # a kind in view, or one another file shares, if this one does
        if seen is not None and not seen[1]:
            self.described_again(s, ktok, self.kinds[seen[0]])
        self.not_an_adjective(s, [ktok], "the name of a kind")
        # The kind's key, which is its type: its name, unless the file keeps the kind to
        # itself, when another file may have a kind of its own with the same name.
        key = name
        if not self.unit.shares_name(name):
            key = f"{name} of {self.unit.title}"
            while key in self.kinds:
                key += "'"
        plural = pluralize(name)
        if s.eat_punct("("):  # "A person (plural people) has ...": a plural not formed by rule
            s.expect_word("plural", hint='For example: "A person (plural people) has an age (number)."',
                          teach="plural_form")
            ptok = s.next()
            if ptok.kind != "WORD":
                s.fail('After "plural" comes the plural: one word.', ptok, teach="plural_form")
            s.expect_punct(")")
            plural = ptok.low
            if plural == name:
                s.fail(f'A kind\'s plural has to differ from its name: with "{name}" for both, "the {name}" would '
                       "mean one and all of them at once.", ptok,
                       hint="Leave out the plural, to have it formed by rule, or choose a name for the kind whose "
                            "plural differs from it.", teach="kind_names")
            self.check_new_name(s, [ptok], "a plural")
            self.not_an_adjective(s, [ptok], "the plural of a kind")
            self.kind_words_free(s, ktok, name, plural)
            self.name_is_new(s, plural, ptok, shared_as=name)
        self.kind_words_free(s, ktok, name, plural)
        s.expect_word("has", teach="kind_form")
        K = Kind(key, plural, s.line, word=name)
        example = 'For example: "A dragon has an age (number) and a lair (text)."'
        while True:
            if not s.eat_word("a", "an"):
                tok = s.peek()
                if tok.kind == "WORD" and tok.low not in KEYWORDS:  # "A dragon has age (number)."
                    s.fail(f'A property takes an article: "{article(tok.text)}".', tok, teach="article",
                           fix=swap(s.line, tok.col, tok.col, article(tok.text)[:-len(tok.text)]))
                s.fail('After "has" comes a property, with "a" or "an", such as "a hoard (money)".', hint=example,
                       teach="kind_form")
            toks = []
            while s.peek().kind == "WORD" and not s.at_word("and"):
                toks.append(s.next())
            if not toks:
                s.fail('This needs the name of a property here, after "a" or "an".', hint=example, teach="kind_form")
            self.check_new_name(s, toks, "a property name")
            fname = " ".join(t.low for t in toks)
            if fname in K.fields:
                s.fail(f'"{fname}" is listed twice.', toks[0], hint="Take one of them out.", teach="taken")
            if fname in self.workouts:
                s.fail(f'"{fname}" is already something that is worked out'
                       f'{self.elsewhere(self.workouts[fname].unit)}, so a property can\'t share its name.', toks[0],
                       teach="taken")
            if not s.eat_punct("("):
                s.fail(
                    f'What sort of value is "{fname}"?', toks[0],
                    hint=f'Say so in brackets, e.g. "{article(fname)} (money)".\n'
                    "Types: number, money, text, percent, or a kind you have described.", teach="kind_form",
                )
            type_at = s.peek().col
            K.fields[fname] = self.bracket_type(s, also=(name, key, plural))
            if K.fields[fname] == key and self.linting(s.line):
                # "A node has a next (node).": the first node would need another before it.
                close = s.toks[s.i - 1]
                self.lint.warn(s.line, toks[0].col, close.end - toks[0].col,
                               f"{cap(article(name))} could never be made: each one needs another {name} as its "
                               f"{fname} before it can be made.", f'Let the {fname} be missing: "({name}, if any)".',
                               "endless_kind", swap(s.line, type_at, close.col, f"{name}, if any"))
            if base(K.fields[fname]) == YES_NO:
                s.fail(
                    f'A property can\'t be yes or no. A yes-or-no fact about {article(name)} is an adjective.', toks[0],
                    hint=f'Write it as its own sentence: "{article(name).capitalize()} can be {fname}."',
                    teach="yes_no_property",
                )

            if s.at_end():
                break
            comma, conj = s.eat_punct(","), s.eat_word("and")
            if not (comma or conj):
                s.fail('Properties are separated by a comma or by "and".', hint=example, teach="list_commas")
        self.defines("kind", name, s.line, ktok.col, len(ktok.text))
        if plural != pluralize(name):
            ptok = next(t for t in s.toks if t.is_word(plural))
            self.defines("plural of a kind", plural, s.line, ptok.col, len(ptok.text), of=name)
        for fname in K.fields:
            ftoks = [t for t in s.toks if t.kind == "WORD"]
            words = fname.split(" ")
            at = next((k for k in range(len(ftoks)) if [t.low for t in ftoks[k:k + len(words)]] == words), None)
            if at is not None:
                first, last = ftoks[at], ftoks[at + len(words) - 1]
                self.defines("property", fname, s.line, first.col, last.end - first.col, of=name,
                             type_=K.fields[fname])
        K.unit = self.unit
        K.adjectives = View(lambda word, adj: self.can_see(adj.unit, word))
        K.props = View(lambda word, prop: self.can_see(prop.unit, word))
        self.kinds[key] = K
        self.nouns[name] = (key, False)
        self.nouns[K.plural] = (key, True)
        self.member_names.update(K.fields)

    def plural_hint(self, word):
        """For a word that looks like the plural of a kind but is not it ("children"
        with a kind "child"): how the plural is formed, and how to state another."""
        low = word.lower()
        for K in self.kinds.values():
            if not self.kind_visible(K.name) or low == K.plural:
                continue
            if low == pluralize(K.name):
                return f'The plural of "{K.word}" was stated as "{K.plural}".'
            stem = K.name[:max(3, len(K.name) - 1)]
            if IRREGULAR.get(K.name) == low or (low.startswith(stem) and len(low) > len(K.name)):
                return (f'The plural of "{K.word}" is "{K.plural}", formed by rule. To use another, say so where '
                        f"the kind is described: {cap(article(K.word))} (plural {low}) has ...")
        return None

    def kind_words_free(self, s, tok, name, plural, kind=None):
        """Refuse a kind whose name or plural is another kind's name or plural
        ("bus" and "buse" would both be "buses")."""
        for word, label in ((name, "name"), (plural, "plural")):
            # The kinds this file may name, and, if this file shares the kind, those other files share.
            other = self.nouns.clash(word, self.unit, shared_as=name)
            if other is None:
                continue
            theirs = "plural" if other[1] else "name"
            K = self.kinds[other[0]]
            if K.word == (kind or name) and K.unit is self.unit:
                continue
            s.fail(f'This kind\'s {label}, "{word}", is already the {theirs} of the kind "{K.word}" ({where(K.line)}), '
                   "so the two could not be told apart.", tok,
                   hint="Choose another name for the kind." if label == "name" else
                   f'Choose another name for the kind, or state another plural: "{cap(article(name))} (plural ...) has ...".',
                   teach="kind_names")

    def described_again(self, s, ktok, K):
        """Refuse "A dragon has ..." for a kind described before, showing how the one
        sentence that describes it would read with the new properties."""
        name, earlier = K.name, K.line
        at = where(earlier) if earlier.library or chapter_of(earlier) is not None else f"on line {earlier.number}"
        hint = None
        if getattr(earlier, "unit", None) is self.unit and not earlier.library:
            old = [f"{article(f)} ({base(t)}{', if any' if is_opt(t) else ''})" for f, t in K.fields.items()]
            has = next((t for t in s.toks if t.is_word("has")), s.toks[2])
            new = [p for p in self.split_list(s.line.text[has.end:s.toks[-1].col])
                   if p.lower() not in (o.lower() for o in old)]
            if new:
                every = old + new
                listed = ", ".join(every[:-1]) + " and " + every[-1] if len(every) > 1 else every[0]
                hint = (f"To give {article(name)} more properties, add them to that sentence. Line {earlier.number} "
                        f"would read: {cap(article(name))} has {listed}.")
            else:
                hint = "This sentence adds nothing new: take it out."
        s.fail(f"{cap(article(name))} was already described {at}, and a kind is described only once.", ktok,
               hint=hint, teach="described_once")

    @staticmethod
    def split_list(text):
        """'an age (number), a lair (text) and a hoard (dragon, if any)' -> its items."""
        items, depth, current = [], 0, ""
        for word in re.split(r"(\s+|,|\(|\))", text):
            if word == "(":
                depth += 1
            elif word == ")":
                depth -= 1
            if depth == 0 and (word == "," or word.strip() == "and"):
                items.append(current)
                current = ""
            else:
                current += word
        items.append(current)
        return [" ".join(item.split()) for item in items if item.strip()]

    def define_choices(self, s):
        """A | An <name> is one of <choice>, <choice> ... or <choice>.   A type whose values are those words."""
        s.next()  # a
        ntok = s.next()
        self.check_new_name(s, [ntok], "the name of a set of choices")
        word = ntok.low
        if word in self.choice_names or self.nouns.clash(word, self.unit) is not None:
            s.fail(f'"{ntok.text}" already names a kind of value, so it can\'t also name this set of choices.',
                   ntok, hint="Choose another name for the set.", teach="taken")
        for _ in range(3):  # is one of
            s.next()
        usage = 'For example: "A mood is one of sleepy, grumpy or content."'
        choices = []
        while True:
            toks = []
            while s.peek().kind == "WORD" and not s.at_word("or"):
                toks.append(s.next())
            if not toks:
                s.fail("This needs a choice here: one or more words.", hint=usage, teach="choices_form")
            self.check_new_name(s, toks, "a choice")
            choice = " ".join(t.low for t in toks)
            if choice in (c for c, _, _ in choices):
                s.fail(f'"{choice}" is listed twice.', toks[0], hint="List each choice once.", teach="choices_form")
            found = self.name_clash(choice)
            if found is not None:
                what, owner = found
                self.refuse_clash(s, toks[0], choice, what, owner,
                                  hint="A choice is a name: it can't also be a kind, a thing, a variable or "
                                       "a worked-out value, nor a choice of another set.")
            choices.append((choice, " ".join(t.text for t in toks), toks[0]))
            if s.at_end():
                break
            if s.eat_word("or"):
                continue
            if not s.eat_punct(","):
                s.fail('Choices are separated by commas, with "or" before the last.', hint=usage,
                       teach="choices_form")
            s.eat_word("or")
        if len(choices) < 2:
            s.fail("A set of choices needs at least two.", s.toks[0], hint=usage, teach="choices_form")
        if s.toks[-2].kind == "WORD" and not any(t.is_word("or") for t in s.toks):
            s.fail('The last choice comes after "or".', hint=usage, teach="choices_form")
        key = word if self.unit.shares_name(word) else f"{word} of {self.unit.title}"
        while key in self.choice_sets or key in self.kinds:
            key += "'"
        cset = ChoiceSet(key, word, [c for c, _, _ in choices], self.unit, s.line, [d for _, d, _ in choices])
        self.defines("set of choices", word, s.line, ntok.col, len(ntok.text))
        for choice, display, ctok in choices:
            self.defines("choice", display, s.line, ctok.col, len(display), of=word)
        self.choice_sets[key] = cset
        self.choice_names[word] = cset
        for choice, display, _ in choices:
            self.choice_words[choice] = Named(display, key, self.unit)
        self.note(f'"{word}" → one of {join_words([d for _, d, _ in choices], "or")}')

    def define_adjective(self, s):
        s.next()
        K = self.need_kind(s, s.next())
        s.next()  # is
        atok = s.next()
        self.check_new_name(s, [atok], "an adjective")
        self.adjective_is_new(s, atok, K)
        s.expect_word("when", hint='For example: "A dragon is ancient when its age is at least 500."',
                      teach="adjective_form")
        start = s.peek().col
        self.scope = self.subject_scope(K.name)
        # Find out whether it reads only its own thing's stored properties: then a change
        # to one thing can change it only for that thing (World.noting).
        self.rule_for, self.probe = K.name, {"local": True}
        try:
            with self.fresh():
                cond = self.condition(s)
                self.end(s)
        finally:
            self.scope = self.globals
            local = self.probe["local"]
            self.rule_for, self.probe = None, None
        source = s.line.text[start:].rstrip(".").strip()
        adj = K.adjectives[atok.low] = Adj(atok.low, self.subject_fn(K.name, cond.fn), source, unit=self.unit,
                                                   line=s.line, local=local, mark=self.slot(atok.low, self.unit))
        self.declare("adjective", atok.low, s.line, (atok.col, len(atok.text)), lambda: adj.used, of=K.word)
        self.adjective_names.add(atok.low)

    # A word is never both an adjective and a name ---------------------------
    #
    # An adjective's word may not be the name of a kind, a thing, a variable, a
    # role or a loop's thing, nor the first word of one, whichever comes first:
    # "If Smaug is ancient" must read one way. Properties and verbs are apart:
    # a property is only reached through "'s", "of" or "whose", and a verb by
    # standing first in its sentence.

    def made(self, name, what, line):
        """Remember a name made with a word that an adjective may not then take."""
        self.made_at.setdefault(name.split(" ")[0], []).append((what, name, line, self.unit))

    def kind_named(self, s, name, type_, span, what):
        """Inside a block, a variable or role may have a kind's name only when it holds
        a thing of that kind: "the card" then means a card either way."""
        noun = self.nouns.get(name)  # only a kind this file may name can be meant
        if noun is None or (not noun[1] and base(type_) == noun[0]):
            return
        kind = noun[0]
        s.fail_span(f'"the {name}" would read as '
                    f'{"some " + self.kinds[kind].plural if noun[1] else article(self.kinds[kind].word)}, '
                    f"but this {what} holds {self.describe(type_)}.", span,
                    hint=f"Choose another name for the {what}.", teach="kind_variable")

    def adjective_of(self, word):
        """(Adj, Kind) for an adjective with that word, of a kind this file may name and
        that this file may say; or None."""
        for K in self.kinds.values():
            adj = K.adjectives.get(word) if self.kind_visible(K.name) else None
            if adj is not None:
                return adj, K
        return None

    def not_an_adjective(self, s, toks, what, fix=None):
        """Refuse a new name (`toks`) that is, or begins with, an adjective."""
        word = toks[0].low
        found = self.adjective_of(word)
        if found is None:
            return
        adj, K = found
        at = f" ({where(adj.line)})" if adj.line is not None else ""
        if len(toks) == 1:
            s.fail(f'"{toks[0].text}" is already an adjective of {article(K.word)}{at}, so it can\'t also be {what}.',
                   toks[0], hint="Choose another word.", teach="namespaces")
        name = " ".join(t.text for t in toks)
        s.fail_span(f'"{name}" begins with the adjective "{toks[0].text}", so a reader would take "{toks[0].text}" '
                    "as a filter, not as part of a name.", (toks[0].col, toks[-1].end),
                    hint=None if fix else "Choose a name that does not begin with an adjective.", teach="namespaces",
                    fix=fix)

    def adjective_is_free(self, s, atok):
        """Refuse an adjective whose word is a name already, or begins one."""
        found = next(((what, name, line) for what, name, line, unit in self.made_at.get(atok.low, ())
                      if self.can_see(unit, name)), None)  # only names this file may say
        if found is None and atok.low in self.nouns:
            kind, plural = self.nouns[atok.low]
            found = ("the plural of a kind" if plural else "a kind", atok.low, self.kinds[kind].line)
        if found is None:
            return
        what, name, line = found
        at = f" ({where(line)})" if line is not None else ""
        if name == atok.low:
            message = f'"{atok.text}" is already {what}{at}, so it can\'t also be an adjective.'
        else:
            message = f'"{atok.text}" begins the name of {what}, "{name}"{at}, so it can\'t also be an adjective.'
        s.fail(message, atok, hint="Choose another word for the adjective.", teach="namespaces")

    def adjective_is_new(self, s, atok, K):
        self.adjective_is_free(s, atok)
        earlier = K.adjectives.clash(atok.low, self.unit)
        if earlier is not None:
            if not self.can_see(earlier.unit, atok.low):
                self.refuse_clash(s, atok, atok.low, f"an adjective of {article(K.word)}", earlier.unit)
            s.fail(f'"{atok.text}" is already defined for {article(K.word)}{self.elsewhere(earlier.unit)}.', atok,
                   hint="An adjective is defined once for each kind: change the first definition, or choose "
                        "another word.", teach="taken")

    def define_stored_adjective(self, s):
        """A | An <kind> can be <adjective>.  A yes-or-no fact, changed with "Now"."""
        s.next()
        K = self.need_kind(s, s.next())
        s.next()  # can
        s.expect_word("be", hint=f'For example: "{article(K.word).capitalize()} can be done."', teach="adjective_form")
        atok = s.next()
        self.check_new_name(s, [atok], "an adjective")
        self.adjective_is_new(s, atok, K)
        self.end(s)
        name = atok.low
        source = f'stored for each {K.word}, set with "Now"'
        mark = self.slot(name, self.unit)  # what Thing.marks holds: another file may have its own "name"
        adj = K.adjectives[name] = Adj(name, lambda world, thing: mark in thing.marks, source, stored=True,
                                     unit=self.unit, line=s.line, mark=mark)
        self.declare("adjective", name, s.line, (atok.col, len(atok.text)), lambda: adj.used, of=K.word)
        self.adjective_names.add(name)

    def define_rule(self, s):
        s.next()
        K = self.need_kind(s, s.next())
        s.next()  # 's
        match = self.match_member(s, K.name)
        if not match:
            self.no_member(s, K.name)
        if match[0] not in K.fields:
            s.fail(f'A never/always rule has to be about a stored property, and "{match[0]}" is worked out or fixed.',
                   teach="rule_form")
        self.scope = self.subject_scope(K.name)
        try:
            with self.fresh():
                kind = K.name
                subject = Expr(kind, lambda env: env.get(kind))
                subject.span = (s.peek().col, s.peek().col)
                subject.key = ("var", kind)
                left = self.member(s, subject, match)
                s.expect_word("is", teach="rule_form")
                mode = s.next()
                if not mode.is_word("never", "always"):
                    if mode.kind == "WORD" and len(close_words(mode.text, ["never", "always"])) == 1:
                        right = close_words(mode.text, ["never", "always"])[0]
                        s.fail(f'I don\'t know the word "{mode.text}". Did you mean "{right}"?', mode,
                               teach="rule_form", category="spelling", fix=s.replace(mode, right))
                    s.fail('After "is" in a rule comes "never" or "always".', mode,
                           hint='For example: "A knight\'s purse is never less than $0."', teach="rule_form")
                # A rule about an "if any" property holds whenever the property is nothing,
                # unless the rule is about being nothing.
                maybe = is_opt(left.type) and not s.at_word("nothing") and not s.at_words("not", "nothing")
                if maybe:
                    left.type = base(left.type)
                self.rule_for = kind
                try:
                    cond = self.tail(s, left).fn
                finally:
                    self.rule_for = None
                self.end(s)
        finally:
            self.scope = self.globals
        holds = cond if mode.low == "always" else (lambda env: not cond(env))
        if maybe:
            value, test = left.fn, holds
            holds = lambda env: value(env) is None or test(env)  # noqa: E731
        rule = Rule(self.subject_fn(K.name, holds), s.line.text.strip())
        K.rules.append(rule)

        def step(env):
            """The rule holds from here on: the things there are already must keep it."""
            world = env.world
            for thing in world.things.get(kind, ()):
                if not thing.removed and not rule.fn(world, thing):
                    raise EnglishError(
                        f'{thing.name} already breaks this rule, so it can\'t be stated here.', stage="run",
                        hint=f"({thing.name}'s {match[0]} is {fmt(thing.fields[match[0]], K.fields[match[0]])}.)\n"
                             "Change it before this sentence, or state the rule before the thing is made.",
                        teach="rule_broken")
            world.rules.setdefault(kind, []).append(rule)
        return step

    def rule_refuses(self, s, span, what, hint=None):
        """Inside a rule: refuse a value the rule may not depend on (see define_rule).
        Inside an adjective's definition (self.probe): note that the adjective reads
        more than its own thing's stored properties, and go on."""
        if self.rule_for is not None and self.probe is not None:
            self.probe["local"] = False
        elif self.rule_for is not None:
            s.fail_span(f"A rule may not depend on {what}: that can change without the rule being checked.", span,
                        hint=hint, teach="rule_reads")

    def define_property(self, s):
        s.next()  # the
        toks = []
        while s.peek().kind == "WORD" and not s.at_word("of"):
            toks.append(s.next())
        if not toks or not s.at_word("of") or not s.peek(1).is_word("a", "an"):
            s.fail(
                "A sentence starts with a verb, or with a definition.", s.toks[0],
                hint='To define a worked-out property: "The interest of a dragon is 5% of its hoard."',
                teach="verb_first",
            )
        s.next()
        s.next()
        K = self.need_kind(s, s.next())
        self.check_new_name(s, toks, "a property name")
        name = " ".join(t.low for t in toks)
        earlier = K.props.clash(name, self.unit)
        if earlier is not None and name not in K.fields and not self.can_see(earlier.unit, name):
            self.refuse_clash(s, toks[0], name, f"a property of {article(K.word)}", earlier.unit)
        if name in K.fields or earlier is not None:
            unit = earlier.unit if earlier is not None else K.unit
            s.fail(f'{article(K.word).capitalize()} already has "{name}"{self.elsewhere(unit)}.', toks[0],
                   hint="Choose another name for the worked-out property.", teach="taken")
        if name in self.workouts:
            s.fail(f'"{name}" is already something that is worked out{self.elsewhere(self.workouts[name].unit)}, '
                   'so a property can\'t share its name.', toks[0], teach="taken")
        s.expect_word("is", teach="property_form")
        start = s.peek().col
        self.scope = self.subject_scope(K.name)
        try:
            with self.fresh():
                value = self.expr(s)
                self.end(s)
        finally:
            self.scope = self.globals
        if value.type == "nothing":
            s.fail_span("A property that is always nothing has no use.", value.span, teach="property_form")
        source = s.line.text[start:].rstrip(".").strip()
        K.props[name] = Prop(name, value.type, self.subject_fn(K.name, value.fn), source, unit=self.unit)
        self.defines("worked-out property", name, s.line, toks[0].col, toks[-1].end - toks[0].col, of=K.word,
                     type_=value.type)
        self.member_names.add(name)

    def param(self, s, prep, stops=PREPOSITIONS):
        teach = "verb_form" if stops is PREPOSITIONS else "workout_form"
        if not s.eat_word("a", "an"):
            tok = s.peek()
            if tok.kind == "WORD" and tok.low in self.nouns and not self.nouns[tok.low][1]:  # "To feed dragon:"
                s.fail(f'A role takes an article: "{article(tok.text)}".', tok, teach="article",
                       fix=swap(s.line, tok.col, tok.col, article(tok.text)[:-len(tok.text)]))
            after = f'After "{prep}"' if prep else "Here"
            s.fail(f'{after} comes what the verb works on, with "a" or "an", such as "a dragon".', teach=teach)
        toks = []
        while s.peek().kind == "WORD" and s.peek().low not in stops:
            toks.append(s.next())
        if not toks:
            s.fail('This needs a name here, after "a" or "an".', teach=teach)
        name = " ".join(t.low for t in toks)
        if s.eat_punct("("):
            self.check_new_name(s, toks, "a name")
            type_ = self.bracket_type(s)
        elif self.kind_word(name) is not None:
            type_ = self.kind_word(name)
        else:
            self.hidden_word(s, toks[0])
            if len(toks) == 1:
                self.misspelt(s, toks[0], self.visible_kinds(), "unknown_kind")
            s.fail(
                f"What is {article(name)}?", toks[0],
                hint=f'Describe that kind first, or give this a type: "{article(name)} (money)".\n'
                     + self.kinds_hint(name), teach="unknown_kind",
            )
        by_kind = not s.toks[s.i - 1].is_punct(")")  # "a dragon", not "a victim (dragon)"
        return Param(name, type_, prep, (toks[0].col, toks[-1].end - toks[0].col), by_kind=by_kind)

    def role_scope(self, s, params, at):
        scope = Scope(self.globals)
        for p in params:
            if p.name in scope.names:
                s.fail(
                    f'There are two things called "{p.name}" here, so "the {p.name}" would be ambiguous.', at,
                    hint=f'Give them their own names: "a first one ({p.type})" and "a second one ({p.type})".',
                    teach="ambiguous_name",
                )
            if self.globals.find(p.name) or p.name in self.workouts:
                s.fail(f'"{p.name}" already means something at the top level.', at,
                       hint=f'Give the role another name, with its type in brackets: "a new one ({p.type})".',
                       teach="taken")
            span = (p.at[0], p.at[0] + p.at[1])
            words = [t for t in s.toks if span[0] <= t.col < span[1] and t.kind == "WORD"]
            if words:
                self.not_an_adjective(s, words, "the name of a role")
            self.kind_named(s, p.name, p.type, span, "role")
            self.made(p.name, "a role", s.line)
            binding = scope.names[p.name] = Binding(p.name, p.type, focus=p.type in self.kinds)
            self.declare("role", p.name, s.line, p.at, lambda b=binding: b.reads > 0, type_=p.type,
                         by_kind=p.by_kind, span=block_span(s.line.children) or (s.line.number, s.line.number))
        return scope

    def name_is_new(self, s, name, tok, local=False, hint=None, shared_as=None):
        """Refuse a name for a thing, a variable, a worked-out value or a kind's plural
        that already means something. A variable of a block need only be new where it
        is. A top-level name must be new among the names this file may say, and, if
        this file shares it, among the names every file shares (name_clash)."""
        if local:
            taken = self.scope.find(name) or name in self.names or name in self.workouts
            if taken:
                s.fail(f'"{name}" already means something here.', tok, hint=hint, teach="taken")
            return
        found = self.name_clash(name, shared_as or name)
        if found is None:
            found = self.scope.find(name)  # a role or a variable of the block around
            if found is None:
                return
            s.fail(f'"{name}" already means something here.', tok, hint=hint, teach="taken")
        what, owner = found
        self.refuse_clash(s, tok, name, what, owner, hint)

    def name_clash(self, name, shared_as=None):
        """(what it is, the file that made it) for a meaning of `name`, among kinds,
        things, variables and worked-out values, that a new top-level name made in
        the file being compiled would collide with: one this file may say, or, if
        this file shares the new name, one that another file shares. Or None."""
        unit = self.unit
        b = self.globals.find(name)
        if b is not None and b.unit is not None:
            return "a variable", b.unit
        if unit.shares_name(shared_as or name):
            for b in self.globals.names.values():
                if b.name == name and b.unit is not None and b.unit is not unit and b.unit.shares_name(name):
                    return "a variable", b.unit
        for view, what in ((self.names, "a thing"), (self.workouts, "a worked-out value"), (self.nouns, "a kind"),
                           (self.choice_words, "a choice")):
            found = view.clash(name, unit, shared_as)
            if found is not None:
                if view is self.nouns:
                    return ("the plural of a kind" if found[1] else "a kind"), self.kinds[found[0]].unit
                return what, found.unit
        return None

    def refuse_clash(self, s, tok, name, what, owner, hint=None):
        """Refuse a new name that collides with `what`, made in `owner`."""
        if owner is None or owner is self.unit or self.can_see(owner, name):
            if owner is not None and owner is not self.unit:
                hint = hint or ("In one file, each name has one meaning: the names it makes, and those shared by "
                                "the chapters it uses.")
            s.fail(f'"{name}" already means something{self.elsewhere(owner)}.', tok, hint=hint, teach="taken")
        s.fail(f'"{name}" is also shared by {owner.title}, as {what}, and a name that files share means one thing '
               "in the whole program.", tok,
               hint=f'Choose another name, or keep this one to this file by leaving it out of "This chapter shares ...".',
               teach="taken")

    def define_procedure(self, s, outside=False):
        """To <verb> ...:  with a block, or, in a library, "... is done by the library."."""
        s.next()  # to
        if s.at_words("work", "out", "the"):
            return self.define_workout(s, outside)
        vtok = s.next()
        self.check_new_name(s, [vtok], "a verb")
        verb = vtok.low
        earlier = self.procs.clash(verb, self.unit)
        if earlier is not None:
            if not self.can_see(earlier.unit, verb):
                self.refuse_clash(s, vtok, verb, "a verb", earlier.unit)
            if earlier.unit is not self.unit or outside:
                s.fail(f'I already know how to "{verb}" ({where(earlier.line)}).', vtok,
                       hint="A verb is taught once in a file: change the first definition, or choose another verb.",
                       teach="taken")
        params = []
        if s.at_word("a", "an"):
            params.append(self.param(s, None))
        elif s.peek().kind == "WORD" and s.peek().low in self.nouns and not self.nouns[s.peek().low][1]:
            self.param(s, None)  # "To feed dragon:" is refused there, with the article
        while not s.at_end():
            ptok = s.next()
            if ptok.kind != "WORD" or ptok.low not in PREPOSITIONS:
                self.misspelt(s, ptok, sorted(PREPOSITIONS), "verb_form")
                s.fail(
                    "This needs a linking word here, such as \"to\" or \"against\", to join the next role to the verb.",
                    ptok, hint="Linking words: " + ", ".join(sorted(PREPOSITIONS)) + ".", teach="verb_form",
                )
            if any(p.prep == ptok.low for p in params):
                s.fail(f'"{ptok.text}" is used twice, so I couldn\'t tell the two apart.', ptok,
                       hint="Give each role its own linking word.", teach="verb_form")
            params.append(self.param(s, ptok.low))
        scope = self.role_scope(s, params, vtok)
        proc = Proc(verb, params, s.line, unit=self.unit)
        if earlier is not None:
            # Another shape of the same verb: told apart by its linking words alone, never by its values.
            same = next((shape for shape in earlier.shapes if shape.prepositions() == proc.prepositions()), None)
            if same is not None and [p.type for p in same.params] == [p.type for p in proc.params]:
                s.fail(f'I already know how to "{verb}" ({where(same.line)}).', vtok,
                       hint="A verb is taught once: change the first definition, or choose another verb.",
                       teach="taken")
            if same is not None:
                s.fail(f'"{verb}" was already taught with the same linking words ({where(same.line)}: '
                       f'"{same.usage()}"), so a sentence using it could only be told from this one by its values.',
                       vtok, hint="Give this shape another linking word, or choose another verb: which verb a "
                                  "sentence uses must never depend on what its values are.", teach="verb_shapes")
            earlier.shapes.append(proc)
            proc.shapes = earlier.shapes
        self.declare("verb", verb, s.line, (vtok.col, len(vtok.text)), lambda: proc.used,
                     roles=[(p.prep, p.name, p.type) for p in params])
        if earlier is None:
            self.procs[verb] = proc  # registered first, so it can call itself
        if outside:
            step = self.outside_verb(s, proc)
            if self.reactive:  # the library's Python code may change things
                step = self.watched(step, None)
            proc.body = [step]
            return
        with self.fresh(verb=proc):
            proc.body = self.block(s.line.children, scope)

    @staticmethod
    def one_question(line):
        """Is this "To work out the ... (<type>) ..., ask the model <text>." or "..., judge <text>.":
        a worked-out value that is one question to a model (section 9.3)? A heading has no comma
        outside brackets, so the comma, with "ask the model" or "judge" after it, tells it apart."""
        toks = line.tokens
        if not (len(toks) > 4 and toks[0].is_word("to") and toks[1].is_word("work") and toks[2].is_word("out")
                and toks[3].is_word("the")):
            return False
        depth = 0
        for k, tok in enumerate(toks):
            if tok.is_punct("("):
                depth += 1
            elif tok.is_punct(")"):
                depth -= 1
            elif tok.is_punct(",") and depth == 0:
                rest = toks[k + 1:k + 4]
                return (len(rest) == 3 and rest[0].is_word("ask") and rest[1].is_word("the")
                        and rest[2].is_word("model")) or (bool(rest) and rest[0].is_word("judge", "grade"))
        return False

    def question_body(self, s, w, scope):
        """The rest of "To work out ..., ask the model <text>." or "..., judge <text>.": the one
        step of the value, which gives the answer. The roles are what the question is about:
        one role is handed over as "about" hands it over; several as "<role>: <value>" lines."""
        s.expect_punct(",")
        scale = s.at_word("grade")
        judging = bool(s.eat_word("judge", "grade"))
        if not judging:
            for _ in range(3):  # ask the model
                s.next()
        usage = ('For example: "To work out the gist (text) of a letter (text), ask the model "Say what this '
                 'letter wants, in one line."."')
        saved = self.scope
        self.scope = scope
        try:
            with self.fresh():
                question = self.question_text(s, usage)
        finally:
            self.scope = saved
        self.end(s)
        params, type_, cset, shape = w.params, w.type, None, None
        for p in params:  # every role is handed over as what the question is about, so each is used
            scope.names[p.name].reads += 1
        if judging:
            if not params:
                s.fail("A judgement is always about something: give the value a role for it to be about.", s.toks[0],
                       hint='For example: "To work out the team (team) for a ticket, judge "Which team?"."',
                       teach="judge_form")
            if type_ in self.choice_sets:
                cset = self.choice_sets[type_]
            elif scale:
                s.fail(f'A grade is one of a set of choices, but "the {w.name}" is {self.describe(type_)}.',
                       s.toks[0], teach="judge_form")
            elif type_ != "percent":
                s.fail(f'A judgement is a chance (percent) or a verdict (a set of choices), but "the {w.name}" is '
                       f"{self.describe(type_)}.", s.toks[0], teach="judge_form")
        else:
            shape = self.reply_shape(type_)
            if shape is None:
                s.fail(f"I can't ask a model for {self.describe(base(type_))}.", s.toks[0],
                       hint="A reply can be text, a number, money, a percentage, yes or no, one of a set of choices, "
                            "or a list of text, numbers, money or percentages.", teach="model_form")
        if len(params) == 1:
            p = params[0]
            if p.type in self.kinds:
                K = self.kinds[p.type]
                word, fields = K.word, list(K.fields.items())

                def state(env, name=p.name):
                    return thing_state(env.get(name), word, fields)
            else:
                def state(env, name=p.name, type_=p.type):
                    return said(env.get(name), type_)
        elif params:
            def state(env):
                return "\n".join(f"{p.name}: {said(env.get(p.name), p.type)}" for p in params)
        else:
            state = None
        qf = question.fn
        self.note(f'"the {w.name}" is worked out by {"a judge" if judging else "a model"}')

        def step(env):
            world = env.world
            if (world.judge is None and world.judges is None) if judging else world.model is None:
                raise no_model()
            about = state(env) if state is not None else None
            if judging:
                raise _Answer(ask_judge(world, qf(env), about, cset, scale)[0])
            raise _Answer(ask_model(world, qf(env), about, shape))
        return step

    def define_workout(self, s, outside=False):
        """To work out the <name> (<type>) [<preposition> a <role>]... :"""
        for _ in range(3):  # work out the
            s.next()
        toks = []
        while s.peek().kind == "WORD" and s.peek().low not in ROLE_WORDS:
            toks.append(s.next())
        if not toks:
            s.fail('After "To work out the" comes the name of what is worked out.', teach="workout_form")
        self.check_new_name(s, toks, "a name")
        name = " ".join(t.low for t in toks)
        earlier = self.workouts.clash(name, self.unit)
        if earlier is not None:
            if not self.can_see(earlier.unit, name):
                self.refuse_clash(s, toks[0], name, "a worked-out value", earlier.unit)
            s.fail(f'I already know how to work out "the {name}" ({where(earlier.line)}).', toks[0],
                   hint="A value is taught once: change the first definition, or choose another name.", teach="taken")
        if name in self.member_names:
            s.fail(f'"{name}" is already a property, so something worked out can\'t share its name.', toks[0],
                   teach="taken")
        self.name_is_new(s, name, toks[0])
        if not s.eat_punct("("):
            s.fail(
                f'What sort of value is "the {name}"?', toks[0],
                hint=f'Say so in brackets: "To work out the {name} (money) ...".', teach="workout_form",
            )
        type_ = self.bracket_type(s)
        params = []
        asks = self.one_question(s.line)
        while not s.at_end():
            if asks and s.peek().is_punct(","):
                break
            ptok = s.next()
            if ptok.kind != "WORD" or ptok.low not in ROLE_WORDS:
                self.misspelt(s, ptok, sorted(ROLE_WORDS), "workout_form")
                s.fail(
                    'This needs a linking word here, such as "of" or "for", to say what it is worked out from.',
                    ptok, teach="workout_form",
                )
            if any(p.prep == ptok.low for p in params):
                s.fail(f'"{ptok.text}" is used twice, so I couldn\'t tell the two apart.', ptok,
                       hint="Give each role its own linking word.", teach="workout_form")
            params.append(self.param(s, ptok.low, ROLE_WORDS))
        scope = self.role_scope(s, params, toks[0])
        w = Workout(name, type_, params, s.line, unit=self.unit)
        self.declare("value", name, s.line, (toks[0].col, toks[-1].end - toks[0].col), lambda: w.used,
                     type_=type_, roles=[(p.prep, p.name, p.type) for p in params])
        self.workouts[name] = w  # registered first, so it can use itself
        if outside:
            w.body = [self.outside_value(s, w)]
            return
        if asks:
            w.asks = True
            w.body = [self.question_body(s, w, scope)]
            return
        with self.fresh(workout=w):
            w.body = self.block(s.line.children, scope)
        if not self.answers(w.body):
            raise EnglishError(
                "Not every path through this block reaches an answer.",
                s.line, s.toks[0].col, len(s.line.text.strip()),
                hint='Finish the block with "The answer is ...".', teach="answer_paths",
            )

    # reactions ----------------------------------------------------------

    def keep_ahead(self, s):
        """Is this "Keep each ..." or "Keep <thing>'s ... as ...", rather than a verb "keep"?
        When the program has its own verb "keep" and the sentence could be either, refuse it."""
        if s.peek(1).is_word("each"):
            form = True
        else:
            match = self.match_words(s, self.names, 1)
            form = bool(match) and s.peek(1 + match[1]).kind == "POS" and any(t.is_word("as") for t in s.toks)
        if form and "keep" in self.procs:
            s.fail('This could be the verb "keep" of this program, or a sentence that keeps a value in step with '
                   "\"Keep ... as ...\".", s.toks[0], hint='Rename the verb "keep", so that each sentence reads '
                   "one way.", teach="ambiguous_name")
        return form

    def define_keep(self, s):
        """Keep each <kind>'s <property> as <expression>.
        Keep <thing>'s <property> as <expression>.
        Keep each <kind> <stored adjective> when <condition>.

        At the end of every turn that changed something, before the settled blocks,
        each kept value is worked out and set if it differs (World.keep)."""
        start = s.next()  # keep
        usage = "For example: \"Keep each card's line as its wording.\" or \"Keep each card open when ...\"."
        if not self.reactive:  # program() looks ahead for every "Keep"
            raise EnglishError("This sentence was not expected by the compiler.", s.line, start.col, len(start.text))
        line, thing_slot, each = s.line, None, bool(s.eat_word("each"))
        if each:
            K = self.need_kind(s, s.next())
        else:
            key, count = self.match_words(s, self.names)
            for _ in range(count):
                s.next()
            entry = self.names[key]
            K, thing_slot, shown = self.kinds[entry[1]], entry.slot, entry[0]
        if each and s.peek().kind != "POS":
            return self.keep_adjective(s, K, line)
        if s.peek().kind != "POS":
            s.fail("After the thing comes the property it keeps, as in \"Keep Smaug's age as ...\".", hint=usage,
                   teach="keep_form")
        s.next()
        match = self.match_member(s, K.name)
        if not match:
            self.no_member(s, K.name)
        fname = match[0]
        ftok = s.peek()
        for _ in range(match[1]):
            s.next()
        if fname not in K.fields:
            s.fail(f'Only a stored property can be kept, and "{fname}" is worked out or fixed.', ftok,
                   hint="A worked-out property is already worked out each time it is read.", teach="keep_form")
        earlier = K.kept.get(fname) or (self.kept_things.get((thing_slot, fname)) if thing_slot else None)
        if earlier is not None:
            s.fail(f'"{fname}" is already kept ({where(earlier)}).', ftok, hint="A value is kept by one sentence.",
                   teach="kept")
        s.expect_word("as", hint=usage, teach="keep_form")
        scope = self.subject_scope(K.name) if each else self.globals
        saved = self.scope
        self.scope = scope
        try:
            with self.fresh():
                value = self.whole_value(s, K.fields[fname])
                self.end(s)
        finally:
            self.scope = saved
        want = K.fields[fname]
        if not self.fits(value.type, want):
            if base(value.type) == base(want):
                self.need(s, value)
            s.fail_span(f"{cap(article(K.word))}'s {fname} is {self.describe(want)}, but {value.text} is "
                        f"{self.describe(value.type)}.", value.span, teach="fit")
        if each:
            K.kept[fname] = line
        else:
            self.kept_things[(thing_slot, fname)] = line
        vf, kind, rules_of = value.fn, K.name, K.name
        ftype = want
        changes = []

        def set_one(world, thing, env):
            new = vf(env)
            old = thing.fields[fname]
            if (old is new) if isinstance(new, Thing) or isinstance(old, Thing) else (old == new):
                return
            if isinstance(new, Thing):
                alive(new)
            thing.fields[fname] = new
            for rule in world.rules.get(rules_of, ()):
                if not rule.fn(world, thing):
                    thing.fields[fname] = old
                    raise EnglishError(f'That would break a rule: "{rule.text}"', stage="run", recoverable=True,
                                       hint=f"({thing.name}'s {fname} is kept as {fmt(new, ftype)}.)",
                                       teach="rule_broken")
            if world.indexes:
                world.changed_field(thing, fname, old)
            changes.append(f"{thing.name}'s {fname}")

        def apply(env):
            world = env.world
            if each:
                for thing in list(world.things.get(kind, ())):
                    if not thing.removed:
                        inner = Env(env)
                        inner.vars[kind] = thing
                        set_one(world, thing, inner)
            else:
                thing = world.named.get(thing_slot)
                if thing is not None and not thing.removed:
                    set_one(world, thing, env)
        return self.keeper_step(line, apply, changes)

    def keep_adjective(self, s, K, line):
        """Keep each <kind> <stored adjective> when <condition>."""
        atok = s.next()
        adj = K.adjectives.get(atok.low) if atok.kind == "WORD" else None
        if adj is None:
            self.unknown_adjective(s, atok, K.name)
        if not adj.stored:
            s.fail(f'"{atok.text}" is worked out from "{adj.source}" already, so it can\'t be kept as well.', atok,
                   hint=f'Keep an adjective made with "can be": "{cap(article(K.word))} can be {atok.text}."',
                   teach="keep_form")
        earlier = K.kept.get(("adjective", adj.name))
        if earlier is not None:
            s.fail(f'"{atok.text}" is already kept ({where(earlier)}).', atok, teach="kept")
        s.expect_word("when", hint=f'For example: "Keep each {K.word} {atok.text} when ...".', teach="keep_form")
        saved = self.scope
        self.scope = self.subject_scope(K.name)
        try:
            with self.fresh():
                cond = self.condition(s)
                self.end(s)
        finally:
            self.scope = saved
        K.kept[("adjective", adj.name)] = line
        adj.used = True
        cf, kind, mark, name = cond.fn, K.name, adj.mark, adj.name
        changes = []

        def apply(env):
            for thing in list(env.world.things.get(kind, ())):
                if thing.removed:
                    continue
                inner = Env(env)
                inner.vars[kind] = thing
                fits = bool(cf(inner))
                if fits != (mark in thing.marks):
                    (thing.marks.add if fits else thing.marks.discard)(mark)
                    changes.append(f"{thing.name} being {name}")
        return self.keeper_step(line, apply, changes)

    def keeper_step(self, line, apply, changes):
        """The step of a "Keep" sentence: from here on, `apply` keeps the value in step
        at the end of each turn; its changes set off reactions (watched)."""
        watched = self.watched(apply, line)

        def keeper(world):
            changes.clear()
            watched(Env(world.globals))
            return list(changes)

        def step(env):
            env.world.keepers.append((line, keeper))
            env.world.changed = True  # this sentence's turn ends by keeping it in step
        return step

    def define_settled(self, s, start):
        """Whenever everything has settled:

        Its block is carried out at the end of a turn that changed something: a
        top-level sentence (of the program or of a chapter being read), with all it
        set off, or an event from a library. See World.settle."""
        for _ in range(3):
            s.next()
        self.end(s)
        if not self.reactive:  # program() looks ahead for every "Whenever"
            raise EnglishError("This reaction was not expected by the compiler.", s.line, start.col, len(start.text))
        text = s.line.text[start.col:].rstrip(" :")
        self.defines("reaction", text, s.line, start.col, len(text))
        with self.fresh(verb=Proc("whenever", [], s.line)):
            body = self.block(s.line.children, Scope(self.globals))  # no thing is in view
        line = s.line

        def run(world):
            frame = Env(world.globals)
            try:
                for inner in body:
                    inner(frame)
            except _StopVerb:
                pass

        def step(env):
            env.world.settlers.append((line, run))
        return step

    def define_reaction(self, s):
        """Whenever a | an <kind> becomes [not] <adjective>:
        Whenever <thing> becomes [not] <adjective>:

        The block is carried out for a thing straight after a sentence that
        leaves it fitting the adjective (or, with "not", no longer fitting it).
        """
        start = s.next()  # whenever
        if s.at_words("everything", "has", "settled") and s.peek(3).kind == "END":
            return self.define_settled(s, start)
        usage = 'For example: "Whenever a knight becomes broke:" or "Whenever Gawain becomes broke:".'
        thing_key = None
        if s.eat_word("a", "an"):
            K = self.need_kind(s, s.next())
        else:
            match = self.match_words(s, self.names)
            if not match:
                tok = s.peek()
                noun = self.nouns.get(tok.low) if tok.kind == "WORD" else None
                if noun and not noun[1]:
                    s.fail(f'Write "a {tok.text}" for any {noun[0]}, or the name of one thing.', tok, hint=usage,
                           teach="article", fix=swap(s.line, tok.col, tok.col, article(tok.text)[:-len(tok.text)]))
                self.hidden_here(s)
                if tok.kind == "WORD" and tok.low not in KEYWORDS and not self.defined_word(tok.low):
                    self.misspelt(s, tok, [disp for disp, _ in self.names.values()], "unknown")
                    s.fail(f'I don\'t know what "{tok.text}" refers to.', tok, teach="unknown",
                           hint="After \"Whenever\" comes a kind (\"a knight\") or a thing with a name, "
                                "made before this sentence.\n" + usage)
                s.fail('After "Whenever" comes "a" or "an" and a kind, or the name of a thing.', tok, hint=usage,
                       teach="reaction_form")
            thing_key, count = match
            for _ in range(count):
                s.next()
            entry = self.names[thing_key]
            K, thing_key = self.kinds[entry[1]], entry.slot
        if not s.at_word("becomes"):
            if s.at_word("is", "become", "gets", "turns"):
                s.fail(f'A reaction is written with "becomes", not "{s.peek().text}".', hint=usage,
                       teach="reaction_form", fix=s.replace(s.peek(), "becomes"))
            self.misspelt(s, s.peek(), ["becomes"], "reaction_form")
            s.fail('This needs "becomes" here: "Whenever ... becomes ...:".', hint=usage, teach="reaction_form")
        s.next()
        negated = bool(s.eat_word("not"))
        atok = s.next()
        adj = K.adjectives.get(atok.low) if atok.kind == "WORD" else None
        if adj is None:
            self.hidden_adjective(s, atok, K)
            if atok.kind != "WORD":
                s.fail('After "becomes" comes an adjective, such as "broke".', atok, hint=usage,
                       teach="reaction_form")
            self.misspelt(s, atok, list(K.adjectives), "unknown_adjective")
            s.fail(
                f'I don\'t know what "{atok.text}" means for {article(K.word)}.', atok,
                hint=f'Define it first: "{article(K.word).capitalize()} is {atok.text} when ..." '
                     f'or "{article(K.word).capitalize()} can be {atok.text}."',
            )
        self.end(s)
        adj.used = True
        self.note(f'"{atok.text}" → {adj.source}')
        if not self.reactive:  # program() looks ahead for every "Whenever"
            raise EnglishError("This reaction was not expected by the compiler.", s.line, start.col, len(start.text))
        kind = K.name
        with self.fresh(verb=Proc("whenever", [], s.line)):
            body = self.block(s.line.children, self.subject_scope(kind))  # the thing is kept under its kind's key
        text = s.line.text.strip().rstrip(":").strip()
        test, adjective, becomes, local = adj.fn, adj.mark, not negated, adj.stored or adj.local
        line, word = s.line, atok.low
        self.defines("reaction", text, line, start.col, len(text), of=K.word)

        def run(world, thing):
            frame = Env(world.globals)
            frame.vars[kind] = thing
            try:
                for inner in body:
                    inner(frame)
            except _StopVerb:
                pass

        def step(env):
            env.world.reactions.append(Reaction(kind, adjective, test, becomes, thing_key, run, text, local,
                                                line, word))
        return step

    # libraries ----------------------------------------------------------

    @staticmethod
    def library_names():
        """The libraries a program may use: the modules of englishscript.libraries
        whose names don't start with an underscore, including any registered in
        sys.modules under that package (as the tests do)."""
        prefix = libraries.__name__ + "."
        names = {found.name for found in pkgutil.iter_modules(libraries.__path__)}
        names.update(key[len(prefix):] for key in sys.modules if key.startswith(prefix))
        return sorted(name for name in names if "." not in name and not name.startswith("_"))

    def use_name(self, s, usage):
        """Refuse a name of a library or chapter that is not made of plain words, such
        as "a.b" or "../secret": what a name may be made of, and the two forms."""
        rest = s.toks[s.i:-1]
        kind = next((t.low for t in rest if t.is_word("library", "chapter")), None)
        end = next((t for t in rest if t.is_word("library", "chapter")), None)
        bad = next((t for t in rest if t.kind != "WORD" and (end is None or t.col < end.col)), None)
        if bad is None or not rest:
            return
        start = rest[0].col
        stop = end.col if end is not None else s.toks[-1].col
        name = s.line.text[start:stop].strip()
        if kind == "library":
            s.fail_span(f'A library\'s name is one word of letters, so "{name}" can\'t be one.', (start, start + len(name)),
                        hint="Libraries: " + ", ".join(self.library_names()) + ".", teach="library")
        where_ = ("A chapter is found beside this file, or in a book (a folder) beside it, so a path to it can't "
                  "be given.\n") if any(t.text in ("/", ".") for t in rest[:3]) and name.startswith((".", "/")) else ""
        s.fail_span(f'The name of a {kind or "library or chapter"} is made of plain words, of letters only, '
                    f'so "{name}" can\'t be one.', (start, start + len(name)),
                    hint=where_ + 'A chapter called "roman numerals" is the file roman_numerals.english.\n' + usage,
                    teach="chapter" if kind == "chapter" else "use_form")

    def use_library(self, s):
        """Use the <name> library.  Compiles the library's SOURCE here, as if written here."""
        use = s.next()
        if self.library is not None:
            s.fail("A library can't use another library.", use,
                   hint='The program itself must say "Use the ... library." for each library it needs.',
                   teach="library_fault")
        usage = ('The two forms: "Use the paint library." for a library, and "Use the calendar chapter." or\n'
                 '"Use the calendar chapter of the almanac book." for a chapter.')
        if s.at_word("a", "an") or (s.peek().kind == "WORD" and not s.at_word("the")):
            tok = s.peek()
            if tok.is_word("a", "an"):
                s.fail('"Use" names one library or chapter with "the": "Use the ...".', tok, hint=usage,
                       teach="use_form", fix=s.replace(tok, "the"))
            s.fail('After "Use" comes "the": "Use the ...".', tok, hint=usage, teach="use_form",
                   fix=swap(s.line, tok.col, tok.col, "the "))
        s.expect_word("the", hint=usage, teach="use_form")
        self.use_name(s, usage)
        words = []
        while s.peek().kind == "WORD" and not s.at_word("library", "chapter"):
            words.append(s.next())
        if s.at_word("chapter") and words:
            return self.use_chapter(s, words)
        if not words:
            s.fail('After "Use the" comes the name of a library or a chapter.', hint=usage, teach="use_form")
        tok = words[0]
        if len(words) > 1:
            s.fail_span(f'A library\'s name is one word, so "{" ".join(t.text for t in words)}" can\'t be one.',
                        (words[0].col, words[-1].end), hint=usage + "\nLibraries: "
                        + ", ".join(self.library_names()) + ".", teach="library")
        if not s.at_word("library"):
            known = tok.low in self.library_names()
            s.fail(f'After the name comes "library" or "chapter": "Use the {tok.text} library." or '
                   f'"Use the {tok.text} chapter."', hint=usage, teach="use_form",
                   fix=swap(s.line, tok.end, tok.end, " library") if known and s.at_end() else None)
        s.next()
        self.end(s)
        name = tok.low
        here = self.unit
        if ("library", name) in here.used:
            s.fail(f"The {name} library is already in use ({where(here.used[('library', name)])}).", tok,
                   hint="A file says it uses a library once; this sentence can be taken out.", teach="library")
        if name in self.libraries:  # loaded already, by another file: this file may now say its words
            here.used[("library", name)] = s.line
            self.use_clashes(s, self.library_units[name], tok)
            here.uses.add(self.library_units[name])
            self.note(f'"{name}" → the Python library, loaded already')
            return None
        available = self.library_names()
        if name not in available:
            self.misspelt(s, tok, available, "library")
            s.fail(
                f'There is no library called "{tok.text}".', tok,
                hint=("Libraries: " + ", ".join(available) + ".") if available else "There are no libraries yet.",
                teach="library",
            )
        try:
            module = importlib.import_module(f"{libraries.__name__}.{name}")
        except Exception as error:  # noqa: BLE001 - any failure to import is the library's fault
            s.fail(f"The {name} library could not be loaded: {error}", tok,
                   hint="This is a fault in the library, not in your program.", teach="library_fault")
        source = getattr(module, "SOURCE", None)
        if not isinstance(source, str):
            s.fail(f"The {name} library has no SOURCE text, so I can't tell what it provides.", tok,
                   hint="This is a fault in the library, not in your program.", teach="library_fault")
        self.libraries[name] = (module, s.line)
        self.note(f'"{name}" → the Python library {module.__name__}')
        use_line = s.line
        self.library = (name, module)
        unit = self.library_units[name] = Unit("library", name)
        here.used[("library", name)] = s.line
        try:
            self.unit = unit
            lines = read_source(source, library=name, unit=unit)
            steps = self.block(lines, self.globals)
        except EnglishError as error:
            raise self.library_fault(use_line, tok, name, error) from None
        finally:
            self.library = None
            self.line = use_line
            self.unit = here
        self.use_clashes(s, unit, tok)
        here.uses.add(unit)

        def step(env):
            for inner in steps:
                inner(env)
        return step

    # chapters and books -------------------------------------------------

    @staticmethod
    def chapter_file(folder, name_words, book_words):
        """Where 'Use the <name> chapter [of the <book> book].' looks: words joined by
        underscores, in lower case, beside the file that says it."""
        if book_words:
            folder = folder / "_".join(w.lower() for w in book_words)
        return folder / ("_".join(w.lower() for w in name_words) + ".english")

    def book_place(self, folder, book_words):
        """Where 'Use the ... chapter of the <book> book.' looks for the book's folder: beside
        the file that says it, or, if there is none there, beside the program that was run.
        Returns that folder's parent; (near, far) when there is one in both places."""
        main = self.main.folder
        same = folder is not None and main is not None and (
            os.path.normcase(os.path.abspath(folder)) == os.path.normcase(os.path.abspath(main)))
        if not book_words or main is None or folder is None or same:
            return folder
        name = "_".join(w.lower() for w in book_words)
        near, far = folder / name, main / name
        if near.is_dir() and far.is_dir():
            return (near, far)
        return main if far.is_dir() and not near.is_dir() else folder

    @staticmethod
    def chapter_words(toks):
        """(name words, book words) from the words after 'Use the', or None if they are
        not a use of a chapter. For looking ahead; use_chapter checks them properly."""
        words = [t.low for t in toks if t.kind != "END"]
        if "chapter" not in words:
            return None
        at = words.index("chapter")
        name, rest = words[:at], words[at + 1:]
        book = []
        if rest[:2] == ["of", "the"] and rest[-1:] == ["book"]:
            book = rest[2:-1]
        if not name or not all(w.isalpha() for w in name + book):
            return None
        return name, book

    def use_chapter(self, s, words):
        """Use the <name> chapter [of the <book> book].  Reads that file here, once."""
        usage = ('The two forms: "Use the calendar chapter." for the file calendar.english beside this one, and\n'
                 '"Use the calendar chapter of the almanac book." for the file almanac/calendar.english.')
        s.next()  # chapter
        book = []
        if s.eat_word("of"):
            s.expect_word("the", hint=usage, teach="chapter")
            while s.peek().kind == "WORD":  # the last word is "book", so a book may be called "book"
                book.append(s.next())
            if not book or not book[-1].is_word("book"):
                s.fail('After the name of the book comes "book": "... of the almanac book."', hint=usage,
                       teach="chapter", fix=swap(s.line, s.prev_end(0), s.prev_end(0), " book")
                       if book and s.at_end() else None)
            book.pop()
            if not book:
                s.fail('After "of the" comes the name of a book.', hint=usage, teach="chapter")
        self.end(s)
        for tok in words + book:
            if not tok.text.isalpha():
                plain = tok.text.replace("_", " ")
                s.fail(f'The name of a chapter or a book is made of plain words, of letters only, so "{tok.text}" '
                       "can't be part of one.", tok, hint=usage, teach="chapter",
                       fix=s.replace(tok, plain) if plain.replace(" ", "").isalpha() else None)
        if self.library is not None:
            s.fail("A library can't use a chapter.", s.toks[0], teach="library_fault")
        here = self.unit
        name = " ".join(t.low for t in words)
        folder = self.book_place(here.folder, [t.low for t in book])
        if isinstance(folder, tuple):  # a book of that name both beside this file and beside the program
            near, far = folder
            s.fail_span(f'There are two books called "{" ".join(t.text for t in book)}": the folder {near} beside this '
                        f"file, and the folder {far} beside the program, so I can't tell which is meant.",
                        (book[0].col, book[-1].end), hint="Rename one of the two folders.", teach="chapter")
        path = self.chapter_file(folder, [t.low for t in words], [t.low for t in book])
        key = os.path.normcase(os.path.abspath(path))
        if ("chapter", key) in here.used:
            s.fail(f"This file already uses the {name} chapter ({where(here.used[('chapter', key)])}).", words[0],
                   hint="A file says it uses a chapter once; this sentence can be taken out.", teach="chapter")
        unit = self.chapters.get(key)
        if unit is not None and unit in self.reading:
            circle = self.reading[self.reading.index(unit):] + [unit]
            s.fail("These chapters use each other in a circle: "
                   + " -> ".join(u.name or "the program" for u in circle) + ".", words[0],
                   hint="Move what they both need into a chapter of its own, which each of them can use.",
                   teach="chapter")
        given = self.read(path) if self.read is not None and unit is None else None
        if unit is None and given is None and not path.is_file():
            self.missing_chapter(s, words, name, path)
        here.used[("chapter", key)] = s.line
        if unit is not None:  # read already, for another file: this one may now say what it shares
            self.use_clashes(s, unit, words[0])
            here.uses.add(unit)
            self.note(f'"{name}" → {unit.file}, read already')
            return None
        try:
            text = given if given is not None else self.chapter_text(path)
        except (OSError, ValueError) as error:
            s.fail(f"I couldn't read the file {path}: {getattr(error, 'strerror', None) or error}.", words[0],
                   teach="chapter")
        file = os.path.relpath(path, self.main.folder) if self.main.folder else str(path)
        unit = Unit("chapter", name, path.parent, key, file.replace(os.sep, "/"))
        unit.used_at = s.line
        self.chapters[key] = unit
        steps = self.read_chapter(unit, text, s)
        self.use_clashes(s, unit, words[0])
        here.uses.add(unit)
        shared = "everything" if unit.shares is None else (unit.shared_list() or "nothing")
        self.note(f'"{name}" → {unit.file}, which shares {shared}')
        # What the chapter does when it is read may change any thing that this file sees.
        self.forget_after_verb()

        def step(env):
            world = env.world
            for inner in steps:
                world.changed = False
                inner(world.globals)
                if world.settlers or world.keepers:  # each top-level sentence of a chapter is a turn too
                    world.settle(inner.line)
        return step

    def shared_by(self, unit):
        """(word, what it is, Kind or None) for every top-level name `unit` shares."""
        found = []
        for K in self.kinds.values():
            if K.unit is unit and unit.shares_name(K.word):
                found += [(K.word, "a kind", None), (K.plural, "the plural of a kind", None)]
            for word, adj in K.adjectives.every():
                if adj.unit is unit and unit.shares_name(word):
                    found.append((word, "an adjective", K))
            for name, prop in K.props.every():
                if prop.unit is unit and unit.shares_name(name):
                    found.append((name, "a property", K))
        for view, what in ((self.names, "a thing"), (self.workouts, "a worked-out value"), (self.procs, "a verb")):
            found += [(key, what, None) for key, value in view.every()
                      if value.unit is unit and unit.shares_name(key)]
        found += [(b.name, "a variable", None) for b in self.globals.names.values()
                  if b.unit is unit and unit.shares_name(b.name)]
        return found

    def use_clashes(self, s, unit, tok):
        """Refuse a "Use" that would bring into view a name this file can already say
        with another meaning: its own, or one a chapter or library it uses shares. In
        one file, a word has one meaning. (Private names of another file are never in
        view, so they never clash.)"""
        here = self.unit
        if unit in here.uses:
            return
        for word, what, K in self.shared_by(unit):
            mine = None
            if K is not None:
                view = K.adjectives if what == "an adjective" else K.props
                if self.kind_visible(K.name) and word in view:
                    mine = (f"{what} of {article(K.word)}", view[word].unit)
            elif what == "a verb":
                if word in self.procs:
                    mine = (what, self.procs[word].unit)
            else:
                b = self.globals.find(word)
                if b is not None and b.unit is not None:
                    mine = ("a variable", b.unit)
                elif word in self.names:
                    mine = ("a thing", self.names[word].unit)
                elif word in self.workouts:
                    mine = ("a worked-out value", self.workouts[word].unit)
                elif word in self.nouns:
                    plural = self.nouns[word][1]
                    mine = ("the plural of a kind" if plural else "a kind", self.kinds[self.nouns[word][0]].unit)
            if mine is None:
                continue
            theirs, owner = mine
            at = "this file" if owner is here else owner.title
            s.fail(f'{cap(unit.title)} shares "{word}" ({what}), and "{word}" already means {theirs} here '
                   f"(from {at}), so in this file it would mean two things.", tok,
                   hint="Rename one of them, or leave one out of its file's \"This chapter shares only ...\": "
                        "a name a file keeps to itself is never in view anywhere else.",
                   teach="taken")

    def chapter_text(self, path):
        """A chapter's text: as an editor has it open, if `read` gives it, or else from the disk."""
        if self.read is not None:
            text = self.read(path)
            if text is not None:
                return text
        with open(path, encoding="utf-8") as handle:
            return handle.read()

    def missing_chapter(self, s, words, name, path):
        folder = path.parent
        if folder.is_dir():
            there = sorted(p.stem.replace("_", " ") for p in folder.glob("*.english")
                           if self.main.path is None or os.path.normcase(str(p.resolve())) != os.path.normcase(str(self.main.path)))
            hint = ("Chapters there: " + ", ".join(there) + ".") if there else "There are no chapters there."
        else:
            hint = f"There is no folder {folder}."
        s.fail_span(f'There is no chapter called "{name}": I looked for the file {path}.',
                    (words[0].col, words[-1].end), hint=hint, teach="chapter")

    def read_chapter(self, unit, text, s):
        """Compile a chapter's sentences as a file of their own. Returns its steps.

        While linting, the chapter's problems are collected apart, and reported as one
        error at the "Use" sentence."""
        saved = (self.unit, self.line, self.lint, self.scope)
        outer = self.lint
        collector = type(outer)(text) if outer is not None else None
        self.reading.append(unit)
        self.unit, self.lint, self.scope = unit, collector, self.globals
        level, self.level = self.level, 0
        try:
            with self.fresh(chapter=True):
                layout = [] if collector is not None else None
                lines = read_source(text, unit=unit, problems=layout)
                for error in layout or ():
                    collector.add(error, "error")
                unit.first = lines[0] if lines else None
                steps = self.block(lines, self.globals)
                self.check_shares(unit)
        finally:
            self.unit, self.line, self.lint, self.scope = saved
            self.level = level
            self.reading.pop()
        if collector is not None:
            errors = [p for p in collector.result() if p.kind == "error"]
            if errors:
                first = errors[0]
                count = f"{len(errors)} problem{'s' if len(errors) != 1 else ''}"
                hint = f"The first, in {unit.file}, line {first.line}:\n    {first.sentence.strip()}\n{first.message}"
                if first.hint:
                    hint += "\n" + first.hint
                col = s.toks[2].col if len(s.toks) > 2 else 0
                outer.add(EnglishError(f"{cap(unit.title)} has {count}.", s.line, col,
                                       max(1, s.prev_end(col) - col), hint,
                                       teach=next((k for k, r in RULES.items() if r[1] == first.rule), None),
                                       category=first.category), "error")
        return steps

    def shares_sentence(self, s):
        """This chapter shares only <name>, <name> and <name>.   This chapter shares nothing."""
        usage = 'For example: "This chapter shares only leapness, month length and weekday."'
        s.next()  # this
        s.next()  # chapter
        if not s.eat_word("shares"):
            self.misspelt(s, s.peek(), ["shares"], "shares_form")
            s.fail('After "This chapter" comes "shares".', hint=usage, teach="shares_form")
        unit = self.unit
        if s.line is not unit.first:
            s.fail('"This chapter shares ..." has to be the first sentence of its file.', s.toks[0],
                   hint="Move it to the top of the file.", teach="shares_first")
        if s.eat_word("nothing"):
            self.end(s)
            unit.shares, unit.share_at = set(), {}
            return None
        s.expect_word("only", hint=usage, teach="shares_form")
        listed = {}
        while True:
            toks = []
            while s.peek().kind == "WORD" and not s.at_word("and"):
                toks.append(s.next())
            if not toks:
                s.fail("This needs a name here, as it was defined, without \"the\".", hint=usage,
                       teach="shares_form")
            for tok in toks:
                if tok.low in ("the", "a", "an"):
                    s.fail("Names are listed as they were defined, without an article.", tok, hint=usage,
                           teach="shares_form", fix=swap(s.line, tok.col, toks[1].col, "")
                           if tok is toks[0] and len(toks) > 1 else None)
            name = " ".join(t.low for t in toks)
            if name in listed:
                s.fail(f'"{name}" is listed twice.', toks[0], hint="List each name once.", teach="shares_form")
            listed[name] = (s.line, toks[0].col, toks[-1].end - toks[0].col, " ".join(t.text for t in toks))
            if s.at_end():
                break
            comma, conj = s.eat_punct(","), s.eat_word("and")
            if not (comma or conj):
                s.fail('Names in the list are separated by a comma or by "and".', hint=usage, teach="list_commas")
        unit.shares, unit.share_at = set(listed), listed
        return None

    def defined_by(self, unit, name):
        """What `unit` defines at its top level under `name`: ["a kind", "a verb", ...]."""
        found = []
        K = self.kinds.get(name)
        if K is not None and K.unit is unit:
            found.append("kind")
        if any(entry.unit is unit for entry in self.names.anywhere(name)):
            found.append("thing")
        if any(proc.unit is unit for proc in self.procs.anywhere(name)):
            found.append("verb")
        if any(w.unit is unit for w in self.workouts.anywhere(name)):
            found.append("worked-out value")
        if any(b.name == name and b.unit is unit for b in self.globals.names.values()):
            found.append("variable")
        kinds = self.kinds.values()
        if any(adj.unit is unit for K in kinds for adj in K.adjectives.anywhere(name)):
            found.append("adjective")
        if any(prop.unit is unit for K in kinds for prop in K.props.anywhere(name)):
            found.append("property")
        return found

    def check_shares(self, unit):
        """At the end of a file: every name it shares must be one thing it defined."""
        for name, (line, col, width, _) in unit.share_at.items():
            found = self.defined_by(unit, name)
            message = hint = None
            if not found:
                message = f'"{name}" is listed as shared, but this file defines no "{name}" at its top level.'
                owner = [K for K in self.kinds.values() if K.unit is unit and name in K.fields]
                if owner:
                    hint = f'"{name}" is a property of {article(owner[0].word)}: it is shared with its kind.'
                elif self.nouns.first(name) is not None:
                    hint = f'Write the kind in the singular: "{self.kinds[self.nouns.first(name)[0]].word}".'
            elif len(found) > 1:
                message = (f'"{name}" could mean the {join_words(found)} called "{name}", '
                           "so I can't tell which to share.")
                hint = "Give one of them another name."
            if message:
                error = EnglishError(message, line, col, width, hint, teach="shared")
                if self.lint is not None:
                    self.lint.add(error, "error")
                else:
                    raise error

    @staticmethod
    def library_fault(use_line, tok, name, error):
        """A sentence of a library's SOURCE can't be read. Point at the "Use"
        sentence, and show the library's own sentence in the hint."""
        detail = []
        if error.line is not None and error.line.library == name:
            detail.append(f"In the {name} library, line {error.line.number}:")
            detail.append("    " + error.line.text.strip())
        else:
            detail.append(f"In the {name} library:")
        detail.append(error.message)
        if error.hint:
            detail.extend(error.hint.split("\n"))
        detail.append(f"This is a fault in the {name} library, unless it reuses a name your program "
                      "defined before this sentence.")
        return EnglishError(f"The {name} library has a sentence I can't read.", use_line, tok.col,
                            len(tok.text), hint="\n".join(detail), teach="library_fault")

    @staticmethod
    def done_by_library(line):
        """Does the sentence end "is done by the library"?"""
        words = line.tokens[:-1]  # without END
        return len(words) > 5 and all(t.is_word(w) for t, w in zip(words[-5:], DONE_BY_LIBRARY))

    def define_outside(self, s):
        """To <verb> ... is done by the library.
        To work out the <name> (<type>) ... is done by the library.

        Only in a library's SOURCE: the header of a verb or worked-out value
        whose block is a Python function of the library.
        """
        line = s.line
        cut = line.tokens[-6]  # "is"
        if self.library is None:
            s.fail('Only a library can say "is done by the library".', cut,
                   hint="A program teaches a verb with a colon and an indented block.", teach="verb_form")
        self.needs_block(s, False)
        header = Sentence(line, line.tokens[:-6] + [Token("END", "", cut.col)])
        self.define_procedure(header, outside=True)

    def library_function(self, s, fname):
        name, module = self.library
        fn = getattr(module, fname, None)
        if not callable(fn):
            s.fail(f'The {name} library has no Python function "{fname}" for this.', s.toks[0],
                   hint=f'It needs: def {fname}(world, ...):', teach="library_fault")
        return name, fn

    def outside_verb(self, s, proc):
        """The body of a verb that is done by the library."""
        lib, fn = self.library_function(s, "verb_" + proc.verb)
        roles = [(p.name, p.name.replace(" ", "_")) for p in proc.params]

        def step(env):
            world = env.world
            try:
                call_library(lib, fn, world, {key: env.get(role) for role, key in roles})
            finally:
                world.indexes = {}  # the library may have changed things directly
        return step

    def outside_value(self, s, w):
        """The body of a worked-out value that is done by the library."""
        lib, fn = self.library_function(s, "value_" + w.name.replace(" ", "_"))
        roles = [(p.name, p.name.replace(" ", "_")) for p in w.params]
        wanted = self.describe(w.type)

        def step(env):
            value = call_library(lib, fn, env.world, {key: env.get(role) for role, key in roles})
            converted = from_library(value, w.type)
            if converted is _MISMATCH:
                shown = repr(value)
                if len(shown) > 60:
                    shown = shown[:57] + "..."
                raise EnglishError(
                    f'The {lib} library gave back {shown} ({type(value).__name__}) for "the {w.name}", '
                    f"which should be {wanted}.", stage="run",
                    hint=f"This is a fault in the {lib} library, not in your program.", teach="library_run",
                )
            raise _Answer(converted)
        step.answers = step.leaves = True
        return step

    def create_thing(self, s):
        """There is a | an [<adjective>]... <kind> called <Name> [whose ...]... .   (top level)"""
        s.next()  # there
        s.expect_word("is", hint='For example: "There is a dragon called Smaug whose age is 771."',
                      teach="thing_form")
        if not s.eat_word("a", "an"):
            self.no_article(s)
        K, marks = self.thing_head(s)
        s.expect_word("called", f"Every {K.word} made this way needs a name: \"There is {article(K.word)} called "
                                f"...\".", hint='For a thing with no name, write "There is a new ...".',
                      teach="thing_form")
        ntoks = []
        while s.peek().kind == "WORD" and not s.at_word("whose"):
            ntoks.append(s.next())
        if not ntoks:
            s.fail('After "called" comes the thing\'s name.', teach="thing_form")
        self.check_new_name(s, ntoks, "a name")
        display = " ".join(t.text for t in ntoks)
        key = display.lower()
        self.name_is_new(s, key, ntoks[0])
        self.not_an_adjective(s, ntoks, "the name of a thing")
        values = self.whose_parts(s, K, ntoks[0])
        self.made(key, "a thing", s.line)
        self.defines("thing", display, s.line, ntoks[0].col, ntoks[-1].end - ntoks[0].col, of=K.word)
        slot = self.slot(key, self.unit)  # where World.named keeps it: apart from another file's private one
        self.names[key] = Named(display, K.name, self.unit, slot)
        make = self.maker(K, marks, values, lambda env, count: display)

        def step(env):
            env.world.named[slot] = make(env)
        return self.changing(step)

    def no_article(self, s):
        """Refuse "There is dragon called ...": the noun needs its article."""
        tok = s.peek()
        k = 0
        while s.peek(k).kind == "WORD" and not s.peek(k).is_word("called", "whose", "new"):
            noun = self.nouns.get(s.peek(k).low)
            if noun and not noun[1] and tok.low not in KEYWORDS:
                written = article(tok.text)
                s.fail(f'A noun takes an article: "There is {written} ...".', tok, teach="article",
                       fix=swap(s.line, tok.col, tok.col, written[:-len(tok.text)]))
            k += 1
        s.fail('After "There is" comes "a" or "an" and a kind, as in "There is a dragon called Smaug".', tok,
               teach="thing_form")

    def create_new(self, s):
        """There is a new <kind> [called <text>] [whose ...]... .   (anywhere)"""
        s.next()  # there
        s.next()  # is
        if not s.eat_word("a", "an"):
            self.no_article(s)
        _, make = self.new_thing(s)
        return self.changing(lambda env: make(env))

    def new_thing(self, s):
        """'new [<adjective>]... <kind> [called <text>] [whose ...]...' to the end of the sentence.

        Returns (the kind, fn(env) -> the new Thing).
        """
        new = s.next()
        if self.workout is not None:
            s.fail("Working something out can't make new things.", new,
                   hint="Make it in a verb, or where the worked-out value is used.", teach="working_out")
        K, marks = self.thing_head(s)
        kind = K.name
        if s.eat_word("called"):
            name = self.expr(s)
            self.need(s, name)
            if name.type != "text":
                s.fail_span(f"A name is text, but {name.text} is {self.describe(name.type)}.", name.span,
                            hint='Put a name in quotes: called "Puff".', teach="fit")
            name_fn = name.fn
            name_of = lambda env, count: name_fn(env)
        else:
            word = K.word
            name_of = lambda env, count: f"{word} {count}"
        values = self.whose_parts(s, K, new)
        return kind, self.maker(K, marks, values, name_of)

    def thing_head(self, s):
        """'[<adjective>]... <kind>' when a thing is made. Returns (Kind, stored adjectives)."""
        k = 0
        while True:
            tok = s.peek(k)
            if tok.kind != "WORD" or tok.is_word("called", "whose"):
                k = 0  # no kind ahead: let need_kind explain
                break
            if tok.low in self.nouns and not self.nouns[tok.low][1]:
                break
            k += 1
        adjectives = [s.next() for _ in range(k)]
        K = self.need_kind(s, s.next())
        marks = []
        for tok in adjectives:
            adj = K.adjectives.get(tok.low)
            if adj is None:
                self.hidden_adjective(s, tok, K)
                self.misspelt(s, tok, [a for a in K.adjectives if K.adjectives[a].stored], "unknown_adjective")
                s.fail(
                    f'I don\'t know what "{tok.text}" means for {article(K.word)}.', tok,
                    hint=f'Say first: "{article(K.word).capitalize()} can be {tok.text}."', teach="unknown_adjective",
                )
            if not adj.stored:
                s.fail(
                    f'"{tok.text}" is worked out from "{adj.source}", so it can\'t be given when {article(K.word)} is made.',
                    tok, hint="Only an adjective made with \"can be\" can be given to a new thing.", teach="new_thing",
                )
            marks.append(adj.mark)
            adj.used = True
        return K, marks

    def whose_parts(self, s, K, at):
        """'whose <property> is <value>', joined by commas or "and", to the end of the sentence."""
        values = {}
        first = True
        while not s.at_end():
            if not first:
                comma, conj = s.eat_punct(","), s.eat_word("and")
                if not (comma or conj):
                    s.fail('After a value comes "and whose ..." or the end of the sentence.', teach="thing_form")
            first = False
            s.expect_word("whose", teach="thing_form")
            match = self.match_words(s, K.fields)
            if not match:
                self.no_member(s, K.name)
            fname, count = match
            ftok = s.peek()
            for _ in range(count):
                s.next()
            if fname in values:
                s.fail(f'"{fname}" is given twice.', ftok, hint="Give each property once.", teach="thing_form")
            s.expect_word("is", teach="thing_form")
            start = s.peek().col
            self.in_thing_whose += 1
            self.group_ended = None
            try:
                value = self.whole_value(s, K.fields.get(fname))
            finally:
                self.in_thing_whose -= 1
            nxt = s.peek(1) if s.peek().is_punct(",") else s.peek()
            if self.group_ended == s.i and (s.at_words("and", "whose") or (s.peek().is_punct(",") and nxt.is_word("whose"))):
                # "whose wage is the total wage of squires whose wage is more than $2 and whose mount ...":
                # the last "whose" could belong to the group or to the thing being made.
                text, end = s.line.text, s.prev_end(start)
                group = text[start:end]
                rest = text[s.peek().col:s.toks[-1].col].strip()
                readings = (f"  (1) {group} {rest}   (the group's)\n"
                            f"  (2) ({group}) {rest}   (the new {K.word}'s)")
                s.fail(f'This "whose" can belong to the group before it or to the new {K.word}:',
                       s.peek(), hint=readings + "\nPut brackets round the group, as in (2), to say it is the "
                       f"{K.word}'s; or give the group's filters before the thing is made, in a variable.",
                       teach="value_order", fix=swap(s.line, start, end, f"({group})"))
            want = K.fields[fname]
            if not self.fits(value.type, want):
                if base(value.type) == base(want):
                    self.need(s, value)
                s.fail_span(
                    f"{article(K.word).capitalize()}'s {fname} is {self.describe(want)}, "
                    f"but {value.text} is {self.describe(value.type)}.", value.span, teach="fit",
                )
            values[fname] = value.fn
        missing = [f for f, t in K.fields.items() if f not in values and not is_opt(t) and not is_list(t)]
        if missing:
            s.fail(
                f"{article(K.word).capitalize()} also needs {join_words(article(m) for m in missing)}.", at,
                hint=f'Add: "whose {missing[0]} is ...".', teach="thing_form",
            )
        return values

    @staticmethod
    def maker(K, marks, values, name_of):
        """fn(env) -> a new thing of kind K, checked against the kind's rules."""
        kind = K.name
        # A list property not given starts empty; any other property not given is nothing.
        absent = [(f, () if is_list(t) and not is_opt(t) else None) for f, t in K.fields.items() if f not in values]

        def make(env):
            world = env.world
            count = world.made[kind] = world.made.get(kind, 0) + 1
            name = name_of(env, count)
            fields = {f: fn(env) for f, fn in values.items()}
            for value in fields.values():
                if isinstance(value, Thing):
                    alive(value)
            fields.update(absent)
            thing = Thing(kind, name, fields, marks, world.new_serial())
            for rule in world.rules.get(kind, ()):
                if not rule.fn(world, thing):
                    raise EnglishError(f'{name} would break a rule: "{rule.text}"', stage="run", recoverable=True,
                                       teach="rule_broken")
            world.things.setdefault(kind, []).append(thing)
            if world.indexes:
                world.added(thing)
            return thing
        return make

    # actions ------------------------------------------------------------

    def let(self, s):
        s.next()
        s.eat_word("the")
        toks = []
        while s.peek().kind == "WORD" and not s.at_word("be", "always"):
            toks.append(s.next())
        if not toks:
            s.fail('After "Let" comes the name of the variable, as in "Let the total be 0."', teach="let_form")
        declared = self.bracket_type(s) if s.eat_punct("(") else None
        fixed = bool(s.eat_word("always"))
        if s.peek().is_punct("=") and toks:
            eq = s.peek()
            name, value = self.new_name(toks), self.certain_value(s.toks[s.i + 1:-1])
            fix = swap(s.line, eq.col, eq.end, "be") if name and value and declared is None else None
            s.fail('EnglishScript writes "Let ... be", not "=".', eq,
                   hint="Write: " + full_stop(f"Let {name or '...'} be {value or '...'}"), teach="let_form", fix=fix)
        s.expect_word("be", hint='For example: "Let the total be 0."', teach="let_form")
        self.check_new_name(s, toks, "a name")
        name = " ".join(t.low for t in toks)
        self.name_is_new(s, name, toks[0], local=self.scope is not self.globals,
                         hint=f'To change it, write "Set {name} to ...".')
        self.not_an_adjective(s, toks, "the name of a variable")
        made_new = s.at_word("a", "an") and s.peek(1).is_word("new")
        if made_new:
            start = s.next().col
            kind, make = self.new_thing(s)
            value = self.stamp(s, Expr(kind, make), start)
        else:
            value = self.whole_value(s, declared)
        self.end(s)
        if declared is None:
            if value.type == "nothing":
                s.fail_span(
                    "Nothing of what sort? I can't tell what this may hold later.", value.span,
                    hint=f'Say so in brackets: "Let {name} (number, if any) be nothing."', teach="let_form",
                )
            declared = value.type
        elif not self.fits(value.type, declared):
            if base(value.type) == base(declared):
                self.need(s, value)
            s.fail_span(
                f'"{name}" is to hold {self.describe(declared)}, but {value.text} is {self.describe(value.type)}.',
                value.span, teach="fit",
            )
        self.kind_named(s, name, declared, (toks[0].col, toks[-1].end), "variable")
        self.made(name, "a variable", s.line)
        binding = Binding(name, declared, let=not fixed, fixed=fixed)
        if self.scope is self.globals:
            binding.unit = self.unit
            binding.slot = self.slot(name, self.unit)  # a private variable is kept apart from other files'
        slot = binding.slot
        self.scope.names[slot] = binding
        self.declare("variable", name, s.line, (toks[0].col, toks[-1].end - toks[0].col),
                     lambda: binding.reads > 0, type_=declared)
        if is_opt(declared) and not is_opt(value.type) and value.type != "nothing":
            self.present = self.present | {("var", slot)}
        self.note(f'"{name}" is {self.describe(declared)}')
        fn = value.fn

        def step(env):
            env.vars[slot] = fn(env)
        if made_new:
            self.changing(step)
        return step

    def target(self, s):
        expr = self.primary(s)
        kind = expr.target[0] if expr.target else None
        if kind == "item":  # "item 2 of the scores": what is changed is the list
            self.check_target(s, expr.target[1])
            return expr
        return self.check_target(s, expr)

    def check_target(self, s, expr):
        kind = expr.target[0] if expr.target else None
        if kind is None:
            s.fail_span(f"{cap(expr.text)} isn't something that can be changed: only a variable or a stored "
                        "property can be.", expr.span, teach="changeable")
        if kind == "prop":
            prop = expr.target[1]
            s.fail_span(
                f"{cap(expr.text)} is worked out by its definition, so it can't be changed directly.", expr.span,
                hint=f'It is worked out as: "{prop.name}" is {prop.source}.', teach="changeable",
            )
        if kind == "fixed":
            s.fail_span(f'{cap(expr.text)} was made with "always", so it can\'t be changed.', expr.span,
                        teach="changeable")
        if kind == "maybe":
            self.need(s, expr.target[1])
        if kind == "field":
            owner, fname, K = expr.target[1], expr.target[2], expr.target[3]
            kept = K.kept.get(fname)
            if kept is None and owner.key is not None and owner.key[0] == "thing":
                kept = self.kept_things.get((owner.key[1], fname))
            if kept is not None:
                s.fail_span(f"{cap(expr.text)} is kept in step by its own sentence ({where(kept)}: "
                            f"\"{kept.text.strip()}\"), so it can't be changed any other way.", expr.span,
                            hint="Change what it is kept as instead.", teach="kept")
        if self.workout is not None and (kind == "field" or expr.target[1] in self.globals.names):
            s.fail_span(
                f"Working something out can't change anything, and {expr.text} belongs to the world outside.",
                expr.span,
                hint="Do the change in a verb, or keep the working in a variable made inside this block.",
                teach="working_out",
            )
        return expr

    def store(self, expr):
        if expr.target[0] == "var":
            name = expr.target[1]
            return lambda env, value: env.set(name, value)
        _, owner, fname, K = expr.target
        owner_fn, ftype = owner.fn, expr.declared

        def put(env, value):
            thing = alive(owner_fn(env))
            if isinstance(value, Thing):
                alive(value)  # a property may not point at a removed thing
            old = thing.fields[fname]
            thing.fields[fname] = value
            for rule in env.world.rules.get(K.name, ()):
                if not rule.fn(env.world, thing):
                    thing.fields[fname] = old
                    raise EnglishError(
                        f'That would break a rule: "{rule.text}"', stage="run", recoverable=True,
                        hint=f"({thing.name}'s {fname} is {fmt(old, ftype)} and would become {fmt(value, ftype)}.)",
                        teach="rule_broken",
                    )
            if env.world.indexes:
                env.world.changed_field(thing, fname, old)
        return put

    def list_add(self, s, verb, target, value):
        """'Add <value> to <list>.': the list with the value put at the end."""
        if verb != "add":
            s.fail_span(f"{cap(target.text)} is a list, and an item is taken out of a list with \"Remove\": "
                        f"Remove {value.text} from {target.text}.", target.span, teach="list",
                        fix=self.whole(s, f"Remove {value.text} from {target.text}."))
        self.need(s, value)
        item = item_type(target.declared)
        if value.type != item:
            s.fail_span(f"{cap(target.text)} holds {self.plural_type(item)}, but {value.text} is "
                        f"{self.describe(value.type)}.", value.span, teach="fit")
        lf, vf = target.fn, value.fn
        return Expr(target.declared, lambda env: lf(env) + (vf(env),))

    def item_set(self, s, target, value):
        """'Set item <number> of <list> to <value>.': (the list's target, the list with that item replaced)."""
        _, items, number = target.target
        item = item_type(items.declared)
        self.need(s, value)
        if value.type != item:
            s.fail_span(f"{cap(items.text)} holds {self.plural_type(item)}, but {value.text} is "
                        f"{self.describe(value.type)}.", value.span, teach="fit")
        lf, nf, vf = items.fn, number.fn, value.fn
        shown = items.text

        def fn(env):
            values, n = lf(env), nf(env)
            if n.denominator != 1 or not 1 <= n <= len(values):
                raise EnglishError(f"There is no item {fmt(n, 'number')} of {shown}: it has "
                                   f"{len(values)} item{'' if len(values) == 1 else 's'}.", stage="run",
                                   recoverable=True, teach="missing_item",
                                   hint='Add an item to the end with "Add ... to ...".')
            at = int(n) - 1
            return values[:at] + (vf(env),) + values[at + 1:]
        return items, Expr(items.declared, fn)

    def linking(self, s, verb, link):
        """Refuse "Subtract $5 to ...", "Set x as 5", "Multiply x with 2": the verb's own
        linking word, with the correction."""
        tok = s.peek()
        wrong = tok.is_punct("=") or (tok.kind == "WORD" and tok.low in ("to", "from", "by", "with", "into",
                                                                         "onto", "as", "of", "in", "on", "is"))
        if wrong and not tok.is_word(link):
            s.fail(f'"{verb.capitalize()}" goes with "{link}": {verb.capitalize()} ... {link} ..., not "{tok.text}".',
                   tok, teach="linking_word", fix=swap(s.line, tok.col, tok.end, link))

    def assign(self, s):
        verb = s.next().low
        if verb == "set":
            target = self.target(s)
            if target.target[0] == "var":
                self.scope.find(target.target[1]).reads -= 1  # set, not read
            self.linking(s, "set", "to")
            s.expect_word("to", hint='For example: "Set the total to 0."', teach="linking_word")
            new = value = self.whole_value(s, target.declared)
            if target.target[0] == "item":
                target, new = self.item_set(s, target, value)
        elif verb in ("add", "subtract"):
            value = self.expr(s)
            to_file = s.at_words("to", "the", "file") and (
                base(value.type) == "text" or not self.match_words(s, self.scope.visible(), 2)
            )
            if verb == "add" and to_file:
                # Text can't be added up, and no variable is called "file ...", so this is
                # "Add <text> to the file <text>." (file_write refuses anything but text).
                for _ in range(3):
                    s.next()
                return self.file_write(s, value, append=True)
            link = "to" if verb == "add" else "from"
            self.linking(s, verb, link)
            s.expect_word(link, hint=f'For example: "{verb.capitalize()} 1 {link} the total."', teach="linking_word")
            target = self.target(s)
            if target.target[0] == "item":
                s.fail_span(f"{cap(target.text)} is one item: to change it, write \"Set {target.text} to ...\".",
                            target.span, teach="list")
            if is_list(target.declared):
                new = self.list_add(s, verb, target, value)
            else:
                new = self.arith(s, "+" if verb == "add" else "-", target, value)
        else:
            target = self.target(s)
            self.linking(s, verb, "by")
            s.expect_word("by", hint=f'For example: "{verb.capitalize()} the total by 2."', teach="linking_word")
            value = self.expr(s)
            new = self.arith(s, "*" if verb == "multiply" else "/", target, value)
        self.end(s)
        want = target.declared
        if not self.fits(new.type, want):
            if base(new.type) == base(want):
                self.need(s, value)
            s.fail_span(
                f"{cap(target.text)} is {self.describe(want)}, but that would make it {self.describe(new.type)}.",
                value.span, teach="fit",
            )
        # Whatever was known about this property or variable no longer holds.
        if target.target[0] == "var":
            self.forget(("var", target.target[1]))
        else:
            self.forget(("field", target.target[2]))
        if target.key is not None and is_opt(want) and new.type != "nothing" and not is_opt(new.type):
            self.present = self.present | {target.key}
        put, fn = self.store(target), new.fn
        step = lambda env: put(env, fn(env))  # noqa: E731
        # An adjective may read a property or a top-level variable, never a variable of a block.
        if target.target[0] != "var" or target.target[1] in self.globals.names:
            self.changing(step)
        if target.target[0] == "field":
            step.focus = target.target[1].fn  # it changes one property of one thing
        return step

    def say(self, s):
        if self.workout is not None:
            s.fail("Working something out can't say anything.",
                   hint="Say it from a verb, or where the worked-out value is used.", teach="working_out")
        s.next()
        value = self.expr(s)
        self.end(s)
        self.sayable(s, value)
        fn, type_ = value.fn, value.type
        return lambda env: env.world.out(fmt(fn(env), type_))

    def answer(self, s):
        """The answer is <expression>.  Ends a "To work out" block."""
        s.next()
        s.next()
        if self.workout is None:
            s.fail('"The answer is" belongs inside a "To work out ...:" block.', s.toks[0],
                   hint='To show a value, write "Say ..." instead.', teach="answer_place")
        s.expect_word("is", teach="answer_place")
        value = self.whole_value(s, self.workout.type)
        self.end(s)
        w = self.workout
        if not self.fits(value.type, w.type):
            if base(value.type) == base(w.type):
                self.need(s, value)
            s.fail_span(
                f"The {w.name} is {self.describe(w.type)}, but {value.text} is {self.describe(value.type)}.",
                value.span, teach="fit",
            )
        fn = value.fn

        def step(env):
            raise _Answer(fn(env))
        step.answers = step.leaves = True
        return step

    def one_loop(self, s, phrase):
        if not self.loops:
            s.fail(f'"{phrase}." needs a loop around it.', s.toks[0], teach="one_loop")
        if len(self.loops) > 1:
            s.fail(
                f'"{phrase}." could mean either of the loops around it.', s.toks[0],
                hint='Move the inner loop into its own verb, and use "Stop." there.', teach="one_loop",
            )
        return self.loops[-1]

    def stop(self, s):
        s.next()
        if s.eat_word("repeating"):
            self.end(s)
            found = self.one_loop(s, "Stop repeating")
            found["stops"].append(self.present)
            loop = found["id"]

            def step(env):
                raise _StopLoop(loop)
            step.leaves = True
            return step
        self.end(s)
        if self.workout is not None:
            s.fail('Inside "To work out", finish with "The answer is ...".', s.toks[0], teach="answer_paths")
        if self.verb is None:
            s.fail(
                '"Stop." ends a verb, and this sentence isn\'t inside one.', s.toks[0],
                hint='To leave a loop, write "Stop repeating." To finish altogether, write "End the program."',
                teach="place",
            )

        def step(env):
            raise _StopVerb()
        step.leaves = True
        return step

    def skip(self, s):
        s.next()
        s.expect_word("this", hint='Write "Skip this round." or, in a For each, "Skip this dragon."',
                      teach="leaving_form")
        tok = s.peek()
        if tok.kind != "WORD":
            s.fail('After "Skip this" comes "round", or the noun of a For each.', tok, teach="leaving_form")
        if tok.low == "round":
            s.next()
            self.end(s)
            found = self.one_loop(s, "Skip this round")
            if found["noun"]:
                s.fail('A "For each" has no rounds.', tok, teach="leaving_form",
                       fix=s.replace(tok, found["noun"]))
        else:
            # A loop's noun may be several words: "For each old task in ...".
            match = self.match_words(s, [loop["noun"] for loop in self.loops if loop["noun"]])
            if not match:
                s.next()
                self.end(s)
                nouns = [loop["noun"] for loop in self.loops if loop["noun"]]
                close = close_words(tok.text, nouns)
                s.fail(f'There is no "For each {tok.text}" around this sentence.', tok, teach="leaving_form",
                       hint=("Loops around it: " + ", ".join(f'"For each {n}"' for n in nouns) + ".") if nouns
                       else 'No "For each" is around it: to go on to the next round, write "Skip this round."',
                       fix=s.replace(tok, close[0]) if len(close) == 1 and " " not in close[0] else None)
            for _ in range(match[1]):
                s.next()
            self.end(s)
            found = [loop for loop in self.loops if loop["noun"] == match[0]][-1]
        found["skips"].append(self.present)
        loop = found["id"]

        def step(env):
            raise _SkipRound(loop)
        step.leaves = True
        return step

    def end_program(self, s):
        s.next()
        if s.at_end() or s.at_word("if", "for", "while", "repeat", "loop", "to", "try", "each", "of"):
            s.fail(f'"{s.line.text[s.toks[0].col:s.prev_end(0) if s.at_end() else s.peek().end].strip()}" '
                   "isn't needed in EnglishScript.", s.toks[0],
                   hint='A block ends where the indentation ends: just stop indenting.\n'
                        'To finish the whole program, write "End the program.".', teach="block_end")
        s.expect_word("the", hint='Write "End the program."', teach="leaving_form")
        s.expect_word("program", hint='Write "End the program."', teach="leaving_form")
        self.end(s)
        if self.workout is not None:
            s.fail('Inside "To work out", finish with "The answer is ...".', s.toks[0], teach="answer_paths")

        def step(env):
            raise _EndProgram()
        step.leaves = True
        return step

    def no_change_here(self, s, what):
        """Refuse a sentence that changes the world inside "To work out"."""
        if self.workout is not None:
            s.fail(f"Working something out can't {what}.", s.toks[0],
                   hint="Do it in a verb, or where the worked-out value is used.", teach="working_out")

    def fail_because(self, s):
        """Fail because <text>.  A problem of the program's own, which "Try:" can recover from.
        Fail again.  Inside "If that fails:": the same problem, passed on unchanged."""
        s.next()
        if s.at_word("again"):
            again = s.next()
            self.end(s)
            if not self.scope.find(PROBLEM_ERROR):
                s.fail('"Fail again." passes on the problem of an "If that fails:" block, so it belongs inside one.',
                       again, hint='To raise a problem of your own, write "Fail because ...".', teach="place")

            def step(env):
                error = env.get(PROBLEM_ERROR)
                raise EnglishError(error.message, stage="run", recoverable=True, teach=error.key, hint=error.hint,
                                   problem=error.kind)
            step.answers = step.leaves = True
            return step
        s.expect_word("because", hint='For example: "Fail because "the gate is shut"."', teach="fail_form")
        reason = self.expr(s)
        self.end(s)
        self.need(s, reason)
        if reason.type != "text":
            s.fail_span(f"The reason is text, but {reason.text} is {self.describe(reason.type)}.", reason.span,
                        hint='Put the reason in quotes, or fill it in: "the count is {the count}".', teach="fit")
        rf = reason.fn

        def step(env):
            raise EnglishError(rf(env), stage="run", recoverable=True, teach="fail")
        # A path that fails never falls off the end, so in "To work out" it
        # needs no answer of its own.
        step.answers = step.leaves = True
        return step

    def now(self, s):
        """Now <thing> is [not] <stored adjective>."""
        s.next()
        self.no_change_here(s, "change anything")
        thing = self.expr(s)
        self.need(s, thing)
        if thing.type not in self.kinds:
            s.fail_span(f"{cap(thing.text)} is {self.describe(thing.type)}, so it has no adjectives.", thing.span,
                        teach="props_of")
        K = self.kinds[thing.type]
        s.expect_word("is", hint='For example: "Now Robin is sworn."', teach="adjective_form")
        negated = bool(s.eat_word("not"))
        atok = s.next()
        adj = K.adjectives.get(atok.low) if atok.kind == "WORD" else None
        if adj is None:
            self.hidden_adjective(s, atok, K)
            self.misspelt(s, atok, [a for a in K.adjectives if K.adjectives[a].stored], "unknown_adjective")
            s.fail(
                f'I don\'t know what "{atok.text}" means for {article(K.word)}.', atok,
                hint=f'To store it, say first: "{article(K.word).capitalize()} can be {atok.text}."',
                teach="unknown_adjective",
            )
        if not adj.stored:
            s.fail(
                f'"{atok.text}" is worked out from "{adj.source}", so "Now" can\'t change it.', atok,
                hint='Change what it is worked out from, or describe it with "can be" instead.', teach="changeable",
            )
        kept = K.kept.get(("adjective", adj.name))
        if kept is not None:
            s.fail(f'"{atok.text}" is kept in step by its own sentence ({where(kept)}: "{kept.text.strip()}"), so '
                   '"Now" can\'t change it.', atok, hint="Change what it is kept as instead.", teach="kept")
        self.end(s)
        self.note(f'"{atok.text}" → {adj.source}')
        tf, name = thing.fn, adj.mark
        adj.used = True

        def step(env):
            target = alive(tf(env))
            if negated:
                target.marks.discard(name)
            else:
                target.marks.add(name)
        step.focus = tf  # it changes a stored adjective of one thing
        return self.changing(step)

    def remove(self, s):
        """Remove <thing>.  It leaves every group; "if any" properties that pointed at it become nothing."""
        s.next()
        thing = self.expr(s)
        if s.at_word("from"):  # "Remove <value> from <list>."
            return self.remove_item(s, thing)
        self.no_change_here(s, "remove anything")
        self.end(s)
        self.need(s, thing)
        if thing.type not in self.kinds:
            s.fail_span(f"Only a thing can be removed, but {thing.text} is {self.describe(thing.type)}.", thing.span,
                        teach="props_of")
        if not self.kind_visible(thing.type):
            K = self.kinds[thing.type]
            s.fail_span(f"{cap(thing.text)} is {article(K.name)}, a kind this file can't name, so it can't remove "
                        "it: only a file that can name a kind may take its things out of the world.", thing.span,
                        hint=f"Leave it to {K.unit.title}: it could share a verb that removes it.", teach="shared")
        # Properties that pointed at it become nothing, so checks no longer hold.
        self.forget_after_verb()
        tf, kinds = thing.fn, self.kinds
        return self.changing(lambda env: self.remove_thing(env.world, alive(tf(env)), kinds))

    def remove_item(self, s, value):
        """'Remove <value> from <list>.': the first item equal to it is taken out; if
        there is none, nothing happens. Told from "Remove <thing>." by "from"."""
        s.next()  # from
        target = self.target(s)
        self.end(s)
        if not is_list(target.declared) or target.target[0] == "item":
            s.fail_span(f'"Remove ... from" takes an item out of a list, but {target.text} is '
                        f"{self.describe(target.type)}.", target.span, teach="list",
                        hint='To take a thing out of the world, write "Remove" and the thing alone.')
        self.need(s, value)
        item = item_type(target.declared)
        if value.type != item:
            s.fail_span(f"{cap(target.text)} holds {self.plural_type(item)}, but {value.text} is "
                        f"{self.describe(value.type)}.", value.span, teach="fit")
        lf, vf, things = target.fn, value.fn, item in self.kinds

        def fn(env):
            values, wanted = lf(env), vf(env)
            for at, v in enumerate(values):
                if (v is wanted) if things else (v == wanted):
                    return values[:at] + values[at + 1:]
            return values
        new = Expr(target.declared, fn)
        if target.target[0] == "var":
            self.forget(("var", target.target[1]))
        else:
            self.forget(("field", target.target[2]))
        put = self.store(target)
        step = lambda env: put(env, fn(env))  # noqa: E731
        if target.target[0] != "var" or target.target[1] in self.globals.names:
            self.changing(step)
        if target.target[0] == "field":
            step.focus = target.target[1].fn
        return step

    @staticmethod
    def remove_thing(world, thing, kinds):
        blockers, cleared, held = [], [], []  # held: list properties it is in, which it leaves
        for kind, items in world.things.items():
            fields = kinds[kind].fields
            for other in items:
                if other is thing:
                    continue
                for fname, value in other.fields.items():
                    if value is thing:
                        (cleared if is_opt(fields[fname]) else blockers).append((other, fname))
                    elif type(value) is tuple and any(item is thing for item in value):
                        held.append((other, fname))
        if blockers:
            which = join_words(f"{other.name}'s {fname}" for other, fname in blockers)
            raise EnglishError(
                f"I can't remove {thing.name} while {which} still {'points' if len(blockers) == 1 else 'point'} at it.",
                stage="run", recoverable=True,
                hint='Change or remove those first, or describe the property with "if any".', teach="removed",
                problem="refused removal",
            )
        for other, fname in held:
            other.fields[fname] = tuple(item for item in other.fields[fname] if item is not thing)
        if world.indexes:
            world.dropped(thing)
        for other, fname in cleared:
            other.fields[fname] = None
            if world.indexes:
                world.changed_field(other, fname, thing)
        for other, fname in cleared:
            for rule in world.rules.get(other.kind, ()):
                if not rule.fn(world, other):
                    for back, bname in cleared:
                        back.fields[bname] = thing
                    world.indexes = {}  # built again when next needed
                    raise EnglishError(
                        f'Removing {thing.name} would break a rule: "{rule.text}"', stage="run", recoverable=True,
                        hint=f"({other.name}'s {fname} would become nothing.)", teach="rule_broken",
                    )
        world.things[thing.kind].remove(thing)
        thing.removed = True

    def question_text(self, s, usage, teach="fit"):
        """The question of "Ask", "Ask the model" or "Judge": a text."""
        question = self.expr(s)
        self.need(s, question)
        if question.type != "text":
            s.fail_span(f"The question is text, but {question.text} is {self.describe(question.type)}.",
                        question.span, hint=usage, teach=teach)
        return question

    def reply_name(self, s, usage, teach, after="and let", taken=None):
        """[the] <name> (<type>): a new variable for a reply, with its type in brackets.
        Returns (name, its words, type, the word that starts the type). The variable is
        made by bind_reply, once the whole sentence has been read. `taken` is a name the
        same sentence has made already."""
        s.eat_word("the")
        toks = []
        while s.peek().kind == "WORD" and not s.at_word("be"):
            toks.append(s.next())
        if not toks:
            s.fail(f'After "{after}" comes a name for the reply.', hint=usage, teach=teach)
        self.check_new_name(s, toks, "a name")
        name = " ".join(t.low for t in toks)
        if name == taken:
            s.fail(f'"{name}" already means something here.', toks[0], hint="Choose a new name for the reply.",
                   teach="taken")
        self.name_is_new(s, name, toks[0], local=self.scope is not self.globals,
                         hint="Choose a new name for the reply.")
        self.not_an_adjective(s, toks, "the name of a variable")
        if not s.eat_punct("("):
            s.fail(f'What sort of reply is "{name}"? Say so in brackets, such as "{name} (number)".', hint=usage,
                   teach=teach)
        type_tok = s.peek()
        type_ = self.bracket_type(s)
        self.kind_named(s, name, type_, (toks[0].col, toks[-1].end), "variable")
        self.made(name, "a variable", s.line)
        return name, toks, type_, type_tok

    def bind_reply(self, s, name, toks, type_, source="the reply"):
        """Make the variable a reply is kept in (see reply_name). Returns its slot."""
        binding = Binding(name, type_, let=True)
        if self.scope is self.globals:
            binding.unit = self.unit
            binding.slot = self.slot(name, self.unit)
        self.scope.names[binding.slot] = binding
        self.declare("variable", name, s.line, (toks[0].col, toks[-1].end - toks[0].col),
                     lambda: binding.reads > 0, type_=type_)
        self.note(f'"{name}" is {self.describe(type_)}, from {source}')
        return binding.slot

    def ask(self, s):
        """Ask <text> and let [the] <name> (<type>) be the reply."""
        s.next()
        if s.at_words("the", "model"):
            return self.ask_model(s)
        self.no_change_here(s, "ask anything")
        usage = 'For example: "Ask "How old?" and let the age (number) be the reply."'
        question = self.question_text(s, 'Put the question in quotes: Ask "How old?" ...')
        s.expect_word("and", hint=usage, teach="ask_form")
        s.expect_word("let", hint=usage, teach="ask_form")
        name, toks, type_, type_tok = self.reply_name(s, usage, "ask_form")
        if type_ not in ASKABLE:
            s.fail(f"I can't ask for {self.describe(type_)}.", type_tok,
                   hint="A reply can be text, a number, money, a percentage, or yes or no.", teach="ask_form")
        for word in ("be", "the", "reply"):
            s.expect_word(word, hint=usage, teach="ask_form")
        self.end(s)
        slot = self.bind_reply(s, name, toks, type_)
        qf = question.fn
        again = {
            "number": "Please answer with a number, such as 7 or 2.5.",
            "money": "Please answer with an amount of money, such as $5 or $2.50.",
            "percent": "Please answer with a percentage, such as 10%.",
            YES_NO: "Please answer yes or no.",
        }

        def step(env):
            world = env.world
            prompt = qf(env)
            while True:
                try:
                    reply = world.ask(prompt)
                except EOFError:
                    reply = None
                if reply is None:  # input has ended: finish quietly, as "End the program." does
                    raise _EndProgram()
                value = read_reply(reply, type_)
                if value is not None:
                    break
                world.out(again[type_])
            env.vars[slot] = value
        return step

    # asking a model, and judging (section 7.8) ---------------------------

    def model_in_view(self, s):
        """Refuse "Ask the model ..." while a name in view starts with the word "model":
        the sentence could then ask a model, or ask a person what that name holds."""
        found = None
        if self.defined_word("model"):
            for names, what in ((self.scope.visible(), "a variable"), (self.names, "a thing"),
                                (self.workouts, "a worked-out value")):
                name = next((key for key in names if key.split(" ")[0] == "model"), None)
                if name is not None:
                    found = (name, what)
                    break
        if found is None and s.peek(1).low in self.nouns:
            found = (s.peek(1).low, "a kind")
        if found is not None:
            name, what = found
            s.fail(f'"Ask the model" could mean asking a model, or asking a person about "the {name}", which is '
                   f"{what} here.", s.peek(1), hint=f'Rename "{name}", so that "Ask the model" reads one way.',
                   teach="ambiguous_name")

    def state_value(self, s, usage, teach):
        """What a question to a model is about: a text, or a thing, handed over written
        out (runtime.thing_state). Returns env -> text."""
        value = self.expr(s)
        self.need(s, value)
        if value.type == "text":
            return value.fn
        if value.type in self.kinds:
            K = self.kinds[value.type]
            word, fields, fn = K.word, list(K.fields.items()), value.fn
            return lambda env: thing_state(fn(env), word, fields)
        s.fail_span(f"A question is about text or a thing, but {value.text} is {self.describe(value.type)}.",
                    value.span, hint='To hand over a value, fill it into a text, such as "{the count}".', teach=teach)

    def reply_shape(self, type_):
        """What a model is told about the reply wanted (Program.run's `model`), or None
        for a type a model can't be asked for."""
        plain = base(type_)
        shape = {"type": plain, "choices": None, "items": None, "optional": is_opt(type_)}
        if plain in ASKABLE:
            return shape
        if plain in self.choice_sets:
            shape.update(type="choice", choices=list(self.choice_sets[plain].displays))
            return shape
        if is_list(plain) and item_type(plain) in BASE_TYPES:
            shape.update(type="list", items=item_type(plain))
            return shape
        return None

    def ask_model(self, s):
        """Ask the model <text> [about <value>] and let [the] <name> (<type>) be the reply."""
        self.model_in_view(s)
        s.next()  # the
        s.next()  # model
        self.no_change_here(s, "ask anything")
        usage = ('For example: "Ask the model "Say what this letter wants." about the letter and let the gist '
                 '(text) be the reply."')
        question = self.question_text(s, 'Put the question in quotes: Ask the model "Which colour?" ...')
        state = self.state_value(s, usage, "model_form") if s.eat_word("about") else None
        s.expect_word("and", hint=usage, teach="model_form")
        s.expect_word("let", hint=usage, teach="model_form")
        name, toks, type_, type_tok = self.reply_name(s, usage, "model_form")
        shape = self.reply_shape(type_)
        if shape is None:
            s.fail(f"I can't ask a model for {self.describe(base(type_))}.", type_tok,
                   hint="A reply can be text, a number, money, a percentage, yes or no, one of a set of choices, or "
                        "a list of text, numbers, money or percentages.", teach="model_form")
        for word in ("be", "the", "reply"):
            s.expect_word(word, hint=usage, teach="model_form")
        self.end(s)
        slot = self.bind_reply(s, name, toks, type_, "the model's reply")
        qf, sf = question.fn, state

        def step(env):
            if env.world.model is None:
                raise no_model()
            env.vars[slot] = ask_model(env.world, qf(env), sf(env) if sf is not None else None, shape)
        return step

    def judge_ahead(self, s):
        """Is this "Judge ... about ...", rather than a verb "judge" of the program? When
        the program has its own verb "judge" and the sentence could be either, refuse it."""
        toks = s.toks
        form = (len(toks) >= 5 and toks[-2].is_word("chance", "verdict", "grade", "likelihood")
                and toks[-3].is_word("the")
                and toks[-4].is_word("be"))
        if "judge" in self.procs:
            if form:
                s.fail('This could be the verb "judge" of this program, or a sentence that asks for a judgement '
                       'with "Judge ... about ...".', toks[0], hint='Rename the verb "judge", so that each sentence '
                       "reads one way.", teach="ambiguous_name")
            return False
        return True

    def judge(self, s):
        """Judge <text> about <value> and let [the] <name> (percent) be the chance.
        Judge <text> about <value> and let [the] <name> (<set of choices>) be the verdict
            [and [the] <name> (percent) be the likelihood]."""
        s.next()
        self.no_change_here(s, "ask for a judgement")
        usage = ('For example: "Judge "Is this letter angry?" about the letter and let the anger (percent) be the '
                 'chance."')
        begins = s.peek().col
        question = self.question_text(s, 'Put the question in quotes: Judge "Is it urgent?" about ...')
        if not s.eat_word("about"):
            s.fail('A judgement is always about something: after the question comes "about" and what it is about.',
                   hint=usage, teach="judge_form")
        state_at = s.peek().col
        state = self.state_value(s, usage, "judge_form")
        state_text = " ".join(s.line.text[state_at:s.prev_end(state_at)].split())
        reads = s.line.text[begins:s.prev_end(state_at)].lower()  # the question and the state, as written
        s.expect_word("and", hint=usage, teach="judge_form")
        s.expect_word("let", hint=usage, teach="judge_form")
        name, toks, type_, type_tok = self.reply_name(s, usage, "judge_form")
        s.expect_word("be", hint=usage, teach="judge_form")
        s.expect_word("the", hint=usage, teach="judge_form")
        what = s.next()
        scale = what.is_word("grade")
        if what.is_word("chance"):
            if type_ != "percent":
                s.fail(f'A chance is a percentage, so "{name}" is written "{name} (percent)".', type_tok,
                       teach="judge_form")
            verdict = False
        elif what.is_word("verdict", "grade"):
            if type_ not in self.choice_sets:
                s.fail(f'A {what.low} is one of a set of choices, but "{name}" is {self.describe(type_)}.', type_tok,
                       hint='Describe the choices first, such as "A team is one of sales, support or returns.", '
                            "and write that set in the brackets.", teach="judge_form")
            verdict = True
        else:
            s.fail('After "be the" comes "chance", "verdict" or "grade".', what, hint=usage, teach="judge_form")
        likely = None
        if s.at_word("and"):
            and_tok = s.next()
            if not verdict:
                s.fail("A likelihood goes with a verdict or a grade: a chance is already how likely something is.",
                       and_tok, hint='To have both, ask for a verdict: "... (<set of choices>) be the verdict and the '
                                     'certainty (percent) be the likelihood."', teach="judge_form")
            lname, ltoks, ltype, ltype_tok = self.reply_name(s, usage, "judge_form", after="and", taken=name)
            if ltype != "percent":
                s.fail(f'A likelihood is a percentage, so "{lname}" is written "{lname} (percent)".', ltype_tok,
                       teach="judge_form")
            for word in ("be", "the", "likelihood"):
                s.expect_word(word, hint=usage, teach="judge_form")
            likely = (lname, ltoks)
        self.end(s)
        slot = self.bind_reply(s, name, toks, type_, "the judgement")
        lslot = self.bind_reply(s, likely[0], likely[1], "percent", "the judgement") if likely else None
        qf, sf = question.fn, state
        cset = self.choice_sets[type_] if verdict else None

        def prepare(env):
            """The judgement this sentence asks for, worked out where it stands."""
            return judge_request(qf(env), sf(env), cset, scale)

        def finish(env, found):
            """Keep (the value, the likelihood) where this sentence keeps them."""
            env.vars[slot] = found[0]
            if lslot is not None:
                env.vars[lslot] = found[1]

        def step(env):
            world = env.world
            if world.judge is None and world.judges is None:
                raise no_model()
            request = prepare(env)
            finish(env, ask_judge(world, request["question"], request["state"], cset, scale))
        # For putting consecutive judgements to the judge together (Compiler.group_judgements):
        # what the state is, as written, and which names the sentence sets and reads.
        sets = [name] + ([likely[0]] if likely else [])
        step.judging = {"state": state_text.lower(), "sets": sets, "reads": reads, "prepare": prepare,
                        "finish": finish}
        return step

    def define_meaning(self, s):
        """For a | an <set of choices>, <choice> means <text>.   What the choice means, for
        whoever judges (section 7.8). It changes nothing else."""
        s.next()  # for
        s.next()  # a, an
        stok = s.next()
        usage = 'For example: "For a team, returns means "the customer wants to send something back"."'
        cset = self.choice_names.get(stok.low) if stok.kind == "WORD" else None
        if cset is None:
            self.misspelt(s, stok, list(self.choice_names), "meaning_form")
            s.fail(f'"{stok.text}" is not a set of choices, so its choices can\'t be given meanings.', stok,
                   hint=usage, teach="meaning_form")
        s.expect_punct(",")
        toks = []
        while s.peek().kind == "WORD" and not (s.at_word("means") and s.peek(1).kind == "STRING"):
            toks.append(s.next())
        if not toks:
            s.fail("This needs one of the choices here.", hint=usage, teach="meaning_form")
        choice = " ".join(t.low for t in toks)
        if choice not in cset.choices:
            self.not_a_choice(s, toks[0], cset.name)
        s.expect_word("means", hint=usage, teach="meaning_form")
        text = s.next()
        if text.kind != "STRING" or "{" in text.text or "}" in text.text:
            s.fail("A meaning is plain text in quotes, without braces.", text, hint=usage, teach="meaning_form")
        self.end(s)
        if choice in cset.meanings:
            s.fail(f'"{cset.displays[cset.choices.index(choice)]}" already has a meaning.', toks[0],
                   hint="Give each choice one meaning, in one sentence.", teach="meaning_form")
        cset.meanings[choice] = text.value
        self.note(f'"{choice}", one of the {pluralize(cset.word)}, is handed to the judge as "{text.value}"')

    def write(self, s):
        """Write <text> to the file <text>."""
        s.next()
        value = self.expr(s)
        usage = 'For example: "Write "Hello" to the file "notes.txt"."'
        if s.at_end():
            # The value was read here, so it can be repeated: Say takes any value but a list,
            # and Write takes text.
            say = "..." if is_list(value.type) else value.text
            written = value.text if value.type == "text" else "..."
            s.fail('"Write" puts text into a file, so it needs "to the file ...".', s.toks[0],
                   hint="To show it, write: " + full_stop(f"Say {say}")
                        + f'\nTo write it to a file: Write {written} to the file "notes.txt".', teach="file_form",
                   fix=self.whole(s, full_stop(f"Say {say}")) if say != "..." else None)
        for word in ("to", "the", "file"):
            s.expect_word(word, hint=usage, teach="file_form")
        return self.file_write(s, value, append=False)

    def file_write(self, s, value, append):
        """The rest of "Write ... to the file <text>." or "Add ... to the file <text>."."""
        self.no_change_here(s, "write to a file")
        self.need(s, value)
        if value.type != "text":
            s.fail_span(f"Only text can be written to a file, but {value.text} is {self.describe(value.type)}.",
                        value.span, hint='To write a number, fill it into a text: "{the count}".', teach="fit")
        path = self.file_name(s)
        self.end(s)
        vf, pf = value.fn, path.fn

        def step(env):
            text = vf(env)
            path = pf(env)
            if env.world.testing is None:  # --test writes no files
                write_file(path, text, append)
        return self.changing(step)  # an adjective may be worked out from a file

    def example(self, s):
        s.next()
        s.next()
        s.eat_punct(",")
        cond = self.condition(s)
        self.end(s)
        fn, subject, line = cond.fn, cond.subject, s.line

        def step(env):
            world = env.world
            if not fn(env):
                hint = None
                if subject is not None:
                    hint = f"In fact, {subject.text} is {fmt(subject.fn(env), subject.type)}."
                if world.testing is not None:  # --test: note it, and go on
                    unit = getattr(line, "unit", None)
                    file = unit.file if unit is not None and unit.kind == "chapter" else None
                    world.testing.append(Example(file, line.number, line.text.strip(), False, hint))
                    return
                raise EnglishError("This example doesn't hold.", stage="run", hint=hint, teach="example")
            world.examples += 1
            if world.testing is not None:
                unit = getattr(line, "unit", None)
                file = unit.file if unit is not None and unit.kind == "chapter" else None
                world.testing.append(Example(file, line.number, line.text.strip(), True, None))
        return step

    def for_each(self, s):
        s.next()
        if not s.at_word("each"):
            self.for_advice(s)
        s.expect_word("each", hint='For example: "For each dragon:"', teach="loop_form")
        j = s.i
        while s.toks[j].kind == "WORD" and s.toks[j].low not in KEYWORDS:
            j += 1
        if j > s.i and s.toks[j].is_word("in"):
            return self.for_each_named(s, j)
        coll = self.collection(s, plural=False)
        self.end(s)
        name = self.kinds[coll.kind].word
        if self.scope.find(name):
            s.fail(
                f'There is already a "{name}" in view here, so "the {name}" would mean two things.', s.toks[2],
                hint=f'Give the loop\'s thing its own name: "For each other in {self.kinds[coll.kind].plural}:".',
                teach="ambiguous_name",
            )
        loop, body = self.loop_body(s.line.children, noun=name, binding=Binding(name, coll.kind, focus=True))
        return self.each_step(name, coll.fn, loop, body)

    def for_each_named(self, s, j):
        """For each <name> in <group, in the plural>:   or   For each <name> in <list>:"""
        toks = s.toks[s.i:j]
        s.i = j + 1  # past "in"
        name = " ".join(t.low for t in toks)
        if self.scope.find(name) or name in self.names or name in self.workouts:
            s.fail(
                f'"{name}" already means something here, so "the {name}" would mean two things.', toks[0],
                hint="Choose another name for the loop's thing.", teach="taken",
            )
        # "For each ancient rival in dragons:" reads as a filter: "For each ancient dragon:".
        group, fix = s.toks[j + 1:-1], None
        noun = self.nouns.get(group[0].low) if len(group) == 1 and group[0].kind == "WORD" else None
        if len(toks) == 2 and noun and noun[1] and toks[0].low in self.kinds[noun[0]].adjectives:
            fix = swap(s.line, toks[0].col, group[0].end, f"{toks[0].text} {self.kinds[noun[0]].word}")
        self.not_an_adjective(s, toks, "the name of a loop's thing", fix)
        self.made(name, "a loop's thing", s.line)
        items = None
        if not (s.at_word("all") or s.peek().is_word(*POSSESSIVES) or self.noun_ahead(s)):
            mark = (s.i, len(self.notes))
            try:
                items = self.expr(s)
            except EnglishError:
                items = None
            if items is not None and s.at_end():
                if not is_list(items.type):
                    s.fail_span(f"{cap(items.text)} is {self.describe(items.type)}, not a group of things or a list.",
                                items.span, teach="list")
            else:
                items = None
                s.i = mark[0]
                del self.notes[mark[1]:]
        if items is not None:
            self.need(s, items)
            item = item_type(items.type)
            binding = Binding(name, item, focus=item in self.kinds)
            get = items.fn
        else:
            coll = self.collection(s, plural=True)
            self.end(s)
            binding = Binding(name, coll.kind, focus=True)
            get = coll.fn
        self.kind_named(s, name, binding.type, (toks[0].col, toks[-1].end), "loop's thing")
        self.defines("loop name", name, s.line, toks[0].col, toks[-1].end - toks[0].col, type_=binding.type,
                     span=block_span(s.line.children) or (s.line.number, s.line.number))
        loop, body = self.loop_body(s.line.children, noun=name, binding=binding)
        return self.each_step(name, get, loop, body, group=items is None)

    def each_step(self, name, items, loop, body, group=True):
        """The loop itself. A group is settled when the loop starts, but a thing
        removed before its turn comes is not visited."""
        run = self.run_block

        def step(env):
            for thing in items(env):
                if group and thing.removed:
                    continue
                inner = Env(env)
                inner.vars[name] = thing
                try:
                    run(body, inner)
                except _SkipRound as signal:
                    if signal.loop != loop:
                        raise
                except _StopLoop as signal:
                    if signal.loop != loop:
                        raise
                    break
        return step

    def repeat(self, s):
        s.next()
        count = self.expr(s)
        self.need(s, count)
        if count.type != "number":
            s.fail_span(f"I need a plain number of times, but {count.text} is {self.describe(count.type)}.", count.span,
                        teach="fit")
        s.expect_word("times", hint='For example: "Repeat 3 times:"', teach="loop_form")
        self.end(s)
        loop, body = self.loop_body(s.line.children)
        fn, run = count.fn, self.run_block

        def step(env):
            n = fn(env)
            if n.denominator != 1 or n < 0:
                raise EnglishError(f"I can't repeat something {fmt(n, 'number')} times.", stage="run", recoverable=True,
                                   hint="Repeat takes a whole number that is not negative.", teach="count")
            for _ in range(int(n)):
                try:
                    run(body, env)
                except _SkipRound as signal:
                    if signal.loop != loop:
                        raise
                except _StopLoop as signal:
                    if signal.loop != loop:
                        raise
                    break
        return step

    def while_loop(self, s):
        s.next()
        mark = s.i

        def head():  # checked before every round, so compiled with what is known then
            s.i = mark
            found = self.condition(s)
            self.end(s)
            return found
        loop, body, found = self.loop_body(s.line.children, head=head)
        cond = found.fn
        run = self.run_block

        def step(env):
            turns = 0
            while cond(env):
                turns += 1
                if turns > LOOP_LIMIT:
                    raise EnglishError(
                        f"This loop has gone round {LOOP_LIMIT:,} times, so I stopped it.", stage="run",
                        hint="Look at what its condition tests: something in the block has to change it.",
                        teach="loop_limit",
                    )
                try:
                    run(body, env)
                except _SkipRound as signal:
                    if signal.loop != loop:
                        raise
                except _StopLoop as signal:
                    if signal.loop != loop:
                        raise
                    break
        return step

    def call(self, s):
        """A verb used as a sentence. A verb with several shapes (define_procedure) is
        read with each; the shape is the one whose linking words the sentence has."""
        vtok = s.next()
        proc = self.procs[vtok.low]
        if len(proc.shapes) == 1:
            return self.call_shape(s, vtok, proc)
        start, notes, present = s.i, len(self.notes), self.present
        found, errors = [], []
        for shape in proc.shapes:
            s.i, self.present = start, present
            del self.notes[notes:]
            try:
                self.call_shape(s, vtok, shape)
                found.append(shape)
            except EnglishError as error:
                errors.append(error)
        s.i, self.present = start, present
        del self.notes[notes:]
        if len(found) == 1:
            return self.call_shape(s, vtok, found[0])
        if found:
            readings = "\n".join(f"  ({k}) {shape.usage()}" for k, shape in enumerate(found, 1))
            s.fail(f'This sentence fits more than one shape of "{proc.verb}":', vtok, hint=readings,
                   teach="ambiguous_name")
        raise max(errors, key=lambda error: (error.col or 0))

    def call_shape(self, s, vtok, proc):
        if self.verb is not proc:
            proc.used = True
        if self.workout is not None:
            s.fail(
                f'Working something out can\'t change anything, and "{proc.verb}" is a verb.', vtok,
                hint='A "To work out" block may use other worked-out values, but not verbs.', teach="working_out",
            )
        by_prep = {p.prep: p for p in proc.params}
        usage = "It goes: " + proc.usage()
        args = {}

        def take(param):
            if s.at_end():
                s.fail(f'The sentence stops too soon: "{proc.verb.capitalize()}" needs {article(param.name)} here.',
                       hint=usage, teach="verb_roles")
            self.choice_expected(s, param.type)
            value = (self.group_as_list(s) if is_list(param.type) else None) or self.expr(s)
            if not self.fits(value.type, param.type):
                if base(value.type) == base(param.type):
                    self.need(s, value)
                s.fail_span(
                    f'"{proc.verb.capitalize()}" wants {article(param.name)} here, '
                    f"but {value.text} is {self.describe(value.type)}.", value.span, hint=usage, teach="fit",
                )
            args[param.name] = value

        if None in by_prep:
            if s.at_end() or (s.peek().kind == "WORD" and s.peek().low in by_prep):
                s.fail(f'{proc.verb.capitalize()} what? "{proc.verb.capitalize()}" needs {article(by_prep[None].name)} '
                       "straight after it.", hint=usage, teach="verb_roles")
            take(by_prep[None])
        while not s.at_end():
            ptok = s.next()
            param = by_prep.get(ptok.low) if ptok.kind == "WORD" else None
            if param is None:
                links = [p.prep for p in proc.params if p.prep]
                if ptok.kind == "WORD" and ptok.low in PREPOSITIONS and links:
                    s.fail(f'"{proc.verb.capitalize()}" was taught with {join_words(f"{chr(34)}{w}{chr(34)}" for w in links)}, '
                           f'not "{ptok.text}".', ptok, hint=usage, teach="verb_roles",
                           fix=s.replace(ptok, links[0]) if len(links) == 1 else None)
                s.fail(f'I don\'t know how "{ptok.text}" fits with "{proc.verb}".', ptok, hint=usage,
                       teach="verb_roles")
            if param.name in args:
                s.fail(f'"{ptok.text}" appears twice.', ptok, hint=usage, teach="verb_roles")
            take(param)
        missing = [p for p in proc.params if p.name not in args]
        if missing:
            wanted = join_words(f"{p.prep} {article(p.name)}" for p in missing)
            s.fail(f'"{proc.verb.capitalize()}" is missing something: {wanted}.', hint=usage, teach="verb_roles")
        self.note(
            f'"{proc.verb}" → ' + ", ".join(f"{name} = {value.text}" for name, value in args.items())
        )
        self.forget_after_verb()
        fns = [(name, value.fn) for name, value in args.items()]
        line = s.line

        def step(env):
            world = env.world
            frame = Env(world.globals)
            for name, fn in fns:
                frame.vars[name] = fn(env)
            world.depth += 1
            try:
                if world.depth > CALL_LIMIT:
                    raise EnglishError(
                        f'"{proc.verb}" keeps calling itself; I stopped after {CALL_LIMIT} levels.', stage="run",
                        hint="Look for the case where it can finish without using itself.", teach="depth",
                    )
                for inner in proc.body:
                    inner(frame)
            except _StopVerb:
                pass
            except EnglishError as error:
                if error.line is not None and error.line is not line and len(error.trace) < 5:
                    error.trace.append(line)
                raise
            finally:
                world.depth -= 1
        return step


# ------------------------------------------------------------------ program


class Program:
    def __init__(self, steps, notes, compiler):
        self.steps = steps
        self.notes = notes
        self.compiler = compiler

    def run(self, out=print, ask=None, trace=None, model=None, judge=None, judges=None, testing=False):
        """Carry out the program. `ask` takes a question and returns the reply,
        or None (or raises EOFError) when input has ended; by default it reads
        a line from standard input.

        `model` and `judge` answer "Ask the model" and "Judge" (section 7.8):
        model(question, state, shape, complaint) -> the reply as text, or None for
        no reply; judge(question, state, choices, meanings) -> a chance from 0 to 1
        when `choices` is None, otherwise {choice: chance}. `judges([request, ...])`
        answers several judgements at once, each request being {"question", "state",
        "choices", "meanings", "scale"}, with a list of what `judge` would give for each.
        Without them, every question to a model is the problem "no model".

        `trace`, if given, is called before each sentence is carried out, with
        (depth, file, line, sentence, cause): file is None for the program's own
        file, and cause is None except for the "Whenever" sentence of a reaction or
        a settled block, where it says what set it off ("Adder became pressed").

        If the sentences run to their end, each library's `live(world)` is
        called; then, however the run ended, each library's `finish(world)`.
        Returns the World, which a live library may still bring events into
        (World.event)."""
        world = World(out, ask, model, judge, judges)
        world.trace = trace
        if testing:
            world.testing = []
        for name in self.compiler.libraries:
            world.libraries[name] = {}
        world.rules = {}  # kind -> the rules stated so far: a rule holds from its sentence on
        limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(limit, RECURSION_LIMIT))  # each English call costs several Python frames
        to_the_end = False  # did the sentences run to their end, with no problem and no "End the program."?
        failures = []
        try:
            world.busy = True  # world.event must wait until the sentences are done
            with no_digit_limit():
                for step in self.steps:
                    world.changed = False
                    step(world.globals)
                    if world.settlers or world.keepers:  # each top-level sentence is a turn
                        world.settle(step.line)
            to_the_end = True
        except _EndProgram:
            pass
        except RecursionError:
            raise EnglishError("This program nests more deeply than I can follow.", stage="run",
                               teach="depth") from None
        finally:
            sys.setrecursionlimit(limit)
            world.busy = False
            world.ended = not to_the_end
            # A library that goes on working after the sentences starts here; then
            # every library is told the run is over, however it ended. If the run
            # failed, that failure is what propagates, never a failure to finish.
            if to_the_end and not testing:
                failures = self.call_libraries(world, "live", "could not go on")
                if failures:
                    world.ended = True
            failures += self.call_libraries(world, "finish", "could not finish")
        if failures:
            raise EnglishError("A library " + "; ".join(failures), stage="run",
                               hint="This is a fault in the library, not in your program.", teach="library_run")
        return world

    def test(self):
        """Carry out the program with nothing said, nothing asked (as if input had
        ended at once), no model listening and no file written, and give back every "For example" it
        reached, in order, as runtime.Example: one that does not hold is noted, and
        the program goes on. A problem that stops the program is raised as usual."""
        world = self.run(out=lambda text: None, ask=lambda question: None, testing=True)
        return world.testing

    def call_libraries(self, world, hook, failed):
        """Call each library's `hook(world)`, if it has one. Returns what went wrong."""
        failures = []
        for name, (module, _) in self.compiler.libraries.items():
            fn = getattr(module, hook, None)
            if not callable(fn):
                continue
            try:
                fn(world)
            except Exception as error:  # noqa: BLE001 - reported (or set aside) above
                failures.append(f"{failed}: the {name} library: {type(error).__name__}: {error}")
        return failures


def compile_source(source, folder=None, name=None, read=None):
    """Compile a whole program. Raises EnglishError; runs nothing.

    `folder` is where the chapters it uses are looked for (by default the
    current directory), and `name` is what messages call its file. `read`, if
    given, takes the path of a chapter and gives its text, or None to read it
    from the disk: for a chapter that is open, unsaved, in an editor."""
    with no_digit_limit():  # a long number written in the program is read in full
        compiler = Compiler(folder, name, read)
        lines = read_source(source, unit=compiler.main)
        steps = compiler.program(lines)
    return Program(steps, compiler.notes, compiler)


def compile_file(path):
    """Compile the program in a file; its chapters are looked for beside it."""
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    return compile_source(source, folder=path.parent, name=str(path))

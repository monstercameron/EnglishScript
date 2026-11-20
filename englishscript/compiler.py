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
from .lexer import QUESTION_WORDS, EnglishError, Token, chapter_of, read_source, swap, tokenize
from .runtime import (
    RECURSION_LIMIT, Env, Reaction, Thing, World, _EndProgram, _Signal, alive, fmt, no_digit_limit, read_file,
    read_number, read_reply, split_lines, write_file,
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
LOOP_LIMIT = 10_000
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
        raise
    except _Signal:
        raise
    except Exception as error:  # noqa: BLE001 - a library's own fault, reported in English
        raise EnglishError(
            f"The {lib} library failed: {type(error).__name__}: {error}", stage="run",
            hint=f"This is a fault in the {lib} library, not in your program.",
        ) from None


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
    """A registry as one file sees it. Everything is kept in `all`, so that a
    name still has one meaning in the whole program; only what the file may
    say shows through."""

    def __init__(self, visible):
        self.all = {}
        self.visible = visible  # (key, value) -> bool

    def __getitem__(self, key):
        value = self.all[key]
        if not self.visible(key, value):
            raise KeyError(key)
        return value

    def __iter__(self):
        return (key for key, value in list(self.all.items()) if self.visible(key, value))

    def __len__(self):
        return sum(1 for _ in self)

    def __setitem__(self, key, value):
        self.all[key] = value


@dataclass
class Kind:
    name: str
    plural: str
    line: object
    fields: dict = field(default_factory=dict)  # name -> type
    props: dict = field(default_factory=dict)  # name -> Prop (a View, from define_kind)
    adjectives: dict = field(default_factory=dict)  # name -> Adj (a View, from define_kind)
    rules: list = field(default_factory=list)  # [Rule]
    unit: object = None  # the file that described it


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
    used: bool = False  # for the linter's "never used"
    unit: object = None


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

    def usage(self):
        return " ".join([f"the {self.name}"] + [f"{p.prep} {p.slot()}" for p in self.params])


@dataclass
class Coll:
    kind: str
    fn: object  # env -> [Thing]


class Binding:
    __slots__ = ("name", "type", "focus", "let", "fixed", "reads", "unit")

    def __init__(self, name, type_, focus=False, let=False, fixed=False):
        self.name = name
        self.type = type_
        self.focus = focus  # can a pronoun refer to it?
        self.let = let  # can it be changed with Set/Add/...?
        self.fixed = fixed  # made with "always"
        self.reads = 0  # how many sentences read it, for the linter
        self.unit = None  # for a top-level variable: the file that made it


class Scope:
    def __init__(self, parent=None):
        self.parent = parent
        self.names = {}
        self.shown = None  # for the top level: binding -> may this file say it?

    def find(self, name):
        scope = self
        while scope is not None:
            b = scope.names.get(name)
            if b is not None and (scope.shown is None or scope.shown(b)):
                return b
            scope = scope.parent
        return None

    def visible(self):
        seen, scope = {}, self
        while scope is not None:
            for name, b in scope.names.items():
                if scope.shown is None or scope.shown(b):
                    seen.setdefault(name, b)
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
                 "key", "declared", "check", "nt", "nf")

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
    def __init__(self, folder=None, name=None):
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
        self.kinds = {}  # every kind; kind_visible says which a file may name
        self.nouns = View(lambda word, entry: self.kind_visible(entry[0]))  # word -> (kind, is_plural)
        self.names = View(lambda key, entry: self.can_see(self.name_units[key], key))  # -> (display, kind)
        self.name_units = {}  # lowercased instance name -> the Unit that made it
        self.procs = View(lambda key, proc: self.can_see(proc.unit, key))
        self.workouts = View(lambda key, w: self.can_see(w.unit, key))
        self.member_names = {"name"}
        self.adjective_names = set()
        self.globals = Scope()
        self.globals.shown = lambda b: b.unit is None or self.can_see(b.unit, b.name)
        self.scope = self.globals
        self.notes = []
        self.line = None
        self._uid = 0
        # Where the sentence being compiled sits.
        self.verb = None  # the verb whose block this is, if any
        self.workout = None  # the worked-out value whose block this is, if any
        self.loops = []  # loops around the sentence: [{"id", "noun"}]
        # For the linter (englishscript/linter.py). Without it, a refused sentence is raised.
        self.lint = None  # the linter's collector, which records problems and carries on
        self.declared = []  # (what, name, line, column, width, is it used?) for "never used"
        self.libraries = {}  # name -> (module, the "Use" line), in the order they were used
        self.library = None  # (name, module) while a library's SOURCE is being compiled
        self.present = NONE  # keys known not to be nothing at this point
        # Does the program (or a library it uses) say "Whenever"? Then a reaction may
        # follow any sentence that changes things: such sentences are watched while
        # running, and checks for nothing don't survive them. Set by `program`.
        self.reactive = False

    # ------------------------------------------------------------- helpers

    def declare(self, what, name, line, at, used):
        """Remember a name the program made, so the linter can say if it is never used.
        Only names of the main file: the other files are not its business."""
        if not line.library and getattr(line, "unit", None) in (None, self.main):
            self.declared.append((what, name, line, at[0], at[1], used))

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
        return K is not None and self.can_see(K.unit, kind)

    def owners(self):
        """Every name defined anywhere in the program -> (the unit that defined it,
        the name it is shared under, what it is)."""
        found = {}

        def put(name, unit, shared, what):
            found.setdefault(name, (unit, shared, what))
        for kind, K in self.kinds.items():
            put(kind, K.unit, kind, "kind")
            put(K.plural, K.unit, kind, "kind")
        for key, unit in self.name_units.items():
            put(key, unit, key, "thing")
        for verb, proc in self.procs.all.items():
            put(verb, proc.unit, verb, "verb")
        for name, w in self.workouts.all.items():
            put(name, w.unit, name, "worked-out value")
        for name, b in self.globals.names.items():
            if b.unit is not None:
                put(name, b.unit, name, "variable")
        for K in self.kinds.values():
            for name, prop in K.props.all.items():
                put(name, prop.unit, name, "property")
        return found

    def unseen(self, name, unit, shared, kind=None):
        """(message, hint) for a name that exists but may not be said in this file."""
        shown = f'"{name}"' if kind is None else f'"{name}" for {article(kind)}'
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
                        "A file can use the chapters beside it, and those of a book in its own folder.")
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
        if os.path.normcase(str(unit.folder.parent)) == os.path.normcase(str(here)):
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
        adj = K.adjectives.all.get(tok.low) if tok.kind == "WORD" else None
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
            s.fail("I understood the sentence up to here, but not this part.")

    def uid(self):
        self._uid += 1
        return self._uid

    def match_words(self, s, names, offset=0):
        """Longest of `names` (space-separated words) found at the cursor."""
        best = None
        for name in names:
            parts = name.split(" ")
            if best and len(parts) <= best[1]:
                continue
            if all(s.peek(offset + k).is_word(p) for k, p in enumerate(parts)):
                best = (name, len(parts))
        return best

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
        if tok.kind == "WORD" and self.kind_visible(tok.low):
            return self.kinds[tok.low]
        if tok.kind != "WORD":
            s.fail('This sentence needs a kind here, such as "dragon".', tok, hint=self.kinds_hint(),
                   teach="unknown_kind")
        self.hidden_word(s, tok)
        noun = self.nouns.get(tok.low)
        if noun and noun[1]:  # "There is a dragons ..."
            s.fail(f'After "a", write one: "{article(noun[0])}", not "a {tok.text}".', tok,
                   teach="number_agreement", fix=s.replace(tok, noun[0]))
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
        return [kind for kind in self.kinds if self.kind_visible(kind)]

    def type_name(self, s, tok, also=None):
        if tok.kind == "WORD" and (tok.low in BASE_TYPES or self.kind_visible(tok.low) or tok.low == also):
            return tok.low
        self.hidden_word(s, tok)
        known = list(BASE_TYPES) + self.visible_kinds() + ([also] if also and also not in self.kinds else [])
        if tok.kind == "WORD" and tok.low in self.nouns and self.nouns[tok.low][1]:
            single = self.nouns[tok.low][0]
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
            else:
                self.hidden_word(s, tok)
                plurals = list(LIST_PLURALS) + [self.kinds[k].plural for k in self.visible_kinds()]
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
    def fresh(self, verb=None, workout=None):
        """Compile a definition: it must not lean on where it happens to be written."""
        saved = (self.verb, self.workout, self.loops, self.present)
        self.verb, self.workout, self.loops, self.present = verb, workout, [], NONE
        try:
            yield
        finally:
            self.verb, self.workout, self.loops, self.present = saved

    def subject_scope(self, kind):
        scope = Scope(self.globals)
        scope.names[kind] = Binding(kind, kind, focus=True)
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
        hidden = self.match_words(s, list(K.fields) + list(K.props.all), offset)
        if hidden and (self.chapters or self.library_units):
            name = hidden[0]
            prop = K.props.all.get(name)
            unit, shared = (prop.unit, name) if prop is not None else (K.unit, kind)
            if not self.can_see(unit, shared):
                message, hint = self.unseen(name if prop is not None else kind, unit, shared)
                if prop is None:
                    message = f'The properties of {article(kind)} come with the kind. ' + message
                s.fail(message, tok, hint=hint, teach="shared")
        members = self.member_list(kind)
        self.misspelt(s, tok, members, "unknown_property")
        what = f'no "{tok.text}"' if tok.kind == "WORD" else "nothing by that description"
        s.fail(
            f"{article(kind).capitalize()} has {what}.", tok,
            hint=f"{article(kind).capitalize()} has: " + ", ".join(some_of(members, tok.text)) + ".",
            teach="unknown_property",
        )

    def member(self, s, owner, match, start=None):
        name, count = match
        for _ in range(count):
            s.next()
        return self.stamp(s, self.member_expr(owner, name), owner.span[0] if start is None else start)

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
            return f"No adjective has been defined for {article(kind)} yet."
        return f"Adjectives for {article(kind)}: " + ", ".join(names) + "."

    def unknown_adjective(self, s, tok, kind, also=()):
        """Refuse a word that stands where an adjective of `kind` belongs. `also` are
        other words that could stand there (the names of things of that kind)."""
        self.hidden_adjective(s, tok, self.kinds[kind])
        self.misspelt(s, tok, list(self.kinds[kind].adjectives) + list(also), "unknown_adjective")
        hint = self.adjectives_hint(kind, tok.text)
        if tok.kind == "WORD" and tok.low not in KEYWORDS and not self.defined_word(tok.low):
            hint = f'Define it first: "{article(kind).capitalize()} is {tok.text} when ...".\n' + hint
        s.fail(f'I don\'t know what "{tok.text}" means for {article(kind)}.', tok, hint=hint,
               teach="unknown_adjective")

    # --------------------------------------------------------- expressions

    def expr(self, s):
        left = self.sum(s)
        while s.at_words("or", "else"):
            s.next()
            s.next()
            left = self.or_else(s, left, self.sum(s))
        return left

    def or_else(self, s, left, right):
        if not is_opt(left.type):
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
            if inner.type not in ("number", "money"):
                s.fail_span(f"I can't make {self.describe(inner.type)} negative: only a number or money can be.",
                            inner.span, teach="arith")
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
            if lt == rt and lt in ("number", "money"):
                result = lt
        elif op == "*":
            if lt == rt == "number":
                result = "number"
            elif {lt, rt} == {"money", "number"}:
                result = "money"
        else:
            if lt == rt and lt in ("number", "money"):
                result = "number"
            elif lt == "money" and rt == "number":
                result = "money"
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
            check = f"{cap(right.text)} was {zero}. Check it first: If {right.text} is not {zero}:"

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
                cond = self.condition(s).fn
                expr = Expr(YES_NO, lambda env: bool(cond(env)))
            elif tok.low in ("a", "an") and s.peek(1).is_word("new"):
                s.fail(
                    'A new thing can only be made as the whole value of "Let", or with "There is a new ...".', tok,
                    hint='For example: "Let the chick be a new dragon whose age is 0."', teach="new_thing",
                )
            else:
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
        name = b.name
        expr = Expr(b.type, lambda env: env.get(name))
        expr.key = ("var", name)
        return expr

    def variable(self, s, match):
        name, count = match
        for _ in range(count):
            s.next()
        b = self.scope.find(name)
        b.reads += 1
        expr = Expr(b.type, lambda env: env.get(name))
        expr.key = ("var", name)
        if b.let:
            expr.target = ("var", name)
        elif b.fixed:
            expr.target = ("fixed", name)
        return self.settle(expr)

    def bare_name(self, s):
        match = self.match_words(s, self.names)
        if match:
            key, count = match
            for _ in range(count):
                s.next()
            expr = Expr(self.names[key][1], lambda env: env.world.named[key])
            expr.key = ("thing", key)
            return expr
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
            s.fail(
                f'Which {kind}? Nothing here says which one "{shown}" is.', tok,
                hint=f'{hint} go through them with "For each {kind}:".', teach="the_noun",
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
            coll = self.collection(s, plural=True)
            cf = coll.fn
            return Expr("number", lambda env: Fraction(len(cf(env))))
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
            return Expr("text", lambda env: env.get(PROBLEM))
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
                coll = self.collection(s, plural=True)
                found = self.getter(coll.kind, name)
                if not found:
                    s.fail(f'{article(coll.kind).capitalize()} has no "{name}" to add up.', name_tok,
                           hint=f"{article(coll.kind).capitalize()} has: "
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
            owner = self.primary(s)
            if base(owner.type) not in self.kinds:
                s.fail_span(f"{cap(owner.text)} is {self.describe(owner.type)}, so it has no {name}.", owner.span,
                            teach="props_of")
            if not self.getter(base(owner.type), name):
                kind = base(owner.type)
                s.fail(
                    f'{article(kind).capitalize()} has no "{name}".', name_tok,
                    hint=f"{article(kind).capitalize()} has: " + ", ".join(some_of(self.member_list(kind), name)) + ".",
                    teach="unknown_property",
                )
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
        by_prep = {p.prep: p for p in w.params}
        usage = "It goes: " + w.usage() + "."
        args = {}
        while s.peek().kind == "WORD" and s.peek().low in by_prep and by_prep[s.peek().low].name not in args:
            ptok = s.next()
            param = by_prep[ptok.low]
            if s.at_end():
                s.fail(f'After "{ptok.text}" comes {article(param.name)}.', hint=usage, teach="verb_roles")
            self.no_group_for_list(s, param.type, f'"The {w.name}" wants')
            value = self.primary(s)  # one value; arithmetic in a role needs brackets
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
        """Refuse 'all horses', 'tired horses' or 'horses' where a list is wanted: not built yet."""
        if is_list(want) and (s.at_word("all") or self.noun_ahead(s)):
            s.fail(
                f"{lead} {self.describe(want)}, but a group of things can't be given where a list is expected yet.",
                hint='Lists come from "the words of", "the lines of" and files. To work on a group, '
                     'go through it with "For each" instead.', teach="list",
            )

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
            if raw[i] != "{":
                plain.append(raw[i])
                i += 1
                continue
            k = raw.find("}", i)
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

    def collection(self, s, plural):
        """'grumpy dragons', 'treasures of Smaug', 'its treasures', 'Smaug's treasures'."""
        start = s.peek().col
        owner = None
        tok = s.peek()
        if plural and tok.kind == "WORD" and tok.low in POSSESSIVES:
            s.next()
            owner = self.stamp(s, self.pronoun(s, tok), start)
            owner.text = f"the {owner.type}"  # reads better than "its" in notes and errors
        else:
            if plural:
                s.eat_word("all")
            if not self.noun_ahead(s):
                tok = s.peek()
                singulars = self.visible_kinds()
                plurals = [self.kinds[k].plural for k in singulars]
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
                    s.fail(f'I don\'t know the kind "{tok.text}".', hint=self.kinds_hint(tok.text),
                           teach="unknown_kind")
                starts_value = tok.kind != "WORD" or (
                    tok.low in ("the",) + POSSESSIVES + PRONOUNS or self.match_words(s, self.names)
                    or self.match_words(s, self.scope.visible()) or tok.low in KEYWORDS)
                if not starts_value:
                    self.hidden_here(s)
                    self.misspelt(s, tok, plurals, "unknown_kind")
                    s.fail(f'I don\'t know the kind "{tok.text}".',
                           hint="A group is written in the plural: " + ", ".join(some_of(plurals, tok.text)) + "."
                           if plurals else "No kind has been described yet.", teach="unknown_kind")
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
        noun = s.next()
        if plural and not is_plural:
            s.fail(f'More than one is meant here, so write "{K.plural}".', noun, teach="number_agreement",
                   fix=s.replace(noun, K.plural))
        if not plural and is_plural:
            s.fail(f'"For each" takes them one at a time, so write "{K.name}".', noun, teach="number_agreement",
                   fix=s.replace(noun, K.name))
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
        whose = None
        if s.at_word("whose"):
            s.next()
            match = self.match_member(s, kind)
            if not match:
                self.no_member(s, kind)
            hidden = f"\0each{self.uid()}"
            each = Expr(kind, lambda env: env.get(hidden))
            each.span = (s.peek().col, s.peek().col)
            left = self.member(s, each, match)
            whose = (hidden, self.comparison_rest(s, left).fn)

        owner_fn = owner.fn if owner is not None else None

        def fn(env):
            world = env.world
            items = world.things.get(kind, [])
            if link:
                mine = alive(owner_fn(env))
                items = [x for x in items if x.fields[link] is mine]
            for test in tests:
                items = [x for x in items if test(world, x)]
            if whose:
                hidden_name, cond = whose
                kept = []
                for x in items:
                    inner = Env(env)
                    inner.vars[hidden_name] = x
                    if cond(inner):
                        kept.append(x)
                items = kept
            return list(items)
        return Coll(kind, fn)

    def relation(self, s, K, owner, noun):
        """Which field makes a K 'of' the owner? There must be exactly one."""
        links = [f for f, t in K.fields.items() if base(t) == owner.type]
        phrase = f"{K.plural} of {owner.text}"
        if len(links) == 1:
            self.note(f'"{phrase}" → {K.plural} whose {links[0]} is {owner.text}')
            return links[0]
        if not links:
            s.fail(
                f"I don't know how {article(K.name)} belongs to {article(owner.type)}: no property of "
                f"{article(K.name)} is {article(owner.type)}.", noun,
                hint=f'Give it a property that points at one, such as "{article(K.name).capitalize()} has an owner '
                     f'({owner.type})."',
                teach="of_link",
            )
        ways = len(links) if len(links) > 2 else "two"
        readings = "\n".join(f"  ({k}) {K.plural} whose {link} is {owner.text}" for k, link in enumerate(links, 1))
        s.fail(
            f'"{phrase}" can be read {ways} ways, because {article(K.name)} is tied to '
            f"{article(owner.type)} by its {join_words(links)}:", noun,
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
            parts = [self.cond_atom(s)]
            ops = []
            while s.at_word("and", "or"):
                op = s.next()
                if ops and op.low != ops[0].low:
                    self.mixed(s, start, ops[-1], op)
                ops.append(op)
                self.present = self.present | (parts[-1].nt if op.low == "and" else parts[-1].nf)
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
        words = re.findall(r"[A-Za-z]\w*", expr.text)
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
        if not is_opt(declared):
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
        if s.at_word("nothing"):
            s.next()
            if not is_opt(left.type):
                s.fail_span(f"{cap(left.text)} can't be nothing here, so there is nothing to check.", left.span,
                            teach="nothing_checks")
            lf = left.fn
            cond = Expr("truth", lambda env: lf(env) is None)
            if left.key is not None:
                cond.nf = frozenset([left.key])
            return cond
        self.need(s, left)
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
        return self.compare(s, "=", left, self.expr(s))

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
        check = f"{cap(right.text)} was 0. Check it first: If {right.text} is not 0:"

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
        return cond

    # -------------------------------------------------------------- blocks

    def block(self, lines, scope=None):
        saved = self.scope
        self.scope = scope if scope is not None else Scope(saved)
        try:
            steps, i = [], 0
            leaving, warned = False, False  # has a sentence that always leaves been seen?
            while i < len(lines):
                line = lines[i]
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
                leaving = leaving or step.leaves
            return steps
        finally:
            self.scope = saved

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
        def step(env):
            world = env.world
            if not world.reactions:  # no "Whenever" has been reached yet
                fn(env)
                return
            before = world.noting()
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
            words = self.chapter_words(line.tokens[2:]) if first.is_word("use") and folder is not None else None
            if words is not None:
                path = self.chapter_file(folder, *words)
                key = os.path.normcase(os.path.abspath(path))
                if key in seen:
                    continue
                seen.add(key)
                try:
                    with open(path, encoding="utf-8") as handle:
                        inner = read_source(handle.read(), problems=[])
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
            try:
                fn(env)
            except EnglishError as error:
                if error.line is None:
                    error.line = line
                raise
        step.answers = getattr(fn, "answers", False)
        step.leaves = getattr(fn, "leaves", False)
        return step

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

    def loop_body(self, lines, noun=None, binding=None):
        """Compile the block of a loop. Returns (loop id, steps).

        A loop's block runs again after its own last sentence, so it may not
        rely on anything that it changes further down. The block is compiled
        once to see what it changes, and again without relying on those.
        """
        loop = {"id": self.uid(), "noun": noun}
        before = self.present
        mark = len(self.notes)
        self.loops.append(loop)
        try:
            for _ in range(3):
                start = self.present
                # What is known at each "Skip" and "Stop repeating" aimed at this
                # loop: a round can also end there, part way through the block.
                loop["skips"], loop["stops"] = [], []
                scope = Scope(self.scope)
                if binding is not None:
                    scope.names[binding.name] = binding
                steps = self.block(lines, scope)
                end = self.present
                for known in loop["skips"]:
                    end = end & known
                if start <= end:
                    break
                self.present = start & end
                del self.notes[mark:]
        finally:
            self.loops.pop()
        for known in loop["stops"]:
            end = end & known
        self.present = before & end
        return loop["id"], steps

    @staticmethod
    def is_if_fails(line):
        toks = line.tokens
        return len(toks) >= 3 and toks[0].is_word("if") and toks[1].is_word("that") and toks[2].is_word("fails")

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
        fallback = self.block(fails_line.children, scope)
        self.present = before & after_try & self.present
        run = self.run_block

        def step(env):
            restore = env.world.snapshot(env)
            try:
                run(tried, env)
            except EnglishError as error:
                if not error.recoverable:
                    raise
                restore()
                inner = Env(env)
                inner.vars[PROBLEM] = error.message
                for inner_step in fallback:
                    inner_step(inner)
        step.answers = self.answers(tried) and self.answers(fallback)
        step.leaves = self.leaves(tried) and self.leaves(fallback)
        return i + 2, step

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
            if nxt.is_word("has"):
                definition = self.define_kind
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
        elif word == "this" and s.peek(1).is_word("chapter"):
            definition = self.shares_sentence
        if definition:
            if not top:
                s.fail("This definition belongs at the top level, not inside a block.",
                       hint="Move it out of the block, and start it at the left edge.", teach="top_level")
            if word == "to" and self.done_by_library(line):
                return self.define_outside(s)
            self.needs_block(s, word in ("to", "whenever"))
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
        if word in simple:
            self.needs_block(s, False)
            return simple[word](s)
        if word in self.procs:
            self.needs_block(s, False)
            return self.call(s)
        proc = self.procs.all.get(word)
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
        starts = list(simple) + list(blocks) + ["if", "try", "otherwise", "use", "whenever"]
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
                hints.append(f'Teach it to me first, with a heading such as "To {word} {article(kind)}:" '
                             "and an indented block.")
            else:
                hints.append(f'Teach it to me first: "To {word} ...:" followed by an indented block.')
        s.fail(f'I don\'t know the verb "{first.text}".', first, hint="\n".join(hints) or None, teach="unknown_verb")

    def what_it_is(self, s):
        """If the sentence starts with a name rather than a verb: (what it is, as "a
        dragon" or "an adjective", and how many words it takes); otherwise None."""
        match = self.match_words(s, self.names)
        if match:
            return article(self.names[match[0]][1]), match[1]
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

    def defined_word(self, word):
        """Is `word` part of a name the program has given a meaning?"""
        names = (
            list(self.scope.visible()) + list(self.names) + list(self.procs) + list(self.workouts)
            + list(self.nouns) + list(self.member_names) + list(self.adjective_names)
        )
        return any(word in name.split(" ") for name in names)

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
        if name in self.kinds:
            self.described_again(s, ktok, self.kinds[name])
        s.next()  # has
        K = Kind(name, pluralize(name), s.line)
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
            if fname in self.workouts.all:
                s.fail(f'"{fname}" is already something that is worked out'
                       f'{self.elsewhere(self.workouts.all[fname].unit)}, so a property can\'t share its name.', toks[0],
                       teach="taken")
            if not s.eat_punct("("):
                s.fail(
                    f'What sort of value is "{fname}"?', toks[0],
                    hint=f'Say so in brackets, e.g. "{article(fname)} (money)".\n'
                    "Types: number, money, text, percent, or a kind you have described.", teach="kind_form",
                )
            K.fields[fname] = self.bracket_type(s, also=name)
            if base(K.fields[fname]) == YES_NO:
                s.fail(
                    f'A property can\'t be yes or no. A yes-or-no fact about {article(name)} is an adjective.', toks[0],
                    hint=f'Write it as its own sentence: "{article(name).capitalize()} can be {fname}."',
                    teach="yes_no_property",
                )
            if is_list(K.fields[fname]):
                s.fail("A property can't hold a list yet.", toks[0],
                       hint="Lists can be held by variables, roles and worked-out values.", teach="list")
            if s.at_end():
                break
            comma, conj = s.eat_punct(","), s.eat_word("and")
            if not (comma or conj):
                s.fail('Properties are separated by a comma or by "and".', hint=example, teach="list_commas")
        K.unit = self.unit
        K.adjectives = View(lambda key, adj: self.can_see(adj.unit, key))
        K.props = View(lambda key, prop: self.can_see(prop.unit, key))
        self.kinds[name] = K
        self.nouns[name] = (name, False)
        self.nouns[K.plural] = (name, True)
        self.member_names.update(K.fields)

    def described_again(self, s, ktok, K):
        """Refuse "A dragon has ..." for a kind described before, showing how the one
        sentence that describes it would read with the new properties."""
        name, earlier = K.name, K.line
        at = where(earlier) if earlier.library or chapter_of(earlier) is not None else f"on line {earlier.number}"
        hint = None
        if getattr(earlier, "unit", None) is self.unit and not earlier.library:
            old = [f"{article(f)} ({base(t)}{', if any' if is_opt(t) else ''})" for f, t in K.fields.items()]
            has = s.toks[2]
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
        try:
            with self.fresh():
                cond = self.condition(s)
                self.end(s)
        finally:
            self.scope = self.globals
        source = s.line.text[start:].rstrip(".").strip()
        adj = K.adjectives[atok.low] = Adj(atok.low, self.subject_fn(K.name, cond.fn), source, unit=self.unit)
        self.declare("adjective", atok.low, s.line, (atok.col, len(atok.text)), lambda: adj.used)
        self.adjective_names.add(atok.low)

    def adjective_is_new(self, s, atok, K):
        earlier = K.adjectives.all.get(atok.low)
        if earlier is not None:
            s.fail(f'"{atok.text}" is already defined for {article(K.name)}{self.elsewhere(earlier.unit)}.', atok,
                   hint="An adjective is defined once for each kind: change the first definition, or choose "
                        "another word.", teach="taken")

    def define_stored_adjective(self, s):
        """A | An <kind> can be <adjective>.  A yes-or-no fact, changed with "Now"."""
        s.next()
        K = self.need_kind(s, s.next())
        s.next()  # can
        s.expect_word("be", hint=f'For example: "{article(K.name).capitalize()} can be done."', teach="adjective_form")
        atok = s.next()
        self.check_new_name(s, [atok], "an adjective")
        self.adjective_is_new(s, atok, K)
        self.end(s)
        name = atok.low
        source = f'stored for each {K.name}, set with "Now"'
        adj = K.adjectives[name] = Adj(name, lambda world, thing: name in thing.marks, source, stored=True,
                                     unit=self.unit)
        self.declare("adjective", name, s.line, (atok.col, len(atok.text)), lambda: adj.used)
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
                cond = self.tail(s, left).fn
                self.end(s)
        finally:
            self.scope = self.globals
        holds = cond if mode.low == "always" else (lambda env: not cond(env))
        K.rules.append(Rule(self.subject_fn(K.name, holds), s.line.text.strip()))

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
        if name in K.fields or name in K.props.all:
            unit = K.props.all[name].unit if name in K.props.all else K.unit
            s.fail(f'{article(K.name).capitalize()} already has "{name}"{self.elsewhere(unit)}.', toks[0],
                   hint="Choose another name for the worked-out property.", teach="taken")
        if name in self.workouts.all:
            s.fail(f'"{name}" is already something that is worked out{self.elsewhere(self.workouts.all[name].unit)}, '
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
        elif self.kind_visible(name):
            type_ = name
        else:
            self.hidden_word(s, toks[0])
            if len(toks) == 1:
                self.misspelt(s, toks[0], self.visible_kinds(), "unknown_kind")
            s.fail(
                f"What is {article(name)}?", toks[0],
                hint=f'Describe that kind first, or give this a type: "{article(name)} (money)".\n'
                     + self.kinds_hint(name), teach="unknown_kind",
            )
        return Param(name, type_, prep, (toks[0].col, toks[-1].end - toks[0].col))

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
            binding = scope.names[p.name] = Binding(p.name, p.type, focus=p.type in self.kinds)
            self.declare("role", p.name, s.line, p.at, lambda b=binding: b.reads > 0)
        return scope

    def name_is_new(self, s, name, tok, local=False, hint=None):
        """Refuse a name for a thing, a variable or a worked-out value that already means
        something. A name made at the top level has one meaning in the whole program,
        so every file counts; a variable of a block need only be new where it is."""
        if local:
            taken = self.scope.find(name) or name in self.names or name in self.workouts
            if taken:
                s.fail(f'"{name}" already means something here.', tok, hint=hint, teach="taken")
            return
        owner = None
        if name in self.globals.names:
            owner = self.globals.names[name].unit
        elif name in self.names.all:
            owner = self.name_units[name]
        elif name in self.workouts.all:
            owner = self.workouts.all[name].unit
        elif name in self.nouns.all:
            owner = self.kinds[self.nouns.all[name][0]].unit
        else:
            found = self.scope.find(name)  # a role or a variable of the block around
            if found is None:
                return
        if owner is not None and owner is not self.unit:
            hint = "A name made at the top level means one thing in the whole program, whichever file made it."
        s.fail(f'"{name}" already means something{self.elsewhere(owner)}.', tok, hint=hint, teach="taken")

    def define_procedure(self, s, outside=False):
        """To <verb> ...:  with a block, or, in a library, "... is done by the library."."""
        s.next()  # to
        if s.at_words("work", "out", "the"):
            return self.define_workout(s, outside)
        vtok = s.next()
        self.check_new_name(s, [vtok], "a verb")
        verb = vtok.low
        if verb in self.procs.all:
            s.fail(f'I already know how to "{verb}" ({where(self.procs.all[verb].line)}).', vtok,
                   hint="A verb is taught once: change the first definition, or choose another verb.", teach="taken")
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
        self.declare("verb", verb, s.line, (vtok.col, len(vtok.text)), lambda: proc.used)
        self.procs[verb] = proc  # registered first, so it can call itself
        if outside:
            step = self.outside_verb(s, proc)
            if self.reactive:  # the library's Python code may change things
                step = self.watched(step, None)
            proc.body = [step]
            return
        with self.fresh(verb=proc):
            proc.body = self.block(s.line.children, scope)

    def define_workout(self, s, outside=False):
        """To work out the <name> (<type>) [<preposition> a <role>]... :"""
        for _ in range(3):  # work out the
            s.next()
        toks = []
        while s.peek().kind == "WORD" and s.peek().low not in ROLE_WORDS:
            toks.append(s.next())
        if not toks:
            s.fail("I expected a name for what is worked out.")
        self.check_new_name(s, toks, "a name")
        name = " ".join(t.low for t in toks)
        if name in self.workouts.all:
            s.fail(f'I already know how to work out "the {name}" ({where(self.workouts.all[name].line)}).', toks[0])
        if name in self.member_names:
            s.fail(f'"{name}" is already a property, so something worked out can\'t share its name.', toks[0])
        self.name_is_new(s, name, toks[0])
        if not s.eat_punct("("):
            s.fail(
                f'What sort of value is "the {name}"?', toks[0],
                hint=f'Say so in brackets: "To work out the {name} (money) ...".',
            )
        type_ = self.bracket_type(s)
        params = []
        while not s.at_end():
            ptok = s.next()
            if ptok.kind != "WORD" or ptok.low not in ROLE_WORDS:
                s.fail(
                    'I expected a preposition here, such as "of" or "for", introducing what it is worked out from.',
                    ptok,
                )
            if any(p.prep == ptok.low for p in params):
                s.fail(f'"{ptok.text}" is used twice, so I couldn\'t tell the two apart.', ptok)
            params.append(self.param(s, ptok.low, ROLE_WORDS))
        scope = self.role_scope(s, params, toks[0])
        w = Workout(name, type_, params, s.line, unit=self.unit)
        self.declare("value", name, s.line, (toks[0].col, toks[-1].end - toks[0].col), lambda: w.used)
        self.workouts[name] = w  # registered first, so it can use itself
        if outside:
            w.body = [self.outside_value(s, w)]
            return
        with self.fresh(workout=w):
            w.body = self.block(s.line.children, scope)
        if not self.answers(w.body):
            raise EnglishError(
                "Not every path through this block reaches an answer.",
                s.line, s.toks[0].col, len(s.line.text.strip()),
                hint='Finish the block with "The answer is ...".',
            )

    # reactions ----------------------------------------------------------

    def define_reaction(self, s):
        """Whenever a | an <kind> becomes [not] <adjective>:
        Whenever <thing> becomes [not] <adjective>:

        The block is carried out for a thing straight after a sentence that
        leaves it fitting the adjective (or, with "not", no longer fitting it).
        """
        start = s.next()  # whenever
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
                    s.fail(f'Write "a {tok.text}" for any {noun[0]}, or the name of one thing.', tok, hint=usage)
                self.hidden_here(s)
                if tok.kind == "WORD" and tok.low not in KEYWORDS and not self.defined_word(tok.low):
                    s.fail(f'I don\'t know what "{tok.text}" refers to.', tok,
                           hint="After \"Whenever\" comes a kind (\"a knight\") or a thing with a name, "
                                "made before this sentence.\n" + usage)
                s.fail('After "Whenever" I expected "a" or "an" and a kind, or the name of a thing.', tok, hint=usage)
            thing_key, count = match
            for _ in range(count):
                s.next()
            K = self.kinds[self.names[thing_key][1]]
        if not s.at_word("becomes"):
            if s.at_word("is", "become", "gets", "turns"):
                s.fail('A reaction is written with "becomes".', hint=usage)
            s.fail('I expected "becomes" here.', hint=usage)
        s.next()
        negated = bool(s.eat_word("not"))
        atok = s.next()
        adj = K.adjectives.get(atok.low) if atok.kind == "WORD" else None
        if adj is None:
            self.hidden_adjective(s, atok, K)
            if atok.kind != "WORD":
                s.fail('I expected an adjective here, such as "broke".', atok, hint=usage)
            s.fail(
                f'I don\'t know what "{atok.text}" means for {article(K.name)}.', atok,
                hint=f'Define it first: "{article(K.name).capitalize()} is {atok.text} when ..." '
                     f'or "{article(K.name).capitalize()} can be {atok.text}."',
            )
        self.end(s)
        adj.used = True
        self.note(f'"{atok.text}" → {adj.source}')
        if not self.reactive:  # program() looks ahead for every "Whenever"
            raise EnglishError("This reaction was not expected by the compiler.", s.line, start.col, len(start.text))
        kind = K.name
        with self.fresh(verb=Proc("whenever", [], s.line)):
            body = self.block(s.line.children, self.subject_scope(kind))
        text = s.line.text.strip().rstrip(":").strip()
        test, adjective, becomes = adj.fn, adj.name, not negated

        def run(world, thing):
            frame = Env(world.globals)
            frame.vars[kind] = thing
            try:
                for inner in body:
                    inner(frame)
            except _StopVerb:
                pass

        def step(env):
            env.world.reactions.append(Reaction(kind, adjective, test, becomes, thing_key, run, text))
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

    def use_library(self, s):
        """Use the <name> library.  Compiles the library's SOURCE here, as if written here."""
        use = s.next()
        if self.library is not None:
            s.fail("A library can't use another library.", use,
                   hint='The program itself must say "Use the ... library." for each library it needs.')
        usage = 'For example: "Use the paint library." or "Use the calendar chapter."'
        s.expect_word("the", hint=usage)
        words = []
        while s.peek().kind == "WORD" and not s.at_word("library", "chapter"):
            words.append(s.next())
        if s.at_word("chapter") and words:
            return self.use_chapter(s, words)
        if not words:
            s.fail("I expected the name of a library or a chapter here.", hint=usage)
        tok = words[0]
        if len(words) > 1 or not s.at_word("library"):
            s.fail('A library\'s name is one word, followed by "library".',
                   words[1] if len(words) > 1 else None, hint=usage)
        s.next()
        self.end(s)
        name = tok.low
        here = self.unit
        if ("library", name) in here.used:
            s.fail(f"The {name} library is already in use ({where(here.used[('library', name)])}).", tok)
        if name in self.libraries:  # loaded already, by another file: this file may now say its words
            here.used[("library", name)] = s.line
            here.uses.add(self.library_units[name])
            self.note(f'"{name}" → the Python library, loaded already')
            return None
        available = self.library_names()
        if name not in available:
            s.fail(
                f'There is no library called "{tok.text}".', tok,
                hint=("Libraries: " + ", ".join(available) + ".") if available else "There are no libraries yet.",
            )
        try:
            module = importlib.import_module(f"{libraries.__name__}.{name}")
        except Exception as error:  # noqa: BLE001 - any failure to import is the library's fault
            s.fail(f"The {name} library could not be loaded: {error}", tok,
                   hint="This is a fault in the library, not in your program.")
        source = getattr(module, "SOURCE", None)
        if not isinstance(source, str):
            s.fail(f"The {name} library has no SOURCE text, so I can't tell what it provides.", tok,
                   hint="This is a fault in the library, not in your program.")
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
        usage = 'For example: "Use the calendar chapter." or "Use the calendar chapter of the almanac book."'
        s.next()  # chapter
        book = []
        if s.eat_word("of"):
            s.expect_word("the", hint=usage)
            while s.peek().kind == "WORD":  # the last word is "book", so a book may be called "book"
                book.append(s.next())
            if not book or not book[-1].is_word("book"):
                s.fail('I expected "book" here.', hint=usage)
            book.pop()
            if not book:
                s.fail("I expected the name of a book here.", hint=usage)
        self.end(s)
        for tok in words + book:
            if not tok.text.isalpha():
                s.fail("The name of a chapter or a book is made of plain words, of letters only.", tok, hint=usage)
        if self.library is not None:
            s.fail("A library can't use a chapter.", s.toks[0])
        here = self.unit
        name = " ".join(t.low for t in words)
        path = self.chapter_file(here.folder, [t.low for t in words], [t.low for t in book])
        key = os.path.normcase(os.path.abspath(path))
        if ("chapter", key) in here.used:
            s.fail(f"This file already uses the {name} chapter ({where(here.used[('chapter', key)])}).", words[0])
        unit = self.chapters.get(key)
        if unit is not None and unit in self.reading:
            circle = self.reading[self.reading.index(unit):] + [unit]
            s.fail("These chapters use each other in a circle: "
                   + " -> ".join(u.name or "the program" for u in circle) + ".", words[0],
                   hint="Move what they both need into a chapter of its own, which each of them can use.")
        if unit is None and not path.is_file():
            self.missing_chapter(s, words, name, path)
        here.used[("chapter", key)] = s.line
        if unit is not None:  # read already, for another file: this one may now say what it shares
            here.uses.add(unit)
            self.note(f'"{name}" → {unit.file}, read already')
            return None
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except (OSError, ValueError) as error:
            s.fail(f"I couldn't read the file {path}: {getattr(error, 'strerror', None) or error}.", words[0])
        file = os.path.relpath(path, self.main.folder) if self.main.folder else str(path)
        unit = Unit("chapter", name, path.parent, key, file.replace(os.sep, "/"))
        unit.used_at = s.line
        self.chapters[key] = unit
        steps = self.read_chapter(unit, text, s)
        here.uses.add(unit)
        shared = "everything" if unit.shares is None else (unit.shared_list() or "nothing")
        self.note(f'"{name}" → {unit.file}, which shares {shared}')
        # What the chapter does when it is read may change any thing that this file sees.
        self.forget_after_verb()

        def step(env):
            for inner in steps:
                inner(env.world.globals)
        return step

    def missing_chapter(self, s, words, name, path):
        folder = path.parent
        if folder.is_dir():
            there = sorted(p.stem.replace("_", " ") for p in folder.glob("*.english")
                           if self.main.path is None or os.path.normcase(str(p.resolve())) != os.path.normcase(str(self.main.path)))
            hint = ("Chapters there: " + ", ".join(there) + ".") if there else "There are no chapters there."
        else:
            hint = f"There is no folder {folder}."
        s.fail_span(f'There is no chapter called "{name}": I looked for the file {path}.',
                    (words[0].col, words[-1].end), hint=hint)

    def read_chapter(self, unit, text, s):
        """Compile a chapter's sentences as a file of their own. Returns its steps.

        While linting, the chapter's problems are collected apart, and reported as one
        error at the "Use" sentence."""
        saved = (self.unit, self.line, self.lint, self.scope)
        outer = self.lint
        collector = type(outer)(text) if outer is not None else None
        self.reading.append(unit)
        self.unit, self.lint, self.scope = unit, collector, self.globals
        try:
            with self.fresh():
                layout = [] if collector is not None else None
                lines = read_source(text, unit=unit, problems=layout)
                for error in layout or ():
                    collector.add(error, "error")
                unit.first = lines[0] if lines else None
                steps = self.block(lines, self.globals)
                self.check_shares(unit)
        finally:
            self.unit, self.line, self.lint, self.scope = saved
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
                                       max(1, s.prev_end(col) - col), hint), "error")
        return steps

    def shares_sentence(self, s):
        """This chapter shares only <name>, <name> and <name>.   This chapter shares nothing."""
        usage = 'For example: "This chapter shares only leapness, month length and weekday."'
        s.next()  # this
        s.next()  # chapter
        if not s.eat_word("shares"):
            s.fail('I expected "shares" here.', hint=usage)
        unit = self.unit
        if s.line is not unit.first:
            s.fail('"This chapter shares ..." has to be the first sentence of its file.', s.toks[0])
        if s.eat_word("nothing"):
            self.end(s)
            unit.shares, unit.share_at = set(), {}
            return None
        s.expect_word("only", hint=usage)
        listed = {}
        while True:
            toks = []
            while s.peek().kind == "WORD" and not s.at_word("and"):
                toks.append(s.next())
            if not toks:
                s.fail("I expected a name here, as it was defined, without \"the\".", hint=usage)
            for tok in toks:
                if tok.low in ("the", "a", "an"):
                    s.fail("Names are listed as they were defined, without an article.", tok, hint=usage)
            name = " ".join(t.low for t in toks)
            if name in listed:
                s.fail(f'"{name}" is listed twice.', toks[0])
            listed[name] = (s.line, toks[0].col, toks[-1].end - toks[0].col, " ".join(t.text for t in toks))
            if s.at_end():
                break
            comma, conj = s.eat_punct(","), s.eat_word("and")
            if not (comma or conj):
                s.fail('I expected "," or "and" between the names.', hint=usage)
        unit.shares, unit.share_at = set(listed), listed
        return None

    def defined_by(self, unit, name):
        """What `unit` defines at its top level under `name`: ["a kind", "a verb", ...]."""
        found = []
        K = self.kinds.get(name)
        if K is not None and K.unit is unit:
            found.append("kind")
        if self.name_units.get(name) is unit:
            found.append("thing")
        if name in self.procs.all and self.procs.all[name].unit is unit:
            found.append("verb")
        if name in self.workouts.all and self.workouts.all[name].unit is unit:
            found.append("worked-out value")
        if name in self.globals.names and self.globals.names[name].unit is unit:
            found.append("variable")
        kinds = self.kinds.values()
        if any(K.adjectives.all.get(name) is not None and K.adjectives.all[name].unit is unit for K in kinds):
            found.append("adjective")
        if any(K.props.all.get(name) is not None and K.props.all[name].unit is unit for K in kinds):
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
                    hint = f'"{name}" is a property of {article(owner[0].name)}: it is shared with its kind.'
                elif name in self.nouns.all:
                    hint = f'Write the kind in the singular: "{self.nouns.all[name][0]}".'
            elif len(found) > 1:
                message = (f'"{name}" could mean the {join_words(found)} called "{name}", '
                           "so I can't tell which to share.")
                hint = "Give one of them another name."
            if message:
                error = EnglishError(message, line, col, width, hint)
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
                            len(tok.text), hint="\n".join(detail))

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
                   hint="A program teaches a verb with a colon and an indented block.")
        self.needs_block(s, False)
        header = Sentence(line, line.tokens[:-6] + [Token("END", "", cut.col)])
        self.define_procedure(header, outside=True)

    def library_function(self, s, fname):
        name, module = self.library
        fn = getattr(module, fname, None)
        if not callable(fn):
            s.fail(f'The {name} library has no Python function "{fname}" for this.', s.toks[0],
                   hint=f'It needs: def {fname}(world, ...):')
        return name, fn

    def outside_verb(self, s, proc):
        """The body of a verb that is done by the library."""
        lib, fn = self.library_function(s, "verb_" + proc.verb)
        roles = [(p.name, p.name.replace(" ", "_")) for p in proc.params]

        def step(env):
            call_library(lib, fn, env.world, {key: env.get(role) for role, key in roles})
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
                    hint=f"This is a fault in the {lib} library, not in your program.",
                )
            raise _Answer(converted)
        step.answers = step.leaves = True
        return step

    def create_thing(self, s):
        """There is a | an [<adjective>]... <kind> called <Name> [whose ...]... .   (top level)"""
        s.next()  # there
        s.expect_word("is", hint='For example: "There is a dragon called Smaug whose age is 771."')
        if not s.eat_word("a", "an"):
            s.fail('I expected "a" or "an" here.')
        K, marks = self.thing_head(s)
        s.expect_word("called", f"Every {K.name} needs a name: \"There is {article(K.name)} called ...\".")
        ntoks = []
        while s.peek().kind == "WORD" and not s.at_word("whose"):
            ntoks.append(s.next())
        if not ntoks:
            s.fail("I expected a name here.")
        self.check_new_name(s, ntoks, "a name")
        display = " ".join(t.text for t in ntoks)
        key = display.lower()
        self.name_is_new(s, key, ntoks[0])
        values = self.whose_parts(s, K, ntoks[0])
        self.names[key] = (display, K.name)
        self.name_units[key] = self.unit
        make = self.maker(K, marks, values, lambda env, count: display)

        def step(env):
            env.world.named[key] = make(env)
        return self.changing(step)

    def create_new(self, s):
        """There is a new <kind> [called <text>] [whose ...]... .   (anywhere)"""
        s.next()  # there
        s.next()  # is
        if not s.eat_word("a", "an"):
            s.fail('I expected "a" or "an" here.')
        _, make = self.new_thing(s)
        return self.changing(lambda env: make(env))

    def new_thing(self, s):
        """'new [<adjective>]... <kind> [called <text>] [whose ...]...' to the end of the sentence.

        Returns (the kind, fn(env) -> the new Thing).
        """
        new = s.next()
        if self.workout is not None:
            s.fail("Working something out can't make new things.", new,
                   hint="Make it in a verb, or where the worked-out value is used.")
        K, marks = self.thing_head(s)
        kind = K.name
        if s.eat_word("called"):
            name = self.expr(s)
            self.need(s, name)
            if name.type != "text":
                s.fail_span(f"A name is text, but {name.text} is {self.describe(name.type)}.", name.span,
                            hint='Put a name in quotes: called "Puff".')
            name_fn = name.fn
            name_of = lambda env, count: name_fn(env)
        else:
            name_of = lambda env, count: f"{kind} {count}"
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
                s.fail(
                    f'I don\'t know what "{tok.text}" means for {article(K.name)}.', tok,
                    hint=f'Say first: "{article(K.name).capitalize()} can be {tok.text}."',
                )
            if not adj.stored:
                s.fail(
                    f'"{tok.text}" is worked out from "{adj.source}", so it can\'t be given when {article(K.name)} is made.',
                    tok,
                )
            marks.append(adj.name)
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
                    s.fail('I expected "and whose ..." or the end of the sentence here.')
            first = False
            s.expect_word("whose")
            match = self.match_words(s, K.fields)
            if not match:
                self.no_member(s, K.name)
            fname, count = match
            ftok = s.peek()
            for _ in range(count):
                s.next()
            if fname in values:
                s.fail(f'"{fname}" is given twice.', ftok)
            s.expect_word("is")
            value = self.expr(s)
            want = K.fields[fname]
            if not self.fits(value.type, want):
                if base(value.type) == base(want):
                    self.need(s, value)
                s.fail_span(
                    f"{article(K.name).capitalize()}'s {fname} is {self.describe(want)}, "
                    f"but {value.text} is {self.describe(value.type)}.", value.span,
                )
            values[fname] = value.fn
        missing = [f for f, t in K.fields.items() if f not in values and not is_opt(t)]
        if missing:
            s.fail(
                f"{article(K.name).capitalize()} also needs {join_words(article(m) for m in missing)}.", at,
                hint=f'Add: "whose {missing[0]} is ...".',
            )
        return values

    @staticmethod
    def maker(K, marks, values, name_of):
        """fn(env) -> a new thing of kind K, checked against the kind's rules."""
        kind = K.name
        absent = [f for f in K.fields if f not in values]

        def make(env):
            world = env.world
            count = world.made[kind] = world.made.get(kind, 0) + 1
            name = name_of(env, count)
            fields = {f: fn(env) for f, fn in values.items()}
            for value in fields.values():
                if isinstance(value, Thing):
                    alive(value)
            fields.update((f, None) for f in absent)
            thing = Thing(kind, name, fields, marks, world.new_serial())
            for rule in K.rules:
                if not rule.fn(world, thing):
                    raise EnglishError(f'{name} would break a rule: "{rule.text}"', stage="run", recoverable=True)
            world.things.setdefault(kind, []).append(thing)
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
            s.fail('I expected a name here: "Let the total be 0."')
        declared = self.bracket_type(s) if s.eat_punct("(") else None
        fixed = bool(s.eat_word("always"))
        if s.peek().is_punct("=") and toks:
            name = self.new_name(toks) or "..."
            value = self.certain_value(s.toks[s.i + 1:-1]) or "..."
            s.fail('EnglishScript writes "Let ... be", not "=".', s.peek(),
                   hint="Write: " + full_stop(f"Let {name} be {value}"))
        s.expect_word("be", hint='For example: "Let the total be 0."')
        self.check_new_name(s, toks, "a name")
        name = " ".join(t.low for t in toks)
        self.name_is_new(s, name, toks[0], local=self.scope is not self.globals,
                         hint=f'To change it, write "Set {name} to ...".')
        made_new = s.at_word("a", "an") and s.peek(1).is_word("new")
        if made_new:
            start = s.next().col
            kind, make = self.new_thing(s)
            value = self.stamp(s, Expr(kind, make), start)
        else:
            if declared is not None:
                self.no_group_for_list(s, declared, f'"{name}" is to hold')
            value = self.expr(s)
        self.end(s)
        if declared is None:
            if value.type == "nothing":
                s.fail_span(
                    "Nothing of what sort? I can't tell what this may hold later.", value.span,
                    hint=f'Say so in brackets: "Let {name} (number, if any) be nothing."',
                )
            declared = value.type
        elif not self.fits(value.type, declared):
            if base(value.type) == base(declared):
                self.need(s, value)
            s.fail_span(
                f'"{name}" is to hold {self.describe(declared)}, but {value.text} is {self.describe(value.type)}.',
                value.span,
            )
        binding = self.scope.names[name] = Binding(name, declared, let=not fixed, fixed=fixed)
        if self.scope is self.globals:
            binding.unit = self.unit
        self.declare("variable", name, s.line, (toks[0].col, toks[-1].end - toks[0].col),
                     lambda: binding.reads > 0)
        if is_opt(declared) and not is_opt(value.type) and value.type != "nothing":
            self.present = self.present | {("var", name)}
        self.note(f'"{name}" is {self.describe(declared)}')
        fn = value.fn

        def step(env):
            env.vars[name] = fn(env)
        if made_new:
            self.changing(step)
        return step

    def target(self, s):
        expr = self.primary(s)
        kind = expr.target[0] if expr.target else None
        if kind is None:
            s.fail_span(f"{cap(expr.text)} isn't something that can be changed.", expr.span)
        if kind == "prop":
            prop = expr.target[1]
            s.fail_span(
                f"{cap(expr.text)} is worked out by a rule, so it can't be changed directly.", expr.span,
                hint=f'The rule: "{prop.name}" is {prop.source}.',
            )
        if kind == "fixed":
            s.fail_span(f'{cap(expr.text)} was made with "always", so it can\'t be changed.', expr.span)
        if kind == "maybe":
            self.need(s, expr.target[1])
        if self.workout is not None and (kind == "field" or expr.target[1] in self.globals.names):
            s.fail_span(
                f"Working something out can't change anything, and {expr.text} belongs to the world outside.",
                expr.span,
                hint="Do the change in a verb, or keep the working in a variable made inside this block.",
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
            for rule in K.rules:
                if not rule.fn(env.world, thing):
                    thing.fields[fname] = old
                    raise EnglishError(
                        f'That would break a rule: "{rule.text}"', stage="run", recoverable=True,
                        hint=f"({thing.name}'s {fname} is {fmt(old, ftype)} and would become {fmt(value, ftype)}.)",
                    )
        return put

    def assign(self, s):
        verb = s.next().low
        if verb == "set":
            target = self.target(s)
            if target.target[0] == "var":
                self.scope.find(target.target[1]).reads -= 1  # set, not read
            s.expect_word("to", hint='For example: "Set the total to 0."')
            new = value = self.expr(s)
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
            s.expect_word(link, hint=f'For example: "{verb.capitalize()} 1 {link} the total."')
            target = self.target(s)
            new = self.arith(s, "+" if verb == "add" else "-", target, value)
        else:
            target = self.target(s)
            s.expect_word("by", hint=f'For example: "{verb.capitalize()} the total by 2."')
            value = self.expr(s)
            new = self.arith(s, "*" if verb == "multiply" else "/", target, value)
        self.end(s)
        want = target.declared
        if not self.fits(new.type, want):
            if base(new.type) == base(want):
                self.need(s, value)
            s.fail_span(
                f"{cap(target.text)} is {self.describe(want)}, but that would make it {self.describe(new.type)}.",
                value.span,
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
        return step

    def say(self, s):
        if self.workout is not None:
            s.fail("Working something out can't say anything.",
                   hint="Say it from a verb, or where the worked-out value is used.")
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
            s.fail('"The answer is" belongs inside a "To work out ...:" block.', s.toks[0])
        s.expect_word("is")
        value = self.expr(s)
        self.end(s)
        w = self.workout
        if not self.fits(value.type, w.type):
            if base(value.type) == base(w.type):
                self.need(s, value)
            s.fail_span(
                f"The {w.name} is {self.describe(w.type)}, but {value.text} is {self.describe(value.type)}.",
                value.span,
            )
        fn = value.fn

        def step(env):
            raise _Answer(fn(env))
        step.answers = step.leaves = True
        return step

    def one_loop(self, s, phrase):
        if not self.loops:
            s.fail(f'"{phrase}." needs a loop around it.', s.toks[0])
        if len(self.loops) > 1:
            s.fail(
                f'"{phrase}." could mean either of the loops around it.', s.toks[0],
                hint='Move the inner loop into its own verb, and use "Stop." there.',
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
            s.fail('Inside "To work out", finish with "The answer is ...".', s.toks[0])
        if self.verb is None:
            s.fail(
                '"Stop." ends a verb, and this sentence isn\'t inside one.', s.toks[0],
                hint='To leave a loop, write "Stop repeating." To finish altogether, write "End the program."',
            )

        def step(env):
            raise _StopVerb()
        step.leaves = True
        return step

    def skip(self, s):
        s.next()
        s.expect_word("this", hint='Write "Skip this round." or, in a For each, "Skip this dragon."')
        tok = s.peek()
        if tok.kind != "WORD":
            s.fail('I expected "round", or the noun of a For each.', tok)
        if tok.low == "round":
            s.next()
            self.end(s)
            found = self.one_loop(s, "Skip this round")
            if found["noun"]:
                s.fail('A "For each" has no rounds.', tok, hint=f'Write "Skip this {found["noun"]}."')
        else:
            # A loop's noun may be several words: "For each old task in ...".
            match = self.match_words(s, [loop["noun"] for loop in self.loops if loop["noun"]])
            if not match:
                s.next()
                self.end(s)
                s.fail(f'There is no "For each {tok.text}" around this sentence.', tok)
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
                        'To finish the whole program, write "End the program.".')
        s.expect_word("the", hint='Write "End the program."')
        s.expect_word("program", hint='Write "End the program."')
        self.end(s)
        if self.workout is not None:
            s.fail('Inside "To work out", finish with "The answer is ...".', s.toks[0])

        def step(env):
            raise _EndProgram()
        step.leaves = True
        return step

    def no_change_here(self, s, what):
        """Refuse a sentence that changes the world inside "To work out"."""
        if self.workout is not None:
            s.fail(f"Working something out can't {what}.", s.toks[0],
                   hint="Do it in a verb, or where the worked-out value is used.")

    def fail_because(self, s):
        """Fail because <text>.  A problem of the program's own, which "Try:" can recover from."""
        s.next()
        s.expect_word("because", hint='For example: "Fail because "the gate is shut"."')
        reason = self.expr(s)
        self.end(s)
        self.need(s, reason)
        if reason.type != "text":
            s.fail_span(f"The reason is text, but {reason.text} is {self.describe(reason.type)}.", reason.span)
        rf = reason.fn

        def step(env):
            raise EnglishError(rf(env), stage="run", recoverable=True)
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
            s.fail_span(f"{cap(thing.text)} is {self.describe(thing.type)}, so it has no adjectives.", thing.span)
        K = self.kinds[thing.type]
        s.expect_word("is", hint='For example: "Now Robin is sworn."')
        negated = bool(s.eat_word("not"))
        atok = s.next()
        adj = K.adjectives.get(atok.low) if atok.kind == "WORD" else None
        if adj is None:
            self.hidden_adjective(s, atok, K)
            s.fail(
                f'I don\'t know what "{atok.text}" means for {article(K.name)}.', atok,
                hint=f'To store it, say first: "{article(K.name).capitalize()} can be {atok.text}."',
            )
        if not adj.stored:
            s.fail(
                f'"{atok.text}" is worked out from "{adj.source}", so "Now" can\'t change it.', atok,
                hint='Change what it is worked out from, or describe it with "can be" instead.',
            )
        self.end(s)
        self.note(f'"{atok.text}" → {adj.source}')
        tf, name = thing.fn, adj.name
        adj.used = True

        def step(env):
            target = alive(tf(env))
            if negated:
                target.marks.discard(name)
            else:
                target.marks.add(name)
        return self.changing(step)

    def remove(self, s):
        """Remove <thing>.  It leaves every group; "if any" properties that pointed at it become nothing."""
        s.next()
        self.no_change_here(s, "remove anything")
        thing = self.expr(s)
        self.end(s)
        self.need(s, thing)
        if thing.type not in self.kinds:
            s.fail_span(f"Only a thing can be removed, but {thing.text} is {self.describe(thing.type)}.", thing.span)
        # Properties that pointed at it become nothing, so checks no longer hold.
        self.forget_after_verb()
        tf, kinds = thing.fn, self.kinds
        return self.changing(lambda env: self.remove_thing(env.world, alive(tf(env)), kinds))

    @staticmethod
    def remove_thing(world, thing, kinds):
        blockers, cleared = [], []
        for kind, items in world.things.items():
            fields = kinds[kind].fields
            for other in items:
                if other is thing:
                    continue
                for fname, value in other.fields.items():
                    if value is thing:
                        (cleared if is_opt(fields[fname]) else blockers).append((other, fname))
        if blockers:
            which = join_words(f"{other.name}'s {fname}" for other, fname in blockers)
            raise EnglishError(
                f"I can't remove {thing.name} while {which} still {'points' if len(blockers) == 1 else 'point'} at it.",
                stage="run", recoverable=True,
                hint='Change or remove those first, or describe the property with "if any".',
            )
        for other, fname in cleared:
            other.fields[fname] = None
        for other, fname in cleared:
            for rule in kinds[other.kind].rules:
                if not rule.fn(world, other):
                    for back, bname in cleared:
                        back.fields[bname] = thing
                    raise EnglishError(
                        f'Removing {thing.name} would break a rule: "{rule.text}"', stage="run", recoverable=True,
                        hint=f"({other.name}'s {fname} would become nothing.)",
                    )
        world.things[thing.kind].remove(thing)
        thing.removed = True

    def ask(self, s):
        """Ask <text> and let [the] <name> (<type>) be the reply."""
        s.next()
        self.no_change_here(s, "ask anything")
        usage = 'For example: "Ask "How old?" and let the age (number) be the reply."'
        question = self.expr(s)
        self.need(s, question)
        if question.type != "text":
            s.fail_span(f"The question is text, but {question.text} is {self.describe(question.type)}.",
                        question.span)
        s.expect_word("and", hint=usage)
        s.expect_word("let", hint=usage)
        s.eat_word("the")
        toks = []
        while s.peek().kind == "WORD" and not s.at_word("be"):
            toks.append(s.next())
        if not toks:
            s.fail("I expected a name here, for the reply.", hint=usage)
        self.check_new_name(s, toks, "a name")
        name = " ".join(t.low for t in toks)
        self.name_is_new(s, name, toks[0], local=self.scope is not self.globals,
                         hint="Choose a new name for the reply.")
        if not s.eat_punct("("):
            s.fail(f'What sort of reply is "{name}"?', hint=usage)
        type_tok = s.peek()
        type_ = self.bracket_type(s)
        if type_ not in ASKABLE:
            s.fail(f"I can't ask for {self.describe(type_)}.", type_tok,
                   hint="A reply can be text, a number, money, a percentage, or yes or no.")
        for word in ("be", "the", "reply"):
            s.expect_word(word, hint=usage)
        self.end(s)
        binding = self.scope.names[name] = Binding(name, type_, let=True)
        if self.scope is self.globals:
            binding.unit = self.unit
        self.declare("variable", name, s.line, (toks[0].col, toks[-1].end - toks[0].col),
                     lambda: binding.reads > 0)
        self.note(f'"{name}" is {self.describe(type_)}, from the reply')
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
            env.vars[name] = value
        return step

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
                        + f'\nTo write it to a file: Write {written} to the file "notes.txt".')
        for word in ("to", "the", "file"):
            s.expect_word(word, hint=usage)
        return self.file_write(s, value, append=False)

    def file_write(self, s, value, append):
        """The rest of "Write ... to the file <text>." or "Add ... to the file <text>."."""
        self.no_change_here(s, "write to a file")
        self.need(s, value)
        if value.type != "text":
            s.fail_span(f"Only text can be written to a file, but {value.text} is {self.describe(value.type)}.",
                        value.span)
        path = self.file_name(s)
        self.end(s)
        vf, pf = value.fn, path.fn

        def step(env):
            text = vf(env)
            write_file(pf(env), text, append)
        return self.changing(step)  # an adjective may be worked out from a file

    def example(self, s):
        s.next()
        s.next()
        s.eat_punct(",")
        cond = self.condition(s)
        self.end(s)
        fn, subject = cond.fn, cond.subject

        def step(env):
            if not fn(env):
                hint = None
                if subject is not None:
                    hint = f"In fact, {subject.text} is {fmt(subject.fn(env), subject.type)}."
                raise EnglishError("This example doesn't hold.", stage="run", hint=hint)
            env.world.examples += 1
        return step

    def for_each(self, s):
        s.next()
        if not s.at_word("each"):
            self.for_advice(s)
        s.expect_word("each", hint='For example: "For each dragon:"')
        j = s.i
        while s.toks[j].kind == "WORD" and s.toks[j].low not in KEYWORDS:
            j += 1
        if j > s.i and s.toks[j].is_word("in"):
            return self.for_each_named(s, j)
        coll = self.collection(s, plural=False)
        self.end(s)
        name = coll.kind
        if self.scope.find(name):
            s.fail(
                f'There is already a "{name}" in view here, so "the {name}" would mean two things.', s.toks[2],
                hint=f'Give the loop\'s thing its own name: "For each other in {self.kinds[name].plural}:".',
            )
        loop, body = self.loop_body(s.line.children, noun=name, binding=Binding(name, name, focus=True))
        return self.each_step(name, coll.fn, loop, body)

    def for_each_named(self, s, j):
        """For each <name> in <group, in the plural>:   or   For each <name> in <list>:"""
        toks = s.toks[s.i:j]
        s.i = j + 1  # past "in"
        name = " ".join(t.low for t in toks)
        if self.scope.find(name) or name in self.names or name in self.workouts:
            s.fail(
                f'"{name}" already means something here, so "the {name}" would mean two things.', toks[0],
                hint="Choose another name for the loop's thing.",
            )
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
                                items.span)
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
            s.fail_span(f"I need a plain number of times, but {count.text} is {self.describe(count.type)}.", count.span)
        s.expect_word("times", hint='For example: "Repeat 3 times:"')
        self.end(s)
        loop, body = self.loop_body(s.line.children)
        fn, run = count.fn, self.run_block

        def step(env):
            n = fn(env)
            if n.denominator != 1 or n < 0:
                raise EnglishError(f"I can't repeat something {fmt(n, 'number')} times.", stage="run", recoverable=True)
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
        cond = self.condition(s).fn
        self.end(s)
        loop, body = self.loop_body(s.line.children)
        run = self.run_block

        def step(env):
            turns = 0
            while cond(env):
                turns += 1
                if turns > LOOP_LIMIT:
                    raise EnglishError(
                        f"This loop has gone round {LOOP_LIMIT:,} times, so I stopped it.", stage="run",
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
        vtok = s.next()
        proc = self.procs[vtok.low]
        if self.verb is not proc:
            proc.used = True
        if self.workout is not None:
            s.fail(
                f'Working something out can\'t change anything, and "{proc.verb}" is a verb.', vtok,
                hint='A "To work out" block may use other worked-out values, but not verbs.',
            )
        by_prep = {p.prep: p for p in proc.params}
        usage = "It goes: " + proc.usage()
        args = {}

        def take(param):
            if s.at_end():
                s.fail(f'I expected {article(param.name)} here.', hint=usage)
            self.no_group_for_list(s, param.type, f'"{proc.verb.capitalize()}" wants')
            value = self.expr(s)
            if not self.fits(value.type, param.type):
                if base(value.type) == base(param.type):
                    self.need(s, value)
                s.fail_span(
                    f'"{proc.verb.capitalize()}" wants {article(param.name)} here, '
                    f"but {value.text} is {self.describe(value.type)}.", value.span, hint=usage,
                )
            args[param.name] = value

        if None in by_prep:
            if s.at_end() or (s.peek().kind == "WORD" and s.peek().low in by_prep):
                s.fail(f'{proc.verb.capitalize()} what? I expected {article(by_prep[None].name)} here.', hint=usage)
            take(by_prep[None])
        while not s.at_end():
            ptok = s.next()
            param = by_prep.get(ptok.low) if ptok.kind == "WORD" else None
            if param is None:
                s.fail(f'I don\'t know how "{ptok.text}" fits with "{proc.verb}".', ptok, hint=usage)
            if param.name in args:
                s.fail(f'"{ptok.text}" appears twice.', ptok, hint=usage)
            take(param)
        missing = [p for p in proc.params if p.name not in args]
        if missing:
            wanted = join_words(f"{p.prep} {article(p.name)}" for p in missing)
            s.fail(f'"{proc.verb.capitalize()}" is missing something: {wanted}.', hint=usage)
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

    def run(self, out=print, ask=None):
        """Carry out the program. `ask` takes a question and returns the reply,
        or None (or raises EOFError) when input has ended; by default it reads
        a line from standard input.

        If the sentences run to their end, each library's `live(world)` is
        called; then, however the run ended, each library's `finish(world)`.
        Returns the World, which a live library may still bring events into
        (World.event)."""
        world = World(out, ask)
        for name in self.compiler.libraries:
            world.libraries[name] = {}
        world.rules = {name: K.rules for name, K in self.compiler.kinds.items()}
        limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(limit, RECURSION_LIMIT))  # each English call costs several Python frames
        to_the_end = False  # did the sentences run to their end, with no problem and no "End the program."?
        failures = []
        try:
            world.busy = True  # world.event must wait until the sentences are done
            with no_digit_limit():
                for step in self.steps:
                    step(world.globals)
            to_the_end = True
        except _EndProgram:
            pass
        except RecursionError:
            raise EnglishError("This program nests more deeply than I can follow.", stage="run") from None
        finally:
            sys.setrecursionlimit(limit)
            world.busy = False
            world.ended = not to_the_end
            # A library that goes on working after the sentences starts here; then
            # every library is told the run is over, however it ended. If the run
            # failed, that failure is what propagates, never a failure to finish.
            if to_the_end:
                failures = self.call_libraries(world, "live", "could not go on")
                if failures:
                    world.ended = True
            failures += self.call_libraries(world, "finish", "could not finish")
        if failures:
            raise EnglishError("A library " + "; ".join(failures), stage="run",
                               hint="This is a fault in the library, not in your program.")
        return world

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


def compile_source(source, folder=None, name=None):
    """Compile a whole program. Raises EnglishError; runs nothing.

    `folder` is where the chapters it uses are looked for (by default the
    current directory), and `name` is what messages call its file."""
    with no_digit_limit():  # a long number written in the program is read in full
        compiler = Compiler(folder, name)
        lines = read_source(source, unit=compiler.main)
        steps = compiler.program(lines)
    return Program(steps, compiler.notes, compiler)


def compile_file(path):
    """Compile the program in a file; its chapters are looked for beside it."""
    path = Path(path)
    source = path.read_text(encoding="utf-8")
    return compile_source(source, folder=path.parent, name=str(path))

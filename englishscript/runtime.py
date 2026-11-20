"""What exists while a program runs: things, the world, variables, formatting."""
from __future__ import annotations

import re
import sys
from contextlib import contextmanager
from fractions import Fraction

from .lexer import EnglishError


@contextmanager
def no_digit_limit():
    """Let numbers of any length be read and said in full.

    Python refuses to turn an integer of more than 4,300 digits into text (or
    back) by default. Exact arithmetic can easily pass that, so the limit is
    lifted while a program compiles or runs, and put back afterwards.
    """
    get = getattr(sys, "get_int_max_str_digits", None)
    if get is None:  # Python before 3.11 has no limit
        yield
        return
    saved = get()
    sys.set_int_max_str_digits(0)
    try:
        yield
    finally:
        sys.set_int_max_str_digits(saved)


class Thing:
    """One instance of a kind, e.g. the dragon called Smaug."""

    __slots__ = ("kind", "name", "fields", "marks", "removed")

    def __init__(self, kind, name, fields, marks=()):
        self.kind = kind
        self.name = name
        self.fields = fields
        self.marks = set(marks)  # stored adjectives that are "yes"
        self.removed = False

    def __repr__(self):
        return f"<{self.kind} {self.name}>"


def alive(thing):
    """The thing itself, or a problem if it has been removed."""
    if thing.removed:
        raise EnglishError(f"{thing.name} has been removed, so it can't be used any more.",
                           stage="run", recoverable=True)
    return thing


class Env:
    """A chain of variable tables. The root one holds the globals."""

    __slots__ = ("vars", "parent", "world")

    def __init__(self, parent, world=None):
        self.vars = {}
        self.parent = parent
        self.world = world if world is not None else parent.world

    def get(self, name):
        env = self
        while env is not None:
            if name in env.vars:
                return env.vars[name]
            env = env.parent
        raise KeyError(name)

    def set(self, name, value):
        env = self
        while env is not None:
            if name in env.vars:
                env.vars[name] = value
                return
            env = env.parent
        raise KeyError(name)


def read_line(prompt):
    """The default way to ask: print the prompt and read a line. None at the end of input."""
    try:
        return input(prompt + " ")
    except EOFError:
        print()
        return None


class World:
    def __init__(self, out=print, ask=None):
        self.out = out
        self.ask = ask if ask is not None else read_line
        self.things = {}  # kind -> [Thing], in order of creation; removed things leave
        self.named = {}  # lowercased name -> Thing
        self.made = {}  # kind -> how many have been made, for default names
        self.libraries = {}  # library name -> that library's own state (outside the world)
        self.globals = Env(None, self)
        self.examples = 0
        self.depth = 0

    def snapshot(self, env):
        """Everything a failed "Try" must put back. Returns a function that does it.

        Values are never changed in place (lists are tuples), so copying each
        table one level deep is enough.
        """
        things = {kind: list(items) for kind, items in self.things.items()}
        states = [
            (thing, dict(thing.fields), set(thing.marks), thing.removed)
            for items in self.things.values() for thing in items
        ]
        tables = []
        while env is not None:
            tables.append((env, dict(env.vars)))
            env = env.parent
        made = dict(self.made)

        def restore():
            self.things = things
            for thing, fields, marks, removed in states:
                thing.fields, thing.marks, thing.removed = fields, marks, removed
            for table, values in tables:
                table.vars.clear()
                table.vars.update(values)
            self.made = made
        return restore


# ------------------------------------------------------------------ files


def _reason(error):
    if isinstance(error, OSError) and error.strerror:
        return error.strerror
    if isinstance(error, UnicodeError):
        return "it isn't UTF-8 text"
    return str(error) or type(error).__name__


def read_file(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except (OSError, ValueError) as error:
        raise EnglishError(f"I couldn't read the file {path}: {_reason(error)}.",
                           stage="run", recoverable=True) from None


def write_file(path, text, append):
    try:
        with open(path, "a" if append else "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except (OSError, ValueError) as error:
        raise EnglishError(f"I couldn't write to the file {path}: {_reason(error)}.",
                           stage="run", recoverable=True) from None


def split_lines(text):
    """Lines split on any line break, without an empty last line."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()
    return tuple(lines)


# ------------------------------------------------------------- reading values

_NUMBER = re.compile(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")


def read_number(text):
    """A number written the way the language writes them, or None."""
    text = text.strip()
    if not _NUMBER.fullmatch(text):
        return None
    try:
        return Fraction(text.replace(",", ""))
    except ValueError:  # more digits than Python will convert
        return None


def read_reply(text, type_):
    """A reply read as `type_`, or None if it can't be. Text is kept as typed."""
    if type_ == "text":
        return text.rstrip("\r\n")
    text = text.strip()
    if type_ == "yes or no":
        low = text.lower()
        if low in ("yes", "y"):
            return True
        if low in ("no", "n"):
            return False
        return None
    if type_ == "money":
        negative = text.startswith("-")
        rest = text[1:].strip() if negative else text
        if rest.startswith("$"):
            rest = rest[1:]
        if rest.startswith("-"):
            return None
        value = read_number(rest)
        if value is None:
            return None
        return -value if negative else value
    if type_ == "percent":
        if not text.endswith("%"):
            return None
        value = read_number(text[:-1])
        return None if value is None else value / 100
    return read_number(text)


# -------------------------------------------------------------- formatting


def fmt(value, type_):
    """Render a value the way a person would write it."""
    if value is None:
        return "nothing"
    type_ = type_.rstrip("?")  # "money?" is money that turned out to be there
    if type_ == "money":
        cents = round(Fraction(value) * 100)
        sign = "-" if cents < 0 else ""
        dollars, rest = divmod(abs(cents), 100)
        return f"{sign}${dollars:,}" + (f".{rest:02d}" if rest else "")
    if type_ == "number":
        return _number(value)
    if type_ == "percent":
        return _number(Fraction(value) * 100) + "%"
    if type_ in ("truth", "yes or no"):
        return "yes" if value else "no"
    if isinstance(value, Thing):
        return value.name
    return str(value)


def _number(value):
    value = Fraction(value)
    if value.denominator == 1:
        return f"{value.numerator:,}"
    try:
        return f"{float(value):,.4f}".rstrip("0").rstrip(".")
    except OverflowError:  # too large for a float: round exactly instead
        sign = "-" if value < 0 else ""
        whole, rest = divmod(round(abs(value) * 10_000), 10_000)
        return f"{sign}{whole:,}" + f".{rest:04d}".rstrip("0").rstrip(".")

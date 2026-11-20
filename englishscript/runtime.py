"""What exists while a program runs: things, the world, variables, formatting."""
from __future__ import annotations

from fractions import Fraction


class Thing:
    """One instance of a kind, e.g. the dragon called Smaug."""

    __slots__ = ("kind", "name", "fields")

    def __init__(self, kind, name, fields):
        self.kind = kind
        self.name = name
        self.fields = fields

    def __repr__(self):
        return f"<{self.kind} {self.name}>"


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


class World:
    def __init__(self, out=print):
        self.out = out
        self.things = {}  # kind -> [Thing], in order of creation
        self.named = {}  # lowercased name -> Thing
        self.globals = Env(None, self)
        self.examples = 0
        self.depth = 0


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
    if type_ == "truth":
        return "yes" if value else "no"
    if isinstance(value, Thing):
        return value.name
    return str(value)


def _number(value):
    value = Fraction(value)
    if value.denominator == 1:
        return f"{value.numerator:,}"
    return f"{float(value):,.4f}".rstrip("0").rstrip(".")

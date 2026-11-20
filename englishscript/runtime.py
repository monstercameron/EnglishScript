"""What exists while a program runs: things, the world, variables, formatting."""
from __future__ import annotations

import math
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


REACTION_LIMIT = 200  # how deeply reactions may set off further reactions
RECURSION_LIMIT = 20_000  # Python frames allowed while English runs: each English call costs several


class _Signal(Exception):
    """Not an error: how Stop, Skip, The answer is and End the program leave a block."""


class _EndProgram(_Signal):
    pass


class Example:
    """A "For example" sentence reached while testing (Program.test)."""

    __slots__ = ("file", "line", "sentence", "held", "fact")

    def __init__(self, file, line, sentence, held, fact):
        self.file = file  # the chapter's file, or None for the program's own
        self.line = line  # its line number
        self.sentence = sentence  # as written
        self.held = held  # did it hold?
        self.fact = fact  # when it didn't: "In fact, ...", if that can be said; otherwise None

    def __repr__(self):
        return f"<Example line {self.line}: {'held' if self.held else 'did not hold'}>"


class Thing:
    """One instance of a kind, e.g. the dragon called Smaug.

    `serial` counts every thing made in a run, across all kinds, from 1, in the
    order they were made. A failed "Try" does not put the count back, so a
    serial is never given twice in one run.
    """

    __slots__ = ("kind", "name", "fields", "marks", "removed", "serial")

    def __init__(self, kind, name, fields, marks=(), serial=0):
        self.kind = kind
        self.name = name
        self.fields = fields
        self.marks = set(marks)  # stored adjectives that are "yes"
        self.removed = False
        self.serial = serial

    def __repr__(self):
        return f"<{self.kind} {self.name}>"


def join(items):
    items = list(items)
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


def alive(thing):
    """The thing itself, or a problem if it has been removed."""
    if thing.removed:
        raise EnglishError(f"{thing.name} has been removed, so it can't be used any more.",
                           stage="run", recoverable=True, teach="removed",
                           hint="Check that it is still there before using it, or stop using it once it is removed.")
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


class Reaction:
    """One "Whenever" sentence, once it has been reached."""

    __slots__ = ("kind", "adjective", "test", "becomes", "thing", "run", "text", "local", "line", "word")

    def __init__(self, kind, adjective, test, becomes, thing, run, text, local=False, line=None, word=None):
        self.line = line  # the "Whenever" sentence, for the trace
        self.word = word  # the adjective as written
        self.local = local  # does the adjective read only its own thing's stored properties?
        self.kind = kind
        self.adjective = adjective
        self.test = test  # (world, thing) -> does it fit the adjective?
        self.becomes = becomes  # True for "becomes", False for "becomes not"
        self.thing = thing  # the lowercased name of the one thing watched, or None for every one of the kind
        self.run = run  # (world, thing) -> None: carries out the block
        self.text = text  # the sentence, for messages

    def watches(self):
        return (self.kind, self.adjective, self.thing)


class World:
    def __init__(self, out=print, ask=None, model=None, judge=None):
        self.out = out
        self.ask = ask if ask is not None else read_line
        # Who answers "Ask the model" and "Judge" (section 7.8), or None: nothing is listening.
        self.model = model  # (question, state, shape, complaint) -> text, or None for no reply
        self.judge = judge  # (question, state, choices, meanings) -> a chance, or {choice: chance}
        self.things = {}  # kind -> [Thing], in order of creation; removed things leave
        self.named = {}  # lowercased name -> Thing
        self.made = {}  # kind -> how many have been made, for default names
        self.libraries = {}  # library name -> that library's own state (outside the world)
        self.globals = Env(None, self)
        self.examples = 0
        self.depth = 0
        self.serials = 0  # how many things have been made, of every kind (Thing.serial)
        self.reactions = []  # [Reaction], in the order written, from when each "Whenever" is reached
        self.reacting = 0  # how deeply reactions are nested
        self.chain = []  # (the reaction's sentence, the thing's name) of each reaction being carried out
        self.settlers = []  # [(Line, run(world))]: each "Whenever everything has settled", once reached
        self.keepers = []  # [(Line, keep(world) -> [what changed])]: each "Keep" sentence, once reached
        self.changed = False  # has the turn being carried out changed anything?
        self.settling = False  # is a settled block being carried out?
        self.rules = {}  # kind -> [Rule] (.fn(world, thing), .text), for world.event
        self.busy = False  # is a sentence or an event being carried out?
        self.ended = False  # did the program end ("End the program.", or a problem)?
        self.testing = None  # with --test: [Example], every "For example" reached, held or not
        self.trace = None  # with --trace: fn(depth, file, line, sentence, cause) for each sentence carried out
        # (kind, property) -> {value: [Thing], in the order made}: built the first time a
        # group is filtered by "whose <property> is <value>", and kept right through every
        # change (see `changed_field`). Anything that changes things in another way (a
        # failed Try putting things back, an event, a library's verb) throws them away.
        self.indexes = {}

    def new_serial(self):
        self.serials += 1
        return self.serials

    def traced(self, line, cause=None):
        """Tell the trace (Program.run's `trace`) that the sentence on `line` is being
        carried out: (depth, file, line number, sentence, cause). The depth is how far
        the line is indented, plus the verbs, worked-out values and reactions it is in."""
        unit = getattr(line, "unit", None)
        if line.library:
            file = f"the {line.library} library"
        elif unit is not None and getattr(unit, "kind", None) == "chapter":
            file = unit.file
        else:
            file = None
        depth = getattr(line, "level", 0) + self.depth + self.reacting
        self.trace(depth, file, line.number, line.text.strip(), cause)

    # Finding things by a stored property, without a search ---------------------

    @staticmethod
    def _key(value):
        """What a value is indexed under: a thing by itself, anything else by its value."""
        return ("thing", id(value)) if isinstance(value, Thing) else value

    def lookup(self, kind, name, value):
        """The things of `kind` whose stored property `name` is `value`, in the order made."""
        index = self.indexes.get((kind, name))
        if index is None:
            index = self.indexes[(kind, name)] = {}
            for thing in self.things.get(kind, ()):
                index.setdefault(self._key(thing.fields[name]), []).append(thing)
        return index.get(self._key(value), ())

    def changed_field(self, thing, name, old):
        """Keep the index of `name`, if there is one, right after the property changed from `old`."""
        index = self.indexes.get((thing.kind, name))
        if index is None:
            return
        bucket = index.get(self._key(old))
        if bucket is not None and thing in bucket:
            bucket.remove(thing)
        bucket = index.setdefault(self._key(thing.fields[name]), [])
        at = len(bucket)
        while at > 0 and bucket[at - 1].serial > thing.serial:
            at -= 1
        bucket.insert(at, thing)

    def added(self, thing):
        """A thing was made: it joins the indexes of its kind."""
        for (kind, name), index in self.indexes.items():
            if kind == thing.kind:
                index.setdefault(self._key(thing.fields[name]), []).append(thing)

    def dropped(self, thing):
        """A thing was removed: it leaves the indexes of its kind."""
        for (kind, name), index in self.indexes.items():
            if kind == thing.kind:
                bucket = index.get(self._key(thing.fields[name]))
                if bucket is not None and thing in bucket:
                    bucket.remove(thing)

    def snapshot(self, env):
        """Everything a failed "Try" must put back. Returns a function that does it."""
        return self._snapshot(env)[0]

    def _snapshot(self, env):
        """(restore, states): a function that puts everything back, and each
        thing with the fields, marks and removal it had.

        Values are never changed in place (lists are tuples), so copying each
        table one level deep is enough. The serial count is not put back.
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
            self.indexes = {}  # built again when next needed
            self.things = things
            for thing, fields, marks, removed in states:
                thing.fields, thing.marks, thing.removed = fields, marks, removed
            for table, values in tables:
                table.vars.clear()
                table.vars.update(values)
            self.made = made
        return restore, states

    # Reactions ("Whenever") -------------------------------------------------

    def noting(self, focus=None):
        """What fits each watched adjective now, before something that may change it.

        {(kind, adjective, thing): (test, [(thing, fits)])}. Each adjective is
        worked out once per thing, however many reactions watch it.

        `focus` is the one thing a sentence is about to change, when it changes
        nothing else (a property or a stored adjective of one known thing). Then
        an adjective that reads only its own thing's stored properties can change
        only for that thing, and only that thing is noted for it. An adjective
        that reads anything else (another thing, a worked-out property, a variable
        that can change) is noted for every thing of its kind, as for any sentence.
        """
        watched = {}
        for reaction in self.reactions:
            key = reaction.watches()
            if key in watched:
                continue
            if focus is not None and reaction.local:
                if focus.removed or focus.kind != reaction.kind or (
                        reaction.thing is not None and self.named.get(reaction.thing) is not focus):
                    continue  # this sentence cannot change it
                items = (focus,)
            elif reaction.thing is None:
                items = self.things.get(reaction.kind, ())
            else:
                one = self.named.get(reaction.thing)
                items = () if one is None or one.removed else (one,)
            test = reaction.test
            watched[key] = (test, [(thing, bool(test(self, thing))) for thing in items])
        return watched

    def react(self, before):
        """Carry out the reactions to what changed since `before` (from noting).

        Only things that existed before can "become"; a thing removed since
        becomes nothing. The things are taken in the order they were made, and
        for each one the reactions in the order they were written.
        """
        due = []
        for key, (test, fits) in before.items():
            for thing, was in fits:
                if thing.removed:
                    continue
                now = bool(test(self, thing))
                if now == was:
                    continue
                for order, reaction in enumerate(self.reactions):
                    if reaction.becomes == now and reaction.watches() == key:
                        due.append((thing.serial, order, thing, reaction))
        due.sort(key=lambda entry: (entry[0], entry[1]))
        for _, _, thing, reaction in due:
            if thing.removed:  # removed by an earlier reaction
                continue
            self.reacting += 1
            self.chain.append((reaction.text, thing.name))
            if self.trace is not None and reaction.line is not None:
                self.reacting -= 1
                self.traced(reaction.line, f"{thing.name} became {'' if reaction.becomes else 'not '}"
                                           f"{reaction.word or reaction.adjective}")
                self.reacting += 1
            try:
                if self.reacting > REACTION_LIMIT:
                    raise EnglishError(
                        f"Reactions keep setting off reactions; I stopped after {REACTION_LIMIT} levels, "
                        + self.circle(), stage="run", teach="depth",
                        hint="Look for a reaction that undoes what set it off, or that sets itself off again.",
                    )
                reaction.run(self, thing)
            finally:
                self.reacting -= 1
                self.chain.pop()

    def circle(self):
        """'in this circle: "Whenever ..." (Robin), then "Whenever ..." (Robin)', when the
        reactions being carried out repeat; otherwise 'at "Whenever ..."'."""
        chain = self.chain
        for size in range(1, len(chain) // 2 + 1):
            if chain[-size:] == chain[-2 * size:-size]:
                # Told from where it began, when the chain went round from its start.
                circle = chain[:size] if chain[:size] == chain[size:2 * size] else chain[-size:]
                steps = ", then ".join(f'"{text}" ({name})' for text, name in circle)
                return f"in this circle: {steps}, and round again."
        return f'at "{chain[-1][0]}".'

    def settle(self, line=None):
        """The end of a turn: if it changed anything, carry out each "Whenever
        everything has settled" block once, in the order written.

        A turn is one top-level sentence (`line`) of the program or of a chapter
        being read, with all it sets off, or one event (World.event, `line` None).
        What a settled block changes sets off reactions as usual, but never another
        settling. A problem in it is a problem of the turn: it gets a trace line
        for the settled block and for the sentence that formed the turn.
        """
        if not self.changed or self.settling:
            return
        self.changed = False
        self.settling = True
        try:
            if self.keepers:
                try:
                    self.keep()
                except EnglishError as error:
                    if error.line is None:
                        error.line = line
                    elif line is not None and error.line is not line and len(error.trace) < 5:
                        error.trace.append(line)
                    raise
            for heading, run in list(self.settlers):
                if self.trace is not None:
                    self.traced(heading, "everything settled" + (f" after line {line.number}" if line else ""))
                try:
                    run(self)
                except EnglishError as error:
                    for where in (heading, line):
                        if where is not None and error.line is not where and len(error.trace) < 5:
                            error.trace.append(where)
                    raise
        finally:
            self.settling = False
            self.changed = False

    KEEP_ROUNDS = 10

    def keep(self):
        """Make every kept property and adjective ("Keep ...") match what it is kept as,
        at the end of a turn and before the settled blocks: again while that changes
        something, up to KEEP_ROUNDS rounds. Their changes set off reactions as usual."""
        for _ in range(self.KEEP_ROUNDS):
            changed = []
            for line, keeper in list(self.keepers):
                if self.trace is not None:
                    self.traced(line, "the end of a turn")
                changed += keeper(self)
            if not changed:
                return
        names = join(dict.fromkeys(changed))
        raise EnglishError(f"These kept values would not settle: after {self.KEEP_ROUNDS} rounds, {names} still "
                           "changed.", stage="run", teach="keep_rounds",
                           hint="Look for kept values that are worked out from each other in a circle.")

    # Events from outside the program ---------------------------------------

    def event(self, change):
        """Bring in something that happened outside the program, such as a click.

        `change()` changes things directly (`thing.fields[...] = ...`,
        `thing.marks.add(...)`, `thing.marks.discard(...)`). It is treated as one
        sentence: the rules are checked for the things it changed, and the
        reactions it sets off are carried out. On a problem, everything is put
        back, as by a failed "Try", and the EnglishError is raised.

        Returns True, or False without calling `change` once the program has
        ended. See englishscript/libraries/__init__.py.
        """
        if self.busy:
            raise RuntimeError(
                "world.event() was called while a sentence or another event is being carried out; "
                "an event can only come in between them."
            )
        if self.ended:
            return False
        self.busy = True
        limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(limit, RECURSION_LIMIT))
        restore, states = self._snapshot(self.globals)
        try:
            with no_digit_limit():
                before = self.noting() if self.reactions else None
                change()
                self.indexes = {}  # the change was made directly, so the indexes are built again
                self._check_rules(states)
                if before is not None:
                    self.react(before)
                if self.settlers or self.keepers:  # an event is a turn
                    self.changed = True
                    self.settle()
        except _EndProgram:
            self.ended = True  # what was changed stays, as with "End the program." anywhere
        except RecursionError:
            restore()
            raise EnglishError("This program nests more deeply than I can follow.", stage="run", teach="depth") from None
        except BaseException:
            restore()
            raise
        finally:
            self.busy = False
            sys.setrecursionlimit(limit)
        return True

    def _check_rules(self, states):
        """The never/always rules of every thing whose properties an event changed."""
        for thing, fields, _, _ in sorted(states, key=lambda state: state[0].serial):
            if thing.removed or thing.fields == fields:
                continue
            for rule in self.rules.get(thing.kind, ()):
                if not rule.fn(self, thing):
                    raise EnglishError(f'That would break a rule: "{rule.text}"', stage="run", recoverable=True,
                                       hint=f"(It was {thing.name} that changed.)", teach="rule_broken")


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
                           stage="run", recoverable=True, teach="file") from None


def write_file(path, text, append):
    try:
        with open(path, "a" if append else "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except (OSError, ValueError) as error:
        raise EnglishError(f"I couldn't write to the file {path}: {_reason(error)}.",
                           stage="run", recoverable=True, teach="file") from None


def split_lines(text):
    """Lines split on any line break, without an empty last line."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[-1] == "":
        lines.pop()
    return tuple(lines)


# ------------------------------------------------------------- reading values

_NUMBER = re.compile(r"-?(?:[1-9][0-9]{0,2}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?")  # digits 0 to 9 only


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


# ------------------------------------------------------------- asking a model
#
# "Ask the model" and "Judge" (section 7.8). What is asked is handed to whoever
# listens (World.model, World.judge); what comes back is read and checked here.

ITEM_PLURALS = {"number": "numbers", "money": "money", "text": "text", "percent": "percentages"}


def expected(shape):
    """What a reply of `shape` has to be, in words: 'a number, such as 7 or 2.5'."""
    kind = shape["type"]
    if kind == "choice":
        words = shape["choices"]
        said_as = "one of " + ", ".join(words[:-1]) + " or " + words[-1]
    elif kind == "list":
        said_as = f"a list of {ITEM_PLURALS[shape['items']]}, one item to a line"
    else:
        said_as = {
            "text": "text", "number": "a number, such as 7 or 2.5",
            "money": "an amount of money, such as $5 or $2.50", "percent": "a percentage, such as 10%",
            "yes or no": "yes or no",
        }[kind]
    if shape["optional"]:
        said_as += ', or "nothing"'
    return said_as


def shortened(text, most=60):
    """A reply as a message quotes it: on one line, and cut short after `most` letters."""
    text = " ".join(str(text).split())
    return text if len(text) <= most else text[:most].rstrip() + "..."


def read_model_reply(text, shape):
    """A model's reply read as `shape` (see World.model): (True, the value), or (False, the
    part that could not be read). Each value is read by read_reply, as a person's reply is.
    A list is one item to a line; blank lines are passed over."""
    if shape["optional"] and text.strip().lower() == "nothing":
        return True, None
    kind = shape["type"]
    if kind == "choice":
        wanted = " ".join(text.split()).lower()
        for choice in shape["choices"]:
            if choice.lower() == wanted:
                return True, choice
        return False, text
    if kind == "list":
        items = []
        for line in split_lines(text):
            if not line.strip():
                continue
            value = read_reply(line, shape["items"])
            if value is None:
                return False, line
            items.append(value)
        return True, tuple(items)
    value = read_reply(text, kind)
    return (False, text) if value is None else (True, value)


def chance_of(value):
    """A probability a judge gave, as an exact fraction from 0 to 1, or None if it is not one."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, Fraction)):
        chance = Fraction(value)
    elif isinstance(value, float) and math.isfinite(value):
        chance = Fraction(repr(value))  # the shortest form, so 0.1 is exactly 1/10
    else:
        return None
    return chance if 0 <= chance <= 1 else None


def verdict_of(result, choices):
    """{choice: chance} from a judge's answer, or None unless it gives one chance from 0
    to 1 to each of the choices and to nothing else. A choice is matched as a reply is."""
    if not isinstance(result, dict):
        return None
    by_word = {choice.lower(): choice for choice in choices}
    found = {}
    for key, value in result.items():
        choice = by_word.get(" ".join(key.split()).lower()) if isinstance(key, str) else None
        chance = chance_of(value)
        if choice is None or choice in found or chance is None:
            return None
        found[choice] = chance
    return found if len(found) == len(choices) else None


def said(value, type_):
    """A value as "Say" says it; a list as the language writes one ("a list of 3, 8 and 5")."""
    if value is None:
        return "nothing"
    type_ = type_.rstrip("?")
    if type_.startswith("list of "):
        items = [said(item, type_[len("list of "):]) for item in value]
        return "a list of " + join(items) if items else "an empty list"
    return fmt(value, type_)


def thing_state(thing, word, fields):
    """A thing written out for a model: "<kind> called <name>", then one "property: value"
    to a line, in the order the kind lists them (section 7.8)."""
    thing = alive(thing)
    lines = [f"{word} called {thing.name}"]
    lines += [f"{name}: {said(thing.fields.get(name), type_)}" for name, type_ in fields]
    return "\n".join(lines)


# -------------------------------------------------------------- formatting


def fmt(value, type_):
    """Render a value the way a person would write it."""
    if value is None:
        return "nothing"
    type_ = type_.rstrip("?")  # "money?" is money that turned out to be there
    if type_ == "money":
        cents = scaled(value, 2)
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


def scaled(value, places):
    """The value times 10 ** places, rounded to a whole number on the exact fraction:
    a half is rounded away from zero. Never through a float."""
    n = Fraction(value) * 10 ** places
    whole = (abs(n.numerator) * 2 + n.denominator) // (2 * n.denominator)  # floor(|n| + 1/2)
    return -whole if n < 0 else whole


def _number(value):
    """A number to at most four places, rounded exactly; never "-0"."""
    value = Fraction(value)
    if value.denominator == 1:
        return f"{value.numerator:,}"
    n = scaled(value, 4)
    sign = "-" if n < 0 else ""
    whole, rest = divmod(abs(n), 10_000)
    return f"{sign}{whole:,}" + f".{rest:04d}".rstrip("0").rstrip(".")


# ------------------------------------------------------------- arithmetic

PLACES = 12  # how many decimal places a power or a root that does not come out exactly is worked out to


def _problem(message, hint=None, teach="rounding"):
    return EnglishError(message, stage="run", recoverable=True, hint=hint, teach=teach)


def remainder(value, divisor):
    """What is left after taking away the divisor as many whole times as it goes,
    rounding down: it has the sign of the divisor (or is 0), so the remainder of
    -7 divided by 2 is 1, and of 7 divided by -2 is -1."""
    if divisor == 0:
        raise _problem("I can't divide by zero, so there is no remainder.", teach="zero")
    return value - divisor * (Fraction(value) / divisor).__floor__()


def rounded(value, step, how):
    """The value rounded to a whole number of steps: "nearest" (a half away from
    zero), "up" or "down" (towards more and towards less)."""
    if step <= 0:
        raise _problem(f"A value is rounded to the nearest step of more than nothing, not {_plain(step)}.",
                       teach="rounding")
    count = Fraction(value) / step
    if how == "up":
        whole = -((-count).__floor__())
    elif how == "down":
        whole = count.__floor__()
    else:
        whole = (abs(count.numerator) * 2 + count.denominator) // (2 * count.denominator)
        whole = -whole if count < 0 else whole
    return whole * step


def _plain(value):
    return _number(value)


def _root(n, k):
    """The whole k-th root of the whole number n >= 0, rounded down."""
    if n < 2:
        return n
    x = 1 << ((n.bit_length() + k - 1) // k)  # more than the root
    while True:
        y = ((k - 1) * x + n // x ** (k - 1)) // k
        if y >= x:
            return x
        x = y


def _to_places(value, k):
    """The k-th root of the fraction `value` >= 0, exactly if it is a fraction, else to PLACES places,
    a half rounded away from zero."""
    value = Fraction(value)
    p, q = value.numerator, value.denominator
    rp, rq = _root(p, k), _root(q, k)
    if rp ** k == p and rq ** k == q:
        return Fraction(rp, rq)
    scale = 10 ** (PLACES + 1)
    tenfold = _root(p * scale ** k // q, k)  # the root times 10 ** (PLACES + 1), rounded down
    return Fraction((tenfold + 5) // 10, 10 ** PLACES)


def square_root(value):
    if value < 0:
        raise _problem(f"A negative number, {_plain(value)}, has no square root.", teach="rounding")
    return _to_places(value, 2)


def power(base, exponent):
    """The base raised to the power: exact for a whole exponent; otherwise worked out
    to PLACES decimal places from the exact fractions, never through a float."""
    base, exponent = Fraction(base), Fraction(exponent)
    if exponent.denominator == 1:
        if base == 0 and exponent < 0:
            raise _problem("Nothing raised to a negative power: that would divide by zero.", teach="zero")
        return base ** int(exponent)
    if base < 0:
        raise _problem(f"A negative number, {_plain(base)}, can't be raised to a power that is not whole.",
                       teach="rounding")
    if base == 0:
        if exponent < 0:
            raise _problem("Nothing raised to a negative power: that would divide by zero.", teach="zero")
        return Fraction(0)
    whole = base ** abs(exponent.numerator)  # then the root, then turned over if the power is negative
    root = _to_places(whole, exponent.denominator) if exponent > 0 else _to_places(1 / whole, exponent.denominator)
    return root

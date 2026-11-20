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

Types are plain strings: "number", "money", "text", "percent", the name of a
kind, or any of those followed by "?" for a value that may be nothing. The
word `nothing` on its own has the type "nothing".
"""
from __future__ import annotations

import difflib
import sys
from contextlib import contextmanager
from dataclasses import dataclass, field
from fractions import Fraction

from .lexer import EnglishError, Token, read_source, tokenize
from .runtime import Env, Thing, World, fmt

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
}
LOOP_LIMIT = 10_000
CALL_LIMIT = 200
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


def cap(text):
    """Capitalise the first letter, for a message that opens with a quoted phrase."""
    return text[:1].upper() + text[1:]


# ------------------------------------------------------------ leaving early


class _Signal(Exception):
    """Not an error: how Stop, Skip and The answer is leave a block."""


class _StopVerb(_Signal):
    pass


class _EndProgram(_Signal):
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


# --------------------------------------------------------------- vocabulary


@dataclass
class Kind:
    name: str
    plural: str
    line: object
    fields: dict = field(default_factory=dict)  # name -> type
    props: dict = field(default_factory=dict)  # name -> Prop
    adjectives: dict = field(default_factory=dict)  # name -> Adj
    rules: list = field(default_factory=list)  # [Rule]


@dataclass
class Prop:
    name: str
    type: str
    fn: object  # (world, thing) -> value
    source: str


@dataclass
class Adj:
    name: str
    fn: object  # (world, thing) -> bool
    source: str


@dataclass
class Rule:
    fn: object  # (world, thing) -> bool, True when the rule holds
    text: str


@dataclass
class Param:
    name: str
    type: str
    prep: object  # None for the direct object

    def slot(self):
        return f"<{article(self.name)}>"


@dataclass
class Proc:
    verb: str
    params: list
    line: object
    body: list = None

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

    def usage(self):
        return " ".join([f"the {self.name}"] + [f"{p.prep} {p.slot()}" for p in self.params])


@dataclass
class Coll:
    kind: str
    fn: object  # env -> [Thing]


class Binding:
    __slots__ = ("name", "type", "focus", "let", "fixed")

    def __init__(self, name, type_, focus=False, let=False, fixed=False):
        self.name = name
        self.type = type_
        self.focus = focus  # can a pronoun refer to it?
        self.let = let  # can it be changed with Set/Add/...?
        self.fixed = fixed  # made with "always"


class Scope:
    def __init__(self, parent=None):
        self.parent = parent
        self.names = {}

    def find(self, name):
        scope = self
        while scope is not None:
            if name in scope.names:
                return scope.names[name]
            scope = scope.parent
        return None

    def visible(self):
        seen, scope = {}, self
        while scope is not None:
            for name, b in scope.names.items():
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

    def expect_word(self, word, message=None, hint=None):
        if not self.eat_word(word):
            self.fail(message or f'I expected "{word}" here.', hint=hint)

    def expect_punct(self, mark):
        if not self.eat_punct(mark):
            self.fail(f'I expected "{mark}" here.')

    def prev_end(self, default):
        return self.toks[self.i - 1].end if self.i > 0 else default

    def fail(self, message, tok=None, hint=None):
        tok = tok or self.peek()
        raise EnglishError(message, self.line, tok.col, max(1, len(tok.text)), hint)

    def fail_span(self, message, span, hint=None):
        raise EnglishError(message, self.line, span[0], max(1, span[1] - span[0]), hint)


# ----------------------------------------------------------------- compiler


class Compiler:
    def __init__(self):
        self.kinds = {}
        self.nouns = {}  # singular or plural word -> (kind, is_plural)
        self.names = {}  # lowercased instance name -> (display name, kind)
        self.procs = {}
        self.workouts = {}
        self.member_names = {"name"}
        self.adjective_names = set()
        self.globals = Scope()
        self.scope = self.globals
        self.notes = []
        self.line = None
        self._uid = 0
        # Where the sentence being compiled sits.
        self.verb = None  # the verb whose block this is, if any
        self.workout = None  # the worked-out value whose block this is, if any
        self.loops = []  # loops around the sentence: [{"id", "noun"}]
        self.present = NONE  # keys known not to be nothing at this point

    # ------------------------------------------------------------- helpers

    def note(self, text):
        entry = (self.line.number, text)
        if entry not in self.notes:
            self.notes.append(entry)

    def describe(self, type_):
        if type_ == "nothing":
            return "nothing"
        if is_opt(type_):
            return self.describe(base(type_)) + ", if any"
        plain = {
            "number": "a plain number", "money": "money", "text": "text",
            "percent": "a percentage", "truth": "a yes-or-no answer",
        }
        return plain.get(type_) or article(type_)

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
                s.fail(f"I expected {what} here.", tok)
            if tok.low in KEYWORDS:
                s.fail(f'"{tok.text}" already has a meaning in EnglishScript, so it can\'t be part of {what}.', tok)

    def need_kind(self, s, tok):
        if tok.kind == "WORD" and tok.low in self.kinds:
            return self.kinds[tok.low]
        if tok.kind != "WORD":
            s.fail('I expected a kind of thing here, like "dragon".', tok)
        s.fail(
            f"I don't know what {article(tok.text)} is.", tok,
            hint=f'Describe it first: "{article(tok.text).capitalize()} has ...".',
        )

    def type_name(self, s, tok, also=None):
        if tok.kind == "WORD" and (tok.low in BASE_TYPES or tok.low in self.kinds or tok.low == also):
            return tok.low
        known = list(BASE_TYPES) + list(self.kinds)
        s.fail(f'"{tok.text}" isn\'t a type I know.', tok, hint="Types: " + ", ".join(known) + ".")

    def bracket_type(self, s, also=None):
        """The inside of "(money)" or "(dragon, if any)". The "(" is already read."""
        type_ = self.type_name(s, s.next(), also)
        if s.eat_punct(","):
            if not (s.eat_word("if") and s.eat_word("any")):
                s.fail('After the comma I expected "if any".')
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
                        hint='To test for it, write "is nothing" or "is not nothing".')
        if is_opt(expr.type):
            check = expr.check or f"If {expr.text} is not nothing:"
            s.fail_span(
                f"{cap(expr.text)} may be nothing.", expr.span,
                hint=f'Check first with "{check}", or give a stand-in with "or else".',
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
        if name in K.fields:
            return K.fields[name], (lambda world, thing: thing.fields[name])
        if name in K.props:
            return K.props[name].type, K.props[name].fn
        if name == "name":
            return "text", (lambda world, thing: thing.name)
        return None

    def member_list(self, kind):
        K = self.kinds[base(kind)]
        return ["name"] + list(K.fields) + list(K.props)

    def match_member(self, s, kind, offset=0):
        return self.match_words(s, self.member_list(kind), offset)

    def no_member(self, s, kind, offset=0):
        kind = base(kind)
        tok = s.peek(offset)
        what = f'no "{tok.text}"' if tok.kind == "WORD" else "nothing by that description"
        s.fail(
            f"{article(kind).capitalize()} has {what}.", tok,
            hint="It has: " + ", ".join(self.member_list(kind)) + ".",
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

    def unknown_adjective(self, s, tok, kind):
        s.fail(
            f'I don\'t know what "{tok.text}" means for {article(kind)}.', tok,
            hint=f'Define it first: "{article(kind).capitalize()} is {tok.text} when ...".',
        )

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
            s.fail_span(f'{cap(left.text)} is never nothing here, so "or else" isn\'t needed.', left.span)
        want = base(left.type)
        if base(right.type) != want:
            s.fail_span(
                f"{cap(left.text)} is {self.describe(want)}, but the stand-in {right.text} is {self.describe(right.type)}.",
                right.span,
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
                s.fail_span(f"I can't make {self.describe(inner.type)} negative.", inner.span)
            fn = inner.fn
            return self.stamp(s, Expr(inner.type, lambda env: -fn(env)), tok.col)
        expr = self.primary(s)
        if expr.type == "percent" and s.at_word("of"):
            s.next()
            amount = self.unary(s)
            self.need(s, amount)
            if amount.type not in ("number", "money"):
                s.fail_span(f"I can't take a percentage of {self.describe(amount.type)}.", amount.span)
            pf, bf = expr.fn, amount.fn
            expr = self.stamp(s, Expr(amount.type, lambda env: pf(env) * bf(env)), expr.span[0])
        return expr

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
            s.fail_span(message, span, hint)
        lf, rf = left.fn, right.fn
        if op == "+":
            fn = lambda env: lf(env) + rf(env)
        elif op == "-":
            fn = lambda env: lf(env) - rf(env)
        elif op == "*":
            fn = lambda env: lf(env) * rf(env)
        else:
            def fn(env):
                divisor = rf(env)
                if divisor == 0:
                    raise EnglishError("I can't divide by zero.", stage="run")
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
            else:
                expr = self.bare_name(s)
        else:
            s.fail("I expected a value here.")
        self.stamp(s, expr, start)
        while s.peek().kind == "POS":
            if base(expr.type) not in self.kinds:
                s.fail_span(f"{expr.text} is {self.describe(expr.type)}, so it has no properties.", expr.span)
            match = self.match_member(s, expr.type, 1)
            if not match:
                if dangling_ok:
                    break
                self.no_member(s, expr.type, 1)
            s.next()
            expr = self.member(s, expr, match, start)
        return expr

    def pronoun(self, s, tok):
        candidates = [b for b in self.scope.visible().values() if b.focus]
        if not candidates:
            s.fail(
                f'"{tok.text}" doesn\'t refer to anything here.', tok,
                hint='A pronoun needs one thing in view: use it inside "For each ...", "To ..." or a definition.',
            )
        if len(candidates) > 1:
            suffix = "" if tok.low in PRONOUNS else "'s"
            if suffix and s.peek().kind == "WORD":
                suffix += " " + s.peek().text
            options = join_words([f"the {b.name}" for b in candidates], "or")
            s.fail(
                f'"{tok.text}" is ambiguous here: it could mean {options}.', tok,
                hint=f'Say which one, e.g. "the {candidates[0].name}{suffix}".',
            )
        b = candidates[0]
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
            s.fail("I expected a value here.", tok)
        noun = self.nouns.get(tok.low)
        if noun:
            kind = noun[0]
            named = [disp for disp, k in self.names.values() if k == kind]
            hint = f'Name one ({join_words(named, "or")}), or' if named else "You could"
            s.fail(
                f'Which {kind}? Nothing here says which one "{shown}" is.', tok,
                hint=f'{hint} go through them with "For each {kind}:".',
            )
        known = [disp for disp, _ in self.names.values()]
        known += [f"the {n}" for n in self.scope.visible() if not n.startswith("\0")]
        s.fail(
            f'I don\'t know what "{shown}" refers to.', tok,
            hint=("I know: " + ", ".join(known) + ".") if known else None,
        )

    def the_phrase(self, s):
        the = s.next()
        if s.at_words("number", "of"):
            s.next()
            s.next()
            coll = self.collection(s, plural=True)
            cf = coll.fn
            return Expr("number", lambda env: Fraction(len(cf(env))))
        match = self.match_words(s, self.workouts)
        if match:
            return self.use_workout(s, match)
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
                    s.fail(f'{article(coll.kind).capitalize()} has no "{name}" to add up.', name_tok)
                type_, get = found
                if base(type_) not in ("number", "money"):
                    s.fail(f'I can\'t add up "{name}": it is {self.describe(type_)}.', name_tok)
                cf = coll.fn

                def add_up(env):
                    values = (get(env.world, x) for x in cf(env))
                    return sum((v for v in values if v is not None), Fraction(0))
                return Expr(base(type_), add_up)
            owner = self.primary(s)
            if base(owner.type) not in self.kinds:
                s.fail_span(f"{owner.text} is {self.describe(owner.type)}, so it has no {name}.", owner.span)
            if not self.getter(base(owner.type), name):
                s.fail(
                    f'{article(base(owner.type)).capitalize()} has no "{name}".', name_tok,
                    hint="It has: " + ", ".join(self.member_list(owner.type)) + ".",
                )
            return self.stamp(s, self.member_expr(owner, name), the.col)
        match = self.match_words(s, self.scope.visible())
        if match:
            return self.variable(s, match)
        if words and s.toks[j].is_word("of") and not self.scope.find(words[0]) and words[0] not in self.nouns:
            s.fail(
                f'Nothing has a property called "{name}".', s.peek(),
                hint='Give a kind that property ("A dragon has ...") or define it ("The ... of a dragon is ...").',
            )
        self.unknown(s, the=True)

    def use_workout(self, s, match):
        """'the bounty for Smaug': a value worked out by a "To work out" block."""
        name, count = match
        for _ in range(count):
            s.next()
        w = self.workouts[name]
        by_prep = {p.prep: p for p in w.params}
        usage = "It goes: " + w.usage() + "."
        args = {}
        while s.peek().kind == "WORD" and s.peek().low in by_prep and by_prep[s.peek().low].name not in args:
            ptok = s.next()
            param = by_prep[ptok.low]
            if s.at_end():
                s.fail(f"I expected {article(param.name)} here.", hint=usage)
            value = self.primary(s)  # one value; arithmetic in a role needs brackets
            if not self.fits(value.type, param.type):
                if base(value.type) == base(param.type):
                    self.need(s, value)
                s.fail_span(
                    f'"The {w.name}" wants {article(param.name)} here, '
                    f"but {value.text} is {self.describe(value.type)}.", value.span, hint=usage,
                )
            args[param.name] = value
        missing = [p for p in w.params if p.name not in args]
        if missing:
            wanted = join_words(f"{p.prep} {article(p.name)}" for p in missing)
            s.fail(f'"The {w.name}" is missing something: {wanted}.', hint=usage)
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
                    )
                for step in w.body:
                    step(frame)
            except _Answer as answer:
                return answer.value
            finally:
                world.depth -= 1
            raise EnglishError(f'"The {w.name}" finished without an answer.', stage="run")
        return Expr(w.type, fn)

    def template(self, s, tok):
        """A quoted text, with {expressions} filled in when it is said."""
        raw, start = tok.value, tok.col + 1
        parts, i = [], 0
        while True:
            j = raw.find("{", i)
            if j < 0:
                parts.append(raw[i:])
                break
            parts.append(raw[i:j])
            k = raw.find("}", j)
            if k < 0:
                raise EnglishError('This "{" is never closed.', s.line, start + j, 1)
            toks = tokenize(s.line.text, s.line, start + j + 1, start + k)
            toks.append(Token("END", "", start + k))
            sub = Sentence(s.line, toks)
            if sub.at_end():
                sub.fail("There is nothing between these braces.")
            inner = self.expr(sub)
            self.end(sub)
            parts.append(inner)
            i = k + 1

        def fn(env):
            return "".join(p if isinstance(p, str) else fmt(p.fn(env), p.type) for p in parts)
        return Expr("text", fn)

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
                if not plural:
                    s.fail(
                        'I expected a kind of thing here, like "dragon".',
                        hint=("Kinds: " + ", ".join(self.kinds) + ".") if self.kinds else None,
                    )
                owner = self.primary(s, dangling_ok=True)
                if s.peek().kind != "POS":
                    s.fail_span(
                        'I expected a group of things here, like "all dragons" or "Smaug\'s treasures".',
                        owner.span,
                    )
                s.next()
        adjectives = []
        while True:
            tok = s.peek()
            if tok.kind != "WORD":
                s.fail('I expected a kind of thing here, like "dragon".')
            if tok.low in self.nouns:
                break
            adjectives.append(s.next())
        kind, is_plural = self.nouns[tok.low]
        K = self.kinds[kind]
        noun = s.next()
        if plural and not is_plural:
            s.fail(f'More than one is meant here, so write "{K.plural}".', noun)
        if not plural and is_plural:
            s.fail(f'"For each" takes them one at a time, so write "{K.name}".', noun)
        tests = []
        for adj_tok in adjectives:
            adj = K.adjectives.get(adj_tok.low)
            if not adj:
                self.unknown_adjective(s, adj_tok, kind)
            tests.append(adj.fn)
            self.note(f'"{adj_tok.text}" → {adj.source}')
        if owner is None and s.at_word("of"):
            s.next()
            owner = self.primary(s)
        link = None
        if owner is not None:
            self.need(s, owner)
            if owner.type not in self.kinds:
                s.fail_span(f"{owner.text} is {self.describe(owner.type)}, so nothing can belong to it.", owner.span)
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
                mine = owner_fn(env)
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
                f"I don't know how {article(K.name)} belongs to {article(owner.type)}.", noun,
                hint=f'Give it a field that points at one, e.g. "{article(K.name).capitalize()} has an owner ({owner.type})."',
            )
        s.fail(
            f'"{phrase}" can be read {len(links)} ways: {article(K.name)} is tied to '
            f"{article(owner.type)} by its {join_words(links)}.", noun,
            hint=f'Say which: "{K.plural} whose {links[0]} is {owner.text}".',
        )

    # ---------------------------------------------------------- conditions

    def condition(self, s):
        """Comparisons joined by "and" or by "or".

        Each later comparison is only reached when the earlier ones went the
        right way, so it may rely on what they checked: after "X has a mount
        and", X's mount is known to be there.
        """
        saved = self.present
        try:
            parts = [self.cond_atom(s)]
            ops = []
            while s.at_word("and", "or"):
                op = s.next()
                if ops and op.low != ops[0].low:
                    s.fail(
                        'This mixes "and" with "or", so it can be read two ways.', op,
                        hint="Put brackets around the part that belongs together:\n"
                        "(A and B) or C   -or-   A and (B or C).",
                    )
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
            s.next()
            negated = s.eat_word("not")
            cond = self.tail(s, left)
            return self.negate(cond) if negated else cond
        if tok.is_punct("<", ">", "<=", ">=", "="):
            s.next()
            return self.compare(s, tok.text, left, self.expr(s))
        s.fail('I expected a comparison here, such as "is", "is less than" or "is at least".')

    def has_test(self, s, left):
        """'Robin has a mount' / 'Robin has no mount': is a property there?"""
        s.next()  # has
        self.need(s, left)
        if left.type not in self.kinds:
            s.fail_span(f"{left.text} is {self.describe(left.type)}, so it has no properties.", left.span)
        without = bool(s.eat_word("no"))
        if not without and not s.eat_word("a", "an"):
            s.fail('After "has" I expected "a", "an" or "no".')
        match = self.match_member(s, left.type)
        if not match:
            self.no_member(s, left.type)
        name_tok = s.peek()
        declared, _ = self.getter(left.type, match[0])
        if not is_opt(declared):
            s.fail(
                f"{article(left.type).capitalize()} always has {article(match[0])}, so there is nothing to check.",
                name_tok,
                hint=f'Only a property described with "if any" can be missing.',
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
                s.fail_span(f"{cap(left.text)} can't be nothing here, so there is nothing to check.", left.span)
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
                return Expr("truth", lambda env: test(env.world, lf(env)))
            starts_value = (
                tok.low in ("the",) + POSSESSIVES + PRONOUNS
                or self.match_words(s, self.names)
                or self.match_words(s, self.scope.visible())
            )
            if not starts_value:
                self.unknown_adjective(s, tok, left.type)
        return self.compare(s, "=", left, self.expr(s))

    def divisible(self, s, left, right):
        for side in (left, right):
            self.need(s, side)
            if side.type != "number":
                s.fail_span(
                    f'"Divisible by" is about plain numbers, but {side.text} is {self.describe(side.type)}.',
                    side.span,
                )
        lf, rf = left.fn, right.fn

        def fn(env):
            divisor = rf(env)
            if divisor == 0:
                raise EnglishError("Nothing is divisible by zero.", stage="run")
            return (lf(env) / divisor).denominator == 1
        cond = Expr("truth", fn)
        cond.subject = left
        return cond

    def compare(self, s, op, left, right):
        self.need(s, left)
        self.need(s, right)
        lt, rt = left.type, right.type
        ordered = ("number", "money", "percent")
        if lt != rt or (op != "=" and lt not in ordered):
            span = (left.span[0], right.span[1])
            if lt != rt:
                s.fail_span(f"I can't compare {self.describe(lt)} with {self.describe(rt)}.", span)
            s.fail_span("Only numbers, money and percentages can be more or less than each other.", span)
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
            while i < len(lines):
                line = lines[i]
                if line.tokens[0].is_word("if"):
                    i, step = self.if_chain(lines, i)
                    steps.append(self.located(line, step))
                else:
                    step = self.statement(line)
                    if step is not None:
                        steps.append(self.located(line, step))
                    i += 1
            return steps
        finally:
            self.scope = saved

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
        if yes and not opens:
            raise EnglishError(
                "This needs a block: end it with a colon and indent the sentences that belong to it.",
                s.line, len(s.line.text) - 1, 1,
            )
        if opens and not yes:
            raise EnglishError(
                "This sentence doesn't open a block, so it should end with a period.",
                s.line, len(s.line.text) - 1, 1,
                hint="Only If, Otherwise, For each, Repeat, While and To take a colon.",
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
                Sentence(lines[i]).fail('Nothing can follow a plain "Otherwise:".')
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
                scope = Scope(self.scope)
                if binding is not None:
                    scope.names[binding.name] = binding
                steps = self.block(lines, scope)
                if start <= self.present:
                    break
                self.present = start & self.present
                del self.notes[mark:]
        finally:
            self.loops.pop()
        self.present = before & self.present
        return loop["id"], steps

    # ---------------------------------------------------------- statements

    def statement(self, line):
        self.line = line
        s = Sentence(line)
        first = s.peek()
        if first.kind != "WORD":
            s.fail("A sentence starts with a word.")
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
            elif nxt.kind == "POS":
                definition = self.define_rule
            else:
                s.fail(
                    'After a kind I expected "has", "is" or "\'s".', nxt,
                    hint='For example: "A dragon has an age (number)."  or  "A dragon is ancient when ...".',
                )
        elif word == "the":
            definition = self.define_property
        elif word == "to":
            definition = self.define_procedure
        elif word == "there":
            definition = self.create_thing
        if definition:
            if not top:
                s.fail("This belongs at the top level, not inside a block.")
            self.needs_block(s, word == "to")
            return definition(s)

        if word == "otherwise":
            s.fail('"Otherwise" has to come straight after an "If" block.')
        if word == "for" and s.peek(1).is_word("example"):
            self.needs_block(s, False)
            return self.example(s)
        blocks = {"for": self.for_each, "repeat": self.repeat, "while": self.while_loop}
        simple = {
            "let": self.let, "set": self.assign, "add": self.assign, "subtract": self.assign,
            "multiply": self.assign, "divide": self.assign, "say": self.say,
            "stop": self.stop, "skip": self.skip, "end": self.end_program,
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
        known = list(simple) + ["if", "for", "repeat", "while"] + list(self.procs)
        close = difflib.get_close_matches(word, known, n=1)
        hint = f'Did you mean "{close[0].capitalize()}"?' if close else (
            f'Teach it to me first: "To {word} ...:" followed by an indented block.'
        )
        s.fail(f'I don\'t know how to "{first.text}".', hint=hint)

    # definitions --------------------------------------------------------

    def define_kind(self, s):
        s.next()
        ktok = s.next()
        self.check_new_name(s, [ktok], "the name of a kind")
        name = ktok.low
        if name in self.kinds:
            s.fail(f"{article(name).capitalize()} was already described on line {self.kinds[name].line.number}.", ktok)
        s.next()  # has
        K = Kind(name, pluralize(name), s.line)
        while True:
            if not s.eat_word("a", "an"):
                s.fail('I expected a property here, like "a hoard (money)".')
            toks = []
            while s.peek().kind == "WORD" and not s.at_word("and"):
                toks.append(s.next())
            if not toks:
                s.fail("I expected the name of a property here.")
            self.check_new_name(s, toks, "a property name")
            fname = " ".join(t.low for t in toks)
            if fname in K.fields:
                s.fail(f'"{fname}" is listed twice.', toks[0])
            if fname in self.workouts:
                s.fail(f'"{fname}" is already something that is worked out, so a property can\'t share its name.', toks[0])
            if not s.eat_punct("("):
                s.fail(
                    f'What sort of value is "{fname}"?', toks[0],
                    hint=f'Say so in brackets, e.g. "{article(fname)} (money)".\n'
                    "Types: number, money, text, percent, or a kind you have described.",
                )
            K.fields[fname] = self.bracket_type(s, also=name)
            if s.at_end():
                break
            comma, conj = s.eat_punct(","), s.eat_word("and")
            if not (comma or conj):
                s.fail('I expected "," or "and" between properties.')
        self.kinds[name] = K
        self.nouns[name] = (name, False)
        self.nouns[K.plural] = (name, True)
        self.member_names.update(K.fields)

    def define_adjective(self, s):
        s.next()
        K = self.need_kind(s, s.next())
        s.next()  # is
        atok = s.next()
        self.check_new_name(s, [atok], "an adjective")
        if atok.low in K.adjectives:
            s.fail(f'"{atok.text}" is already defined for {article(K.name)}.', atok)
        s.expect_word("when", hint='For example: "A dragon is ancient when its age is at least 500."')
        start = s.peek().col
        self.scope = self.subject_scope(K.name)
        try:
            with self.fresh():
                cond = self.condition(s)
                self.end(s)
        finally:
            self.scope = self.globals
        source = s.line.text[start:].rstrip(".").strip()
        K.adjectives[atok.low] = Adj(atok.low, self.subject_fn(K.name, cond.fn), source)
        self.adjective_names.add(atok.low)

    def define_rule(self, s):
        s.next()
        K = self.need_kind(s, s.next())
        s.next()  # 's
        match = self.match_member(s, K.name)
        if not match:
            self.no_member(s, K.name)
        if match[0] not in K.fields:
            s.fail(f'A never/always rule has to be about a stored property, and "{match[0]}" is worked out or fixed.')
        self.scope = self.subject_scope(K.name)
        try:
            with self.fresh():
                kind = K.name
                subject = Expr(kind, lambda env: env.get(kind))
                subject.span = (s.peek().col, s.peek().col)
                left = self.member(s, subject, match)
                s.expect_word("is")
                mode = s.next()
                if not mode.is_word("never", "always"):
                    s.fail('I expected "never" or "always" here.', mode,
                           hint='For example: "A knight\'s purse is never less than $0."')
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
            )
        s.next()
        s.next()
        K = self.need_kind(s, s.next())
        self.check_new_name(s, toks, "a property name")
        name = " ".join(t.low for t in toks)
        if name in K.fields or name in K.props:
            s.fail(f'{article(K.name).capitalize()} already has "{name}".', toks[0])
        if name in self.workouts:
            s.fail(f'"{name}" is already something that is worked out, so a property can\'t share its name.', toks[0])
        s.expect_word("is")
        start = s.peek().col
        self.scope = self.subject_scope(K.name)
        try:
            with self.fresh():
                value = self.expr(s)
                self.end(s)
        finally:
            self.scope = self.globals
        if value.type == "nothing":
            s.fail_span("A property that is always nothing has no use.", value.span)
        source = s.line.text[start:].rstrip(".").strip()
        K.props[name] = Prop(name, value.type, self.subject_fn(K.name, value.fn), source)
        self.member_names.add(name)

    def param(self, s, prep, stops=PREPOSITIONS):
        if not s.eat_word("a", "an"):
            s.fail('I expected "a" or "an" here, introducing what this works on.')
        toks = []
        while s.peek().kind == "WORD" and s.peek().low not in stops:
            toks.append(s.next())
        if not toks:
            s.fail("I expected a name here.")
        name = " ".join(t.low for t in toks)
        if s.eat_punct("("):
            self.check_new_name(s, toks, "a name")
            type_ = self.bracket_type(s)
        elif name in self.kinds:
            type_ = name
        else:
            s.fail(
                f"What is {article(name)}?", toks[0],
                hint=f'Describe that kind first, or give this a type: "{article(name)} (money)".',
            )
        return Param(name, type_, prep)

    def role_scope(self, s, params, at):
        scope = Scope(self.globals)
        for p in params:
            if p.name in scope.names:
                s.fail(
                    f'There are two things called "{p.name}" here, so "the {p.name}" would be ambiguous.', at,
                    hint=f'Give them their own names: "a first one ({p.type})" and "a second one ({p.type})".',
                )
            if self.globals.find(p.name) or p.name in self.workouts:
                s.fail(f'"{p.name}" already means something at the top level.', at)
            scope.names[p.name] = Binding(p.name, p.type, focus=p.type in self.kinds)
        return scope

    def define_procedure(self, s):
        s.next()  # to
        if s.at_words("work", "out", "the"):
            return self.define_workout(s)
        vtok = s.next()
        self.check_new_name(s, [vtok], "a verb")
        verb = vtok.low
        if verb in self.procs:
            s.fail(f'I already know how to "{verb}" (line {self.procs[verb].line.number}).', vtok)
        params = []
        if s.at_word("a", "an"):
            params.append(self.param(s, None))
        while not s.at_end():
            ptok = s.next()
            if ptok.kind != "WORD" or ptok.low not in PREPOSITIONS:
                s.fail(
                    "I expected a preposition here, linking the next thing to the verb.", ptok,
                    hint="Such as: " + ", ".join(sorted(PREPOSITIONS)) + ".",
                )
            if any(p.prep == ptok.low for p in params):
                s.fail(f'"{ptok.text}" is used twice, so I couldn\'t tell the two apart.', ptok)
            params.append(self.param(s, ptok.low))
        scope = self.role_scope(s, params, vtok)
        proc = Proc(verb, params, s.line)
        self.procs[verb] = proc  # registered first, so it can call itself
        with self.fresh(verb=proc):
            proc.body = self.block(s.line.children, scope)

    def define_workout(self, s):
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
        if name in self.workouts:
            s.fail(f'I already know how to work out "the {name}" (line {self.workouts[name].line.number}).', toks[0])
        if name in self.member_names:
            s.fail(f'"{name}" is already a property, so something worked out can\'t share its name.', toks[0])
        if self.globals.find(name) or name in self.names or name in self.nouns:
            s.fail(f'"{name}" already means something.', toks[0])
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
        w = Workout(name, type_, params, s.line)
        self.workouts[name] = w  # registered first, so it can use itself
        with self.fresh(workout=w):
            w.body = self.block(s.line.children, scope)
        if not self.answers(w.body):
            raise EnglishError(
                "Not every path through this block reaches an answer.",
                s.line, s.toks[0].col, len(s.line.text.strip()),
                hint='Finish the block with "The answer is ...".',
            )

    def create_thing(self, s):
        s.next()  # there
        s.expect_word("is", hint='For example: "There is a dragon called Smaug whose age is 771."')
        if not s.eat_word("a", "an"):
            s.fail('I expected "a" or "an" here.')
        K = self.need_kind(s, s.next())
        s.expect_word("called", f"Every {K.name} needs a name: \"There is {article(K.name)} called ...\".")
        ntoks = []
        while s.peek().kind == "WORD" and not s.at_word("whose"):
            ntoks.append(s.next())
        if not ntoks:
            s.fail("I expected a name here.")
        self.check_new_name(s, ntoks, "a name")
        display = " ".join(t.text for t in ntoks)
        key = display.lower()
        if key in self.names or key in self.nouns or key in self.workouts or self.globals.find(key):
            s.fail(f'"{display}" already means something.', ntoks[0])
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
                f"{article(K.name).capitalize()} also needs {join_words(article(m) for m in missing)}.", ntoks[0],
                hint=f'Add: "whose {missing[0]} is ...".',
            )
        self.names[key] = (display, K.name)
        kind = K.name
        absent = [f for f in K.fields if f not in values]

        def step(env):
            world = env.world
            fields = {f: fn(env) for f, fn in values.items()}
            fields.update((f, None) for f in absent)
            thing = Thing(kind, display, fields)
            for rule in K.rules:
                if not rule.fn(world, thing):
                    raise EnglishError(f'{display} would break a rule: "{rule.text}"', stage="run")
            world.things.setdefault(kind, []).append(thing)
            world.named[key] = thing
        return step

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
        s.expect_word("be", hint='For example: "Let the total be 0."')
        self.check_new_name(s, toks, "a name")
        name = " ".join(t.low for t in toks)
        if self.scope.find(name) or name in self.names or name in self.workouts:
            s.fail(
                f'"{name}" already means something here.', toks[0],
                hint=f'To change it, write "Set {name} to ...".',
            )
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
        self.scope.names[name] = Binding(name, declared, let=not fixed, fixed=fixed)
        if is_opt(declared) and not is_opt(value.type) and value.type != "nothing":
            self.present = self.present | {("var", name)}
        self.note(f'"{name}" is {self.describe(declared)}')
        fn = value.fn

        def step(env):
            env.vars[name] = fn(env)
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
            thing = owner_fn(env)
            old = thing.fields[fname]
            thing.fields[fname] = value
            for rule in K.rules:
                if not rule.fn(env.world, thing):
                    thing.fields[fname] = old
                    raise EnglishError(
                        f'That would break a rule: "{rule.text}"', stage="run",
                        hint=f"({thing.name}'s {fname} is {fmt(old, ftype)} and would become {fmt(value, ftype)}.)",
                    )
        return put

    def assign(self, s):
        verb = s.next().low
        if verb == "set":
            target = self.target(s)
            s.expect_word("to", hint='For example: "Set the total to 0."')
            new = value = self.expr(s)
        elif verb in ("add", "subtract"):
            value = self.expr(s)
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
        return lambda env: put(env, fn(env))

    def say(self, s):
        if self.workout is not None:
            s.fail("Working something out can't say anything.",
                   hint="Say it from a verb, or where the worked-out value is used.")
        s.next()
        value = self.expr(s)
        self.end(s)
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
            loop = self.one_loop(s, "Stop repeating")["id"]

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
        tok = s.next()
        if tok.kind != "WORD":
            s.fail('I expected "round", or the noun of a For each.', tok)
        self.end(s)
        if tok.low == "round":
            found = self.one_loop(s, "Skip this round")
            if found["noun"]:
                s.fail('A "For each" has no rounds.', tok, hint=f'Write "Skip this {found["noun"]}."')
        else:
            matches = [loop for loop in self.loops if loop["noun"] == tok.low]
            if not matches:
                s.fail(f'There is no "For each {tok.text}" around this sentence.', tok)
            found = matches[-1]
        loop = found["id"]

        def step(env):
            raise _SkipRound(loop)
        step.leaves = True
        return step

    def end_program(self, s):
        s.next()
        s.expect_word("the", hint='Write "End the program."')
        s.expect_word("program", hint='Write "End the program."')
        self.end(s)
        if self.workout is not None:
            s.fail('Inside "To work out", finish with "The answer is ...".', s.toks[0])

        def step(env):
            raise _EndProgram()
        step.leaves = True
        return step

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
        s.expect_word("each", hint='For example: "For each dragon:"')
        coll = self.collection(s, plural=False)
        self.end(s)
        name = coll.kind
        if self.scope.find(name):
            s.fail(
                f'There is already a "{name}" in view here, so "the {name}" would mean two things.', s.toks[2],
                hint="Move this loop into its own \"To ...:\" block, where the names can differ.",
            )
        loop, body = self.loop_body(s.line.children, noun=name, binding=Binding(name, name, focus=True))
        items, run = coll.fn, self.run_block

        def step(env):
            for thing in items(env):
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
                raise EnglishError(f"I can't repeat something {fmt(n, 'number')} times.", stage="run")
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

    def run(self, out=print):
        world = World(out)
        limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(limit, 20_000))  # each English call costs several Python frames
        try:
            for step in self.steps:
                step(world.globals)
        except _EndProgram:
            pass
        except RecursionError:
            raise EnglishError("This program nests more deeply than I can follow.", stage="run") from None
        finally:
            sys.setrecursionlimit(limit)
        return world


def compile_source(source):
    """Compile a whole program. Raises EnglishError; runs nothing."""
    lines = read_source(source)
    compiler = Compiler()
    steps = compiler.block(lines, compiler.globals)
    return Program(steps, compiler.notes, compiler)

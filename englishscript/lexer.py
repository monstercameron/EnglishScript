"""Turns source text into sentences.

EnglishScript is line-based: one sentence per line, ending in a period (or a
colon when the sentence opens an indented block). This module splits each
sentence into tokens and nests the lines by indentation. It knows nothing about
what the words mean.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction


class EnglishError(Exception):
    """A problem with a program, phrased for the person who wrote it."""

    def __init__(self, message, line=None, col=None, width=1, hint=None, stage="compile"):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col
        self.width = width
        self.hint = hint
        self.stage = stage  # "compile" or "run"
        self.trace = []

    def render(self, filename=None, location=True):
        head = "I can't read this sentence" if self.stage == "compile" else "This went wrong while running"
        out = []
        if self.line is None:
            out.append(head + ":")
        else:
            where = f"line {self.line.number}"
            if filename:
                where = f"{filename}, {where}"
            out.append(f"{head} ({where}):" if location else f"{head}:")
            text = self.line.text
            lead = len(text) - len(text.lstrip())
            out.append("")
            out.append("    " + text.strip())
            if self.col is not None:
                out.append("    " + " " * max(0, self.col - lead) + "^" * max(1, self.width))
        out.append("")
        out.append("  " + self.message)
        if self.hint:
            out.extend("  " + h for h in self.hint.split("\n"))
        for caller in self.trace:
            out.append(f"  (while doing line {caller.number}: {caller.text.strip()})")
        return "\n".join(out)


@dataclass
class Token:
    kind: str  # WORD NUMBER MONEY PERCENT STRING POS PUNCT END
    text: str
    col: int
    value: object = None

    @property
    def low(self):
        return self.text.lower()

    @property
    def end(self):
        return self.col + len(self.text)

    def is_word(self, *words):
        return self.kind == "WORD" and self.low in words

    def is_punct(self, *marks):
        return self.kind == "PUNCT" and self.text in marks


@dataclass
class Line:
    number: int
    text: str
    indent: int
    tokens: list = field(default_factory=list)
    terminator: str = "."
    children: list = field(default_factory=list)


TOKEN_RE = re.compile(
    r"""
    (?P<STRING>"[^"]*")
  | (?P<MONEY>\$\d{1,3}(?:,\d{3})+(?:\.\d+)?|\$\d+(?:\.\d+)?)
  | (?P<PERCENT>\d+(?:\.\d+)?%)
  | (?P<NUMBER>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)
  | (?P<POS>'s\b)
  | (?P<WORD>[A-Za-z][A-Za-z0-9_]*)
  | (?P<PUNCT><=|>=|[()+\-*/<>=,.:])
  | (?P<WS>\s+)
    """,
    re.VERBOSE,
)


def tokenize(text, line, start, end):
    """Tokens for text[start:end]. Columns are positions in the whole line."""
    tokens = []
    pos = start
    while pos < end:
        m = TOKEN_RE.match(text, pos, end)
        if not m:
            if text[pos] == '"':
                raise EnglishError("This quotation is never closed.", line, pos, 1)
            raise EnglishError(f"I don't know what to do with {text[pos]!r}.", line, pos, 1)
        kind, raw = m.lastgroup, m.group()
        if kind != "WS":
            value = None
            if kind == "NUMBER":
                value = Fraction(raw.replace(",", ""))
            elif kind == "MONEY":
                value = Fraction(raw[1:].replace(",", ""))
            elif kind == "PERCENT":
                value = Fraction(raw[:-1]) / 100
            elif kind == "STRING":
                value = raw[1:-1]
            tokens.append(Token(kind, raw, pos, value))
        pos = m.end()
    return tokens


def _strip_comment(raw):
    in_string = False
    for i, ch in enumerate(raw):
        if ch == '"':
            in_string = not in_string
        elif ch == "#" and not in_string:
            return raw[:i]
    return raw


def read_source(source):
    """Source text -> top-level Lines, each with its indented children."""
    source = source.replace("“", '"').replace("”", '"').replace("’", "'")
    lines = []
    for number, raw in enumerate(source.splitlines(), 1):
        text = _strip_comment(raw).rstrip()
        if not text.strip():
            continue
        indent = len(text) - len(text.lstrip())
        line = Line(number, text, indent)
        if "\t" in text[:indent]:
            raise EnglishError("Indent with spaces, not tabs.", line, 0, indent)
        tokens = tokenize(text, line, indent, len(text))
        last = tokens[-1]
        end_col = len(text)
        if last.is_punct(".", ":"):
            line.terminator = last.text
            end_col = last.col
            tokens.pop()
        elif last.kind != "STRING":  # a closing quote may end a sentence
            raise EnglishError(
                "A sentence ends with a period, or with a colon when it opens a block.",
                line, len(text), 1,
            )
        if not tokens:
            raise EnglishError("There is no sentence here.", line, indent, 1)
        tokens.append(Token("END", "", end_col))
        line.tokens = tokens
        lines.append(line)
    return _nest(lines)


def _nest(lines):
    root = []
    stack = [(0, root)]
    prev = None
    for line in lines:
        if prev is None:
            if line.indent:
                raise EnglishError("The first sentence can't be indented.", line, 0, line.indent)
        elif line.indent > prev.indent:
            if prev.terminator != ":":
                raise EnglishError(
                    "This is indented, but the sentence before it doesn't open a block.",
                    line, 0, line.indent,
                    hint="Only a sentence ending in a colon can have sentences indented under it.",
                )
            stack.append((line.indent, prev.children))
        else:
            while stack[-1][0] > line.indent:
                stack.pop()
            if stack[-1][0] != line.indent:
                raise EnglishError(
                    "This indentation doesn't line up with any sentence above it.",
                    line, 0, max(1, line.indent),
                )
        stack[-1][1].append(line)
        prev = line
    _check_blocks(root)
    return root


def _check_blocks(lines):
    for line in lines:
        if line.terminator == ":" and not line.children:
            raise EnglishError(
                "This opens a block, but nothing is indented under it.",
                line, len(line.text) - 1, 1,
            )
        _check_blocks(line.children)

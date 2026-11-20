"""Rename a name throughout a program, and let the compiler judge the result.

    python -m englishscript.rename FILE "old name" "new name" [--write]

    from englishscript.rename import rename, RenameRefused
    text = rename(source, "Smaug", "Fafnir")

`rename` gives back the new text, or raises RenameRefused with a reason a
person can read. It never gives back a text that the linter likes less than
the one it was given: the result is linted, and if any problem is there that
was not there before, the rename is refused and nothing is changed.

How the names are found
-----------------------

`read_program` asks the compiler for its own table of names
(`englishscript.names`): what each name is, what it belongs to, and where it
is defined. That table is taken wherever it has something to say.

Under it is a reading of the *text*. `read_names` goes through the sentences
and recognises the forms that define a name ("A dragon has ...", "There is a
dragon called Smaug ...", "To send a knight against a dragon:", "Let the
total be ...", and the rest). That is a second, much simpler reading than the
compiler's, and it can be wrong about a sentence the compiler would refuse.
It is used for what the compiler's table leaves out (the name a loop gives
its thing, the words of a library, how the lines nest, what is written in
brackets after a name), and for everything when the compiler's table can't
be had. Whether a rename is *right* is decided by the compiler either way,
through `englishscript.lint`.

The language server (server.py) uses the same reading for its outline, for
"go to definition" and for its suggestions.

A word is letters of any alphabet, digits and underscores, starting with a
letter, as section 3 of the reference says, and capitals are folded with
`str.lower`, as the compiler folds them.

What a rename changes
---------------------

* Every whole occurrence of the name outside quoted text, and inside the
  {fill-ins} of quoted text. Capitals don't matter in EnglishScript, so
  "smaug" is found where "Smaug" was defined. Each occurrence keeps its own
  pattern of capitals where it differed from the definition: a verb that
  starts a sentence stays capitalised.
* For a kind, its plural too, formed by the rule of section 3 of the
  reference ("dragons", "foxes", "ponies"). A kind whose plural was stated
  where it was described ("A child (plural children) has ...") keeps that
  plural, and the plural formed by rule is not a word for it. The stated
  plural is a name of its own and can be renamed.
* A name of several words is matched whole, and a longer name that contains
  it is left alone: renaming "month" does not touch "month row".
* An occurrence that turns out not to be the name at all (the "total" of
  "the total worth of all treasures", beside a variable called "total") is
  found by asking the linter, and left as it was.
* Quoted text itself is never changed.
"""
from __future__ import annotations

import importlib
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["rename", "plan", "apply_edits", "RenameRefused", "Edit", "read_names", "read_program", "reserved_words",
           "pluralize"]


class RenameRefused(Exception):
    """The rename was not made, and nothing was changed. str(error) says why."""


# ------------------------------------------------------------ reserved words

# Section 3 of docs/SYNTAX.md, for when the compiler's own set can't be found.
FALLBACK_RESERVED = frozenset("""
    a an the it its they them their
    let set add subtract multiply divide say if for repeat while there stop skip end now remove ask write
    try fail use whenever
    number money text percent yes no list
    of is are be has called whose when each all otherwise example name nothing any else answer whether
    can in new reply problem items becomes
    not and or never always than less more greater least most divisible
    plus minus times divided
    with to from against for by on at into onto about over under as through toward towards upon
""".split())


def reserved_words():
    """The words no name may use: `englishscript.KEYWORDS` if it is there, or the table of section 3."""
    for module in ("englishscript", "englishscript.compiler"):
        try:
            words = getattr(importlib.import_module(module), "KEYWORDS", None)
            if words and all(isinstance(word, str) for word in words):
                return frozenset(word.lower() for word in words)
        except Exception:  # noqa: BLE001 - the compiler may be missing or half-written; the table will do
            pass
    return FALLBACK_RESERVED


def pluralize(word):
    """The plural by rule (section 3): add "s"; "es" after s, x, z, ch, sh; consonant + "y" to "ies"."""
    low = word.lower()
    upper = word.isupper() and len(word) > 1
    if low.endswith("y") and len(low) > 1 and low[-2] not in "aeiou":
        return word[:-1] + ("IES" if upper else "ies")
    if low.endswith(("s", "x", "z", "ch", "sh")):
        return word + ("ES" if upper else "es")
    return word + ("S" if upper else "s")


# ----------------------------------------------------------------- the words

# A word: a letter of any alphabet, then letters, digits and underscores (section 3; the lexer's own pattern).
LETTERS = r"[^\W\d_]\w*"
WORD = re.compile(LETTERS + r"\Z")
_TOKEN = re.compile(
    r"""
    (?P<string>"(?:[^"]|"")*"?)
  | (?P<pos>'s\b)
  | (?P<word>[^\W\d_]\w*)
  | (?P<number>\$?[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?%?)
  | (?P<space>\s+)
  | (?P<mark>.)
    """,
    re.VERBOSE,
)
_STRAIGHT = str.maketrans({"“": '"', "”": '"', "’": "'"})  # curly quotes are read as straight ones


@dataclass
class Tok:
    kind: str  # word pos string number mark
    text: str
    start: int
    end: int
    group: int = 0  # 0 outside quotes; inside quotes, the number of the {fill-in} it is in

    @property
    def low(self):
        return self.text.lower()

    def is_word(self, *words):
        return self.kind == "word" and (not words or self.text.lower() in words)


def fill_ins(text, start, end):
    """(from, to) of what is between each pair of braces in the quoted text text[start:end]."""
    closed = end - start >= 2 and text[end - 1] == '"'
    i, stop = start + 1, end - 1 if closed else end
    while i < stop:
        if text[i:i + 2] in ('""', "{{", "}}"):
            i += 2
        elif text[i] == "{":
            k = text.find("}", i, stop)
            if k < 0:
                return
            yield i + 1, k
            i = k + 1
        else:
            i += 1


def scan(raw):
    """The words and marks of one line. A quoted text is one token, followed by
    the words inside each of its fill-ins. A comment is left out."""
    text = raw.translate(_STRAIGHT)
    tokens, pos, group = [], 0, 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        kind = m.lastgroup
        if kind == "mark" and m.group() == "#":
            break
        if kind == "string":
            tokens.append(Tok("string", m.group(), pos, m.end()))
            for a, b in fill_ins(text, pos, m.end()):
                group += 1
                for inner in _TOKEN.finditer(text, a, b):
                    if inner.lastgroup != "space":
                        tokens.append(Tok(inner.lastgroup, inner.group(), inner.start(), inner.end(), group))
        elif kind != "space":
            tokens.append(Tok(kind, m.group(), pos, m.end()))
        pos = m.end()
    return tokens


@dataclass
class SourceLine:
    number: int  # counting from 0
    raw: str  # as written, without its line ending
    indent: int
    tokens: list  # every token, the words of fill-ins included
    code: list  # the tokens outside quotes (a quoted text is one of them)
    parent: int | None = None  # the line that opens the block this one is in
    last: int = 0  # the last line of the block this one opens (itself, if it opens none)

    def low(self, k):
        return self.code[k].low if 0 <= k < len(self.code) and self.code[k].kind == "word" else None

    def starts(self, *words):
        return [self.low(k) for k in range(len(words))] == list(words)


@dataclass
class Name:
    """A name, at the sentence that defines it."""
    words: tuple  # in lower case
    text: str  # as written there
    what: str  # kind plural property adjective thing verb value variable role loop choices choice
    line: int  # counting from 0
    start: int
    end: int
    top: bool = True  # defined at the top level (not a role, a loop's name or a variable of a block)
    owner: str | None = None  # the kind of a property, an adjective, a thing or a plural; the set of a choice
    type: str | None = None  # what is written in brackets after it, if anything
    scope: tuple | None = None  # (first line, last line) where a name of a block may be said
    worked: bool = False  # a property that is worked out ("The hoard of a dragon is ...")
    constant: bool = False  # a variable made with "always"
    pattern: list = field(default_factory=list)  # a verb's or value's roles: [(preposition or None, role)]


@dataclass
class Use:
    line: int
    what: str  # "chapter" or "library"
    words: tuple  # the chapter's or library's name, in lower case
    book: tuple = ()
    start: int = 0
    end: int = 0


WHAT = {
    "kind": "a kind", "plural": "the plural of a kind", "property": "a property", "adjective": "an adjective",
    "thing": "a thing", "verb": "a verb", "value": "a worked-out value", "variable": "a variable",
    "role": "a role", "loop": "the name of a loop's thing", "choices": "a set of choices", "choice": "a choice",
}
# What the compiler's table of names (englishscript.names) calls each of them.
FROM_COMPILER = {
    "kind": "kind", "plural of a kind": "plural", "property": "property", "worked-out property": "property",
    "thing": "thing", "adjective": "adjective", "verb": "verb", "worked-out value": "value",
    "variable": "variable", "role": "role", "set of choices": "choices", "choice": "choice",
}
ONE_WORD = ("kind", "plural", "adjective", "verb")  # section 3: these are named with one word


class Reading:
    """What a text defines, found by reading its sentence forms.

    This is a reading of the text, not of the compiler's tables: it knows the
    forms of the sentences that define names and nothing else."""

    def __init__(self, source, reserved=None):
        self.reserved = reserved if reserved is not None else reserved_words()
        self.lines = []
        for number, raw in enumerate(source.splitlines()):
            tokens = scan(raw)
            self.lines.append(SourceLine(number, raw, len(raw) - len(raw.lstrip()), tokens,
                                         [t for t in tokens if t.group == 0], last=number))
        self.names = []
        self.reactions = []  # (line, the sentence): not names, but the outline shows them
        self.uses = []
        self.plurals = {}  # kind -> its stated plural
        self.shares = None  # None: everything; or the set of names "This chapter shares only" lists
        self._nest()
        for line in self.lines:
            if line.code:
                try:
                    self._define(line)
                except IndexError:  # a sentence cut short; it defines nothing
                    pass

    # Layout ---------------------------------------------------------------

    def _nest(self):
        stack = []
        for line in self.lines:
            if not line.code:
                continue
            while stack and self.lines[stack[-1]].indent >= line.indent:
                stack.pop()
            line.parent = stack[-1] if stack else None
            for above in stack:
                self.lines[above].last = line.number
            stack.append(line.number)

    def root(self, number):
        """The top-level line whose block this line is in (itself, at the top level)."""
        if not 0 <= number < len(self.lines):
            return number
        while self.lines[number].parent is not None:
            number = self.lines[number].parent
        return number

    # Sentence forms -------------------------------------------------------

    def _run(self, code, k):
        """The name that starts at code[k]: (words, text, start, end, the index after it), or None."""
        j = k
        while j < len(code) and code[j].kind == "word" and code[j].low not in self.reserved:
            j += 1
        if j == k:
            return None
        return (tuple(t.low for t in code[k:j]), " ".join(t.text for t in code[k:j]), code[k].start,
                code[j - 1].end, j)

    @staticmethod
    def _bracket(line, k):
        """(what is written in the brackets that open at code[k], the index after them), or (None, k)."""
        code = line.code
        if k >= len(code) or code[k].text != "(":
            return None, k
        depth = 0
        for j in range(k, len(code)):
            if code[j].text == "(":
                depth += 1
            elif code[j].text == ")":
                depth -= 1
                if depth == 0:
                    return line.raw[code[k].end:code[j].start].strip(), j + 1
        return line.raw[code[k].end:].strip(), len(code)

    def _add(self, line, run, what, **more):
        words, text, start, end, _ = run
        name = Name(words, text, what, line.number, start, end, **more)
        self.names.append(name)
        return name

    def _define(self, line):
        code, low = line.code, line.low
        top = line.parent is None
        first = low(0)
        if first in ("a", "an") and top:
            kind = self._run(code, 1)
            if kind is None or kind[4] != 2:
                return
            # "A person (plural people) has ...": a plural stated in brackets after the kind (section 4.1).
            stated = (len(code) > 6 and code[2].text == "(" and low(3) == "plural" and code[4].kind == "word"
                      and code[5].text == ")" and low(6) == "has")
            if low(2) == "has" or stated:
                self._add(line, kind, "kind")
                if stated:
                    plural = code[4]
                    self._add(line, ((plural.low,), plural.text, plural.start, plural.end, 5), "plural",
                              owner=kind[0][0])
                    self.plurals[kind[0][0]] = plural.text
                k = 7 if stated else 3
                while k < len(code):
                    if code[k].text == "(":
                        k = self._bracket(line, k)[1]
                    elif low(k) in ("a", "an") and self._run(code, k + 1):
                        run = self._run(code, k + 1)
                        type_, k = self._bracket(line, run[4])
                        self._add(line, run, "property", owner=kind[0][0], type=type_)
                    else:
                        k += 1
            elif low(2) == "is" and low(3) == "one" and low(4) == "of":
                # "A mood is one of sleepy, grumpy or very cross." (section 4.6)
                self._add(line, kind, "choices")
                k = 5
                while k < len(code):
                    run = self._run(code, k)
                    if run:
                        self._add(line, run, "choice", owner=kind[0][0])
                    k = run[4] if run else k + 1
            elif low(2) == "is" and low(4) == "when" and self._run(code, 3):
                self._add(line, self._run(code, 3), "adjective", owner=kind[0][0])
            elif low(2) == "can" and low(3) == "be" and self._run(code, 4):
                self._add(line, self._run(code, 4), "adjective", owner=kind[0][0])
        elif first == "the" and top:
            run = self._run(code, 1)
            if run and low(run[4]) == "of" and low(run[4] + 1) in ("a", "an") and low(run[4] + 3) == "is":
                kind = self._run(code, run[4] + 2)
                if kind and kind[4] == run[4] + 3:
                    self._add(line, run, "property", owner=kind[0][0], worked=True)
        elif first == "there" and low(1) == "is" and low(2) in ("a", "an") and low(3) != "new" and top:
            for k in range(4, len(code)):
                if low(k) == "called":
                    run = self._run(code, k + 1)
                    if run:
                        self._add(line, run, "thing", owner=low(k - 1))
                    break
        elif first == "to" and top:
            scope = (line.number, line.last)
            if line.starts("to", "work", "out", "the"):
                run = self._run(code, 4)
                if run:
                    type_, k = self._bracket(line, run[4])
                    name = self._add(line, run, "value", type=type_)
                    name.pattern = self._roles(line, k, scope)
            else:
                run = self._run(code, 1)
                if run:
                    run = (run[0][:1], code[1].text, code[1].start, code[1].end, 2)  # a verb is one word
                    name = self._add(line, run, "verb")
                    name.pattern = self._roles(line, 2, scope)
        elif first == "let":
            self._let(line, 1)
        elif first == "ask":
            for k in range(1, len(code)):
                if low(k) == "let":
                    self._let(line, k + 1)
                    break
        elif first == "for" and low(1) == "each":
            run = self._run(code, 2)
            if run and low(run[4]) == "in":
                self._add(line, run, "loop", top=False, scope=(line.number, line.last))
        elif first == "whenever" and top:
            self.reactions.append((line.number, line.raw[code[0].start:code[-1].end].rstrip(" :")))
        elif first == "use" and low(1) == "the":
            self._use(line)
        elif line.starts("this", "chapter", "shares") and top:
            self._shares(line)

    def _let(self, line, k):
        code, low = line.code, line.low
        if low(k) == "the":
            k += 1
        run = self._run(code, k)
        if not run:
            return
        type_, after = self._bracket(line, run[4])
        constant = low(after) == "always"
        if low(after + constant) != "be":
            return
        top = line.parent is None
        scope = None
        if not top:
            scope = (line.number, self.lines[line.parent].last)
        self._add(line, run, "variable", top=top, type=type_, scope=scope, constant=constant)

    def _roles(self, line, k, scope):
        """The roles written from code[k] on. One with a type in brackets has a name of its own."""
        code, pattern = line.code, []
        while k < len(code):
            run = self._run(code, k + 1) if line.low(k) in ("a", "an") else None
            if run is None:
                k += 1
                continue
            before = code[k - 1]
            preposition = before.low if before.kind == "word" and before.low in self.reserved else None
            type_, after = self._bracket(line, run[4])
            if type_ is not None:
                self._add(line, run, "role", top=False, type=type_, scope=scope)
            pattern.append((preposition, run[1]))
            k = after
        return pattern

    def _use(self, line):
        code, low = line.code, line.low
        words = [k for k in range(2, len(code)) if code[k].kind == "word"]
        if len(code) >= 4 and low(3) == "library" and code[2].kind == "word":
            self.uses.append(Use(line.number, "library", (low(2),), (), code[2].start, code[2].end))
            return
        for k in words:
            if low(k) == "chapter" and k > 2:
                name = tuple(code[j].low for j in range(2, k))
                book = ()
                if low(k + 1) == "of" and low(k + 2) == "the":
                    for j in range(k + 3, len(code)):
                        if low(j) == "book":
                            book = tuple(code[i].low for i in range(k + 3, j))
                            break
                if all(code[j].kind == "word" for j in range(2, k)):
                    self.uses.append(Use(line.number, "chapter", name, book, code[2].start, code[k - 1].end))
                return

    def _shares(self, line):
        code, low = line.code, line.low
        self.shares = set()
        if low(3) != "only":
            return
        name = []
        for tok in code[4:]:
            if tok.kind == "word" and tok.low != "and":
                name.append(tok.low)
            elif name:
                self.shares.add(tuple(name))
                name = []
        if name:
            self.shares.add(tuple(name))

    # The compiler's table -------------------------------------------------

    def adopt(self, entries, shares=False):
        """Take the compiler's own names for this text (entries of englishscript.names) in
        place of those read from the sentence forms. What the table does not say is kept
        from the reading: what is in brackets after a name, a verb's roles, how far a name
        of a block reaches, and the name a loop gives its thing, which the table leaves out.
        `shares` is the chapter's list of what it shares, None for everything; False keeps
        what the text says. An entry that does not fit the text is left out."""
        read = {(n.line, n.start): n for n in self.names}
        names, plurals, reactions = [], {}, {}
        for entry in entries:
            what = FROM_COMPILER.get(entry.get("what"))
            number, start, width = entry.get("line"), entry.get("col"), entry.get("width")
            if not (isinstance(number, int) and isinstance(start, int) and isinstance(width, int)):
                continue
            number -= 1
            if not 0 <= number < len(self.lines):
                continue
            line = self.lines[number]
            if entry.get("what") == "reaction":
                if line.code:
                    reactions[number] = line.raw[line.code[0].start:line.code[-1].end].rstrip(" :")
                continue
            written = line.raw[start:start + width]
            words = tuple(str(entry.get("name", "")).lower().split())
            if what is None or not words or tuple(written.translate(_STRAIGHT).lower().split()) != words:
                continue
            before = read.get((number, start))
            name = Name(words, " ".join(written.split()), what, number, start, start + width, owner=entry.get("of"))
            name.worked = entry.get("what") == "worked-out property"
            if before is not None and before.what == what:
                name.type, name.pattern, name.constant = before.type, before.pattern, before.constant
            after = next((tok for tok in line.code if tok.start >= name.end), None)
            if what == "role":
                if after is None or after.text != "(":
                    continue  # a role called by its kind's name ("a dragon") is the kind's word, not a new name
                name.top, name.scope = False, (number, line.last)
            elif what == "variable" and line.parent is not None:
                name.top, name.scope = False, (number, self.lines[line.parent].last)
            if what == "plural" and name.owner:
                plurals[str(name.owner).lower()] = name.text
            names.append(name)
        names += [n for n in self.names if n.what == "loop"]
        for number, sentence in self.reactions:  # "Whenever everything has settled:" is not in the table
            reactions.setdefault(number, sentence)
        self.names = sorted(names, key=lambda n: (n.line, n.start))
        self.plurals, self.reactions = plurals, sorted(reactions.items())
        if shares is not False:
            self.shares = None if shares is None else {tuple(str(s).lower().split()) for s in shares}

    # Looking up -----------------------------------------------------------

    def defined(self, words, within=None):
        """The definitions of a name (a tuple of lower-case words), in order."""
        return [n for n in self.names
                if n.words == tuple(words) and (within is None or within[0] <= n.line <= within[1])]

    def vocabulary(self):
        """Every name the text defines, and the plural of every kind: {words: the Name}.
        A stated plural is a Name of its own; a plural formed by rule leads to its kind's Name,
        and is left out for a kind whose plural was stated."""
        found = {}
        for name in self.names:
            found.setdefault(name.words, name)
        for name in self.names:
            if name.what == "kind" and name.words[0] not in self.plurals:
                found.setdefault((pluralize(name.text).lower(),), name)
        return found

    def shared(self):
        """The names another file may say: all of them, or those "This chapter shares only" lists
        (a shared kind brings its plural and its properties with it)."""
        every = {words: name for words, name in self.vocabulary().items() if name.top}
        if self.shares is None:
            return every
        kinds = {name.words[0] for name in self.names if name.what == "kind" and name.words in self.shares}
        return {words: name for words, name in every.items()
                if name.words in self.shares or (name.what in ("property", "plural") and name.owner in kinds)}


def read_names(source, reserved=None):
    """Read a text's sentence forms and say what it defines (see Reading)."""
    return Reading(source, reserved)


# ------------------------------------------------- chapters and libraries

def chapter_path(folder, words, book=()):
    """The file "Use the <words> chapter [of the <book> book]." reads (section 9.6)."""
    base = Path(folder) if folder is not None else Path(".")
    if book:
        base = base / "_".join(book)
    return base / ("_".join(words) + ".english")


def _read_file(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _library_source(word):
    if not re.fullmatch(r"[a-z][a-z0-9]*", word):
        return None
    try:
        module = importlib.import_module(f"englishscript.libraries.{word}")
    except Exception:  # noqa: BLE001 - no such library, or one that can't be loaded here
        return None
    source = getattr(module, "SOURCE", None)
    return source if isinstance(source, str) else None


def neighbours(reading, folder=None, read=None):
    """The chapters and libraries a text uses, each read the same way:
    [(the Use, what to call it, its path or None, its Reading)]. One that can't be read is left out.
    `read(path)` gives the text of a chapter that is open and unsaved, or None for the file on the disk."""
    found = []
    for use in reading.uses:
        if use.what == "library":
            source, path, label = _library_source(use.words[0]), None, f"the {use.words[0]} library"
        else:
            path = chapter_path(folder, use.words, use.book)
            source, label = read(path) if read is not None else None, f"the {' '.join(use.words)} chapter"
            if source is None:
                source = _read_file(path)
        if source is not None:
            found.append((use, label, path, Reading(source, reading.reserved)))
    return found


def _table(source, folder, name, read):
    """The compiler's table of names, {"names": [...], "chapters": [...]}, or None if it can't be had."""
    try:
        names = getattr(importlib.import_module("englishscript"), "names", None)
        if not callable(names):
            return None
        try:
            table = names(source, folder, name, read=read)
        except TypeError:  # a compiler whose `names` does not take `read`
            table = names(source, folder, name)
    except Exception:  # noqa: BLE001 - the text reading will do
        return None
    if not isinstance(table, dict) or not isinstance(table.get("names"), list):
        return None
    if not all(isinstance(entry, dict) for entry in table["names"]):
        return None
    return table


def _same_file(a, b):
    import os
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def read_program(source, folder=None, name=None, read=None, reserved=None):
    """A text and the chapters and libraries it uses, read for their names:
    (the text's Reading, [(the Use, what to call it, its path or None, its Reading)]).

    The names are the compiler's own (englishscript.names) where it gives them. The
    reading of the sentence forms stands in where it does not: for a library's words,
    and for everything if the compiler's table can't be had or has nothing for a text
    in which the sentence forms do define names (`names` gives an empty table when it
    fails, as it does for an empty program)."""
    reading = Reading(source, reserved)
    others = neighbours(reading, folder, read)
    table = _table(source, folder, name, read)
    if table is None:
        return reading, others
    mine = [entry for entry in table["names"] if not entry.get("file")]
    if mine or not reading.names:
        reading.adopt(mine)
    chapters = [c for c in table.get("chapters") or [] if isinstance(c, dict) and c.get("file")]
    base = Path(folder) if folder is not None else Path(".")
    for _, _, path, other in others:
        if path is None:
            continue  # a library: its words are not in the table
        for chapter in chapters:
            if _same_file(base / str(chapter["file"]), path):
                theirs = [entry for entry in table["names"] if entry.get("file") == chapter["file"]]
                if theirs or not other.names:
                    other.adopt(theirs, chapter.get("shares"))
                break
    return reading, others


# ------------------------------------------------------------- occurrences

@dataclass
class Occurrence:
    line: int
    start: int
    end: int
    words: tuple  # which of the names looked for
    text: str  # as written here
    verb: bool  # it stands where only a verb can: first in its sentence, or after "To"
    free: bool = False  # in "This chapter shares only ...", where a verb and a name look alike


def occurrences(reading, targets, known=(), lines=None):
    """Where each of `targets` (tuples of lower-case words) is written, outside quotes and
    inside fill-ins. Words are matched the way the compiler matches them: the longest
    of the `known` names first, so a longer name that contains a target is passed over.
    `lines` are the numbers of the lines to look in (all of them, by default)."""
    targets = set(targets)
    known = set(known) | targets
    longest = max((len(words) for words in known), default=1)
    found = []
    for line in (reading.lines if lines is None else [reading.lines[n] for n in lines if 0 <= n < len(reading.lines)]):
        toks = line.tokens
        free = line.starts("this", "chapter", "shares")
        worked_out = line.starts("to", "work", "out")
        i = 0
        while i < len(toks):
            if toks[i].kind != "word":
                i += 1
                continue
            j = i
            while j + 1 < len(toks) and toks[j + 1].kind == "word" and toks[j + 1].group == toks[i].group:
                j += 1
            k = i
            while k <= j:
                for n in range(min(j - k + 1, longest), 0, -1):
                    words = tuple(t.low for t in toks[k:k + n])
                    if words not in known:
                        continue
                    if words in targets:
                        tok = toks[k]
                        verb = tok is line.code[0] or (
                            len(line.code) > 1 and tok is line.code[1] and line.low(0) == "to" and not worked_out)
                        found.append(Occurrence(line.number, tok.start, toks[k + n - 1].end, words,
                                                " ".join(t.text for t in toks[k:k + n]), verb, free))
                    k += n
                    break
                else:
                    k += 1
            i = j + 1
    return found


def recase(written, defined, new):
    """`new`, with the capitals of this occurrence where it differed from the definition.

    The compiler folds capitals with str.lower, so a spelling is only used if it folds
    back to the same name: "MASS" is not "Maß" again, so "Maß" is then written as given."""
    if written == defined or not written or not new:
        return new
    if written.isupper() and not defined.isupper() and len(written) > 1:
        dressed = new.upper()
    elif written.islower() and not defined.islower():
        dressed = new.lower()
    elif written[0].isupper() != defined[0].isupper():
        dressed = (new[0].upper() if written[0].isupper() else new[0].lower()) + new[1:]
    else:
        return new
    return dressed if dressed.lower() == new.lower() else new


# ---------------------------------------------------------------- the edits

@dataclass(frozen=True)
class Edit:
    """Replace raw[start:end] of a line (counting from 0, as str.splitlines counts lines) with `text`."""
    line: int
    start: int
    end: int
    text: str
    whole: bool = False  # the whole line, written out again (after "a" became "an", or the other way)


def apply_edits(source, edits):
    """The text with the edits made. Line endings are kept as they were."""
    kept = source.splitlines(keepends=True)
    bare = source.splitlines()
    by_line = {}
    for edit in edits:
        by_line.setdefault(edit.line, []).append(edit)
    for number, here in by_line.items():
        body, ending = bare[number], kept[number][len(bare[number]):]
        for edit in sorted(here, key=lambda e: e.start, reverse=True):
            body = body[:edit.start] + edit.text + body[edit.end:]
        kept[number] = body + ending
    return "".join(kept)


def _name_words(text, which):
    words = str(text).split()
    if len(words) > 1 and words[0].lower() == "the":
        words = words[1:]  # "the month row" is the name "month row"
    if not words:
        raise RenameRefused(f"The {which} name is empty.")
    for word in words:
        if not WORD.match(word):
            raise RenameRefused(
                f'"{word}" can\'t be part of a name: a name is made of words of letters, digits and '
                "underscores, each starting with a letter (section 3 of the reference).")
    return words


def _problems(source, folder, name, read=None):
    """The linter's problems as dicts. Raises RenameRefused if the linter can't be asked."""
    try:
        lint = importlib.import_module("englishscript").lint
        try:
            found = lint(source, folder, name, read=read) if read is not None else lint(source, folder, name)
        except TypeError:  # a linter that does not take `read`
            found = lint(source, folder, name)
    except Exception as error:  # noqa: BLE001 - without the compiler's verdict there is no rename
        raise RenameRefused(
            f"The compiler could not be asked to check the result ({type(error).__name__}: {error}), "
            "so nothing was changed.") from None
    out = []
    for problem in found:
        as_dict = getattr(problem, "as_dict", None)
        data = as_dict() if callable(as_dict) else problem if isinstance(problem, dict) else dict(vars(problem))
        out.append(data)
    return out


def _phrase(words):
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(w) for w in words) + r"(?!\w)", re.I)


class _Judge:
    """Compares what the linter says before and after, leaving the two names out of account."""

    def __init__(self, source, folder, name, phrases, read=None):
        self.folder, self.name, self.read = folder, name, read
        self.patterns = [_phrase(words) for words in sorted(set(phrases), key=len, reverse=True)]
        self.before = Counter(self.key(p) for p in _problems(source, folder, name, read))
        self.asked = 0

    def key(self, problem):
        message = str(problem.get("message") or "")
        for pattern in self.patterns:
            message = pattern.sub("\0", message)
        message = re.sub(r"\ban?(\s+\0)", r"a\1", message, flags=re.I)  # "a dragon" may become "an egg"
        return problem.get("kind"), message

    def fresh(self, text):
        """The problems of `text` that the original did not have."""
        self.asked += 1
        left = Counter(self.before)
        found = []
        for problem in _problems(text, self.folder, self.name, self.read):
            key = self.key(problem)
            if left[key] > 0:
                left[key] -= 1
            else:
                found.append(problem)
        return found


_SEGMENT = re.compile(r"[^\W\d_]+|[\W\d_]+")  # runs of letters, and what is between them


def _article_swaps(current, fixed):
    """If `fixed` is `current` with only "a" and "an" exchanged: {which piece: what it becomes}; else None."""
    ours, theirs = _SEGMENT.findall(current), _SEGMENT.findall(fixed.translate(_STRAIGHT))
    if len(ours) != len(theirs):
        return None
    swaps = {}
    for k, (mine, other) in enumerate(zip(ours, theirs)):
        if mine.translate(_STRAIGHT) == other:
            continue
        if {mine.lower(), other.lower()} != {"a", "an"}:
            return None
        swaps[k] = other
    return swaps or None


def _subsets(items, most=4):
    """Each one alone, then pairs, and so on, then all of them."""
    from itertools import combinations
    if len(items) > most:
        return [(item,) for item in items] + [tuple(items)]
    return [combo for size in range(1, len(items) + 1) for combo in combinations(items, size)]


MOST_QUESTIONS = 60  # how often one rename may ask the linter


def plan(source, old, new, folder=None, name=None, only=None, within=None, read=None):
    """The edits that rename `old` to `new` in `source`, or RenameRefused.

    `only` is "verb" or "name", for a word that is both a verb and something
    else (section 3 lets them share a word) when only one of them is meant.
    `within` is (first line, last line), counting from 0, to rename a name of
    one block there and nowhere else. `read(path)` gives the text of a chapter
    that is open in an editor and not saved, or None for the file on the disk,
    as for englishscript.lint.
    """
    old_words, new_words = _name_words(old, "old"), _name_words(new, "new")
    old_key, new_key = tuple(w.lower() for w in old_words), tuple(w.lower() for w in new_words)
    old_said, new_text = " ".join(old_words), " ".join(new_words)
    reserved = reserved_words()
    reading, others = read_program(source, folder, name, read, reserved)

    # 1. The old name must be defined here.
    definitions = reading.defined(old_key, within)
    if not definitions:
        for _, label, path, other in others:
            there = [n for n in other.defined(old_key) if n.top]
            if there:
                where = f"{label}, line {there[0].line + 1}" if path is None else f"{path}, line {there[0].line + 1}"
                raise RenameRefused(f'"{old_said}" is not defined in this text. It is {WHAT[there[0].what]} of '
                                    f"{label} ({where}); rename it there.")
        if within is not None and reading.defined(old_key):
            raise RenameRefused(f'"{old_said}" is not defined in lines {within[0] + 1} to {within[1] + 1}.')
        raise RenameRefused(f'"{old_said}" is not defined in this text, so there is nothing to rename.')
    senses = {"verb" if n.what == "verb" else "name" for n in definitions}
    if only is not None:
        if only not in senses:
            raise RenameRefused(f'"{old_said}" is not defined as a {only} in this text.')
        senses = {only}
        definitions = [n for n in definitions if (n.what == "verb") == (only == "verb")]

    # 2. The new name must be one the language allows, and free.
    if new_key == old_key:
        raise RenameRefused(f'"{new_text}" is the same name as "{old_said}": capitals don\'t matter, '
                            "so there is nothing to rename.")
    for word in new_words:
        if word.lower() in reserved:
            raise RenameRefused(f'The word "{word}" already has a meaning in EnglishScript, so it can\'t be '
                                f'part of a name (section 3 of the reference). "{new_text}" was not used.')
    for definition in definitions:
        if definition.what in ONE_WORD and len(new_words) > 1:
            raise RenameRefused(f'"{old_said}" is {WHAT[definition.what]}, and {WHAT[definition.what]} is named '
                                f'with one word. "{new_text}" has {len(new_words)}.')
    kind = next((n for n in definitions if n.what == "kind"), None)
    with_plural = kind is not None and kind.words[0] not in reading.plurals and "name" in senses
    old_plural = pluralize(kind.text) if with_plural else None
    new_plural = pluralize(new_text) if with_plural else None

    vocabulary = {}  # words -> (the Name, where it is from: None for this text)
    for words, found in reading.vocabulary().items():
        vocabulary[words] = (found, None)
    for _, label, _, other in others:
        for words, found in other.vocabulary().items():
            if found.top:
                vocabulary.setdefault(words, (found, label))
    wanted = [(new_key, new_text)] + ([((new_plural.lower(),), new_plural)] if with_plural else [])
    for words, said in wanted:
        if words in vocabulary:
            found, where = vocabulary[words]
            if found.words == words:
                what = f"{WHAT[found.what]}"
            else:
                what = f'the plural of the kind "{found.text}"'
            place = f"line {found.line + 1}" if where is None else f"{where}, line {found.line + 1}"
            raise RenameRefused(f'"{said}" is already in use: it is {what} ({place}). '
                                "A name means one thing in the whole program.")

    # 3. A thing found by its name in quotes would no longer be found.
    if any(n.what == "thing" for n in definitions):
        for line in reading.lines:
            for tok, after in zip(line.code, line.code[1:]):
                if tok.is_word("called") and after.kind == "string":
                    quoted = after.text.strip('"').replace('""', '"')
                    if tuple(quoted.lower().split()) == old_key and (
                            within is None or within[0] <= line.number <= within[1]):
                        raise RenameRefused(
                            f'Line {line.number + 1} looks for a thing by the quoted text "{quoted}". A rename '
                            "never changes quoted text, so that sentence would stop finding it. Change that "
                            "line by hand first.")

    # 4. Where the name is written.
    targets = {old_key: (definitions[0].text, new_text)}
    if with_plural:
        targets[(old_plural.lower(),)] = (old_plural, new_plural)
    known = set(vocabulary) | set(targets)
    defining = {(n.line, n.start) for n in definitions}
    edits, fixed = [], set()
    for found in occurrences(reading, targets, known):
        if within is not None and not within[0] <= found.line <= within[1]:
            continue
        if not found.free and ("verb" if found.verb else "name") not in senses:
            continue
        if found.verb and found.words != old_key:
            continue  # a plural is never a verb
        defined, replacement = targets[found.words]
        edit = Edit(found.line, found.start, found.end, recase(found.text, defined, replacement))
        edits.append(edit)
        if (found.line, found.start) in defining:
            fixed.add(edit)

    # 5. The compiler judges. An occurrence it can't read as the new name is put back,
    #    if the text then reads as it did; "a" and "an" are put right as the linter says.
    phrases = [old_key, new_key]
    if with_plural:
        phrases += [(old_plural.lower(),), (new_plural.lower(),)]
    judge = _Judge(source, folder, name, phrases, read)
    edits = _settle(source, edits, fixed, judge)
    return edits


def _settle(source, edits, fixed, judge):
    fresh = judge.fresh(apply_edits(source, edits))
    if fresh:
        edits, fresh = _articles(source, edits, fresh, judge)
    while fresh and judge.asked < MOST_QUESTIONS:
        better = None
        for problem in fresh:
            if problem.get("kind") != "error" or problem.get("file") or not isinstance(problem.get("line"), int):
                continue
            number = problem["line"] - 1
            here = [e for e in edits if e.line == number and e not in fixed and not e.whole]
            for dropped in _subsets(here):
                trial = [e for e in edits if e not in dropped]
                found = judge.fresh(apply_edits(source, trial))
                if len(found) < len(fresh) and not any(p.get("line") == problem["line"] and not p.get("file")
                                                       for p in found):
                    better = (trial, found)
                    break
                if judge.asked >= MOST_QUESTIONS:
                    break
            if better or judge.asked >= MOST_QUESTIONS:
                break
        if not better:
            break
        edits, fresh = better
        if fresh:
            edits, fresh = _articles(source, edits, fresh, judge)
    if fresh:
        problem = fresh[0]
        where = f"line {problem.get('line')}"
        if problem.get("file"):
            where = f"{problem.get('file')}, {where}"
        kind = "suggestion" if problem.get("kind") == "warning" else "problem"
        raise RenameRefused(f"The rename would bring a new {kind}, on {where}: {problem.get('message')} "
                            "Nothing was changed.")
    return sorted(edits, key=lambda e: (e.line, e.start))


def _articles(source, edits, fresh, judge):
    """Where the linter now says "a" should be "an" (or the other way) on a line the
    rename changed, and its correction changes nothing else, take the correction."""
    lines = apply_edits(source, edits).splitlines()
    bare = source.splitlines()
    changed = {e.line for e in edits}
    swaps = {}  # line -> {which piece: what it becomes}
    for problem in fresh:
        fix = problem.get("fix")
        if problem.get("file") or not isinstance(fix, dict) or not isinstance(fix.get("line"), int):
            continue
        number = fix["line"] - 1
        if number in changed and 0 <= number < len(lines):
            found = _article_swaps(lines[number], str(fix.get("text", "")))
            if found:
                swaps.setdefault(number, {}).update(found)
    if not swaps or judge.asked >= MOST_QUESTIONS:
        return edits, fresh
    trial = [e for e in edits if e.line not in swaps]
    for number, pieces in swaps.items():
        parts = _SEGMENT.findall(lines[number])
        for k, text in pieces.items():
            parts[k] = text
        trial.append(Edit(number, 0, len(bare[number]), "".join(parts), whole=True))
    found = judge.fresh(apply_edits(source, trial))
    return (trial, found) if len(found) < len(fresh) else (edits, fresh)


def rename(source, old, new, folder=None, name=None, only=None, within=None, read=None):
    """`source` with the name `old` changed to `new` everywhere, or RenameRefused.

    `folder` is where the program's chapters are looked for and `name` is what
    to call its file, as for englishscript.lint. See `plan` for `only`, `within` and `read`."""
    return apply_edits(source, plan(source, old, new, folder, name, only, within, read))


# ------------------------------------------------------------ command line

def main(argv=None):
    import argparse

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog="python -m englishscript.rename",
        description="Rename a name throughout an EnglishScript program. The result is checked by the "
                    "compiler; if it reads any worse than before, nothing is changed.",
    )
    parser.add_argument("file", help="a .english file")
    parser.add_argument("old", help='the name as it is now, such as "month row"')
    parser.add_argument("new", help="the name it should have")
    parser.add_argument("--write", action="store_true", help="rewrite the file instead of printing the new text")
    parser.add_argument("--only", choices=("verb", "name"),
                        help="for a word that is both a verb and a name: which of the two to rename")
    args = parser.parse_args(argv)
    path = Path(args.file)
    try:
        with open(path, encoding="utf-8", newline="") as handle:  # keep the line endings as they are
            source = handle.read()
    except (OSError, UnicodeError) as error:
        print(f"I couldn't read {args.file}: {getattr(error, 'strerror', None) or error}.", file=sys.stderr)
        return 1
    try:
        edits = plan(source, args.old, args.new, folder=path.parent, name=args.file, only=args.only)
    except RenameRefused as refused:
        print(f"Refused: {refused}", file=sys.stderr)
        return 1
    text = apply_edits(source, edits)
    if args.write:
        try:
            with open(path, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
        except OSError as error:
            print(f"I couldn't write {args.file}: {error.strerror}.", file=sys.stderr)
            return 1
        places = "1 place" if len(edits) == 1 else f"{len(edits)} places"
        print(f'Renamed "{args.old}" to "{args.new}" in {places}.')
    else:
        sys.stdout.flush()
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())

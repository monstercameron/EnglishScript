"""The linter: every problem in a program at once, with advice, and warnings.

    from englishscript import lint
    for problem in lint(source):
        print(problem.render("my.english"))

`lint` only compiles; it never runs the program or asks for anything. It never
raises: whatever the text, it gives back a list of Problems, in order of line
and then column.

How it carries on after a problem
---------------------------------

* Layout. `read_source` is given a list to put its problems in instead of
  raising them. A line whose words can't be read is kept but marked `broken`
  and is not compiled; a line with no period is read as if it had one (or a
  colon, when the next line is indented further); a line indented under one
  that doesn't open a block is kept as that line's (never compiled) block.

* Sentences. The compiler's `block` catches a refused sentence, reports it
  here, and goes on with the next sentence of the same block, skipping the
  refused sentence's own block and any Otherwise / If that fails parts that
  belong to it. Nothing a refused sentence would have defined is registered.
  A library's own sentences are not recovered: a problem there is reported
  once, at the program's "Use" sentence.

* Floods. When a sentence is refused (or lost to a layout problem), the names
  it was trying to define are worked out from its words, and a later error
  that points at one of those names, or quotes it, is left out: it exists only
  because the first sentence was refused. At most one error is kept per line.

Warnings are never given for a line that has an error.
"""
from __future__ import annotations

import importlib
import re
from dataclasses import asdict, dataclass

from .compiler import BORROWED, KEYWORDS, ROLE_WORDS, Compiler, pluralize
from .lexer import (
    CATEGORIES, NO_COLON, NO_PERIOD, RULES, EnglishError, _strip_comment, chapter_of, mark, read_source, swap,
)
from .runtime import no_digit_limit


@dataclass
class Problem:
    line: int  # counting from 1
    col: int | None  # counting from 0, or None when no place in the line is pointed at
    width: int  # at least 1
    kind: str  # "error" or "warning"
    message: str  # what is wrong here
    hint: str | None  # how to mend it
    sentence: str  # the line of the program, as written
    file: str | None = None  # the chapter's file, for a line of a chapter; None for the main file
    category: str | None = None  # "spelling", "punctuation", ... (lexer.CATEGORIES)
    rule: str | None = None  # the rule to remember, one sentence, the same each time it is broken
    see: str | None = None  # the section of docs/SYNTAX.md that teaches it: "1", "4.2"
    fix: dict | None = None  # {"line": number, "text": the line as it should be}, when certain

    def as_dict(self):
        return asdict(self)

    def render(self, filename=None):
        """The same layout as EnglishError.render: a teacher's mark."""
        where = f"line {self.line}"
        if self.file:
            where = f"{self.file}, {where}"
        elif filename:
            where = f"{filename}, {where}"
        fixed = self.fix["text"] if self.fix is not None and self.fix["line"] == self.line else None
        return mark(self.category, where, self.sentence, self.col, self.width, self.message, self.hint,
                    self.rule, self.see, fixed, warning=self.kind == "warning")


def tally(problems):
    """What a teacher writes at the foot of the page:
    "3 things to mend: 2 of spelling, 1 of punctuation. 1 suggestion." """
    errors = [p for p in problems if p.kind == "error"]
    suggestions = len(problems) - len(errors)
    if not errors:
        out = "Nothing to mend: every sentence reads one way."
    else:
        counts = {}
        for problem in errors:
            counts[problem.category] = counts.get(problem.category, 0) + 1
        order = list(CATEGORIES)
        parts = [f"{n} {CATEGORIES.get(c, CATEGORIES['grammar'])[1]}"
                 for c, n in sorted(counts.items(), key=lambda item: (-item[1], order.index(item[0])
                                                                        if item[0] in order else len(order)))]
        things = "1 thing" if len(errors) == 1 else f"{len(errors)} things"
        out = f"{things} to mend: " + ", ".join(parts) + "."
    if suggestions:
        out += f" {suggestions} suggestion{'' if suggestions == 1 else 's'}."
    return out


def lint(source, folder=None, name=None, notes=False, read=None):
    """Every problem in `source`: errors the compiler refuses, and warnings.

    `folder` is where the chapters it uses are looked for (by default the
    current directory). The problems of a chapter it uses are given as one
    error at the "Use" sentence; `name` is what to call the file. `read`, if
    given, takes a chapter's path and gives its text, or None to read the disk.

    With `notes=True`, gives back (problems, notes) instead: the notes are
    (line, text), how each sentence that could be read was read, as --explain
    shows them, for every line that has no error."""
    try:
        with no_digit_limit():
            problems, compiler = _lint(source, folder, name, read)
    except RecursionError:
        problems, compiler = [_whole("This program nests more deeply than I can follow.", source)], None
    except Exception as error:  # noqa: BLE001 - the linter must never raise
        problems = [_whole(f"The linter could not read this program: {type(error).__name__}: {error}", source)]
        compiler = None
    if not notes:
        return problems
    wrong = {p.line for p in problems if p.kind == "error" and p.file is None}
    found = [(line, text) for line, text in (compiler.notes if compiler is not None else ()) if line not in wrong]
    return problems, found


def names(source, folder=None, name=None, read=None):
    """The table of names of a program, as far as it can be read (through the linter,
    so a program with errors gives what its good sentences define).

    Returns {"names": [...], "chapters": [...]}. Each name is a dict with "name" (as
    written), "what" ("kind", "plural of a kind", "property", "worked-out property",
    "thing", "adjective", "verb", "worked-out value", "variable", "role", "reaction",
    "set of choices" or "choice"), "of" (the kind an adjective, property or thing
    belongs to, or the set of a choice, else None), "file" (a chapter's file, or None
    for the program's own), "line", "col" (from 0) and "width". Each chapter is a dict
    with "file", "name" and "shares": the names it shares, or None for everything."""
    try:
        with no_digit_limit():
            _, compiler = _lint(source, folder, name, read)
    except Exception:  # noqa: BLE001 - like the linter, never raises
        return {"names": [], "chapters": []}
    table = []
    for what, written, of, line, col, width in compiler.defined:
        table.append({"name": written, "what": what, "of": of, "file": chapter_file(line), "line": line.number,
                      "col": col, "width": width})
    chapters = [{"file": unit.file, "name": unit.name,
                 "shares": None if unit.shares is None else [entry[3] for entry in unit.share_at.values()]}
                for unit in compiler.chapters.values() if unit is not compiler.main]
    return {"names": table, "chapters": chapters}


def _whole(message, source):
    first = (source.splitlines() or [""])[0]
    category, rule, see = RULES["sentence_form"]
    return Problem(1, None, 1, "error", message, None, first, None, category, rule, see)


def _lint(source, folder=None, name=None, read=None):
    collector = Collector(source)
    compiler = Compiler(folder, name, read)
    layout = []
    lines = read_source(source, problems=layout, unit=compiler.main)
    for error in layout:
        collector.add(error, "error")
    compiler.lint = collector
    compiler.program(lines)
    collector.never_used(compiler)
    return collector.result(), compiler


def chapter_file(line):
    chapter = chapter_of(line)
    return chapter.file if chapter is not None else None


WORD = re.compile(r"[^\W\d_]\w*")
QUOTED = re.compile(r'"([^"]+)"')
ARTICLES = ("the", "a", "an")
NO_ENDING = (NO_PERIOD, NO_COLON)
# The rules of problems that come from a word with no meaning: after a library or
# chapter that could not be used, these are left out (its words are unknown).
UNKNOWN_RULES = {"unknown", "unknown_kind", "unknown_property", "unknown_adjective", "unknown_verb",
                 "unknown_variable", "the_noun", "pronoun", "types"}

# "a" or "an": by the sound the next word starts with. Where the spelling does
# not tell (most words starting with "u", and with "h"), only the words listed
# are judged; for the others nothing is said.
SOUNDS_LIKE_A = {  # start with a vowel letter, but with the sound of "y" or "w"
    "one", "once", "ones", "ouija", "unit", "units", "unity", "user", "users", "use", "used", "uses", "useful",
    "usual", "usually", "usage", "union", "unions", "unique", "universe", "university", "universal",
    "uniform", "unicorn", "unicorns", "utensil", "utility", "uranium", "utopia", "ukulele", "eulogy",
    "euro", "euros", "european", "eucalyptus", "ewe", "ewes", "unanimous", "uterus", "urine",
}
SOUNDS_LIKE_AN = {"hour", "hours", "hourly", "honest", "honestly", "honour", "honor", "honourable", "honorable",
                  "heir", "heirs", "heiress", "herb", "herbs"}
SURELY_AN_PREFIXES = ("un", "up", "um", "ug", "ul", "us", "ut", "ur")  # "an umbrella", "an upper", "an urn"


def article_for(word):
    """"a" or "an" for a word, or None when it can't be told from the spelling."""
    low = word.lower()
    if len(low) < 2 or not low.isalpha() or (word.isupper() and len(word) > 1):
        return None  # a single letter, or an abbreviation such as "FBI"
    if low in SOUNDS_LIKE_A:
        return "a"
    if low in SOUNDS_LIKE_AN:
        return "an"
    if low[0] in "aio":
        return "an"
    if low[0] == "e":
        return None if low.startswith(("eu", "ew")) else "an"
    if low[0] == "u":
        if low.startswith("uni") or low.startswith(("usu", "use", "uti", "ura", "uri", "ure", "uto")):
            return None
        return "an" if low.startswith(SURELY_AN_PREFIXES) else None
    if low[0] == "h":
        return None if low.startswith(("hon", "hou", "hei", "her")) else "a"
    return "a"


class Collector:
    """What the compiler reports to while linting (Compiler.lint)."""

    def __init__(self, source):
        self.raw = source.splitlines()
        self.problems = []
        self.hidden = set()  # names (tuples of words) whose definitions were refused
        self.unknown_library = False  # a library that doesn't exist was used
        self.refused_words = set()  # every word of a refused or lost sentence

    # Recording ------------------------------------------------------------

    def add(self, error, kind, line=None):
        where = error.line if error.line is not None and not error.line.library else line
        if where is None:
            return
        col = error.col if where is error.line else None
        fix = error.fix if where is error.line else None
        self.record(kind, where.number, col, error.width, error.message, error.hint, chapter_file(where),
                    error.key, error.category, fix)

    def record(self, kind, number, col, width, message, hint, file=None, teach=None, category=None, fix=None):
        sentence = self.raw[number - 1] if 0 < number <= len(self.raw) else ""
        found, rule, see = RULES[teach or ("unused" if kind == "warning" else "sentence_form")]
        self.problems.append(Problem(number, col, max(1, width or 1), kind, message, hint, sentence, file,
                                     category or found, rule, see, fix))

    def warn(self, line, col, width, message, hint=None, teach="unused", fix=None):
        if not line.library:
            fix = {"line": line.number, "text": fix} if fix is not None else None
            self.record("warning", line.number, col, width, message, hint, chapter_file(line), teach, None, fix)

    def capital(self, line):
        """Sentences start with a capital letter, and "a" or "an" goes with the sound
        of the word after it."""
        first = line.tokens[0] if line.tokens else None
        if first is not None and first.kind == "WORD" and first.text[0].islower():
            word = first.text[0].upper() + first.text[1:]
            self.warn(line, first.col, len(first.text), "A sentence starts with a capital letter.",
                      None, "capital", swap(line, first.col, first.end, word))
        self.articles(line)

    def articles(self, line):
        for tok, after in zip(line.tokens, line.tokens[1:]):
            if not tok.is_word("a", "an") or after.kind != "WORD":
                continue
            wanted = article_for(after.text)
            if wanted is None or wanted == tok.low:
                continue
            written = wanted.capitalize() if tok.text[0].isupper() else wanted
            sound = "a vowel sound" if wanted == "an" else "the sound of a consonant"
            self.warn(line, tok.col, len(tok.text),
                      f'Write "{written} {after.text}": "{after.text}" starts with {sound}.',
                      None, "a_an", swap(line, tok.col, tok.end, written))

    def are_after_one(self, line, tok, subject):
        """'If Gawain's purse are $300:': "is" after one thing."""
        self.warn(line, tok.col, len(tok.text),
                  f'Write "is" after one thing: "{subject} is", not "{subject} {tok.text}".', None, "is_are",
                  swap(line, tok.col, tok.end, "Is" if tok.text[0].isupper() else "is"))

    # A refused sentence ---------------------------------------------------

    def refused(self, error, line, compiler):
        """The compiler refused `line` (and its block) with `error`."""
        if not self.caused_by_hidden(error):
            self.add(error, "error", line)
        self.lost(line, compiler)

    def lost(self, line, compiler):
        """`line` will not be compiled: what it defines is unknown from now on."""
        for name in self.defined_names(line):
            if not self.known(compiler, name):
                self.hidden.add(name)
        self.remember_words(line)

    def remember_words(self, line):
        self.refused_words.update(WORD.findall(line.text.lower()))
        for child in line.children:
            self.remember_words(child)

    @staticmethod
    def known(compiler, name):
        """Does the name still have a meaning, from an earlier definition?"""
        text = " ".join(name)
        return (
            text in compiler.nouns or text in compiler.names or text in compiler.procs
            or text in compiler.workouts or text in compiler.adjective_names
            or text in compiler.member_names or compiler.scope.find(text) is not None
        )

    def caused_by_hidden(self, error):
        """Does the error only exist because an earlier definition was refused?"""
        message = error.message
        if self.unknown_library and error.key in UNKNOWN_RULES:
            return True
        if not self.hidden:
            return False
        candidates = [WORD.findall(quoted.lower()) for quoted in QUOTED.findall(message)]
        if error.line is not None and error.col is not None:
            span = error.line.text[error.col:error.col + max(1, error.width)]
            candidates.append(WORD.findall(span.lower()))
        for words in candidates:
            while words and words[0] in ARTICLES:
                words = words[1:]
            if not words:
                continue
            for name in self.hidden:
                if tuple(words[:len(name)]) == name or name[:len(words)] == tuple(words):
                    return True
                if any(tuple(words[k:k + len(name)]) == name for k in range(len(words))):
                    return True
        return False

    def defined_names(self, line):
        """The names a sentence was trying to define, worked out from its words."""
        words = [t for t in line.tokens if t.kind != "END"]
        low = [t.low if t.kind == "WORD" else t.text for t in words]

        def run_of_words(start, stops=()):
            name = []
            for tok in words[start:]:
                if tok.kind != "WORD" or tok.low in stops:
                    break
                name.append(tok.low)
            return tuple(name)

        if not low:
            return []
        first = low[0]
        if first in ("a", "an") and len(low) > 2:
            if low[2] == "(" and len(low) > 6 and low[3] == "plural" and low[6] == "has":
                # "A person (plural people) has ...": the stated plural instead of the one by rule.
                names = [(low[1],), (low[4],)]
                names += [run_of_words(k + 1) for k in range(7, len(words)) if low[k] in ("a", "an")]
                return [name for name in names if name]
            if low[2] == "has":
                # The kind, its plural, and each property: "a hoard (money)", "an owner (dragon)".
                names = [(low[1],), (pluralize(low[1]),)]
                names += [run_of_words(k + 1) for k in range(3, len(words)) if low[k] in ("a", "an")]
                return [name for name in names if name]
            if low[2] in ("is", "can"):
                at = 3 if low[2] == "is" else 4  # "A knight is <adjective>", "A knight can be <adjective>"
                adjective = low[at] if len(low) > at else None
                return [(adjective,)] if adjective and adjective != "be" else []
            return []
        if first == "the" and "of" in low:
            return [run_of_words(1, ("of",))]
        if first == "there" and "called" in low:
            return [run_of_words(low.index("called") + 1, ("whose",))]
        if first == "to" and len(low) > 1:
            if low[1:4] == ["work", "out", "the"]:
                return [run_of_words(4, ROLE_WORDS)]
            return [(low[1],)]
        if first == "let":
            start = 2 if len(low) > 1 and low[1] == "the" else 1
            return [run_of_words(start, ("be", "always"))]
        if first == "ask" and "let" in low:
            start = low.index("let") + 1
            if start < len(low) and low[start] == "the":
                start += 1
            return [run_of_words(start, ("be",))]
        if first == "use" and "chapter" in low:
            # A chapter that couldn't be used: what it shares is unknown, so leave out
            # the errors about unknown names that follow, as for an unknown library.
            self.unknown_library = True
            return []
        if first == "use" and len(low) > 2:
            return self.library_names(low[2])
        return self.assigned_name(words)

    @staticmethod
    def assigned_name(words):
        """An assignment borrowed from another language names a variable it meant to make:
        "x = 5", "x is 5", "the total is 5", "var x = 5", "int x = 5"."""
        if not words or (words[0].low in KEYWORDS and not words[0].is_word("the")):
            return []  # a sentence of EnglishScript's own, such as "If x is 1:"
        j = 0
        while j < len(words) and words[j].kind == "WORD" and not words[j].is_word("is"):
            j += 1
        if j == 0 or j >= len(words):
            return []
        op, after = words[j], words[j + 1] if j + 1 < len(words) else None
        if not (op.is_word("is") or (op.is_punct("=") and not (after and after.is_punct("=")))):
            return []
        name = [t.low for t in words[:j]]
        if len(name) > 1 and BORROWED.get(name[0]) == "variable":
            name = name[1:]
        if name and name[0] in ARTICLES:
            name = name[1:]
        return [tuple(name)] if name else []

    def library_names(self, name):
        """What a library that couldn't be used would have defined, if it can be told."""
        if name not in Compiler.library_names():
            self.unknown_library = True
            return []
        try:
            module = importlib.import_module(f"englishscript.libraries.{name}")
            lines = read_source(getattr(module, "SOURCE", ""), library=name, problems=[])
        except Exception:  # noqa: BLE001 - a library that can't even be read defines nothing
            return []
        names = []
        for line in lines:
            names.extend(self.defined_names(line))
        return names

    # Never used -----------------------------------------------------------

    def never_used(self, compiler):
        """Variables, roles, verbs, worked-out values and adjectives nothing uses."""
        seen = {}
        for what, name, line, col, width, used in compiler.declared:
            key = (line.number, col)
            entry = seen.setdefault(key, [what, name, line, col, width, False])
            entry[5] = entry[5] or used()
        messages = {
            "variable": ('"{name}" is never used after it is made.', "Use it, or take this sentence out."),
            "role": ('The role "{name}" is never used in this block.',
                     'Use "the {name}" in the block, or take the role out.'),
            "verb": ('The verb "{name}" is never used.', "Use it, or take its definition out."),
            "value": ('"The {name}" is never worked out anywhere.', "Use it, or take its definition out."),
            "adjective": ('The adjective "{name}" is never used.', "Use it, or take its definition out."),
        }
        shared = compiler.main.shares or set()  # what the file shares is there for other files to use
        for what, name, line, col, width, used in seen.values():
            if used or set(name.split(" ")) & self.refused_words:
                continue
            if what != "role" and name in shared:
                continue
            message, hint = messages[what]
            self.warn(line, col, width, message.format(name=name), hint.format(name=name), "unused")

    # The result -----------------------------------------------------------

    def result(self):
        """At most one error per line; no warning on a line with an error; in order."""
        errors, kept = {}, []
        for problem in self.problems:
            if problem.kind != "error":
                continue
            first = errors.get(problem.line)
            if first is None:
                errors[problem.line] = problem
                kept.append(problem)
            elif first.message in NO_ENDING and first in kept:
                # A missing period is easily seen; what else is wrong matters more.
                kept[kept.index(first)] = errors[problem.line] = problem
                ending = "a colon" if first.message == NO_COLON else "a period"
                problem.hint = (problem.hint + "\n" if problem.hint else "") + \
                    f"The sentence also needs {ending} at the end."
                if problem.fix is not None and first.fix is not None and problem.fix["line"] == problem.line:
                    # The correction mends both: put the missing mark on it too.
                    mark_ = ":" if first.message == NO_COLON else "."
                    text = problem.fix["text"]
                    code = len(_strip_comment(text).rstrip())
                    if not text[:code].endswith((".", ":", '"')):  # the correction may end the sentence itself
                        problem.fix = {"line": problem.line, "text": text[:code] + mark_ + text[code:]}
        seen = set()
        for problem in self.problems:
            key = (problem.line, problem.col, problem.message)
            if problem.kind == "warning" and problem.line not in errors and key not in seen:
                seen.add(key)
                kept.append(problem)
        kept.sort(key=lambda p: (p.line, -1 if p.col is None else p.col, p.kind != "error"))
        return kept

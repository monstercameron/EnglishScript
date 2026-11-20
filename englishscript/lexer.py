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


# ------------------------------------------------------------- teacher's marks
#
# Every problem is marked the way a teacher marks a paper: the words are
# underlined, what is wrong is said in the pupil's terms, the correction is
# written in where it is certain, and the rule is given with the section of
# docs/SYNTAX.md that teaches it. A problem names its rule by a key of RULES.

CATEGORIES = {
    # category -> the heading word of a mark, and how the tally counts it
    "spelling": ("Spelling", "of spelling"),
    "punctuation": ("Punctuation", "of punctuation"),
    "capitals": ("Capital letters", "of capital letters"),
    "grammar": ("Grammar", "of grammar"),
    "vocabulary": ("Vocabulary", "of vocabulary"),
    "meaning": ("Meaning", "of meaning"),
    "kinds": ("Kinds of value", "of kinds of value"),
    "layout": ("Layout", "of layout"),
    "borrowed": ("From another language", "from another language"),
    "style": ("Style", "of style"),
    "running": ("While running", "while running"),
}

RULES = {
    # key: (category, the rule to remember, the section of docs/SYNTAX.md)
    # Punctuation
    "period": ("punctuation", "A sentence ends with a period.", "1"),
    "colon": ("punctuation", "A sentence that opens a block ends with a colon, and its block is indented under it.", "1"),
    "no_colon": ("punctuation", "Only a sentence that opens a block ends with a colon: If, Otherwise, For each, "
                                "Repeat, While, Try, To and Whenever.", "1"),
    "quotes": ("punctuation", "Text goes between double quotes.", "2"),
    "fill_in": ("punctuation", "A fill-in goes between braces inside the quotes, and holds one value.", "2"),
    "brackets": ("punctuation", "Every opening bracket has a closing one.", "5.3"),
    "marks": ("punctuation", "A sentence is made of words, numbers, quoted text and the marks . , : ( ) + - * / $ %.", "1"),
    "question": ("punctuation", "A program gives instructions; it does not ask questions.", "6"),
    "list_commas": ("punctuation", 'Items in a list are separated by commas, with "and" before the last.', "4.1"),
    # Capital letters
    "capital": ("capitals", "A sentence starts with a capital letter.", "1"),
    # Layout
    "one_line": ("layout", "Each sentence goes on a line of its own.", "1"),
    "empty": ("layout", "A line holds one whole sentence.", "1"),
    "indent": ("layout", "Sentences in the same block line up, and a block is indented further than the "
                         "sentence that opens it.", "1"),
    "tabs": ("layout", "Indent with spaces, not tabs.", "1"),
    "stray_indent": ("layout", "Only a sentence that ends with a colon has sentences indented under it.", "1"),
    "empty_block": ("layout", "A sentence that ends with a colon has at least one sentence indented under it.", "1"),
    "top_level": ("layout", "Definitions are written at the top level, never inside a block.", "4"),
    "otherwise": ("layout", '"Otherwise" comes straight after an "If" block, at the same indent as the "If".', "8.1"),
    "try": ("layout", 'A "Try:" block is followed straight away by an "If that fails:" block, at the same indent.', "8.5"),
    "shares_first": ("layout", '"This chapter shares ..." is the first sentence of its file.', "9.6"),
    # Vocabulary
    "unknown": ("vocabulary", "A name is introduced by an earlier sentence before it is used.", "3"),
    "unknown_kind": ("vocabulary", 'A kind is described with "A ... has ..." before it is used.', "4.1"),
    "unknown_property": ("vocabulary", "A thing has only the properties its kind was described with, and those "
                                       "worked out for it.", "5.2"),
    "unknown_adjective": ("vocabulary", "An adjective is defined for a kind before it is used.", "4.3"),
    "unknown_verb": ("vocabulary", 'A verb is taught with "To ...:" before it is used.', "9.1"),
    "unknown_variable": ("vocabulary", 'A variable is made with "Let" before it is used.', "7.1"),
    "reserved": ("vocabulary", "A new name cannot use a word that EnglishScript already uses.", "3"),
    "names": ("vocabulary", "A name is made of words: letters, digits and underscores, starting with a letter.", "3"),
    "namespaces": ("vocabulary", "A word that is an adjective is not also the name of a kind, a thing, a variable, a "
                                 "role or a loop's thing, and no name begins with one.", "3"),
    "kind_variable": ("meaning", "Inside a block, a variable or role may have a kind's name only when it holds a "
                                 'thing of that kind, so that "the dragon" means a dragon either way.', "5.1"),
    "kind_names":("vocabulary", "Every kind has its own name and its own plural, shared with no other kind.", "4.1"),
    "taken":("vocabulary", "A name has one meaning: it cannot be given a second one while the first is in view.", "3"),
    "described_once": ("vocabulary", "A kind is described once, in one sentence that lists all its properties.", "4.1"),
    "types": ("vocabulary", "A type is number, money, text, percent, yes or no, a list, or a kind already "
                            "described.", "2"),
    "library": ("vocabulary", 'A library is used with "Use the <name> library.", and its name is one word of '
                              "letters.", "9.4"),
    "chapter": ("vocabulary", 'A chapter is used with "Use the <name> chapter." or "Use the <name> chapter of the '
                              '<book> book.", and its name is made of plain words.', "9.6"),
    "shared": ("vocabulary", "A file can say only its own names and those shared by the chapters and libraries "
                             "it uses.", "9.6"),
    "library_fault": ("vocabulary", "A library's own sentences have to be readable, like a program's.", "9.4"),
    # Grammar
    "verb_first": ("grammar", "A sentence begins with its verb, or is a definition.", "11"),
    "sentence_form": ("grammar", "Each kind of sentence has a fixed form, word for word.", "11"),
    "article": ("grammar", 'A noun takes an article: "a dragon", "an age", "the dragon".', "4.2"),
    "a_an": ("grammar", 'Write "an" before a vowel sound and "a" before any other sound.', "4.1"),
    "is_are": ("grammar", 'Write "is" after one thing and "are" after several.', "6"),
    "comparison": ("grammar", 'A comparison is written "is", "is not", "is more than", "is less than", '
                              '"is at least" or "is at most".', "6"),
    "contraction": ("grammar", 'A contraction is written out in full, such as "is not" for "isn\'t".', "6"),
    "linking_word": ("grammar", 'Each verb has its own linking word: "Add ... to", "Subtract ... from", '
                                '"Multiply ... by", "Divide ... by", "Set ... to".', "7.2"),
    "verb_roles": ("grammar", "A verb is used with the roles it was taught, each after its own linking word.", "9.2"),
    "number_agreement": ("grammar", 'A group of things is written in the plural, such as "dragons"; '
                                    '"For each" takes the singular.', "5.5"),
    "value_needed": ("grammar", "A value is a number, money, a percentage, quoted text, a name, or a phrase "
                                "made from them.", "5"),
    "definition_form": ("grammar", 'A definition starts with its kind: "A dragon has ...", "A dragon is ... when ...", '
                                   '"A dragon can be ..." or "A dragon\'s ... is never ...".', "4"),
    "plural_form": ("grammar", 'A plural that is not formed by rule is stated in brackets after the kind\'s name, '
                               'where the kind is described: "A person (plural people) has ..."', "4.1"),
    "kind_form":("grammar", 'A kind is described as "A <kind> has a <property> (<type>) and a <property> '
                             '(<type>)."', "4.1"),
    "thing_form": ("grammar", 'A thing is made as "There is a <kind> called <Name> whose <property> is '
                              '<value>."', "4.2"),
    "adjective_form": ("grammar", 'An adjective is defined as "A <kind> is <adjective> when <condition>." or '
                                  '"A <kind> can be <adjective>."', "4.3"),
    "property_form": ("grammar", 'A worked-out property is defined as "The <property> of a <kind> is <value>."', "4.4"),
    "rule_form": ("grammar", 'A rule is written "A <kind>\'s <property> is never ..." or "... is always ...".', "4.5"),
    "let_form": ("grammar", 'A variable is made as "Let <name> be <value>."', "7.1"),
    "ask_form": ("grammar", 'A question is asked as "Ask <text> and let <name> (<type>) be the reply."', "7.6"),
    "file_form": ("grammar", 'Text is written to a file as "Write <text> to the file <name>."', "7.7"),
    "loop_form": ("grammar", 'A loop is written "For each <kind>:", "Repeat <number> times:" or '
                             '"While <condition>:".', "8.2"),
    "leaving_form": ("grammar", 'A block is left with "Stop.", "Stop repeating.", "Skip this round.", '
                                '"Skip this <thing>." or "End the program."', "8.4"),
    "fail_form": ("grammar", 'A problem of the program\'s own is raised with "Fail because <text>."', "8.5"),
    "verb_form": ("grammar", 'A verb is taught as "To <verb> a <kind> <linking word> a <kind>:", with a '
                             "linking word before each role after the first.", "9.1"),
    "workout_form": ("grammar", 'A worked-out value is taught as "To work out the <name> (<type>) of a <kind>:".', "9.3"),
    "reaction_form": ("grammar", 'A reaction is written "Whenever a <kind> becomes <adjective>:" or '
                                 '"Whenever <Name> becomes <adjective>:".', "9.5"),
    "use_form": ("grammar", 'A library or chapter is used with "Use the <name> library.", "Use the <name> '
                            'chapter." or "Use the <name> chapter of the <book> book."', "9.6"),
    "shares_form": ("grammar", 'A chapter lists what it shares as "This chapter shares only <name> and <name>." '
                               'or "This chapter shares nothing."', "9.6"),
    "has_form": ("grammar", 'A missing property is tested with "<thing> has a <property>" or "<thing> has no '
                            '<property>".', "2"),
    "new_thing": ("grammar", 'A new thing is made with "There is a new ..." or as the whole value of "Let".', "7.5"),
    # Meaning
    "value_order": ("meaning", 'A phrase that could be grouped two ways is written with brackets: "or else", '
                               '"whether" and a group\'s "whose" do not stand beside + - * / or "and" and "or" '
                               "without them.", "5.3"),
    "pronoun":("meaning", "A pronoun (it, its, they, them, their) points at the one thing in view, so there has "
                           "to be exactly one.", "5.1"),
    "the_noun": ("meaning", '"The" with a kind points at the one such thing in view, so there has to be exactly '
                            "one.", "5.1"),
    "and_or": ("meaning", '"And" and "or" are not mixed without brackets, and a "not" before "and" or "or" '
                          "needs brackets to say how much it turns round.", "6"),
    "of_link": ("meaning", '"Of" between two kinds needs exactly one property that links them.', "5.5"),
    "maybe_nothing": ("meaning", "A value that may be nothing is checked before it is used.", "2"),
    "nothing_checks": ("meaning", "Only a value that may be nothing needs checking for nothing.", "2"),
    "one_loop": ("meaning", '"Stop repeating" and "Skip" need exactly one loop around them to leave.', "8.4"),
    "place": ("meaning", "Some sentences belong inside a particular block, and mean nothing anywhere else.", "8.4"),
    "answer_place": ("meaning", '"The answer is ..." is said only inside a "To work out ...:" block.', "9.3"),
    "answer_paths": ("meaning", 'Every way through a "To work out" block ends with "The answer is ...".', "9.3"),
    "working_out": ("meaning", "Working something out only works it out: it does not say, make, change or "
                               "remove anything.", "9.3"),
    "changeable": ("meaning", 'Only a variable or a stored property can be changed, and not one made with "always".', "7.2"),
    "rule_reads": ("meaning", "A rule is checked when its thing's stored properties change, so it may depend only on "
                              'what cannot change behind its back: values written out, variables made with "always", '
                              "and the thing's own stored properties.", "4.5"),
    "ambiguous_name":("meaning", "Every name in view has one meaning, so that each phrase reads one way.", "3"),
    # Kinds of value
    "arith": ("kinds", "Arithmetic needs values that go together: money with money, and plain numbers with plain "
                       "numbers or money.", "5.3"),
    "compare_kinds": ("kinds", "Only values of the same kind can be compared, and only numbers, money and "
                               "percentages can be more or less than each other.", "6"),
    "fit": ("kinds", "A property, variable, role or answer holds only the kind of value it was described with.", "2"),
    "text_only": ("kinds", "Text is worked on only as text: a number or money is not text.", "5.6"),
    "list": ("kinds", "A list holds values of one kind, numbered from 1. It is written out only as the whole value "
                      'of "Let", "Set", a "whose" part or "The answer is", and cannot yet be said or compared.', "2"),
    "percent": ("kinds", "A percentage is taken of a number or of money.", "5.4"),
    "props_of": ("kinds", "Only a thing has properties and adjectives.", "5.2"),
    "yes_no_property": ("kinds", "A yes-or-no fact about a thing is an adjective, not a property.", "4.3"),
    # From another language
    "say": ("borrowed", 'Things are shown with "Say".', "7.3"),
    "else": ("borrowed", '"Otherwise" and "Otherwise if" follow an "If" block.', "8.1"),
    "then": ("borrowed", 'A condition ends with a colon, not with "then".', "8.1"),
    "return": ("borrowed", 'A worked-out value gives its answer with "The answer is ...".', "9.3"),
    "remove": ("borrowed", 'A thing is taken out of the world with "Remove".', "7.5"),
    "make": ("borrowed", 'A thing is made with "There is a new ...".', "7.5"),
    "define": ("borrowed", 'A verb is taught with "To ...:" and a value worked out with "To work out ...:".', "9.1"),
    "variable": ("borrowed", 'A variable is made with "Let", and needs no type word.', "7.1"),
    "set": ("borrowed", 'A variable is changed with "Set ... to ...".', "7.1"),
    "increase": ("borrowed", 'Numbers and money are changed with "Add ... to" and "Subtract ... from".', "7.2"),
    "ask": ("borrowed", 'The person at the keyboard is asked with "Ask ... and let ... be the reply."', "7.6"),
    "use": ("borrowed", 'A library is used with "Use the <name> library."', "9.4"),
    "loop": ("borrowed", 'Loops are written "For each ...:", "Repeat ... times:" and "While ...:".', "8.3"),
    "block_end": ("borrowed", "A block ends where its indentation ends.", "1"),
    "leave": ("borrowed", 'A loop is left with "Stop repeating.", a round skipped with "Skip this round.", and '
                          'the program ended with "End the program."', "8.4"),
    "symbols": ("borrowed", 'Conditions are tested with "is" and joined with the words "and", "or" and "not".', "6"),
    "call": ("borrowed", "A verb is used as a sentence, and a worked-out value as a phrase.", "9.2"),
    "values": ("borrowed", 'The yes-or-no values are "yes" and "no", and a missing value is "nothing".', "2"),
    "semicolon": ("borrowed", "Each sentence goes on a line of its own.", "1"),
    # Style (warnings)
    "unused": ("style", "Whatever a program makes, it uses; what it never uses can be taken out.", "3"),
    "unreachable": ("style", "A sentence straight after one that always leaves its block is never carried out.", "8.4"),
    # While running
    "rule_broken": ("running", 'A change that would break a "never" or "always" rule is refused, and the program '
                               'stops unless a "Try" catches it.', "4.5"),
    "example": ("running", 'A "For example" sentence has to hold when it is reached.', "7.4"),
    "zero": ("running", "Nothing can be divided by zero.", "5.3"),
    "choices_form": ("grammar", 'A set of choices is written "A mood is one of sleepy, grumpy or content.": the '
                                'choices separated by commas, with "or" before the last.', "4.6"),
    "count": ("running", "A count of times or of letters is a whole number, and not negative.", "8.3"),
    "rounding": ("running", "A value is rounded to a step of more than nothing; a negative number has no square "
                            "root, and is raised only to a whole power.", "5.3"),
    "file": ("running", "A file that is read has to be there, and a file that is written has to be writable.", "7.7"),
    "missing_item": ("running", "An item can be changed only where there is one: the items of a list are numbered "
                                "from 1 to the number of items.", "2"),
    "removed": ("running", "A removed thing cannot be used, and a thing cannot be removed while a property that "
                           'is not "if any" points at it.', "7.5"),
    "fail": ("running", '"Fail because" stops the program, unless a "Try" around it catches the problem.', "8.5"),
    "loop_limit": ("running", 'A "While" loop has to end: I stop one after 1,000,000 rounds.', "8.3"),
    "depth": ("running", "A verb, a worked-out value or a reaction may set off itself, but not more than 200 "
                         "levels deep.", "9.1"),
    "library_run": ("running", "A library's own fault is the library's, not the program's.", "9.4"),
}


def classify(message, stage):
    """The rule of a problem that was not given one: the general rule for its stage."""
    return "fail" if stage == "run" else "sentence_form"


def rule_line(rule, see):
    """'The rule: a sentence ends with a period. (See section 1.)'"""
    first = rule.split(" ", 1)[0]
    if not (rule.startswith('"') or first in ("EnglishScript", "I") or first[1:2].isupper()):
        rule = rule[:1].lower() + rule[1:]
    return f"The rule: {rule} (See section {see}.)"


def correction_under(sentence, col, width, fixed):
    """The words that take the place of the underlined ones, if the correction
    changes nothing else; otherwise None."""
    if fixed is None or col is None:
        return None
    before, after = sentence[:col], sentence[col + max(1, width):]
    if not fixed.startswith(before) or not fixed.endswith(after) or len(fixed) < len(before) + len(after):
        return None
    words = fixed[len(before):len(fixed) - len(after)]
    return words if words.strip() else None


def mark(category, where, sentence, col, width, message, hint, rule, see, fixed, warning=False, notes=()):
    """A problem as a teacher marks it. `fixed` is the corrected line, when it is
    this line and certain; `notes` are lines about where it happened."""
    head = CATEGORIES.get(category, CATEGORIES["grammar"])[0]
    if warning:
        head += ", a suggestion"
    out = [f"{head} ({where}):" if where else f"{head}:"]
    correction = None
    if sentence is not None:
        lead = len(sentence) - len(sentence.lstrip())
        out += ["", "    " + sentence.strip()]
        if col is not None:
            pad = "    " + " " * max(0, col - lead)
            out.append(pad + "^" * max(1, width))
            correction = correction_under(sentence, col, width, fixed)
            if correction is not None:
                out.append(pad + correction.strip())
    out += ["", "  " + message]
    if hint:
        out.extend("  " + h for h in hint.split("\n"))
    if fixed is not None and correction is None and fixed.strip() not in (hint or ""):
        out.append("  Write: " + fixed.strip())
    out.extend("  " + note for note in notes)
    if rule:
        out.append("  " + rule_line(rule, see))
    return "\n".join(out)


class EnglishError(Exception):
    """A problem with a program, phrased for the person who wrote it.

    `teach` is a key of RULES, which gives the problem its category, the rule
    to remember and the section that teaches it; `category` may override the
    category (a misspelt name keeps the rule of an unknown one). `fix` is the
    corrected line, when the correction is certain: its text, for the line of
    the problem, or (Line, text) for another line.
    """

    def __init__(self, message, line=None, col=None, width=1, hint=None, stage="compile", recoverable=False,
                 teach=None, fix=None, category=None):
        super().__init__(message)
        self.message = message
        self.line = line
        self.col = col
        self.width = width
        self.hint = hint
        self.stage = stage  # "compile" or "run"
        # A problem in the world (a broken rule, a missing file) that "Try:" may
        # recover from, as opposed to a fault in the program itself.
        self.recoverable = recoverable
        self.trace = []
        self.fix_text = fix
        self.teach(teach or classify(message, stage), category)

    def teach(self, key, category=None):
        """Give the problem the rule `key` (and perhaps another category)."""
        self.key = key
        found, self.rule, self.see = RULES[key]
        self.category = category or ("running" if self.stage == "run" else found)
        return self

    @property
    def fix(self):
        """{"line": number, "text": the line as it should be}, or None."""
        found = self.fix_text
        if found is None:
            return None
        line, text = found if isinstance(found, tuple) else (self.line, found)
        if line is None:
            return None
        return {"line": line.number, "text": text}

    def render(self, filename=None, location=True):
        chapter = chapter_of(self.line)
        where, sentence = None, None
        if self.line is not None:
            where = f"line {self.line.number}"
            if self.line.library:
                where = f"{where} of the {self.line.library} library"
            elif chapter is not None:
                where = f"{chapter.file}, {where}"
            elif filename:
                where = f"{filename}, {where}"
            sentence = self.line.raw if self.line.raw is not None else self.line.text
        notes = [f"(while doing {place(caller)}: {caller.text.strip()})" for caller in self.trace]
        if chapter is not None and chapter.used_at is not None:
            used = chapter.used_at
            notes.append(f"({chapter.title[:1].upper() + chapter.title[1:]} is used at "
                         f"{place(used, filename)}: {used.text.strip()})")
        fix = self.fix
        fixed = fix["text"] if fix is not None and self.line is not None and fix["line"] == self.line.number \
            and not isinstance(self.fix_text, tuple) else None
        return mark(self.category, where if location else None, sentence, self.col, self.width, self.message,
                    self.hint, self.rule, self.see, fixed, notes=notes)


def chapter_of(line):
    """The chapter a line is from, or None for a line of the program or of a library."""
    unit = getattr(line, "unit", None)
    return unit if unit is not None and getattr(unit, "kind", None) == "chapter" else None


def place(line, filename=None):
    """'line 7', or 'almanac/feasts.english, line 7' for a line of a chapter."""
    chapter = chapter_of(line)
    if chapter is not None:
        return f"{chapter.file}, line {line.number}"
    if line.library:
        return f"line {line.number} of the {line.library} library"
    # The program's own file is named as the chapters are: by its name, not its whole path.
    filename = getattr(getattr(line, "unit", None), "file", None) or filename
    if filename:
        return f"{filename}, line {line.number}"
    return f"line {line.number}"


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
    library: str = None  # the library whose SOURCE this line is from, if any
    unit: object = None  # the file it is from (compiler.Unit): the program, a chapter or a library
    # Only when the linter reads a program with problems in its layout:
    broken: bool = False  # its words couldn't be read, so it is not compiled
    unfinished: bool = False  # it had no period or colon
    stray: bool = False  # sentences are indented under it, but it doesn't open a block
    raw: str = None  # the line as written, comment included, for corrections
    after: object = None  # the next line of the file, if any
    question: bool = False  # it ended with "?" and reads as a question; the compiler explains


TOKEN_RE = re.compile(
    r"""
    (?P<STRING>"(?:[^"]|"")*")
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


CONTRACTIONS = {
    "isn't": "is not", "aren't": "are not", "wasn't": "was not", "weren't": "were not",
    "don't": "do not", "doesn't": "does not", "didn't": "did not", "can't": "cannot", "won't": "will not",
    "hasn't": "has not", "haven't": "have not", "hadn't": "had not", "shouldn't": "should not",
    "couldn't": "could not", "wouldn't": "would not", "mustn't": "must not", "i'm": "I am",
    "you're": "you are", "we're": "we are", "they're": "they are", "i'll": "I will", "you'll": "you will",
    "we'll": "we will", "they'll": "they will", "it'll": "it will", "i've": "I have", "you've": "you have",
    "we've": "we have", "they've": "they have", "i'd": "I would", "you'd": "you would",
}


def swap(line, start, end, new):
    """The line as written, with its characters from `start` to `end` replaced by `new`."""
    text = line.raw if getattr(line, "raw", None) is not None else line.text
    return text[:start] + new + text[end:]


def _contraction(text, pos):
    """(start, end, word, in full) for a contraction such as "isn't" around `pos`, or None."""
    start = pos
    while start > 0 and text[start - 1].isalpha():
        start -= 1
    end = pos + 1
    while end < len(text) and text[end].isalpha():
        end += 1
    word = text[start:end]
    full = CONTRACTIONS.get(word.lower())
    if full is None or start == pos:
        return None
    if word[:1].isupper() and not full.startswith("I "):
        full = full[:1].upper() + full[1:]
    return start, end, word, full


def _symbol_advice(text, pos, line):
    """(message, hint, rule, start, width, fix) for a character EnglishScript doesn't
    use, often borrowed from another programming language."""
    ch, nxt = text[pos], text[pos + 1:pos + 2]
    at_end = not text[pos + 1:].strip()
    if ch == "!" and nxt == "=":
        return ('EnglishScript doesn\'t use "!=".',
                'To test that two values differ, write "is not": "If the count is not 3:".', "symbols", pos, 2, None)
    if ch in "!?" and at_end:
        name = "an exclamation mark" if ch == "!" else "a question mark"
        return (f"A sentence ends with a period, not with {name}.", None, "period", pos, 1,
                swap(line, pos, pos + 1, "."))
    if ch == "!":
        return ('EnglishScript doesn\'t use "!".',
                'To turn a condition round, write "not" in front of it: "If not Smaug is ancient:".', "symbols", pos,
                2 if nxt == "!" else 1, None)
    if ch == "&":
        return ('EnglishScript doesn\'t use "&".', 'To join two conditions, write "and": "If x is 1 and y is 2:".',
                "symbols", pos, 2 if nxt == "&" else 1, None)
    if ch == "|":
        return ('EnglishScript doesn\'t use "|".', 'To offer two conditions, write "or": "If x is 1 or y is 2:".',
                "symbols", pos, 2 if nxt == "|" else 1, None)
    if ch == ";":
        return ('EnglishScript doesn\'t use ";".', "Write one sentence per line, and end each with a period.",
                "semicolon", pos, 1, None)
    if ch in "{}":
        return (
            f'EnglishScript doesn\'t use "{ch}" outside quotes.',
            "A block is the sentences indented under a line that ends with a colon,\n"
            "and it ends where the indentation ends. Braces are only for fill-ins inside quotes.",
            "block_end", pos, 1, None,
        )
    if ch == "'":
        found = _contraction(text, pos)
        if found:
            start, end, word, full = found
            return (f'I don\'t read contractions: "{word}" is written out in full, as "{full}".', None,
                    "contraction", start, end - start, swap(line, start, end, full))
        close = text.find("'", pos + 1)
        inside = text[pos + 1:close] if close > pos else None
        # Repeat their text only where it can't be misread inside double quotes.
        safe = inside is not None and not any(ch in inside for ch in '"{}')
        example = f'"{inside}"' if safe else '"..."'
        fix = swap(line, pos, close + 1, example) if safe else None
        return ("Text goes between double quotes, not single ones.", f"Write {example}.", "quotes", pos, 1, fix)
    return (f'EnglishScript doesn\'t use "{ch}".', "A sentence holds words, numbers, quoted text and the marks "
            ". , : ( ) + - * / $ %.", "marks", pos, 1, None)


def tokenize(text, line, start, end, partial=None):
    """Tokens for text[start:end]. Columns are positions in the whole line.

    If `partial` is a list, the tokens read before a problem are left in it.
    """
    tokens = [] if partial is None else partial
    pos = start
    while pos < end:
        m = TOKEN_RE.match(text, pos, end)
        if not m:
            if text[pos] == '"':
                body = text.rstrip()
                fix = swap(line, 0, len(body), body + '"') if end == len(text) else None
                raise EnglishError("This quotation has no closing quote.", line, pos, 1,
                                   'A text ends with a second ", where its words end.', teach="quotes", fix=fix)
            message, hint, rule, at, width, fix = _symbol_advice(text, pos, line)
            raise EnglishError(message, line, at, width, hint, teach=rule, fix=fix)
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
                value = raw[1:-1].replace('""', '"')  # "" inside quotes is one quote
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


def read_source(source, library=None, problems=None, unit=None):
    """Source text -> top-level Lines, each with its indented children.

    `library` names the library whose SOURCE this is, so that its lines are
    never mistaken for lines of the program. `unit` is the file the text is
    from (a compiler.Unit), kept on every line.

    Without `problems`, the first problem with the layout is raised. With a
    list, every problem is added to it and reading carries on, for the linter:
    a line whose words can't be read is kept, marked `broken`, with the tokens
    read before the problem; a line with no period is read as if it had one
    (or a colon, if the next line is indented further).
    """
    def report(error):
        if problems is None:
            raise error
        problems.append(error)

    source = source.replace("“", '"').replace("”", '"').replace("’", "'")
    written = []  # (number, raw, text) of each line with a sentence on it
    for number, raw in enumerate(source.splitlines(), 1):
        text = _strip_comment(raw).rstrip()
        if text.strip():
            written.append((number, raw, text))
    lines = []
    for k, (number, raw, text) in enumerate(written):
        indent = len(text) - len(text.lstrip())
        line = Line(number, text, indent, library=library, unit=unit, raw=raw)
        if lines:
            lines[-1].after = line
        lines.append(line)
        if "\t" in text[:indent]:
            report(EnglishError("This line is indented with a tab.", line, 0, indent,
                                "Indent it with spaces instead.", teach="tabs"))
            line.broken = True
        words = text.split()
        if text.endswith("?") and words[0].lower() in QUESTION_WORDS:
            line.question = True  # the compiler explains, once it knows the words
            text = text[:-1].rstrip() + "."
            line.text = text
        tokens = []
        try:
            tokenize(text, line, indent, len(text), tokens)
        except EnglishError as error:
            report(error)
            line.broken = True
            line.terminator = ":" if text.endswith(":") else "."
            tokens.append(Token("END", "", len(text)))
            line.tokens = tokens
            continue
        if _two_sentences(line, tokens, report):
            line.broken = True
            line.terminator = ":" if text.endswith(":") else "."
            tokens.append(Token("END", "", len(text)))
            line.tokens = tokens
            continue
        last = tokens[-1]
        end_col = len(text)
        if last.is_punct(".", ":"):
            line.terminator = last.text
            end_col = last.col
            tokens.pop()
        elif last.kind != "STRING":  # a closing quote may end a sentence
            # It opens a block if the next sentence is indented further.
            opens = k + 1 < len(written) and _indent_of(written[k + 1][2]) > indent
            mark_ = ":" if opens else "."
            report(EnglishError(NO_COLON if opens else NO_PERIOD, line, len(text), 1, teach="colon" if opens else "period",
                                fix=swap(line, len(text), len(text), mark_)))
            line.unfinished = True  # read as if it ended properly; see below
        if not tokens:
            report(EnglishError("This line has a period but no sentence.", line, indent, 1,
                                "Write the sentence in front of the period, or take the line out.", teach="empty"))
            line.broken = True
        tokens.append(Token("END", "", end_col))
        line.tokens = tokens
    # A sentence with no period or colon opens a block if the next one is indented further.
    for line, after in zip(lines, lines[1:]):
        if line.unfinished and after.indent > line.indent:
            line.terminator = ":"
    return _nest(lines, report)


NO_PERIOD = "This sentence has no period at the end."
NO_COLON = "This sentence opens a block, so it needs a colon at the end."
# Words a question starts with. "Is Smaug ancient?" is explained by the compiler.
QUESTION_WORDS = {
    "is", "are", "does", "do", "did", "can", "has", "have", "was", "were", "will", "should", "could",
    "would", "shall", "may", "what", "who", "which", "how", "why", "where",
}
# Sentences that open a block, by their first word ("For example" is not one).
OPENERS = ("if", "otherwise", "for", "repeat", "while", "try", "to", "whenever")


def _indent_of(text):
    return len(text) - len(text.lstrip())


def _two_sentences(line, tokens, report):
    """Report a line with a sentence after a period or a colon, such as
    "Tax Smaug. Tax Glaurung." or "If x is 1: Say 2.". Returns True if it has one."""
    cuts = [k for k, (tok, after) in enumerate(zip(tokens, tokens[1:]))
            if tok.is_punct(".", ":") and after.kind == "WORD" and after.col > tok.end]
    if not cuts:
        return False
    text = line.text
    k = cuts[0]
    second = tokens[k + 1]
    if tokens[k].text == ":":
        inner = " " * (line.indent + 2)
        report(EnglishError(
            "The sentences of a block go on the lines under it, not on the same line.", line, second.col,
            len(text) - second.col,
            "Write:\n    " + text[line.indent:tokens[k].end].strip() + "\n    " + inner[line.indent:]
            + text[second.col:].strip(), teach="one_line"))
        return True
    parts, start = [], line.indent
    for cut in cuts:
        parts.append(text[start:tokens[cut].end].strip())
        start = tokens[cut + 1].col
    parts.append(text[start:].strip())
    report(EnglishError(
        f"This line holds {len(parts) if len(parts) > 2 else 'two'} sentences.", line, second.col,
        len(text) - second.col, "Each goes on a line of its own:\n" + "\n".join("    " + part for part in parts),
        teach="one_line"))
    return True


def _raise(error):
    raise error


def _nest(lines, report=_raise):
    root = []
    stack = [(0, root)]  # (indent, the list sentences at that indent go into)
    prev = None
    for line in lines:
        if prev is None:
            if line.indent:
                report(EnglishError("The first sentence of a file starts at the left edge, with no spaces "
                                    "in front of it.", line, 0, line.indent, teach="indent"))
                stack = [(line.indent, root)]
        elif line.indent > prev.indent:
            if prev.terminator != ":":
                report(EnglishError(
                    "This line is indented, but the sentence above it does not open a block.",
                    line, 0, line.indent,
                    hint="If it belongs to the sentence above, end that sentence with a colon.\n"
                         "If not, take away the spaces in front of this line.",
                    teach="stray_indent",
                ))
                prev.stray = True  # its "block" is never compiled
            stack.append((line.indent, prev.children))
        else:
            while len(stack) > 1 and stack[-1][0] > line.indent:
                stack.pop()
            if stack[-1][0] != line.indent:
                report(EnglishError(
                    "This line does not line up with any sentence above it.",
                    line, 0, max(1, line.indent),
                    "Start it in the same column as the sentences of the block it belongs to.",
                    teach="indent",
                ))
                if line.indent < stack[0][0]:
                    stack[0] = (line.indent, root)
                else:  # treat this indent as one more level of the same block
                    stack.append((line.indent, stack[-1][1]))
        stack[-1][1].append(line)
        prev = line
    steps = [b.indent - a.indent for a, b in zip(lines, lines[1:]) if b.indent > a.indent]
    _check_blocks(root, report, min(steps) if steps else 2)
    return root


def _check_blocks(lines, report=_raise, step=2):
    for line in lines:
        if line.terminator == ":" and not line.children and not line.broken:
            first = line.tokens[0] if line.tokens else None
            opens = first is not None and first.is_word(*OPENERS) and not line.tokens[1].is_word("example")
            colon = len(line.text) - 1
            if not opens:
                report(EnglishError(
                    "This sentence does not open a block, so it ends with a period, not a colon.",
                    line, colon, 1, teach="no_colon", fix=swap(line, colon, colon + 1, "."),
                ))
            else:
                after, fix = line.after, None
                if (after is not None and after.indent == line.indent and not after.broken and after.tokens
                        and not after.tokens[0].is_word("otherwise", "to", "whenever", "use", "this", "there", "a", "an")
                        and not (after.tokens[0].is_word("if") and after.tokens[1].is_word("that"))):
                    raw = after.raw if after.raw is not None else after.text
                    fix = (after, " " * (line.indent + step) + raw.lstrip())
                report(EnglishError(
                    "This sentence ends with a colon, so it opens a block, but nothing is indented under it.",
                    line, colon, 1,
                    "Indent the sentences that belong to it under it.", teach="empty_block", fix=fix,
                ))
        _check_blocks(line.children, report, step)

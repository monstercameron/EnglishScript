"""A language server for EnglishScript, speaking the Language Server Protocol over stdio.

    python -m englishscript.server

An editor starts this and talks to it through its standard input and output:
JSON-RPC 2.0 messages, each behind a `Content-Length` header. It needs
nothing but Python's standard library.

What it does
------------

* Marks every problem the linter finds, as the editor's diagnostics.
* Offers each certain correction as a quick fix ("Mend: ..."), and all of
  them at once.
* On hover, says how a sentence was read (what `--explain` prints), or what
  is wrong with it.
* Gives an outline of the file, goes from a name to the sentence that
  defines it (into a chapter's file too), and suggests sentence forms and
  names while you write.
* Renames a name throughout the file, through rename.py, which refuses any
  rename the compiler likes less than what was there.

How it is put together
----------------------

`Server` knows nothing about pipes. `Server.handle` takes one message as a
dict and gives back the messages to send, as dicts, so the tests drive it
directly. `serve` is the loop that frames messages on a pair of streams.

Problems, and the notes on how each sentence was read, come from
`englishscript.lint`. The outline, the definitions and the suggestions come
from rename.py's `read_program`: the compiler's own table of names
(`englishscript.names`) where it has one, and under it `read_names`, a reading
of the *text* that recognises the sentence forms that define names. The text
reading supplies what the table leaves out (a loop's name, a library's words,
a verb's roles) and stands in for the table if the compiler can't give it;
alone, it can be wrong about a sentence the compiler refuses. A chapter that
is open in the editor is read from the editor, saved or not, by all of them.

Positions. The compiler counts lines as `str.splitlines` does and columns in
characters. The protocol counts lines by \\n, \\r\\n and \\r only, and columns
in UTF-16 code units. `Text` converts between the two.
"""
from __future__ import annotations

import bisect
import importlib
import json
import os
import re
import sys
import traceback
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib.request import url2pathname

from . import rename as renaming

REFERENCE = "https://monstercameron.github.io/EnglishScript/reference.html"

# JSON-RPC and LSP error codes.
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INTERNAL_ERROR = -32700, -32600, -32601, -32603
NOT_INITIALIZED, REQUEST_FAILED = -32002, -32803


class Refused(Exception):
    """A request that can't be answered; becomes a JSON-RPC error."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# ------------------------------------------------------------------ positions

_BREAK = re.compile(r"\r\n|\r|\n")


def utf16_length(text):
    return sum(2 if ord(ch) > 0xFFFF else 1 for ch in text)


class Text:
    """A document's text, with both ways of counting where something is."""

    def __init__(self, text):
        self.text = text
        self.lines = text.splitlines()  # as the compiler counts them
        self.starts, self.ends = [], []  # where each of those starts, and where the next begins
        at = 0
        for kept in text.splitlines(keepends=True):
            self.starts.append(at)
            at += len(kept)
            self.ends.append(at)
        self.rows = [0] + [m.end() for m in _BREAK.finditer(text)]  # where each line starts, as an editor counts

    def line(self, number):
        return self.lines[number] if 0 <= number < len(self.lines) else ""

    def at(self, number, col):
        """The offset of a column (in characters) of a line (counting from 0, as the compiler's lines)."""
        if number < 0 or not self.lines:
            return 0
        if number >= len(self.lines):
            return len(self.text)
        return self.starts[number] + max(0, min(col, len(self.lines[number])))

    def where(self, offset):
        """(line, column) of an offset, as the compiler counts. The line after the last one,
        where the text ends with a line break, is given as a line of its own."""
        if not self.lines:
            return 0, 0
        offset = max(0, min(offset, len(self.text)))
        number = bisect.bisect_right(self.starts, offset) - 1
        col = offset - self.starts[number]
        if col > len(self.lines[number]):
            if offset >= self.ends[number] and self.ends[number] > self.starts[number] + len(self.lines[number]):
                return number + 1, 0
            col = len(self.lines[number])
        return number, col

    def position(self, offset):
        """An offset as the protocol's position: a line, and a column in UTF-16 code units."""
        offset = max(0, min(offset, len(self.text)))
        row = bisect.bisect_right(self.rows, offset) - 1
        return {"line": row, "character": utf16_length(self.text[self.rows[row]:offset])}

    def offset(self, position):
        """The offset of a position. One past the end of its line is taken as the end of the line."""
        row, character = int(position.get("line", 0)), int(position.get("character", 0))
        if row < 0:
            return 0
        if row >= len(self.rows):
            return len(self.text)
        at = self.rows[row]
        end = self.rows[row + 1] if row + 1 < len(self.rows) else len(self.text)
        while end > at and row + 1 < len(self.rows) and self.text[end - 1] in "\r\n":
            end -= 1
        units = 0
        while at < end:
            width = 2 if ord(self.text[at]) > 0xFFFF else 1
            if units + width > character:
                break
            units += width
            at += 1
        return at

    def range(self, number, start, end):
        """The protocol's range for columns start to end of one of the compiler's lines."""
        return {"start": self.position(self.at(number, start)), "end": self.position(self.at(number, end))}

    def span(self, first, start, last, end):
        return {"start": self.position(self.at(first, start)), "end": self.position(self.at(last, end))}


def path_of(uri):
    """The file a file: URI names, or None for any other URI."""
    try:
        parts = urlparse(uri)
    except (ValueError, TypeError, AttributeError):
        return None
    if parts.scheme != "file":
        return None
    raw = parts.path
    if re.match(r"/[A-Za-z]%3[Aa]", raw):  # some editors write the colon of "C:" as %3A
        raw = raw[:2] + ":" + raw[5:]
    if parts.netloc and parts.netloc != "localhost":
        raw = "//" + parts.netloc + raw
    try:
        return Path(url2pathname(raw))
    except (ValueError, OSError):
        return None


def same_file(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def uri_beside(uri, path, other):
    """The URI of the file `other`, written like `uri` (which names `path`) where it is beside or below it."""
    try:
        relative = Path(os.path.abspath(other)).relative_to(Path(os.path.abspath(path)).parent)
        return uri.rsplit("/", 1)[0] + "/" + "/".join(quote(part) for part in relative.parts)
    except ValueError:
        return Path(os.path.abspath(other)).as_uri()


class Document:
    def __init__(self, uri, text, version=None):
        self.uri = uri
        self.version = version
        self.text = Text(text)
        self.path = path_of(uri)
        self.problems = None  # the linter's problems, as dicts, once asked for
        self.notes = None  # {line number: [how it was read]}; None until asked for, False if they can't be had
        self.program = None  # (rename.Reading of the text, the chapters and libraries it uses), once asked for

    @property
    def folder(self):
        return str(self.path.parent) if self.path is not None else None

    @property
    def name(self):
        return str(self.path) if self.path is not None else None


# ----------------------------------------------------------- what is offered

# The sentence forms, as snippets, from the README's table. `where` is "top" for
# a definition (allowed only at the top level), "block" for a sentence that
# belongs inside a block, and "any" otherwise.
OPENERS = [
    ("Say \"…\"", 'Say "$1"', "any", "Say a text. Values go in {braces}."),
    ("Say ….", "Say ${1:the total}.", "any", "Say a value."),
    ("Let the … be ….", "Let the ${1:total} be ${2:0}.", "any", "Make a variable."),
    ("Let the … always be ….", "Let the ${1:tax rate} always be ${2:10%}.", "any",
     "Make a variable that never changes."),
    ("Let the … be a list of …, … and ….", "Let the ${1:scores} be a list of ${2:3}, ${3:8} and ${4:5}.", "any",
     "Make a list, written out."),
    ("Let the … be an empty list of ….", "Let the ${1:scores} be an empty list of ${2:numbers}.", "any",
     "Make a list with nothing in it."),
    ("Set … to ….", "Set ${1:the total} to ${2:0}.", "any", "Change a variable or a property."),
    ("Add … to ….", "Add ${1:1} to ${2:the total}.", "any",
     "Add to a number, or put a value at the end of a list."),
    ("Remove … from ….", "Remove ${1:3} from ${2:the scores}.", "any", "Take a value out of a list."),
    ("Set item … of … to ….", "Set item ${1:1} of ${2:the scores} to ${3:0}.", "any",
     "Replace an item of a list."),
    ("Subtract … from ….", "Subtract ${1:1} from ${2:the total}.", "any",
     "Subtract from a variable or a property."),
    ("Multiply … by ….", "Multiply ${1:the total} by ${2:2}.", "any", "Multiply a variable or a property."),
    ("Divide … by ….", "Divide ${1:the total} by ${2:2}.", "any", "Divide a variable or a property."),
    ("If …:", "If ${1:the total is more than 0}:\n  $0", "any", "Do the block if the condition holds."),
    ("Otherwise if …:", "Otherwise if ${1:the total is 0}:\n  $0", "any", "After an If: another condition."),
    ("Otherwise:", "Otherwise:\n  $0", "any", "After an If: when no condition held."),
    ("For each …:", "For each ${1:dragon}:\n  $0", "any", "Go through the things of a kind."),
    ("For each … in …:", "For each ${1:rival} in ${2:dragons}:\n  $0", "any",
     "Go through a group or a list, giving each a name."),
    ("Repeat … times:", "Repeat ${1:3} times:\n  $0", "any", "Do the block a number of times."),
    ("While …:", "While ${1:the total is less than 10}:\n  $0", "any", "Do the block while the condition holds."),
    ("Try:", "Try:\n  $1\nIf that fails:\n  $0", "any", "Recover from a problem."),
    ("Either way:", "Either way:\n  $0", "any", "After If that fails: what is done whether the Try failed or not."),
    ("Fail because \"…\"", 'Fail because "${1:the reason}".', "any", "Stop with a problem a Try can recover from."),
    ("There is a … called … whose … is ….", "There is a ${1:dragon} called ${2:Smaug} whose ${3:age} is ${4:771}.",
     "top", "Make a thing with a name."),
    ("There is a new … whose … is ….", "There is a new ${1:dragon} whose ${2:age} is ${3:0}.", "any",
     "Make a thing while the program runs."),
    ("Remove ….", "Remove ${1:the task}.", "any", "Take a thing out of the world."),
    ("Now … is ….", "Now ${1:the task} is ${2:done}.", "any", "Set a stored adjective."),
    ("Ask \"…\" and let the … (…) be the reply.",
     'Ask "${1:Age?}" and let the ${2:age} (${3:number}) be the reply.', "any", "Ask a question."),
    ("Write … to the file \"…\"", 'Write ${1:the total} to the file "${2:notes.txt}".', "any", "Write a file."),
    ("Add … to the file \"…\"", 'Add ${1:the total} to the file "${2:notes.txt}".', "any", "Add a line to a file."),
    ("For example, ….", "For example, ${1:the total is 0}.", "any", "A test that runs with the program."),
    ("A … has a … (…).", "A ${1:dragon} has ${2:an age} (${3:number}).", "top", "Describe a kind."),
    ("A … is … when ….", "A ${1:dragon} is ${2:ancient} when ${3:its age is at least 500}.", "top",
     "Define an adjective."),
    ("A … can be ….", "A ${1:task} can be ${2:done}.", "top", "An adjective the program sets with Now."),
    ("A … is one of …, … or ….", "A ${1:mood} is one of ${2:sleepy}, ${3:grumpy} or ${4:very cross}.", "top",
     "A fixed set of choices, used as a type."),
    ("Keep each …'s … as ….", "Keep each ${1:card}'s ${2:line} as ${3:its wording}.", "top",
     "Keep a property of every thing of a kind in step with a value."),
    ("Keep …'s … as ….", "Keep ${1:Milk}'s ${2:line} as ${3:the heading}.", "top",
     "Keep a property of one thing in step with a value."),
    ("Keep each … … when ….", "Keep each ${1:card} ${2:open} when ${3:the card is not done}.", "top",
     "Keep a stored adjective in step with a condition."),
    ("The … of a … is ….", "The ${1:tax} of a ${2:dragon} is ${3:10% of its hoard}.", "top",
     "Define a worked-out property."),
    ("A …'s … is never ….", "A ${1:knight}'s ${2:purse} is never ${3:less than \\$0}.", "top", "State a rule."),
    ("A … (plural …) has a … (…).", "A ${1:person} (plural ${2:people}) has ${3:an age} (${4:number}).", "top",
     "Describe a kind whose plural is not formed by rule."),
    ("To …:", "To ${1:send} a ${2:knight} ${3:against} a ${4:dragon}:\n  $0", "top", "Teach a verb."),
    ("To work out the … (…) of a …:", "To work out the ${1:bounty} (${2:money}) ${3:of} a ${4:dragon}:\n  "
     "The answer is ${5:\\$0}.", "top", "Define a value that is worked out."),
    ("Whenever … becomes …:", "Whenever a ${1:knight} becomes ${2:broke}:\n  $0", "top", "React to a change."),
    ("Whenever everything has settled:", "Whenever everything has settled:\n  $0", "top",
     "React once at the end of each turn in which something changed."),
    ("Use the … library.", "Use the ${1:page} library.", "top", "Use a library."),
    ("Use the … chapter.", "Use the ${1:calendar} chapter.", "top", "Use another file beside this one."),
    ("Use the … chapter of the … book.", "Use the ${1:calendar} chapter of the ${2:almanac} book.", "top",
     "Use a file of a folder beside this one."),
    ("This chapter shares only ….", "This chapter shares only ${1:a name}.", "top",
     "Say which words other files may use. It is the first sentence of its file."),
    ("The answer is ….", "The answer is ${1:0}.", "block", "Inside To work out: give the value."),
    ("Stop.", "Stop.", "block", "Leave the verb."),
    ("Stop repeating.", "Stop repeating.", "block", "Leave the loop."),
    ("Skip this round.", "Skip this ${1:round}.", "block", "Go on with the loop's next turn."),
    ("End the program.", "End the program.", "any", "End the program."),
]
_PLACEHOLDER = re.compile(r"\$\{\d+:((?:[^}\\]|\\.)*)\}|\$\{\d+\}|\$\d+")

# Completion item kinds and symbol kinds of the protocol, for each sort of name.
ITEM_KIND = {"kind": 7, "plural": 7, "property": 10, "adjective": 20, "thing": 21, "verb": 2, "value": 3,
             "variable": 6, "role": 6, "loop": 6, "choices": 13, "choice": 20}
SNIPPET = 15
SYMBOL_KIND = {"kind": 5, "property": 7, "adjective": 17, "thing": 19, "verb": 6, "value": 12, "variable": 13,
               "reaction": 24, "choices": 10, "choice": 22}


def heading(category):
    """The heading word of a category of mistake, as the compiler's own marks have it ("Kinds of value")."""
    try:
        headings = getattr(importlib.import_module("englishscript"), "CATEGORY_HEADINGS", None)
        if isinstance(headings, dict) and isinstance(headings.get(category), str):
            return headings[category]
    except Exception:  # noqa: BLE001 - the category's own word will do
        pass
    return str(category).capitalize() if category else "Problem"


def plain_snippet(snippet):
    """A snippet as plain text, for an editor that can't fill one in."""
    return _PLACEHOLDER.sub(lambda m: m.group(1) or "", snippet).replace("\\$", "$")


def rule_line(rule):
    """'The rule: a sentence ends with a period.', as the compiler's own messages put it."""
    first = rule.split(" ", 1)[0]
    if not (rule.startswith('"') or first in ("EnglishScript", "I") or first[1:2].isupper()):
        rule = rule[:1].lower() + rule[1:]
    return f"The rule: {rule}"


def section_link(see):
    """Where the reference teaches a section such as "4.1", or None."""
    if isinstance(see, str) and re.fullmatch(r"\d+(\.\d+)*", see):
        return f"{REFERENCE}#s{see.replace('.', '-')}"
    return None


def escape_markdown(text):
    return re.sub(r"([\\`*_{}\[\]<>#|~])", r"\\\1", text)


def describe(name):
    """'a thing (dragon)', 'a property of dragon (number)', ..."""
    said = renaming.WHAT.get(name.what, name.what)
    if name.what == "property":
        said = ("a worked-out property" if name.worked else "a property") + (f" of {name.owner}" if name.owner else "")
    elif name.what == "adjective" and name.owner:
        said += f" of {name.owner}"
    elif name.what == "thing" and name.owner:
        said += f" ({name.owner})"
    elif name.what == "plural" and name.owner:
        said = f"the plural of the kind {name.owner}"
    elif name.what == "choice" and name.owner:
        said = f"a choice of {name.owner}"
    elif name.what == "variable" and name.constant:
        said = "a variable that never changes"
    if name.type:
        said += f" ({name.type})"
    return said


def as_dict(problem):
    """A linter's Problem as a dict, whatever shape it has today."""
    maker = getattr(problem, "as_dict", None)
    if callable(maker):
        return dict(maker())
    if isinstance(problem, dict):
        return dict(problem)
    return dict(getattr(problem, "__dict__", {}))


# ------------------------------------------------------------------ the server

class Server:
    """The language server, without the pipes: `handle` takes a message and gives the messages to send."""

    def __init__(self, log=None):
        self.log = log or (lambda text: print(text, file=sys.stderr, flush=True))
        self.documents = {}
        self.client = {}  # the editor's capabilities
        self.initialized = False
        self.shut_down = False
        self.exit_code = None  # set by "exit": the loop then stops
        self.outbox = []
        self.requests = {
            "initialize": self.initialize,
            "shutdown": self.shutdown,
            "textDocument/codeAction": self.code_action,
            "textDocument/hover": self.hover,
            "textDocument/documentSymbol": self.document_symbol,
            "textDocument/definition": self.definition,
            "textDocument/completion": self.completion,
            "textDocument/prepareRename": self.prepare_rename,
            "textDocument/rename": self.rename,
        }
        self.notifications = {
            "initialized": lambda params: None,
            "exit": self.exit,
            "textDocument/didOpen": self.did_open,
            "textDocument/didChange": self.did_change,
            "textDocument/didSave": self.did_save,
            "textDocument/didClose": self.did_close,
        }

    # Messages ---------------------------------------------------------------

    def handle(self, message):
        """Deal with one message (a dict). Returns the messages to send back, in order. Never raises."""
        self.outbox = []
        try:
            self._handle(message)
        except Exception:  # noqa: BLE001 - whatever happens, the server carries on
            self.log("englishscript server: " + traceback.format_exc())
        out, self.outbox = self.outbox, []
        return out

    def _handle(self, message):
        if not isinstance(message, dict):
            self._error(None, INVALID_REQUEST, "A message is a JSON object.")
            return
        method, ident = message.get("method"), message.get("id")
        is_request = "id" in message
        if not isinstance(method, str):
            if "result" not in message and "error" not in message:  # not an answer to anything either
                self._error(ident, INVALID_REQUEST, "The message has no method.")
            return
        params = message.get("params")
        if params is None:
            params = {}
        if is_request:
            if self.shut_down:
                self._error(ident, INVALID_REQUEST, "The server has been shut down.")
            elif not self.initialized and method != "initialize":
                self._error(ident, NOT_INITIALIZED, "The server has not been initialized.")
            elif method not in self.requests:
                self._error(ident, METHOD_NOT_FOUND, f"The server does not answer {method}.")
            else:
                try:
                    result = self.requests[method](params)
                except Refused as refused:
                    self._error(ident, refused.code, str(refused))
                except Exception as error:  # noqa: BLE001 - one bad request must not end the session
                    self.log(f"englishscript server: {method} failed:\n" + traceback.format_exc())
                    self._error(ident, INTERNAL_ERROR, f"{type(error).__name__}: {error}")
                else:
                    self.outbox.append({"jsonrpc": "2.0", "id": ident, "result": result})
            return
        if method == "exit" or (method in self.notifications and self.initialized and not self.shut_down):
            try:
                self.notifications[method](params)
            except Exception:  # noqa: BLE001
                self.log(f"englishscript server: {method} failed:\n" + traceback.format_exc())

    def _error(self, ident, code, message):
        self.outbox.append({"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}})

    def notify(self, method, params):
        self.outbox.append({"jsonrpc": "2.0", "method": method, "params": params})

    def supports(self, *path):
        """Something the editor said about itself in `initialize`, or None."""
        found = self.client
        for key in path:
            if not isinstance(found, dict):
                return None
            found = found.get(key)
        return found

    # The start and the end --------------------------------------------------

    def initialize(self, params):
        self.client = params.get("capabilities") or {}
        self.initialized = True
        info = {"name": "englishscript"}
        version = getattr(sys.modules.get("englishscript"), "__version__", None)
        if isinstance(version, str):
            info["version"] = version
        return {
            "capabilities": {
                "positionEncoding": "utf-16",
                "textDocumentSync": {"openClose": True, "change": 1, "save": {"includeText": False}},
                "codeActionProvider": {"codeActionKinds": ["quickfix", "source.fixAll.englishscript"]},
                "hoverProvider": True,
                "completionProvider": {},
                "documentSymbolProvider": True,
                "definitionProvider": True,
                "renameProvider": {"prepareProvider": True},
            },
            "serverInfo": info,
        }

    def shutdown(self, params):
        self.shut_down = True
        return None

    def exit(self, params):
        self.exit_code = 0 if self.shut_down else 1

    # Documents --------------------------------------------------------------

    def document(self, params):
        """The open document a request is about, or None."""
        holder = params.get("textDocument") if isinstance(params, dict) else None
        return self.documents.get(holder.get("uri")) if isinstance(holder, dict) else None

    def did_open(self, params):
        item = params["textDocument"]
        doc = Document(item["uri"], str(item.get("text", "")), item.get("version"))
        self.documents[doc.uri] = doc
        self.publish(doc)
        self.others_changed(doc, publish=False)

    def others_changed(self, doc, publish=True):
        """A document was opened, changed, saved or closed. The others may use it as a chapter,
        and the compiler reads an open chapter from the editor: forget what was worked out for
        them, and tell the editor again about those that use chapters."""
        for other in list(self.documents.values()):
            if other is doc:
                continue
            uses_chapters = any(use.what == "chapter" for use in self.reading(other).uses)
            other.problems = other.notes = other.program = None
            if publish and uses_chapters:
                self.publish(other)

    def did_change(self, params):
        doc = self.document(params)
        if doc is None:
            return
        text = doc.text
        for change in params.get("contentChanges") or []:
            if isinstance(change.get("range"), dict):  # a part of the text, though we asked for all of it
                span = change["range"]
                start, end = text.offset(span["start"]), text.offset(span["end"])
                text = Text(text.text[:start] + str(change.get("text", "")) + text.text[end:])
            else:
                text = Text(str(change.get("text", "")))
        fresh = Document(doc.uri, "", params["textDocument"].get("version", doc.version))
        fresh.text = text
        self.documents[doc.uri] = fresh
        self.publish(fresh)
        self.others_changed(fresh)

    def did_save(self, params):
        doc = self.document(params)
        if doc is not None and isinstance(params.get("text"), str) and params["text"] != doc.text.text:
            doc = Document(doc.uri, params["text"], doc.version)
            self.documents[doc.uri] = doc
        # A chapter that is not open is read from the disk, so a save may change what any file's problems are.
        for other in list(self.documents.values()):
            other.problems = other.notes = other.program = None
            self.publish(other)

    def did_close(self, params):
        doc = self.document(params)
        if doc is not None:
            del self.documents[doc.uri]
            self.notify("textDocument/publishDiagnostics", {"uri": doc.uri, "diagnostics": []})
            self.others_changed(None)

    # What the compiler says -------------------------------------------------

    def open_text(self, path):
        """The text of a file that is open in the editor, or None: what the compiler's `read=` asks for."""
        for other in self.documents.values():
            if other.path is not None and same_file(other.path, path):
                return other.text.text
        return None

    def read_file(self, path):
        """A chapter's text: what is open in the editor, or else what is on the disk."""
        text = self.open_text(path)
        if text is not None:
            return text
        try:
            return Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return None

    def check(self, doc):
        """Ask the linter for the document's problems and, where it gives them, the notes on how
        each good sentence was read. A chapter that is open in the editor is read from there."""
        doc.problems, doc.notes = [], None
        try:
            lint = importlib.import_module("englishscript").lint
            source = doc.text.text
            try:
                found = lint(source, doc.folder, doc.name, notes=True, read=self.open_text)
            except TypeError:  # a linter without `notes` or `read`
                found = lint(source, doc.folder, doc.name)
            if isinstance(found, tuple) and len(found) == 2:
                found, notes = found
                doc.notes = {}
                for entry in notes or []:
                    doc.notes.setdefault(entry[0], []).append(str(entry[1]))
            doc.problems = [as_dict(problem) for problem in found]
        except Exception as error:  # noqa: BLE001 - the compiler may be half-written; say so and carry on
            self.log("englishscript server: the linter failed:\n" + traceback.format_exc())
            doc.notes = False
            doc.problems = [{"line": 1, "col": None, "width": 1, "kind": "warning", "category": None,
                             "message": f"The EnglishScript compiler could not check this file "
                                        f"({type(error).__name__}: {error}).",
                             "hint": None, "rule": None, "see": None, "fix": None, "file": None}]

    def problems(self, doc):
        """The linter's problems for a document, as dicts, in the linter's order."""
        if doc.problems is None:
            self.check(doc)
        return doc.problems

    def notes(self, doc):
        """{line number, from 1: how its sentence was read}, or None if that can't be had."""
        if doc.problems is None:
            self.check(doc)
        if doc.notes is None:  # the linter gave no notes: the compiler has them, if the whole file compiles
            doc.notes = False
            try:
                compile_source = importlib.import_module("englishscript").compile_source
                try:
                    program = compile_source(doc.text.text, doc.folder, doc.name, read=self.open_text)
                except TypeError:
                    program = compile_source(doc.text.text, doc.folder, doc.name)
                found = {}
                for entry in getattr(program, "notes", None) or []:
                    found.setdefault(entry[0], []).append(str(entry[1]))
                doc.notes = found
            except Exception:  # noqa: BLE001 - an EnglishError, or a compiler that is being rewritten
                pass
        return doc.notes or None

    def program(self, doc):
        """(the Reading of the document, [(the Use, what to call it, its path, its Reading, its text)])
        for the document and the chapters and libraries it uses: rename.read_program, which takes
        the compiler's table of names where there is one. A library has no path and no text."""
        if doc.program is None:
            texts = {}

            def read(path):
                texts[str(path)] = self.read_file(path)
                return texts[str(path)]

            reading, others = renaming.read_program(doc.text.text, doc.folder, doc.name, read)
            doc.program = (reading, [(use, label, path, other, texts.get(str(path)))
                                     for use, label, path, other in others])
        return doc.program

    def reading(self, doc):
        return self.program(doc)[0]

    def neighbours(self, doc):
        return self.program(doc)[1]

    # Diagnostics ------------------------------------------------------------

    def publish(self, doc):
        params = {"uri": doc.uri, "diagnostics": [d for d, _ in self.diagnostics(doc)]}
        if isinstance(doc.version, int):
            params["version"] = doc.version
        self.notify("textDocument/publishDiagnostics", params)

    def diagnostics(self, doc):
        """[(the diagnostic, the problem it came from)]"""
        return [(self.diagnostic(doc, problem), problem) for problem in self.problems(doc)]

    def diagnostic(self, doc, problem):
        text = doc.text
        line, col, width = problem.get("line"), problem.get("col"), problem.get("width")
        number = max(0, min((line if isinstance(line, int) else 1) - 1, len(text.lines) - 1))
        message = str(problem.get("message") or "This sentence can't be read.")
        if problem.get("file"):
            # A line of a chapter: there is no such place in this file. Point at the sentence that uses it.
            message = f"In {problem['file']}, line {line}: {message}"
            stem = Path(str(problem["file"])).stem.replace("_", " ").lower()
            uses = [u.line for u in self.reading(doc).uses if u.what == "chapter" and " ".join(u.words) == stem]
            number, col = (uses[0] if uses else 0), None
        body = text.line(number)
        if isinstance(col, int) and 0 <= col <= len(body):
            start, end = col, min(len(body), col + max(1, width if isinstance(width, int) else 1))
            if end <= start:  # at the very end of the line, as for a missing period: mark its last character
                start, end = max(0, len(body) - 1), len(body)
        else:
            start, end = 0, len(body)  # no column: the whole line
        if problem.get("hint"):
            message += "\n" + str(problem["hint"])
        if problem.get("rule"):
            message += "\n" + rule_line(str(problem["rule"]))
        found = {
            "range": text.range(number, start, end),
            "severity": 2 if problem.get("kind") == "warning" else 1,
            "source": "englishscript",
            "message": message,
        }
        link = section_link(problem.get("see"))
        if isinstance(problem.get("category"), str):
            found["code"] = problem["category"]
        elif link:
            found["code"] = f"section {problem['see']}"
        if link:
            found["codeDescription"] = {"href": link}
        return found

    # Quick fixes ------------------------------------------------------------

    def fix_edit(self, doc, fix):
        """The edit that writes a correction's whole line, or None if it can't be placed."""
        if not isinstance(fix, dict) or not isinstance(fix.get("line"), int) or not isinstance(fix.get("text"), str):
            return None
        number = fix["line"] - 1
        if not 0 <= number < len(doc.text.lines):
            return None
        return {"range": doc.text.range(number, 0, len(doc.text.lines[number])), "newText": fix["text"]}

    def code_action(self, params):
        doc = self.document(params)
        if doc is None:
            return []
        asked = params.get("range") or {}
        first = (asked.get("start") or {}).get("line", 0)
        last = (asked.get("end") or {}).get("line", first)
        only = (params.get("context") or {}).get("only")

        def wanted(kind):
            return not only or any(kind == o or kind.startswith(o + ".") for o in only)

        fixable = [(d, p, self.fix_edit(doc, p.get("fix"))) for d, p in self.diagnostics(doc)]
        fixable = [(d, p, edit) for d, p, edit in fixable if edit is not None]
        actions = []
        if wanted("quickfix"):
            for diagnostic, problem, edit in fixable:
                if diagnostic["range"]["start"]["line"] <= last and diagnostic["range"]["end"]["line"] >= first:
                    actions.append({
                        "title": "Mend: " + problem["fix"]["text"].strip(),
                        "kind": "quickfix",
                        "diagnostics": [diagnostic],
                        "isPreferred": True,
                        "edit": {"changes": {doc.uri: [edit]}},
                    })
        if len(fixable) >= 2:
            lines, edits = set(), []
            for _, _, edit in fixable:  # one correction for each line; the rest are offered when this is done
                if edit["range"]["start"]["line"] not in lines:
                    lines.add(edit["range"]["start"]["line"])
                    edits.append(edit)
            kind = next((k for k in ("quickfix", "source.fixAll.englishscript") if wanted(k)), None)
            if kind is not None:
                actions.append({
                    "title": "Mend all that can be mended",
                    "kind": kind,
                    "diagnostics": [d for d, _, _ in fixable],
                    "edit": {"changes": {doc.uri: edits}},
                })
        return actions

    # Hover ------------------------------------------------------------------

    def hover(self, params):
        doc = self.document(params)
        if doc is None:
            return None
        offset = doc.text.offset(params["position"])
        number, col = doc.text.where(offset)
        formats = self.supports("textDocument", "hover", "contentFormat")
        markdown = not isinstance(formats, list) or "markdown" in formats
        position = doc.text.position(offset)

        def holds(span):
            start, end = span["start"], span["end"]
            return (start["line"], start["character"]) <= (position["line"], position["character"]) <= (
                end["line"], end["character"])

        here = [(d, p) for d, p in self.diagnostics(doc)
                if d["range"]["start"]["line"] <= position["line"] <= d["range"]["end"]["line"]]
        here.sort(key=lambda pair: not holds(pair[0]["range"]))
        if here:
            diagnostic, problem = here[0]
            return {"contents": self._contents(self.problem_text(problem, markdown), markdown),
                    "range": diagnostic["range"]}
        parts = []
        notes = (self.notes(doc) or {}).get(number + 1)
        if notes:
            esc = escape_markdown if markdown else (lambda text: text)
            parts.append("How this sentence was read:\n\n" + "\n".join(f"- {esc(note)}" for note in notes))
        found = self.name_at(doc, number, col)
        if found is not None:
            for uri, name, there, label in self.definitions_of(doc, found, number)[:3]:
                where = f"line {name.line + 1}" if label is None else f"{label}, line {name.line + 1}"
                title = f"**{escape_markdown(name.text)}**" if markdown else name.text
                text = f"{title}: {describe(name)}, {where}"
                sentence = there.line(name.line).strip() if there is not None else ""
                if sentence and not (uri == doc.uri and name.line == number):
                    text += f"\n\n```\n{sentence}\n```" if markdown else f"\n    {sentence}"
                parts.append(text)
        if not parts:
            return None
        return {"contents": self._contents("\n\n".join(parts), markdown)}

    @staticmethod
    def _contents(text, markdown):
        return {"kind": "markdown" if markdown else "plaintext", "value": text}

    @staticmethod
    def problem_text(problem, markdown):
        """A problem as the hover shows it: what is wrong, how to mend it, and the rule."""
        esc = escape_markdown if markdown else (lambda text: text)
        head = heading(problem.get("category"))
        if problem.get("kind") == "warning":
            head += ", a suggestion"
        parts = [f"**{esc(head)}**" if markdown else head, esc(str(problem.get("message") or ""))]
        if problem.get("hint"):
            parts.append(("  \n" if markdown else "\n").join(esc(h) for h in str(problem["hint"]).split("\n")))
        fix = problem.get("fix")
        if isinstance(fix, dict) and isinstance(fix.get("text"), str):
            parts.append(f"Write:\n\n```\n{fix['text'].strip()}\n```" if markdown else f"Write: {fix['text'].strip()}")
        if problem.get("rule"):
            rule = esc(rule_line(str(problem["rule"])))
            link, see = section_link(problem.get("see")), problem.get("see")
            if link:
                rule += f" ([section {see}]({link}))" if markdown else f" (See section {see}: {link})"
            parts.append(rule)
        return "\n\n".join(part for part in parts if part)

    # Names ------------------------------------------------------------------

    def vocabulary(self, doc):
        """Every name that may be written in the document:
        {words: [(uri or None, the Name, its file's Text or None, None or what its chapter or library is called)]}.

        The names are the compiler's own table (englishscript.names) where it gives one, and
        otherwise a reading of the sentence forms in the text: see rename.read_program."""
        found = {}
        reading = self.reading(doc)
        for name in reading.names:
            found.setdefault(name.words, []).append((doc.uri, name, doc.text, None))
        for name in reading.names:
            if name.what == "kind" and name.words[0] not in reading.plurals:  # a stated plural is a name already
                found.setdefault((renaming.pluralize(name.text).lower(),), []).append((doc.uri, name, doc.text, None))
        for _, label, path, other, text in self.neighbours(doc):
            uri = self.uri_of(doc, path) if path is not None and text is not None else None
            there = Text(text) if text is not None else None
            for words, name in other.shared().items():
                found.setdefault(words, []).append((uri, name, there, label))
        return found

    @staticmethod
    def uri_of(doc, path):
        """The URI of a chapter's file, written the way the editor wrote the document's own."""
        if doc.path is not None:
            return uri_beside(doc.uri, doc.path, path)
        return Path(os.path.abspath(path)).as_uri()

    def name_at(self, doc, number, col):
        """The rename.Occurrence of the known name written at a place, or None."""
        vocabulary = self.vocabulary(doc)
        for found in renaming.occurrences(self.reading(doc), vocabulary, vocabulary, lines=[number]):
            if found.start <= col <= found.end:
                return found
        return None

    def definitions_of(self, doc, found, number):
        """Where the name of an occurrence is defined, the likeliest first: entries of `vocabulary`.
        A name of a block (a role, a loop's name, a variable made inside) is looked for first."""
        every = self.vocabulary(doc).get(found.words, [])
        local = [e for e in every if e[0] == doc.uri and not e[1].top
                 and e[1].scope and e[1].scope[0] <= number <= e[1].scope[1]]
        if local:
            before = [e for e in local if e[1].line <= number]
            return [max(before or local, key=lambda e: e[1].line)]
        top = [e for e in every if e[1].top]
        chosen = [e for e in top if (e[1].what == "verb") == found.verb] or top
        return [e for e in chosen if e[0] == doc.uri] or chosen

    def definition(self, params):
        doc = self.document(params)
        if doc is None:
            return None
        number, col = doc.text.where(doc.text.offset(params["position"]))
        found = self.name_at(doc, number, col)
        if found is None:
            # On "Use the calendar chapter of the almanac book.": the chapter's file.
            for use, _, path, _, text in self.neighbours(doc):
                if use.line == number and path is not None and text is not None:
                    return {"uri": self.uri_of(doc, path), "range": Text(text).range(0, 0, 0)}
            return None
        places = [{"uri": uri, "range": text.range(name.line, name.start, name.end)}
                  for uri, name, text, _ in self.definitions_of(doc, found, number)
                  if uri is not None and text is not None]
        if not places:
            return None
        return places[0] if len(places) == 1 else places

    # The outline ------------------------------------------------------------

    def document_symbol(self, params):
        """The kinds, sets of choices, things, adjectives, verbs, worked-out values, top-level
        variables and reactions of the file, each at its defining sentence.

        They are the compiler's own table of names (englishscript.names) where it gives one.
        Where it does not, they are found by reading the sentence forms ("A dragon has ...",
        "There is a dragon called Smaug ...", "To send a knight against a dragon:", ...) in
        rename.read_names: that is a reading of the text, not of the compiler's tables, and it
        also supplies "Whenever everything has settled:", which the table leaves out."""
        doc = self.document(params)
        if doc is None:
            return []
        reading, text = self.reading(doc), doc.text
        symbols, parents = [], {}  # parents: a kind or a set of choices, by its word

        def symbol(label, what, detail, number, start, end):
            line = reading.lines[number]
            first = line.code[0].start if line.code else 0
            last = reading.lines[line.last]
            return {
                "name": label, "kind": SYMBOL_KIND[what], "detail": detail,
                "range": text.span(number, first, last.number, len(last.raw.rstrip())),
                "selectionRange": text.range(number, start, end),
            }

        for name in reading.names:
            if not name.top or name.what == "plural":
                continue
            what = "value" if name.what == "property" and name.worked else name.what
            found = symbol(name.text, what, describe(name), name.line, name.start, name.end)
            if name.what == "variable" and name.constant:
                found["kind"] = 14
            owner = (str(name.owner).lower(), name.what == "choice")
            if (name.what == "choice" or (name.what == "property" and not name.worked)) and owner in parents:
                found["range"] = found["selectionRange"]
                parents[owner].setdefault("children", []).append(found)
                continue
            if name.what in ("kind", "choices"):
                parents[(name.words[0], name.what == "choices")] = found
            symbols.append((name.line, name.start, found))
        for number, sentence in reading.reactions:
            line = reading.lines[number]
            symbols.append((number, 0, symbol(sentence, "reaction", "a reaction", number, line.code[0].start,
                                              len(line.raw.rstrip()))))
        return [found for _, _, found in sorted(symbols, key=lambda entry: entry[:2])]

    # Suggestions ------------------------------------------------------------

    @staticmethod
    def context(prefix):
        """Where the cursor is, given the line up to it: "code", "comment", "text" (in quotes) or "fill"."""
        text = prefix.translate(renaming._STRAIGHT)
        state, i = "code", 0
        while i < len(text):
            ch = text[i]
            if state == "code":
                if ch == "#":
                    return "comment"
                if ch == '"':
                    state = "text"
            elif state == "text":
                if text[i:i + 2] in ('""', "{{", "}}"):
                    i += 2
                    continue
                if ch == '"':
                    state = "code"
                elif ch == "{":
                    state = "fill"
            elif ch == "}":
                state = "text"
            elif ch == '"':
                state = "code"
            i += 1
        return state

    def completion(self, params):
        doc = self.document(params)
        if doc is None:
            return []
        offset = doc.text.offset(params["position"])
        number, col = doc.text.where(offset)
        prefix = doc.text.line(number)[:col]
        context = self.context(prefix)
        if context in ("comment", "text"):
            return []
        written = prefix.lstrip()
        if context == "code" and re.fullmatch(r"(?:[^\W\d_]\w*)?", written):  # nothing yet, or one word begun
            return self.sentence_starts(doc, number, col, len(prefix) - len(written))
        return self.name_items(doc, number, prefix, context)

    def sentence_starts(self, doc, number, col, indent):
        """The sentence forms, and the document's verbs, for the start of a line."""
        snippets = self.supports("textDocument", "completion", "completionItem", "snippetSupport") is True
        span = doc.text.range(number, indent, col)
        items = []

        def add(label, snippet, kind, detail, order, word=None):
            text = snippet if snippets else plain_snippet(snippet)
            items.append({
                "label": label, "kind": kind, "detail": detail, "sortText": f"{order}{len(items):03}",
                "filterText": word or plain_snippet(snippet), "insertTextFormat": 2 if snippets else 1,
                "textEdit": {"range": span, "newText": text},
            })

        for label, snippet, where, detail in OPENERS:
            if (where == "top" and indent) or (where == "block" and not indent):
                continue
            add(label, snippet, SNIPPET, detail, 1)
        for words, entries in self.vocabulary(doc).items():
            for uri, name, _, _ in entries:
                if name.what != "verb" or (uri == doc.uri and name.line > number):
                    continue
                verb = name.text[:1].upper() + name.text[1:]
                parts, plain = [verb], [verb]
                for k, (preposition, role) in enumerate(name.pattern, 1):
                    parts.append((f"{preposition} " if preposition else "") + f"${{{k}:{role}}}")
                    plain.append((f"{preposition} " if preposition else "") + "…")
                add(" ".join(plain) + ".", " ".join(parts) + ".", ITEM_KIND["verb"], describe(name), 0, verb)
        return items

    def name_items(self, doc, number, prefix, context):
        """The names that may be written here: after a possessive the properties, elsewhere the rest."""
        tail = prefix[prefix.rfind("{") + 1:] if context == "fill" else prefix
        toks = renaming.scan(tail)
        if toks and toks[-1].kind == "word" and toks[-1].end == len(tail):
            toks = toks[:-1]  # the word being written
        last = toks[-1] if toks else None
        before = toks[-2] if len(toks) > 1 else None
        possessive = last is not None and (
            last.kind == "pos" or last.is_word("its", "their", "whose")
            or (last.is_word("a", "an", "no") and before is not None and before.is_word("has")))
        items, seen = [], set()

        def add(label, what, detail, order):
            if label.lower() not in seen:
                seen.add(label.lower())
                items.append({"label": label, "kind": ITEM_KIND.get(what, 6), "detail": detail,
                              "sortText": f"{order}{label.lower()}"})

        for words, entries in self.vocabulary(doc).items():
            for uri, name, _, _ in entries:
                mine = uri == doc.uri
                plural = name.words != words  # the plural, formed by rule, of the kind `name`
                label = renaming.pluralize(name.text) if plural else name.text
                group = plural or name.what == "plural"  # ... or a plural stated in brackets after its kind
                if possessive:
                    if name.what == "property":
                        add(label, "property", describe(name), 1)
                    elif group and (last.kind == "pos" or last.is_word("its", "their")):
                        add(label, "plural", "a group: the plural of a kind", 2)  # "its treasures"
                    continue
                if name.what == "verb":
                    continue  # a verb stands first in its sentence
                if mine and not name.top:
                    if name.scope and name.scope[0] <= number <= name.scope[1] and name.line <= number:
                        add(label, name.what, describe(name), 1)
                elif mine and name.line > number:
                    continue  # defined further down: it can't be said yet
                elif plural:
                    add(label, "plural", f"the plural of the kind {name.text}", 2)
                else:
                    add(label, name.what, describe(name), {"property": 4, "adjective": 3}.get(name.what, 2))
        if possessive:
            add("name", "property", "every thing has a name (text)", 1)
        return items

    # Renaming ---------------------------------------------------------------

    def rename_target(self, doc, params):
        """(the occurrence under the cursor, the name to rename as written there, its definitions here), or None.

        On the plural of a kind ("dragons"), the name is the kind's ("dragon")."""
        number, col = doc.text.where(doc.text.offset(params["position"]))
        found = self.name_at(doc, number, col)
        if found is None:
            return None
        here = [entry[1] for entry in self.vocabulary(doc).get(found.words, []) if entry[0] == doc.uri]
        if not here:
            return None
        local = [n for n in here if not n.top and n.scope and n.scope[0] <= number <= n.scope[1]]
        chosen = local or [n for n in here if n.top] or here
        return found, number, chosen

    def prepare_rename(self, params):
        doc = self.document(params)
        target = self.rename_target(doc, params) if doc is not None else None
        if target is None:
            return None
        found, _, chosen = target
        placeholder = found.text if chosen[0].words == found.words else chosen[0].text
        return {"range": doc.text.range(found.line, found.start, found.end), "placeholder": placeholder}

    def rename(self, params):
        doc = self.document(params)
        if doc is None:
            raise Refused(REQUEST_FAILED, "That file is not open.")
        target = self.rename_target(doc, params)
        if target is None:
            raise Refused(REQUEST_FAILED, "There is no name defined in this file at that place.")
        found, number, chosen = target
        senses = {"verb" if n.what == "verb" else "name" for n in chosen}
        only = ("verb" if found.verb else "name") if len(senses) > 1 else None
        within = None
        if all(not n.top for n in chosen):  # a role, a loop's name or a variable of a block: only that block
            root = self.reading(doc).root(number)
            within = (root, self.reading(doc).lines[root].last)
        try:
            edits = renaming.plan(doc.text.text, chosen[0].text, str(params.get("newName", "")), doc.folder,
                                  doc.name, only=only, within=within, read=self.read_file)
        except renaming.RenameRefused as refused:
            raise Refused(REQUEST_FAILED, str(refused)) from None
        changes = [{"range": doc.text.range(e.line, e.start, e.end), "newText": e.text} for e in edits]
        return {"changes": {doc.uri: changes}}


# ------------------------------------------------------------------ the pipes

class BadFrame(Exception):
    """What arrived was not a message behind a Content-Length header."""


def read_message(stream):
    """The body of the next message on a binary stream, as bytes; None when the stream has ended."""
    length = None
    seen = False
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            if not seen:
                continue  # blank lines between messages
            break
        seen = True
        name, _, value = line.decode("ascii", "replace").partition(":")
        if name.strip().lower() == "content-length":
            try:
                length = int(value.strip())
            except ValueError:
                length = -1
    if length is None or length < 0:
        raise BadFrame("a message came without a usable Content-Length header")
    body = b""
    while len(body) < length:
        chunk = stream.read(length - len(body))
        if not chunk:
            return None
        body += chunk
    return body


def write_message(stream, message):
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stream.write(b"Content-Length: %d\r\n\r\n" % len(body) + body)
    stream.flush()


def serve(server, reader, writer):
    """Read messages from `reader` and answer on `writer` until "exit" or the end of the input.
    Returns the exit status: 0 after a shutdown and an exit, 1 otherwise."""
    while server.exit_code is None:
        try:
            body = read_message(reader)
        except BadFrame as error:
            server.log(f"englishscript server: {error}")
            continue
        if body is None:
            break
        try:
            message = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            server.log(f"englishscript server: a message could not be read: {error}")
            write_message(writer, {"jsonrpc": "2.0", "id": None,
                                   "error": {"code": PARSE_ERROR, "message": f"The message is not JSON: {error}"}})
            continue
        for part in message if isinstance(message, list) else [message]:
            for answer in server.handle(part):
                write_message(writer, answer)
    return server.exit_code if server.exit_code is not None else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print("python -m englishscript.server\n\n"
              "A language server for EnglishScript. An editor starts it and speaks the Language Server\n"
              "Protocol to it over standard input and output. See docs/EDITORS.md.")
        return 0
    return serve(Server(), sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    sys.exit(main())

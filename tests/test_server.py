"""The language server (englishscript/server.py).

    python -m unittest tests.test_server

Most tests drive the Server class with dicts, as an editor's messages would
arrive once unframed. One starts `python -m englishscript.server` and talks
to it over pipes. The compiler's wording changes, so the tests look at the
shape of what comes back (ranges, kinds, that a correction mends), not at
what any message says.
"""
import io
import json
import queue
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import englishscript  # noqa: E402
from englishscript import rename as renaming  # noqa: E402
from englishscript import server as serving  # noqa: E402
from englishscript.server import Server, Text  # noqa: E402

EXAMPLES = ROOT / "examples"
SNIPPETS = {"textDocument": {"completion": {"completionItem": {"snippetSupport": True}}}}
PLAIN_HOVER = {"textDocument": {"hover": {"contentFormat": ["plaintext"]}}}

WORLD = """\
A dragon has an age (number).
A dragon is ancient when its age is at least 500.
There is a dragon called Smaug whose age is 771.
There is a dragon called Norbert whose age is 1.
To greet a dragon:
  Let the greeting be "Hello".
  Say "{the greeting}, {the dragon}."
Let the total be 0.
A dragon can be asleep.
Whenever a dragon becomes asleep:
  Say "{the dragon} sleeps."
Greet Smaug.
Add Smaug's age to the total.
Say the total.
"""


def utf16(text):
    return len(text.encode("utf-16-le")) // 2


def cut(text, span):
    """What a range covers, in a text."""
    held = Text(text)
    return text[held.offset(span["start"]):held.offset(span["end"])]


def apply(text, edits):
    """A text with the protocol's edits made."""
    held = Text(text)
    spans = sorted(((held.offset(e["range"]["start"]), held.offset(e["range"]["end"]), e["newText"]) for e in edits),
                   reverse=True)
    for start, end, new in spans:
        text = text[:start] + new + text[end:]
    return text


def lint(text, folder=None):
    return [p.as_dict() for p in englishscript.lint(text, folder)]


class Editor:
    """Stands where the editor would: sends the Server dicts and keeps what comes back."""

    def __init__(self, capabilities=None, start=True):
        self.logged = []
        self.server = Server(log=self.logged.append)
        self.ident = 0
        self.published = {}  # uri -> the diagnostics last published for it
        self.texts = {}
        if start:
            self.result = self.request("initialize", {"processId": None, "rootUri": None,
                                                      "capabilities": capabilities or {}})
            self.notify("initialized", {})

    def keep(self, messages):
        for message in messages:
            if message.get("method") == "textDocument/publishDiagnostics":
                self.published[message["params"]["uri"]] = message["params"]["diagnostics"]
        return messages

    def answer(self, method, params):
        self.ident += 1
        out = self.keep(self.server.handle({"jsonrpc": "2.0", "id": self.ident, "method": method, "params": params}))
        answers = [m for m in out if m.get("id") == self.ident and "method" not in m]
        assert len(answers) == 1, out
        return answers[0]

    def request(self, method, params):
        answer = self.answer(method, params)
        assert "error" not in answer, answer
        return answer["result"]

    def notify(self, method, params):
        return self.keep(self.server.handle({"jsonrpc": "2.0", "method": method, "params": params}))

    def open(self, text, uri="file:///tmp/world.english", version=1):
        self.texts[uri] = text
        self.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": "englishscript",
                                                              "version": version, "text": text}})
        return uri

    def open_file(self, path):
        return self.open(path.read_text(encoding="utf-8"), path.as_uri())

    def change(self, uri, text, version=2):
        self.texts[uri] = text
        self.notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": version},
                                               "contentChanges": [{"text": text}]})

    def place(self, uri, needle, inside=0, nth=0):
        """The position of the `nth` place `needle` is written, `inside` characters into it."""
        text = self.texts[uri]
        at = -1
        for _ in range(nth + 1):
            at = text.index(needle, at + 1)
        return {"textDocument": {"uri": uri}, "position": Text(text).position(at + inside)}

    def end_of(self, uri, needle):
        return self.place(uri, needle, len(needle))


class Problem:
    """What the linter gives back, as the server sees it."""

    def __init__(self, **fields):
        self.fields = fields

    def as_dict(self):
        return dict(self.fields)


def linter(*problems):
    return mock.patch.object(englishscript, "lint", lambda source, folder=None, name=None: list(problems))


class Positions(unittest.TestCase):
    def test_columns_are_counted_in_utf16(self):
        text = Text('Say "Héllo 🐉 wörld 🐉🐉" and more.\nSecond.')
        line = text.lines[0]
        for col in range(len(line) + 1):
            position = text.position(text.at(0, col))
            self.assertEqual(position, {"line": 0, "character": utf16(line[:col])})
            self.assertEqual(text.offset(position), col)
            self.assertEqual(text.where(col), (0, col))
        self.assertEqual(text.position(text.at(0, 12)), {"line": 0, "character": 13})  # one dragon before it
        self.assertEqual(text.offset({"line": 0, "character": 12}), 11)  # the middle of the dragon: before it
        self.assertEqual(text.offset({"line": 0, "character": 999}), len(line))
        self.assertEqual(text.offset({"line": 1, "character": 3}), len(line) + 1 + 3)
        self.assertEqual(text.offset({"line": 9, "character": 0}), len(text.text))

    def test_line_endings_of_every_sort(self):
        text = Text("One.\r\nTwo.\rThree.\nFour.")
        self.assertEqual(text.lines, ["One.", "Two.", "Three.", "Four."])
        for number, line in enumerate(text.lines):
            self.assertEqual(text.range(number, 0, len(line)),
                             {"start": {"line": number, "character": 0}, "end": {"line": number, "character": len(line)}})
            self.assertEqual(text.where(text.offset({"line": number, "character": 2})), (number, 2))
        self.assertEqual(text.offset({"line": 0, "character": 99}), 4)  # not past the line break

    def test_a_line_break_only_python_counts(self):
        # str.splitlines (and so the compiler) starts a new line at a form feed; an editor does not.
        text = Text("One.\x0cTwo.\nThree.")
        self.assertEqual(text.lines, ["One.", "Two.", "Three."])
        self.assertEqual(text.range(1, 0, 4), {"start": {"line": 0, "character": 5}, "end": {"line": 0, "character": 9}})
        self.assertEqual(text.range(2, 0, 6), {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 6}})
        self.assertEqual(text.where(text.offset({"line": 0, "character": 6})), (1, 1))

    def test_the_line_after_the_last(self):
        text = Text("One.\n")
        self.assertEqual(text.where(text.offset({"line": 1, "character": 0})), (1, 0))
        self.assertEqual(text.line(1), "")
        self.assertEqual(Text("").where(0), (0, 0))
        self.assertEqual(Text("").range(0, 0, 5), {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}})

    def test_file_uris(self):
        path = EXAMPLES / "almanac.english"
        self.assertTrue(serving.same_file(serving.path_of(path.as_uri()), path))
        self.assertIsNone(serving.path_of("untitled:Untitled-1"))
        if sys.platform == "win32":
            self.assertEqual(str(serving.path_of("file:///c%3A/Users/x/a%20b.english")).lower(), r"c:\users\x\a b.english")
        beside = serving.uri_beside(path.as_uri(), path, EXAMPLES / "almanac" / "roman numerals.english")
        self.assertEqual(beside, path.as_uri().rsplit("/", 1)[0] + "/almanac/roman%20numerals.english")


class StartAndEnd(unittest.TestCase):
    def test_initialize_says_what_the_server_can_do(self):
        can = Editor().result["capabilities"]
        self.assertEqual(can["textDocumentSync"]["change"], 1)  # the whole text each time
        self.assertTrue(can["textDocumentSync"]["openClose"])
        self.assertIn("quickfix", can["codeActionProvider"]["codeActionKinds"])
        self.assertTrue(can["hoverProvider"])
        self.assertTrue(can["documentSymbolProvider"])
        self.assertTrue(can["definitionProvider"])
        self.assertEqual(can["renameProvider"], {"prepareProvider": True})
        self.assertIn("completionProvider", can)
        json.dumps(can)

    def test_nothing_is_answered_before_initialize(self):
        editor = Editor(start=False)
        self.assertEqual(editor.answer("textDocument/hover", {})["error"]["code"], serving.NOT_INITIALIZED)
        self.assertEqual(editor.notify("textDocument/didOpen", {"textDocument": {"uri": "file:///x", "text": "Say 1."}}), [])

    def test_shutdown_then_exit(self):
        editor = Editor()
        self.assertIsNone(editor.request("shutdown", None))
        self.assertEqual(editor.answer("textDocument/hover", {})["error"]["code"], serving.INVALID_REQUEST)
        self.assertIsNone(editor.server.exit_code)
        editor.notify("exit", None)
        self.assertEqual(editor.server.exit_code, 0)
        hasty = Editor()
        hasty.notify("exit", None)
        self.assertEqual(hasty.server.exit_code, 1)

    def test_a_bad_message_is_survived(self):
        editor = Editor()
        for message in ("nonsense", 7, None, [], {}, {"jsonrpc": "2.0", "id": 5}, {"method": 12, "id": 1},
                        {"jsonrpc": "2.0", "id": 9, "result": None}):
            out = editor.server.handle(message)
            for answer in out:
                self.assertIn("error", answer)
        self.assertEqual(editor.server.handle({"jsonrpc": "2.0", "id": 9, "result": None}), [])  # an answer: ignored
        self.assertEqual(editor.answer("textDocument/unheardOf", {})["error"]["code"], serving.METHOD_NOT_FOUND)
        self.assertEqual(editor.notify("$/unheardOf", {}), [])
        self.assertEqual(editor.notify("textDocument/didChange", {"wrong": "shape"}), [])
        self.assertEqual(editor.answer("textDocument/hover", {"textDocument": {"uri": "file:///not/open"}})["result"], None)
        uri = editor.open("Say 1.\n")
        self.assertIn("error", editor.answer("textDocument/hover", {"textDocument": {"uri": uri}}))  # no position
        self.assertEqual(editor.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}}), [])

    def test_a_compiler_that_raises_is_survived(self):
        editor = Editor()
        with mock.patch.object(englishscript, "lint", side_effect=RuntimeError("half-written")), \
                mock.patch.object(englishscript, "compile_source", side_effect=RuntimeError("half-written")):
            uri = editor.open(WORLD)
            self.assertEqual(len(editor.published[uri]), 1)  # it says that it could not check
            self.assertTrue(editor.logged)
            for method in ("hover", "definition", "completion", "prepareRename"):
                self.assertNotIn("error", editor.answer("textDocument/" + method, editor.place(uri, "Smaug")), method)
            self.assertEqual(len(editor.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})), 8)
            renamed = editor.answer("textDocument/rename", {**editor.place(uri, "Smaug"), "newName": "Fafnir"})
            self.assertEqual(renamed["error"]["code"], serving.REQUEST_FAILED)  # nothing vouches for the result


class Diagnostics(unittest.TestCase):
    BAD = ("A dragon has an age (number).\n"
           "There is a dragon called Smaug whose age is 771.\n"
           'Say "Héllo 🐉 {the number of dragns} 🐉"\n'
           "Let the spare be 5\n")

    def test_every_problem_is_published_with_a_range(self):
        editor = Editor()
        uri = editor.open(self.BAD)
        found, expected = editor.published[uri], lint(self.BAD)
        self.assertEqual(len(found), len(expected))
        self.assertGreaterEqual(len(found), 2)
        lines = self.BAD.splitlines()
        for diagnostic, problem in zip(found, expected):
            self.assertEqual(diagnostic["source"], "englishscript")
            self.assertEqual(diagnostic["severity"], 2 if problem["kind"] == "warning" else 1)
            self.assertEqual(diagnostic["code"], problem["category"])
            self.assertTrue(diagnostic["message"].startswith(problem["message"]))
            if problem["hint"]:
                self.assertIn(problem["hint"], diagnostic["message"])
            self.assertEqual(diagnostic["range"]["start"]["line"], problem["line"] - 1)
            self.assertEqual(diagnostic["range"]["end"]["line"], problem["line"] - 1)
            self.assertTrue(cut(self.BAD, diagnostic["range"]), "a range that covers something")
            if problem["see"]:
                self.assertEqual(diagnostic["codeDescription"]["href"],
                                 "https://monstercameron.github.io/EnglishScript/reference.html#s"
                                 + problem["see"].replace(".", "-"))
            line = lines[problem["line"] - 1]
            if problem["col"] is not None and problem["col"] < len(line):
                self.assertEqual(diagnostic["range"]["start"]["character"], utf16(line[:problem["col"]]))
                self.assertEqual(cut(self.BAD, diagnostic["range"]), line[problem["col"]:problem["col"] + problem["width"]])
        json.dumps(found)

    def test_a_column_after_an_emoji_is_counted_in_utf16(self):
        editor = Editor()
        uri = editor.open(self.BAD)
        problem = next((p for p in lint(self.BAD) if p["line"] == 3 and p["col"] is not None and p["col"] > 12), None)
        if problem is None:
            self.skipTest("the linter points at nothing after the dragon on line 3 at the moment")
        diagnostic = next(d for d in editor.published[uri] if d["range"]["start"]["line"] == 2)
        self.assertEqual(diagnostic["range"]["start"]["character"], problem["col"] + 1)  # the dragon counts twice
        self.assertEqual(cut(self.BAD, diagnostic["range"]),
                         self.BAD.splitlines()[2][problem["col"]:problem["col"] + problem["width"]])

    def test_the_shape_of_a_diagnostic(self):
        text = "Say “héllo 🐉” to the wörld.\nSecond line here.\nThird.\n"
        problems = [
            Problem(line=1, col=14, width=2, kind="error", message="First.", hint="Do this.\nOr that.",
                    category="grammar", rule="A sentence ends with a period.", see="4.1"),
            Problem(line=2, col=None, width=1, kind="warning", message="Second.", hint=None, category="style",
                    rule=None, see=None, fix=None),
            Problem(line=3, col=6, width=1, kind="error", message="Third."),  # at the end of the line; keys missing
            Problem(line=99, kind="error", message="Nowhere."),
            Problem(line=2, col=3, width=4, kind="error", message="Elsewhere.", file="almanac/calendar.english"),
        ]
        with linter(*problems):
            editor = Editor()
            uri = editor.open(text)
        first, second, third, nowhere, chapter = editor.published[uri]
        self.assertEqual(first["range"], {"start": {"line": 0, "character": 15}, "end": {"line": 0, "character": 17}})
        self.assertEqual(cut(text, first["range"]), "to")
        self.assertEqual(first["severity"], 1)
        self.assertEqual(first["code"], "grammar")
        self.assertEqual(first["message"], "First.\nDo this.\nOr that.\nThe rule: a sentence ends with a period.")
        self.assertEqual(first["codeDescription"],
                         {"href": "https://monstercameron.github.io/EnglishScript/reference.html#s4-1"})
        self.assertEqual(cut(text, second["range"]), "Second line here.")  # no column: the whole line
        self.assertEqual(second["severity"], 2)
        self.assertEqual(second["message"], "Second.")
        self.assertNotIn("codeDescription", second)
        self.assertEqual(cut(text, third["range"]), ".")
        self.assertNotIn("code", third)
        self.assertEqual(nowhere["range"]["start"]["line"], 2)
        self.assertIn("almanac/calendar.english", chapter["message"])
        self.assertEqual(chapter["range"]["start"], {"line": 0, "character": 0})

    def test_a_change_publishes_again_and_closing_clears(self):
        editor = Editor()
        uri = editor.open(self.BAD)
        self.assertTrue(editor.published[uri])
        editor.change(uri, 'Say "Hello."\n')
        self.assertEqual(editor.published[uri], [])
        editor.change(uri, self.BAD, version=3)
        self.assertTrue(editor.published[uri])
        saved = editor.notify("textDocument/didSave", {"textDocument": {"uri": uri}})
        self.assertEqual([m["method"] for m in saved], ["textDocument/publishDiagnostics"])
        self.assertEqual(saved[0]["params"]["version"], 3)
        closed = editor.notify("textDocument/didClose", {"textDocument": {"uri": uri}})
        self.assertEqual([m["params"] for m in closed], [{"uri": uri, "diagnostics": []}])
        self.assertNotIn(uri, editor.server.documents)

    def test_the_examples_have_nothing_to_mend(self):
        editor = Editor()
        for name in ("dragons.english", "almanac.english"):
            path = EXAMPLES / name
            if lint(path.read_text(encoding="utf-8"), EXAMPLES):
                self.skipTest(f"the linter finds something in examples/{name} at the moment")
            self.assertEqual(editor.published[editor.open_file(path)], [], name)


class QuickFixes(unittest.TestCase):
    BAD = "Let the total be 5\nSay the total\nSay the total + 1.\n"

    def whole(self, uri, text):
        end = Text(text).position(len(text))
        return {"textDocument": {"uri": uri}, "range": {"start": {"line": 0, "character": 0}, "end": end},
                "context": {"diagnostics": []}}

    def test_a_fix_is_offered_and_mends(self):
        before = lint(self.BAD)
        fixable = [p for p in before if p["fix"]]
        if len(fixable) < 2:
            self.skipTest("the linter is not certain how to mend a missing period at the moment")
        editor = Editor()
        uri = editor.open(self.BAD)
        actions = editor.request("textDocument/codeAction", self.whole(uri, self.BAD))
        mends = [a for a in actions if a["title"].startswith("Mend: ")]
        self.assertEqual(len(mends), len(fixable))
        for action, problem in zip(mends, fixable):
            self.assertEqual(action["kind"], "quickfix")
            self.assertEqual(action["title"], "Mend: " + problem["fix"]["text"].strip())
            self.assertEqual(action["diagnostics"], [d for d in editor.published[uri]
                                                     if d["range"]["start"]["line"] == problem["line"] - 1])
            edits = action["edit"]["changes"][uri]
            self.assertEqual(len(edits), 1)
            self.assertEqual(cut(self.BAD, edits[0]["range"]), self.BAD.splitlines()[problem["fix"]["line"] - 1])
            mended = apply(self.BAD, edits)
            self.assertEqual(len(lint(mended)), len(before) - 1, "one problem fewer")
        # Only the fixes of the lines asked about.
        asked = {"textDocument": {"uri": uri}, "context": {"diagnostics": []},
                 "range": {"start": {"line": 1, "character": 2}, "end": {"line": 1, "character": 2}}}
        here = [a for a in editor.request("textDocument/codeAction", asked) if a["title"].startswith("Mend: ")]
        self.assertEqual([a["title"] for a in here], ["Mend: " + fixable[1]["fix"]["text"].strip()])

    def test_mend_all(self):
        before = lint(self.BAD)
        if len([p for p in before if p["fix"]]) < 2:
            self.skipTest("the linter is not certain how to mend a missing period at the moment")
        editor = Editor()
        uri = editor.open(self.BAD)
        actions = editor.request("textDocument/codeAction", self.whole(uri, self.BAD))
        every = [a for a in actions if a["title"] == "Mend all that can be mended"]
        self.assertEqual(len(every), 1)
        mended = apply(self.BAD, every[0]["edit"]["changes"][uri])
        self.assertEqual(len(lint(mended)), len(before) - 2)
        self.assertEqual(mended.splitlines()[2], self.BAD.splitlines()[2])
        # With one thing to mend there is no "all".
        editor.change(uri, apply(self.BAD, [every[0]["edit"]["changes"][uri][0]]))
        actions = editor.request("textDocument/codeAction", self.whole(uri, editor.texts[uri]))
        self.assertEqual([a["title"] for a in actions if not a["title"].startswith("Mend: ")], [])
        self.assertEqual(len(actions), 1)

    def test_the_edit_replaces_the_whole_line_whatever_is_on_it(self):
        text = "First.\r\n  Say “héllo 🐉” to the wörld\r\nThird.\r\n"
        fixed = '  Say "héllo 🐉" to the wörld.'
        problems = [Problem(line=2, col=27, width=1, kind="error", message="No period.", category="punctuation",
                            fix={"line": 2, "text": fixed}),
                    Problem(line=3, col=0, width=5, kind="warning", message="No fix for this.", fix=None),
                    Problem(line=1, col=0, width=5, kind="warning", message="A fix for another line.",
                            fix={"line": 3, "text": "Third!"}),
                    Problem(line=1, col=0, width=5, kind="warning", message="A fix for no line.",
                            fix={"line": 40, "text": "Fortieth."})]
        with linter(*problems):
            editor = Editor()
            uri = editor.open(text)
            actions = editor.request("textDocument/codeAction", self.whole(uri, text))
            only = editor.request("textDocument/codeAction", {**self.whole(uri, text), "context": {"only": ["refactor"]}})
            fix_all = editor.request("textDocument/codeAction",
                                     {**self.whole(uri, text), "context": {"only": ["source.fixAll"]}})
        self.assertEqual([a["title"] for a in actions],
                         ["Mend: " + fixed.strip(), "Mend: Third!", "Mend all that can be mended"])
        self.assertEqual(apply(text, actions[0]["edit"]["changes"][uri]), "First.\r\n" + fixed + "\r\nThird.\r\n")
        self.assertEqual(apply(text, actions[1]["edit"]["changes"][uri]), text.replace("Third.", "Third!"))
        self.assertEqual(apply(text, actions[2]["edit"]["changes"][uri]), "First.\r\n" + fixed + "\r\nThird!\r\n")
        self.assertEqual(only, [])
        self.assertEqual([a["kind"] for a in fix_all], ["source.fixAll.englishscript"])


class Hover(unittest.TestCase):
    def test_a_good_line_says_how_it_was_read(self):
        path = EXAMPLES / "dragons.english"
        source = path.read_text(encoding="utf-8")
        try:
            notes = englishscript.compile_source(source, EXAMPLES, str(path)).notes
        except englishscript.EnglishError:
            self.skipTest("the compiler does not read examples/dragons.english at the moment")
        by_line = {}
        for number, note in notes:
            by_line.setdefault(number, []).append(note)
        self.assertTrue(by_line)
        editor = Editor(PLAIN_HOVER)
        uri = editor.open_file(path)
        lines = source.splitlines()
        for number, said in by_line.items():
            where = {"textDocument": {"uri": uri}, "position": {"line": number - 1, "character": len(lines[number - 1]) - 1}}
            hover = editor.request("textDocument/hover", where)
            self.assertEqual(hover["contents"]["kind"], "plaintext")
            for note in said:
                self.assertIn(note, hover["contents"]["value"])
        markdown = Editor()
        uri = markdown.open_file(path)
        number = min(by_line)
        hover = markdown.request("textDocument/hover", {"textDocument": {"uri": uri},
                                                        "position": {"line": number - 1, "character": 0}})
        self.assertEqual(hover["contents"]["kind"], "markdown")
        self.assertEqual(hover["contents"]["value"].count("\n- "), len(by_line[number]))
        blank = {"textDocument": {"uri": uri}, "position": {"line": 1, "character": 0}}
        self.assertIsNone(markdown.request("textDocument/hover", blank))

    def test_a_bad_line_says_what_is_wrong(self):
        text = Diagnostics.BAD
        problem = next(p for p in lint(text) if p["kind"] == "error")
        for capabilities, kind in ((PLAIN_HOVER, "plaintext"), ({}, "markdown")):
            editor = Editor(capabilities)
            uri = editor.open(text)
            where = {"textDocument": {"uri": uri}, "position": {"line": problem["line"] - 1, "character": 1}}
            hover = editor.request("textDocument/hover", where)
            self.assertEqual(hover["contents"]["kind"], kind)
            self.assertEqual(hover["range"]["start"]["line"], problem["line"] - 1)
            value = hover["contents"]["value"]
            if kind == "plaintext":
                self.assertIn(problem["message"], value)
                for part in (problem["hint"], problem["rule"] and problem["rule"][1:]):
                    if part:
                        self.assertIn(part, value)
            elif problem["see"]:
                self.assertIn("reference.html#s" + problem["see"].replace(".", "-"), value)

    def test_the_markdown_of_a_problem(self):
        problem = {"kind": "warning", "category": "kinds", "message": "A *star* and an _underline_.",
                   "hint": "First line.\nSecond line.", "rule": "A rule to remember.", "see": "5.2",
                   "fix": {"line": 1, "text": "  Say 1.  "}}
        value = Server.problem_text(problem, markdown=True)
        self.assertIn("**Kinds of value, a suggestion**", value)
        self.assertIn(r"A \*star\* and an \_underline\_.", value)
        self.assertIn("First line.  \nSecond line.", value)
        self.assertIn("[section 5.2](https://monstercameron.github.io/EnglishScript/reference.html#s5-2)", value)
        self.assertIn("```\nSay 1.\n```", value)
        plain = Server.problem_text(problem, markdown=False)
        self.assertIn("A *star* and an _underline_.", plain)
        self.assertIn("The rule: a rule to remember.", plain)
        self.assertEqual(Server.problem_text({"message": "Only this."}, markdown=False), "Problem\n\nOnly this.")

    def test_a_name_says_where_it_is_defined(self):
        editor = Editor(PLAIN_HOVER)
        uri = editor.open(WORLD)
        hover = editor.request("textDocument/hover", editor.place(uri, "Greet Smaug", 8))
        self.assertIn("Smaug", hover["contents"]["value"])
        self.assertIn("There is a dragon called Smaug whose age is 771.", hover["contents"]["value"])


class Symbols(unittest.TestCase):
    def symbols(self, text, uri="file:///tmp/world.english"):
        editor = Editor()
        editor.open(text, uri)
        return editor.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}})

    def test_the_symbols_of_the_dragons_example(self):
        source = (EXAMPLES / "dragons.english").read_text(encoding="utf-8")
        lines = source.splitlines()
        symbols = self.symbols(source)
        by_kind = {}
        for symbol in symbols:
            by_kind.setdefault(symbol["kind"], []).append(symbol["name"])
        self.assertEqual(by_kind[5], ["dragon", "treasure", "knight"])  # Class: the kinds
        self.assertEqual(by_kind[19], ["Smaug", "Norbert", "Arkenstone", "Goblet", "Teaspoon", "Gawain", "Robin"])
        self.assertEqual(by_kind[17], ["ancient", "poor", "brave"])  # the adjectives
        self.assertEqual(by_kind[6], ["send", "give"])  # the verbs
        self.assertEqual(by_kind[12], ["hoard", "tax"])  # what is worked out
        self.assertEqual(set(by_kind), {5, 19, 17, 6, 12})  # "the loot" is a variable of a block: not here
        children = {s["name"]: [c["name"] for c in s.get("children", [])] for s in symbols if s["kind"] == 5}
        self.assertEqual(children, {"dragon": ["age"], "treasure": ["worth", "owner"], "knight": ["purse", "courage"]})
        starts = {
            "dragon": "A dragon has", "hoard": "The hoard of a dragon is", "ancient": "A dragon is ancient when",
            "Smaug": "There is a dragon called Smaug", "send": "To send a knight against a dragon:",
            "give": "To give a treasure to a dragon:", "Robin": "There is a knight called Robin",
        }
        for symbol in symbols:
            chosen, whole = symbol["selectionRange"], symbol["range"]
            self.assertEqual(cut(source, chosen), symbol["name"])
            self.assertLessEqual((whole["start"]["line"], whole["start"]["character"]),
                                 (chosen["start"]["line"], chosen["start"]["character"]))
            self.assertGreaterEqual((whole["end"]["line"], whole["end"]["character"]),
                                    (chosen["end"]["line"], chosen["end"]["character"]))
            if symbol["name"] in starts:
                self.assertTrue(lines[chosen["start"]["line"]].startswith(starts[symbol["name"]]), symbol["name"])
        send = next(s for s in symbols if s["name"] == "send")
        self.assertTrue(cut(source, send["range"]).startswith("To send a knight against a dragon:"))
        self.assertTrue(cut(source, send["range"]).rstrip().endswith('in tax from {the dragon\'s name}."'))

    def test_variables_reactions_and_the_rest(self):
        symbols = self.symbols(WORLD)
        self.assertEqual([(s["name"], s["kind"]) for s in symbols], [
            ("dragon", 5), ("ancient", 17), ("Smaug", 19), ("Norbert", 19), ("greet", 6), ("total", 13),
            ("asleep", 17), ("Whenever a dragon becomes asleep", 24)])
        more = self.symbols("Let the tax rate always be 10%.\n"
                            "To work out the bounty (money) for a size (number):\n  The answer is $5.\n"
                            'Ask "Age?" and let the age (number) be the reply.\n'
                            "A mood is one of sleepy, grumpy or very cross.\n"
                            "Whenever everything has settled:\n  Say the age.\n")
        self.assertEqual([(s["name"], s["kind"], [c["name"] for c in s.get("children", [])]) for s in more],
                         [("tax rate", 14, []), ("bounty", 12, []), ("age", 13, []),
                          ("mood", 10, ["sleepy", "grumpy", "very cross"]),
                          ("Whenever everything has settled", 24, [])])

    def test_the_outline_is_the_compilers_own_table_of_names(self):
        """Where the compiler has a table of names, the outline is that table, not a guess from the text."""
        text = ("A dragon has an age (number).\n"
                "To work out the bounty (money) for a dragn:\n  The answer is $5.\n"  # refused: no kind "dragn"
                "There is a dragon called Smaug whose age is 771.\n")
        table = englishscript.names(text)
        self.assertEqual([n["name"] for n in table["names"]], ["dragon", "age", "Smaug"])
        self.assertEqual([s["name"] for s in self.symbols(text)], ["dragon", "Smaug"])
        # Without the table, the sentence forms are read instead, and they take the refused sentence at its word.
        with mock.patch.object(englishscript, "names", side_effect=RuntimeError("no table today")):
            self.assertEqual([s["name"] for s in self.symbols(text)], ["dragon", "bounty", "Smaug"])
        with mock.patch.object(englishscript, "names", None):
            self.assertEqual([s["name"] for s in self.symbols(text)], ["dragon", "bounty", "Smaug"])
        with mock.patch.object(englishscript, "names", lambda *args, **more: {"names": [], "chapters": []}):
            self.assertEqual([s["name"] for s in self.symbols(text)], ["dragon", "bounty", "Smaug"])

    def test_a_text_that_is_not_a_program(self):
        self.assertEqual(self.symbols(""), [])
        self.assertEqual(self.symbols("To\nA\nThe of a\nLet the\nThere is a dragon called\n((((\n\"unclosed"), [])


class Definitions(unittest.TestCase):
    def setUp(self):
        self.editor = Editor()
        self.path = EXAMPLES / "almanac.english"
        self.uri = self.editor.open_file(self.path)

    def test_into_a_chapter(self):
        found = self.editor.request("textDocument/definition", self.editor.place(self.uri, "leapness of the year", 3))
        self.assertTrue(found["uri"].endswith("/examples/almanac/calendar.english"))
        self.assertTrue(found["uri"].startswith(self.uri.rsplit("/", 1)[0]))
        chapter = serving.path_of(found["uri"]).read_text(encoding="utf-8")
        self.assertEqual(cut(chapter, found["range"]), "leapness")
        line = chapter.splitlines()[found["range"]["start"]["line"]]
        self.assertTrue(line.startswith("To work out the leapness"))
        # A name of several words, a kind and a thing of other chapters.
        for needle, inside, chapter_name, start in (
                ("month title of the feast", 8, "calendar", "To work out the month title"),
                ("For each feast", 10, "feasts", "A feast has"),
                ("Michaelmas's month", 2, "feasts", "There is a feast called Michaelmas"),
                ("wintry feasts", 9, "feasts", "A feast has")):
            with self.subTest(needle):
                found = self.editor.request("textDocument/definition", self.editor.place(self.uri, needle, inside))
                self.assertTrue(found["uri"].endswith(f"/examples/almanac/{chapter_name}.english"))
                chapter = serving.path_of(found["uri"]).read_text(encoding="utf-8")
                self.assertTrue(chapter.splitlines()[found["range"]["start"]["line"]].startswith(start))

    def test_from_the_use_sentence_to_the_file(self):
        found = self.editor.request("textDocument/definition", self.editor.place(self.uri, "Use the numerals", 2))
        self.assertTrue(found["uri"].endswith("/examples/almanac/numerals.english"))
        self.assertEqual(found["range"]["start"], {"line": 0, "character": 0})

    def test_in_the_same_file(self):
        found = self.editor.request("textDocument/definition", self.editor.place(self.uri, "the roman of the year", 18))
        self.assertEqual(found["uri"], self.uri)
        source = self.editor.texts[self.uri]
        self.assertEqual(cut(source, found["range"]), "year")
        self.assertTrue(source.splitlines()[found["range"]["start"]["line"]].startswith("Let the year be"))
        nothing = self.editor.request("textDocument/definition", self.editor.place(self.uri, "being a leap year", 9))
        self.assertIsNone(nothing)  # words in quotes are not names

    def test_a_chapter_that_is_open_is_read_from_the_editor(self):
        chapter = EXAMPLES / "almanac" / "calendar.english"
        text = "\n\n\n" + chapter.read_text(encoding="utf-8")
        self.editor.open(text, chapter.as_uri())
        found = self.editor.request("textDocument/definition", self.editor.place(self.uri, "leapness of the year", 3))
        self.assertTrue(text.splitlines()[found["range"]["start"]["line"]].startswith("To work out the leapness"))

    def test_names_of_blocks_and_verbs(self):
        editor = Editor()
        uri = editor.open(WORLD)
        for needle, inside, start in (("{the greeting}", 6, "  Let the greeting be"), ("Greet Smaug", 2, "To greet a dragon:"),
                                      ("Greet Smaug", 8, "There is a dragon called Smaug"),
                                      ("{the dragon} sleeps", 6, "A dragon has"), ("to the total", 8, "Let the total be")):
            with self.subTest(needle):
                found = editor.request("textDocument/definition", editor.place(uri, needle, inside))
                self.assertEqual(found["uri"], uri)
                self.assertTrue(WORLD.splitlines()[found["range"]["start"]["line"]].startswith(start))


class Completion(unittest.TestCase):
    def test_sentence_forms_at_the_start_of_a_line(self):
        editor = Editor(SNIPPETS)
        uri = editor.open(WORLD + "\n")
        where = {"textDocument": {"uri": uri}, "position": {"line": len(WORLD.splitlines()), "character": 0}}
        items = editor.request("textDocument/completion", where)
        texts = [item["textEdit"]["newText"] for item in items]
        for start in ("Say ", "Let the ", "If ", "For each ", "There is a ", "To ", "To work out the ", "Whenever ",
                      "Try:", "Use the ", "Otherwise", "Repeat ", "While ", "A ", "Set ", "Add ", "Ask ", "For example, "):
            self.assertTrue(any(text.startswith(start) for text in texts), start)
        for item in items:
            self.assertEqual(item["insertTextFormat"], 2)
            self.assertEqual(item["textEdit"]["range"], {"start": where["position"], "end": where["position"]})
            self.assertTrue(item["label"])
            self.assertNotIn("\t", item["textEdit"]["newText"])  # the language refuses tabs
        verbs = [item for item in items if item["kind"] == 2]
        self.assertEqual([item["textEdit"]["newText"] for item in verbs], ["Greet ${1:dragon}."])
        self.assertFalse(any(text.startswith("The answer is") for text in texts))  # that belongs inside a block

    def test_a_word_begun_is_replaced_and_a_block_has_its_own_forms(self):
        editor = Editor(SNIPPETS)
        text = WORLD + "If the total is 1:\n    sa"
        uri = editor.open(text)
        items = editor.request("textDocument/completion", editor.end_of(uri, "    sa"))
        self.assertEqual({cut(text, item["textEdit"]["range"]) for item in items}, {"sa"})
        texts = [item["textEdit"]["newText"] for item in items]
        self.assertTrue(any(text.startswith("Stop.") for text in texts))
        self.assertFalse(any(text.startswith("Whenever") for text in texts))  # a definition: top level only
        self.assertFalse(any(text.startswith("A ") for text in texts))

    def test_without_snippets_plain_text_is_given(self):
        editor = Editor()
        uri = editor.open("")
        items = editor.request("textDocument/completion", {"textDocument": {"uri": uri},
                                                           "position": {"line": 0, "character": 0}})
        self.assertTrue(items)
        for item in items:
            self.assertEqual(item["insertTextFormat"], 1)
            self.assertNotIn("${", item["textEdit"]["newText"])
        self.assertIn("Let the total be 0.", [item["textEdit"]["newText"] for item in items])

    def test_the_snippets_are_sentences_the_compiler_reads(self):
        """Each form, filled in with its own examples, in a world that has the words they use."""
        world = ("A dragon has an age (number).\nThe hoard of a dragon is $5.\nA knight has a purse (money).\n"
                 "A task has a size (number).\nA task can be done.\nA knight is broke when its purse is $0.\n"
                 "There is a task called Chore whose size is 1.\nLet the total be 0.\n"
                 "A card has a wording (text) and a line (text).\nA card can be open.\nA card can be done.\n"
                 'There is a card called Milk whose wording is "milk" and whose line is "".\n'
                 'Let the heading be "- milk".\nLet the scores be a list of 1 and 2.\n')
        self.assertEqual([p for p in lint(world) if p["kind"] == "error"], [])
        after_a_try = "Try:\n  Say 1.\nIf that fails:\n  Say 2.\n" + serving.plain_snippet(
            next(snippet for label, snippet, _, _ in serving.OPENERS if label == "Either way:")) + "Say 3.\n"
        self.assertEqual([p for p in lint(after_a_try) if p["kind"] == "error"], [])
        refused = []
        for label, snippet, where, _ in serving.OPENERS:
            sentence = serving.plain_snippet(snippet)
            self.assertNotIn("$", sentence.replace("$0", "").replace("$5", ""), label)
            if where == "block" or sentence.startswith(("Otherwise", "Use the", "This chapter", "Try:", "Ask ", "Write ",
                                                        "Add the total to the file", "There is a dragon called",
                                                        "A dragon has", "Either way")):
                continue  # needs a sentence before it, a file, or words this world has already
            if sentence.endswith(":\n  "):
                sentence += "Say 1."
            sentence = {"Remove the task.": "Remove Chore.", "Now the task is done.": "Now Chore is done.",
                        "Let the total be 0.": "Let the tally be 0.", "A task can be done.": "A task can be late.",
                        "Let the scores be a list of 3, 8 and 5.": "Let the marks be a list of 3, 8 and 5.",
                        "Let the scores be an empty list of numbers.": "Let the blanks be an empty list of numbers.",
                        "For each rival in dragons:\n  Say 1.": "For each rival in dragons:\n  Say the rival.",
                        "A dragon is ancient when its age is at least 500.": "A dragon is old when its age is at least 500.",
                        "The tax of a dragon is 10% of its hoard.": "The levy of a dragon is 10% of its hoard.",
                        }.get(sentence, sentence)
            errors = [p for p in lint(world + sentence + "\n") if p["kind"] == "error"]
            if errors:
                refused.append((label, sentence, errors[0]["message"]))
        self.assertEqual(refused, [])

    def test_properties_after_a_possessive(self):
        editor = Editor()
        text = WORLD + "Say Smaug's \nSay \"{its a}\"\nIf Smaug has a "
        uri = editor.open(text)
        for needle in ("Say Smaug's ", 'Say "{its a', "If Smaug has a "):
            items = editor.request("textDocument/completion", editor.end_of(uri, needle))
            labels = [item["label"] for item in items]
            self.assertIn("age", labels, needle)
            self.assertIn("name", labels, needle)
            self.assertNotIn("Smaug", labels, needle)
            self.assertNotIn("greet", labels, needle)
            self.assertEqual({item["kind"] for item in items if item["label"] in ("age", "name")}, {10})

    def test_names_elsewhere(self):
        editor = Editor()
        text = WORLD + "Say the \nTo wake a dragon:\n  Let the noise be 1.\n  Say the "
        uri = editor.open(text)
        after_world = {"textDocument": {"uri": uri}, "position": {"line": len(WORLD.splitlines()), "character": 8}}
        top = [item["label"] for item in editor.request("textDocument/completion", after_world)]
        for label in ("Smaug", "Norbert", "dragon", "dragons", "total", "ancient", "asleep"):
            self.assertIn(label, top)
        for label in ("greet", "greeting", "noise", "wake"):  # a verb; names of blocks; what comes later
            self.assertNotIn(label, top)
        inside = [item["label"] for item in editor.request("textDocument/completion", editor.end_of(uri, "  Say the "))]
        self.assertIn("noise", inside)
        self.assertIn("Smaug", inside)
        self.assertNotIn("greeting", inside)
        self.assertEqual(len(inside), len(set(inside)))

    def test_nothing_inside_quotes_or_comments_but_names_in_a_fill_in(self):
        editor = Editor()
        text = WORLD + 'Say "Hello \nSay 1. # a comment \nSay "Hello {the '
        uri = editor.open(text)
        in_quotes = {"textDocument": {"uri": uri}, "position": {"line": len(WORLD.splitlines()), "character": 11}}
        self.assertEqual(editor.request("textDocument/completion", in_quotes), [])
        self.assertEqual(editor.request("textDocument/completion", editor.end_of(uri, "# a comment ")), [])
        labels = [item["label"] for item in editor.request("textDocument/completion", editor.end_of(uri, "Hello {the "))]
        self.assertIn("Smaug", labels)

    def test_the_words_of_a_chapter(self):
        editor = Editor()
        path = EXAMPLES / "almanac.english"
        text = path.read_text(encoding="utf-8") + "Say the "
        uri = editor.open(text, path.as_uri())
        labels = [item["label"] for item in editor.request("textDocument/completion", editor.end_of(uri, "\nSay the "))]
        for label in ("leapness", "month title", "weekday", "feast", "feasts", "Michaelmas", "wintry", "year"):
            self.assertIn(label, labels)
        self.assertNotIn("month row", labels)  # the calendar keeps that to itself


class RenameRequests(unittest.TestCase):
    def setUp(self):
        if [p for p in lint(WORLD) if p["kind"] == "error"]:
            self.skipTest("the compiler does not read this file's own program at the moment")
        self.editor = Editor()
        self.uri = self.editor.open(WORLD)

    def rename(self, where, new):
        return self.editor.answer("textDocument/rename", {**where, "newName": new})

    def test_prepare_gives_the_name_and_where_it_is(self):
        for needle, inside, placeholder, covered in (("Greet Smaug", 8, "Smaug", "Smaug"), ("to the total", 8, "total", "total"),
                                                     ("Greet Smaug", 0, "Greet", "Greet")):
            found = self.editor.request("textDocument/prepareRename", self.editor.place(self.uri, needle, inside))
            self.assertEqual(found["placeholder"], placeholder)
            self.assertEqual(cut(WORLD, found["range"]), covered)
        for needle, inside in (("Hello", 2), ("Say the total", 1), ("whose age", 2)):
            self.assertIsNone(self.editor.request("textDocument/prepareRename", self.editor.place(self.uri, needle, inside)))

    def test_a_rename_is_a_workspace_edit(self):
        answer = self.rename(self.editor.place(self.uri, "Greet Smaug", 8), "Fafnir")
        edits = answer["result"]["changes"][self.uri]
        self.assertEqual({cut(WORLD, e["range"]) for e in edits}, {"Smaug"})
        self.assertEqual(apply(WORLD, edits), renaming.rename(WORLD, "Smaug", "Fafnir"))
        self.assertEqual(apply(WORLD, edits), WORLD.replace("Smaug", "Fafnir"))

    def test_a_kind_can_be_renamed_from_its_plural(self):
        text = WORLD + "Say the number of dragons.\n"
        self.editor.change(self.uri, text)
        where = self.editor.place(self.uri, "of dragons", 5)
        self.assertEqual(self.editor.request("textDocument/prepareRename", where)["placeholder"], "dragon")
        edits = self.rename(where, "wyrm")["result"]["changes"][self.uri]
        self.assertEqual(apply(text, edits), renaming.rename(text, "dragon", "wyrm"))
        self.assertIn("Say the number of wyrms.", apply(text, edits))

    def test_a_name_of_a_block_is_renamed_in_its_block(self):
        text = WORLD + "To wake a dragon:\n  Let the greeting be 1.\n  Say the greeting.\n"
        self.editor.change(self.uri, text)
        edits = self.rename(self.editor.place(self.uri, "{the greeting}", 6), "welcome")["result"]["changes"][self.uri]
        mended = apply(text, edits)
        self.assertIn('  Let the welcome be "Hello".\n  Say "{the welcome}, {the dragon}."', mended)
        self.assertIn("  Let the greeting be 1.\n  Say the greeting.", mended)

    def test_a_verb_and_a_property_of_one_word_are_told_apart(self):
        text = WORLD.replace("To greet", "To age").replace("Greet Smaug", "Age Smaug")
        if [p for p in lint(text) if p["kind"] == "error"]:
            self.skipTest("the compiler does not let a verb share a property's word at the moment")
        self.editor.change(self.uri, text)
        edits = self.rename(self.editor.place(self.uri, "Age Smaug", 1), "greet")["result"]["changes"][self.uri]
        self.assertEqual(apply(text, edits), WORLD)

    def test_a_refusal_is_an_error_with_the_reason(self):
        for needle, inside, new in (("Greet Smaug", 8, "Norbert"), ("to the total", 8, "list"),
                                    ("to the total", 8, "sum of"), ("Greet Smaug", 8, "")):
            with self.subTest(new=new):
                answer = self.rename(self.editor.place(self.uri, needle, inside), new)
                self.assertEqual(answer["error"]["code"], serving.REQUEST_FAILED)
                self.assertGreater(len(answer["error"]["message"]), 10)
        nowhere = self.rename(self.editor.place(self.uri, "Hello", 2), "Goodbye")
        self.assertEqual(nowhere["error"]["code"], serving.REQUEST_FAILED)

    def test_a_name_of_a_chapter_is_not_renamed_from_outside(self):
        path = EXAMPLES / "almanac.english"
        uri = self.editor.open_file(path)
        where = self.editor.place(uri, "leapness of the year", 3)
        self.assertIsNone(self.editor.request("textDocument/prepareRename", where))
        self.assertIn("error", self.rename(where, "leaping"))


class StatedPlurals(unittest.TestCase):
    """A plural stated in brackets after its kind: "A person (plural people) has ..." (section 4.1)."""

    TEXT = ("A person (plural people) has an age (number).\n"
            "A dragon has a rider (person, if any).\n"
            "There is a person called Ann whose age is 3.\n"
            "Say the number of people.\n"
            "Say the number of dragons.\n")

    def setUp(self):
        self.assertEqual([p for p in lint(self.TEXT) if p["kind"] == "error"], [], "the compiler reads this form")
        self.editor = Editor()
        self.uri = self.editor.open(self.TEXT)
        self.assertEqual(self.editor.published[self.uri], [])

    def test_the_outline_has_the_kind_and_its_properties(self):
        symbols = self.editor.request("textDocument/documentSymbol", {"textDocument": {"uri": self.uri}})
        self.assertEqual([(s["name"], s["kind"], [c["name"] for c in s.get("children", [])]) for s in symbols],
                         [("person", 5, ["age"]), ("dragon", 5, ["rider"]), ("Ann", 19, [])])
        self.assertEqual(cut(self.TEXT, symbols[0]["selectionRange"]), "person")

    def test_the_stated_plural_is_suggested_and_the_one_by_rule_is_not(self):
        text = self.TEXT + "Say the number of "
        self.editor.change(self.uri, text)
        labels = [i["label"] for i in self.editor.request("textDocument/completion", self.editor.end_of(self.uri, "\nSay the number of "))]
        self.assertIn("people", labels)
        self.assertIn("person", labels)
        self.assertIn("dragons", labels)
        self.assertNotIn("persons", labels)

    def test_the_stated_plural_leads_to_where_it_is_stated(self):
        where = self.editor.place(self.uri, "of people", 5)
        found = self.editor.request("textDocument/definition", where)
        self.assertEqual(found["uri"], self.uri)
        self.assertEqual(found["range"]["start"]["line"], 0)
        self.assertEqual(cut(self.TEXT, found["range"]), "people")
        hover = self.editor.request("textDocument/hover", where)
        self.assertIn("person", hover["contents"]["value"])

    def test_renaming_the_kind_keeps_the_plural_and_the_plural_can_be_renamed(self):
        kind = self.editor.place(self.uri, "(person, if any)", 3)
        self.assertEqual(self.editor.request("textDocument/prepareRename", kind)["placeholder"], "person")
        edits = self.editor.request("textDocument/rename", {**kind, "newName": "human"})["changes"][self.uri]
        self.assertEqual(apply(self.TEXT, edits), self.TEXT.replace("person", "human"))
        plural = self.editor.place(self.uri, "of people", 5)
        self.assertEqual(self.editor.request("textDocument/prepareRename", plural)["placeholder"], "people")
        edits = self.editor.request("textDocument/rename", {**plural, "newName": "folk"})["changes"][self.uri]
        self.assertEqual(apply(self.TEXT, edits), self.TEXT.replace("people", "folk"))
        # A kind whose plural is formed by rule is still renamed from its plural.
        ruled = self.editor.place(self.uri, "of dragons", 5)
        self.assertEqual(self.editor.request("textDocument/prepareRename", ruled)["placeholder"], "dragon")


class AnyAlphabet(unittest.TestCase):
    """Names in any alphabet (section 3), and columns in UTF-16 around them."""

    SAGA = ("A drağon has a länge (number).\n"
            "An élan is one of été, hiver or très froid.\n"
            "There is a drağon called Fáfnir whose länge is 771.\n"
            "There is a drağon called 𝒜lpha Ωmega whose länge is 1.\n"
            "Let the Überzahl be 2.\n"
            "To grüß a drağon:\n"
            '  Say "Grüß {the drağon}: {𝒜LPHA ΩMEGA\'s LÄNGE}, {the überzahl}."\n'
            "Grüß fáfnir.\n"
            "Say ÜBERZAHL + 𝒜lpha Ωmega's Länge.\n")

    def setUp(self):
        self.assertEqual([p for p in lint(self.SAGA) if p["kind"] == "error"], [])
        self.editor = Editor(SNIPPETS)
        self.uri = self.editor.open(self.SAGA)

    def test_the_outline(self):
        symbols = self.editor.request("textDocument/documentSymbol", {"textDocument": {"uri": self.uri}})
        self.assertEqual([(s["name"], s["kind"], [c["name"] for c in s.get("children", [])]) for s in symbols], [
            ("drağon", 5, ["länge"]), ("élan", 10, ["été", "hiver", "très froid"]), ("Fáfnir", 19, []),
            ("𝒜lpha Ωmega", 19, []), ("Überzahl", 13, []), ("grüß", 6, [])])
        for symbol in symbols:
            self.assertEqual(cut(self.SAGA, symbol["selectionRange"]), symbol["name"])
        beyond = symbols[3]["selectionRange"]
        self.assertEqual(beyond["end"]["character"] - beyond["start"]["character"], len("𝒜lpha Ωmega") + 1)

    def test_definitions_whatever_the_capitals(self):
        for needle, inside, written, start in (
                ("{𝒜LPHA ΩMEGA's", 9, "𝒜lpha Ωmega", "There is a drağon called 𝒜lpha"),
                ("ΩMEGA's LÄNGE", 9, "länge", "A drağon has"), ("{the überzahl}", 6, "Überzahl", "Let the Überzahl"),
                ("Grüß fáfnir", 1, "grüß", "To grüß"), ("Grüß fáfnir", 7, "Fáfnir", "There is a drağon called Fáfnir"),
                ("Say ÜBERZAHL", 5, "Überzahl", "Let the Überzahl"), ("{the drağon}", 6, "drağon", "A drağon has")):
            with self.subTest(needle):
                found = self.editor.request("textDocument/definition", self.editor.place(self.uri, needle, inside))
                self.assertEqual(cut(self.SAGA, found["range"]), written)
                self.assertTrue(self.SAGA.splitlines()[found["range"]["start"]["line"]].startswith(start))

    def test_a_problem_after_a_letter_beyond_the_first_plane(self):
        text = self.SAGA + "Say 𝒜lpha Ωmega's längee + 𝒜lpha Ωmega's länge.\n"
        self.editor.change(self.uri, text)
        problem = next(p for p in lint(text) if p["kind"] == "error")
        self.assertEqual((problem["line"], problem["col"]), (10, 18))
        diagnostic = next(d for d in self.editor.published[self.uri] if d["severity"] == 1)
        self.assertEqual(diagnostic["range"]["start"], {"line": 9, "character": 19})  # the 𝒜 counts twice
        self.assertEqual(cut(text, diagnostic["range"]), "längee")

    def test_a_rename(self):
        where = self.editor.place(self.uri, "{𝒜LPHA ΩMEGA's", 9)
        prepared = self.editor.request("textDocument/prepareRename", where)
        self.assertEqual(cut(self.SAGA, prepared["range"]), "𝒜LPHA ΩMEGA")
        edits = self.editor.request("textDocument/rename", {**where, "newName": "Sköll"})["changes"][self.uri]
        self.assertEqual([cut(self.SAGA, e["range"]) for e in edits], ["𝒜lpha Ωmega", "𝒜LPHA ΩMEGA", "𝒜lpha Ωmega"])
        self.assertEqual(apply(self.SAGA, edits), renaming.rename(self.SAGA, "𝒜lpha Ωmega", "Sköll"))
        self.assertIn("{SKÖLL's LÄNGE}", apply(self.SAGA, edits))

    def test_suggestions(self):
        text = self.SAGA + "grü"
        self.editor.change(self.uri, text)
        items = self.editor.request("textDocument/completion", self.editor.end_of(self.uri, "\ngrü"))
        self.assertEqual({cut(text, item["textEdit"]["range"]) for item in items}, {"grü"})
        self.assertIn("Grüß ${1:drağon}.", [item["textEdit"]["newText"] for item in items])
        text = self.SAGA + "Say Fáfnir's \nSay the "
        self.editor.change(self.uri, text)
        after = [i["label"] for i in self.editor.request("textDocument/completion", self.editor.end_of(self.uri, "Say Fáfnir's "))]
        self.assertIn("länge", after)
        names = [i["label"] for i in self.editor.request("textDocument/completion", self.editor.end_of(self.uri, "\nSay the "))]
        for label in ("Fáfnir", "𝒜lpha Ωmega", "Überzahl", "drağon", "drağons", "élan", "très froid"):
            self.assertIn(label, names)


class WhatTheCompilerGives(unittest.TestCase):
    """The parts of the compiler made for tools: notes beside errors, unsaved chapters, headings, the version."""

    def test_the_version_and_the_headings(self):
        editor = Editor()
        self.assertEqual(editor.result["serverInfo"], {"name": "englishscript", "version": englishscript.__version__})
        for category, heading in englishscript.CATEGORY_HEADINGS.items():
            self.assertEqual(serving.heading(category), heading)
            self.assertTrue(Server.problem_text({"category": category, "message": "x"}, False).startswith(heading + "\n"))
        self.assertEqual(serving.heading("novelty"), "Novelty")
        with mock.patch.object(englishscript, "CATEGORY_HEADINGS", None):
            self.assertEqual(serving.heading("kinds"), "Kinds")

    def test_a_good_line_is_explained_though_another_line_is_wrong(self):
        text = ("A dragon has an age (number).\n"
                "A dragon is ancient when its age is at least 500.\n"
                "There is a dragon called Smaug whose age is 771.\n"
                "Say the number of dragns.\n"
                "If Smaug is ancient:\n  Say 1.\n")
        problems, notes = englishscript.lint(text, notes=True)
        self.assertEqual([p.line for p in problems if p.kind == "error"], [4])
        by_line = {}
        for number, note in notes:
            by_line.setdefault(number, []).append(note)
        self.assertIn(2, by_line)
        editor = Editor(PLAIN_HOVER)
        uri = editor.open(text)
        for number, said in by_line.items():
            hover = editor.request("textDocument/hover", {"textDocument": {"uri": uri},
                                                          "position": {"line": number - 1, "character": 0}})
            for note in said:
                self.assertIn(note, hover["contents"]["value"])
        wrong = editor.request("textDocument/hover", {"textDocument": {"uri": uri}, "position": {"line": 3, "character": 20}})
        self.assertIn(problems[0].message, wrong["contents"]["value"])

    def test_without_notes_from_the_linter_the_compiler_is_asked(self):
        text = ("A dragon has an age (number).\nA dragon is ancient when its age is at least 500.\n"
                "There is a dragon called Smaug whose age is 771.\nIf Smaug is ancient:\n  Say 1.\n")
        real = englishscript.lint

        def older(source, folder=None, name=None):  # a linter that knows neither `notes` nor `read`
            return real(source, folder, name)

        with mock.patch.object(englishscript, "lint", older):
            editor = Editor(PLAIN_HOVER)
            uri = editor.open(text)
            hover = editor.request("textDocument/hover", {"textDocument": {"uri": uri}, "position": {"line": 1, "character": 0}})
        notes = [note for number, note in englishscript.compile_source(text).notes if number == 2]
        self.assertTrue(notes)
        for note in notes:
            self.assertIn(note, hover["contents"]["value"])

    def test_a_chapter_that_is_open_and_unsaved_is_what_is_checked(self):
        editor = Editor()
        main = EXAMPLES / "almanac.english"
        text = main.read_text(encoding="utf-8") + "Say the moon of 3.\n"
        uri = editor.open(text, main.as_uri())
        self.assertEqual([d["severity"] for d in editor.published[uri]], [1])  # on the disk, no chapter has a "moon"
        chapter = EXAMPLES / "almanac" / "calendar.english"
        saved = chapter.read_text(encoding="utf-8")
        unsaved = (saved.replace("month title and weekday.", "month title, weekday and moon.")
                   + '\nTo work out the moon (text) of a month (number):\n  The answer is "moon {the month}".\n')
        chapter_uri = editor.open(saved, chapter.as_uri())
        self.assertEqual(len(editor.published[uri]), 1)
        editor.change(chapter_uri, unsaved)
        self.assertEqual(editor.published[chapter_uri], [])
        self.assertEqual(editor.published[uri], [], "told again, now that the chapter it uses shares a moon")
        found = editor.request("textDocument/definition", editor.place(uri, "Say the moon of 3", 9))
        self.assertEqual(found["uri"], chapter_uri)
        self.assertEqual(cut(unsaved, found["range"]), "moon")
        after_the = {"textDocument": {"uri": uri}, "position": Text(text).position(text.index("moon of 3"))}
        self.assertIn("moon", [i["label"] for i in editor.request("textDocument/completion", after_the)])
        editor.notify("textDocument/didClose", {"textDocument": {"uri": chapter_uri}})
        self.assertEqual(len(editor.published[uri]), 1, "closed without saving: the file on the disk counts again")
        self.assertEqual(chapter.read_text(encoding="utf-8"), saved)

    def test_a_rename_sees_the_unsaved_chapter_too(self):
        editor = Editor()
        main = EXAMPLES / "almanac.english"
        text = main.read_text(encoding="utf-8")
        uri = editor.open(text, main.as_uri())
        chapter = EXAMPLES / "almanac" / "calendar.english"
        saved = chapter.read_text(encoding="utf-8")
        editor.open(saved.replace("month title and weekday.", "month title, weekday and moon.")
                    + '\nTo work out the moon (text) of a month (number):\n  The answer is "new".\n', chapter.as_uri())
        where = editor.place(uri, "Let the year be", 9)
        refused = editor.answer("textDocument/rename", {**where, "newName": "moon"})
        self.assertEqual(refused["error"]["code"], serving.REQUEST_FAILED)  # in use, in the chapter as it is open
        edits = editor.request("textDocument/rename", {**where, "newName": "annum"})["changes"][uri]
        self.assertEqual(apply(text, edits), renaming.rename(text, "year", "annum", folder=EXAMPLES))


class Pipes(unittest.TestCase):
    def test_frames(self):
        out = io.BytesIO()
        serving.write_message(out, {"jsonrpc": "2.0", "method": "x", "params": {"text": "héllo 🐉"}})
        raw = out.getvalue()
        head, _, body = raw.partition(b"\r\n\r\n")
        self.assertEqual(head, b"Content-Length: %d" % len(body))
        self.assertEqual(json.loads(serving.read_message(io.BytesIO(raw))), {"jsonrpc": "2.0", "method": "x",
                                                                           "params": {"text": "héllo 🐉"}})
        self.assertIsNone(serving.read_message(io.BytesIO(b"")))
        self.assertIsNone(serving.read_message(io.BytesIO(b"Content-Length: 10\r\n\r\n{}")))  # cut short
        with self.assertRaises(serving.BadFrame):
            serving.read_message(io.BytesIO(b"Content-Type: text/plain\r\n\r\n{}"))
        with self.assertRaises(serving.BadFrame):
            serving.read_message(io.BytesIO(b"Content-Length: many\r\n\r\n{}"))
        both = io.BytesIO(b"Content-Length: 2\r\nContent-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n{}"
                          b"content-length:2\r\n\r\n[]")
        self.assertEqual([serving.read_message(both), serving.read_message(both), serving.read_message(both)],
                         [b"{}", b"[]", None])

    @staticmethod
    def frame(message):
        out = io.BytesIO()
        serving.write_message(out, message)
        return out.getvalue()

    def frames(self, raw):
        stream, found = io.BytesIO(raw), []
        while True:
            body = serving.read_message(stream)
            if body is None:
                return found
            found.append(json.loads(body))

    def test_the_loop_carries_on_after_what_it_cannot_read(self):
        sent = (self.frame({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"capabilities": {}}})
                + b"Content-Length: 9\r\n\r\n{not json"
                + b"Rubbish: yes\r\n\r\n"
                + self.frame({"jsonrpc": "2.0", "id": 2, "method": "no/such", "params": {}})
                + self.frame({"jsonrpc": "2.0", "id": 3, "method": "shutdown"})
                + self.frame({"jsonrpc": "2.0", "method": "exit"})
                + self.frame({"jsonrpc": "2.0", "id": 4, "method": "shutdown"}))
        logged, out = [], io.BytesIO()
        status = serving.serve(Server(log=logged.append), io.BytesIO(sent), out)
        answers = self.frames(out.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual([a.get("id") for a in answers], [1, None, 2, 3])  # nothing after "exit"
        self.assertEqual(answers[1]["error"]["code"], serving.PARSE_ERROR)
        self.assertEqual(answers[2]["error"]["code"], serving.METHOD_NOT_FOUND)
        self.assertEqual(answers[3]["result"], None)
        self.assertEqual(len(logged), 2)
        self.assertEqual(serving.serve(Server(log=logged.append), io.BytesIO(sent[:40]), io.BytesIO()), 1)  # the pipe closed

    def test_a_real_exchange_over_pipes(self):
        process = subprocess.Popen([sys.executable, "-m", "englishscript.server"], cwd=ROOT, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        arrived = queue.Queue()

        def listen():
            while True:
                try:
                    body = serving.read_message(process.stdout)
                except Exception as error:  # noqa: BLE001 - whatever it is, the test should see it
                    arrived.put(error)
                    return
                arrived.put(None if body is None else json.loads(body.decode("utf-8")))
                if body is None:
                    return

        def errors_of(pipe, into):
            into.append(pipe.read())

        said = []
        threads = [threading.Thread(target=listen, daemon=True),
                   threading.Thread(target=errors_of, args=(process.stderr, said), daemon=True)]
        for thread in threads:
            thread.start()

        def send(message):
            process.stdin.write(self.frame(message))
            process.stdin.flush()

        def receive():
            try:
                message = arrived.get(timeout=60)
            except queue.Empty:
                self.fail("the server did not answer in a minute")
            self.assertIsInstance(message, dict, message)
            return message

        try:
            send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                  "params": {"processId": None, "rootUri": None, "capabilities": {}}})
            answer = receive()
            self.assertEqual(answer["id"], 1)
            self.assertTrue(answer["result"]["capabilities"]["hoverProvider"])
            send({"jsonrpc": "2.0", "method": "initialized", "params": {}})

            text = Diagnostics.BAD
            uri = (ROOT / "untitled 🐉.english").as_uri()
            send({"jsonrpc": "2.0", "method": "textDocument/didOpen",
                  "params": {"textDocument": {"uri": uri, "languageId": "englishscript", "version": 1, "text": text}}})
            published = receive()
            self.assertEqual(published["method"], "textDocument/publishDiagnostics")
            self.assertEqual(published["params"]["uri"], uri)
            self.assertEqual(published["params"]["version"], 1)
            expected = lint(text, ROOT)
            self.assertEqual(len(published["params"]["diagnostics"]), len(expected))
            self.assertEqual([d["range"]["start"]["line"] for d in published["params"]["diagnostics"]],
                             [p["line"] - 1 for p in expected])
            self.assertEqual([d["severity"] for d in published["params"]["diagnostics"]],
                             [2 if p["kind"] == "warning" else 1 for p in expected])

            send({"jsonrpc": "2.0", "id": 2, "method": "textDocument/documentSymbol",
                  "params": {"textDocument": {"uri": uri}}})
            answer = receive()
            self.assertEqual(answer["id"], 2)
            self.assertEqual([s["name"] for s in answer["result"]], ["dragon", "Smaug", "spare"])

            send({"jsonrpc": "2.0", "method": "textDocument/didClose", "params": {"textDocument": {"uri": uri}}})
            self.assertEqual(receive()["params"], {"uri": uri, "diagnostics": []})

            send({"jsonrpc": "2.0", "id": 3, "method": "shutdown"})
            self.assertEqual(receive(), {"jsonrpc": "2.0", "id": 3, "result": None})
            send({"jsonrpc": "2.0", "method": "exit"})
            self.assertEqual(process.wait(timeout=60), 0)
            self.assertIsNone(arrived.get(timeout=60))  # and its output ended
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            for thread in threads:
                thread.join(timeout=10)
            for pipe in (process.stdin, process.stdout, process.stderr):
                pipe.close()
        self.assertEqual(b"".join(said).strip(), b"", "nothing was logged")


if __name__ == "__main__":
    unittest.main()

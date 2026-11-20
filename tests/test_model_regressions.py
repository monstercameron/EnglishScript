import base64
import json
import os
import tempfile
import unittest
from urllib.error import HTTPError
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

from englishscript import EnglishError, compile_source, models
from englishscript.runtime import read_image


class ModelRegressions(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)

    def test_chapter_meanings_are_part_of_a_cached_judgment(self):
        for chapter, verb, meaning in [("east", "alpha", "hot"), ("west", "beta", "cold")]:
            (self.folder / f"{chapter}.english").write_text(
                f'This chapter shares only {verb}.\nA tone is one of red or blue.\n'
                f'For a tone, red means "{meaning}".\nTo {verb}:\n'
                '  Judge "Which?" about "mail" and let the pick (tone) be the verdict.\n  Say the pick.\n')
        program = compile_source("Use the east chapter.\nUse the west chapter.\nAlpha.\nBeta.\nAlpha.", self.folder)
        calls = []
        def judge(q, state, choices, meanings):
            calls.append(meanings["red"])
            return {"red": int(meanings["red"] == "hot"), "blue": int(meanings["red"] == "cold")}
        out = []
        program.run(out.append, judge=judge)
        self.assertEqual((out, calls), (["red", "blue", "red"], ["hot", "cold"]))

    def test_batch_dependencies_use_resolved_multiword_names(self):
        p = compile_source('Judge "A" about "x" and let the risk score (percent) be the chance.\n'
                           'Judge "B {the risk   score}" about "x" and let the y (percent) be the chance.\nSay the y.')
        calls = []
        def judges(requests):
            calls.append([r["question"] for r in requests])
            return [.7] * len(requests)
        out = []
        p.run(out.append, judges=judges)
        self.assertEqual((calls, out), ([["A"], ["B 70%"]], ["70%"]))

    def test_positional_testing_suppresses_writes(self):
        target = self.folder / "side-effect"
        p = compile_source(f'Write "test" to the file "{target.as_posix()}".')
        p.run(print, None, None, None, None, True)
        self.assertFalse(target.exists())

    def test_single_named_and_batched_grades_use_ordered_scores(self):
        sent = []
        def send(body):
            sent.append([q["type"] for q in body["questions"].values()])
            return {"answers": {k: ({"type": "score", "probabilities": {"0": 0, "1": 1}}
                                    if q["type"] == "score" else {"noul": .5})
                                for k, q in body["questions"].items()}}
        jev = models.Jev(send=send)
        p = compile_source('A level is one of low or high.\n'
                           'To work out the rating (level) of a note (text), grade "Named?".\n'
                           'Say the rating of "x".\n'
                           'Judge "Alone?" about "x" and let solo (level) be the grade.\nSay solo.\n'
                           'Judge "Grouped?" about "x" and let grouped (level) be the grade.\n'
                           'Judge "Other?" about "x" and let other (percent) be the chance.\nSay grouped.')
        out = []
        p.run(out.append, judge=jev.judge, judges=jev.judges)
        self.assertEqual((out, sent), (["high"] * 3, [["score"], ["score"], ["score", "noul"]]))

    def test_record_and_replay_preserve_failures_and_prior_answers(self):
        p = compile_source('Try:\n  Judge "A" about "mail" and let x (percent) be the chance.\n'
                           '  Judge "B" about "mail" and let y (percent) be the chance.\nIf that fails:\n'
                           '  Say whether (the problem is a bad reply).\n'
                           '  Judge "A" about "mail" and let z (percent) be the chance.\n  Say z.\n'
                           '  Judge "B" about "mail" and let fresh (percent) be the chance.\n  Say fresh.')
        path = self.folder / "tape"
        for spec in (f"record:{path}:person", f"replay:{path}"):
            pair = models.connect(spec)
            out = []
            with patch("builtins.input", side_effect=["40%", "invalid", "85%"]) as prompted, redirect_stdout(StringIO()):
                p.run(out.append, judge=pair[1], judges=pair.judges)
            self.assertEqual(out, ["yes", "40%", "85%"])
            self.assertEqual(prompted.call_count, 3 if spec.startswith("record") else 0)

    def test_recording_missing_writer_preserves_no_model_on_replay(self):
        p = compile_source('Try:\n  Ask the model "Q" and let the gist (text) be the reply.\n'
                           'If that fails:\n  Say whether (the problem is no model).')
        path = self.folder / "answers"
        for spec in (f"record:{path}:jev", f"replay:{path}"):
            pair = models.connect(spec)
            out = []
            p.run(out.append, model=pair[0])
            self.assertEqual(out, ["yes"])

    def test_replay_matches_typed_questions_after_reordering(self):
        a = 'Ask the model "Q" and let colour (text) be the reply.\n'
        b = 'Ask the model "Q" and let count (number) be the reply.\n'
        path = self.folder / "tape"
        recorder = models.Transcript(path, (lambda q, s, shape, c: "red" if shape["type"] == "text" else "7", None))
        compile_source(a + b).run(model=recorder.model)
        out = []
        compile_source(b + a + 'Say "{colour} {count}".').run(out.append, model=models.Transcript(path).model)
        self.assertEqual(out, ["red 7"])

    def test_human_answers_multiword_choices_grades_and_lists(self):
        responses = iter(["very cross 80%", "calm=45%, very cross=10%, furious=45%", "first", "second", ""])
        person = models.Person(ask=lambda _: next(responses), say=lambda _: None)
        p = compile_source('A mood is one of calm, very cross or furious.\n'
                           'Judge "Mood?" about "x" and let first (mood) be the verdict.\n'
                           'Judge "Mood?" about "x" and let second (mood) be the grade.\n'
                           'Ask the model "Lines?" and let notes (list of text) be the reply.\n'
                           'Say "{first} / {second}".\nSay the notes joined with ", ".')
        out = []
        p.run(out.append, model=person.model, judge=person.judge)
        self.assertEqual(out, ["very cross / very cross", "first, second"])

    def test_image_questions_and_replay_use_content_identity(self):
        image = Path(__file__).resolve().parents[1] / "docs/assets/triangle-gpu.png"
        path = self.folder / "tape"
        sent = []
        def send(body):
            sent.append(body)
            return {"answers": {"q0": {"noul": .9}}}
        j = models.Jev(send=send)
        transcript = models.Transcript(path, (None, j.judge))
        p = compile_source(f'Judge "Triangle?" about the image in the file "{image.as_posix()}" '
                           'and let p (percent) be the chance.\nSay p.')
        out = []
        p.run(out.append, judge=transcript.judge)
        p.run(out.append, judge=models.Transcript(path).judge)
        body, = sent
        self.assertEqual(out, ["90%", "90%"])
        self.assertEqual(base64.b64decode(body["assets"][body["state"]["image"]]["data_base64"]), image.read_bytes())
        tape = path.read_text()
        self.assertIn("sha256", tape)
        self.assertNotIn("data_base64", tape)
        with self.assertRaises(EnglishError):
            read_image(path)

    def test_luna_writer_uses_the_responses_api_with_an_image(self):
        image = read_image(Path(__file__).resolve().parents[1] / "docs/assets/triangle-gpu.png")
        response = BytesIO(json.dumps({"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": "triangle"}]}]}).encode())
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}), \
                patch("urllib.request.urlopen", return_value=response) as post:
            pair = models.connect("jev+openai")
            self.assertEqual(pair[0]("Shape?", image, {"type": "text"}, None), "triangle")
        request = post.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual(json.loads(request.data)["model"], "gpt-6-luna")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-only")
        self.assertTrue(json.loads(request.data)["input"][0]["content"][1]["image_url"].startswith("data:image/png;"))

    def test_luna_quota_failure_is_recoverable_and_never_changes_models(self):
        body = BytesIO(b'{"error":{"code":"credit_balance_exhausted"}}')
        error = HTTPError("https://api.openai.com/v1/responses", 429, "Too Many Requests", {}, body)
        source = ('Try:\n  Ask the model "Q" and let the gist (text) be the reply.\n'
                  'If that fails:\n  Say the problem.')
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-only"}), \
                patch("urllib.request.urlopen", side_effect=error) as post:
            out = []
            compile_source(source).run(out.append, model=models.connect("openai:gpt-6-luna")[0])
        self.assertEqual(out, ["The OpenAI project has no available API credit."])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(json.loads(post.call_args.args[0].data)["model"], "gpt-6-luna")

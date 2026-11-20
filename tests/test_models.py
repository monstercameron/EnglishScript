"""The listeners that answer when a program asks a model (englishscript/models.py).

None of these reaches a real service. The Claude and Jev listeners are given
stand-ins for the network, which return what those services' documentation
says they return.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from englishscript import EnglishError
from englishscript import models

TEXT = {"type": "text", "choices": None, "items": None, "optional": False}
NUMBER = {"type": "number", "choices": None, "items": None, "optional": False}
TEAM = {"type": "choice", "choices": ["returns", "billing"], "items": None, "optional": True}
LINES = {"type": "list", "choices": None, "items": "text", "optional": False}


class APerson(unittest.TestCase):
    def test_a_person_answers_as_the_model_would(self):
        asked, shown = [], []
        person = models.Person(ask=lambda prompt: (asked.append(prompt), "42")[1], say=shown.append)
        self.assertEqual(person.model("How many?", "a dragon called Smaug\nage: 771", NUMBER, None), "42")
        self.assertIn("[You are the model] How many?", asked[0])
        self.assertIn("a number written in digits", asked[0])
        self.assertEqual(shown, ["The model is asked about this:", "    a dragon called Smaug", "    age: 771"])
        person.model("How many?", None, NUMBER, "it was not a number")
        self.assertIn("(That could not be read: it was not a number)", shown)

    def test_a_person_judges_with_a_percentage(self):
        person = models.Person(ask=lambda prompt: "80%", say=lambda line: None)
        self.assertAlmostEqual(person.judge("Is it urgent?", "text", None, None), 0.8)
        person = models.Person(ask=lambda prompt: "billing 70%", say=lambda line: None)
        verdict = person.judge("Which team?", "text", ["returns", "billing", "post"], {})
        self.assertAlmostEqual(verdict["billing"], 0.7)
        self.assertAlmostEqual(verdict["returns"] + verdict["post"], 0.3)
        for bad in ("lots", "120%", None):
            person = models.Person(ask=lambda prompt, bad=bad: bad, say=lambda line: None)
            with self.subTest(bad), self.assertRaises(EnglishError) as caught:
                person.judge("Is it urgent?", None, None, None)
            self.assertTrue(caught.exception.recoverable)
        person = models.Person(ask=lambda prompt: "shipping", say=lambda line: None)
        with self.assertRaises(EnglishError):
            person.judge("Which team?", None, ["returns", "billing"], {})


class Transcripts(unittest.TestCase):
    def test_what_is_recorded_is_replayed_and_nothing_else_is_asked(self):
        canned = models.Canned(replies=["a short note", "7"], verdicts=[{"returns": 0.9, "billing": 0.1}])
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "answers.txt")
            recorder = models.Transcript(path, (canned.model, canned.judge))
            self.assertEqual(recorder.model("Sum it up.", "the letter", TEXT, None), "a short note")
            self.assertEqual(recorder.judge("Which team?", "the letter", ["returns", "billing"], {}), {"returns": 0.9, "billing": 0.1})
            self.assertEqual(recorder.model("How many?", None, NUMBER, None), "7")
            lines = Path(path).read_text(encoding="utf-8").splitlines()
            self.assertEqual([json.loads(line)["kind"] for line in lines], ["ask", "judge", "ask"])
            player = models.Transcript(path)
            # Answers are found by question and state, not by order.
            self.assertEqual(player.model("How many?", None, NUMBER, None), "7")
            self.assertEqual(player.judge("Which team?", "the letter", ["returns", "billing"], {})["returns"], 0.9)
            self.assertEqual(player.model("Sum it up.", "the letter", TEXT, None), "a short note")
            with self.assertRaises(EnglishError):
                player.model("Sum it up.", "another letter", TEXT, None)

    def test_a_missing_or_spoilt_file_is_a_problem(self):
        with self.assertRaises(EnglishError):
            models.Transcript(os.path.join(tempfile.gettempdir(), "no such file here.txt"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "spoilt.txt"
            path.write_text("this is not what was written\n", encoding="utf-8")
            with self.assertRaises(EnglishError):
                models.Transcript(str(path))


class Claude(unittest.TestCase):
    """The Claude listener, against a stand-in for the anthropic package."""

    def stand_in(self, reply=None, stop="end_turn", error=None):
        sent = []

        def create(**request):
            sent.append(request)
            if error is not None:
                raise error
            blocks = [] if reply is None else [SimpleNamespace(type="text", text=json.dumps(reply))]
            return SimpleNamespace(stop_reason=stop, content=blocks)

        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        return client, sent

    def test_a_reply_is_asked_for_in_a_typed_form(self):
        client, sent = self.stand_in({"reply": "returns"})
        listener = models.Claude(client=client)
        self.assertEqual(listener.model("Which team?", "the letter", TEAM, None), "returns")
        request = sent[0]
        self.assertEqual(request["model"], "claude-opus-5-5")
        schema = request["output_config"]["format"]["schema"]
        self.assertEqual(schema["properties"]["reply"]["enum"], ["returns", "billing", "nothing"])
        self.assertFalse(schema["additionalProperties"])
        self.assertIn("It is about this:\nthe letter", request["messages"][0]["content"])
        self.assertEqual(request["fallbacks"], "default")

    def test_a_list_comes_back_one_item_to_a_line(self):
        client, _ = self.stand_in({"reply": ["eggs", "flour"]})
        self.assertEqual(models.Claude(client=client).model("What is needed?", None, LINES, None), "eggs\nflour")

    def test_a_complaint_is_passed_on_when_asking_again(self):
        client, sent = self.stand_in({"reply": "12"})
        models.Claude(client=client).model("How many?", None, NUMBER, '"twelve" is not a number')
        self.assertIn('"twelve" is not a number', sent[0]["messages"][0]["content"])

    def test_a_refusal_or_an_answer_cut_short_is_no_reply(self):
        for stop in ("refusal", "max_tokens"):
            client, _ = self.stand_in({"reply": "x"}, stop=stop)
            self.assertIsNone(models.Claude(client=client).model("Q", None, TEXT, None), stop)

    def test_a_failure_to_reach_it_is_a_problem_a_program_can_recover_from(self):
        failure = Exception("connection reset")
        failure.status_code = 429
        client, _ = self.stand_in(error=failure)
        with self.assertRaises(EnglishError) as caught:
            models.Claude(client=client).model("Q", None, TEXT, None)
        self.assertTrue(caught.exception.recoverable)
        self.assertIn("too many questions", caught.exception.message)

    def test_it_can_estimate_a_judgement(self):
        client, sent = self.stand_in({"returns": 0.8, "billing": 0.2})
        verdict = models.Claude(client=client).judge("Which team?", "the letter", ["returns", "billing"], {"returns": "sending back"})
        self.assertEqual(verdict, {"returns": 0.8, "billing": 0.2})
        self.assertIn("- returns: sending back", sent[0]["messages"][0]["content"])
        client, _ = self.stand_in({"probability": 0.25})
        self.assertEqual(models.Claude(client=client).judge("Is it urgent?", None, None, None), 0.25)


class ClaudeJudgingSeveral(unittest.TestCase):
    def test_several_judgements_are_one_call_with_one_property_each(self):
        sent = []

        def create(**request):
            sent.append(request)
            reply = {"q1": {"returns": 0.6, "billing": 0.4}, "q2": 0.3}
            return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(reply))])

        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
        answers = models.Claude(client=client).judges([
            {"question": "Which team?", "state": "the letter", "choices": ["returns", "billing"], "meanings": {}, "scale": False},
            {"question": "Is the customer angry?", "state": "the letter", "choices": None, "meanings": None, "scale": False},
        ])
        self.assertEqual(answers, [{"returns": 0.6, "billing": 0.4}, 0.3])
        self.assertEqual(len(sent), 1)
        schema = sent[0]["output_config"]["format"]["schema"]
        self.assertEqual(sorted(schema["properties"]), ["q1", "q2"])
        self.assertIn("Every question is about this:\nthe letter", sent[0]["messages"][0]["content"])


class Jev(unittest.TestCase):
    """The Jev listener, against a stand-in for TypeSafe's service."""

    def test_a_chance_is_asked_as_a_yes_or_no_question(self):
        sent = []
        jev = models.Jev(send=lambda body: (sent.append(body), {"answers": {"q0": {"type": "noul", "noul": 0.93}}})[1])
        self.assertEqual(jev.judge("Does the customer want a person?", "Please, a human.", None, None), 0.93)
        self.assertEqual(sent[0]["questions"]["q0"], {"type": "noul", "instructions": "Does the customer want a person?"})
        self.assertEqual((sent[0]["model"], sent[0]["state"]), ("jev-latest", "Please, a human."))

    def test_a_verdict_is_asked_as_a_choice_with_each_meaning(self):
        sent = []
        reply = {"answers": {"q0": {"type": "choice", "choice": "returns", "confidence": 0.6,
                                   "probabilities": {"returns": 0.8, "billing": 0.2}}}}
        jev = models.Jev(send=lambda body: (sent.append(body), reply)[1])
        verdict = jev.judge("Which team?", "the letter", ["returns", "billing"], {"returns": "sending something back"})
        self.assertEqual(verdict, {"returns": 0.8, "billing": 0.2})
        # Jev wants a description of every option: a choice with no meaning given stands for itself.
        self.assertEqual(sent[0]["questions"]["q0"]["criteria"], {"returns": "sending something back", "billing": "billing"})

    def test_several_questions_about_one_state_go_in_one_request(self):
        sent = []

        def send(body):
            sent.append(body)
            answers = {}
            for key, question in body["questions"].items():
                if question["type"] == "noul":
                    answers[key] = {"type": "noul", "noul": 0.2}
                elif question["type"] == "score":
                    answers[key] = {"type": "score", "score": 1.0, "probabilities": {"0": 0.45, "1": 0.1, "2": 0.45}}
                else:
                    answers[key] = {"type": "choice", "probabilities": {"returns": 0.7, "billing": 0.3}}
            return {"answers": answers}

        jev = models.Jev(send=send)
        requests = [
            {"question": "Which team?", "state": "the letter", "choices": ["returns", "billing"], "meanings": {}, "scale": False},
            {"question": "Is the customer angry?", "state": "the letter", "choices": None, "meanings": None, "scale": False},
            {"question": "How urgent is it?", "state": "the letter", "choices": ["low", "middle", "high"], "meanings": {}, "scale": True},
            {"question": "Is it spam?", "state": "another letter", "choices": None, "meanings": None, "scale": False},
        ]
        answers = jev.judges(requests)
        self.assertEqual(len(sent), 2)  # one request for each state
        self.assertEqual(sorted(sent[0]["questions"]), ["q0", "q1", "q2"])
        self.assertEqual(sent[0]["questions"]["q2"], {"type": "score", "instructions": "How urgent is it?",
                                                      "criteria": ["low", "middle", "high"]})
        self.assertEqual(answers[0], {"returns": 0.7, "billing": 0.3})
        self.assertEqual(answers[1], 0.2)
        # A Score's probabilities come back keyed by level number, and go out keyed by choice.
        self.assertEqual(answers[2], {"low": 0.45, "middle": 0.1, "high": 0.45})
        self.assertEqual(answers[3], 0.2)

    def test_an_answer_in_another_form_is_a_problem(self):
        jev = models.Jev(send=lambda body: {"something": "else"})
        with self.assertRaises(EnglishError):
            jev.judge("Q", None, None, None)

    def test_without_a_key_it_says_so(self):
        saved = os.environ.pop("TYPESAFE_API_KEY", None)
        try:
            with self.assertRaises(EnglishError) as caught:
                models.Jev().judge("Q", None, None, None)
            self.assertIn("TYPESAFE_API_KEY", caught.exception.message)
        finally:
            if saved is not None:
                os.environ["TYPESAFE_API_KEY"] = saved


class Connecting(unittest.TestCase):
    def test_each_spec_gives_the_listeners_it_names(self):
        model, judge = models.connect("person")
        self.assertIsNotNone(model)
        self.assertIsNotNone(judge)
        model, judge = models.connect("jev")
        self.assertIsNone(model)  # Jev writes no text
        self.assertIsNotNone(judge)
        model, judge = models.connect("jev+anthropic")
        self.assertEqual(model.__self__.__class__.__name__, "Claude")
        self.assertEqual(judge.__self__.__class__.__name__, "Jev")
        model, _ = models.connect("anthropic:claude-haiku-5-5")
        self.assertEqual(model.__self__.name, "claude-haiku-5-5")

    def test_the_judge_and_its_way_of_judging_several_go_together(self):
        listeners = models.connect("jev+anthropic")
        model, judge = listeners  # still a pair
        self.assertEqual(judge.__self__.__class__.__name__, "Jev")
        self.assertEqual(listeners.judges.__self__.__class__.__name__, "Jev")
        listeners = models.connect("anthropic+jev")
        self.assertEqual(listeners.judges.__self__.__class__.__name__, "Claude")
        # A listener that is asked one question at a time is given a way to be asked several.
        canned = models.Canned(verdicts=[0.1, 0.9])
        judges = models.one_by_one(canned.judge)
        self.assertEqual(judges([{"question": "a", "state": None, "choices": None, "meanings": None, "scale": False}] * 2),
                         [0.1, 0.9])
        self.assertIsNone(models.one_by_one(None))

    def test_record_and_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / "answers.txt")  # on Windows this has a colon of its own
            model, judge = models.connect(f"record:{path}:jev+person")
            self.assertEqual(model.__self__.__class__.__name__, "Transcript")
            self.assertEqual(model.__self__.path, path)
            Path(path).write_text("", encoding="utf-8")
            model, _ = models.connect(f"replay:{path}")
            self.assertEqual(model.__self__.path, path)

    def test_a_spec_that_names_nothing_known_is_refused(self):
        for spec in ("", "gpt", "record:answers.txt", "record:answers.txt:nobody"):
            with self.subTest(spec), self.assertRaises(EnglishError):
                models.connect(spec)

    def test_the_compiler_does_not_load_this_module(self):
        import subprocess
        import sys

        code = "import sys, englishscript; englishscript.compile_source('Say 1.'); print('englishscript.models' in sys.modules)"
        found = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                               cwd=Path(__file__).resolve().parent.parent)
        self.assertEqual(found.stdout.strip(), "False", found.stderr)


if __name__ == "__main__":
    unittest.main()

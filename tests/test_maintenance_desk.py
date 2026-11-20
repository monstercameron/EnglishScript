import json
import os
import tempfile
import unittest
from pathlib import Path
from io import BytesIO
from unittest.mock import patch

from englishscript import compile_file, models


APP = Path(__file__).resolve().parents[1] / "apps" / "maintenance"


class MaintenanceDesk(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.program = compile_file(APP / "desk.english")

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(tmp.name)

    def run_inbox(self, inbox, **listeners):
        Path("inbox.txt").write_text(inbox, encoding="utf-8")
        lines = []
        world = self.program.run(lines.append, **listeners)
        self.assertEqual(world.examples, 3)
        self.assertEqual(lines, [Path("shift-plan.txt").read_text(encoding="utf-8")])
        return lines[0]

    def test_sample_replays_the_same_shift_and_handoffs(self):
        def replay():
            pair = models.connect("replay:" + str(APP / "demo.jsonl"))
            return self.run_inbox((APP / "inbox.txt").read_text(), model=pair[0], judge=pair[1], judges=pair.judges)
        plan = replay()
        self.assertEqual(plan, replay())
        self.assertIn("Garden room | $65 | plumbing | prompt | Scheduled", plan)
        self.assertIn("Trade opinions disagree", plan)
        self.assertIn("Wait for next shift budget", plan)
        self.assertIn("Supervisor approval required", plan)
        self.assertIn("A display shelf sags, and other shelving is available.", plan)
        self.assertTrue(plan.endswith("Scheduled 3 of 6. Reserved $260. Remaining $40. Rejected 0."))

    def test_offline_does_not_allocate_and_preserves_original_reports(self):
        plan = self.run_inbox("Lobby|40|Tap drips.\nLab|201|New shelves.")
        self.assertIn("Assessment unavailable; supervisor review\n  Tap drips.", plan)
        self.assertIn("Supervisor approval required for estimates over $200", plan)
        self.assertTrue(plan.endswith("Scheduled 0 of 2. Reserved $0. Remaining $300. Rejected 0."))

    def test_intake_recovers_per_line_and_keeps_audit_identifiers(self):
        plan = self.run_inbox("missing fields\n\nRoom|-1|No\nRoom|.25|Wrong number\nRoom|0.005|Too precise\n"
                              " |4|Blank site\nHall|15.75|Lamp out\n")
        self.assertIn("Rejected M-1:", plan)
        self.assertIn("Rejected M-4: the estimate must be an amount in whole cents", plan)
        self.assertIn("M-6 | Hall | $15.75", plan)
        self.assertTrue(plan.endswith("Scheduled 0 of 1. Reserved $0. Remaining $300. Rejected 5."))

    def test_priority_precedes_input_order_and_trade_capacity_is_two(self):
        def judge(q, state, choices, meanings):
            pick = ("lighting" if "lighting" in choices else "urgent" if state == "Third" else "routine")
            return {c: int(c == pick) for c in choices}
        plan = self.run_inbox("A|100|First\nB|100|Second\nC|100|Third", judge=judge)
        self.assertIn("M-2 | B | $100 | lighting | routine | Wait for next crew slot", plan)
        self.assertIn("M-3 | C | $100 | lighting | urgent | Scheduled\n  Third", plan)
        self.assertIn("Reserved $200. Remaining $100", plan)

    def test_inconclusive_below_half_does_not_call_writer(self):
        def judge(q, state, choices, meanings):
            if "lighting" in choices:
                return {"lighting": .4, "plumbing": .3, "joinery": .3}
            return {"routine": 1, "prompt": 0, "urgent": 0}
        def writer(*args):
            self.fail("a low-confidence judgment should go directly to a supervisor")
        plan = self.run_inbox("Lobby|50|Report", judge=judge, model=writer)
        self.assertIn("Trade uncertain; supervisor review", plan)

    def test_supervisor_approval_precedes_billable_calls(self):
        def unexpected(*args):
            self.fail("an over-cap estimate must bypass models")
        plan = self.run_inbox("Roof|200.01|Replace shelves", judge=unexpected, model=unexpected)
        self.assertIn("Supervisor approval required", plan)

    def test_luna_outage_at_confidence_boundaries(self):
        calls = []
        def judge(q, state, choices, meanings):
            if "lighting" in choices:
                chance = .85 if state == "Ceiling lamp" else .50
                return {"lighting": chance, "plumbing": 1-chance, "joinery": 0}
            return {"routine": 1, "prompt": 0, "urgent": 0}
        def writer(q, state, shape, complaint):
            calls.append(shape["type"])
            raise models.problem("The OpenAI project has no available API credit.")
        plan = self.run_inbox("Hall|200|Ceiling lamp\nDesk|5|Loose fixture", model=writer, judge=judge)
        self.assertEqual(calls, ["text", "choice"])
        self.assertIn("Hall | $200 | lighting | routine | Scheduled", plan)
        self.assertIn("Original report. Handoff unavailable", plan)
        self.assertIn("Second opinion unavailable; supervisor review", plan)
        self.assertIn("Scheduled 1 of 2. Reserved $200.", plan)

    def test_full_shift_through_jev_and_luna_wire_formats(self):
        attempts = []
        def http(request, timeout):
            body = json.loads(request.data)
            if request.full_url == models.JEV_ENDPOINT:
                self.assertEqual(request.get_header("Authorization"), "Bearer test-judge")
                self.assertEqual([q["type"] for q in body["questions"].values()], ["choice", "score"])
                response = {"answers": {
                    "q0": {"type": "choice", "probabilities": {"lighting": .7, "plumbing": .25, "joinery": .05}},
                    "q1": {"type": "score", "probabilities": {"0": .05, "1": .05, "2": .9}}}}
            else:
                self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
                self.assertEqual(request.get_header("Authorization"), "Bearer test-writer")
                self.assertEqual(body["model"], "gpt-6-luna")
                self.assertIs(body["store"], False)
                attempts.append(body)
                reply = ["not a trade", "lighting", "Reading room lamp reported out."][len(attempts)-1]
                response = {"status": "completed", "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": reply}]}]}
            return BytesIO(json.dumps(response).encode())
        pair = models.connect("jev+openai:gpt-6-luna")
        with patch.dict(os.environ, {"TYPESAFE_API_KEY": "test-judge", "OPENAI_API_KEY": "test-writer"}), \
                patch("urllib.request.urlopen", side_effect=http):
            plan = self.run_inbox("Library|80|Lamp out", model=pair[0], judge=pair[1], judges=pair.judges)
        self.assertEqual(len(attempts), 3)
        self.assertIn("previous reply", attempts[1]["instructions"])
        self.assertIn("lighting | urgent | Scheduled\n  Reading room lamp reported out.", plan)
        self.assertIn("Reserved $80. Remaining $220.", plan)

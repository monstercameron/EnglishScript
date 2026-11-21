import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from englishscript import compile_file

RED = Path(__file__).resolve().parents[1] / "docs" / "red"


def fake_value(kind):
    return "" if kind is str else "walk" if kind == "mode" else 0


def fake_named(bridge):
    return {name: types.SimpleNamespace(fields={field: fake_value(kind) for field, kind in fields.items()})
            for name, fields in bridge.CONTRACT.items()}


class RedBridgeContract(unittest.IsolatedAsyncioTestCase):
    def load_bridge(self, js):
        spec = importlib.util.spec_from_file_location("contract_bridge", RED / "bridge.py")
        bridge = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"js": js}):
            spec.loader.exec_module(bridge)
        return bridge

    async def test_chapters_satisfy_contract(self):
        bridge = self.load_bridge(types.SimpleNamespace())
        world = await compile_file(RED / "main.english").run_async(out=lambda _: None)
        bridge.validate_contract(world)

    async def test_startup_reports_contract_failures(self):
        errors = []
        ready = []
        bridge = self.load_bridge(types.SimpleNamespace(redError=errors.append, redReady=lambda: ready.append(True)))
        world = types.SimpleNamespace(named=fake_named(bridge))
        bridge.validate_contract(world)

        class Program:
            async def run_async(self, out, model, on_world):
                on_world(world)

        with patch.object(bridge, "compile_file", return_value=Program()), patch.object(bridge.page, "use_remote_canvas"):
            del world.named["speaker"].fields["identity"]
            await bridge.start()
            self.assertEqual(errors.pop(), "Red bridge requires 'speaker.identity' (text).")
            world.named["speaker"].fields["identity"] = ""
            world.named["score"].fields["tempo"] = "fast"
            await bridge.start()
            self.assertEqual(errors.pop(), "Red bridge requires 'score.tempo' to be number; got str.")
            world.named["score"].fields["tempo"] = 144
            del world.named["talk"]
            await bridge.start()
        self.assertEqual(errors, ["Red bridge requires an object named 'talk'."])
        self.assertEqual(ready, [])

    async def test_contract_refuses_a_mode_the_page_does_not_know(self):
        bridge = self.load_bridge(types.SimpleNamespace())
        world = types.SimpleNamespace(named=fake_named(bridge))
        world.named["journey"].fields["mode"] = "wolk"
        with self.assertRaisesRegex(bridge.ContractError, "'journey.mode' to be a mode"):
            bridge.validate_contract(world)

    async def test_every_chapter_mode_is_published_as_the_page_mode(self):
        states = []
        bridge = self.load_bridge(types.SimpleNamespace(redState=lambda text: states.append(json.loads(text))))
        program = compile_file(RED / "main.english")
        self.assertEqual(set(program.compiler.choice_sets["mode"].displays), set(bridge.PAGE_MODES))
        bridge.world = await program.run_async(out=lambda _: None)
        journey = bridge.world.named["journey"].fields
        for mode, published in (("main menu", "menu"), ("trainer card", "card"), ("battle", "battle")):
            journey["mode"] = mode
            bridge.state()
            self.assertEqual(states[-1]["mode"], published)
        self.assertEqual((states[-1]["badge"], states[-1]["tm34"]), (0, 0))

    def test_companion_reply_is_capped_before_it_enters_the_world(self):
        states = []
        bridge = self.load_bridge(types.SimpleNamespace(redState=lambda text: states.append(json.loads(text))))
        world = types.SimpleNamespace(ended=False, event=lambda update: update(),
                                      named=fake_named(bridge))
        world.named["talk"].fields["phase"] = "waiting"
        bridge.world = world
        bridge.talk_session = bridge.talk_request = 1
        with patch.object(bridge.page, "sync"):
            bridge.talk_reply(1, 1, "Oak says hello. " * 400)
        talk = world.named["talk"].fields
        self.assertEqual(talk["command"], "reply")
        self.assertEqual(len(talk["transcript"]), bridge.REPLY_LIMIT)
        self.assertLessEqual(len(talk["wording"]), bridge.REPLY_LIMIT)
        self.assertEqual(len(states[-1]["talkRawReply"]), bridge.REPLY_LIMIT)
        self.assertEqual(states[-1]["effectCount"], 0)
        self.assertNotIn("effect count", states[-1])


if __name__ == "__main__":
    unittest.main()

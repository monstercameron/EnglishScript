import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from englishscript import compile_file
from englishscript.libraries import page

RED = Path(__file__).resolve().parents[1] / "docs" / "red"


class RedConversation(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.frames = []
        self.states = []
        js = types.SimpleNamespace(redFrame=lambda w, h, p: self.frames.append(bytes(p)),
                                   redState=lambda s: self.states.append(json.loads(s)))
        spec = importlib.util.spec_from_file_location("conversation_bridge", RED / "bridge.py")
        self.bridge = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"js": js}):
            spec.loader.exec_module(self.bridge)
        await compile_file(RED / "main.english").run_async(out=lambda _: None, on_world=self.bridge.remember)
        self.journey = self.bridge.world.named["journey"]
        self.journey.fields.update({"place": "Home", "column": 5, "row": 5, "facing": "north", "mode": "walk"})
        page.sync(self.bridge.world)

    async def test_talk_is_paginated_on_canvas_without_changing_journey(self):
        before = dict(self.journey.fields)
        self.bridge.talk_open()
        session = self.bridge.talk_session
        self.assertEqual(self.states[-1]["talkPerson"], "Mom")
        self.assertEqual(self.states[-1]["talkPhase"], "composing")
        result = json.loads(self.bridge.talk_ask(session, 1, "Pokemon"))
        self.assertEqual(result["person"], "Mom")
        self.assertTrue(result["identity"] and result["profile"] and result["voice"])
        self.bridge.talk_reply(session, 1, "A long reply has several words and continues across several pages for the trainer to read carefully.")
        first = self.frames[-1]
        self.assertTrue(self.states[-1]["talkHasMore"])
        self.bridge.talk_page(session)
        self.assertNotEqual(first, self.frames[-1])
        while self.states[-1]["talkHasMore"]:
            self.bridge.talk_page(session)
        self.bridge.talk_page(session)
        self.assertEqual(self.states[-1]["talkPhase"], "composing")
        self.bridge.talk_close(session)
        self.assertEqual(dict(self.journey.fields), before)
        self.assertEqual(self.states[-1]["talkPhase"], "closed")

    async def test_story_dialogue_is_restored_and_styled_reply_is_readable(self):
        self.bridge.act("a")
        self.assertEqual(self.journey.fields["mode"], "dialogue")
        before = dict(self.journey.fields)
        original = self.frames[-1]
        self.bridge.talk_open()
        session = self.bridge.talk_session
        self.assertEqual(self.states[-1]["talkPhase"], "composing")
        self.bridge.talk_ask(session, 1, "Hello")
        raw = "“Hello”—it’s café time…\n" + "Keep going! " * 180
        self.bridge.talk_reply(session, 1, raw)
        self.assertEqual(self.states[-1]["talkRawReply"], raw)
        self.assertTrue(self.bridge.world.named["talk"].fields["wording"].startswith("'Hello'-it's cafe time..."))
        self.assertEqual(len(self.bridge.world.named["talk"].fields["wording"]), 2000)
        self.bridge.talk_close(session)
        self.assertEqual(dict(self.journey.fields), before)
        self.assertEqual(self.frames[-1], original)

    async def test_counter_conversations_use_the_persons_actual_location(self):
        for place, column, row, facing, person, identity in [
            ("Viridian Center", 3, 3, "north", "Nurse", "Viridian Center:3,1:Nurse"),
            ("Viridian Mart", 2, 5, "west", "Clerk", "Viridian Mart:0,5:Clerk"),
        ]:
            self.journey.fields.update({"place": place, "column": column, "row": row, "facing": facing, "mode": "walk"})
            self.bridge.talk_open()
            session = self.bridge.talk_session
            self.assertEqual(self.states[-1]["talkPerson"], person)
            result = json.loads(self.bridge.talk_ask(session, 1, "Hello"))
            self.assertEqual(result["identity"], identity)
            self.assertTrue(result["profile"] and result["voice"])
            self.bridge.talk_close(session)

    async def test_empty_space_and_stale_replies_are_ignored(self):
        self.journey.fields["facing"] = "south"
        self.bridge.talk_open()
        self.assertEqual(self.states[-1]["talkPhase"], "closed")
        self.journey.fields["facing"] = "north"
        self.bridge.talk_open()
        old = self.bridge.talk_session
        self.bridge.talk_ask(old, 1, "Hello")
        self.bridge.talk_close(old)
        self.bridge.talk_open()
        current = self.bridge.talk_session
        self.bridge.talk_ask(current, 1, "Hello")
        self.bridge.talk_reply(old, 1, "stale")
        self.bridge.talk_reply(current, 2, "stale")
        self.assertEqual(self.bridge.world.named["talk"].fields["phase"], "waiting")
        self.bridge.talk_reply(current, 1, "Welcome")
        self.assertEqual(self.states[-1]["talkPage"], "Welcome")


if __name__ == "__main__":
    unittest.main()

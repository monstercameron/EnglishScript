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


def snapshot(world):
    state = {name: dict(world.named[name].fields) for name in ("journey", "controls", "stock", "combat")}
    for side in ("ally", "foe"):
        state["combat"][side] = dict(state["combat"][side].fields)
    return state


class RedReplay(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.frames = []
        self.states = []
        js = types.SimpleNamespace(redFrame=lambda width, height, pixels: self.frames.append(bytes(pixels)),
                                   redState=lambda state: self.states.append(json.loads(state)))
        spec = importlib.util.spec_from_file_location("red_bridge", RED / "bridge.py")
        self.bridge = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"js": js}):
            spec.loader.exec_module(self.bridge)
        self.program = compile_file(RED / "main.english")

    async def start_world(self):
        await self.program.run_async(out=lambda text: None, on_world=self.bridge.remember)
        page.sync(self.bridge.world)
        self.frames.clear()
        self.states.clear()

    async def test_replay_matches_ordinary_controls_and_final_pixels(self):
        actions = ["tick", "a", "a", "a", "a", "a", "down", "a", "a"]
        await self.start_world()
        self.assertEqual(self.bridge.world.named["journey"].fields["place"], "")
        for action in actions:
            self.bridge.act(action)
        expected = snapshot(self.bridge.world)
        pixels = self.frames[-1]
        await self.start_world()
        self.bridge.replay(json.dumps(actions))
        self.assertEqual(snapshot(self.bridge.world), expected)
        self.assertEqual(self.frames[-1], pixels)
        self.assertEqual(len(self.frames), 1)
        self.assertEqual(len(self.states), 1)

    async def test_rendering_restored_if_intermediate_action_fails(self):
        await self.start_world()
        with patch.object(self.bridge, "act", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                self.bridge.replay(json.dumps(["a", "b"]))
        self.assertEqual(self.bridge.world.named["controls"].fields["rendering"], 1)
        self.assertFalse(self.bridge.quiet)
        self.bridge.act("a")
        self.assertTrue(self.frames)

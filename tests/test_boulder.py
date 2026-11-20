import asyncio
import unittest
from pathlib import Path

from englishscript import compile_file
from englishscript.libraries import page


ENTRY = Path(__file__).resolve().parents[1] / "docs" / "boulder" / "main.english"


class BoulderReplay(unittest.IsolatedAsyncioTestCase):
    async def replay(self):
        requests = []
        world_ready = []
        frames = []
        waiting = asyncio.Event()
        reply = asyncio.get_running_loop().create_future()

        async def model(question, state, shape, complaint):
            requests.append((question, state, shape["type"], complaint))
            waiting.set()
            return await reply

        def on_world(world):
            page.use_remote_canvas(world, lambda serial, name, width, height, pixels:
                                   frames.append((name, width, height, pixels)))
            world_ready.append(world)

        task = asyncio.create_task(compile_file(ENTRY).run_async(
            out=lambda text="": None, model=model, on_world=on_world
        ))
        self.addAsyncCleanup(self.cancel_task, task)
        await asyncio.wait_for(waiting.wait(), 30)
        world = world_ready[0]
        screen = world.named["screen"]
        player = world.named["player"]
        controls = world.named["input"]
        practice = world.named["practice"]

        def pixel(x, y):
            return page.value_pixel(world, screen, x, y)

        page.sync(world)
        initial_frame = frames[-1]
        initial = (pixel(72, 80), pixel(64, 80))
        positions = []
        for action in ("left", "right", "up", "down"):
            world.event(lambda: controls.fields.__setitem__("action", action))
            positions.append((player.fields["column"], player.fields["row"]))
            if action == "left":
                changed = (pixel(72, 80), pixel(64, 80))
                page.sync(world)
                changed_frame = frames[-1]
        self.assertEqual(initial_frame[:3], ("Screen", 160, 144))
        self.assertNotEqual(initial_frame[3], changed_frame[3])
        self.assertFalse(task.done())
        self.assertEqual(practice.fields["field note"], "Waiting for calibration")
        reply.set_result("Calibration complete. Keep exploring.")
        finished = await asyncio.wait_for(task, 30)
        self.assertIs(finished, world)
        return initial_frame, changed_frame, initial, changed, positions, player.fields["step count"], practice.fields["field note"], requests

    @staticmethod
    async def cancel_task(task):
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_input_during_delayed_model_reply_replays_identically(self):
        first = await self.replay()
        second = await self.replay()
        self.assertEqual(first, second)
        _, _, initial, changed, positions, steps, result, requests = first
        self.assertEqual(initial, (3, 0))
        self.assertEqual(changed, (0, 3))
        self.assertEqual(positions, [(64, 80), (72, 80), (72, 72), (72, 80)])
        self.assertEqual(steps, 4)
        self.assertEqual(result, "Calibration complete. Keep exploring.")
        self.assertEqual(requests, [("Give a short Field Lab calibration message.", None, "text", None)])



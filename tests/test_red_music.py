import math
import unittest
from pathlib import Path

from englishscript import compile_file


ENTRY = Path(__file__).resolve().parents[1] / "docs" / "red" / "main.english"


class RedMusic(unittest.IsolatedAsyncioTestCase):
    async def test_campaign_music_routes_and_arrangements(self):
        async def model(question, state, shape, complaint):
            return ""

        world = await compile_file(ENTRY).run_async(out=lambda text="": None, model=model)
        journey = world.named["journey"].fields
        combat = world.named["combat"].fields
        score = world.named["score"].fields
        controls = world.named["controls"].fields
        controls["rendering"] = 0

        def check(expected):
            self.assertEqual(score["music"], expected)
            self.assertGreater(score["tempo"], 0)
            for voice in ("melody", "harmony", "bass"):
                self.assertTrue(score[voice], (expected, voice))
            for voice in ("melody", "harmony", "bass", "percussion", "intro melody",
                          "intro harmony", "intro bass", "intro percussion"):
                for token in score[voice].split():
                    pitch, duration = token.split(":")
                    self.assertTrue(pitch == "noise" or 0 <= float(pitch) <= 127, (expected, voice, token))
                    self.assertTrue(math.isfinite(float(duration)) and float(duration) > 0,
                                    (expected, voice, token))

        def tick():
            self.assertTrue(world.event(lambda: controls.__setitem__("action", "tick")))

        check("intro duel")
        cases = (
            ("opening", "Pewter Gym", "intro duel"),
            ("title", "", "opening"), ("title", "Pewter Gym", "opening"),
            ("main menu", "Route 1", "opening"), ("intro", "", "oak speech"),
            ("walk", "", "oak speech"), ("walk", "Bedroom", "pallet"),
            ("walk", "Pallet Town", "pallet"), ("walk", "Home", "pallet"),
            ("walk", "Blue's House", "pallet"), ("walk", "Oak's Lab", "lab"),
            ("walk", "Route 1", "route"), ("walk", "Route 2", "route"),
            ("walk", "Route 22", "route west"), ("walk", "Viridian Forest", "forest"),
            ("walk", "Route 22 Gate", "forest"), ("walk", "Viridian Center", "center"),
            ("walk", "Pewter Center", "center"), ("walk", "Viridian Mart", "center"),
            ("walk", "Pewter Mart", "center"), ("walk", "Viridian City", "city"),
            ("walk", "Pewter City", "city"), ("walk", "Pewter Gym", "gym"),
            ("walk", "unknown place", "city"),
            ("dialogue", "Route 1", "route"), ("field menu", "Route 1", "route"),
            ("party", "Route 1", "route"), ("bag", "Route 1", "route"),
            ("trainer card", "Route 1", "route"), ("shop", "Route 1", "route"),
            ("town map", "Route 1", "route"),
        )
        for mode, place, expected in cases:
            with self.subTest(mode=mode, place=place):
                journey["mode"], journey["place"] = mode, place
                combat["active"] = 0
                tick()
                check(expected)

        for foe, expected in (("wild", "wild"), ("rival", "trainer"),
                              ("brock", "leader"), ("unknown foe", "trainer"), ("", "trainer")):
            with self.subTest(foe=foe):
                journey["mode"], journey["place"] = "walk", "Pewter Gym"
                combat["active"], combat["challenger"] = 1, foe
                tick()
                check(expected)
                journey["mode"] = "battle bag"
                tick()
                check(expected)
                journey["mode"] = "battle party"
                tick()
                check(expected)
                journey["mode"], journey["place"] = "title", ""
                tick()
                check(expected)
                combat["active"] = 0
                journey["mode"], journey["place"] = "walk", "Pewter Gym"
                tick()
                check("gym")

        journey["mode"], journey["place"] = "walk", "Route 1"
        tick()
        check("route")
        world.named["talk"].fields["phase"] = "composing"
        journey["place"] = "Pewter Gym"
        tick()
        check("route")
        world.named["talk"].fields["phase"] = "closed"
        tick()
        check("gym")

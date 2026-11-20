import json
import unittest
from pathlib import Path

from englishscript import compile_file
from englishscript.libraries import page


ENTRY = Path(__file__).resolve().parents[1] / "docs" / "red" / "main.english"


class Campaign:
    def __init__(self, world):
        self.world = world
        self.journey = world.named["journey"]
        self.controls = world.named["controls"]
        self.combat = world.named["combat"]
        self.actions = []

    @classmethod
    async def start(cls):
        frames = []

        def on_world(world):
            page.use_remote_canvas(world, lambda serial, name, width, height, pixels:
                                   frames.append((name, width, height, bytes(pixels))))

        async def model(question, state, shape, complaint):
            return ""

        world = await compile_file(ENTRY).run_async(out=lambda text="": None, model=model, on_world=on_world)
        campaign = cls(world)
        campaign.frames = frames
        page.sync(world)
        return campaign

    def press(self, *actions):
        for action in actions:
            self.actions.append(action)
            accepted = self.world.event(lambda: self.controls.fields.__setitem__("action", action))
            if not accepted:
                raise AssertionError(f"World ended before {action}; actions: {self.actions!r}")

    def field(self, name):
        return self.journey.fields[name]

    def position(self):
        return tuple(self.field(name) for name in ("place", "column", "row"))


class RedCampaign(unittest.IsolatedAsyncioTestCase):
    async def test_opening_accepts_controller_input(self):
        campaign = await Campaign.start()
        self.assertEqual(campaign.field("mode"), "opening")
        self.assertEqual(campaign.frames[-1][:3], ("Screen", 160, 144))
        for _ in range(30):
            if campaign.field("mode") == "walk":
                break
            if campaign.field("mode") in ("naming", "rival naming") and campaign.field("selection") == 0:
                campaign.press("down")
            campaign.press("a")
        self.assertEqual(campaign.field("mode"), "walk")
        self.assertEqual(campaign.field("place"), "Bedroom")
        self.assertEqual(campaign.field("stage"), "find oak")

    async def test_brocks_portraits_stay_above_the_player_status(self):
        campaign = await Campaign.start()
        campaign.journey.fields["mode"] = "battle"
        campaign.combat.fields["species"] = "Bulbasaur"

        def draw(opponent):
            campaign.combat.fields["opponent"] = opponent
            campaign.press("noop")
            page.sync(campaign.world)
            return campaign.frames[-1][3]

        empty = draw("")
        for opponent in ("Geodude", "Onix"):
            with self.subTest(opponent=opponent):
                frame = draw(opponent)
                self.assertTrue(any(frame[y * 160 + x] for y in range(56) for x in range(104, 160)))
                self.assertEqual(frame[56 * 160:96 * 160], empty[56 * 160:96 * 160])

    async def test_three_starters_earn_and_keep_brock_rewards(self):
        fixtures = (("replay.json", "Bulbasaur"),
                    ("replay-squirtle.json", "Squirtle"),
                    ("replay-charmander.json", "Charmander"))
        for filename, starter in fixtures:
            with self.subTest(starter=starter):
                campaign = await Campaign.start()
                journey = campaign.journey
                combat = campaign.combat
                campaign.controls.fields["rendering"] = 0
                actions = json.loads((ENTRY.parent / filename).read_text())
                observed = set()
                reward = None
                badge_payment = None
                for index, action in enumerate(actions):
                    previous_place = journey.fields["place"]
                    previous_parcel = journey.fields["parcel"]
                    previous_badge = journey.fields["badge"]
                    previous_wallet = journey.fields["wallet"]
                    if index == len(actions) - 1:
                        campaign.controls.fields["rendering"] = 1
                    campaign.press(action)
                    state = journey.fields
                    if previous_place == "Viridian City" and state["place"] == "Viridian Mart" and state["mode"] == "dialogue":
                        observed.add("mart cutscene")
                    if previous_parcel == 0 and state["parcel"] == 1 and state["place"] == "Viridian Mart" and state["mode"] == "dialogue":
                        observed.add("parcel during cutscene")
                    if previous_badge == 0 and state["badge"] == 1:
                        badge_payment = state["wallet"] - previous_wallet
                    if state["parcel"] == 1:
                        observed.add("parcel")
                    if state["dex"] == 1:
                        observed.add("dex")
                    if state["mode"] == "battle":
                        observed.add(combat.fields["opponent"])
                    if state["badge"] == 1 and state["tm34"] == 1 and reward is None:
                        reward = (state["badge"], state["tm34"], state["wallet"])
                self.assertEqual(state["starter"], starter)
                self.assertTrue({"mart cutscene", "parcel during cutscene", "parcel", "dex", "Geodude", "Onix"} <= observed, observed)
                self.assertEqual(state["stage"], "boulder badge")
                self.assertEqual(state["objective"], "Brock awarded you the Boulder Badge and TM34.")
                self.assertEqual(state["mode"], "walk")
                self.assertEqual(badge_payment, 1386)
                self.assertIsNotNone(reward)
                self.assertEqual((state["badge"], state["tm34"], state["wallet"]), reward)

    async def test_road_is_closed_until_oak_receives_parcel(self):
        campaign = await Campaign.start()
        actions = json.loads((ENTRY.parent / "replay-gate.json").read_text())
        saw_warning = False
        for action in actions:
            campaign.press(action)
            if "unsafe" in campaign.field("message"):
                saw_warning = True
        self.assertTrue(saw_warning)
        self.assertEqual(campaign.field("starter"), "Bulbasaur")
        self.assertEqual(campaign.field("dex"), 0)
        self.assertEqual(campaign.field("place"), "Viridian City")
        self.assertEqual(campaign.field("mode"), "dialogue")
        self.assertIn("road is closed", campaign.field("message"))

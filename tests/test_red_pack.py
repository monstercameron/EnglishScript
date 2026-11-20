import shutil
import tempfile
import unittest
from pathlib import Path

from englishscript import compile_file


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


def copy_chapters(root):
    for chapter in RED.glob("*.english"):
        shutil.copy(chapter, root / chapter.name)


class RedPack(unittest.TestCase):
    def test_controller_items_shop_and_save(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            copy_chapters(root)
            (root / "main.english").write_text('''Use the foundation chapter.
Use the battle chapter.
Use the pack chapter.
Set Journey's mode to "walk".
Set Combat's starter to "Bulbasaur".
Enlist.
Set Combat's health to 1.
Set Stock's potions to 1.
Inventory "start".
Inventory "down".
Inventory "a".
Inventory "a".
Inventory "a".
Inventory "b".
Inventory "down".
Inventory "down".
Inventory "a".
Catalogue.
''', encoding="utf-8")
            world = compile_file(root / "main.english").run(out=lambda text="": None)
            stock = world.named["stock"].fields
            combat = world.named["combat"].fields
            self.assertEqual(combat["health"], combat["maximum health"])
            self.assertEqual(stock["potions"], 0)
            self.assertEqual(stock["save request"], 1)

    def test_shop_charges_only_when_affordable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            copy_chapters(root)
            (root / "main.english").write_text('''Use the foundation chapter.
Use the pack chapter.
Set Journey's mode to "shop".
Set Journey's wallet to 300.
Inventory "a".
Inventory "a".
Catalogue.
''', encoding="utf-8")
            world = compile_file(root / "main.english").run(out=lambda text="": None)
            self.assertEqual(world.named["journey"].fields["wallet"], 0)
            self.assertEqual(world.named["stock"].fields["potions"], 1)
            self.assertEqual(world.named["stock"].fields["notice"], "NOT ENOUGH MONEY")


    def test_ground_item_is_collected_once(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            copy_chapters(root)
            (root / "main.english").write_text('''Use the foundation chapter.
Use the pack chapter.
Set Journey's place to "Viridian Forest".
Set Journey's column to 12.
Set Journey's row to 30.
Set Journey's facing to "north".
Examine.
Set Journey's mode to "walk".
Examine.
''', encoding="utf-8")
            world = compile_file(root / "main.english").run(out=lambda text="": None)
            self.assertEqual(world.named["stock"].fields["potions"], 1)
            self.assertEqual(world.named["stock"].fields["forest potion"], 1)
            self.assertEqual(world.named["journey"].fields["mode"], "walk")

    def test_battle_potion_only_spends_turn_on_use(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            copy_chapters(root)
            (root / "main.english").write_text('''Use the foundation chapter.
Use the battle chapter.
Use the pack chapter.
Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "wild".
Set Stock's potions to 1.
Set Journey's mode to "battle bag".
Inventory "a".
Set Combat's health to 1.
Inventory "a".
''', encoding="utf-8")
            world = compile_file(root / "main.english").run(out=lambda text="": None)
            self.assertEqual(world.named["stock"].fields["potions"], 0)
            self.assertEqual(world.named["journey"].fields["mode"], "battle")
            self.assertEqual(world.named["combat"].fields["turn"], 1)

    def test_battle_party_switch_spends_turn(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            copy_chapters(root)
            (root / "main.english").write_text('''Use the foundation chapter.
Use the battle chapter.
Use the party chapter.
Use the pack chapter.
Set Combat's starter to "Bulbasaur".
Enlist.
Record.
Set Team's count to 2.
Set Second's starter to "Pidgey".
Set Second's species to "Pidgey".
Set Second's health to 20.
Set Second's maximum health to 20.
Set Second's defense to 10.
Challenge "wild".
Set Journey's mode to "battle party".
Inventory "down".
Inventory "a".
''', encoding="utf-8")
            world = compile_file(root / "main.english").run(out=lambda text="": None)
            self.assertEqual(world.named["team"].fields["selected"], 2)
            self.assertEqual(world.named["combat"].fields["starter"], "Pidgey")
            self.assertEqual(world.named["combat"].fields["turn"], 1)
            self.assertEqual(world.named["journey"].fields["mode"], "battle")

    def test_ball_cannot_be_used_on_a_trainer(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            copy_chapters(root)
            (root / "main.english").write_text('''Use the foundation chapter.
Use the battle chapter.
Use the pack chapter.
Set Combat's starter to "Bulbasaur".
Enlist.
Challenge "rival".
Set Stock's balls to 1.
Set Stock's cursor to 1.
Set Journey's mode to "battle bag".
Inventory "a".
''', encoding="utf-8")
            world = compile_file(root / "main.english").run(out=lambda text="": None)
            self.assertEqual(world.named["stock"].fields["balls"], 1)
            self.assertEqual(world.named["combat"].fields["turn"], 0)
            self.assertEqual(world.named["journey"].fields["mode"], "battle bag")


class RedFieldPickup(unittest.IsolatedAsyncioTestCase):
    async def test_facing_ground_item_through_controller(self):
        from englishscript.libraries import page

        def on_world(world):
            page.use_remote_canvas(world, lambda *args: None)

        async def model(question, state, shape, complaint):
            return ""

        world = await compile_file(RED / "main.english").run_async(
            out=lambda text="": None, model=model, on_world=on_world
        )
        journey = world.named["journey"].fields
        controls = world.named["controls"].fields
        journey.update({"place": "Viridian Forest", "column": 12, "row": 30,
                        "facing": "north", "mode": "walk"})
        world.event(lambda: controls.__setitem__("action", "a"))
        self.assertEqual(journey["mode"], "dialogue")
        self.assertEqual(world.named["stock"].fields["potions"], 1)
        world.event(lambda: controls.__setitem__("action", "a"))
        world.event(lambda: controls.__setitem__("action", "a"))
        self.assertEqual(world.named["stock"].fields["potions"], 1)

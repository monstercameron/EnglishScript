import re
import shutil
import tempfile
import unittest
from pathlib import Path

from englishscript import compile_file


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


def run_story(sentences):
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        for chapter in RED.glob("*.english"):
            shutil.copy(chapter, root / chapter.name)
        (root / "main.english").write_text(
            "Use the foundation chapter.\nUse the battle chapter.\nUse the party chapter.\n"
            "Use the pack chapter.\nUse the town map chapter.\n" + sentences, encoding="utf-8")
        return compile_file(root / "main.english").run(out=lambda text="": None)


class RedTownMapMarker(unittest.TestCase):
    def marked_town(self, place):
        world = run_story('Set Journey\'s mode to town map.\nSet Journey\'s place to "%s".\nChart.\n' % place)
        navigator = next(thing for name, thing in world.named.items() if name.startswith("navigator"))
        return navigator.fields["current"]

    def test_houses_mark_their_own_town(self):
        self.assertEqual(self.marked_town("Viridian House"), 2)
        self.assertEqual(self.marked_town("Pewter House"), 6)
        self.assertEqual(self.marked_town("Nidoran House"), 6)

    def test_towns_and_routes_keep_their_marker(self):
        self.assertEqual(self.marked_town("Pallet Town"), 0)
        self.assertEqual(self.marked_town("Route 1"), 1)
        self.assertEqual(self.marked_town("Route 22 Gate"), 3)
        self.assertEqual(self.marked_town("Viridian Forest"), 5)
        self.assertEqual(self.marked_town("Pewter Center"), 6)

    def test_cursor_wraps_over_every_location(self):
        world = run_story('Set Journey\'s mode to town map.\nNavigate "up".\n')
        self.assertEqual(world.named["journey"].fields["selection"], 14)
        world = run_story('Set Journey\'s mode to town map.\nSet Journey\'s selection to 14.\nNavigate "down".\n')
        self.assertEqual(world.named["journey"].fields["selection"], 0)


class RedEveryPlaceHasASelection(unittest.TestCase):
    def test_every_map_place_has_a_town_map_selection(self):
        maps = (RED / "maps.english").read_text(encoding="utf-8")
        table = maps.split("The map layouts are", 1)[1].split("\n\n", 1)[0]
        places = re.findall(r'^  "([^"]+)" has', table, re.MULTILINE)
        self.assertGreater(len(places), 20)
        said = []
        sentences = "".join('Say the town pin for "%s".\n' % place for place in places)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for chapter in RED.glob("*.english"):
                shutil.copy(chapter, root / chapter.name)
            (root / "main.english").write_text("Use the foundation chapter.\nUse the town map chapter.\n" + sentences,
                                               encoding="utf-8")
            compile_file(root / "main.english").run(out=lambda text="": said.append(text))
        self.assertTrue(all(text.isdigit() for text in said[:len(places)]))

    def test_unknown_place_is_refused_clearly(self):
        with self.assertRaises(Exception) as caught:
            run_story('Say the town pin for "Nowhere".\n')
        self.assertIn("No town map selection for Nowhere", str(caught.exception))



class RedShopAndCard(unittest.TestCase):
    def test_shop_up_moves_up_and_wraps(self):
        world = run_story('Set Journey\'s mode to shop.\nInventory "up".\n')
        self.assertEqual(world.named["stock"].fields["shop item"], 2)
        world = run_story('Set Journey\'s mode to shop.\nInventory "down".\nInventory "down".\nInventory "up".\n')
        self.assertEqual(world.named["stock"].fields["shop item"], 1)

    def test_shop_down_wraps_to_the_top(self):
        world = run_story('Set Journey\'s mode to shop.\nInventory "down".\nInventory "down".\nInventory "down".\n')
        self.assertEqual(world.named["stock"].fields["shop item"], 0)

    def test_each_item_costs_its_listed_price(self):
        world = run_story('Set Journey\'s mode to shop.\nSet Journey\'s wallet to 1000.\n'
                          'Inventory "a".\nInventory "down".\nInventory "a".\nInventory "down".\nInventory "a".\n')
        self.assertEqual(world.named["journey"].fields["wallet"], 400)
        stock = world.named["stock"].fields
        self.assertEqual((stock["potions"], stock["balls"], stock["antidotes"]), (1, 1, 1))

    def test_closing_the_trainer_card_returns_to_trainer(self):
        world = run_story('Set Journey\'s mode to trainer card.\nInventory "b".\n')
        self.assertEqual(world.named["journey"].fields["mode"], "field menu")
        self.assertEqual(world.named["stock"].fields["cursor"], 2)

    def test_drawing_the_party_does_not_change_the_roster(self):
        world = run_story('Enlist "Bulbasaur".\nSet Combat\'s ally\'s health to 1.\n'
                          'Set Journey\'s mode to party.\nCatalogue.\n')
        team = next(thing for name, thing in world.named.items() if name.startswith("team"))
        self.assertEqual(len(team.fields["members"]), 1)
        self.assertEqual(team.fields["members"][0].fields["health"], 1)

if __name__ == "__main__":
    unittest.main()

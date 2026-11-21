import re
import unittest
from html.parser import HTMLParser
from pathlib import Path


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


class GameElements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.by_id = {}
        self.links = []
        self.scripts = []
        self.in_sidebar = False
        self.sidebar_ids = set()

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if tag == "aside":
            self.in_sidebar = True
        if "id" in attrs:
            identifier = attrs["id"]
            if identifier in self.by_id:
                raise ValueError(f"Duplicate game element {identifier}")
            self.by_id[identifier] = (tag, attrs)
            if self.in_sidebar:
                self.sidebar_ids.add(identifier)
        if tag == "script" and "src" in attrs:
            self.scripts.append(attrs["src"])
        if tag == "link" and attrs.get("rel") == "stylesheet":
            self.links.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag == "aside":
            self.in_sidebar = False


class RedShell(unittest.TestCase):
    def test_controls_and_browser_assets_exist_on_the_served_page(self):
        elements = GameElements()
        elements.feed((RED / "index.html").read_text(encoding="utf-8"))
        script = (RED / "main.js").read_text(encoding="utf-8")
        required = set(re.findall(r"querySelector\(['\"]#([\w-]+)['\"]\)", script))
        self.assertFalse(required - elements.by_id.keys(), required - elements.by_id.keys())
        self.assertEqual(elements.by_id["companion"][0], "form")
        self.assertEqual(elements.by_id["question"][0], "input")
        for identifier in ("screen", "provider-keys", "source-reader", "talk-reply"):
            self.assertIn(identifier, elements.by_id)
        sidebar_controls = {"sound-toggle", "music-title", "talk-open", "talk-next", "talk-close", "talk-status"}
        self.assertTrue(sidebar_controls <= elements.sidebar_ids)
        for asset in elements.scripts + elements.links:
            self.assertTrue((RED / asset.split("?")[0]).is_file(), asset)

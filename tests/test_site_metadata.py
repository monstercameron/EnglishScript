"""Metadata and share images served by the project site."""
import struct
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

DOCS = Path(__file__).resolve().parent.parent / "docs"
BASE = "https://monstercameron.github.io/EnglishScript/"


class Head(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta = []
        self.links = []
        self.titles = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            self.meta.append(attrs)
        elif tag == "link":
            self.links.append(attrs)
        elif tag == "title":
            self.in_title = True
            self.titles.append("")

    def handle_data(self, data):
        if self.in_title:
            self.titles[-1] += data

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False


def png_size(path):
    data = path.read_bytes()[:24]
    if data[:16] != b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR":
        raise ValueError(f"{path} does not have a PNG IHDR header")
    return struct.unpack_from(">II", data, 16)


class SiteMetadata(unittest.TestCase):
    def one_meta(self, head, attribute, name):
        matches = [item.get("content", "").strip() for item in head.meta
                   if item.get(attribute, "").lower() == name]
        self.assertEqual(len(matches), 1, f"expected one {name} tag")
        self.assertTrue(matches[0], f"empty {name} tag")
        return matches[0]

    def local_asset(self, url, canonical):
        resolved = urlsplit(urljoin(canonical, url))
        self.assertEqual((resolved.scheme, resolved.netloc), ("https", "monstercameron.github.io"))
        self.assertTrue(resolved.path.startswith("/EnglishScript/assets/"), url)
        self.assertFalse(resolved.query or resolved.fragment, url)
        relative = unquote(resolved.path.removeprefix("/EnglishScript/"))
        path = (DOCS / relative).resolve()
        self.assertTrue(path.is_relative_to((DOCS / "assets").resolve()), url)
        self.assertTrue(path.is_file(), url)
        return path

    def test_every_page_has_distinct_metadata_and_resolvable_assets(self):
        pages = sorted(DOCS.rglob("*.html"))
        self.assertTrue(pages)
        titles, descriptions = set(), set()
        for path in pages:
            name = path.relative_to(DOCS).as_posix()
            with self.subTest(page=name):
                suffix = name.removesuffix("index.html") if path.name == "index.html" else name
                canonical = urljoin(BASE, suffix)
                head = Head()
                page = path.read_text(encoding="utf-8")
                self.assertIn("</head>", page)
                head.feed(page.split("</head>", 1)[0] + "</head>")
                self.assertEqual(len(head.titles), 1)
                title = head.titles[0].strip()
                self.assertTrue(title)
                description = self.one_meta(head, "name", "description")
                self.assertNotIn(title, titles)
                self.assertNotIn(description, descriptions)
                titles.add(title)
                descriptions.add(description)
                canonical_links = [item.get("href") for item in head.links
                                   if "canonical" in item.get("rel", "").lower().split()]
                self.assertEqual(canonical_links, [canonical])
                for key, expected in (("og:title", title), ("og:description", description),
                                      ("og:url", canonical), ("og:type", "website"),
                                      ("og:site_name", "EnglishScript")):
                    self.assertEqual(self.one_meta(head, "property", key), expected)
                self.assertEqual(self.one_meta(head, "name", "twitter:card"), "summary_large_image")
                self.assertEqual(self.one_meta(head, "name", "twitter:title"), title)
                self.assertEqual(self.one_meta(head, "name", "twitter:description"), description)
                image = self.one_meta(head, "property", "og:image")
                self.assertEqual(self.one_meta(head, "name", "twitter:image"), image)
                self.one_meta(head, "property", "og:image:alt")
                self.one_meta(head, "name", "twitter:image:alt")
                self.assertEqual(image, BASE + "assets/" + ("red-preview.png" if name == "red/index.html" else "social-preview.png"))
                self.local_asset(image, canonical)
                for rel, expected in (("icon", {"favicon.ico", "favicon-32.png"}),
                                      ("apple-touch-icon", {"apple-touch-icon.png"})):
                    icons = [item for item in head.links if rel in item.get("rel", "").lower().split()]
                    self.assertEqual({self.local_asset(icon.get("href", ""), canonical).name
                                      for icon in icons}, expected)

    def test_preview_and_icon_files_have_the_expected_formats(self):
        assets = DOCS / "assets"
        for name, size in (("social-preview.png", (1200, 630)), ("red-preview.png", (1200, 630)),
                           ("favicon-32.png", (32, 32)), ("apple-touch-icon.png", (180, 180))):
            with self.subTest(asset=name):
                self.assertEqual(png_size(assets / name), size)
        ico = (assets / "favicon.ico").read_bytes()
        self.assertGreaterEqual(len(ico), 22)
        reserved, kind, count = struct.unpack_from("<HHH", ico)
        self.assertEqual((reserved, kind), (0, 1))
        self.assertGreater(count, 0)
        self.assertGreaterEqual(len(ico), 6 + 16 * count)
        sizes = {(ico[6 + 16 * index] or 256, ico[7 + 16 * index] or 256)
                 for index in range(count)}
        self.assertTrue({(16, 16), (32, 32), (48, 48)} <= sizes)
        for index in range(count):
            length, offset = struct.unpack_from("<II", ico, 6 + 16 * index + 8)
            self.assertGreater(length, 0)
            self.assertGreaterEqual(offset, 6 + 16 * count)
            self.assertLessEqual(offset + length, len(ico))


if __name__ == "__main__":
    unittest.main()

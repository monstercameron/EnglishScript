"""Turn the project's Markdown documents into pages of the site.

docs/SYNTAX.md and docs/VULKAN.md are the source. GitHub Pages serves Markdown
as plain text, so tools/build_site.py uses this module to print them as
docs/reference.html and docs/vulkan.html, in the same dress as the other pages.

This reads only the Markdown those two documents use: headings, paragraphs,
lists (one level of nesting), tables, fenced blocks, block quotes, pictures,
links, `code`, **bold** and *italic*. It needs nothing but the standard library.
"""
from __future__ import annotations

import html
import re

SOURCE = "https://github.com/monstercameron/EnglishScript"
FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500'
    "&amp;family=IM+Fell+English:ital@0;1&amp;family=IM+Fell+English+SC&amp;family=UnifrakturMaguntia&amp;display=swap\">\n"
    '<link rel="stylesheet" href="assets/english.css">\n'
)
PAGES = [
    ("./", "The treatise"), ("playground.html", "The playground"), ("todo.html", "A page"), ("compare.html", "Compared"), ("opposition.html", "The opposition"), ("systems.html", "Three systems"),
    ("reference.html", "The grammar"), ("how.html", "The machinery"), (SOURCE, "The source"),
]
# Where a link to another document of the repository goes on the site.
LINKS = {"SYNTAX.md": "reference.html", "VULKAN.md": "vulkan.html", "PAGE.md": "page.html", "CONCERNS.md": "concerns.html", "EDITORS.md": "editors.html", "OPPOSITION.md": "opposition.html",
         "docs/SYNTAX.md": "reference.html", "docs/VULKAN.md": "vulkan.html", "docs/PAGE.md": "page.html", "docs/CONCERNS.md": "concerns.html", "docs/EDITORS.md": "editors.html", "docs/OPPOSITION.md": "opposition.html"}


def nav(current):
    links = "\n".join(
        f'    <a class="page" href="{href}"' + (' aria-current="page"' if href == current else "") + f">{name}</a>"
        for href, name in PAGES)
    return ('<nav class="sitenav" aria-label="The pages of this site">\n  <div class="inner">\n'
            f'    <a class="home" href="./">EnglishScript</a>\n{links}\n  </div>\n</nav>\n')


def anchor(title, used):
    """An id for a heading: s4-2 for "4.2 Things", otherwise its words."""
    numbered = re.match(r"(\d+(?:\.\d+)*)\.?\s", title)
    if numbered:
        base = "s" + numbered.group(1).replace(".", "-")
    else:
        base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "part"
    name, n = base, 2
    while name in used:
        name, n = f"{base}-{n}", n + 1
    used.add(name)
    return name


class Markdown:
    def __init__(self, text):
        self.lines = text.replace("\r\n", "\n").split("\n")
        self.ids = set()
        self.headings = []  # (level, id, title) in order
        self.blocks = self.parse()

    # ------------------------------------------------------------- inline

    def inline(self, text):
        codes = []

        def keep(match):
            codes.append("<code>" + html.escape(match.group(1), quote=False) + "</code>")
            return f"\0{len(codes) - 1}\0"
        text = re.sub(r"`([^`]+)`", keep, text)
        text = html.escape(text, quote=False)
        text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)",
                      lambda m: f'<img src="{m.group(2)}" alt="{html.escape(html.unescape(m.group(1)))}">', text)
        text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", lambda m: f'<a href="{self.link(m.group(2))}">{m.group(1)}</a>', text)
        text = re.sub(r"&lt;(https?://[^&\s]+)&gt;", r'<a href="\1">\1</a>', text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<![\w*])\*([^*\s](?:[^*]*[^*\s])?)\*(?![\w*])", r"<em>\1</em>", text)
        text = re.sub(r"\b(sections?) (\d+(?:\.\d+)*(?:(?:, | and | to )\d+(?:\.\d+)*)*)", self.sections, text)
        return re.sub(r"\0(\d+)\0", lambda m: codes[int(m.group(1))], text)

    @staticmethod
    def link(target):
        if target in LINKS:
            return LINKS[target]
        if target.startswith(("http://", "https://", "#", "assets/")):
            return target
        return f"{SOURCE}/blob/main/docs/{target}"

    def sections(self, match):
        """"section 8.5" becomes a link, when this document has a section 8.5."""
        def one(number):
            name = "s" + number.group(0).replace(".", "-")
            return f'<a href="#{name}">{number.group(0)}</a>' if name in self.numbered else number.group(0)
        return match.group(1) + " " + re.sub(r"\d+(?:\.\d+)*", one, match.group(2))

    # -------------------------------------------------------------- blocks

    def parse(self):
        blocks, lines, i = [], self.lines, 0
        while i < len(lines):
            line = lines[i]
            if not line.strip():
                i += 1
            elif line.startswith("```"):
                kind, body = line[3:].strip(), []
                i += 1
                while i < len(lines) and not lines[i].startswith("```"):
                    body.append(lines[i])
                    i += 1
                i += 1
                blocks.append(("code", kind, "\n".join(body)))
            elif re.match(r"#{1,4} ", line):
                level = len(line) - len(line.lstrip("#"))
                title = line[level:].strip()
                name = anchor(title, self.ids)
                self.headings.append((level, name, title))
                blocks.append(("heading", level, name, title))
                i += 1
            elif line.startswith("|"):
                rows = []
                while i < len(lines) and lines[i].startswith("|"):
                    rows.append(self.cells(lines[i]))
                    i += 1
                blocks.append(("table", rows))
            elif line.startswith(">"):
                quote = []
                while i < len(lines) and lines[i].startswith(">"):
                    quote.append(lines[i][1:].strip())
                    i += 1
                blocks.append(("quote", " ".join(quote)))
            elif re.match(r"\s*([-*]|\d+\.) ", line):
                items = []
                while i < len(lines) and (re.match(r"\s*([-*]|\d+\.) ", lines[i]) or (lines[i].startswith("  ") and lines[i].strip())):
                    found = re.match(r"(\s*)([-*]|\d+\.) (.*)", lines[i])
                    if found:
                        items.append([len(found.group(1)), found.group(2)[0].isdigit(), found.group(3)])
                    else:
                        items[-1][2] += " " + lines[i].strip()
                    i += 1
                blocks.append(("list", items))
            elif line.strip() == "---":
                blocks.append(("rule",))
                i += 1
            else:
                para = []
                while i < len(lines) and lines[i].strip() and not re.match(r"(```|#{1,4} |\||>|\s*([-*]|\d+\.) )", lines[i]):
                    para.append(lines[i].strip())
                    i += 1
                blocks.append(("para", " ".join(para)))
        return blocks

    @staticmethod
    def cells(row):
        """The cells of a table row. A | inside `code` does not divide cells."""
        cells, cell, coded = [], "", False
        row = row.strip()
        row = row[1:] if row.startswith("|") else row
        row = row[:-1] if row.endswith("|") and not row.endswith("\\|") else row
        i = 0
        while i < len(row):
            char = row[i]
            if char == "\\" and row[i + 1:i + 2] == "|":  # \| is a bar that is part of the text
                cell += "|"
                i += 2
                continue
            if char == "`":
                coded = not coded
            if char == "|" and not coded:
                cells.append(cell.strip())
                cell = ""
            else:
                cell += char
            i += 1
        cells.append(cell.strip())
        return cells

    # ---------------------------------------------------------------- html

    def render(self, skip_title=True):
        self.numbered = {name for _, name, _ in self.headings if re.fullmatch(r"s\d+(-\d+)*", name)}
        out, seen_world = [], False
        for block in self.blocks:
            kind = block[0]
            if kind == "heading":
                _, level, name, title = block
                if level == 1 and skip_title:
                    continue
                out.append(f'<h{level} id="{name}">{self.inline(title)}</h{level}>')
            elif kind == "para":
                out.append(f"<p>{self.inline(block[1])}</p>")
            elif kind == "quote":
                out.append(f"<blockquote><p>{self.inline(block[1])}</p></blockquote>")
            elif kind == "rule":
                out.append('<p class="fleuron" aria-hidden="true">&#10086;</p>')
            elif kind == "table":
                out.append(self.table(block[1]))
            elif kind == "list":
                out.append(self.list(block[1]))
            elif kind == "code":
                _, lang, body = block
                text = html.escape(body, quote=False)
                if lang == "englishscript":
                    mark = " data-with-world" if seen_world else " data-world"
                    seen_world = True
                    out.append(f'<figure class="snippet"{mark}>\n<pre class="program" data-expect="ok">{text}</pre>\n</figure>')
                elif lang == "refused":
                    out.append(f'<figure class="snippet" data-with-world>\n<pre class="program" data-expect="refused">{text}</pre>\n</figure>')
                else:
                    out.append(f'<pre class="form">{text}</pre>')
        return "\n".join(out)

    def table(self, rows):
        head, body = rows[0], [row for row in rows[2:]]
        out = ['<div class="scroll"><table>', "<thead><tr>" + "".join(f"<th>{self.inline(c)}</th>" for c in head) + "</tr></thead>", "<tbody>"]
        for row in body:
            out.append("<tr>" + "".join(f"<td>{self.inline(c)}</td>" for c in row) + "</tr>")
        out.append("</tbody></table></div>")
        return "\n".join(out)

    def list(self, items):
        """A list, with items indented under another item as a list inside it."""
        base = items[0][0]
        out, i = [], 0
        tag = "ol" if items[0][1] else "ul"
        out.append(f"<{tag}>")
        while i < len(items):
            indent, _, text = items[i]
            inner = []
            i += 1
            while i < len(items) and items[i][0] > base:
                inner.append(items[i])
                i += 1
            out.append(f"<li>{self.inline(text)}" + (self.list(inner) if inner else "") + "</li>")
        out.append(f"</{tag}>")
        return "\n".join(out)

    def title(self):
        return next((title for level, _, title in self.headings if level == 1), "")

    def contents(self, later=()):
        """The chapters, as a list of links. `later` names chapter numbers that are designs, not built."""
        rows = []
        for level, name, title in self.headings:
            if level != 2:
                continue
            number = re.match(r"(\d+)", title)
            cls = ' class="later"' if number and number.group(1) in later else ""
            rows.append(f'<li><a href="#{name}"{cls}>{html.escape(title, quote=False)}</a></li>')
        return '<nav class="contents" aria-label="Contents">\n<h2>Contents</h2>\n<ol>\n' + "\n".join(rows) + "\n</ol>\n</nav>"


def document(*, title, description, current, heading, standfirst, body, contents=None, runnable=True, colophon=""):
    """A whole page: the navigation, an optional contents list, and the text."""
    script = ('<script type="module">\nimport { mountSnippets } from "./play/snippets.js";\nmountSnippets();\n</script>\n'
              if runnable else "")
    side = contents + "\n" if contents else ""
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
{FONTS}</head>
<body>

{nav(current)}
<main class="doc {'sided' if contents else 'plain'}">
{side}<article>
<h1>{heading}</h1>
<p class="standfirst">{standfirst}</p>
{body}
</article>
<footer class="colophon">
  {colophon}
</footer>
</main>

{script}</body>
</html>
'''

"""docs/fizzbuzz.html: FizzBuzz in EnglishScript, beside FizzBuzz in each of its rivals.

The samples and what is known about each live in docs/rivals/fizzbuzz.json. The
EnglishScript program is examples/fizzbuzz.english, printed with what the
compiler says it does (tools/build_site.py fills that in, as it does on every
page that prints a program).
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pages

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "rivals" / "fizzbuzz.json"

FAMILIES = [
    ("classic", "English-like languages"),
    ("controlled", "Controlled English"),
    ("teaching", "For teaching"),
    ("model", "Languages that ask a model"),
]
CHECKS = {
    "run": ("Run", "It was run, and what it printed is FizzBuzz exactly."),
    "documentation": ("Checked", "Every construct was checked against the documentation cited. It was not run."),
    "partly checked": ("Partly checked", "Some constructs could not be confirmed: the note says which."),
    "not a program": ("Not a program", "A specification, or a request to a model. It does not compute FizzBuzz itself."),
}


def rivals():
    return json.loads(DATA.read_text(encoding="utf-8"))


def sentences(code):
    """Lines that say something: not blank, and not only a comment."""
    comment = re.compile(r"^\s*(#|--|//|\*|;|\(\*|<!--)")
    return sum(1 for line in code.splitlines() if line.strip() and not comment.match(line))


def esc(text):
    return html.escape(str(text), quote=False)


def card(rival):
    label, meaning = CHECKS.get(rival["checked"], (rival["checked"], ""))
    family = dict(FAMILIES).get(rival["family"], rival["family"])
    sources = " ".join(f'<a href="{html.escape(url)}">{esc(_site(url))}</a>' for url in rival.get("sources", []))
    printed = ""
    if rival.get("output_head"):
        head = "\n".join(rival["output_head"])
        tail = "\n".join(rival.get("output_tail") or [])
        printed = (f'<details class="printed"><summary>What it printed</summary>'
                   f'<pre>{esc(head)}\n…\n{esc(tail)}</pre></details>')
    runs = "Computes it by itself" if rival.get("runs") else "Does not compute it by itself"
    return f'''<article class="rival" data-family="{html.escape(rival["family"])}" id="{html.escape(rival["id"])}">
  <header>
    <h2>{esc(rival["name"])} <span class="year">{rival["year"]}</span></h2>
    <p class="tags"><span class="tag">{esc(family)}</span><span class="check check-{rival["checked"].replace(" ", "-")}" title="{html.escape(meaning)}">{esc(label)}</span><span class="tag">{sentences(rival["code"])} lines</span></p>
  </header>
  <pre class="code" tabindex="0">{esc(rival["code"])}</pre>
  <p class="note">{esc(rival["note"])}</p>
  <p class="meta"><span>{esc(runs)}.</span> <span>{esc(rival.get("checked_with") or "")}</span></p>
  {printed}
  <p class="sources">{sources}<a class="back" href="#ledger">Back to the list</a></p>
</article>'''


def _site(url):
    host = re.sub(r"^https?://(www\.)?", "", url).split("/", 1)[0]
    return host or url


def page():
    english = (ROOT / "examples" / "fizzbuzz.english").read_text(encoding="utf-8").replace("\r\n", "\n").rstrip("\n")
    found = rivals()
    filters = "\n".join(
        f'<input type="radio" name="family" id="f-{key}"{" checked" if key == "all" else ""}>'
        f'<label for="f-{key}">{esc(name)} <span class="count">{count}</span></label>'
        for key, name, count in [("all", "All", len(found))]
        + [(key, name, sum(1 for rival in found if rival["family"] == key)) for key, name in FAMILIES])
    hide = "\n".join(
        f'  #f-{key}:checked ~ .rivals .rival:not([data-family="{key}"]) {{ display: none; }}' for key, _ in FAMILIES)
    rows = "\n".join(
        f'<tr><td><a href="#{html.escape(rival["id"])}">{esc(rival["name"])}</a></td><td>{rival["year"]}</td>'
        f'<td>{sentences(rival["code"])}</td><td>{"yes" if rival.get("runs") else "no"}</td>'
        f'<td>{esc(CHECKS.get(rival["checked"], (rival["checked"],))[0])}</td></tr>'
        for rival in found)
    ours = sentences(english)
    checked = sum(1 for rival in found if rival["checked"] == "run")
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FizzBuzz in EnglishScript and its rivals</title>
<meta name="description" content="FizzBuzz in EnglishScript beside FizzBuzz in {len(found)} other English-like languages and languages that ask a model, each checked against its documentation.">
{pages.FONTS}<style>
  .fizz {{ max-width: 84rem; margin: 0 auto; padding: 0 16px 2rem; }}
  .fizz > h1 {{ font: 400 clamp(2.4rem, 8vw, 3.7rem)/1.05 var(--fell); margin: 2.5rem 0 0.4rem; text-align: center; text-wrap: balance; }}
  .fizz > .standfirst {{ font: italic 1.35rem/1.4 var(--fell); color: var(--muted); margin: 0 auto 1.5rem; max-width: 42rem; text-align: center; text-wrap: pretty; }}
  .fizz > .intro, .fizz > .ledger {{ max-width: 48rem; margin-left: auto; margin-right: auto; }}
  .side-by-side {{ display: grid; grid-template-columns: minmax(0, 1fr); gap: 1.5rem; margin-top: 2rem; }}
  @media (min-width: 960px) {{
    .side-by-side {{ grid-template-columns: minmax(0, 0.85fr) minmax(0, 1.15fr); align-items: start; }}
    .ours {{ position: sticky; top: 1rem; max-height: calc(100vh - 2rem); overflow: auto; }}
  }}
  .ours figure.snippet {{ margin: 0; }}
  .ours .output {{ max-height: 14rem; overflow: auto; }}
  .ours h2, .rival h2 {{ font: 400 1.5rem/1.2 var(--fell); margin: 0; }}
  .ours > p {{ font: italic 1.05rem/1.4 var(--fell); color: var(--muted); margin: 0.6rem 0 0.8rem; }}
  .filters {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0 0 1rem; }}
  .filters input {{ position: absolute; opacity: 0; pointer-events: none; }}
  .filters label {{ font: 0.95rem var(--caps); letter-spacing: 0.08em; text-transform: lowercase; border: 1px solid var(--ink); padding: 0.3rem 0.7rem 0.35rem; cursor: pointer; transition: background-color 0.2s ease, color 0.2s ease; }}
  .filters label .count {{ color: var(--muted); }}
  .filters input:checked + label {{ background: var(--ink); color: var(--bg); }}
  .filters input:checked + label .count {{ color: var(--bg); opacity: 0.7; }}
  .filters input:focus-visible + label {{ outline: 2px solid var(--focus); outline-offset: 2px; }}
{hide}
  .rivals {{ flex: 0 0 100%; min-width: 0; margin-top: 0.6rem; }}
  .side-by-side > section {{ min-width: 0; }}
  .rival {{ min-width: 0; }}
  .rival .meta, .rival .note {{ overflow-wrap: anywhere; }}
  .rival {{ border: 1px solid var(--ink); background: var(--bg); box-shadow: 4px 4px 0 var(--rule); margin: 0 0 1.4rem; scroll-margin-top: 1rem; }}
  .rival > header {{ padding: 0.7rem 1rem 0.5rem; background: var(--panel); border-bottom: 3px double var(--ink); }}
  .rival .year {{ font: 1rem var(--caps); letter-spacing: 0.08em; color: var(--muted); }}
  .rival .tags {{ display: flex; flex-wrap: wrap; gap: 0.3rem 0.5rem; margin: 0.35rem 0 0; }}
  .tag, .check {{ font: 0.85rem var(--caps); letter-spacing: 0.08em; text-transform: lowercase; border: 1px solid var(--rule); padding: 0.05rem 0.45rem 0.12rem; }}
  .check-run {{ border-color: var(--good); color: var(--good); }}
  .check-documentation {{ border-color: var(--ink); }}
  .check-partly-checked {{ border-color: var(--warn); color: var(--warn); }}
  .check-not-a-program {{ border-color: var(--accent); color: var(--accent); }}
  .rival pre.code {{ margin: 0; padding: 0.9rem 1rem; font: 0.8rem/1.55 var(--mono); font-variant-ligatures: none; white-space: pre; overflow-x: auto; border-bottom: 1px solid var(--rule); }}
  .rival .note {{ margin: 0.7rem 1rem 0.3rem; font-size: 1.1rem; line-height: 1.4; }}
  .rival .meta {{ margin: 0 1rem 0.4rem; font: italic 1rem/1.4 var(--fell); color: var(--muted); }}
  .rival .printed {{ margin: 0 1rem 0.4rem; }}
  .rival .printed summary {{ font: 0.9rem var(--caps); letter-spacing: 0.08em; text-transform: lowercase; cursor: pointer; color: var(--accent); }}
  .rival .printed pre {{ font: 0.78rem/1.5 var(--mono); margin: 0.3rem 0 0; }}
  .rival .sources {{ margin: 0 1rem 0.8rem; font-size: 0.95rem; display: flex; flex-wrap: wrap; gap: 0.2rem 0.8rem; }}
  .rival .back {{ margin-left: auto; font: 0.9rem var(--caps); letter-spacing: 0.08em; text-transform: lowercase; }}
  table.ledger {{ scroll-margin-top: 1rem; }}
  .to-top {{
    position: fixed; right: 1.2rem; bottom: 1.2rem; z-index: 50; padding: 0.5rem 0.9rem 0.55rem;
    font: 0.95rem var(--caps); letter-spacing: 0.08em; text-transform: lowercase; text-decoration: none;
    color: var(--accent-ink); background: var(--accent); border: 1px solid var(--accent); box-shadow: 3px 3px 0 var(--rule);
    transition: opacity 0.25s ease, transform 0.25s ease;
  }}
  .to-top:hover {{ filter: brightness(1.08); }}
  .to-top:focus-visible {{ outline: 2px solid var(--focus); outline-offset: 3px; }}
  /* With scripts, it waits until the reader has scrolled; without, it is always there. */
  .to-top:not(.shown) {{ opacity: 0; transform: translateY(0.6rem); pointer-events: none; }}
  @media (scripting: none) {{ .to-top:not(.shown) {{ opacity: 1; transform: none; pointer-events: auto; }} }}
  .to-top:not(.shown):focus-visible {{ opacity: 1; transform: none; pointer-events: auto; }}
  @media print {{ .to-top {{ display: none; }} }}
  table.ledger td:nth-child(n+2), table.ledger th:nth-child(n+2) {{ text-align: right; font-variant-numeric: lining-nums tabular-nums; }}
  table.ledger tr.ours td {{ font-weight: 600; }}
</style>
</head>
<body>

{pages.nav("")}
<main class="fizz">
<h1 id="top">FizzBuzz, Every Way</h1>
<p class="standfirst">One small program in EnglishScript, and the same program in {len(found)} of its rivals: the English-like languages since 1955, and the new ones that ask a model.</p>

<div class="intro">
<p>FizzBuzz counts from 1 to 100, saying “Fizz” for a multiple of three, “Buzz” for a multiple of five, “FizzBuzz” for both, and otherwise the number. It is small enough to show whole, and it needs a loop, a choice and a little arithmetic, which is where English-like languages differ most.</p>
<p>Each sample was written for this page from its language's own documentation, and is marked with how far it was checked: <strong>run</strong>, when it was run and printed FizzBuzz exactly ({checked} of them); <strong>checked</strong>, when every construct was checked against the documentation but nothing here could run it; <strong>partly checked</strong>; or <strong>not a program</strong>, for a specification, or for a request that hands the arithmetic to a model. Some of these languages cannot do it at all, and their cards say why. <a href="opposition.html">The opposition</a> tells each one's story.</p>
</div>

<div class="scroll">
<table class="ledger" id="ledger">
  <thead><tr><th>Language</th><th>Year</th><th>Lines</th><th>Computes it itself</th><th>How far checked</th></tr></thead>
  <tbody>
    <tr class="ours"><td>EnglishScript</td><td>2026</td><td>{ours}</td><td>yes</td><td>Run, here, on every build</td></tr>
{rows}
  </tbody>
</table>
</div>

<div class="side-by-side">
  <section class="ours" aria-labelledby="ours-title">
    <h2 id="ours-title">EnglishScript</h2>
    <p>Kept beside the others as you scroll. The output under it is what the compiler said when this page was built, and “Run it” runs it again in your browser.</p>
    <figure class="snippet">
<pre class="program" data-expect="ok">{esc(english)}</pre>
<pre class="output"></pre>
    </figure>
  </section>

  <section aria-label="The rivals">
    <div class="filters" role="radiogroup" aria-label="Which rivals to show">
{filters}
    <div class="rivals">
{chr(10).join(card(rival) for rival in found)}
    </div>
    </div>
  </section>
</div>
</main>
<footer class="colophon" style="max-width: 48rem; margin: 3rem auto 0; padding: 2.5rem 16px 3rem; border-top: 3px double var(--ink);">
  Printed from <a href="{pages.SOURCE}/blob/main/docs/rivals/fizzbuzz.json">docs/rivals/fizzbuzz.json</a> and <a href="{pages.SOURCE}/blob/main/examples/fizzbuzz.english">examples/fizzbuzz.english</a> by <code>tools/build_site.py</code>. The rivals' samples were written for this page; corrections are welcome.
</footer>

<a class="to-top" href="#top" aria-label="Back to the top of the page"><span aria-hidden="true">↑</span> Top</a>

<script type="module">
import {{ mountSnippets }} from "./play/snippets.js";
mountSnippets();

// The button back to the top shows only once the reader has scrolled away from it.
const button = document.querySelector(".to-top");
const away = () => button.classList.toggle("shown", window.scrollY > 600);
away();
window.addEventListener("scroll", away, {{ passive: true }});
</script>
</body>
</html>
'''

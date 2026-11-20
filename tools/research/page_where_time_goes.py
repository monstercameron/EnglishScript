"""Which functions one tick on the to-do page spends its time in, with 200 cards.

Run from the repository:  python tools/research/page_where_time_goes.py .
"""
import cProfile
import pstats
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
from englishscript import compile_source  # noqa: E402
from englishscript.libraries import page  # noqa: E402

examples = root / "examples"
page.STORE.clear()
page.STORE["tasks"] = "".join(f"- - - Task number {i + 1}\n" for i in range(200))
world = compile_source((examples / "web_todo.english").read_text(encoding="utf-8"), folder=examples).run(out=lambda text="": None)

profiler = cProfile.Profile()
profiler.enable()
page.tick(world, "card 3")
profiler.disable()

rows = []
for (filename, line, name), (calls, _, own, cumulative, _) in pstats.Stats(profiler).stats.items():
    if "englishscript" in filename:
        rows.append((cumulative, own, calls, name, Path(filename).name, line))
whole = max(row[0] for row in rows)
print(f"one tick among 200 cards: {whole * 1000:.0f} ms under the profiler")
for cumulative, own, calls, name, filename, line in sorted(rows, reverse=True)[:16]:
    print(f"  {cumulative * 1000:7.1f} ms with callees  {own * 1000:7.1f} ms own  {calls:7} calls  {name} ({filename}:{line})")

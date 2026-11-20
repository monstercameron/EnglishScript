"""Where the time goes when the vocabulary is large. Run from the snapshot folder."""
import cProfile
import pstats
import sys

sys.path.insert(0, sys.argv[1])
from englishscript import compile_source  # noqa: E402

kinds = 600
parts = []
for k in range(kinds):
    word = "thing" + "".join(chr(97 + int(d)) for d in str(k))
    parts.append(f"A {word} has a weight (number) and a label (text).\n")
    parts.append(f"There is a {word} called Item{''.join(chr(65 + int(d)) for d in str(k))} whose weight is {k} and whose label is \"x\".\n")
    parts.append(f"A {word} is heavy when its weight is more than 5.\n")
source = "".join(parts) + "Let the count be 0.\n" + "".join("Add 1 to the count.\n" for _ in range(300))

profiler = cProfile.Profile()
profiler.enable()
compile_source(source)
profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats("cumulative")
rows = []
for (filename, line, name), (calls, _, own, cumulative, _) in stats.stats.items():
    if "englishscript" in filename:
        rows.append((own, cumulative, calls, name, line))
total = sum(row[0] for row in rows)
print(f"time inside the compiler's own functions: {total:.2f} s for {kinds} kinds")
for own, cumulative, calls, name, line in sorted(rows, reverse=True)[:12]:
    print(f"  {own:6.2f} s own  {cumulative:6.2f} s with callees  {calls:9} calls  {name} (line {line})")

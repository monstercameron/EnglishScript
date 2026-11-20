import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "Node is needed to exercise the playground JavaScript")
class PlaygroundPositions(unittest.TestCase):
    def test_highlights_and_selection_use_python_character_positions(self):
        script = r'''
const fs = require("fs");
const assert = require("assert");
const html = fs.readFileSync(process.argv[1], "utf8");
const painting = html.slice(html.indexOf("function characterOffset("), html.indexOf("\nfunction paint()"));
const selection = html.slice(html.indexOf("function goTo("), html.indexOf("\n// What a mark"));
assert(painting.startsWith("function characterOffset("));
assert(selection.startsWith("function goTo("));
globalThis.commentStart = () => Infinity;
globalThis.escapeHtml = text => text;
globalThis.source = {
  value: "", clientHeight: 10, focus() {},
  setSelectionRange(start, end) { this.start = start; this.end = end; },
};
globalThis.getComputedStyle = () => ({lineHeight: "10"});
globalThis.syncScroll = () => {};
eval(painting + "\n" + selection + `
  globalThis.checkPosition = (text, col, width) => {
    source.value = text;
    const problem = {line: 1, col, width, kind: "error"};
    const highlighted = paintLine(text, [problem]);
    goTo(problem);
    return {highlighted, selected: text.slice(source.start, source.end)};
  };
`);
for (const text of ['Say "é" then dragon.', 'Say "😀" then dragon.']) {
  const result = checkPosition(text, 13, 6);
  assert.strictEqual(result.selected, "dragon");
  assert(result.highlighted.includes('<span class="bad">dragon</span>'));
}
const emoji = checkPosition('Say "😀".', 5, 1);
assert.strictEqual(emoji.selected, "😀");
assert(emoji.highlighted.includes('bad">😀</span>'));
const end = checkPosition('Say "😀".', 8, 1);
assert.strictEqual(end.selected, "");
assert(end.highlighted.endsWith('<span class="bad"> </span>'));
'''
        result = subprocess.run(
            [NODE, "-e", script, str(ROOT / "docs" / "playground.html")],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

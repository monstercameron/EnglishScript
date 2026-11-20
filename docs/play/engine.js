// The EnglishScript compiler, running in the browser.
//
// The compiler is Python. Pyodide is Python built as WebAssembly, so this
// loads Pyodide, unpacks the englishscript package into it (play/englishscript.zip,
// made by tools/build_site.py), and calls it. Both pages of the site use this file.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
const HERE = new URL(".", import.meta.url);

// What a first visit fetches from the Pyodide distribution, with the size of
// each file in bytes once unpacked (they travel compressed, but a page can
// only count what it has unpacked). Used to show how far the download has got.
const RUNTIME = [
  ["pyodide.asm.wasm", 10088051],
  ["python_stdlib.zip", 2341872],
  ["pyodide.asm.js", 1229099],
  ["pyodide-lock.json", 106335],
];

// The Python side.
//
// play: run a program. When it asks a question nobody has answered yet, stop
// and say so. The page then asks the reader and runs the program again from
// the top with one more reply. Programs are deterministic, so replaying gives
// the same thing each time.
//
// check: every problem in a program, without running it.
//
// stock: write the chapters of the example books into the folder programs run
// in. A book is a folder, and _restore only clears loose files, so they stay.
const BRIDGE = `
import inspect, json, os, sys
sys.path.insert(0, "/site")
os.chdir("/work")
import englishscript
from englishscript import EnglishError, compile_source, explain

_kept = {}  # files left by the last finished run: name -> bytes


class _NeedsReply(BaseException):
    # Not an Exception: it must pass through everything between the question
    # and play() below, including the compiler's handling of a model that fails.
    def __init__(self, question):
        self.question = question


def _restore():
    for name in os.listdir("."):
        if os.path.isfile(name):
            os.remove(name)
    for name, data in _kept.items():
        with open(name, "wb") as handle:
            handle.write(data)


def _keep():
    _kept.clear()
    for name in os.listdir("."):
        if os.path.isfile(name):
            with open(name, "rb") as handle:
                _kept[name] = handle.read()


def stock(shelf):
    """Put the books of the shelf where programs can use them: /work/<book>/<chapter>.english."""
    for path, text in json.loads(shelf).items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)


def play(source, mode, replies, late=None):
    replies = iter(json.loads(replies))
    running = [True]
    events = []
    result = {"state": "done", "events": events}
    try:
        if mode == "explain":
            events.append(["explain", explain(source)])
            return json.dumps(result)
        program = compile_source(source)
        if mode == "check":
            events.append(["note", "Every sentence reads one way. Nothing was run."])
            return json.dumps(result)
        _restore()

        def out(text=""):
            # A page goes on answering clicks after the run is over. What it
            # says then goes straight to the page that is showing it.
            if running[0]:
                events.append(["say", text])
            elif late is not None:
                late(str(text))

        def ask(question):
            if not running[0]:
                return None  # nobody is asked once the run is over
            try:
                reply = next(replies)
            except StopIteration:
                raise _NeedsReply(question) from None
            events.append(["ask", question])
            if reply is None:
                events.append(["note", "No more input."])
                return None
            events.append(["reply", reply])
            return reply

        # There is no model in a browser, and no key to reach one. When a
        # program asks a model, or asks for a judgement, the reader answers as
        # the model would, through the same questions as "Ask".
        listeners = {}
        if "model" in inspect.signature(program.run).parameters:
            from englishscript.models import Person
            reader = Person(ask=ask, say=lambda text: events.append(["note", text]))
            listeners = {"model": reader.model, "judge": reader.judge}
        world = program.run(out, ask, **listeners)
        _keep()
        if world.examples:
            noun = "example" if world.examples == 1 else "examples"
            events.append(["note", f"{world.examples} {noun} checked."])
        if _kept:
            events.append(["note", "Kept for the next run: " + ", ".join(sorted(_kept)) + "."])
    except _NeedsReply as need:
        result["state"] = "waiting"
        result["question"] = need.question
    except EnglishError as error:
        result["state"] = "error"
        events.append(["error", error.render()])
    finally:
        running[0] = False
    return json.dumps(result)


def check(source):
    linter = getattr(englishscript, "lint", None)
    if linter is not None:
        return json.dumps([problem.as_dict() for problem in linter(source)])
    # An older compiler without a linter: report the first problem only.
    try:
        compile_source(source)
    except EnglishError as error:
        line = error.line
        return json.dumps([{
            "line": line.number if line else 1, "col": error.col, "width": error.width,
            "kind": "error", "message": error.message, "hint": error.hint,
            "sentence": line.text if line else "",
        }])
    return "[]"
`;

let engine = null;

class StartupError extends Error {}

async function startupStep(message, action) {
  try {
    return await action();
  } catch (error) {
    throw new StartupError(message);
  }
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const tag = document.createElement("script");
    tag.src = src;
    tag.onload = resolve;
    tag.onerror = () => { tag.remove(); reject(new Error("Script failed to load")); };
    document.head.append(tag);
  });
}

// Fetch the runtime's files once, counting bytes as they arrive, so that the
// page can show a measure of it. Pyodide then asks for the same addresses and
// the browser hands them over from its cache. If anything here fails it is
// ignored: Pyodide fetches the file itself, and reports it if it cannot.
async function fetchRuntime(report) {
  const total = RUNTIME.reduce((sum, [, size]) => sum + size, 0);
  const got = RUNTIME.map(() => 0);
  const tell = () => {
    const sum = Math.min(total, got.reduce((a, b) => a + b, 0));
    report(sum / total, sum, total);
  };
  await Promise.all(RUNTIME.map(async ([name, size], index) => {
    try {
      const response = await fetch(PYODIDE + name);
      if (!response.ok || !response.body) return;
      const reader = response.body.getReader();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        got[index] = Math.min(size, got[index] + value.length);
        tell();
      }
      got[index] = size;
      tell();
    } catch (error) { /* left to Pyodide */ }
  }));
}

// Wait until the page has drawn what it was just told to show. A page that is
// not being shown (a tab in the background) draws nothing, so do not wait long.
export function painted() {
  return new Promise((resolve) => {
    const giveUp = setTimeout(resolve, 150);
    requestAnimationFrame(() => { clearTimeout(giveUp); setTimeout(resolve, 30); });
  });
}

const megabytes = (bytes) => (bytes / 1048576).toFixed(1);

// Start Python and the compiler, once. `say(words, progress)` is told what is
// happening: `progress` has `step` and `steps` (which of how many), `overall`
// (how much of the whole start is done, from 0 to 1) and `note`, a few words
// such as "4.2 of 13.1 MB".
export function startEngine(say = () => {}) {
  if (!engine) {
    engine = (async () => {
      const steps = 4;
      await startupStep("WebAssembly is unavailable or disabled in this browser. Enable WebAssembly or try a current browser, then try again.", () => {
        if (typeof WebAssembly !== "object" || typeof WebAssembly.validate !== "function" || typeof WebAssembly.compile !== "function" ||
            !WebAssembly.validate(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0]))) throw new Error();
      });
      await startupStep("WebAssembly could not compile a program. Your browser or its security settings may be blocking it. Enable WebAssembly or try a current browser, then try again.",
        () => WebAssembly.compile(new Uint8Array([0, 97, 115, 109, 1, 0, 0, 0])));
      say("Fetching Python", { step: 1, steps, overall: 0, note: "the first time only" });
      await startupStep("The Pyodide loader (pyodide.js) could not be loaded. Check your connection and access to cdn.jsdelivr.net, then try again.", async () => {
        let reporting = true;
        try {
          await Promise.all([
            loadScript(PYODIDE + "pyodide.js"),
            fetchRuntime((fraction, got, total) => {
              if (reporting) say("Fetching Python", {
                step: 1, steps, overall: 0.7 * fraction, note: megabytes(got) + " of " + megabytes(total) + " MB",
              });
            }),
          ]);
          if (typeof globalThis.loadPyodide !== "function") throw new Error();
        } finally {
          reporting = false;
        }
      });
      say("Starting Python", { step: 2, steps, overall: 0.72 });
      const py = await startupStep("Pyodide could not start Python or load its runtime files. Check your connection and access to cdn.jsdelivr.net, then try again. If it still fails, try a current browser.",
        () => globalThis.loadPyodide({ indexURL: PYODIDE }));
      say("Fetching the compiler", { step: 3, steps, overall: 0.88 });
      const bundle = await startupStep("The compiler bundle (englishscript.zip) could not be downloaded. Check your connection, then try again. If it still fails, reload the page.", async () => {
        const response = await fetch(new URL("englishscript.zip", HERE));
        if (!response.ok) throw new Error();
        return response.arrayBuffer();
      });
      await startupStep("The compiler bundle (englishscript.zip) could not be unpacked. Reload the page and try again.", () => {
        py.FS.mkdirTree("/site");
        py.FS.mkdirTree("/work");
        py.unpackArchive(bundle, "zip", { extractDir: "/site" });
      });
      say("Reading the compiler", { step: 4, steps, overall: 0.94 });
      await new Promise((resolve) => setTimeout(resolve, 30));
      const bridge = await startupStep("The compiler or its library could not be initialized. Reload the page and try again.", () => {
        py.runPython(BRIDGE);
        const stock = py.globals.get("stock");
        const play = py.globals.get("play");
        const check = py.globals.get("check");
        if (typeof stock !== "function" || typeof play !== "function" || typeof check !== "function") throw new Error();
        return { stock, play, check };
      });
      const shelf = await startupStep("The example library (shelf.json) could not be loaded. Check your connection, then try again. If it still fails, reload the page.", async () => {
        const response = await fetch(new URL("shelf.json", HERE));
        if (!response.ok) throw new Error();
        return response.text();
      });
      await startupStep("The example library (shelf.json) could not be set up. Reload the page and try again.", () => bridge.stock(shelf));
      say("Ready", { step: steps, steps, overall: 1, done: true });
      return { play: bridge.play, check: bridge.check, py };
    })();
    const starting = engine;
    starting.catch(() => { if (engine === starting) engine = null; });
  }
  return engine;
}

const ROMAN = ["", "i", "ii", "iii", "iv", "v", "vi", "vii", "viii"];

// A loader in `box`. It gives back a function to hand to startEngine, play or
// lint as their `say`, and to call yourself:
//
//   say("Fetching Python", { step: 1, steps: 4, overall: 0.3, note: "4.2 of 13.1 MB" })
//   say("Running", {})          nothing to measure: a ribbon goes to and fro
//   say("Link copied.")         plain words, with nothing moving
//   say("")                     nothing
//
// With `grand`, it is drawn large, with an initial that is inked in as the
// work goes: for a page that has nothing else to show until the work is done.
export function loader(box, { grand = false, initial = "E" } = {}) {
  let parts = null;
  return (words, progress) => {
    if (!words || progress === undefined) {
      box.replaceChildren();
      parts = null;
      if (words) box.textContent = words;
      return;
    }
    if (!parts || !parts.root.isConnected) {
      const make = (css, hidden = true) => {
        const span = document.createElement("span");
        span.className = css;
        if (hidden) span.setAttribute("aria-hidden", "true");
        return span;
      };
      parts = { root: make("loader" + (grand ? " grand" : ""), false), letter: make("loader-initial"), mark: make("loader-mark"),
                words: make("loader-words", false), bar: make("loader-bar"), fill: make("loader-fill"), note: make("loader-note") };
      parts.letter.textContent = initial;
      parts.mark.textContent = "\u2766";
      parts.bar.append(parts.fill);
      parts.root.append(parts.letter, parts.mark, parts.words, parts.bar, parts.note);
      box.replaceChildren(parts.root);
    }
    // The words change seldom and the numbers often: only the words are read aloud.
    if (parts.words.textContent !== words) parts.words.textContent = words;
    const measured = typeof progress.overall === "number";
    parts.root.classList.toggle("unmeasured", !measured);
    parts.root.classList.toggle("done", Boolean(progress.done));
    const done = measured ? Math.max(0, Math.min(1, progress.overall)) : 0;
    parts.root.style.setProperty("--done", String(done));
    parts.root.style.setProperty("--inked", Math.round(18 + done * 66) + "%");
    const step = progress.step ? (ROMAN[progress.step] || progress.step) + " of " + (ROMAN[progress.steps] || progress.steps) : "";
    parts.note.textContent = [step, progress.note].filter(Boolean).join(" \u00b7 ");
  };
}

// Run a program (mode "run"), explain it ("explain") or only compile it ("check").
// `replies` are the answers given so far to its questions; null means "no more input".
// Gives { state: "done" | "waiting" | "error", events: [[kind, text]...], question? }.
// `late` is told each line a program says after its run is over, which only a
// program with a page does (see docs/PAGE.md).
export async function play(source, mode, replies, say = () => {}, late = null) {
  const python = await startEngine(say);
  say(mode === "explain" ? "Reading" : "Running", {});
  // Python runs on the page's own thread, so nothing is drawn until it is
  // done. Wait for the loader to be painted first; its motion then carries on.
  await painted();
  const result = JSON.parse(python.play(source, mode, JSON.stringify(replies), late));
  say("");
  return result;
}

// Every problem in a program, without running it:
// [{ line, col, width, kind: "error" | "warning", message, hint, sentence }...]
export async function lint(source, say = () => {}) {
  const python = await startEngine(say);
  return JSON.parse(python.check(source));
}

// Show what a program said in `box`.
export function show(box, events) {
  box.replaceChildren();
  for (const [kind, text] of events) addLine(box, kind, text);
}

// One more line of what a program said.
export function addLine(box, kind, text) {
  const line = document.createElement("div");
  line.className = "line " + (kind === "explain" ? "say" : kind);
  line.textContent = text;
  box.append(line);
}

export function failed(box, error) {
  const message = error instanceof StartupError ? error.message : "The program could not run. Try again; if it still fails, reload the page.";
  show(box, [["error", message]]);
}

// A program packed into the part of an address after "#p=", and back again.
export function toLink(text) {
  let binary = "";
  for (const byte of new TextEncoder().encode(text)) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function fromLink(code) {
  const binary = atob(code.replace(/-/g, "+").replace(/_/g, "/"));
  return new TextDecoder().decode(Uint8Array.from(binary, (char) => char.charCodeAt(0)));
}

export const escapeHtml = (text) => text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// Where a line's comment starts (a # outside quotes), or the line's length.
export function commentStart(line) {
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    if (line[i] === '"') quoted = !quoted;
    else if (line[i] === "#" && !quoted) return i;
  }
  return line.length;
}

// A program as HTML, with quoted text and comments coloured. The spaces that
// indent a line are wrapped so the page can widen them: in a book face a space
// is narrow, and the indent is what shows which sentences belong to a block.
export function tint(source) {
  return source.split("\n").map((line) => {
    const indent = line.match(/^ */)[0];
    const cut = Math.max(commentStart(line), indent.length);
    const lead = indent ? `<span class="in">${indent}</span>` : "";
    const code = escapeHtml(line.slice(indent.length, cut)).replace(/"(?:[^"]|"")*"/g, (text) => `<span class="s">${text}</span>`);
    const comment = cut < line.length ? `<span class="c">${escapeHtml(line.slice(cut))}</span>` : "";
    return lead + code + comment;
  }).join("\n");
}

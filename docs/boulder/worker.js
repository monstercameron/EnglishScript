const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
let python;
let act;
let started = false;
let accepting = false;
let nextRequest = 0;
const pending = new Map();

function report(error) {
  self.postMessage({ type: "error", message: String(error && error.message || error) });
}

self.boulderFrame = (width, height, pixels) => {
  let view;
  try {
    view = typeof pixels.getBuffer === "function" ? pixels.getBuffer("u8") : null;
    const source = view ? view.data : pixels;
    const bytes = Uint8Array.from(source);
    self.postMessage({ type: "frame", width, height, pixels: bytes.buffer }, [bytes.buffer]);
  } finally {
    if (view) view.release();
    if (typeof pixels.destroy === "function") pixels.destroy();
  }
};
self.boulderState = (state) => self.postMessage({ type: "state", ...JSON.parse(state) });
self.boulderOutput = (text) => self.postMessage({ type: "output", text });
self.boulderComplete = () => self.postMessage({ type: "complete" });
self.boulderError = (message) => self.postMessage({ type: "error", message });
self.boulderReady = () => {
  if (!accepting) {
    accepting = true;
    self.postMessage({ type: "ready" });
  }
};
self.boulderRequest = (prompt) => new Promise((resolve) => {
  const id = ++nextRequest;
  pending.set(id, resolve);
  self.postMessage({ type: "request", id, prompt });
});

async function start() {
  if (started) return;
  started = true;
  importScripts(PYODIDE + "pyodide.js");
  python = await loadPyodide({ indexURL: PYODIDE });
  const paths = ["main.english", "field.english", "scene.english", "bridge.py"];
  const [archive, ...files] = await Promise.all([
    fetch(new URL("../play/englishscript.zip", self.location.href)),
    ...paths.map((path) => fetch(new URL(path, self.location.href))),
  ]);
  if (!archive.ok || files.some((file) => !file.ok)) throw new Error("Could not load the compiler or Boulder chapters.");
  python.FS.mkdirTree("/site");
  python.FS.mkdirTree("/work");
  python.unpackArchive(await archive.arrayBuffer(), "zip", { extractDir: "/site" });
  const texts = await Promise.all(files.map((file) => file.text()));
  paths.slice(0, -1).forEach((path, index) => python.FS.writeFile("/work/" + path, texts[index]));
  python.runPython(texts[texts.length - 1]);
  act = python.globals.get("act");
  const run = python.globals.get("start");
  try {
    await run();
  } finally {
    run.destroy();
  }
}

self.onmessage = (event) => {
  const message = event.data || {};
  if (message.type === "start") {
    start().catch(report);
  } else if (message.type === "reply") {
    const resolve = pending.get(message.id);
    if (resolve) {
      pending.delete(message.id);
      resolve(String(message.text ?? ""));
    }
  } else if (message.type === "action" && accepting &&
             ["up", "down", "left", "right"].includes(message.action)) {
    try {
      act(message.action);
    } catch (error) {
      report(error);
    }
  }
};


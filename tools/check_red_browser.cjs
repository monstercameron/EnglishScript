const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const [
  edge,
  work,
  replayPath,
  baseUrl = "http://127.0.0.1:8767/red/",
  output = work,
] = process.argv.slice(2);
if (!edge || !work || !replayPath)
  throw new Error(
    "Usage: node tools/check_red_browser.cjs <edge-executable> <temporary-directory> <replay.json> [base-url] [award-output-directory]",
  );
fs.mkdirSync(work, { recursive: true });
fs.mkdirSync(output, { recursive: true });
const profile = fs.mkdtempSync(path.join(work, "red-edge-"));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, label, timeout = 120000) {
  let end = Date.now() + timeout;
  while (Date.now() < end) {
    let x = await fn();
    if (x) return x;
    await sleep(30);
  }
  throw Error("Timed out: " + label);
}
async function main() {
  const browser = spawn(
    edge,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-first-run",
      "--remote-debugging-port=0",
      `--user-data-dir=${profile}`,
      "about:blank",
    ],
    { stdio: "ignore" },
  );
  try {
    const port = await until(() => {
      try {
        return fs
          .readFileSync(path.join(profile, "DevToolsActivePort"), "utf8")
          .split("\n")[0];
      } catch {
        return null;
      }
    }, "DevTools");
    const target = await (
      await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, {
        method: "PUT",
      })
    ).json();
    const ws = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((r, j) => {
      ws.onopen = r;
      ws.onerror = j;
    });
    let id = 0;
    const pending = new Map();
    ws.onmessage = (e) => {
      let m = JSON.parse(e.data);
      if (!m.id) return;
      let p = pending.get(m.id);
      if (!p) return;
      pending.delete(m.id);
      m.error ? p.reject(Error(m.error.message)) : p.resolve(m.result);
    };
    const send = (method, params = {}) =>
      new Promise((resolve, reject) => {
        let n = ++id;
        pending.set(n, { resolve, reject });
        ws.send(JSON.stringify({ id: n, method, params }));
      });
    const ev = async (expression) => {
      let r = await send("Runtime.evaluate", {
        expression,
        returnByValue: true,
        awaitPromise: true,
      });
      if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails));
      return r.result.value;
    };
    let screenshotWidth = 1280;
    const screenshot = async (filename) => {
      let metrics = await send("Page.getLayoutMetrics"),
        s = metrics.cssContentSize;
      // Headless Edge may wait indefinitely for a compositor frame while idle.
      // A small viewport nudge requests one without changing game state.
      const nudge = setTimeout(() => {
        screenshotWidth = screenshotWidth === 1280 ? 1281 : 1280;
        send("Emulation.setDeviceMetricsOverride", {
          width: screenshotWidth,
          height: 1000,
          deviceScaleFactor: 1,
          mobile: false,
        }).catch(() => {});
      }, 3000);
      let image;
      let timeout;
      try {
        image = await Promise.race([
          send("Page.captureScreenshot", {
            format: "png",
            captureBeyondViewport: true,
            clip: {
              x: 0,
              y: 0,
              width: Math.ceil(s.width),
              height: Math.ceil(s.height),
              scale: 1,
            },
          }),
          new Promise(
            (_, reject) =>
              (timeout = setTimeout(
                () => reject(Error("Screenshot timed out")),
                30000,
              )),
          ),
        ]);
      } finally {
        clearTimeout(nudge);
        clearTimeout(timeout);
      }
      fs.writeFileSync(filename, Buffer.from(image.data, "base64"));
    };
    await send("Runtime.enable");
    await send("Page.enable");
    await send("Emulation.setDeviceMetricsOverride", {
      width: 1280,
      height: 1000,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await send("Page.addScriptToEvaluateOnNewDocument", {
      source: `window.testEvents=[]; window.testState={}; const NativeWorker=window.Worker; window.Worker=class extends NativeWorker { constructor(...args){super(...args);this.addEventListener('message', e=>{if(e.data.type==='state')window.testState=e.data.state; if(e.data.type==='ack'||e.data.type==='error')window.testEvents.push(e.data);});} };`,
    });
    await send("Page.navigate", { url: baseUrl });
    await until(
      async () => {
        let x = await ev(
          '({state:window.testState,conn:document.querySelector("#connection")?.textContent})',
        );
        if (
          await ev(
            "document.querySelector('#display-status')?.textContent === 'STOPPED'",
          )
        )
          throw Error(JSON.stringify(x));
        return x.state.mode === "opening" && x.conn.startsWith("Playing");
      },
      "initial opening",
      180000,
    );
    const actions = JSON.parse(fs.readFileSync(replayPath, "utf8"));
    if (!Array.isArray(actions)) throw Error("Expected array of actions");
    const keys = {
      up: ["ArrowUp", 38],
      down: ["ArrowDown", 40],
      left: ["ArrowLeft", 37],
      right: ["ArrowRight", 39],
      a: ["z", 90],
      b: ["x", 88],
      start: ["Enter", 13],
      select: ["Shift", 16],
    };
    let taken = new Set(),
      last = "";
    const durations = [];
    for (let i = 0; i < actions.length; i++) {
      const started = performance.now();
      let action = actions[i];
      if (!keys[action]) throw Error(`Unsupported action ${i} ${action}`);
      let [key, code] = keys[action];
      let before = await ev("window.testEvents.length");
      await send("Input.dispatchKeyEvent", {
        type: "keyDown",
        key,
        code: key.startsWith("Arrow") ? key : undefined,
        windowsVirtualKeyCode: code,
      });
      await send("Input.dispatchKeyEvent", {
        type: "keyUp",
        key,
        code: key.startsWith("Arrow") ? key : undefined,
        windowsVirtualKeyCode: code,
      });
      await until(
        async () => {
          let events = await ev(`window.testEvents.slice(${before})`);
          let error = events.find((x) => x.type === "error");
          if (error) throw Error(JSON.stringify(error));
          return events.some((x) => x.type === "ack" && x.action === action);
        },
        `ack ${i} ${action}`,
        30000,
      );
      durations.push(performance.now() - started);
      let state = await ev("window.testState");
      let marker =
        state.place +
        " / " +
        state.mode +
        " / " +
        state.stage +
        " / " +
        state.opponent;
      if (marker !== last) {
        console.log(i, marker, state.column, state.row, state.message);
        last = marker;
      }
      let name =
        state.mode === "title"
          ? "title"
          : state.place === "Bedroom" && state.mode === "walk"
            ? "bedroom"
            : state.place === "Viridian Forest" && state.mode === "walk"
              ? "forest"
              : state.place === "Pewter Gym" && state.mode === "battle"
                ? "brock"
                : Number(state.badge)
                  ? "badge"
                  : null;
      if (name && !taken.has(name)) {
        if (name === "bedroom")
          console.log("BEDROOM_TRANSITION_ACK_MS", durations.at(-1));
        taken.add(name);
        await screenshot(path.join(work, `red-${name}.png`));
        console.log("captured", name, i);
        if (name === "badge")
          fs.copyFileSync(
            path.join(work, "red-badge.png"),
            path.join(output, "Boulder Badge earned.png"),
          );
      }
    }
    let state = await ev(
      '({state:window.testState,badge:document.querySelector("#badge").textContent,objective:document.querySelector("#objective").textContent,canvas:[document.querySelector("#screen").width,document.querySelector("#screen").height],status:document.querySelector("#display-status").textContent})',
    );
    console.log("FINAL", JSON.stringify(state));
    if (
      !Number(state.state.badge) ||
      !Number(state.state.tm34) ||
      state.badge !== "Boulder Badge earned" ||
      state.objective !== "Brock awarded you the Boulder Badge and TM34." ||
      state.canvas.join(",") !== "160,144" ||
      state.status !== "LIVE"
    )
      throw Error("Badge verification failed");
    await screenshot(path.join(output, "Boulder Badge earned.png"));
    await send("Page.reload", { ignoreCache: true });
    await until(
      async () => {
        const restored = await ev(
          '({badge: window.testState?.badge, tm34: window.testState?.tm34, objective: document.querySelector("#objective")?.textContent, status: document.querySelector("#display-status")?.textContent, connection: document.querySelector("#connection")?.textContent})',
        );
        if (restored.status === "STOPPED")
          throw Error(`Reload failed: ${JSON.stringify(restored)}`);
        return (
          Number(restored.badge) === 1 &&
          Number(restored.tm34) === 1 &&
          restored.objective ===
            "Brock awarded you the Boulder Badge and TM34." &&
          restored.status === "LIVE" &&
          restored.connection.startsWith("Playing")
        );
      },
      "restored badge after reload",
      300000,
    );
    console.log("RELOAD_RESTORED_BADGE");
    for (const milestone of ["title", "bedroom", "forest", "brock", "badge"]) {
      if (!taken.has(milestone)) throw Error(`Missing milestone: ${milestone}`);
    }
    durations.sort((a, b) => a - b);
    console.log(
      "ACTION_TIMING_MS",
      JSON.stringify({
        mean: durations.reduce((a, b) => a + b, 0) / durations.length,
        median: durations[Math.floor(durations.length / 2)],
        p95: durations[Math.floor(durations.length * 0.95)],
        max: durations.at(-1),
        note: "Includes key dispatch and ack polling; excludes screenshots",
      }),
    );
    console.log("MILESTONES", JSON.stringify([...taken]));
    ws.close();
  } finally {
    browser.kill();
    if (browser.exitCode === null)
      await new Promise((r) => browser.once("exit", r));
    fs.rmSync(profile, { recursive: true, force: true });
  }
}
main().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');

const browserPath = process.argv[2];
const profileParent = process.argv[3];
if (!browserPath || !profileParent) throw new Error('Usage: node tools/check_boulder_browser.cjs <edge-executable> <temporary-profile-parent>');
const root = path.resolve(__dirname, '..', 'docs');
const temporaryRoot = path.resolve(profileParent);
const profile = fs.mkdtempSync(path.join(temporaryRoot, 'boulder-edge-'));
if (!profile.startsWith(temporaryRoot + path.sep)) throw new Error('Profile is outside the temporary directory');
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.wasm': 'application/wasm', '.english': 'text/plain' };
const server = http.createServer((req, res) => {
  const relative = decodeURIComponent(new URL(req.url, 'http://localhost').pathname).replace(/^\/+/, '');
  const file = path.resolve(root, relative);
  if (!file.startsWith(root + path.sep)) { res.writeHead(403).end(); return; }
  fs.readFile(file, (error, data) => {
    if (error) { res.writeHead(404).end(); return; }
    res.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream' }).end(data);
  });
});

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, label, timeout = 30000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    const value = await fn();
    if (value) return value;
    await sleep(100);
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function main() {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = spawn(browserPath, ['--headless=new', '--disable-gpu', '--no-first-run', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { stdio: 'ignore' });
  try {
    const port = await until(() => {
      try { return fs.readFileSync(path.join(profile, 'DevToolsActivePort'), 'utf8').split('\n')[0]; } catch { return null; }
    }, 'Edge DevTools');
    const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' })).json();
    const socket = new WebSocket(target.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
    let id = 0;
    const pending = new Map();
    socket.onmessage = event => {
      const message = JSON.parse(event.data);
      if (!message.id) return;
      const entry = pending.get(message.id);
      if (!entry) return;
      pending.delete(message.id);
      if (message.error) entry.reject(new Error(message.error.message));
      else entry.resolve(message.result);
    };
    const send = (method, params = {}) => new Promise((resolve, reject) => {
      const next = ++id;
      pending.set(next, { resolve, reject });
      socket.send(JSON.stringify({ id: next, method, params }));
    });
    const evaluate = async expression => {
      const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
      if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
      return result.result.value;
    };
    const screenshot = async name => {
      const metrics = await send('Page.getLayoutMetrics');
      const size = metrics.cssContentSize;
      const capture = await send('Page.captureScreenshot', {
        format: 'png', captureBeyondViewport: true,
        clip: { x: 0, y: 0, width: Math.ceil(size.width), height: Math.ceil(size.height), scale: 1 },
      });
      fs.writeFileSync(path.join(temporaryRoot, name), Buffer.from(capture.data, 'base64'));
    };
    await send('Runtime.enable');
    await send('Page.enable');
    await send('Page.addScriptToEvaluateOnNewDocument', { source: `
      window.boulderSmoke = [];
      const NativeWorker = window.Worker;
      window.Worker = class extends NativeWorker {
        constructor(...args) {
          super(...args);
          this.addEventListener('message', event => window.boulderSmoke.push(event.data));
        }
        postMessage(message, ...args) {
          window.boulderSmoke.push({sent: message.type});
          return super.postMessage(message, ...args);
        }
      };
    ` });
    await send('Page.navigate', { url: `http://127.0.0.1:${server.address().port}/boulder/index.html` });
    await until(() => evaluate('!!document.querySelector("#screen")'), 'page markup');
    const screenBox = () => evaluate('(() => { const r = document.querySelector("#screen").getBoundingClientRect(); return [r.width, r.height]; })()');
    const beforeFrame = await screenBox();
    await until(async () => {
      const status = await evaluate('({ connection: document.querySelector("#connection")?.textContent, activity: document.querySelector("#activity")?.textContent, canvas: !!document.querySelector("#screen canvas") })');
      if (status.connection === 'Stopped') throw new Error(status.activity);
      return status.connection === 'Waiting for reply' && status.canvas;
    }, 'initial frame and pending request', 120000);
    const afterFrame = await screenBox();
    if (beforeFrame.some((value, index) => Math.abs(value - afterFrame[index]) > 1)) throw new Error(`First frame shifted the display: ${beforeFrame} to ${afterFrame}`);
    const size = await evaluate('(() => { const c = document.querySelector("#screen canvas"); return [c.width, c.height]; })()');
    if (size[0] !== 160 || size[1] !== 144) throw new Error(`Unexpected canvas size: ${size}`);
    await send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
    const layout = await evaluate('({ viewport: innerWidth, page: document.documentElement.scrollWidth, canvas: document.querySelector("#screen canvas").getBoundingClientRect().width })');
    if (layout.page > layout.viewport || layout.canvas > layout.viewport) throw new Error(`Mobile layout overflows: ${JSON.stringify(layout)}`);
    await screenshot('boulder-mobile.png');
    await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });
    const pixels = () => evaluate(`(() => {
      const c = document.querySelector('#screen canvas');
      const bytes = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
      let result = '';
      for (let i = 0; i < bytes.length; i += 8192) result += String.fromCharCode(...bytes.subarray(i, i + 8192));
      return btoa(result);
    })()`);
    const initial = await pixels();
    await evaluate('document.querySelector("[data-action=right]").click()');
    await until(async () => await pixels() !== initial, 'movement while the request is pending', 4000);
    const firstMove = await pixels();
    if (await evaluate('document.querySelector("#connection").textContent') !== 'Waiting for reply') throw new Error('Reply completed before movement was observed');
    await evaluate('document.querySelector("[data-action=right]").focus()');
    const beforePadKey = await pixels();
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    await until(async () => await pixels() !== beforePadKey, 'keyboard movement from direction control', 4000);
    await evaluate('document.querySelector("#restart").focus()');
    const beforeKey = await pixels();
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    await sleep(300);
    if (await pixels() !== beforeKey) throw new Error('Arrow key moved the field while a control had focus');
    await until(() => evaluate('window.boulderSmoke.some(item => item.sent === "reply") && window.boulderSmoke.some(item => item.type === "state" && item.result === "Calibration complete. Keep exploring.") && window.boulderSmoke.some(item => item.type === "complete") && document.querySelector("#connection").textContent === "Ready"'), 'recorded reply applied in world');
    await evaluate('document.activeElement.blur()');
    const beforeMove = await pixels();
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    await until(async () => await pixels() !== beforeMove, 'keyboard movement after the reply');
    await evaluate('window.scrollTo(0, 0)');
    await screenshot('boulder-desktop.png');
    const restartPosition = await evaluate(`(() => {
      const button = document.querySelector('#restart');
      button.scrollIntoView({ block: 'center' });
      const rect = button.getBoundingClientRect();
      return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
    })()`);
    await send('Input.dispatchMouseEvent', { type: 'mouseMoved', ...restartPosition });
    await send('Input.dispatchMouseEvent', { type: 'mousePressed', button: 'left', clickCount: 1, ...restartPosition });
    await send('Input.dispatchMouseEvent', { type: 'mouseReleased', button: 'left', clickCount: 1, ...restartPosition });
    await until(() => evaluate('document.querySelector("#connection").textContent === "Waiting for reply" && !!document.querySelector("#screen canvas")'), 'restarted field', 120000);
    if (await pixels() !== initial) throw new Error('Restart did not restore the original canvas');
    await until(() => evaluate('document.querySelector("#connection").textContent === "Ready"'), 'restarted field ready', 30000);
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 });
    await until(async () => await pixels() !== initial, 'first keyboard movement after restart', 4000);
    if (await pixels() !== firstMove) throw new Error('Keyboard input after restart produced a different canvas');
    console.log('Canvas size, mobile layout, pending request movement, keyboard isolation, applied reply, restart, and first keyboard movement after restart passed.');
    socket.close();
  } finally {
    browser.kill();
    await new Promise(resolve => server.close(resolve));
    if (browser.exitCode === null) await new Promise(resolve => browser.once('exit', resolve));
    fs.rmSync(profile, { recursive: true, force: true });
  }
}

main().catch(error => { console.error(error); process.exitCode = 1; });

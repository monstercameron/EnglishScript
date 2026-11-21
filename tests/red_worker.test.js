const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = name => fs.readFileSync(path.join(root, 'docs', name), 'utf8');
const settle = () => new Promise(resolve => setTimeout(resolve, 5));

function worker({ chapters = { 'main.english': 'Say "hi".', 'field.english': 'A field.' }, replayFails = false, fetchFails, runtime, runtimePatience } = {}) {
  const messages = [], requests = [], replays = [], timeouts = [];
  const python = {
    FS: { mkdirTree() {}, writeFile() {} },
    unpackArchive() {},
    runPython() {},
    globals: { get: name => functions[name] || (() => {}) },
  };
  const start = async () => context.redReady();
  start.destroy = () => {};
  const functions = {
    start,
    replay: history => { if (replayFails) throw Error('The program stopped.'); replays.push(JSON.parse(history)); },
  };
  const fetch = async (url, options) => {
    requests.push({ url: String(url), options });
    if (fetchFails) throw fetchFails;
    const name = new URL(url).pathname.split('/').pop();
    return { ok: true, status: 200, json: async () => Object.keys(chapters), text: async () => chapters[name] ?? '', arrayBuffer: async () => new ArrayBuffer(0) };
  };
  const AbortSignal = Object.assign(function AbortSignal() {}, { timeout: milliseconds => { timeouts.push(milliseconds); return { milliseconds }; } });
  const context = {
    URL, Uint8Array, WebAssembly, setTimeout, clearTimeout, AbortSignal, fetch,
    location: { href: 'https://example.test/red/worker.js' },
    postMessage: message => messages.push(JSON.parse(JSON.stringify(message))),
    importScripts(url) {
      if (!String(url).endsWith('worker-start.js')) return;
      vm.runInContext(source('play/worker-start.js'), context);
      if (runtimePatience) context.workerStart.runtimePatience = runtimePatience;
    },
    loadPyodide: async () => runtime ? runtime() : python,
  };
  context.self = context;
  vm.createContext(context);
  vm.runInContext(source('red/worker.js'), context);
  const finished = async () => {
    const deadline = Date.now() + 2000;
    while (!messages.some(message => ['ready', 'changed', 'error', 'restore-failed'].includes(message.type)) && Date.now() < deadline) await settle();
  };
  return {
    messages, requests, replays, timeouts,
    async start(history = [], content) { context.onmessage({ data: { type: 'start', history, content, offersChoice: true } }); await finished(); },
    async startFromOldPage(history) { context.onmessage({ data: { type: 'start', history } }); await finished(); },
    send: data => context.onmessage({ data }),
    last: () => messages.at(-1),
  };
}

test('every chapter, manifest, bridge and compiler download is revalidated and has a deadline', async () => {
  const game = worker();
  await game.start();
  assert.deepEqual(game.requests.map(request => request.url.split('/').pop()).sort(), ['bridge.py', 'chapters.json', 'englishscript.zip', 'field.english', 'main.english']);
  for (const request of game.requests) {
    assert.equal(request.options.cache, 'no-cache', request.url);
    assert.ok(request.options.signal, request.url);
  }
  assert.ok(game.timeouts.every(milliseconds => milliseconds === 60000));
});

test('a download that hangs reports how long the worker waited', async () => {
  const game = worker({ fetchFails: Object.assign(new Error('timed out'), { name: 'TimeoutError' }) });
  await game.start();
  assert.equal(game.last().type, 'error');
  assert.match(game.last().message, /chapters\.json: the server did not answer within 60 seconds/);
});

test('ready reports a fingerprint that follows the chapter text', async () => {
  const first = worker(), same = worker(), changed = worker({ chapters: { 'main.english': 'Say "hello".', 'field.english': 'A field.' } });
  for (const game of [first, same, changed]) await game.start();
  const fingerprint = game => game.messages.find(message => message.type === 'ready').content;
  assert.match(fingerprint(first), /^[0-9a-f]{16}$/);
  assert.equal(fingerprint(first), fingerprint(same));
  assert.notEqual(fingerprint(first), fingerprint(changed));
});

test('a save with the current fingerprint is replayed at once', async () => {
  const probe = worker();
  await probe.start();
  const content = probe.last().content;
  const game = worker();
  await game.start(['a', 'b'], content);
  assert.deepEqual(game.replays, [['a', 'b']]);
  assert.deepEqual(game.last(), { type: 'ready', content });
});

for (const [name, content] of [['changed', '0000000000000000'], ['older', undefined]]) {
  test(`a ${name} save waits for the player before it is replayed`, async () => {
    const game = worker();
    await game.start(['a', 'b'], content);
    assert.equal(game.last().type, 'changed');
    assert.deepEqual(game.replays, []);
    game.send({ type: 'restore', history: ['a', 'b'] });
    assert.deepEqual(game.replays, [['a', 'b']]);
    assert.equal(game.last().type, 'ready');
    game.send({ type: 'restore', history: ['a'] });
    assert.equal(game.replays.length, 1);
  });
}

test('a save that cannot be replayed is reported as a restore failure', async () => {
  const probe = worker();
  await probe.start();
  const game = worker({ replayFails: true });
  await game.start(['a'], probe.last().content);
  assert.deepEqual(game.last(), { type: 'restore-failed', message: 'The program stopped.' });
});

test('the red worker no longer forwards program output', () => {
  assert.doesNotMatch(source('red/worker.js'), /redOutput|'output'/);
});

test('a page from before fingerprints is restored without asking, so it never stalls', async () => {
  const game = worker();
  await game.startFromOldPage(['a', 'b']);
  assert.deepEqual(game.replays, [['a', 'b']]);
  assert.equal(game.last().type, 'ready');
});

test('a Python runtime that never loads is reported instead of hanging', async () => {
  const game = worker({ runtime: () => new Promise(() => {}), runtimePatience: 0.02 });
  await game.start();
  assert.equal(game.last().type, 'error');
  assert.match(game.last().message, /Python runtime didn't load within 0\.02 seconds/);
  assert.match(game.last().message, /reload/);
});

test('a Python runtime that fails to load is still reported as a failure', async () => {
  const game = worker({ runtime: async () => { throw Error('runtime exploded'); } });
  await game.start();
  assert.match(game.last().message, /Could not initialize Pyodide/);
});

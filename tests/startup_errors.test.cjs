const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = name => fs.readFileSync(path.join(root, 'docs', name), 'utf8');
const tick = () => new Promise(resolve => setTimeout(resolve, 5));

function fakePython(state, ready) {
  const run = async () => { if (state.fail === 'run') throw Error('program exploded'); ready(); };
  run.destroy = () => {};
  const play = () => { throw Error('program exploded'); };
  const check = () => '[]';
  const act = () => { if (state.fail === 'action') throw Error('program exploded'); };
  const noop = () => {};
  const functions = { start: run, play, check, act };
  return {
    FS: { mkdirTree() {}, writeFile() {} },
    unpackArchive() { if (state.fail === 'unpack') throw Error('bad archive'); },
    runPython() { if (state.fail === 'init') throw Error('bad package'); },
    globals: { get(name) { return functions[name] || noop; } },
  };
}

function response(url, state) {
  const name = new URL(url).pathname.split('/').pop();
  const failed = name === state.fail;
  return {
    ok: !failed,
    status: failed ? 404 : 200,
    body: null,
    arrayBuffer: async () => new ArrayBuffer(0),
    text: async () => name === 'shelf.json' ? '{}' : '',
    json: async () => ['main.english', 'field.english'],
  };
}

function engineHarness() {
  const state = {};
  const context = {
    URL, Uint8Array, WebAssembly, setTimeout, clearTimeout,
    requestAnimationFrame: callback => callback(),
    fetch: async url => response(url, state),
    document: {
      createElement: () => ({ remove() {} }),
      head: { append(tag) { if (state.fail === 'loader') tag.onerror(); else tag.onload(); } },
    },
  };
  context.loadPyodide = async () => {
    if (state.fail === 'runtime') throw Error('runtime exploded');
    return fakePython(state, () => {});
  };
  vm.createContext(context);
  const code = source('play/engine.js').replace('import.meta.url', '"https://example.test/play/engine.js"').replace(/export /g, '');
  vm.runInContext(code + '\nglobalThis.api = { startEngine, play, failed };', context);
  return { state, context, api: context.api };
}

function workerHarness(name) {
  const state = {};
  const messages = [];
  const context = {
    URL, Uint8Array, WebAssembly, setTimeout, clearTimeout,
    location: { href: `https://example.test/${name}/worker.js` },
    postMessage: message => messages.push(message),
    importScripts(url) {
      if (String(url).endsWith('worker-start.js')) vm.runInContext(source('play/worker-start.js'), context);
      else if (state.fail === 'loader') throw Error('loader exploded');
    },
    fetch: async url => response(url, state),
  };
  context.self = context;
  context.loadPyodide = async () => {
    if (state.fail === 'runtime') throw Error('runtime exploded');
    return fakePython(state, () => context[name === 'red' ? 'redReady' : 'boulderReady']());
  };
  vm.createContext(context);
  vm.runInContext(source(`${name}/worker.js`), context);
  return { state, context, messages, async start() {
    context.onmessage({ data: { type: 'start', history: [] } });
    const deadline = Date.now() + 2000;
    while (!messages.some(message => message.type === 'ready' || message.type === 'error') && Date.now() < deadline) await tick();
    assert.ok(messages.some(message => message.type === 'ready' || message.type === 'error'), 'worker did not finish startup');
  } };
}

function errorText(messages) {
  return messages.filter(message => message.type === 'error').map(message => message.message).join(' ');
}

test('engine startup failures identify the failed stage and allow retry', async t => {
  for (const [failure, expected] of [
    ['wasm', /webassembly/i], ['loader', /loader/i], ['runtime', /python/i],
    ['englishscript.zip', /compiler/i], ['unpack', /unpack/i], ['init', /initializ/i], ['shelf.json', /library/i],
  ]) await t.test(failure, async () => {
    const { state, context, api } = engineHarness();
    state.fail = failure;
    if (failure === 'wasm') context.WebAssembly = undefined;
    await assert.rejects(api.startEngine(), expected);
    state.fail = null;
    context.WebAssembly = WebAssembly;
    await assert.doesNotReject(api.startEngine());
  });
});

test('engine distinguishes startup errors from program errors', async () => {
  const { state, context, api } = engineHarness();
  const box = { replaceChildren() { this.children = []; }, append(child) { this.children.push(child); } };
  state.fail = 'runtime';
  let startup;
  try { await api.startEngine(); } catch (error) { startup = error; }
  api.failed(box, startup);
  assert.match(box.children[0].textContent, /python/i);
  state.fail = null;
  let program;
  try { await api.play('bad', 'run', []); } catch (error) { program = error; }
  assert.match(program.message, /program exploded/);
  api.failed(box, program);
  assert.match(box.children[0].textContent, /program/i);
  assert.doesNotMatch(box.children[0].textContent, /python/i);
});

for (const name of ['boulder', 'red']) {
  test(`${name} worker reports startup failures and recovers after reload`, async t => {
    const failures = [
      ['wasm', /webassembly/i], ['wasm-blocked', /webassembly/i],
      ['loader', /loader|python/i], ['runtime', /python|pyodide/i],
      ['englishscript.zip', /compiler/i], ['bridge.py', /chapter|script|bridge/i],
      ['main.english', /chapter/i], ['unpack', /unpack/i], ['init', /initializ|compiler|bridge/i],
    ];
    if (name === 'red') failures.push(['chapters.json', /chapter/i]);
    for (const [failure, expected] of failures) await t.test(failure, async () => {
      const worker = workerHarness(name);
      worker.state.fail = failure;
      if (failure === 'wasm') worker.context.WebAssembly = undefined;
      if (failure === 'wasm-blocked') worker.context.WebAssembly = { compile: async () => { throw Error('blocked'); } };
      await worker.start();
      assert.match(errorText(worker.messages), expected);
      assert.match(errorText(worker.messages), /reload/i);
      if (failure.endsWith('.zip') || failure.endsWith('.py') || failure.endsWith('.english') || failure.endsWith('.json')) {
        assert.ok(errorText(worker.messages).includes(failure));
        assert.match(errorText(worker.messages), /404/);
      }
      const reloaded = workerHarness(name);
      await reloaded.start();
      assert.ok(reloaded.messages.some(message => message.type === 'ready'), JSON.stringify(reloaded.messages));
    });
  });
}

for (const name of ['boulder', 'red']) {
  test(`${name} worker reports program errors after startup`, async () => {
    const worker = workerHarness(name);
    await worker.start();
    assert.ok(worker.messages.some(message => message.type === 'ready'));
    worker.messages.length = 0;
    worker.state.fail = 'action';
    worker.context.onmessage({ data: { type: 'action', action: 'up' } });
    assert.match(errorText(worker.messages), /program exploded/);
    assert.doesNotMatch(errorText(worker.messages), /startup|initialize|download/i);
  });
}

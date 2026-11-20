const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
let python, act, replay, talkOpen, talkAsk, talkReply, talkPage, talkClose, started = false, accepting = false;
function report(error) { self.postMessage({ type: 'error', message: String(error && error.message || error) }); }
self.redFrame = (width, height, pixels) => {
  let view;
  try {
    view = typeof pixels.getBuffer === 'function' ? pixels.getBuffer('u8') : null;
    const bytes = Uint8Array.from(view ? view.data : pixels);
    self.postMessage({ type: 'frame', width, height, pixels: bytes.buffer }, [bytes.buffer]);
  } finally {
    if (view) view.release();
    if (typeof pixels.destroy === 'function') pixels.destroy();
  }
};
self.redState = state => self.postMessage({ type: 'state', state: JSON.parse(state) });
self.redOutput = text => self.postMessage({ type: 'output', text });
self.redError = message => report(message);
self.redReady = () => { accepting = true; };
async function start(history) {
  if (started) return;
  started = true;
  importScripts(PYODIDE + 'pyodide.js');
  python = await loadPyodide({ indexURL: PYODIDE });
  const manifest = await fetch(new URL('chapters.json', self.location.href));
  if (!manifest.ok) throw new Error('Could not load the adventure chapters.');
  const paths = await manifest.json();
  if (!Array.isArray(paths) || !paths.includes('main.english') || paths.some(path => typeof path !== 'string' || !/^[a-zA-Z0-9_./-]+\.english$/.test(path) || path.includes('..'))) throw new Error('The adventure chapter list is invalid.');
  const [archive, bridge, ...files] = await Promise.all([
    fetch(new URL('../play/englishscript.zip', self.location.href)),
    fetch(new URL('bridge.py', self.location.href)),
    ...paths.map(path => fetch(new URL(path, self.location.href)))
  ]);
  if (!archive.ok || !bridge.ok || files.some(file => !file.ok)) throw new Error('Could not load the compiler or adventure chapters.');
  python.FS.mkdirTree('/site');
  python.FS.mkdirTree('/work');
  python.unpackArchive(await archive.arrayBuffer(), 'zip', { extractDir: '/site' });
  for (let i = 0; i < paths.length; i++) {
    const target = '/work/' + paths[i];
    const slash = target.lastIndexOf('/');
    python.FS.mkdirTree(target.slice(0, slash));
    python.FS.writeFile(target, await files[i].text());
  }
  python.runPython(await bridge.text());
  act = python.globals.get('act');
  replay = python.globals.get('replay');
  talkOpen = python.globals.get('talk_open');
  talkAsk = python.globals.get('talk_ask');
  talkReply = python.globals.get('talk_reply');
  talkPage = python.globals.get('talk_page');
  talkClose = python.globals.get('talk_close');
  const run = python.globals.get('start');
  try { await run(); } finally { run.destroy(); }
  if (!accepting) return;
  if (history.length) replay(JSON.stringify(history));
  self.postMessage({ type: 'ready' });
}
self.onmessage = ({ data: message }) => {
  if (message.type === 'start') start(message.history || []).catch(report);
  else if (accepting && ['talk-open','talk-ask','talk-reply','talk-page','talk-close'].includes(message.type)) {
    const operation = message.type.slice(5);
    try {
      const session = Number(message.session), request = Number(message.request);
      if (operation === 'open') talkOpen();
      else if (operation === 'ask') {
        const result = talkAsk(session, request, String(message.question || '').slice(0, 200));
        if (result) self.postMessage({ type: 'talk-asked', session, request, ...JSON.parse(result) });
      } else if (operation === 'reply') talkReply(session, request, String(message.response || ''));
      else if (operation === 'page') talkPage(session);
      else talkClose(session);
    } catch (error) { report(error); }
    self.postMessage({ type: 'talk-ack', operation });
  }
  else if (message.type === 'action' && accepting && ['up','down','left','right','a','b','start','select','tick'].includes(message.action)) {
    try { act(message.action); self.postMessage({ type: 'ack', action: message.action }); } catch (error) { report(error); }
  }
};


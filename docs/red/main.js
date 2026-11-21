const canvas = document.querySelector('#screen');
const context = canvas.getContext('2d');
const screenWrap = document.querySelector('.screen-wrap');
const bezel = screenWrap.parentElement;
const resizeScreen = () => {
  const style = getComputedStyle(bezel);
  const available = bezel.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  const scale = Math.max(1, Math.min(3, Math.floor(available / 160)));
  screenWrap.style.width = `${scale * 160}px`;
  canvas.style.width = `${scale * 160}px`;
  canvas.style.height = `${scale * 144}px`;
};
if (typeof ResizeObserver === 'function') new ResizeObserver(resizeScreen).observe(bezel);
else { resizeScreen(); window.addEventListener('resize', resizeScreen); }
const palette = [[224,248,208],[136,192,112],[52,104,86],[8,24,32]];
const saveVersion = 2;
const replyLimit = 2000;
const storageKey = 'englishscript-red-adventure-v2';
const manualKey = 'englishscript-red-manual-save-v2';
const allowed = new Set(['up','down','left','right','a','b','start','select','tick']);
const watching = new URLSearchParams(location.search).get('watch') === 'badge';
const scriptVersion = document.currentScript ? new URL(document.currentScript.src).search : '';
const validSave = saved => saved && saved.version === saveVersion && Array.isArray(saved.actions) && saved.actions.every(action => allowed.has(action)) && (saved.content === undefined || typeof saved.content === 'string');
let manualCache = { read: async () => null, write: async () => false };
let audio = null;
try { if (typeof createRedSaveCache === 'function') manualCache = createRedSaveCache(validSave); }
catch { featureUnavailable('Backup saves'); }
try { if (typeof createRedAudio === 'function') audio = createRedAudio(); }
catch { featureUnavailable('Sound'); }
const soundButton = document.querySelector('#sound-toggle');
const musicTitle = document.querySelector('#music-title');
const trackNames = {
  'intro duel': 'Opening duel', opening: 'Title theme', 'oak speech': 'Professor Oak',
  pallet: 'Pallet Town', lab: 'Oak’s lab', route: 'Routes 1 & 2', 'route west': 'Route 22',
  city: 'Viridian & Pewter City', center: 'Pokémon Center', forest: 'Viridian Forest', gym: 'Pokémon Gym',
  wild: 'Wild Pokémon battle', trainer: 'Trainer battle', leader: 'Gym Leader battle',
};
let soundOn = false, mutedByPlayer = false, enablingSound = false;
soundButton.disabled = !audio;
async function enableSound() {
  if (!audio || soundOn || mutedByPlayer || enablingSound) return;
  enablingSound = true;
  try {
    soundOn = await audio.unlock();
    soundButton.textContent = soundOn ? 'Mute sound' : 'Enable sound';
  } catch {
    soundOn = false;
    soundButton.textContent = 'Enable sound';
  } finally {
    enablingSound = false;
  }
}
soundButton.addEventListener('click', () => {
  if (soundOn) {
    audio.setMuted(true);
    mutedByPlayer = true;
    soundOn = false;
    soundButton.textContent = 'Unmute sound';
    return;
  }
  if (mutedByPlayer) audio.setMuted(false);
  mutedByPlayer = false;
  enableSound();
});
let worker, generation = 0, ready = false, choosing = false, busy = false, queue = [], history = [], content, state = {}, image;
let storageAvailable = true, lastSaveRequest = 0, manualPending = false, cosmeticTick = false;
let conversationRevision = 0, liveAvailable = false, talkPending = false, capabilityRevision = 0;
const livePreferenceKey = 'englishscript-red-live-companion';
let heldDirection, heldTimer, conversations = new Map(), pendingConversation, announcedReply = "", judgeSource = "";
function cancelConversation() {
  conversationRevision++;
  if (pendingConversation) pendingConversation.abort();
  pendingConversation = undefined;
}
function deadline(seconds) {
  return typeof AbortSignal === 'function' && typeof AbortSignal.timeout === 'function' ? AbortSignal.timeout(seconds * 1000) : undefined;
}
function downloadFailure(url, seconds, error, otherwise) {
  const timedOut = error?.name === 'TimeoutError';
  return Object.assign(new Error(timedOut ? `Could not download ${url}: it did not arrive within ${seconds} seconds. Check your connection.` : otherwise), { timedOut });
}
async function downloadJson(url, seconds, options = {}) {
  let response;
  try { response = await fetch(url, { ...options, signal: deadline(seconds) }); }
  catch (error) { throw downloadFailure(url, seconds, error, `Could not download ${url}. Check your connection.`); }
  if (!response.ok) throw new Error(`Could not download ${url} (HTTP ${response.status}).`);
  try { return await response.json(); }
  catch (error) { throw downloadFailure(url, seconds, error, `${url} could not be read.`); }
}

function warnAboutSaves(text) {
  const warning = document.querySelector('#save-warning');
  warning.textContent = text;
  warning.hidden = false;
}
function readSave(key) {
  let text = null;
  try { text = localStorage.getItem(key); } catch { }
  if (text === null) return { saved: null, damaged: false };
  try {
    const saved = JSON.parse(text);
    if (validSave(saved)) return { saved, damaged: false };
  } catch { }
  return { saved: null, damaged: true };
}
function readAutosave() {
  const { saved, damaged } = readSave(storageKey);
  if (damaged) warnAboutSaves('Your autosaved adventure in this browser is damaged and could not be loaded, so a new adventure began. Choose Continue last SAVE if you saved in the game.');
  return saved;
}
async function latestManualSave() {
  const local = readSave(manualKey);
  const cached = await manualCache.read();
  if (local.damaged && !cached) warnAboutSaves('Your last SAVE in this browser is damaged and could not be loaded.');
  return cached && (!local.saved || (cached.savedAt || 0) > (local.saved.savedAt || 0)) ? cached : local.saved;
}
function store(key, saved) {
  try { localStorage.setItem(key, JSON.stringify(saved)); return true; }
  catch { return false; }
}
function autosave() {
  storageAvailable = store(storageKey, { version: saveVersion, content, actions: history });
  if (!storageAvailable) warnAboutSaves('This browser could not store your autosave, so reloading may lose recent progress. Use SAVE in the game menu to keep your progress.');
}
async function keepManualSave() {
  const saved = { version: saveVersion, content, savedAt: Date.now(), actions: [...history] };
  const stored = store(manualKey, saved);
  if (stored) document.querySelector('#continue-save').disabled = false;
  if (await manualCache.write(saved)) document.querySelector('#continue-save').disabled = false;
  else if (!stored) warnAboutSaves('Your SAVE could not be stored in this browser. Free some browser storage, then save again.');
}
function draw(frame) {
  const pixels = new Uint8Array(frame.pixels);
  if (frame.width !== 160 || frame.height !== 144 || pixels.length !== 160 * 144) throw new Error('The game sent an invalid frame.');
  if (!image) image = context.createImageData(160, 144);
  for (let i = 0; i < pixels.length; i++) {
    const color = palette[pixels[i]];
    if (!color) throw new Error('The game sent an invalid screen color.');
    const offset = i * 4;
    image.data[offset] = color[0]; image.data[offset + 1] = color[1]; image.data[offset + 2] = color[2]; image.data[offset + 3] = 255;
  }
  context.putImageData(image, 0, 0);
  document.querySelector('#loading').textContent = '';
  document.querySelector('#display-status').textContent = 'LIVE';
}
function display(next) {
  if (!watching && ready && Number(next['save request'] || 0) > lastSaveRequest) manualPending = true;
  lastSaveRequest = Number(next['save request'] || 0);
  const previousPhase = state.talkPhase;
  state = next;
  updateTalk(previousPhase);
  if (state.mode !== 'walk') stopHeldDirection();
  const value = (name, fallback = '—') => state[name] === undefined || state[name] === '' ? fallback : String(state[name]);
  document.querySelector('#location').textContent = value('place');
  document.querySelector('#objective').textContent = value('objective');
  document.querySelector('#starter').textContent = value('starter');
  document.querySelector('#badge').textContent = Number(state.badge) ? 'Boulder Badge earned' : 'Not yet earned';
  document.querySelector('#message').textContent = value('message', '');
  canvas.setAttribute('aria-label', `Game screen. ${value('place', 'Opening')}. ${value('message', '')}`);
  musicTitle.textContent = trackNames[state.music] || '';
  if (audio) audio.update(state);
}
function reloadAdvice(message) {
  return (/reload/i.test(message) ? '' : 'Reload the page to try again. ') + 'Reloading keeps your saved progress.';
}
function fail(message, advice = reloadAdvice(message)) {
  generation++;
  cancelConversation();
  closeChoice();
  clearTimeout(showTimer);
  stopHeldDirection();
  if (audio) audio.setPaused(true);
  ready = false;
  document.querySelectorAll('[data-action]').forEach(button => button.disabled = true);
  if (worker) worker.terminate();
  worker = null;
  document.querySelector('#display-status').textContent = 'STOPPED';
  document.querySelector('#watch-controls').hidden = true;
  document.querySelector('#talk-open').disabled = true;
  document.querySelector('#connection').textContent = `${message} ${advice}`;
  document.querySelector('#loading').textContent = 'The adventure could not continue.';
}
function failRestore(message) {
  const manualSaveExists = !document.querySelector('#continue-save').disabled;
  fail(`Your saved adventure could not be restored: ${message}`, manualSaveExists
    ? 'Choose New adventure to start over, or Continue last SAVE to try your last in-game save.'
    : 'Choose New adventure to start over.');
}
function offerChoice() {
  choosing = true;
  document.querySelector('#save-choice-text').textContent = (content === undefined
    ? 'This save is from an older version of the game and may not match it.'
    : 'The game has changed since this save was made.') + ' Continuing may put you somewhere unexpected or stop the game.';
  document.querySelector('#save-choice').hidden = false;
  document.querySelector('#loading').textContent = '';
  document.querySelector('#connection').textContent = 'Choose whether to continue your saved adventure.';
  document.querySelector('#save-keep').focus();
}
function closeChoice() {
  choosing = false;
  document.querySelector('#save-choice').hidden = true;
}
function restoreWith(actions) {
  if (!choosing || !worker) return;
  closeChoice();
  history = actions;
  document.querySelector('#loading').textContent = history.length ? 'Continuing your adventure…' : 'Preparing your adventure…';
  document.querySelector('#connection').textContent = history.length ? 'Restoring your adventure…' : 'Connecting to the game…';
  worker.postMessage({ type: 'restore', history });
  canvas.focus();
}
function begin(data) {
  ready = true;
  content = data.content;
  if (!watching) {
    autosave();
    document.querySelectorAll('[data-action]').forEach(button => button.disabled = false);
  }
  document.querySelector('#connection').textContent = storageAvailable ? 'Playing · progress saved in this browser' : 'Playing · browser save unavailable';
  const current = generation;
  if (watching) startShow(current).catch(error => { if (current === generation) fail(error.message); });
  pump();
}
function acknowledgeTalk(data) {
  busy = false;
  talkPending = false;
  if (data.operation === 'open' && (!state.talkPhase || state.talkPhase === 'closed')) {
    document.querySelector('#talk-status').textContent = 'Stand next to a person and face them to talk.';
  }
  pump();
}
function acknowledgeAction(data) {
  if (!watching && !cosmeticTick) { history.push(data.action); autosave(); }
  if (manualPending) {
    manualPending = false;
    keepManualSave();
  }
  busy = false;
  if (watching) showNext();
  else pump();
}
const workerMessages = {
  frame: draw,
  state: data => display(data.state),
  changed: offerChoice,
  'restore-failed': data => failRestore(data.message || 'the game stopped.'),
  ready: begin,
  'talk-asked': replyTo,
  'talk-ack': acknowledgeTalk,
  ack: acknowledgeAction,
  error: data => fail(data.message || 'The game stopped.'),
};
function startGame(resume, restored) {
  stopHeldDirection();
  if (audio) audio.setPaused(false);
  generation++;
  cancelConversation();
  closeChoice();
  const current = generation;
  if (worker) worker.terminate();
  ready = false; busy = false; queue = []; state = {}; lastSaveRequest = 0; manualPending = false; cosmeticTick = false;
  document.querySelector('#question').value = '';
  talkPending = false; conversations.clear(); announcedReply = "";
  document.querySelector('#talk-reply').textContent = '';
  document.querySelector('#companion').hidden = true;
  const saved = watching ? null : restored || (resume ? readAutosave() : null);
  history = saved ? [...saved.actions] : [];
  content = saved ? saved.content : undefined;
  if (!watching && (!resume || restored)) autosave();
  document.querySelector('#loading').textContent = history.length ? 'Continuing your adventure…' : 'Preparing your adventure…';
  document.querySelector('#connection').textContent = history.length ? 'Restoring your adventure…' : 'Connecting to the game…';
  document.querySelector('#display-status').textContent = 'STARTING';
  document.querySelectorAll('[data-action]').forEach(button => button.disabled = true);
  try {
    worker = new Worker(`worker.js${scriptVersion}`);
    worker.onmessage = ({ data }) => {
      if (current !== generation || !Object.hasOwn(workerMessages, data.type)) return;
      try { workerMessages[data.type](data); }
      catch (error) { fail(error.message); }
    };
    worker.onerror = () => { if (current === generation) fail('The game worker (worker.js) could not load or stopped unexpectedly. Check your connection.'); };
    worker.onmessageerror = () => { if (current === generation) fail('The game worker sent an unreadable message.'); };
    worker.postMessage({ type: 'start', history, content, offersChoice: true });
  } catch (error) { fail(`The game worker could not start: ${error.message || 'unknown error'}.`); }
}
function pump() {
  if (!ready || busy || !worker || !queue.length) return;
  busy = true;
  const item = queue.shift();
  cosmeticTick = item === 'tick' && state.mode === 'title';
  try { worker.postMessage(typeof item === 'string' ? { type: 'action', action: item } : item); }
  catch (error) { fail(`Could not send input to the game: ${error.message || 'unknown error'}.`); }
}
function input(action) {
  if (watching) return;
  enableSound();
  if (!ready || talkPending) return;
  if (state.talkPhase && state.talkPhase !== 'closed') {
    if (state.talkPhase === 'reply' && (action === 'a' || action === 'b')) {
      talkAction(action === 'a' ? 'page' : 'close');
    }
    return;
  }
  if (action === 'select' && ['walk', 'dialogue'].includes(state.mode)) { openTalk(); return; }
  if (queue.length >= 64) return;
  queue.push(action); pump();
}
function talkAction(operation, extra = {}) {
  if (watching || !ready || talkPending || busy || queue.length) return false;
  talkPending = true;
  if (operation === 'close') { cancelConversation(); announcedReply = ''; }
  queue.push({ type: `talk-${operation}`, session: state.talkSession, ...extra });
  pump();
  return true;
}
function openTalk() {
  if (watching || !['walk', 'dialogue'].includes(state.mode)) return;
  stopHeldDirection();
  if (talkAction('open')) document.querySelector('#talk-status').textContent = 'Looking for someone to talk to…';
}
function updateTalk(previousPhase) {
  const phase = state.talkPhase || 'closed';
  const composing = phase === 'composing';
  document.querySelector('#companion').hidden = !composing;
  document.querySelector('#talk-person').textContent = state.talkPerson || 'the person ahead';
  document.querySelector('#talk-open').disabled = watching || phase !== 'closed' || !['walk', 'dialogue'].includes(state.mode);
  document.querySelector('#talk-next').hidden = phase !== 'reply';
  document.querySelector('#talk-next').textContent = state.talkHasMore ? 'Next' : 'Ask again';
  document.querySelector('#talk-close').hidden = phase === 'closed' || composing;
  if (phase !== 'closed') stopHeldDirection();
  if (composing && previousPhase !== 'composing') {
    document.querySelector('#question').value = '';
    document.querySelector('#question').focus();
    document.querySelector('#talk-status').textContent = 'Type your question, then press Ask.';
  }
  if (phase === 'reply') {
    const replyId = `${state.talkSession}:${state.talkRequest}`;
    if (announcedReply !== replyId) {
      announcedReply = replyId;
      document.querySelector('#talk-reply').textContent = String(state.talkRawReply || state.talkPage || '');
    }
  }
  if (phase === 'closed' && previousPhase && previousPhase !== 'closed') {
    cancelConversation();
    document.querySelector('#talk-reply').textContent = '';
    document.querySelector('#talk-status').textContent = 'Stand next to a person, face them, and press Talk or Select.';
    canvas.focus();
  }
}
function stopHeldDirection() {
  heldDirection = undefined;
  clearTimeout(heldTimer);
  heldTimer = undefined;
}
function repeatDirection() {
  if (!heldDirection) return;
  if (ready && state.mode === 'walk' && !busy && !queue.length) input(heldDirection.action);
  heldTimer = setTimeout(repeatDirection, 125);
}
function isolatedTarget(target) {
  return target instanceof Element && target.closest('button, a, input, textarea, select, summary, [contenteditable=true], [role=button], [role=checkbox], [role=radio], [role=slider], [role=menuitem]') && !target.closest('[data-action]');
}
document.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', () => input(button.dataset.action)));
window.addEventListener('keydown', event => {
  const actions = { ArrowUp:'up', ArrowDown:'down', ArrowLeft:'left', ArrowRight:'right', z:'a', Z:'a', x:'b', X:'b', Enter:'start', Shift:'select' };
  if (isolatedTarget(event.target) && !event.target.closest('#companion')) return;
  if (event.key === 'Escape' && state.talkPhase && state.talkPhase !== 'closed') { event.preventDefault(); event.stopPropagation(); talkAction('close'); return; }
  const action = actions[event.key];
  if (!action || event.repeat || event.altKey || event.ctrlKey || event.metaKey) return;
  if (isolatedTarget(event.target)) return;
  event.preventDefault(); input(action);
  if (event.key.startsWith('Arrow') && ready && state.mode === 'walk') {
    stopHeldDirection();
    heldDirection = { key: event.key, action };
    heldTimer = setTimeout(repeatDirection, 250);
  }
});
window.addEventListener('keyup', event => {
  if (heldDirection && event.key === heldDirection.key) stopHeldDirection();
});
window.addEventListener('blur', stopHeldDirection);
document.addEventListener('focusin', event => { if (isolatedTarget(event.target)) stopHeldDirection(); });
document.addEventListener('visibilitychange', () => { if (document.hidden) stopHeldDirection(); });

const liveOption = document.querySelector('#live-companion');
const liveStatus = document.querySelector('#live-status');
function preferredLive() {
  try { return localStorage.getItem(livePreferenceKey) !== 'local'; } catch { return true; }
}
async function checkLiveCompanion() {
  const revision = ++capabilityRevision;
  if (!['localhost', '127.0.0.1', '[::1]'].includes(location.hostname)) {
    liveStatus.textContent = 'Local replies active. Live companion requires the local host.';
    return;
  }
  let unavailable = 'Local replies active. Live companion is unavailable.';
  try {
    const capability = await downloadJson('/api/companion', 10, { cache: 'no-store' });
    if (revision !== capabilityRevision) return;
    liveAvailable = capability?.available === true;
    judgeSource = capability?.judge === 'jev' ? 'Jev' : capability?.judge === 'anthropic' ? 'Anthropic' : '';
  } catch (error) {
    if (revision !== capabilityRevision) return;
    liveAvailable = false;
    if (error.timedOut) unavailable = 'Local replies active. The live companion service did not answer in time.';
  }
  liveOption.disabled = !liveAvailable || watching;
  liveOption.checked = liveAvailable && preferredLive();
  liveStatus.textContent = liveAvailable ? (liveOption.checked ? 'Live companion selected. Questions and game context are sent to the local service.' : 'Local replies selected.') : unavailable;
}
liveOption.addEventListener('change', () => {
  if (!liveOption.checked && pendingConversation) pendingConversation.abort();
  try { localStorage.setItem(livePreferenceKey, liveOption.checked ? 'live' : 'local'); } catch { }
  liveStatus.textContent = liveOption.checked ? 'Live companion selected. Questions and game context are sent to the local service.' : 'Local replies selected.';
});
function companionContext(fallback, identity) {
  const short = value => String(value ?? '').slice(0, 80);
  const data = { place: short(state.place), objective: short(state.objective), starter: short(state.starter), trainer: short(state.trainer), badge: short(state.badge), localResponse: fallback.slice(0, 500), conversation: (conversations.get(identity) || []).map(pair => ({ question: pair.question.slice(0, 500), reply: pair.reply.slice(0, 500) })) };
  let result = JSON.stringify(data);
  while (result.length > 4000 && data.conversation.length) {
    const pair = data.conversation[0];
    if (pair.question.length + pair.reply.length < 100) data.conversation.shift();
    else { pair.question = pair.question.slice(0, Math.floor(pair.question.length / 2)); pair.reply = pair.reply.slice(0, Math.floor(pair.reply.length / 2)); }
    result = JSON.stringify(data);
  }
  if (result.length > 4000) { delete data.localResponse; result = JSON.stringify(data); }
  return result;
}
async function replyTo(job) {
  cancelConversation();
  const revision = conversationRevision;
  const identity = typeof job.identity === 'string' && job.identity.length <= 100 ? job.identity.trim() : '';
  const fallback = String(job.response || '');
  let reply = fallback;
  let source = 'Local reply';
  if (liveAvailable && liveOption.checked && job.person) {
    source = 'Live companion thinking…';
    document.querySelector('#talk-status').textContent = source;
    const context = companionContext(fallback, identity);
    const controller = new AbortController();
    pendingConversation = controller;
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch('/api/companion', {
        method: 'POST', signal: controller.signal, headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ actor: job.person, question: job.question, context, profile: job.profile, voice: job.voice })
      });
      if (!response.ok) throw Error('Live companion unavailable');
      const result = await response.json();
      if (typeof result.reply !== 'string' || !result.reply.trim()) throw Error('Empty reply');
      if (liveOption.checked && !controller.signal.aborted) {
        reply = result.reply.trim();
        const perceptions = ['neutral', 'friendly', 'rude', 'cruel', 'flirting', 'uncertain'];
        source = perceptions.includes(result.perception) ? `${judgeSource || 'Companion'} heard this as ${result.perception} · GPT-6 Luna` : 'Live companion reply · GPT-6 Luna';
      } else { source = 'Local reply'; }
    } catch { source = controller.signal.aborted && !liveOption.checked ? 'Local reply' : 'Live companion unavailable · local reply'; }
    finally { clearTimeout(timeout); if (pendingConversation === controller) pendingConversation = undefined; }
  }
  if (revision !== conversationRevision || state.talkSession !== job.session || state.talkRequest !== job.request || state.talkPhase !== 'waiting') return;
  document.querySelector('#talk-status').textContent = source;
  if (identity) {
    const exchanges = conversations.get(identity) || [];
    exchanges.push({ question: String(job.question || '').slice(0, 500), reply: reply.slice(0, 500) });
    conversations.delete(identity);
    conversations.set(identity, exchanges.slice(-2));
    if (conversations.size > 32) conversations.delete(conversations.keys().next().value);
  }
  queue.push({ type: 'talk-reply', session: job.session, request: job.request, response: reply.slice(0, replyLimit) });
  pump();
}
checkLiveCompanion();
window.addEventListener('red-companion-settings', checkLiveCompanion);

latestManualSave().then(saved => { if (saved?.actions.length) document.querySelector('#continue-save').disabled = false; });
document.querySelector('#save-keep').addEventListener('click', () => restoreWith(history));
document.querySelector('#save-fresh').addEventListener('click', () => restoreWith([]));
document.querySelector('#talk-open').addEventListener('click', openTalk);
document.querySelector('#talk-next').addEventListener('click', () => talkAction('page'));
document.querySelector('#talk-close').addEventListener('click', () => talkAction('close'));
document.querySelector('#talk-cancel').addEventListener('click', () => talkAction('close'));
document.querySelector('#companion').addEventListener('submit', event => {
  event.preventDefault();
  const question = document.querySelector('#question').value.trim();
  if (!question || state.talkPhase !== 'composing') return;
  if (talkAction('ask', { request: Number(state.talkRequest || 0) + 1, question })) {
    document.querySelector('#talk-status').textContent = 'Preparing a reply…';
  }
});
document.querySelector('#continue-save').addEventListener('click', async () => {
  const saved = await latestManualSave();
  if (!saved?.actions.length || !confirm('Continue from your last in-game SAVE? Current progress will be replaced.')) return;
  startGame(true, saved); canvas.focus();
});
document.querySelector('#restart').addEventListener('click', () => {
  if (!confirm('Start a new adventure? Your saved progress in this browser will be replaced.')) return;
  startGame(false); canvas.focus();
});
setInterval(() => {
  if (!watching && ready && !busy && !queue.length && ['opening', 'title'].includes(state.mode)) { queue.push('tick'); pump(); }
}, 125);
let recording = [], cursor = 0, paused = false, showTimer;
async function startShow(current) {
  document.querySelector('#connection').textContent = 'Loading the Boulder Badge run…';
  const loaded = await downloadJson('replay.json', 30, { cache: 'no-cache' });
  if (current !== generation) return;
  recording = loaded;
  if (!Array.isArray(recording) || !recording.length || !recording.every(key => allowed.has(key))) throw Error('The recording is incomplete.');
  document.querySelector('#watch-controls').hidden = false;
  for (const element of document.querySelectorAll('#companion, .talk-controls, .help, #continue-save, #restart')) element.hidden = true;
  document.querySelectorAll('[data-action]').forEach(button => button.disabled = true);
  showNext();
}
function showNext() {
  clearTimeout(showTimer);
  const progress = document.querySelector('#connection');
  if (cursor === recording.length) {
    const won = state.badge === 1 && state.tm34 === 1 && state.mode === 'walk';
    progress.textContent = won ? 'Run complete · Boulder Badge and TM34 earned' : 'Run ended before the reward.';
    document.querySelector('#watch-toggle').hidden = true;
    return;
  }
  progress.textContent = (paused ? 'Paused' : 'Watching the Boulder Badge run') + ' · ' + cursor.toLocaleString() + ' / ' + recording.length.toLocaleString();
  if (paused || busy) return;
  const reading = ['intro', 'dialogue', 'naming', 'rival naming', 'starter'].includes(state.mode);
  const gymBattle = state.mode === 'battle' && state.music === 'leader';
  const delay = gymBattle ? 950 : cursor < 16 || state.mode === 'title' ? 430 : reading ? 145 : 12;
  showTimer = setTimeout(() => { queue.push(recording[cursor++]); pump(); }, delay);
}
if (watching) {
  document.querySelector('#watch-toggle').addEventListener('click', event => {
    paused = !paused;
    event.currentTarget.textContent = paused ? 'Resume run' : 'Pause run';
    if (audio) audio.setPaused(paused);
    if (!paused) enableSound();
    showNext();
  });
}
startGame(true);

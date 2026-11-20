const screen = document.querySelector('#screen');
const displayStatus = document.querySelector('#display-status');
const connection = document.querySelector('#connection');
const activity = document.querySelector('#activity');
const restart = document.querySelector('#restart');
const palette = [[236, 240, 220], [180, 193, 164], [99, 117, 97], [40, 56, 46]];
const practiceResponse = 'Calibration complete. Keep exploring.';
let worker;
let generation = 0;
let canvas;
let context;
let image;
let timers = new Set();
let pending = 0;
let fieldResult;

function drawFrame(message) {
  const { width, height } = message;
  const pixels = new Uint8Array(message.pixels);
  if (!Number.isInteger(width) || !Number.isInteger(height) || width < 1 || height < 1 || pixels.length !== width * height) {
    throw new Error('The field display received an invalid frame.');
  }
  if (!canvas) {
    canvas = document.createElement('canvas');
    context = canvas.getContext('2d');
    screen.replaceChildren(canvas);
  }
  if (!image || canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
    screen.style.aspectRatio = `${width} / ${height}`;
    image = context.createImageData(width, height);
  }
  for (let i = 0; i < pixels.length; i++) {
    const color = palette[pixels[i]];
    if (!color) throw new Error('The field display received an unknown color.');
    const offset = i * 4;
    image.data[offset] = color[0];
    image.data[offset + 1] = color[1];
    image.data[offset + 2] = color[2];
    image.data[offset + 3] = 255;
  }
  context.putImageData(image, 0, 0);
  displayStatus.textContent = 'Live';
}

function showError(message) {
  generation += 1;
  if (worker) worker.terminate();
  worker = undefined;
  for (const timer of timers) clearTimeout(timer);
  timers.clear();
  connection.textContent = 'Stopped';
  displayStatus.textContent = 'Stopped';
  activity.textContent = `${message} Try restarting the field.`;
}

function startField() {
  generation += 1;
  const current = generation;
  if (worker) worker.terminate();
  for (const timer of timers) clearTimeout(timer);
  timers = new Set();
  pending = 0;
  fieldResult = undefined;
  canvas = undefined;
  context = undefined;
  image = undefined;
  screen.replaceChildren(Object.assign(document.createElement('span'), { className: 'loading', textContent: 'Preparing field…' }));
  screen.style.removeProperty('aspect-ratio');
  screen.setAttribute('aria-label', 'Field display loading');
  displayStatus.textContent = 'Starting';
  connection.textContent = 'Connecting';
  activity.textContent = 'Preparing the field…';
  try {
    worker = new Worker('worker.js');
    const activeWorker = worker;
    activeWorker.onmessage = ({ data }) => {
      if (current !== generation) return;
      try {
        if (data.type === 'frame') drawFrame(data);
        if (data.type === 'ready') {
          connection.textContent = pending ? 'Waiting for reply' : 'Ready';
          if (activity.textContent === 'Preparing the field…') activity.textContent = 'The field is ready to explore.';
        }
        if (data.type === 'request') {
          pending += 1;
          connection.textContent = 'Waiting for reply';
          activity.textContent = `Practice request: ${data.prompt}`;
          const timer = setTimeout(() => {
            timers.delete(timer);
            if (current !== generation) return;
            activeWorker.postMessage({ type: 'reply', id: data.id, text: practiceResponse });
            connection.textContent = 'Applying reply';
            activity.textContent = 'Recorded offline practice response sent; waiting for the field.';
          }, 5000);
          timers.add(timer);
        }
        if (data.type === 'state') fieldResult = data.result;
        if (data.type === 'state' && Number.isFinite(data.column) && Number.isFinite(data.row)) {
          screen.setAttribute('aria-label', `Boulder Badge field display. Position column ${data.column}, row ${data.row}. Steps ${data.steps}.`);
        }
        if (data.type === 'complete') {
          pending = Math.max(0, pending - 1);
          connection.textContent = pending ? 'Waiting for reply' : 'Ready';
          activity.textContent = `Recorded offline practice response: ${fieldResult}`;
        }
        if (data.type === 'error') showError(data.message || 'The field could not continue.');
      } catch (error) {
        showError(error.message);
      }
    };
    activeWorker.onerror = () => {
      if (current === generation) showError('The field could not start.');
    };
    activeWorker.postMessage({ type: 'start' });
  } catch (error) {
    showError('The field could not start.');
  }
}

function move(action) {
  if (worker) worker.postMessage({ type: 'action', action });
}

document.querySelectorAll('[data-action]').forEach(button => {
  button.addEventListener('click', () => move(button.dataset.action));
});
window.addEventListener('keydown', event => {
  const actions = { ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right' };
  const action = actions[event.key];
  if (!action || event.altKey || event.ctrlKey || event.metaKey || (event.target.closest('button, a, input, textarea, select, [contenteditable=true]') && !event.target.closest('[data-action]'))) return;
  event.preventDefault();
  move(action);
});
restart.addEventListener('click', () => {
  startField();
  screen.focus();
});
startField();




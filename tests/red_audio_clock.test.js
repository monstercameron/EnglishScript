const test = require("node:test");
const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");

class Param {
  setValueAtTime() {}
  exponentialRampToValueAtTime() {}
}
class Node {
  constructor() { this.gain = new Param(); this.frequency = new Param(); }
  connect() {}
  disconnect() {}
  setPeriodicWave(wave) { this.wave = wave; }
  start(time) { this.started = time; }
  stop() {}
}
class AudioContext {
  constructor() { this.currentTime = 0; this.sampleRate = 100; this.state = "running"; this.destination = {}; this.notes = []; this.waves = []; AudioContext.instance = this; }
  createGain() { return new Node(); }
  createOscillator() { const node = new Node(); this.notes.push(node); return node; }
  createBufferSource() { return new Node(); }
  createBuffer(channels, length) { const data = new Float32Array(length); return { getChannelData: () => data }; }
  createPeriodicWave(real, imag) { const wave = { real, imag }; this.waves.push(wave); return wave; }
  resume() { return Promise.resolve(); }
  close() { return Promise.resolve(); }
}

const unit = 120 / 1280;
const loop = 12 * unit;
const melody = Array.from({ length: 12 }, (_, step) => `${60 + step}:1`).join(" ");
const bass = Array.from({ length: 4 }, (_, step) => `${40 + step}:3`).join(" ");

function pitchOf(node) {
  return Math.round(69 + 12 * Math.log2(node.frequency.value / 440));
}

function songOffset(node, context) {
  const pitch = pitchOf(node);
  const position = node.wave === context.waves[0] ? pitch - 60 : (pitch - 40) * 3;
  const offset = (node.started - position * unit) % loop;
  return (offset + loop) % loop;
}

async function playingSong() {
  let scheduler;
  const scope = { AudioContext, setInterval: (callback) => { scheduler = callback; return 1; }, clearInterval() {} };
  vm.runInNewContext(readFileSync("docs/red/audio.js", "utf8"), scope);
  const audio = scope.createRedAudio();
  audio.update({ music: "route", tempo: 120, melody, bass });
  await audio.unlock();
  return { audio, context: AudioContext.instance, schedule: scheduler };
}

function assertTogether(nodes, context) {
  const offsets = nodes.map((node) => songOffset(node, context));
  for (const offset of offsets) assert.ok(Math.abs(offset - offsets[0]) < 1e-9, `tracks drifted apart: ${offsets.join(", ")}`);
}

test("melody and bass stay on one song clock after the scheduler stalls", async () => {
  const { context, schedule } = await playingSong();
  context.currentTime = 10;
  schedule();
  const after = context.notes.filter((node) => node.started >= 10);
  assert.ok(after.some((node) => node.wave === context.waves[0]));
  assert.ok(after.some((node) => node.wave === context.waves[2]));
  assert.ok(Math.min(...after.map((node) => node.started)) >= 10.02 - 1e-9);
  assertTogether(after, context);
});

test("melody and bass stay together after a pause", async () => {
  const { audio, context, schedule } = await playingSong();
  context.currentTime = 0.1;
  schedule();
  audio.setPaused(true);
  context.currentTime = 4;
  audio.setPaused(false);
  const after = context.notes.filter((node) => node.started >= 4);
  assert.ok(after.length >= 2);
  assertTogether(after, context);
});

const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const vm = require("node:vm");

class Param {
  constructor() { this.value = 0; this.ramps = []; }
  setValueAtTime() {}
  exponentialRampToValueAtTime(value, time) { this.ramps.push([value, time]); }
}
class Node {
  constructor(context) { this.context = context; this.gain = new Param(); this.frequency = new Param(); this.stops = []; }
  connect() {}
  disconnect() {}
  setPeriodicWave(wave) { this.wave = wave; }
  start(time) { this.started = time; }
  stop(time) { this.stops.push(time); }
}
class AudioContext {
  constructor() { this.currentTime = 0; this.sampleRate = 100; this.state = "running"; this.destination = {}; this.nodes = []; this.waves = []; this.gains = []; AudioContext.instance = this; }
  createGain() { const node = new Node(this); this.gains.push(node); return node; }
  createOscillator() { const node = new Node(this); this.nodes.push(node); return node; }
  createBufferSource() { const node = new Node(this); this.nodes.push(node); return node; }
  createBuffer(channels, length) { const data = new Float32Array(length); this.noise = data; return { getChannelData: () => data }; }
  createPeriodicWave(real, imag) { const wave = { real, imag }; this.waves.push(wave); return wave; }
  resume() { return Promise.resolve(); }
  close() { return Promise.resolve(); }
}
const scope = { AudioContext, setInterval: () => 1, clearInterval: () => {} };
vm.runInNewContext(readFileSync("docs/red/audio.js", "utf8"), scope);

(async () => {
  const audio = scope.createRedAudio();
  const state = { music: "route", tempo: 120, melody: "69:2", harmony: "72:2", bass: "45:2", percussion: "noise:2", effectCount: 0 };
  audio.update(state);
  assert.equal(await audio.unlock(), true);
  const context = AudioContext.instance;
  assert.equal(context.nodes.length, 4);
  assert.equal(context.gains[0].gain.value, 0.78);
  assert.notDeepEqual(Array.from(context.waves[0].real), Array.from(context.waves[1].real));
  assert.notDeepEqual(Array.from(context.waves[1].real), Array.from(context.waves[2].real));
  assert.equal(context.nodes[0].started, 0.03);
  assert.equal(context.nodes[0].stops[0], 0.03 + 2 * 120 / 1280);
  assert.ok(context.noise.includes(-1) && context.noise.includes(1));
  await audio.unlock();
  assert.equal(context.nodes.length, 4);
  audio.update({ ...state, music: "battle" });
  assert.ok(context.nodes.slice(0, 4).every(node => node.stops.length === 2));
  assert.equal(context.nodes.length, 8);
  audio.update({ ...state, music: "battle", effect: "80:1 82:1", effectCount: 1 });
  const oldEffects = context.nodes.slice(-2);
  audio.update({ ...state, music: "battle", effect: "noise:1", effectCount: 2 });
  assert.ok(oldEffects.every(node => node.stops.length === 2));
  audio.setPaused(true);
  const count = context.nodes.length;
  audio.setPaused(false);
  assert.equal(context.nodes.length, count + 4);
  audio.setMuted(true);
  const mutedCount = context.nodes.length;
  audio.update({ ...state, music: "battle", effect: "90:1", effectCount: 3 });
  assert.equal(context.nodes.length, mutedCount);
  audio.setMuted(false);
  assert.equal(context.nodes.length, mutedCount + 4);
  const beforeIntro = context.nodes.length;
  audio.update({ ...state, music: "intro", "intro melody": "81:2", "effect priority": 3, effect: "80:2", effectCount: 4 });
  assert.equal(context.nodes[beforeIntro + 1].frequency.value, 440 * Math.pow(2, (81 - 69) / 12));
  const highEffect = context.nodes[beforeIntro];
  const beforeLow = context.nodes.length;
  audio.update({ ...state, music: "intro", "effect priority": 1, effect: "82:1", effectCount: 5 });
  assert.equal(context.nodes.length, beforeLow);
  assert.equal(highEffect.stops.length, 1);
  audio.setMuted(true);
  assert.equal(context.gains[0].gain.value, 0);
  const beforeResume = context.nodes.length;
  audio.setMuted(false);
  assert.equal(context.gains[0].gain.value, 0.78);
  assert.equal(context.nodes[beforeResume].frequency.value, 440);
  context.currentTime = 3;
  const beforeCry = context.nodes.length;
  audio.update({ ...state, music: "intro", cry: "72~48:2", "cry count": 1 });
  const glide = context.nodes[beforeCry];
  assert.equal(glide.frequency.ramps.length, 1);
  assert.equal(glide.frequency.ramps[0][0], 440 * Math.pow(2, (48 - 69) / 12));
  assert.equal(glide.frequency.ramps[0][1], 3.02 + 0.15);
  audio.close();
  audio.update(state);
  assert.equal(await audio.unlock(), true);
  assert.equal(AudioContext.instance.nodes.length, 4);
  assert.equal(AudioContext.instance.gains[0].gain.value, 0.78);
  audio.close();
  console.log("red audio tests passed");
})().catch(error => { console.error(error); process.exitCode = 1; });

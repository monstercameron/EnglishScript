(function (scope) {
  function parseNotes(source) {
    return String(source || "").split(/\s+/).map((part) => {
      const [pitch, length] = part.split(":");
      const duration = Number(length);
      const [first, last] = pitch.split("~");
      const note = first === "noise" ? first : Number(first);
      const glide = last === undefined ? null : Number(last);
      return Number.isFinite(duration) && duration > 0 && (note === "noise" || Number.isFinite(note)) && (glide === null || (Number.isFinite(glide) && note !== "noise")) ? { note, glide, duration } : null;
    }).filter(Boolean);
  }

  const masterLevel = 0.78;

  function createRedAudio() {
    let context;
    let output;
    let noiseBuffer;
    let waves;
    let timer;
    let music = "";
    let tracks = [];
    let effectCount = 0;
    let cryCount = 0;
    let effectPriority = 0;
    let effectUntil = 0;
    let latest = null;
    let muted = false;
    let paused = false;
    const musicNodes = new Set();
    const effectNodes = new Set();
    const cryNodes = new Set();

    function pulseWave(duty) {
      const real = new Float32Array(33);
      const imag = new Float32Array(33);
      for (let i = 1; i < real.length; i += 1) real[i] = 2 * Math.sin(Math.PI * i * duty) / (Math.PI * i);
      return context.createPeriodicWave(real, imag);
    }

    function bassWave() {
      const real = new Float32Array(17);
      const imag = new Float32Array(17);
      for (let i = 1; i < imag.length; i += 2) imag[i] = (i % 4 === 1 ? 1 : -1) / (i * i);
      return context.createPeriodicWave(real, imag);
    }

    function prepare() {
      if (context) return true;
      const Audio = scope.AudioContext || scope.webkitAudioContext;
      if (!Audio) return false;
      context = new Audio();
      output = context.createGain();
      output.gain.value = muted ? 0 : masterLevel;
      output.connect(context.destination);
      waves = [pulseWave(0.125), pulseWave(0.25), bassWave()];
      noiseBuffer = context.createBuffer(1, Math.floor(context.sampleRate * 0.3), context.sampleRate);
      const samples = noiseBuffer.getChannelData(0);
      let register = 0x7fff;
      for (let i = 0; i < samples.length; i += 1) {
        const bit = (register ^ (register >> 1)) & 1;
        register = (register >> 1) | (bit << 14);
        samples[i] = (register & 1) ? 1 : -1;
      }
      return true;
    }

    function stopNodes(nodes) {
      for (const source of nodes) {
        try { source.stop(); } catch (_) {}
      }
      nodes.clear();
    }

    function note(pitch, start, duration, voice, nodes, glide) {
      if (pitch === 0 || !context) return;
      const gain = context.createGain();
      const level = [0.24, 0.16, 0.14, 0.1, 0.22][voice];
      const end = start + Math.max(0.025, duration);
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(level, start + Math.min(0.008, duration * 0.2));
      gain.gain.setValueAtTime(level, start + Math.max(0.01, duration * 0.7));
      gain.gain.exponentialRampToValueAtTime(0.0001, start + Math.max(0.02, duration * 0.92));
      gain.connect(output);
      let source;
      if (pitch === "noise") {
        source = context.createBufferSource();
        source.buffer = noiseBuffer;
        source.loop = true;
      } else {
        source = context.createOscillator();
        source.setPeriodicWave(waves[voice < 3 ? voice : 0]);
        source.frequency.value = 440 * Math.pow(2, (pitch - 69) / 12);
        if (glide !== null && glide !== undefined) {
          source.frequency.setValueAtTime(source.frequency.value, start);
          source.frequency.exponentialRampToValueAtTime(440 * Math.pow(2, (glide - 69) / 12), end);
        }
      }
      source.connect(gain);
      nodes.add(source);
      source.onended = () => { nodes.delete(source); source.disconnect(); gain.disconnect(); };
      source.start(start);
      source.stop(end);
    }

    function resetTracks() {
      stopNodes(musicNodes);
      tracks = [];
      music = latest ? latest.music || "" : "";
      if (!context || !latest || !music) return;
      const unit = Math.max(40, Math.min(300, Number(latest.tempo) || 144)) / 1280;
      tracks = ["melody", "harmony", "bass", "percussion"].map((name, voice) => {
        const intro = parseNotes(latest["intro " + name]);
        const body = parseNotes(latest[name]);
        return { notes: intro.length ? intro : body, body, intro: intro.length > 0, voice, unit, index: 0, time: context.currentTime + 0.03 };
      });
    }

    function moveSongTo(start) {
      const playing = tracks.filter((track) => track.notes.length);
      if (!playing.length) return;
      const shift = start - Math.min(...playing.map((track) => track.time));
      for (const track of tracks) track.time += shift;
    }

    function catchUp(now) {
      if (tracks.some((track) => track.notes.length && track.time < now - 0.2)) moveSongTo(now + 0.02);
    }

    function schedule() {
      if (!context || context.state !== "running" || muted || paused) return;
      const now = context.currentTime;
      catchUp(now);
      for (const track of tracks) {
        while (track.notes.length && track.time < now + 0.15) {
          const item = track.notes[track.index];
          const duration = item.duration * track.unit;
          note(item.note, track.time, duration, track.voice, musicNodes);
          track.time += duration;
          track.index += 1;
          if (track.index === track.notes.length) {
            if (track.intro) { track.notes = track.body; track.intro = false; }
            track.index = 0;
          }
        }
      }
    }

    function update(state) {
      if (!state) return;
      latest = state;
      if (!context) return;
      if ((state.music || "") !== music) resetTracks();
      const count = Number(state.effectCount) || 0;
      if (count !== effectCount) {
        effectCount = count;
        const priority = Math.max(1, Math.min(3, Number(state["effect priority"]) || 1));
        if (!muted && !paused && context.state === "running" && (context.currentTime >= effectUntil || priority >= effectPriority)) {
          stopNodes(effectNodes);
          effectPriority = priority;
          let start = context.currentTime + 0.02;
          for (const item of parseNotes(state.effect).slice(0, 32)) {
            if (start >= context.currentTime + 2) break;
            const duration = Math.min(item.duration * 0.075, 1, context.currentTime + 2 - start);
            note(item.note, start, duration, 4, effectNodes, item.glide);
            start += duration;
          }
          effectUntil = start;
        }
      }
      const cries = Number(state["cry count"]) || 0;
      if (cries !== cryCount) {
        cryCount = cries;
        stopNodes(cryNodes);
        if (!muted && !paused && context.state === "running") {
          let start = context.currentTime + 0.02;
          for (const item of parseNotes(state.cry).slice(0, 32)) {
            if (start >= context.currentTime + 2) break;
            const duration = Math.min(item.duration * 0.075, 1, context.currentTime + 2 - start);
            note(item.note, start, duration, 4, cryNodes, item.glide);
            start += duration;
          }
        }
      }
      schedule();
    }

    function unlock() {
      const needsTracks = !context;
      if (!prepare()) return Promise.resolve(false);
      return context.resume().then(() => {
        if (!timer) timer = scope.setInterval(schedule, 50);
        if (latest && needsTracks) {
          effectCount = Number(latest.effectCount) || 0;
          cryCount = Number(latest["cry count"]) || 0;
          resetTracks();
          schedule();
        }
        return true;
      }).catch(() => false);
    }

    function resumeTracks() {
      if (!context) return;
      moveSongTo(context.currentTime + 0.03);
      schedule();
    }

    function setMuted(value) {
      const next = Boolean(value);
      if (next === muted) return;
      muted = next;
      if (output) output.gain.value = muted ? 0 : masterLevel;
      stopNodes(effectNodes);
      stopNodes(cryNodes);
      effectUntil = 0;
      if (muted) stopNodes(musicNodes);
      else if (!paused) resumeTracks();
    }

    function setPaused(value) {
      const next = Boolean(value);
      if (next === paused) return;
      paused = next;
      stopNodes(effectNodes);
      stopNodes(cryNodes);
      effectUntil = 0;
      if (paused) stopNodes(musicNodes);
      else if (!muted) resumeTracks();
    }

    function close() {
      if (timer) scope.clearInterval(timer);
      timer = null;
      stopNodes(musicNodes);
      stopNodes(effectNodes);
      stopNodes(cryNodes);
      if (context) context.close();
      context = null;
      tracks = [];
      music = "";
      latest = null;
      effectCount = 0;
      cryCount = 0;
      effectPriority = 0;
      effectUntil = 0;
      output = null;
      noiseBuffer = null;
      waves = null;
      muted = false;
      paused = false;
    }

    return { update, unlock, setMuted, setPaused, close };
  }
  scope.createRedAudio = createRedAudio;
})(globalThis);

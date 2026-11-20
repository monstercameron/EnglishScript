#!/usr/bin/env python3
"""Replay independent original and English controller paths through early Red.

Requires PyBoy 2.9.0 and a locally built ROM matching the pinned Red SHA-1.
Run: python tools/compare_red_segment.py --rom /private/pokered.gbc --out /private/report.json
The original fixture uses frame-boundary button edges; English consumes a
separate action sequence. These checkpoints do not establish timing parity.
Optionally pass --reward-state with a private, genuine post-Brock PyBoy save.
That snapshot is independently sourced and not part of the cold-boot trace.
The tool writes measurements and state, never the ROM or reference graphics.
"""
import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.compare_red_frames import EXPECTED, WIDTH, HEIGHT, compare_frames

MAP_NAMES = {0: 'Pallet Town', 1: 'Viridian City', 2: 'Pewter City', 51: 'Viridian Forest', 54: 'Pewter Gym', 42: 'Viridian Mart', 37: 'Home', 38: 'Bedroom', 40: "Oak's Lab"}
FACINGS = {0: 'south', 4: 'north', 8: 'west', 12: 'east'}


def as_int(value):
    return int(value) if value is not None else None


def alignment(original, english):
    return {
        'map': MAP_NAMES.get(original['map_id']) == english.get('place'),
        'position': (original['x'], original['y']) == (as_int(english.get('column')), as_int(english.get('row'))),
        'facing': FACINGS.get(original['sprite_facing_raw']) == english.get('facing'),
        'party_presence': (original['party_count'] > 0) == bool(english.get('starter')),
        'badges': original['badges'] == as_int(english.get('badge')),
    }


def reference_checkpoints(rom, trace):
    if hashlib.sha1(rom.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError('ROM SHA-1 does not match the pinned upstream English Red build')
    if importlib.metadata.version('pyboy') != '2.9.0':
        raise ValueError('This benchmark is pinned to PyBoy 2.9.0')
    from pyboy import PyBoy
    emulator = PyBoy(str(rom), window='null', sound_emulated=False)
    events = trace['events']
    if events != sorted(events, key=lambda event: event['frame']):
        raise ValueError('reference events must be sorted by frame')
    previous = 0
    event_index = 0
    results = []
    shades = {(255,255,255):0, (153,153,153):1, (85,85,85):2, (0,0,0):3}
    try:
        for checkpoint in trace['checkpoints']:
            frame = checkpoint['frame']
            if frame <= previous or frame > trace['frames']:
                raise ValueError('checkpoints must be increasing and within the trace')
            while event_index < len(events) and events[event_index]['frame'] < frame:
                event = events[event_index]
                if event['frame'] < previous:
                    raise ValueError('event precedes current frame')
                if event['frame'] > previous:
                    emulator.tick(event['frame'] - previous, render=True, sound=False)
                    previous = event['frame']
                if event['edge'] == 'down':
                    emulator.button_press(event['button'])
                elif event['edge'] == 'up':
                    emulator.button_release(event['button'])
                else:
                    raise ValueError('invalid button edge')
                event_index += 1
            emulator.tick(frame - previous, render=True, sound=False)
            previous = frame
            image = emulator.screen.image.convert('RGB')
            if image.size != (WIDTH, HEIGHT):
                raise ValueError(f'unexpected reference dimensions: {image.size}')
            pixels = bytes(shades[image.getpixel((x, y))] for y in range(HEIGHT) for x in range(WIDTH))
            state = {name: emulator.memory[address] for name, address in (
                ('map_id', 0xd35e), ('x', 0xd362), ('y', 0xd361),
                ('movement_direction_raw', 0xd52a), ('sprite_facing_raw', 0xc109),
                ('party_count', 0xd163), ('party_species', 0xd16b), ('party_level', 0xd18c), ('party_hp_low', 0xd16d), ('battle_kind', 0xd057), ('bag_count', 0xd31d), ('first_bag_item', 0xd31e), ('badges', 0xd356))}
            digits = bytes(emulator.memory[0xd347:0xd34a]).hex()
            state['money'] = int(digits) if all(char.isdigit() for char in digits) else None
            state['bag_items'] = [{'id': emulator.memory[0xd31e + i * 2], 'quantity': emulator.memory[0xd31f + i * 2]} for i in range(state['bag_count'])]
            results.append((pixels, state, event_index))
    finally:
        emulator.stop(save=False)
    return results



async def english_checkpoints(checkpoints, actions):
    from englishscript import compile_file
    from englishscript.libraries import page
    frames, worlds = [], []
    def on_world(world):
        worlds.append(world)
        page.use_remote_canvas(world, lambda serial, name, width, height, pixels: frames.append((name, width, height, bytes(pixels))))
    async def model(*args):
        return ''
    await compile_file(ROOT / 'docs/red/main.english').run_async(out=lambda *_: None, model=model, on_world=on_world)
    if not worlds:
        raise RuntimeError('EnglishScript did not initialize a world')
    world = worlds[0]
    controls = world.named['controls']
    cursor = 0
    results = []
    for checkpoint in checkpoints:
        count = checkpoint['english_actions']
        if count <= cursor or count > len(actions):
            raise ValueError('English action checkpoints must be increasing and within the action path')
        for index in range(cursor, count):
            controls.fields['rendering'] = int(index == count - 1)
            accepted = world.event(lambda: controls.fields.__setitem__('action', actions[index]))
            if not accepted:
                raise RuntimeError(f'English world ended at action {index}')
        cursor = count
        page.sync(world)
        if not frames:
            raise RuntimeError('EnglishScript emitted no canvas frame')
        name, width, height, pixels = frames[-1]
        if (width, height) != (WIDTH, HEIGHT) or len(pixels) != WIDTH * HEIGHT or any(pixel > 3 for pixel in pixels):
            raise RuntimeError(f'invalid English frame: {name}, {width}x{height}')
        results.append((pixels, dict(world.named['journey'].fields)))
    return results


def run(rom, reference, english_actions):
    results = []
    snapshots = reference_checkpoints(rom, reference)
    english_snapshots = asyncio.run(english_checkpoints(reference['checkpoints'], english_actions))
    for checkpoint, (original_pixels, original_state, edges), (english_pixels, english_state) in zip(reference['checkpoints'], snapshots, english_snapshots):
        frame = checkpoint['frame']
        count = checkpoint['english_actions']
        changed, first = compare_frames(original_pixels, english_pixels, WIDTH, HEIGHT)
        state = {key: english_state.get(key) for key in ('place', 'mode', 'column', 'row', 'facing', 'trainer', 'rival', 'starter', 'badge', 'stage', 'parcel', 'dex', 'tm34', 'wallet')}
        for key in ('column', 'row', 'badge', 'parcel', 'dex', 'tm34', 'wallet'):
            state[key] = as_int(state[key])
        result = {
            'checkpoint': checkpoint['name'], 'reference_frame': frame,
            'reference_button_edges': edges, 'english_actions': count,
            'reference_state': original_state, 'english_state': state,
            'alignment': alignment(original_state, state),
            'mismatched_pixels': changed, 'total_pixels': WIDTH * HEIGHT,
            'first_mismatch': None if first is None else dict(zip(('x', 'y', 'reference_shade', 'english_shade'), first)),
            'interpretation': 'Independent paths and clocks; basic alignment flags do not establish matching dialogue, battle phases, or identity.',
        }
        results.append(result)
        print(json.dumps(result), flush=True)
    return results



def compare_reward_snapshot(rom, snapshot, actions):
    if hashlib.sha1(rom.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError('ROM SHA-1 does not match the pinned upstream English Red build')
    if importlib.metadata.version('pyboy') != '2.9.0':
        raise ValueError('This benchmark is pinned to PyBoy 2.9.0')
    from pyboy import PyBoy
    emulator = PyBoy(str(rom), window='null', sound_emulated=False)
    shades = {(255,255,255):0, (153,153,153):1, (85,85,85):2, (0,0,0):3}
    try:
        with snapshot.open('rb') as source:
            emulator.load_state(source)
        image = emulator.screen.image.convert('RGB')
        if image.size != (WIDTH, HEIGHT):
            raise ValueError('invalid snapshot frame dimensions')
        pixels = bytes(shades[image.getpixel((x,y))] for y in range(HEIGHT) for x in range(WIDTH))
        original = {name: emulator.memory[address] for name, address in (
            ('map_id', 0xd35e), ('x', 0xd362), ('y', 0xd361), ('sprite_facing_raw', 0xc109),
            ('party_count', 0xd163), ('party_species', 0xd16b), ('party_level', 0xd18c),
            ('party_hp_low', 0xd16d), ('bag_count', 0xd31d), ('first_bag_item', 0xd31e),
            ('badges', 0xd356))}
    finally:
        emulator.stop(save=False)
    checkpoint = {'english_actions': len(actions)}
    actual, raw = asyncio.run(english_checkpoints([checkpoint], actions))[0]
    state = {key: raw.get(key) for key in ('place', 'mode', 'column', 'row', 'facing', 'trainer', 'rival', 'starter', 'badge', 'stage', 'parcel', 'dex', 'tm34', 'wallet')}
    for key in ('column', 'row', 'badge', 'parcel', 'dex', 'tm34', 'wallet'):
        state[key] = as_int(state[key])
    changed, first = compare_frames(pixels, actual, WIDTH, HEIGHT)
    result = {
        'checkpoint': 'brock_reward_snapshot', 'reference_frame': None,
        'reference_button_edges': None, 'english_actions': len(actions),
        'reference_state': original, 'english_state': state,
        'alignment': alignment(original, state), 'mismatched_pixels': changed,
        'total_pixels': WIDTH * HEIGHT,
        'first_mismatch': None if first is None else dict(zip(('x', 'y', 'reference_shade', 'english_shade'), first)),
        'interpretation': 'Original uses a private, independently controller-verified saved state; it is not part of the cold-boot trace. Timing, dialogue, position and battle phase are not assumed aligned.',
    }
    print(json.dumps(result), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True, type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--reward-state', type=Path, help='optional private genuine original post-Brock emulator save state')
    args = parser.parse_args()
    try:
        reference = json.loads((ROOT / 'tests/fixtures/red-segment-reference.json').read_text())
        actions = json.loads((ROOT / 'tests/fixtures/red-segment-english.json').read_text())
        results = run(args.rom, reference, actions)
        if args.reward_state:
            reward_actions = json.loads((ROOT / 'tests/fixtures/red-segment-reward-english.json').read_text())
            results.append(compare_reward_snapshot(args.rom, args.reward_state, reward_actions))
        args.out.write_text(json.dumps({'scope': 'Independent early-game controller checkpoints; state and timing are not assumed equivalent.', 'results': results}, indent=2) + '\n', encoding='utf-8')
        return 1 if any(row['mismatched_pixels'] or not all(row['alignment'].values()) for row in results) else 0
    except Exception as exc:
        print(f'benchmark failed: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())

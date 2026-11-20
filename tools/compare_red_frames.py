#!/usr/bin/env python3
"""Compare live EnglishScript output with a user-built original Red ROM.

Install PyBoy 2.9.0 and Pillow in the Python environment, then for example:
  python tools/compare_red_frames.py --rom /private/pokered.gbc --reference-frame 1400 --ticks 144
The reference frame is counted from emulator startup (including the default PyBoy
boot ROM); ticks are explicit EnglishScript input events, not assumed equivalent
in duration. A frame match is meaningful only at matching animation states.
A trace JSON contains {"frames": 1500, "events": [{"frame": 1400,
"button": "start", "edge": "down"}, {"frame": 1408, "button": "start",
"edge": "up"}], "english_tick_frames": [10, 20]}. Events occur at the
boundary after the indicated number of original frames. Button downs are
sent to both programs; releases are applied only to PyBoy because the English
interface has no release event. English ticks must be explicitly scheduled.
Replay the original bedroom and navigate English independently to the same
RED/BLUE starting position with:
  python tools/compare_red_frames.py --rom /private/pokered.gbc --trace tests/fixtures/red-bedroom-trace.json --independent-english --actions a,a,a,a,a,a,a,a,a,a,down,a,down,a
The state and timing remain distinct and must be checked at the checkpoint.
No reference files are written unless --diff is specified; keep those private.
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
EXPECTED = 'ea9bcae617fdf159b045185467ae58b2e4a48b9a'
WIDTH, HEIGHT = 160, 144

async def english_frame(actions):
    from englishscript import compile_file
    from englishscript.libraries import page
    frames, worlds = [], []
    def on_world(world):
        worlds.append(world)
        page.use_remote_canvas(world, lambda serial, name, w, h, pixels: frames.append((name, w, h, pixels)))
    async def model(*args):
        return ''
    await compile_file(ROOT / 'docs/red/main.english').run_async(out=lambda *_: None, model=model, on_world=on_world)
    if not worlds:
        raise RuntimeError('EnglishScript did not initialize a world')
    world = worlds[0]
    controls = world.named['controls']
    for action in actions:
        world.event(lambda: controls.fields.__setitem__('action', action))
    page.sync(world)
    if not frames:
        raise RuntimeError('EnglishScript emitted no canvas frame')
    name, w, h, pixels = frames[-1]
    if (w,h) != (WIDTH,HEIGHT) or len(pixels) != WIDTH*HEIGHT or any(p > 3 for p in pixels):
        raise RuntimeError(f'invalid English frame {name}: {w}x{h}, {len(pixels)} bytes or non-DMG shade')
    return bytes(pixels), world.named['journey'].fields

def reference_frame(rom, count, events):
    if hashlib.sha1(rom.read_bytes()).hexdigest() != EXPECTED:
        raise ValueError('ROM SHA-1 does not match the pinned upstream English Red build')
    if importlib.metadata.version('pyboy') != '2.9.0':
        raise ValueError('This comparison is pinned to PyBoy 2.9.0')
    from pyboy import PyBoy
    p = PyBoy(str(rom), window='null', sound_emulated=False)
    try:
        cursor = 0
        for event in events:
            target = event['frame']
            if target > cursor:
                p.tick(target - cursor, render=True, sound=False)
                cursor = target
            if event['edge'] == 'down':
                p.button_press(event['button'])
            else:
                p.button_release(event['button'])
        if cursor < count:
            p.tick(count - cursor, render=True, sound=False)
        reference_state = {name: p.memory[address] for name, address in (
            ('map_id', 0xd35e), ('x', 0xd362), ('y', 0xd361),
            ('movement_direction_raw', 0xd52a), ('sprite_facing_raw', 0xc109), ('party_count', 0xd163), ('badges', 0xd356))}
        image = p.screen.image.convert('RGB')
        if image.size != (WIDTH,HEIGHT):
            raise ValueError(f'unexpected reference dimensions: {image.size}')
        shades = {(255,255,255):0,(153,153,153):1,(85,85,85):2,(0,0,0):3}
        try:
            return bytes(shades[image.getpixel((x, y))] for y in range(HEIGHT) for x in range(WIDTH)), reference_state
        except KeyError as e:
            raise ValueError(f'unexpected PyBoy palette color: {e}') from e
    finally:
        p.stop(save=False)

def compare_frames(reference, actual, width, height):
    if width < 1 or height < 1 or len(reference) != width * height or len(actual) != width * height:
        raise ValueError('frame dimensions and pixel counts do not agree')
    mismatch_count = 0
    first = None
    for index, (expected, observed) in enumerate(zip(reference, actual)):
        if expected != observed:
            mismatch_count += 1
            if first is None:
                first = (index % width, index // width, expected, observed)
    return mismatch_count, first

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--reference-frame', type=int, help='one-based frame count from PyBoy startup; independent mode')
    parser.add_argument('--trace', type=Path, help='JSON timestamped input trace')
    parser.add_argument('--independent-english', action='store_true', help='with --trace, select the English checkpoint separately using --ticks and --actions')
    parser.add_argument('--ticks', type=int, default=0, help='number of English tick events before actions')
    parser.add_argument('--actions', default='', help='comma-separated English input actions after ticks')
    parser.add_argument('--diff', type=Path, help='optional private PNG: reference, English, and red mismatch mask')
    args = parser.parse_args()
    if args.trace and (args.reference_frame is not None or (not args.independent_english and (args.ticks or args.actions))):
        parser.error('trace cannot be combined with independent checkpoint options')
    if args.independent_english and not args.trace:
        parser.error('--independent-english requires --trace')
    if not args.trace and (args.reference_frame is None or args.reference_frame < 1 or args.ticks < 0):
        parser.error('independent mode requires positive --reference-frame and nonnegative --ticks')
    try:
        if args.trace:
            trace = json.loads(args.trace.read_text(encoding='utf-8-sig'))
            count = trace['frames']
            events = trace['events']
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                raise ValueError('trace frames must be a positive integer')
            held = set()
            previous = 0
            for event in events:
                frame, button, edge = event['frame'], event['button'], event['edge']
                if not isinstance(frame, int) or isinstance(frame, bool) or not previous <= frame < count:
                    raise ValueError('trace event frames must be ordered and within [0, frames)')
                if button not in ('up', 'down', 'left', 'right', 'a', 'b', 'start', 'select'):
                    raise ValueError(f'unknown button {button}')
                if edge == 'down' and button not in held:
                    held.add(button)
                elif edge == 'up' and button in held:
                    held.remove(button)
                else:
                    raise ValueError(f'invalid {edge} edge for {button}')
                previous = frame
            if held:
                raise ValueError(f'trace ends with buttons held: {sorted(held)}')
            ticks = trace.get('english_tick_frames', [])
            if any(not isinstance(t, int) or isinstance(t, bool) or t < 0 or t >= count for t in ticks) or ticks != sorted(ticks):
                raise ValueError('english_tick_frames must be ordered frame boundaries within [0, frames)')
            timeline = [(e['frame'], 1, e['button']) for e in events if e['edge'] == 'down']
            timeline += [(t, 0, 'tick') for t in ticks]
            actions = [item[2] for item in sorted(timeline, key=lambda item: (item[0], item[1]))]
            if args.independent_english:
                actions = ['tick'] * args.ticks + [x.strip() for x in args.actions.split(',') if x.strip()]
                mode = f'independent checkpoints; reference trace frame={count}; English ticks={args.ticks}; actions={actions[args.ticks:]}'
            else:
                mode = f'timestamped trace; frame={count}; down/up edges={len(events)}; English tick events={len(ticks)}'
        else:
            count, events = args.reference_frame, []
            actions = ['tick'] * args.ticks + [x.strip() for x in args.actions.split(',') if x.strip()]
            mode = f'independent checkpoints; reference frame={count}; English ticks={args.ticks}; actions={actions[args.ticks:]}'
        ref, ref_state = reference_frame(args.rom, count, events)
        actual, state = asyncio.run(english_frame(actions))
        changed, first = compare_frames(ref, actual, WIDTH, HEIGHT)
        print(mode)
        print(f'reference state (read-only raw ROM symbols): {ref_state}')
        english_state = {key: state.get(key) for key in ('mode', 'place', 'column', 'row', 'facing', 'animation', 'trainer', 'rival', 'starter', 'badge')}
        print(f'English state: {english_state}')
        print('State and elapsed-time equivalence are not inferred; verify checkpoints and timing separately.')
        if args.trace and not args.independent_english:
            print('Button-down edges are delivered as English actions; English has no button-release event or held-button repeat.')
        print(f'mismatched pixels: {changed}/{WIDTH*HEIGHT} ({100*changed/(WIDTH*HEIGHT):.2f}%)')
        if first is None:
            print('first mismatch: none')
        else:
            x, y, expected, observed = first
            print(f'first mismatch: x={x}, y={y}, reference shade={expected}, English shade={observed}')
        if args.diff:
            from PIL import Image
            shades = [255,153,85,0]
            out = Image.new('RGB',(WIDTH*3,HEIGHT))
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    i=y*WIDTH+x
                    out.putpixel((x,y),(shades[ref[i]],)*3)
                    out.putpixel((WIDTH+x,y),(shades[actual[i]],)*3)
                    out.putpixel((2*WIDTH+x,y),(255,0,0) if ref[i] != actual[i] else (255,255,255))
            out.save(args.diff)
        return 1 if changed else 0
    except Exception as exc:
        print(f'comparison failed: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    sys.exit(main())



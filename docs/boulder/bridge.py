import json
import sys

sys.path.insert(0, "/site")

import js
from englishscript import EnglishError, compile_file
from englishscript.libraries import page

world = None
tick = 0


def frame(serial, name, width, height, pixels):
    js.boulderFrame(int(width), int(height), pixels)


def state():
    if world is None:
        return
    player = world.named.get("player")
    practice = world.named.get("practice")
    if player is None or practice is None:
        return
    js.boulderState(json.dumps({
        "tick": tick,
        "column": int(player.fields["column"]),
        "row": int(player.fields["row"]),
        "steps": int(player.fields["step count"]),
        "result": str(practice.fields["field note"]),
    }))


def remember(current):
    global world
    world = current
    page.use_remote_canvas(world, frame)


async def model(question, context, shape, complaint):
    page.sync(world)
    state()
    js.boulderReady()
    return await js.boulderRequest(str(question))


async def start():
    try:
        program = compile_file("/work/main.english")
        await program.run_async(out=lambda text: js.boulderOutput(str(text)), model=model, on_world=remember)
        page.sync(world)
        state()
        if not world.ended:
            js.boulderReady()
            js.boulderComplete()
    except EnglishError as error:
        js.boulderError(error.render())


def act(action):
    global tick
    if world is None or world.ended:
        return
    controls = world.named.get("input")
    if controls is None:
        return
    try:
        world.event(lambda: controls.fields.__setitem__("action", action))
        tick += 1
        page.sync(world)
        state()
    except EnglishError as error:
        js.boulderError(error.render())


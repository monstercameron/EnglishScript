import json
import sys
import unicodedata
from fractions import Fraction

sys.path.insert(0, "/site")

import js
from englishscript import EnglishError, compile_file
from englishscript.libraries import page

world = None
quiet = False
talk_session = 0
talk_request = 0


def frame(serial, name, width, height, pixels):
    if not quiet:
        js.redFrame(int(width), int(height), pixels)


def state():
    if world is None:
        return
    journey = world.named.get("journey")
    if journey is None:
        return
    values = {str(key): float(value) if isinstance(value, Fraction) else value for key, value in journey.fields.items() if isinstance(value, (str, int, float, bool, Fraction)) or value is None}
    score = world.named.get("score")
    if score is not None:
        values.update({("effectCount" if key == "effect count" else str(key)): float(value) if isinstance(value, Fraction) else value for key, value in score.fields.items() if isinstance(value, (str, int, float, bool, Fraction)) or value is None})
    stock = world.named.get("stock")
    if stock is not None:
        request = stock.fields.get("save request", 0)
        values["save request"] = float(request) if isinstance(request, Fraction) else request
    speaker = world.named.get("speaker")
    if speaker is not None:
        values["speaker"] = str(speaker.fields.get("actor", ""))
        values["response"] = str(speaker.fields.get("response", ""))
    talk = world.named.get("talk")
    if talk is not None:
        values.update({"talkPhase": talk.fields["phase"], "talkSession": talk_session,
                       "talkRequest": talk_request, "talkPerson": talk.fields["actor"],
                       "talkHasMore": bool(talk.fields["remainder"]),
                       "talkPage": visible_page(talk.fields["page"]),
                       "talkRawReply": talk.fields["transcript"]})
    js.redState(json.dumps(values))


def remember(current):
    global world
    world = current
    page.use_remote_canvas(world, frame)


async def model(question, context, shape, complaint):
    return ""


async def start():
    try:
        program = compile_file("/work/main.english")
        await program.run_async(out=lambda text: js.redOutput(str(text)), model=model, on_world=remember)
        page.sync(world)
        state()
        js.redReady()
    except EnglishError as error:
        js.redError(error.render())


def act(action):
    if world is None or world.ended:
        return
    controls = world.named.get("controls")
    if controls is None:
        return
    world.event(lambda: controls.fields.__setitem__("action", action))
    if not quiet:
        page.sync(world)
        state()


def replay(actions):
    global quiet
    history = json.loads(actions)
    controls = world.named.get("controls") if world is not None else None
    if controls is None:
        return
    quiet = True
    controls.fields["rendering"] = 0
    try:
        for action in history[:-1]:
            act(action)
    finally:
        controls.fields["rendering"] = 1
        quiet = False
    if history:
        act(history[-1])
    else:
        page.sync(world)
        state()


def visible_page(text):
    lines = []
    for _ in range(2):
        if len(text) <= 19:
            line = text
        elif text[19] == " ":
            line = text[:19]
        else:
            split = text[:19].rfind(" ")
            line = text[:split] if split >= 0 else text[:19]
        lines.append(line)
        text = text[len(line):].lstrip(" ")
    return " ".join(line for line in lines if line)


def command(name, **fields):
    if world is None or world.ended:
        return False
    talk = world.named.get("talk")
    if talk is None:
        return False
    def update():
        talk.fields.update(fields)
        talk.fields["command"] = name
    world.event(update)
    return True


def publish():
    page.sync(world)
    state()


def talk_open():
    global talk_session, talk_request
    if world is None or world.ended:
        return
    talk = world.named.get("talk")
    if talk is None or talk.fields["phase"] != "closed":
        return
    command("open")
    if talk.fields["phase"] == "composing":
        talk_session += 1
        talk_request = 0
    publish()


def talk_ask(session, request, question):
    global talk_request
    if world is None or world.ended:
        return ""
    talk = world.named.get("talk")
    if talk is None or talk.fields["phase"] != "composing" or session != talk_session or request <= talk_request or not question.strip():
        return ""
    talk_request = request
    command("ask", question=question[:200])
    speaker = world.named["speaker"].fields
    result = {name: speaker[name] for name in ("identity", "profile", "voice", "question", "response")}
    result["person"] = speaker["actor"]
    publish()
    return json.dumps(result)


def display_text(text):
    replacements = str.maketrans({"\u2018": "'", "\u2019": "'", "\u201c": "'", "\u201d": "'",
                                  "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00a0": " "})
    text = unicodedata.normalize("NFKD", text.translate(replacements))
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,;:!?-' /()\u2642\u2640"
    return " ".join("".join(c if c in allowed else "" if unicodedata.combining(c) else " " if c.isspace() else "?" for c in text).split())


def talk_reply(session, request, response):
    if world is None or world.ended:
        return
    talk = world.named.get("talk")
    if talk is None or talk.fields["phase"] != "waiting" or session != talk_session or request != talk_request:
        return
    command("reply", wording=display_text(response)[:2000], transcript=response)
    publish()


def talk_page(session):
    if world is None or world.ended:
        return
    talk = world.named.get("talk")
    if talk is None or talk.fields["phase"] != "reply" or session != talk_session:
        return
    command("page")
    publish()


def talk_close(session):
    if world is None or world.ended:
        return
    talk = world.named.get("talk")
    if talk is None or talk.fields["phase"] == "closed" or session != talk_session:
        return
    command("close")
    publish()

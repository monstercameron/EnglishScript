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
REPLY_LIMIT = 2000

PAGE_MODES = {"opening": "opening", "title": "title", "main menu": "menu", "intro": "intro", "naming": "naming",
              "custom naming": "custom naming", "rival naming": "rival naming",
              "custom rival naming": "custom rival naming", "walk": "walk", "dialogue": "dialogue",
              "starter": "starter", "battle": "battle", "battle party": "battle party", "battle bag": "battle bag",
              "field menu": "field menu", "party": "party", "bag": "bag", "trainer card": "card",
              "town map": "town map", "shop": "shop"}

CONTRACT = {
    "journey": {"mode": "mode", "place": str, "objective": str, "starter": str,
                "trainer": str, "message": str, "badge": "number", "tm34": "number"},
    "controls": {"action": str, "rendering": "number"},
    "stock": {"save request": "number"},
    "speaker": {name: str for name in ("actor", "question", "response", "identity", "profile", "voice")},
    "talk": {name: str for name in ("command", "phase", "actor", "question", "wording", "transcript", "page", "remainder")},
    "score": {**{name: str for name in ("music", "melody", "harmony", "bass", "percussion",
                                        "intro melody", "intro harmony", "intro bass", "intro percussion", "effect", "cry")},
              **{name: "number" for name in ("tempo", "effect priority", "effect count", "cry count")}},
}


class ContractError(ValueError):
    pass


def described(expected):
    return "text" if expected is str else "a mode" if expected == "mode" else expected


def fits(value, expected):
    if expected is str:
        return isinstance(value, str)
    if expected == "mode":
        return value in PAGE_MODES
    return isinstance(value, (int, float, Fraction)) and not isinstance(value, bool)


def validate_contract(current):
    for name, fields in CONTRACT.items():
        entity = current.named.get(name)
        if entity is None:
            raise ContractError(f"Red bridge requires an object named '{name}'.")
        for field, expected in fields.items():
            if field not in entity.fields:
                raise ContractError(f"Red bridge requires '{name}.{field}' ({described(expected)}).")
            value = entity.fields[field]
            if not fits(value, expected):
                raise ContractError(f"Red bridge requires '{name}.{field}' to be {described(expected)}; got {type(value).__name__}.")


def frame(serial, name, width, height, pixels):
    if not quiet:
        js.redFrame(int(width), int(height), pixels)


def plain(value):
    return float(value) if isinstance(value, Fraction) else value


def plain_fields(entity):
    return {str(key): plain(value) for key, value in entity.fields.items()
            if value is None or isinstance(value, (str, int, float, bool, Fraction))}


def state():
    values = plain_fields(world.named["journey"])
    values["mode"] = PAGE_MODES[values["mode"]]
    score = plain_fields(world.named["score"])
    score["effectCount"] = score.pop("effect count")
    values.update(score)
    values["save request"] = plain(world.named["stock"].fields["save request"])
    speaker = world.named["speaker"].fields
    values["speaker"] = str(speaker["actor"])
    values["response"] = str(speaker["response"])
    talk = world.named["talk"].fields
    values.update({"talkPhase": "reply" if talk["phase"] == "answering" else talk["phase"], "talkSession": talk_session,
                   "talkRequest": talk_request, "talkPerson": talk["actor"],
                   "talkHasMore": bool(talk["remainder"]),
                   "talkPage": visible_page(talk["page"]),
                   "talkRawReply": talk["transcript"]})
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
        await program.run_async(out=print, model=model, on_world=remember)
        validate_contract(world)
        page.sync(world)
        state()
        js.redReady()
    except EnglishError as error:
        js.redError(error.render())
    except ContractError as error:
        js.redError(str(error))


def act(action):
    if world is None or world.ended:
        return
    controls = world.named["controls"].fields
    world.event(lambda: controls.__setitem__("action", action))
    if not quiet:
        publish()


def replay(actions):
    global quiet
    history = json.loads(actions)
    controls = world.named["controls"].fields
    quiet = True
    controls["rendering"] = 0
    try:
        for action in history[:-1]:
            act(action)
    finally:
        controls["rendering"] = 1
        quiet = False
    if history:
        act(history[-1])
    else:
        publish()


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
    talk = world.named["talk"].fields
    def update():
        talk.update(fields)
        talk["command"] = name
    world.event(update)


def current_talk():
    if world is None or world.ended:
        return None
    return world.named["talk"].fields


def publish():
    page.sync(world)
    state()


def talk_open():
    global talk_session, talk_request
    talk = current_talk()
    if talk is None or talk["phase"] != "closed":
        return
    command("open")
    if talk["phase"] == "composing":
        talk_session += 1
        talk_request = 0
    publish()


def talk_ask(session, request, question):
    global talk_request
    talk = current_talk()
    if talk is None or talk["phase"] != "composing" or session != talk_session or request <= talk_request or not question.strip():
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
    talk = current_talk()
    if talk is None or talk["phase"] != "waiting" or session != talk_session or request != talk_request:
        return
    response = response[:REPLY_LIMIT]
    command("reply", wording=display_text(response)[:REPLY_LIMIT], transcript=response)
    publish()


def talk_page(session):
    talk = current_talk()
    if talk is None or talk["phase"] != "answering" or session != talk_session:
        return
    command("page")
    publish()


def talk_close(session):
    talk = current_talk()
    if talk is None or talk["phase"] == "closed" or session != talk_session:
        return
    command("close")
    publish()

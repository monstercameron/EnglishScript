import argparse
import asyncio
import json
import os
import secrets
import threading
import time
from http.cookies import SimpleCookie, CookieError
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from englishscript import compile_file, models

PERCEPTIONS = frozenset(("neutral", "friendly", "rude", "cruel", "flirting", "uncertain"))


async def answer_companion(data, system1, keys=None):
    keys = keys or {}
    if system1 == "jev" and keys.get("jev"):
        jev = models.Jev(api_key=keys["jev"])
        listeners = models.Listeners(None, jev.judge, jev.judges)
    else:
        listeners = models.connect(system1)
    _, judge = listeners
    writer_listener = (models.OpenAIWriter("gpt-6-luna", api_key=keys["openai"]).model
                       if keys.get("openai") else models.connect("openai:gpt-6-luna")[0])
    answers = iter((data["actor"], data["question"], data["context"],
                    data.get("profile", "No additional background is available."),
                    data.get("voice", "Speak naturally in character.")))
    output = []

    async def writer(*args):
        return await asyncio.to_thread(writer_listener, *args)

    program = compile_file(ROOT / "docs" / "red" / "companion_model.english")
    await program.run_async(ask=lambda _: next(answers), out=output.append,
                            model=writer, judge=judge, judges=listeners.judges)
    if (len(output) != 2 or output[0] not in PERCEPTIONS or
            not isinstance(output[1], str) or not output[1].strip()):
        raise ValueError("Invalid companion response")
    return {"reply": output[1], "perception": output[0]}


class KeySessions:
    def __init__(self):
        self.lock = threading.Lock()
        self.sessions = {}

    def _prune(self):
        now = time.monotonic()
        self.sessions = {token: item for token, item in self.sessions.items() if item[0] > now}

    def get(self, token):
        with self.lock:
            self._prune()
            return dict(self.sessions.get(token, (0, {}))[1])

    def put(self, token, keys):
        with self.lock:
            self._prune()
            if token not in self.sessions:
                if len(self.sessions) >= 256:
                    raise ValueError("Too many sessions")
                token = secrets.token_urlsafe(32)
            current = dict(self.sessions.get(token, (0, {}))[1])
            current.update(keys)
            self.sessions[token] = (time.monotonic() + 3600, current)
            return token

    def delete(self, token):
        with self.lock:
            self._prune()
            self.sessions.pop(token, None)


class RedHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=str(ROOT / "docs"), **kwargs)

    def end_headers(self):
        if self.path.startswith("/api/companion"):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def token(self):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get("Cookie", ""))
            return cookie["red_companion"].value if "red_companion" in cookie else ""
        except CookieError:
            return ""

    def authorized(self, origin=False):
        expected = f"127.0.0.1:{self.server.server_port}"
        return (self.headers.get("Host") == expected and
                (not origin or self.headers.get("Origin") == "http://" + expected))

    def respond(self, result, cookie=None):
        body = json.dumps(result, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cookie is not None:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def read_json(self, maximum):
        if self.headers.get_content_type() != "application/json" or self.headers.get("Transfer-Encoding"):
            raise ValueError()
        length = int(self.headers.get("Content-Length", ""))
        if length < 1 or length > maximum:
            raise ValueError()
        data = json.loads(self.rfile.read(length))
        if not isinstance(data, dict):
            raise ValueError()
        return data

    def do_GET(self):
        if self.path != "/api/companion":
            return super().do_GET()
        if not self.authorized():
            self.send_error(403)
            return
        keys = self.server.key_sessions.get(self.token())
        jev = bool(keys.get("jev") or os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY"))
        openai = bool(keys.get("openai") or os.environ.get("OPENAI_API_KEY"))
        judge = bool(os.environ.get("ANTHROPIC_API_KEY")) if self.server.system1 == "anthropic" else jev
        self.respond({"available": judge and openai, "jev": jev, "openai": openai,
                      "sessionKeys": bool(keys), "judge": self.server.system1})

    def do_POST(self):
        if self.path not in ("/api/companion", "/api/companion/keys"):
            self.send_error(404)
            return
        if not self.authorized(origin=True):
            self.send_error(403)
            return
        try:
            data = self.read_json(16384 if self.path == "/api/companion" else 4096)
            if self.path == "/api/companion/keys":
                if set(data) - {"jev", "openai"} or not data:
                    raise ValueError()
                if any(not isinstance(value, str) or len(value) > 1024 or
                       any(ord(c) < 32 or ord(c) == 127 for c in value) for value in data.values()):
                    raise ValueError()
                keys = {name: value.strip() for name, value in data.items() if value.strip()}
                if not keys:
                    raise ValueError()
                token = self.server.key_sessions.put(self.token(), keys)
                self.respond({"ok": True}, f"red_companion={token}; HttpOnly; SameSite=Strict; Path=/api/companion; Max-Age=3600")
                return
            if (not {"actor", "question", "context"} <= set(data) or
                    set(data) - {"actor", "question", "context", "profile", "voice"}):
                raise ValueError()
            if any(not isinstance(data[k], str) or not data[k].strip() or len(data[k]) > limit
                   for k, limit in (("actor", 80), ("question", 1000), ("context", 4000),
                                    ("profile", 2000), ("voice", 1000)) if k in data):
                raise ValueError()
        except (ValueError, UnicodeDecodeError):
            self.send_error(400)
            return
        try:
            keys = self.server.key_sessions.get(self.token())
            result = asyncio.run(answer_companion(data, self.server.system1, keys))
        except Exception:
            self.send_error(503, "Companion unavailable")
            return
        self.respond(result)

    def do_DELETE(self):
        if self.path != "/api/companion/keys":
            self.send_error(404)
            return
        if not self.authorized(origin=True):
            self.send_error(403)
            return
        self.server.key_sessions.delete(self.token())
        self.respond({"ok": True}, "red_companion=; HttpOnly; SameSite=Strict; Path=/api/companion; Max-Age=0")

    def log_message(self, format, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description="Serve Red and its optional local companion.")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--system1", choices=("jev", "anthropic"), default="jev")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), RedHandler)
    server.system1 = args.system1
    server.key_sessions = KeySessions()
    print(f"Red: http://127.0.0.1:{server.server_port}/red/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()



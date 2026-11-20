import asyncio
import io
import json
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import patch

from tools import serve_red


class RedServerTests(unittest.TestCase):
    def test_real_companion_program_uses_configured_listeners(self):
        calls = []
        seen = []

        def connect(spec):
            calls.append(spec)
            if spec == "jev":
                def judge(question, state, choices, meanings):
                    seen.append(state)
                    return {choice: float(choice == "friendly") for choice in choices}
                return serve_red.models.Listeners(None, judge)
            def writer(question, *args):
                seen.append(question)
                return "OAK: Hello, trainer."
            return serve_red.models.Listeners(writer, None)

        with patch.object(serve_red.models, "connect", side_effect=connect):
            result = asyncio.run(serve_red.answer_companion(
                {"actor": "Oak", "question": "Hello!", "context": "Oak is in his lab.",
                 "profile": "Oak appreciates politeness.", "voice": "Warm and thoughtful."}, "jev"))
        self.assertEqual(result, {"reply": "OAK: Hello, trainer.", "perception": "friendly"})
        self.assertEqual(calls, ["jev", "openai:gpt-6-luna"])
        self.assertIn("Oak appreciates politeness", seen[0])
        self.assertIn("perceives the quoted dialogue as friendly", seen[1])

    def request(self, data=None, answer=None, origin="http://127.0.0.1:8767", method="POST", path="/api/companion", cookie="", sessions=None):
        body = json.dumps(data).encode()
        handler = object.__new__(serve_red.RedHandler)
        handler.server = SimpleNamespace(server_port=8767, system1="jev", key_sessions=sessions or serve_red.KeySessions())
        handler.path = path
        handler.headers = Message()
        handler.headers["Host"] = "127.0.0.1:8767"
        handler.headers["Origin"] = origin
        if cookie:
            handler.headers["Cookie"] = cookie
        handler.headers["Content-Type"] = "application/json"
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        statuses = []
        handler.send_error = lambda code, *args: statuses.append(code)
        handler.send_response = lambda code: statuses.append(code)
        headers = {}
        handler.send_header = lambda name, value: headers.update({name: value})
        handler.end_headers = lambda: None
        with patch.object(serve_red, "answer_companion", side_effect=answer):
            getattr(handler, "do_" + method)()
        return statuses[0], handler.wfile.getvalue(), headers

    def test_validation_legacy_and_provider_failure(self):
        data = {"actor": "Oak", "question": "Hello", "context": "Oak is a professor."}
        async def answer(data, system1, keys):
            return {"reply": "Hello!", "perception": "friendly"}
        status, body, _ = self.request(data, answer)
        self.assertEqual((status, json.loads(body)), (200, {"reply": "Hello!", "perception": "friendly"}))
        self.assertEqual(self.request(data, answer, "http://evil.example")[0], 403)
        self.assertEqual(self.request({**data, "extra": "x"}, answer)[0], 400)
        self.assertEqual(self.request({**data, "profile": "x" * 2001}, answer)[0], 400)
        self.assertEqual(self.request(data, RuntimeError("secret"))[0], 503)


    def test_session_keys_isolate_browsers_and_keep_defaults(self):
        sessions = serve_red.KeySessions()
        path = "/api/companion/keys"
        with patch.dict(serve_red.os.environ, {"JEV_API_KEY": "default-jev"}, clear=True):
            status, body, headers = self.request({"openai": "123456789", "jev": ""}, path=path, sessions=sessions)
            self.assertEqual(status, 200)
            self.assertNotIn(b"123456789", body)
            cookie = headers["Set-Cookie"].split(";", 1)[0]
            self.assertIn("HttpOnly", headers["Set-Cookie"])
            self.assertIn("SameSite=Strict", headers["Set-Cookie"])
            status, body, _ = self.request(method="GET", cookie=cookie, sessions=sessions)
            self.assertEqual(json.loads(body), {"available": True, "jev": True, "openai": True, "sessionKeys": True, "judge": "jev"})
            status, body, _ = self.request(method="GET", sessions=sessions)
            self.assertEqual(json.loads(body), {"available": False, "jev": True, "openai": False, "sessionKeys": False, "judge": "jev"})
            _, _, second_headers = self.request({"jev": "other-session"}, path=path, sessions=sessions)
            second_cookie = second_headers["Set-Cookie"].split(";", 1)[0]
            received = []
            async def answer(data, system1, keys):
                received.append(keys)
                return {"reply": "Hello!", "perception": "neutral"}
            data = {"actor": "Oak", "question": "Hello", "context": "In a lab"}
            self.request(data, answer, cookie=cookie, sessions=sessions)
            self.request(data, answer, sessions=sessions)
            self.request(data, answer, cookie=second_cookie, sessions=sessions)
            self.assertEqual(received, [{"openai": "123456789"}, {}, {"jev": "other-session"}])
            self.assertEqual(self.request(method="DELETE", path=path, cookie=cookie, sessions=sessions)[0], 200)
            self.assertFalse(json.loads(self.request(method="GET", cookie=cookie, sessions=sessions)[1])["openai"])
            self.assertEqual(self.request({"jev": " "}, path=path, sessions=sessions)[0], 400)
            self.assertEqual(self.request({"jev": "secret"}, path=path, sessions=sessions, origin="http://evil.example")[0], 403)

    def test_instance_keys_do_not_touch_environment(self):
        with patch.dict(serve_red.os.environ, {"JEV_API_KEY": "env-jev", "OPENAI_API_KEY": "env-openai"}, clear=True):
            jev = serve_red.models.Jev(api_key="session-jev")
            writer = serve_red.models.OpenAIWriter("gpt-6-luna", api_key="123456789")
            seen = []
            def fail(request, timeout):
                seen.append(request.get_header("Authorization"))
                raise OSError("offline")
            with patch.object(serve_red.models.urllib.request, "urlopen", side_effect=fail):
                with self.assertRaises(Exception):
                    jev._post({})
                with self.assertRaises(Exception):
                    writer.model("Hello", None, {"type": "text"}, None)
            self.assertEqual(seen, ["Bearer session-jev", "Bearer 123456789"])
            self.assertEqual(serve_red.os.environ["OPENAI_API_KEY"], "env-openai")


if __name__ == "__main__":
    unittest.main()

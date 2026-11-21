import math
import re
import unittest
from pathlib import Path

from englishscript import compile_file


SOUND = Path(__file__).resolve().parents[1] / "docs" / "red" / "sound.english"
VOICES = ("melody", "intro melody", "harmony", "intro harmony", "bass",
          "intro bass", "intro percussion", "percussion")
TOKEN = re.compile(r"(\d+|noise):(\d+(?:\.\d+)?)\Z", re.ASCII)


def validate_voice(cue, voice, source):
    for token in source.split():
        match = TOKEN.fullmatch(token)
        valid = bool(match)
        if match:
            pitch, length = match.groups()
            duration = float(length)
            valid = math.isfinite(duration) and duration > 0
            if voice.endswith("percussion"):
                valid = valid and pitch in ("0", "noise")
            else:
                valid = valid and pitch != "noise" and 0 <= int(pitch) <= 127
        if not valid:
            raise ValueError(f"{cue}: {voice}: invalid token {token!r}")


class RedAudioScores(unittest.TestCase):
    def test_authored_scores(self):
        compiler = compile_file(SOUND).compiler
        table = compiler.fact_tables["scores"]
        properties = dict(compiler.kinds[table.kind].props.every())
        self.assertTrue({"tempo", *VOICES} <= properties.keys())
        rows = [row for row in table.rows.values() if not row.removed]
        self.assertTrue(rows)
        for row in rows:
            cue = row.name
            fields = {name: properties[name].fn(None, row) for name in ("tempo", *VOICES)}
            self.assertTrue(40 <= fields["tempo"] <= 300, (cue, "tempo"))
            for voice in VOICES:
                validate_voice(cue, voice, fields[voice])
            for voice in ("melody", "harmony", "bass"):
                self.assertTrue(fields[voice].strip(), (cue, voice))

    def test_invalid_tokens_identify_cue_and_voice(self):
        for voice, token in (("melody", "noise:1"), ("percussion", "69:1"),
                             ("intro bass", "128:1"), ("melody", "-1:1"),
                             ("melody", "1.5:1"), ("melody", "60:0"),
                             ("melody", "60:1:2"), ("melody", "60~61:1"),
                             ("melody", "60:1e2"), ("melody", "60:Infinity")):
            with self.subTest(voice=voice, token=token):
                with self.assertRaisesRegex(ValueError, re.escape(f"test cue: {voice}: invalid token '{token}'")):
                    validate_voice("test cue", voice, token)

    def test_valid_tokens(self):
        validate_voice("test cue", "melody", "0:0.5 1:1 127:1.3333")
        validate_voice("test cue", "intro percussion", "0:160.0 noise:0.5")


if __name__ == "__main__":
    unittest.main()

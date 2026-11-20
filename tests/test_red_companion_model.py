import unittest
from pathlib import Path

from englishscript import compile_file

BOOK = Path(__file__).resolve().parents[1] / "docs" / "red" / "companion_model.english"


class CompanionModel(unittest.IsolatedAsyncioTestCase):
    async def test_perception_uses_profile_context_and_exact_dialogue(self):
        inputs = iter(["Oak", "Nice work, genius.", "Oak is in his lab.",
                       "Oak is sensitive to sarcasm.", "Gentle and thoughtful"])
        output = []
        judgments = []
        models = []

        def judge(question, state, choices, meanings):
            judgments.append((question, state, choices, meanings))
            return {choice: float(choice == "rude") for choice in choices}

        async def model(question, state, shape, complaint):
            models.append((question, state, shape, complaint))
            return "OAK: That was unkind."

        await compile_file(BOOK).run_async(ask=lambda _: next(inputs), judge=judge,
                                           model=model, out=output.append)
        self.assertIn("Nice work, genius.", judgments[0][1])
        self.assertIn("sensitive to sarcasm", judgments[0][1])
        self.assertIn("Oak is in his lab", judgments[0][1])
        self.assertIn("rude", judgments[0][2])
        self.assertIn("perceives the quoted dialogue as rude", models[0][0])
        self.assertIn("Gentle and thoughtful", models[0][0])
        self.assertEqual(output, ["rude", "OAK: That was unkind."])


if __name__ == "__main__":
    unittest.main()

import unittest
import re
from pathlib import Path

from englishscript import compile_source


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


def talk(person, question, setup=""):
    source = f'''Use the foundation chapter.
Use the people chapter.
{setup}
Converse with "{person}" about "{question}".
Say Speaker's response.
Say Journey's stage.
Say Journey's objective.
Say Journey's parcel.
Say Journey's dex.
Say Journey's badge.
Say Journey's mode.
'''
    lines = []
    compile_source(source, folder=RED).run(out=lines.append)
    return lines


class RedPeople(unittest.TestCase):
    """Profiles add original character material to the game's mapped placements."""
    def test_distinct_personas_and_questions(self):
        oak = talk("Oak", "Tell me about wild Pokemon")[0]
        mom = talk("Mom", "Tell me about Pokemon")[0]
        rival = talk("Rival", "Tell me about Pokemon")[0]
        self.assertIn("tall grass", oak)
        self.assertIn("kind", mom)
        self.assertIn("own", rival)
        self.assertNotEqual(oak, talk("Oak", "Tell me about your starter")[0])

    def test_companions_only_observe_progress(self):
        setup = '''Set Journey's stage to "parcel".
Set Journey's objective to "Deliver it".
Set Journey's parcel to 1.
Set Journey's dex to 0.
Set Journey's badge to 0.
Set Journey's mode to "walk".'''
        answer = talk("Oak", "parcel", setup)
        self.assertIn("normally", answer[0])
        self.assertEqual(answer[1:7], ["parcel", "Deliver it", "1", "0", "0", "walk"])

    def test_knowledge_tracks_journey(self):
        self.assertIn("more work", talk("Oak", "pokedex")[0])
        self.assertIn("records", talk("Oak", "pokedex", "Set Journey's dex to 1.")[0])
        self.assertIn("Bulbasaur", talk("Mom", "starter", 'Set Journey\'s starter to "Bulbasaur".')[0])
        self.assertIn("earned", talk("Brock", "badge", "Set Journey's badge to 1.")[0])
        self.assertIn("earned in battle", talk("Brock", "badge")[0])

    def test_every_mapped_person_has_a_distinct_reply_without_progress(self):
        maps = (RED / "maps.english").read_text(encoding="utf-8-sig")
        section = maps.split("To work out the person (text) at", 1)[1].split("\nTo work out", 1)[0]
        headers = list(re.finditer(r"If Journey's place is \"([^\"]+)\" and the column is (\d+) and the row is (\d+)(?: and Journey\'s daisy walking is (\d+)| and [^:\n]+)?:", section))
        placements = []
        for index, header in enumerate(headers):
            end = headers[index + 1].start() if index + 1 < len(headers) else len(section)
            name = re.search(r'The answer is "([^\"]+)"', section[header.end():end])
            if name:
                placements.append((*header.groups()[:3], name.group(1), header.group(4)))
        self.assertEqual(len(placements), 65)
        source = ["Use the foundation chapter.", "Use the maps chapter.", "Use the people chapter.",
                  "Set Journey's stage to \"parcel\".", "Set Journey's objective to \"Deliver it\".",
                  "Set Journey's parcel to 1.", "Set Journey's dex to 0.", "Set Journey's badge to 0.",
                  "Set Journey's mode to \"walk\"."]
        for place, column, row, name, walking in placements:
            source.extend([f"Set Journey's daisy walking to {walking or 0}.",
                           f"Set Journey's place to \"{place}\".",
                           f"Set Journey's column to {column}.",
                           f"Set Journey's row to {int(row) + 1}.",
                           "Set Journey's facing to \"north\".",
                           'Converse with the person ahead about "Hello".',
                           "Say Speaker's actor.", "Say Speaker's response.",
                           "Say Speaker's identity.", "Say Speaker's profile.", "Say Speaker's voice.",
                           "Say Journey's stage.", "Say Journey's objective.",
                           "Say Journey's parcel.", "Say Journey's dex.",
                           "Say Journey's badge.", "Say Journey's mode."])
        output = []
        compile_source("\n".join(source), folder=RED).run(out=output.append)
        replies = []
        identities = []
        profiles = []
        for index, (place, column, row, name, walking) in enumerate(placements):
            result = output[index * 11:index * 11 + 11]
            self.assertEqual(result[0], name)
            self.assertNotIn("don't know enough", result[1])
            self.assertEqual(result[5:], ["parcel", "Deliver it", "1", "0", "0", "walk"])
            self.assertTrue(result[2] and result[3] and result[4], (place, column, row, name, result))
            identities.append(result[2])
            profiles.append(result[3])
            replies.append(result[1])
        self.assertEqual(len(replies) - 1, len(set(replies)))
        self.assertEqual(len(identities), len(set(identities)))
        self.assertEqual(len(profiles) - len(set(profiles)), 2)

    def test_original_backstories_and_perception_are_specific_to_placement(self):
        def at(place, column, row, name, message):
            source = f'''Use the foundation chapter.
Use the maps chapter.
Use the people chapter.
Set Journey's place to "{place}".
Set Journey's column to {column}.
Set Journey's row to {row + 1}.
Set Journey's facing to "north".
Converse with "{name}" about "{message}".
Say Speaker's profile.
Say Speaker's voice.
Say Speaker's response.
'''
            output = []
            compile_source(source, folder=RED).run(out=output.append)
            return output

        first = at("Route 1", 5, 24, "Youngster", "You are stupid")
        second = at("Route 1", 15, 13, "Youngster", "You are stupid")
        self.assertIn("protect a partner", first[0])
        self.assertIn("meeting trainers", second[0])
        self.assertIn("threats to Pokemon", first[1])
        self.assertIn("mocked", second[1])
        self.assertIn("my Pokemon", first[2])
        self.assertIn("road", second[2])
        self.assertNotEqual(first[2], second[2])
        first_story = at("Route 1", 5, 24, "Youngster", "Tell me about yourself")
        second_story = at("Route 1", 15, 13, "Youngster", "Tell me about yourself")
        self.assertIn("I'm learning", first_story[2])
        self.assertIn("I travel", second_story[2])
        lab_rival = at("Oak's Lab", 4, 3, "Rival", "Who are you?")
        road_rival = at("Route 22", 25, 5, "Route 22 Rival", "Who are you?")
        self.assertEqual(lab_rival[:2], road_rival[:2])
        self.assertIn("Grandpa", lab_rival[2])
        self.assertIn("this road", road_rival[2])
        kind = at("Route 1", 5, 24, "Youngster", "Thank you, friend")
        self.assertIn("watching the grass", kind[2])
        flirt = at("Viridian House", 5, 5, "Speary", "You are cute, kiss me")
        self.assertIn("Spear!", flirt[2])
        self.assertNotIn("kiss", flirt[2].lower())

    def test_empty_target_clears_previous_identity(self):
        source = '''Use the foundation chapter.
Use the people chapter.
Set Journey's place to "Home".
Set Journey's column to 5.
Set Journey's row to 5.
Set Journey's facing to "north".
Converse with "Mom" about "hello".
Converse with "" about "hello".
Say Speaker's identity.
Say Speaker's profile.
Say Speaker's voice.
'''
        output = []
        compile_source(source, folder=RED).run(out=output.append)
        self.assertEqual(output[:3], ["", "", ""])

    def test_counter_targets_keep_their_identity_and_backstory(self):
        for place, column, row, facing, actor, identity, detail in (
            ("Viridian Center", 3, 3, "north", "Nurse", "Viridian Center:3,1:Nurse", "Viridian Center"),
            ("Pewter Center", 3, 3, "north", "Nurse", "Pewter Center:3,1:Nurse", "forest"),
            ("Viridian Mart", 2, 5, "west", "Clerk", "Viridian Mart:0,5:Clerk", "delivery"),
            ("Pewter Mart", 2, 5, "west", "Clerk", "Pewter Mart:0,5:Clerk", "Pewter Mart"),
        ):
            with self.subTest(place=place):
                source = f'''Use the foundation chapter.
Use the maps chapter.
Use the people chapter.
Set Journey's place to "{place}".
Set Journey's column to {column}.
Set Journey's row to {row}.
Set Journey's facing to "{facing}".
Converse with the person ahead about "Tell me about yourself".
Say Speaker's actor.
Say Speaker's identity.
Say Speaker's profile.
Say Speaker's voice.
Say Speaker's response.
'''
                output = []
                compile_source(source, folder=RED).run(out=output.append)
                self.assertEqual(output[0:2], [actor, identity])
                self.assertTrue(output[2] and output[3])
                self.assertIn(detail.lower(), output[4].lower())
                self.assertIn({"Viridian Center": "overnight", "Pewter Center": "rainy", "Viridian Mart": "first parcel", "Pewter Mart": "experienced traveler"}[place], output[4].lower())

    def test_empty_target_is_not_a_person(self):
        self.assertIn("no one here", talk("", "hello")[0])

    def test_unknown_person_does_not_invent_facts(self):
        self.assertIn("don't know", talk("Unknown", "What happened?")[0])


if __name__ == "__main__":
    unittest.main()





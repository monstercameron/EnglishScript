import unittest
from pathlib import Path

from englishscript import compile_source


RED = Path(__file__).resolve().parents[1] / "docs" / "red"


PLACEMENTS = (
    ('Home', 5, 4, 'Mom', 0),
    ("Oak's Lab", 4, 3, 'Rival', 0),
    ("Oak's Lab", 5, 2, 'Oak', 0),
    ("Oak's Lab", 1, 9, 'Girl', 0),
    ("Oak's Lab", 2, 10, 'Scientist', 0),
    ("Oak's Lab", 8, 10, 'Scientist', 0),
    ("Oak's Lab", 6, 3, 'Charmander', 0),
    ("Oak's Lab", 7, 3, 'Squirtle', 0),
    ("Oak's Lab", 8, 3, 'Bulbasaur', 0),
    ('Viridian Mart', 0, 5, 'Clerk', 0),
    ('Viridian Center', 3, 1, 'Nurse', 0),
    ('Viridian Forest', 30, 33, 'Bug Catcher 1', 0),
    ('Viridian Forest', 30, 19, 'Bug Catcher 2', 0),
    ('Viridian Forest', 2, 18, 'Bug Catcher 3', 0),
    ('Pewter Gym', 4, 1, 'Brock', 0),
    ('Pewter Gym', 3, 6, 'Gym Trainer', 0),
    ('Pewter Gym', 7, 10, 'Gym Guide', 0),
    ('Pallet Town', 3, 8, 'Girl', 0),
    ('Pallet Town', 11, 14, 'Fisher', 0),
    ('Route 1', 5, 24, 'Youngster', 0),
    ('Route 1', 15, 13, 'Youngster', 0),
    ('Viridian City', 13, 20, 'Youngster', 0),
    ('Viridian City', 30, 8, 'Man', 0),
    ('Viridian City', 30, 25, 'Youngster', 0),
    ('Viridian City', 17, 9, 'Girl', 0),
    ('Viridian City', 18, 9, 'Old Man', 0),
    ('Viridian City', 6, 23, 'Fisher', 0),
    ('Viridian City', 17, 5, 'Old Man', 0),
    ('Viridian Mart', 5, 5, 'Youngster', 0),
    ('Viridian Mart', 3, 3, 'Customer', 0),
    ('Viridian Center', 10, 5, 'Gentleman', 0),
    ('Viridian Center', 4, 3, 'Visitor', 0),
    ('Viridian Center', 11, 2, 'Receptionist', 0),
    ('Forest South Gate', 8, 4, 'Girl', 0),
    ('Forest South Gate', 2, 4, 'Girl', 0),
    ('Viridian Forest', 16, 43, 'Youngster', 0),
    ('Viridian Forest', 27, 40, 'Youngster', 0),
    ('Forest North Gate', 3, 2, 'Visitor', 0),
    ('Forest North Gate', 2, 5, 'Gramps', 0),
    ('Pewter City', 8, 15, 'Visitor', 0),
    ('Pewter City', 17, 25, 'Visitor', 0),
    ('Pewter City', 27, 17, 'Visitor', 0),
    ('Pewter City', 26, 25, 'Visitor', 0),
    ('Pewter City', 35, 16, 'Youngster', 0),
    ('Route 22', 25, 5, 'Route 22 Rival', 0),
    ('Route 22 Gate', 6, 2, 'Guard', 0),
    ('Pewter Center', 3, 1, 'Nurse', 0),
    ('Pewter Center', 11, 7, 'Gentleman', 0),
    ('Pewter Center', 1, 3, 'Jigglypuff', 0),
    ('Pewter Center', 11, 2, 'Receptionist', 0),
    ('Pewter Mart', 0, 5, 'Clerk', 0),
    ('Pewter Mart', 3, 3, 'Youngster', 0),
    ('Pewter Mart', 5, 5, 'Visitor', 0),
    ("Blue's House", 2, 3, 'Daisy', 0),
    ("Blue's House", 6, 4, 'Daisy', 1),
    ('Viridian School', 3, 5, 'Girl', 0),
    ('Viridian School', 4, 1, 'Teacher', 0),
    ('Viridian House', 5, 3, 'Man', 0),
    ('Viridian House', 1, 4, 'Girl', 0),
    ('Viridian House', 5, 5, 'Speary', 0),
    ('Pewter House', 2, 3, 'Man', 0),
    ('Pewter House', 4, 5, 'Youngster', 0),
    ('Nidoran House', 4, 5, 'Nidoran', 0),
    ('Nidoran House', 3, 5, 'Boy', 0),
    ('Nidoran House', 1, 2, 'Man', 0),
)


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

    def test_topics_match_whole_words_only(self):
        brock_default = "BROCK: Training takes patience. Learn what your Pokemon can do and stand by them."
        self.assertEqual(talk("Brock", "Hi Brock, how are you today?")[0], brock_default)
        self.assertEqual(talk("Brock", "What do you do in the winter?")[0], brock_default)
        self.assertIn("badge is earned", talk("Brock", "Can I win your badges?")[0])
        self.assertEqual(talk("Mom", "What do you do all day?", 'Set Journey\'s trainer to "RED".')[0],
                         "MOM: It's good to see you, RED. Take care of yourself out there.")
        self.assertIn("Home is always here", talk("Mom", "Do you miss me?")[0])
        self.assertIn("Squirtle", talk("Mom", "How is my Pokémon?", 'Set Journey\'s starter to "Squirtle".')[0])
        self.assertIn("Rock-type", talk("Gym Guide", "What about Brock's team?")[0])
        self.assertIn("Rock-type", talk("Gym Guide", "Any tips for the rocks?")[0])

    def test_tone_allows_intensifiers_and_ignores_kind_of(self):
        def mom(question):
            source = f'''Use the foundation chapter.
Use the maps chapter.
Use the people chapter.
Set Journey's place to "Home".
Set Journey's column to 5.
Set Journey's row to 5.
Set Journey's facing to "north".
Converse with "Mom" about "{question}".
Say Speaker's response.
'''
            output = []
            compile_source(source, folder=RED).run(out=output.append)
            return output[0]

        firm = "Mom: Please speak kindly in our home. I worry enough when my child is on the road."
        warm = "Mom: A kind word means a lot when your child is away. Come in and rest."
        self.assertEqual(mom("You are so mean!"), firm)
        self.assertEqual(mom("You're really mean"), firm)
        self.assertNotIn(mom("You are not so mean"), (firm, warm))
        self.assertNotIn(mom("What kind of Pokemon should I pick?"), (firm, warm))
        self.assertNotIn(mom("I don't really love you"), (firm, warm))
        self.assertEqual(mom("You are kind"), warm)

    def test_overlapping_topics_follow_each_persons_priority(self):
        self.assertEqual(talk("Oak", "wild starter parcel pokedex")[0],
                         "OAK: I study Pokemon, but I have more work to do before I can tell you about that.")
        self.assertEqual(talk("Mom", "home oak starter")[0],
                         "MOM: I wonder what Pokemon you'll meet on your journey. Be kind to them.")
        self.assertEqual(talk("Rival", "battle grandpa starter")[0],
                         "RIVAL: I'm ready to get a Pokemon of my own. Grandpa is taking his time!")
        self.assertEqual(talk("Brock", "rock badge")[0],
                         "BROCK: A badge is earned in battle. Face me when you're ready.")

    def test_companions_only_observe_progress(self):
        setup = '''Set Journey's stage to "parcel".
Set Journey's objective to "Deliver it".
Set Journey's parcel to 1.
Set Journey's dex to 0.
Set Journey's badge to 0.
Set Journey's mode to walk.'''
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
        placements = PLACEMENTS
        self.assertEqual(len(placements), 65)
        source = ["Use the foundation chapter.", "Use the maps chapter.", "Use the people chapter.",
                  "Set Journey's stage to \"parcel\".", "Set Journey's objective to \"Deliver it\".",
                  "Set Journey's parcel to 1.", "Set Journey's dex to 0.", "Set Journey's badge to 0.",
                  "Set Journey's mode to walk."]
        for place, column, row, name, walking in placements:
            source.extend([f"Set Journey's daisy walking to {walking or 0}.",
                           f"Set Journey's place to \"{place}\".",
                           f"Set Journey's column to {column}.",
                           f"Set Journey's row to {int(row) + 1}.",
                           "Set Journey's facing to \"north\".",
                           f"Say the person at {column} by {row}.",
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
        returning_characters = {
            "Blue's House:6,4:Daisy": "Blue's House:2,3:Daisy",
            "Route 22:25,5:Route 22 Rival": "Oak's Lab:4,3:Rival",
        }
        for index, (place, column, row, name, walking) in enumerate(placements):
            result = output[index * 12:index * 12 + 12]
            self.assertEqual(result.pop(0), name, (place, column, row, walking))
            self.assertEqual(result[0], name)
            self.assertNotIn("don't know enough", result[1])
            self.assertEqual(result[5:], ["parcel", "Deliver it", "1", "0", "0", "walk"])
            self.assertTrue(result[2] and result[3] and result[4], (place, column, row, name, result))
            address = f"{place}:{column},{row}:{name}"
            self.assertEqual(result[2], returning_characters.get(address, address))
            identities.append(result[2])
            profiles.append(result[3])
            replies.append(result[1])
        self.assertEqual(len(replies) - 1, len(set(replies)))
        self.assertEqual(len(identities) - len(set(identities)), len(returning_characters))
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





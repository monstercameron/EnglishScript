import unittest
from fractions import Fraction
from pathlib import Path

from englishscript import compile_file, compile_source


RED = Path(__file__).resolve().parents[1] / "docs" / "red"

GEN_ONE = {
    "normal": {"rock": 0.5, "ghost": 0},
    "fire": {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 2, "bug": 2, "rock": 0.5, "dragon": 0.5},
    "water": {"fire": 2, "water": 0.5, "grass": 0.5, "ground": 2, "rock": 2, "dragon": 0.5},
    "electric": {"water": 2, "electric": 0.5, "grass": 0.5, "ground": 0, "flying": 2, "dragon": 0.5},
    "grass": {"fire": 0.5, "water": 2, "grass": 0.5, "poison": 0.5, "ground": 2, "flying": 0.5,
              "bug": 0.5, "rock": 2, "dragon": 0.5},
    "ice": {"water": 0.5, "grass": 2, "ice": 0.5, "ground": 2, "flying": 2, "dragon": 2},
    "fighting": {"normal": 2, "ice": 2, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5,
                 "rock": 2, "ghost": 0},
    "poison": {"grass": 2, "poison": 0.5, "ground": 0.5, "bug": 2, "rock": 0.5, "ghost": 0.5},
    "ground": {"fire": 2, "electric": 2, "grass": 0.5, "poison": 2, "flying": 0, "bug": 0.5, "rock": 2},
    "flying": {"electric": 0.5, "grass": 2, "fighting": 2, "bug": 2, "rock": 0.5},
    "psychic": {"fighting": 2, "poison": 2, "psychic": 0.5},
    "bug": {"fire": 0.5, "grass": 2, "fighting": 0.5, "poison": 2, "flying": 0.5, "psychic": 2, "ghost": 0.5},
    "rock": {"fire": 2, "ice": 2, "fighting": 0.5, "ground": 0.5, "flying": 2, "bug": 2},
    "ghost": {"normal": 0, "psychic": 0, "ghost": 2},
    "dragon": {"dragon": 2},
}

SPECIES_TYPES = {
    "Bulbasaur": ("grass", "poison"), "Ivysaur": ("grass", "poison"),
    "Charmander": ("fire",), "Charmeleon": ("fire",), "Squirtle": ("water",), "Wartortle": ("water",),
    "Caterpie": ("bug",), "Metapod": ("bug",), "Butterfree": ("bug", "flying"),
    "Weedle": ("bug", "poison"), "Kakuna": ("bug", "poison"), "Beedrill": ("bug", "poison"),
    "Pidgey": ("normal", "flying"), "Pidgeotto": ("normal", "flying"), "Pidgeot": ("normal", "flying"),
    "Spearow": ("normal", "flying"), "Fearow": ("normal", "flying"),
    "Rattata": ("normal",), "Raticate": ("normal",),
    "Nidoran F": ("poison",), "Nidorina": ("poison",), "Nidoran M": ("poison",), "Nidorino": ("poison",),
    "Pikachu": ("electric",), "Geodude": ("rock", "ground"), "Onix": ("rock", "ground"),
    "Diglett": ("ground",), "Sandshrew": ("ground",),
}


def expected(attacking, species):
    result = Fraction(1)
    for defending in SPECIES_TYPES[species]:
        result *= Fraction(GEN_ONE[attacking].get(defending, 1)).limit_denominator()
    return result


def say_all(sentences):
    output = []
    compile_source("Use the matchups chapter.\n" + "".join(sentences), folder=RED).run(out=output.append)
    return output


class MatchupParity(unittest.TestCase):
    def test_every_species_has_its_gen_one_types(self):
        compiler = compile_file(RED / "matchups.english").compiler
        species = set(compiler.fact_tables["species types"].rows)
        stats = set(compile_file(RED / "battle.english").compiler.fact_tables["base stats"].rows)
        self.assertEqual(species, set(SPECIES_TYPES))
        self.assertEqual(stats, set(SPECIES_TYPES))
        output = say_all(f'Say the types of "{name}" joined with "/".\n' for name in SPECIES_TYPES)
        self.assertEqual(output, ["/".join(types) for types in SPECIES_TYPES.values()])

    def test_every_attacking_type_against_every_species(self):
        pairs = [(attacking, species) for attacking in GEN_ONE for species in SPECIES_TYPES]
        output = say_all(f'Say the effectiveness of "{attacking}" against "{species}".\n'
                         for attacking, species in pairs)
        for (attacking, species), value in zip(pairs, output):
            with self.subTest(attacking=attacking, species=species):
                self.assertEqual(Fraction(value), expected(attacking, species))

    def test_reported_gaps_are_closed(self):
        cases = {("electric", "Squirtle"): 2, ("poison", "Caterpie"): 2, ("poison", "Diglett"): 0.5,
                 ("electric", "Bulbasaur"): 0.5, ("grass", "Nidoran F"): 0.5, ("electric", "Geodude"): 0,
                 ("flying", "Metapod"): 2, ("water", "Onix"): 4}
        output = say_all(f'Say the effectiveness of "{a}" against "{s}".\n' for a, s in cases)
        self.assertEqual([Fraction(value) for value in output],
                         [Fraction(value).limit_denominator() for value in cases.values()])

    def test_every_move_has_a_known_type(self):
        moves = compile_file(RED / "battle.english").compiler.fact_tables["battle moves"].rows
        for move, row in moves.items():
            with self.subTest(move=move):
                self.assertIn(row.values[2], GEN_ONE)

    def test_thundershock_against_squirtle_is_doubled_in_battle(self):
        output = []
        compile_source('''Use the foundation chapter.
Use the battle chapter.
Enlist "Pikachu".
Confront "Squirtle" at 5.
Set Combat's foe's speed to 0.
Set Combat's seed to 0.
Fight.
Say Combat's later lines joined with "|".
''', folder=RED).run(out=output.append)
        self.assertIn("It's super effective!", output[0])

    def test_immunity_deals_no_damage(self):
        output = []
        compile_source('''Use the foundation chapter.
Use the battle chapter.
Enlist "Pikachu".
Confront "Geodude" at 5.
Set Combat's foe's speed to 0.
Set Combat's seed to 0.
Fight.
Say Combat's later lines joined with "|".
Say whether (Combat's foe's health is Combat's foe's maximum health).
''', folder=RED).run(out=output.append)
        self.assertTrue(output[0].startswith("It doesn't affect Geodude!"))
        self.assertEqual(output[1], "yes")


if __name__ == "__main__":
    unittest.main()

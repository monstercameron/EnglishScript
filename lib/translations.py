def convert_pairs_to_tuple_string(pairs):
    result = ""
    for pair in pairs:
        javascript_code = pair["javascript"]
        english_description = pair["english"]
        tuple_representation = "({}, {}), ".format(
            javascript_code, english_description)
        result += tuple_representation
    result = result.rstrip(", ")  # Remove the trailing comma and space
    return result


def convert_alias_to_tuple_string(alias):
    tuple_string = "("
    for sublist in alias:
        tuple_string += "(" + ", ".join(sublist) + "), "
    tuple_string = tuple_string.rstrip(", ") + ")"
    return tuple_string


def get_rules():
    pairs = [
        {"javascript": "const value = 1;",
            "english": "I have a fixed number that is 1"},
        {"javascript": "let value = 1;", "english": "I have a number that is 1"},
        {"javascript": "const value = 'string';",
            "english": "I have a fixed word that is 'string',"},
        {"javascript": "let value = 'string';",
            "english": "I have a word that is 'string'"},
        {"javascript": "const value='string'; let carDoor=5;",
            "english": "I have a fixed word that is 'string' and a number carDoor of 5)"},
        {"javascript": "let a = 1 + 2;",
            "english": "I have a number a that I add 1 and 2,"},
        {"javascript": "let a = a + 2;",
            "english": "I have a number a that I add a and 2,"},
        {"javascript": "let a = a + b;",
            "english": "I have a number a that I add a and b,"},
        {"javascript": "let a = (a + b) / a;",
         "english": "I have a number a that I add a and b then divide by a,"},
        {"javascript": "let a = (a + b) / a * b;",
         "english": "I have a number a that I add a and b then divide by a then multiply by b,"},
        {"javascript": "const a = 1; const result = (a + b) * 2;",
         "english": "I have a number a that is 1 then I add a and b then multiply by 2"},
        {"javascript": "console.log(a);",
         "english": "show my number a"},
        {"javascript": "console.log(a);",
         "english": "log my number a"},
    ]
    return {"role": "user", "content": convert_pairs_to_tuple_string(pairs)}


def get_aliases():
    alias = [
        ["const", "constant", "fixed"],
        ["number", "digit", "count"],
        ["word", "string", "character"],
        ["multiply", "times", "mul", "mult"],
        ["divide", "div"],
        ["log", "console", "display", "show"]
    ]
    return {"role": "user", "content": convert_alias_to_tuple_string(alias)}

"""EnglishScript: a strict, compilable subset of English."""
from .compiler import KEYWORDS, Program, compile_file, compile_source
from .lexer import CATEGORIES, RULES, EnglishError
from .linter import Problem, lint, names

__version__ = "0.9.0"

# The heading word of each category of mistake, as a mark shows it: {"spelling": "Spelling", ...}
CATEGORY_HEADINGS = {category: heading for category, (heading, _) in CATEGORIES.items()}

__all__ = ["compile_source", "compile_file", "Program", "EnglishError", "run_source", "explain", "lint", "Problem",
           "names", "KEYWORDS", "CATEGORIES", "CATEGORY_HEADINGS", "RULES", "__version__"]


def run_source(source, out=print, ask=None, folder=None, name=None, model=None, judge=None):
    """Compile and run a program. Returns the finished World.

    `ask` answers the program's questions (see Program.run); by default the
    replies are read from standard input. `model` and `judge` answer "Ask the
    model" and "Judge" (Program.run); by default nothing is listening.
    `folder` and `name` are as for compile_source.
    """
    return compile_source(source, folder, name).run(out, ask, model=model, judge=judge)


def explain(source, folder=None, name=None):
    """The source, with a note under each sentence on how it was read."""
    program = compile_source(source, folder, name)
    notes = {}
    for number, text in program.notes:
        notes.setdefault(number, []).append(text)
    out = []
    for number, raw in enumerate(source.splitlines(), 1):
        out.append(f"{number:>3}  {raw}".rstrip())
        indent = len(raw) - len(raw.lstrip())
        for text in notes.get(number, []):
            out.append(" " * (5 + indent) + "  ↳ " + text)
    return "\n".join(out)

"""EnglishScript: a strict, compilable subset of English."""
from .compiler import Program, compile_file, compile_source
from .lexer import EnglishError
from .linter import Problem, lint

__all__ = ["compile_source", "compile_file", "Program", "EnglishError", "run_source", "explain", "lint", "Problem"]


def run_source(source, out=print, ask=None, folder=None, name=None):
    """Compile and run a program. Returns the finished World.

    `ask` answers the program's questions (see Program.run); by default the
    replies are read from standard input. `folder` and `name` are as for compile_source.
    """
    return compile_source(source, folder, name).run(out, ask)


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

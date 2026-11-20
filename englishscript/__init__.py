"""EnglishScript: a strict, compilable subset of English."""
from .compiler import Program, compile_source
from .lexer import EnglishError

__all__ = ["compile_source", "Program", "EnglishError", "run_source", "explain"]


def run_source(source, out=print, ask=None):
    """Compile and run a program. Returns the finished World.

    `ask` answers the program's questions (see Program.run); by default the
    replies are read from standard input.
    """
    return compile_source(source).run(out, ask)


def explain(source):
    """The source, with a note under each sentence on how it was read."""
    program = compile_source(source)
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

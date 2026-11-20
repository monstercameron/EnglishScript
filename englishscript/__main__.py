"""Command line:  python -m englishscript [FILE] [--explain | --check]"""
import argparse
import sys

from . import EnglishError, compile_source, explain
from .tour import tour


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(
        prog="python -m englishscript",
        description="Run a program written in EnglishScript. With no file, takes you on a tour.",
    )
    parser.add_argument("file", nargs="?", help="a .english file")
    parser.add_argument("--explain", action="store_true", help="show how each sentence was read; don't run it")
    parser.add_argument("--check", action="store_true", help="compile only; don't run it")
    args = parser.parse_args(argv)

    if not args.file:
        tour()
        return 0
    try:
        with open(args.file, encoding="utf-8") as handle:
            source = handle.read()
    except OSError as error:
        print(f"I couldn't open {args.file}: {error.strerror}.", file=sys.stderr)
        return 1
    try:
        if args.explain:
            print(explain(source))
            return 0
        program = compile_source(source)
        if args.check:
            print("Every sentence reads one way. Nothing was run.")
            return 0
        world = program.run()
        sys.stdout.flush()
        if world.examples:
            noun = "example" if world.examples == 1 else "examples"
            print(f"\n({world.examples} {noun} checked.)", file=sys.stderr)
        return 0
    except EnglishError as error:
        sys.stdout.flush()
        print("\n" + error.render(args.file), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Command line:  python -m englishscript [FILE] [--explain | --check | --lint [--json] | --test | --trace]
[--model SPEC]"""
import argparse
import json
import os
import sys

from . import EnglishError, compile_source, explain, lint
from .linter import tally
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
    parser.add_argument("--lint", action="store_true",
                        help="list every problem, with advice and warnings; don't run it")
    parser.add_argument("--json", action="store_true", help="with --lint: the problems as JSON")
    parser.add_argument("--test", action="store_true",
                        help="check every 'For example', saying nothing else, asking nothing and writing no file")
    parser.add_argument("--trace", action="store_true", help="say each sentence as it is carried out")
    parser.add_argument("--model", metavar="SPEC",
                        help="who answers 'Ask the model' and 'Judge' (see englishscript/models.py); "
                             "without it, nothing is listening. --test never connects one")
    args = parser.parse_args(argv)
    if args.json and not args.lint:
        parser.error("--json goes with --lint")

    if not args.file:
        tour()
        return 0
    try:
        with open(args.file, encoding="utf-8") as handle:
            source = handle.read()
    except OSError as error:
        print(f"I couldn't open {args.file}: {error.strerror}.", file=sys.stderr)
        return 1
    folder = os.path.dirname(args.file) or "."  # its chapters are beside it
    if args.lint:
        return lint_file(args.file, source, args.json, folder)
    try:
        if args.explain:
            print(explain(source, folder, args.file))
            return 0
        program = compile_source(source, folder, args.file)
        if args.check:
            print("Every sentence reads one way. Nothing was run.")
            return 0
        if args.test:
            return test_program(program, args.file)
        model = judge = None
        if args.model:
            # Only now: the compiler itself depends on no model, nor on this module.
            from . import models
            try:
                model, judge = models.connect(args.model)
            except EnglishError:
                raise
            except Exception as error:  # noqa: BLE001 - reported in English
                print(f"I couldn't connect the model {args.model}: {error}", file=sys.stderr)
                return 1
        trace = None
        if args.trace:
            def trace(depth, file, line, sentence, cause):
                where = f"{file}, line {line}" if file else f"line {line}"
                because = f"   (because {cause})" if cause else ""
                print(f"{'  ' * depth}[{where}] {sentence}{because}", file=sys.stderr, flush=True)
        world = program.run(trace=trace, model=model, judge=judge)
        sys.stdout.flush()
        if world.examples:
            noun = "example" if world.examples == 1 else "examples"
            print(f"\n({world.examples} {noun} checked.)", file=sys.stderr)
        return 0
    except EnglishError as error:
        sys.stdout.flush()
        print("\n" + error.render(args.file), file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # Ctrl+C while the program waits for a reply
        print()
        return 130


def test_program(program, filename):
    """--test: report every example; 1 if one did not hold or the program stopped."""
    try:
        results = program.test()
    except EnglishError as error:
        print(error.render(filename), file=sys.stderr)
        return 1
    failed = 0
    for example in results:
        where = f"{example.file}, line {example.line}" if example.file else f"line {example.line}"
        if example.held:
            print(f"{where}: holds: {example.sentence}")
        else:
            failed += 1
            print(f"{where}: DOES NOT HOLD: {example.sentence}")
            if example.fact:
                print(f"    {example.fact}")
    count = len(results)
    noun = "example" if count == 1 else "examples"
    print(f"\n{count} {noun}: {count - failed} held, {failed} did not.")
    return 1 if failed else 0


def lint_file(filename, source, as_json, folder=None):
    """Print every problem in the program. 1 if there is an error, otherwise 0."""
    problems = lint(source, folder, filename)
    errors = sum(1 for p in problems if p.kind == "error")
    if as_json:
        print(json.dumps([p.as_dict() for p in problems], ensure_ascii=False, indent=2))
        return 1 if errors else 0
    for problem in problems:
        print(problem.render(filename))
        print()
    print(tally(problems))  # at the foot, as a teacher writes it
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

"""Libraries: verbs and worked-out values carried out by Python code.

A program writes, at the top level:

    Use the paint library.

and the compiler loads the module ``englishscript.libraries.paint``. It never
imports anything else on a program's say-so. Every module in this package whose
name does not start with an underscore is a library a program may use.

Writing a library
=================

A library module provides:

``SOURCE`` (required)
    A string of ordinary EnglishScript. It is compiled where the program says
    "Use the ... library.", as if its sentences were written there, so the
    kinds, things, adjectives, rules, verbs and worked-out values it defines
    join the program's vocabulary. SOURCE may not say "Use" itself.

    Inside SOURCE only, two more sentence forms declare something whose block
    is a Python function of this module. The part before "is done by the
    library" is exactly the header of a verb or of a worked-out value, without
    its colon::

        To fill a canvas with a colour (text) is done by the library.
        To work out the pixel count (number) of a canvas is done by the library.

``verb_<verb>(world, **roles)``
    One for each verb declared that way, such as ``verb_fill``. What it returns
    is ignored.

``value_<name>(world, **roles)``
    One for each worked-out value declared that way, with the spaces in its
    name turned into underscores, such as ``value_pixel_count``. What it
    returns is checked against the declared type (see below).

``finish(world)`` (optional)
    Called exactly once when a run ends for any reason: the end of the
    program, "End the program.", input running out, or a problem. Release
    what the library holds here. A failure in ``finish`` is reported only if
    the run itself went well, so it never hides what really happened.

A function the SOURCE asks for that the module does not have is refused when
the program is compiled.

Calling convention
------------------

``world`` is the running ``englishscript.runtime.World``. Keep the library's
own state in ``world.libraries[<library name>]``, a dict that starts empty at
the start of every run.

Each role is passed by keyword under its role name, with spaces turned into
underscores (the role "an across (number)" arrives as ``across=...``). Values
arrive as the program holds them:

    number, money, percent   fractions.Fraction
    text                     str
    yes or no                bool
    a thing                  englishscript.runtime.Thing (.kind, .name, .fields)
    a list                   tuple
    nothing                  None

A worked-out value must give back:

    text                     a str
    number, money, percent   an int, float or Fraction (a float is converted
                             through its shortest repr, so 0.1 is exactly 1/10)
    yes or no                a bool
    a kind                   a Thing of that kind that has not been removed
    a list                   a tuple or list of such items (it becomes a tuple)
    anything "if any"        also None

Anything else is a fault in the library, and ends the program.

Problems
--------

For a problem in the world, such as a file or a device that is not there,
raise ``englishscript.EnglishError(message, stage="run", recoverable=True)``.
A program can recover from it with "Try:" / "If that fails:", and the message
becomes "the problem". A failed Try undoes the changes made to things in the
world, but not what the library did outside it (including what it keeps in
``world.libraries``), so undo or tolerate that yourself.

Any other exception raised by a library function is reported to the person
running the program as a fault in the library, and ends the program.
KeyboardInterrupt passes through untouched.
"""

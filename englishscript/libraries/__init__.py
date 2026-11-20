"""Libraries: verbs and worked-out values carried out by Python code.

A program writes, at the top level:

    Use the paint library.

and the compiler loads the module ``englishscript.libraries.paint``. It never
imports anything else on a program's say-so. In a program of several files
(chapters, docs/SYNTAX.md section 9.6), each file that wants the library's
words says so; the library is loaded, its SOURCE compiled and its hooks
called once for the whole program, and ``world.libraries`` has one entry for it. Every module in this package whose
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

``live(world)`` (optional)
    Called once, after the program's last sentence, only when the sentences
    ran to their end: not after "End the program.", input running out, or a
    problem. A library that goes on working after the program's sentences
    (a page that waits for clicks) starts doing so here, and from then on
    brings in what happens with ``world.event`` (below). It is called before
    any library's ``finish``, for each library in the order the program used
    them. A failure in ``live`` is reported like a failure in ``finish``, and
    sets ``world.ended``.

``finish(world)`` (optional)
    Called exactly once when a run ends for any reason: the end of the
    program, "End the program.", input running out, or a problem. Release
    what the library holds here. A failure in ``finish`` is reported only if
    the run itself went well, so it never hides what really happened.
    ``finish`` is called before ``Program.run`` returns, so a library that
    is live must keep what ``world.event`` needs.

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
    a thing                  englishscript.runtime.Thing (see "Reading the world")
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

Reading the world
-----------------

A library may read, but should change only through ``world.event`` or its
own verbs:

    world.things[kind]   the things of a kind that are in the world, in the
                         order they were made (a removed thing leaves it)
    world.named[name]    a thing made with "There is ... called", by its name
                         in lower case
    thing.kind, .name    the kind's name, and the thing's name
    thing.fields         property name -> value, as in the table above
    thing.marks          the set of stored adjectives that are "yes"
    thing.removed        True once "Remove" has taken it out of the world
    thing.serial         an int: things are numbered from 1 in the order
                         they were made in this run, across all kinds. A
                         failed Try does not put the count back, so a serial
                         is never given to two things in one run, and the
                         things that remain keep their order.
    world.ended          True once the program has ended: "End the program."
                         (in its own sentences or in a reaction to an event),
                         input running out, a problem, or a failed ``live``

Events from outside
-------------------

``world.event(change)``
    Brings in something that happened outside the program, such as a click,
    at any time after ``live`` has been called, including long after
    ``Program.run()`` has returned and ``finish`` has been called.

    ``change`` is a function of no arguments that changes things directly:
    ``thing.fields[name] = value`` for a property, and
    ``thing.marks.add(adjective)`` or ``thing.marks.discard(adjective)`` for a
    stored adjective. Values must already be of the property's type, as in
    the table above: that is the library's responsibility, and nothing
    checks it. ``change`` must not make, remove or rename things.

    ``world.event`` treats ``change`` as one sentence of the program:

    * it notes what fits each adjective a "Whenever" watches, calls
      ``change()``, checks the never/always rules of every thing whose
      properties changed, and then carries out the reactions, exactly as
      after a sentence (see "Reactions" in docs/SYNTAX.md);
    * it lifts the limits a run lifts (on the length of numbers and the
      depth of Python's recursion) while it works, and puts them back;
    * on a problem (a rule broken, "Fail because", or any EnglishError in a
      reaction, recoverable or not) it puts the world back as a failed
      "Try" does, including what the reactions changed, and raises the
      EnglishError. What was said stays said. Any other exception raised by
      ``change`` also puts the world back, and passes through;
    * if a reaction says "End the program.", the event ends quietly, its
      changes stay, and ``world.ended`` becomes True.

    It returns True when ``change`` was carried out (also when a reaction
    ended the program), and False, without calling ``change``, once
    ``world.ended`` is True.

    It raises RuntimeError (not an EnglishError) if called while one of the
    program's sentences, or another event, is being carried out: for
    instance from a library's verb, from ``change`` itself, or from
    ``world.out`` during a reaction. ``world.out`` and ``world.ask`` work
    as usual during an event.
"""

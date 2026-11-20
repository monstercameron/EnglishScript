"""The page library: things that are elements of a web page.

A program that says "Use the page library." gets fifteen kinds of thing. Each
thing of one of those kinds *is* an element of the page:

    panel     a box that holds other elements, side by side where they fit
    heading   a title
    note      a line of text
    field     a box to type in
    button    something to press
    card      a line with a tick box, words that can be edited where they
              stand, a tag, a star and a cross to dismiss it
    gauge     a bar that shows how far along something is
    picture   an image, with words for a reader who cannot see it
    link      words that lead somewhere else
    table     rows of cells: a "row" belongs to a table, a "cell" to a row
    menu      a list to choose one of: an "option" belongs to a menu

The binding goes both ways and there is nothing else to call.

  * What the program changes, the page shows. Setting a note's wording changes
    the words on the page; "Now the card is hidden." takes it off the page;
    removing a thing removes its element; making a thing makes one.
  * What a person does, the program sees. Typing changes the field's wording,
    a tick box changes whether its card is ticked, and a press makes a button
    "pressed". The program answers with "Whenever":

        Whenever Adder becomes pressed:
          There is a new card whose wording is Entry's wording.

Five adjectives are momentary: a button is "pressed", a field is "changed"
(something was typed in it) or "entered" (Enter was pressed in it), and a card
is "reworded" (its words were edited) or "dismissed" (its cross was pressed)
only while the program's answer to that is being carried out.

Elements are laid out in the order their things were made. An element whose
panel is given sits inside that panel, again in the order made. A card may be
given an order, a number: cards with a lower order come first, and cards with
the same order (or none, which counts as 0) stay in the order made.

Outside a browser there is no page, so the library keeps a stand-in for one in
memory, and sketches it in text when the program ends. The functions at the
end of this module press, type and tick on that stand-in, which is how the
tests use a page without a browser.

In a browser (Pyodide), the page is built inside the element whose id is
"englishscript-page", or at the end of the document if there is none. What is
"remembered" is kept in the browser's local storage, so it is still there the
next time the page is opened.
"""
from __future__ import annotations

from fractions import Fraction

from ..lexer import EnglishError

SOURCE = '''
A panel has a title (text, if any) and a panel (panel, if any).
A panel can be hidden.

A heading has a wording (text) and a panel (panel, if any).
A heading can be hidden.

A note has a wording (text) and a panel (panel, if any).
A note can be hidden.

A field has a wording (text), a hint (text, if any), and a panel (panel, if any).
A field can be entered.
A field can be changed.
A field can be hidden.

A button has a label (text) and a panel (panel, if any).
A button can be pressed.
A button can be chosen.
A button can be hidden.

A card has a wording (text), a tag (text, if any), an order (number, if any), and a panel (panel, if any).
A card can be ticked.
A card can be starred.
A card can be reworded.
A card can be dismissed.
A card can be hidden.

A gauge has a level (number), a limit (number), and a panel (panel, if any).
A gauge can be hidden.

A canvas has a width (number), a height (number), and a panel (panel, if any).
A canvas can be hidden.
A canvas's width is always divisible by 1.
A canvas's height is always divisible by 1.
A canvas's width is never less than 1.
A canvas's width is never more than 1024.
A canvas's height is never less than 1.
A canvas's height is never more than 1024.

A picture has a source (text), a caption (text, if any), and a panel (panel, if any).
A picture can be hidden.

A link has a wording (text), a target (text), and a panel (panel, if any).
A link can be hidden.

A table has a title (text, if any) and a panel (panel, if any).
A table can be hidden.
A row has a table (table).
A row can be leading.
A row can be hidden.
A cell has a wording (text) and a row (row).

A menu has a hint (text, if any) and a panel (panel, if any).
A menu can be hidden.
An option has a wording (text) and a menu (menu).
An option can be picked.

To fill a canvas (canvas) from a left (number) by a top (number) with a width (number) over a height (number) as a shade (number) is done by the library.
To paint a canvas (canvas) at a column (number) by a down (number) with a shade (number) is done by the library.
To trace a canvas (canvas) from a start column (number) by a start row (number) to a finish column (number) at a finish row (number) with a shade (number) is done by the library.
To shade a canvas (canvas) at a column (number) by a down (number) with a vertices (list of numbers) as a shade (number) is done by the library.
To work out the pixel (number) of a canvas (canvas) at a column (number) by a down (number) is done by the library.

To remember a line (text) under a key (text) is done by the library.
To work out the memory (text, if any) of a key (text) is done by the library.
'''

NAME = "page"
KINDS = ("panel", "heading", "note", "field", "button", "card", "gauge",
         "picture", "link", "table", "row", "cell", "menu", "option", "canvas")
#: What each kind of element sits inside, by the property that says so. A kind
#: not listed here sits in its panel, if it has one, and otherwise on the page.
INSIDE = {"row": "table", "cell": "row", "option": "menu"}
#: The kinds that hold other elements, and the part of their element that holds them.
HOLDERS = {"panel": "body", "table": "body", "row": None, "menu": None}
MOMENTARY = {"button": ("pressed",), "field": ("entered", "changed"), "card": ("dismissed", "reworded")}
MOUNT = "englishscript-page"
PREFIX = "englishscript:"
LEAVING = 260  # milliseconds an element is given to leave the page, in a browser
ROOT = 0  # things are numbered from 1, so 0 can stand for the page itself


# --------------------------------------------------------------- a stand-in page


class Node:
    """An element of the stand-in page. It has the few members of a browser's
    element that this library uses, under the same names, so that one piece of
    code drives both."""

    #: Put a list here to have every write to an element noted in it, as
    #: (element, member, value). The tests use it to see what was written.
    LOG = None

    def __init__(self, tag):
        self.tag = tag
        self.attributes = {}
        self.children = []
        self.parent = None
        self.listeners = {}
        self.textContent = ""
        self.value = ""
        self.checked = False
        self.selected = False
        self.hidden = False
        self.className = ""

    def __setattr__(self, name, value):
        if Node.LOG is not None and name in ("textContent", "value", "checked", "selected", "hidden"):
            Node.LOG.append((self, name, value))
        object.__setattr__(self, name, value)

    def setAttribute(self, name, value):
        if Node.LOG is not None:
            Node.LOG.append((self, name, str(value)))
        self.attributes[name] = str(value)

    def removeAttribute(self, name):
        self.attributes.pop(name, None)

    def appendChild(self, child):
        if child.parent is not None:
            child.parent.children.remove(child)
        child.parent = self
        self.children.append(child)
        return child

    def insertBefore(self, child, before):
        if child.parent is not None:
            child.parent.children.remove(child)
        child.parent = self
        self.children.insert(self.children.index(before), child)
        return child

    def removeChild(self, child):
        self.children.remove(child)
        child.parent = None
        return child

    def blur(self):
        self.fire("blur")

    def addEventListener(self, name, handler):
        self.listeners.setdefault(name, []).append(handler)

    def fire(self, name, **details):
        """What a person does to this element: every listener hears of it."""
        event = Happening(self, **details)
        for handler in list(self.listeners.get(name, ())):
            handler(event)

    def __repr__(self):
        return f"<{self.tag} {self.className}>"


class Happening:
    def __init__(self, target, **details):
        self.target = target
        self.key = details.get("key", "")

    def preventDefault(self):
        pass


class Paper:
    """The stand-in for a browser's document, with a dict for its storage."""

    def __init__(self):
        self.root = Node("main")
        self.kept = {}

    def createElement(self, tag):
        return Node(tag)


#: What the stand-in pages remember, by key, for as long as Python runs. A
#: test (or a host) may put a dict of its own in ``STORE`` to see or seed it.
STORE = {}
def use_remote_canvas(world, callback):
    if not callable(callback):
        raise TypeError("The canvas callback must be callable.")
    state = world.libraries[NAME]
    if "backend" in state:
        raise RuntimeError("The page backend has already been selected for this world.")
    state["remote_canvas"] = callback


# -------------------------------------------------------------- the two backends


class Backend:
    """Where the page is: a browser's document, or the stand-in."""

    def __init__(self, remote_canvas=None):
        self.browser = False
        self.remote_canvas = remote_canvas
        self.proxies = []
        if self.remote_canvas is not None:
            self.document = Paper()
            self.root = self.document.root
            return
        try:
            import js  # noqa: PLC0415 - only there under Pyodide
            from pyodide.ffi import create_proxy  # noqa: PLC0415
            document = js.document
            document.createElement  # a worker has "js" but no document
        except Exception:  # noqa: BLE001 - no browser: use the stand-in
            self.document = Paper()
            self.root = self.document.root
            return
        self.browser = True
        self.js = js
        self.create_proxy = create_proxy
        self.document = document
        root = document.getElementById(MOUNT)
        if root is None:
            root = document.createElement("main")
            root.setAttribute("id", MOUNT)
            document.body.appendChild(root)
        root.textContent = ""  # a page run again starts from nothing
        self.root = root

    def discard(self, parent, node):
        """Take an element off the page. In a browser it is marked as leaving
        first, so that the page's style sheet can show it go."""
        if not self.browser:
            parent.removeChild(node)
            return
        js = self.js
        self.hand_on(node)
        try:
            still = bool(js.matchMedia("(prefers-reduced-motion: reduce)").matches)
        except Exception:  # noqa: BLE001 - an old browser: just remove it
            still = True
        if still:
            parent.removeChild(node)
            return

        def gone(*_):
            if node.parentNode is not None:  # the page may have been run again meanwhile
                node.parentNode.removeChild(node)

        from pyodide.ffi import create_once_callable  # noqa: PLC0415
        node.setAttribute("data-leaving", "true")
        js.setTimeout(create_once_callable(gone), LEAVING)

    def active(self):
        """Whatever on the page has the reader's attention, if this is a browser."""
        if not self.browser:
            return None
        try:
            return self.document.activeElement
        except Exception:  # noqa: BLE001
            return None

    def attend(self, element):
        """Give the reader's attention back to an element that was moved."""
        if element is None:
            return
        try:
            if bool(element.isConnected) and self.document.activeElement != element:
                element.focus()
        except Exception:  # noqa: BLE001 - not worth stopping for
            pass

    def hand_on(self, node):
        """If the reader's attention is inside an element that is going, give it
        to the element after it, or the one before, so that it is not lost."""
        try:
            active = self.document.activeElement
            if active is None or not bool(node.contains(active)):
                return
            for neighbour in (node.nextElementSibling, node.previousElementSibling):
                while neighbour is not None and neighbour.hasAttribute("data-leaving"):
                    neighbour = neighbour.nextElementSibling
                if neighbour is None:
                    continue
                target = neighbour.querySelector("input, button, [contenteditable]") or neighbour
                target.focus()
                return
        except Exception:  # noqa: BLE001 - not worth stopping for
            pass

    def listen(self, node, name, handler):
        if self.browser:
            proxy = self.create_proxy(handler)
            self.proxies.append(proxy)
            node.addEventListener(name, proxy)
        else:
            node.addEventListener(name, handler)

    def keep(self, key, line):
        if not self.browser:
            STORE[key] = line
            return
        try:
            self.js.localStorage.setItem(PREFIX + key, line)
        except Exception:  # noqa: BLE001 - storage can be switched off or full
            raise EnglishError(f'The browser would not remember "{key}".',
                               stage="run", recoverable=True) from None

    def kept(self, key):
        if not self.browser:
            return STORE.get(key)
        try:
            line = self.js.localStorage.getItem(PREFIX + key)
        except Exception:  # noqa: BLE001 - storage switched off: nothing is remembered
            return None
        return None if line is None else str(line)


def _safe(address, pictures=False):
    """An address a page may use, or "" for one it may not. A page written by a
    program must not be able to run a script because a text said so: only the
    web, the post, and places on this site are allowed (and, for a picture,
    an image carried in the address itself)."""
    address = str(address).strip()
    head = address.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if ":" not in head:
        return address  # no scheme: somewhere on this site, or on this page
    scheme = head.split(":", 1)[0].lower()
    if scheme in ("http", "https") or (scheme == "mailto" and not pictures):
        return address
    if pictures and address.lower().startswith("data:image/") and not address.lower().startswith("data:image/svg"):
        return address
    return ""


def _state(world):
    state = world.libraries[NAME]
    if "backend" not in state:
        state["backend"] = Backend(state.get("remote_canvas"))
        state["bound"] = {}  # a thing's serial -> its Binding
        state["order"] = {}  # ROOT or a panel's serial -> the bindings inside it, in order
        state["choices"] = set()  # ROOT or a panel's serial: where some button has been chosen
        state["lists"] = {}  # ROOT or a panel's serial -> is it marked as a list?
        state["live"] = False
        state["problems"] = []
        state["canvases"] = {}
    return state


# ---------------------------------------------------------------------- bindings


class Binding:
    """One thing and the element that shows it."""

    def __init__(self, thing, node, parts):
        self.thing = thing
        self.node = node  # the outermost element
        self.parts = parts  # named inner elements
        self.inside = None  # the node this binding's element is in
        self.home = None  # which panel that is (its thing's serial), or ROOT
        self.choice = False  # a button: is it one of a set of choices?
        self.shown = {}  # what the element was last told, so only changes are written

    def tell(self, key, value, write):
        """Write a value to the page only if it differs from what is there."""
        if self.shown.get(key, _UNSET) != value:
            self.shown[key] = value
            write(value)


_UNSET = object()


def _text(node):
    return lambda value: setattr(node, "textContent", value)


def _flag(node, name):
    def write(value):
        if value:
            node.setAttribute(name, "true")
        else:
            node.setAttribute(name, "false")
    return write


def _make(world, state, thing):
    """The element for a thing, with its listeners."""
    backend = state["backend"]
    new = backend.document.createElement
    kind = thing.kind
    if backend.remote_canvas is not None and kind != "canvas":
        raise EnglishError("The remote canvas backend only supports canvases.", stage="run", recoverable=True)

    def element(tag, css, parent=None):
        node = new(tag)
        node.className = css
        if parent is not None:
            parent.appendChild(node)
        return node

    if kind == "panel":
        node = element("section", "es-panel")
        binding = Binding(thing, node, {
            "title": element("h2", "es-panel-title", node),
            "body": element("div", "es-panel-body", node),
        })
    elif kind == "heading":
        binding = Binding(thing, element("h1", "es-heading"), {})
    elif kind == "note":
        node = element("p", "es-note")
        node.setAttribute("role", "status")  # so that a change is spoken to a reader who cannot see it
        binding = Binding(thing, node, {})
    elif kind == "field":
        node = element("input", "es-field")
        node.setAttribute("type", "text")
        node.setAttribute("autocomplete", "off")
        binding = Binding(thing, node, {})

        def typed(event):
            words = str(node.value)

            def change():
                thing.fields["wording"] = words
                thing.marks.add("changed")
            _act(world, change)

        def keyed(event):
            if str(event.key) == "Enter":
                words = str(node.value)

                def change():
                    thing.fields["wording"] = words
                    thing.marks.add("entered")
                _act(world, change)

        backend.listen(node, "input", typed)
        backend.listen(node, "keydown", keyed)
    elif kind == "button":
        node = element("button", "es-button")
        node.setAttribute("type", "button")
        binding = Binding(thing, node, {})
        backend.listen(node, "click", lambda event: _act(world, lambda: thing.marks.add("pressed")))
    elif kind == "card":
        node = element("div", "es-card")
        node.setAttribute("role", "listitem")
        box = element("input", "es-card-box", node)
        box.setAttribute("type", "checkbox")
        words = element("span", "es-card-words", node)
        words.setAttribute("contenteditable", "plaintext-only")
        words.setAttribute("role", "textbox")
        words.setAttribute("spellcheck", "false")
        tag = element("span", "es-card-tag", node)
        star = element("button", "es-card-star", node)
        star.setAttribute("type", "button")
        cross = element("button", "es-card-cross", node)
        cross.setAttribute("type", "button")
        cross.setAttribute("title", "Remove")
        cross.textContent = "\u00d7"
        binding = Binding(thing, node, {"box": box, "words": words, "tag": tag, "star": star, "cross": cross})

        def ticked(event):
            if bool(box.checked):
                _act(world, lambda: thing.marks.add("ticked"))
            else:
                _act(world, lambda: thing.marks.discard("ticked"))

        def starred(event):
            if "starred" in thing.marks:
                _act(world, lambda: thing.marks.discard("starred"))
            else:
                _act(world, lambda: thing.marks.add("starred"))

        def edited(event):
            text = " ".join(str(words.textContent).split())  # one line, with no loose spaces
            if text == thing.fields["wording"]:
                if str(words.textContent) != text:
                    words.textContent = text
                return

            def change():
                thing.fields["wording"] = text
                thing.marks.add("reworded")
            _act(world, change)

        def keyed(event):
            key = str(event.key)
            if key == "Enter":  # the words are one line: Enter finishes the edit
                event.preventDefault()
                words.blur()
            elif key == "Escape":  # and Escape gives it up
                words.textContent = thing.fields["wording"]
                words.blur()

        backend.listen(box, "change", ticked)
        backend.listen(star, "click", starred)
        backend.listen(words, "blur", edited)
        backend.listen(words, "keydown", keyed)
        backend.listen(cross, "click", lambda event: _act(world, lambda: thing.marks.add("dismissed")))
    elif kind == "gauge":
        node = element("div", "es-gauge")
        node.setAttribute("role", "progressbar")
        node.setAttribute("aria-valuemin", "0")
        node.setAttribute("aria-valuemax", "100")
        binding = Binding(thing, node, {"bar": element("div", "es-gauge-bar", node)})
    elif kind == "canvas":
        binding = Binding(thing, element("canvas", "es-canvas"), {})
    elif kind == "picture":
        binding = Binding(thing, element("img", "es-picture"), {})
    elif kind == "link":
        binding = Binding(thing, element("a", "es-link"), {})
    elif kind == "table":
        node = element("table", "es-table")
        binding = Binding(thing, node, {
            "title": element("caption", "es-table-title", node),
            "body": element("tbody", "es-table-body", node),
        })
    elif kind == "row":
        binding = Binding(thing, element("tr", "es-row"), {})
    elif kind == "cell":
        binding = Binding(thing, element("td", "es-cell"), {})
    elif kind == "menu":
        node = element("select", "es-menu")
        # Until something is picked, the menu shows its hint, which cannot itself be picked.
        blank = element("option", "es-menu-hint", node)
        blank.setAttribute("value", "")
        blank.setAttribute("disabled", "")
        binding = Binding(thing, node, {"blank": blank})

        def picked(event):
            chosen = str(node.value)
            options = [each for each in world.things.get("option", ())
                       if not each.removed and each.fields.get("menu") is thing]

            def change():
                for each in options:
                    if str(each.serial) == chosen:
                        each.marks.add("picked")
                    else:
                        each.marks.discard("picked")
            _act(world, change)

        backend.listen(node, "change", picked)
    else:  # an option of a menu
        node = element("option", "es-option")
        node.setAttribute("value", str(thing.serial))
        binding = Binding(thing, node, {})
    binding.node.setAttribute("data-kind", kind)
    binding.node.setAttribute("data-name", thing.name)
    return binding


def _plain(number):
    """A number as a person says it: 3, not 3/1."""
    number = Fraction(number)
    return str(number.numerator) if number.denominator == 1 else f"{float(number):g}"


def _share(thing):
    """How full a gauge is, from 0 to 100."""
    level, limit = Fraction(thing.fields["level"]), Fraction(thing.fields["limit"])
    if limit <= 0:
        return 0
    return int(max(Fraction(0), min(Fraction(100), level / limit * 100)))


def _show(binding):
    """Tell the element whatever about its thing has changed."""
    thing, node, parts = binding.thing, binding.node, binding.parts
    fields, marks, kind = thing.fields, thing.marks, thing.kind
    binding.tell("hidden", "hidden" in marks, lambda value: setattr(node, "hidden", value))
    if kind == "panel":
        title = fields.get("title")
        binding.tell("title", title or "", _text(parts["title"]))
        binding.tell("titled", title is None, lambda value: setattr(parts["title"], "hidden", value))
    elif kind in ("heading", "note"):
        binding.tell("wording", fields["wording"], _text(node))
    elif kind == "field":
        wording = fields["wording"]
        if str(node.value) != wording:  # never write back what was just typed: it moves the caret
            node.value = wording
        binding.tell("hint", fields.get("hint") or "", lambda value: (
            node.setAttribute("placeholder", value),
            # A hint disappears when something is typed. The name stays.
            node.setAttribute("aria-label", value) if value else node.removeAttribute("aria-label")))
    elif kind == "button":
        binding.tell("label", fields["label"], _text(node))
        # Only a button that is one of a set of choices is a switch. An ordinary
        # button says nothing about being pressed, or it would be read out as one.
        if binding.choice:
            binding.tell("chosen", "chosen" in marks, _flag(node, "aria-pressed"))
    elif kind == "card":
        wording = fields["wording"]
        if str(parts["words"].textContent) != wording:  # as with a field: leave what was just typed
            parts["words"].textContent = wording
        binding.tell("named", wording, lambda value: (
            parts["box"].setAttribute("aria-label", f"Done: {value}"),
            parts["words"].setAttribute("aria-label", f"Reword: {value}"),
            parts["cross"].setAttribute("aria-label", f"Remove: {value}")))
        ticked = "ticked" in marks
        if bool(parts["box"].checked) != ticked:
            parts["box"].checked = ticked
        binding.tell("ticked", ticked, _flag(node, "data-ticked"))
        tag = fields.get("tag")
        binding.tell("tag", tag or "", _text(parts["tag"]))
        binding.tell("tagged", not tag, lambda value: setattr(parts["tag"], "hidden", value))
        starred = "starred" in marks
        binding.tell("starred", starred, lambda value: (
            _flag(node, "data-starred")(value),
            _flag(parts["star"], "aria-pressed")(value),
            parts["star"].setAttribute("aria-label", f"Star: {wording}"),
            setattr(parts["star"], "textContent", "\u2605" if value else "\u2606")))
    elif kind == "canvas":
        pass
    elif kind == "picture":
        binding.tell("source", _safe(fields["source"], pictures=True), lambda value: node.setAttribute("src", value))
        binding.tell("caption", fields.get("caption") or "", lambda value: node.setAttribute("alt", value))
    elif kind == "link":
        binding.tell("wording", fields["wording"], _text(node))
        binding.tell("target", _safe(fields["target"]), lambda value: (
            node.setAttribute("href", value) if value else node.removeAttribute("href")))
    elif kind == "table":
        title = fields.get("title")
        binding.tell("title", title or "", _text(parts["title"]))
        binding.tell("titled", title is None, lambda value: setattr(parts["title"], "hidden", value))
    elif kind == "row":
        binding.tell("leading", "leading" in marks, _flag(node, "data-leading"))
    elif kind == "cell":
        binding.tell("wording", fields["wording"], _text(node))
        row = fields.get("row")
        heads = row is not None and "leading" in row.marks
        binding.tell("heads", heads, lambda value: node.setAttribute("role", "columnheader" if value else "cell"))
    elif kind == "menu":
        hint = fields.get("hint") or ""
        binding.tell("hint", hint, lambda value: (
            setattr(parts["blank"], "textContent", value),
            node.setAttribute("aria-label", value) if value else node.removeAttribute("aria-label")))
    elif kind == "option":
        binding.tell("wording", fields["wording"], _text(node))
        picked = "picked" in marks
        if bool(node.selected) != picked:
            node.selected = picked
    else:
        share = _share(thing)
        binding.tell("share", share, lambda value: (
            parts["bar"].setAttribute("style", f"width: {value}%"),
            node.setAttribute("aria-valuenow", value)))
        binding.tell("spoken", (fields["level"], fields["limit"]), lambda value: node.setAttribute(
            "aria-valuetext", f"{_plain(value[0])} of {_plain(value[1])}"))


def sync(world):
    """Make the page match the world: new elements for new things, changes for
    changed ones, and nothing left of a thing that has been removed."""
    state = _state(world)
    backend, bound, order = state["backend"], state["bound"], state["order"]
    things = sorted(
        (thing for kind in KINDS for thing in world.things.get(kind, ()) if not thing.removed),
        key=lambda thing: thing.serial,
    )
    for thing in things:
        if thing.serial not in bound:
            bound[thing.serial] = _make(world, state, thing)
    present = {thing.serial for thing in things}
    for serial in [serial for serial in bound if serial not in present]:
        binding = bound.pop(serial)
        if binding.inside is not None:
            backend.discard(binding.inside, binding.node)
        order.pop(serial, None)
        state["lists"].pop(serial, None)
        state["choices"].discard(serial)
    # What belongs inside what. The page itself is 0; a holder is its thing's serial.
    wanted = {ROOT: []}
    wanted.update((thing.serial, []) for thing in things if thing.kind in HOLDERS)
    for thing in things:
        binding = bound[thing.serial]
        holder = thing.fields.get(INSIDE.get(thing.kind, "panel"))
        home = holder.serial if holder is not None and holder.serial in wanted else ROOT
        if thing.kind in INSIDE and home == ROOT:
            home = None  # a row with no table, a cell with no row: there is nowhere to put it
        if thing.kind == "panel" and home != ROOT:
            # A panel inside itself, or inside a panel that is inside it, goes on the page instead.
            seen, above = {thing.serial}, holder
            while above is not None and above.serial not in seen:
                seen.add(above.serial)
                above = above.fields.get("panel")
            if above is not None:
                home = ROOT
        binding.home = home
        if home is None:
            if binding.inside is not None:
                binding.inside.removeChild(binding.node)
                binding.inside = None
            continue
        wanted[home].append(binding)
        if thing.kind == "button" and "chosen" in thing.marks:
            state["choices"].add(home)  # the buttons that stand with a chosen one are choices too
    for thing in things:
        binding = bound[thing.serial]
        binding.choice = thing.kind == "button" and binding.home in state["choices"]
        _show(binding)
    active = backend.active()
    for home, bindings in wanted.items():
        if home == ROOT:
            parent = backend.root
        else:
            part = HOLDERS[bound[home].thing.kind]
            parent = bound[home].node if part is None else bound[home].parts[part]
        # A lower order comes first; with the same order (or none), the order made.
        bindings.sort(key=lambda binding: (Fraction(binding.thing.fields.get("order") or 0), binding.thing.serial))
        now = [binding for binding in order.get(home, ())
               if binding.thing.serial in present and binding.home == home and binding.inside is parent]
        for index, binding in enumerate(bindings):
            if index < len(now) and now[index] is binding:
                continue
            if binding in now:
                now.remove(binding)
            # Only an element that is out of place is touched: one put in again is
            # drawn again, and whatever had the reader's attention inside it loses it.
            if index < len(now):
                parent.insertBefore(binding.node, now[index].node)
            else:
                parent.appendChild(binding.node)  # after anything the library put there itself
            now.insert(index, binding)
            binding.inside = parent
        order[home] = bindings
        # A place that holds nothing but cards is a list, and is told so once.
        listed = bool(bindings) and all(binding.thing.kind == "card" for binding in bindings)
        if state["lists"].get(home) != listed:
            state["lists"][home] = listed
            if listed:
                parent.setAttribute("role", "list")
            else:
                parent.removeAttribute("role")
    for thing in things:
        if thing.kind == "menu":
            binding = bound[thing.serial]
            blank = binding.parts["blank"]
            none = not any("picked" in each.thing.marks for each in order.get(thing.serial, ()))
            if bool(blank.selected) != none:
                blank.selected = none
    for thing in things:
        if thing.kind == "canvas":
            _show_canvas(state, bound[thing.serial])
    for serial in set(state["canvases"]) - present:
        del state["canvases"][serial]
    backend.attend(active)


def _act(world, change):
    """Something a person did: change the world, let the program answer, show the result."""
    state = _state(world)
    try:
        world.event(change)
    except EnglishError as error:
        message = getattr(error, "message", None) or str(error)
        state["problems"].append(message)
        world.out(f"That could not be done: {message}")
    finally:
        _settle(world)


def _settle(world):
    """Momentary adjectives are over once the program has answered them."""
    for kind, adjectives in MOMENTARY.items():
        for thing in world.things.get(kind, ()):
            thing.marks.difference_update(adjectives)
    if _state(world)["live"]:
        sync(world)


# ------------------------------------------------------- what the compiler calls


def _whole(value, name, least, most):
    value = Fraction(value)
    if value.denominator != 1 or not least <= value <= most:
        raise EnglishError(f"{name} has to be a whole number from {least} to {most}.",
                           stage="run", recoverable=True)
    return int(value)


def _canvas(state, canvas):
    from ..runtime import alive
    canvas = alive(canvas)
    width = _whole(canvas.fields["width"], "The canvas width", 1, 1024)
    height = _whole(canvas.fields["height"], "The canvas height", 1, 1024)
    entry = state["canvases"].get(canvas.serial)
    if entry is None or entry["size"] != (width, height):
        entry = {"size": (width, height), "pixels": bytearray(width * height), "dirty": True}
        state["canvases"][canvas.serial] = entry
    return entry


def verb_fill(world, canvas, left, top, width, height, shade):
    entry = _canvas(_state(world), canvas)
    canvas_width, canvas_height = entry["size"]
    x = _whole(left, "The left column", 0, canvas_width - 1)
    y = _whole(top, "The top row", 0, canvas_height - 1)
    width = _whole(width, "The fill width", 1, canvas_width - x)
    height = _whole(height, "The fill height", 1, canvas_height - y)
    shade = _whole(shade, "The shade", 0, 3)
    line = bytes([shade]) * width
    pixels = entry["pixels"]
    for row in range(y, y + height):
        start = row * canvas_width + x
        if pixels[start:start + width] != line:
            pixels[start:start + width] = line
            entry["dirty"] = True


def verb_paint(world, canvas, column, down, shade):
    entry = _canvas(_state(world), canvas)
    width, height = entry["size"]
    x = _whole(column, "The column", 0, width - 1)
    y = _whole(down, "The row", 0, height - 1)
    shade = _whole(shade, "The shade", 0, 3)
    index = y * width + x
    if entry["pixels"][index] != shade:
        entry["pixels"][index] = shade
        entry["dirty"] = True


def verb_trace(world, canvas, start_column, start_row, finish_column, finish_row, shade):
    entry = _canvas(_state(world), canvas)
    width, height = entry["size"]
    x = _whole(start_column, "The start column", 0, width - 1)
    y = _whole(start_row, "The start row", 0, height - 1)
    end_x = _whole(finish_column, "The finish column", 0, width - 1)
    end_y = _whole(finish_row, "The finish row", 0, height - 1)
    shade = _whole(shade, "The shade", 0, 3)
    dx, dy = abs(end_x - x), -abs(end_y - y)
    step_x = 1 if x < end_x else -1
    step_y = 1 if y < end_y else -1
    error = dx + dy
    pixels = entry["pixels"]
    while True:
        index = y * width + x
        if pixels[index] != shade:
            pixels[index] = shade
            entry["dirty"] = True
        if x == end_x and y == end_y:
            break
        twice = 2 * error
        if twice >= dy:
            error += dy
            x += step_x
        if twice <= dx:
            error += dx
            y += step_y


def verb_shade(world, canvas, column, down, vertices, shade):
    entry = _canvas(_state(world), canvas)
    width, height = entry["size"]
    def integer(value, name):
        value = Fraction(value)
        if value.denominator != 1:
            raise EnglishError(f"{name} has to be a whole number.", stage="run", recoverable=True)
        return int(value)
    x = integer(column, "The origin column")
    y = integer(down, "The origin row")
    if len(vertices) < 6 or len(vertices) % 2:
        raise EnglishError("The vertices have to contain at least three pairs of coordinates.",
                           stage="run", recoverable=True)
    points = []
    for i in range(0, len(vertices), 2):
        px = x + integer(vertices[i], "A vertex column")
        py = y + integer(vertices[i + 1], "A vertex row")
        points.append((_whole(px, "A vertex column", 0, width - 1),
                       _whole(py, "A vertex row", 0, height - 1)))
    shade = _whole(shade, "The shade", 0, 3)
    edges = list(zip(points, points[1:] + points[:1]))
    pixels = entry["pixels"]
    def paint(px, py):
        index = py * width + px
        if pixels[index] != shade:
            pixels[index] = shade
            entry["dirty"] = True
    for py in range(min(p[1] for p in points), max(p[1] for p in points) + 1):
        crossings = []
        for (x1, y1), (x2, y2) in edges:
            if min(y1, y2) <= py < max(y1, y2):
                crossings.append(Fraction(x1) + Fraction((py - y1) * (x2 - x1), y2 - y1))
        crossings.sort()
        for i in range(0, len(crossings) - 1, 2):
            left, right = crossings[i:i + 2]
            for px in range(-(-left.numerator // left.denominator), right.numerator // right.denominator + 1):
                paint(px, py)
    for start, end in edges:
        (px, py), (end_x, end_y) = sorted((start, end))
        dx, dy = abs(end_x - px), -abs(end_y - py)
        step_x = 1 if px < end_x else -1
        step_y = 1 if py < end_y else -1
        error = dx + dy
        while True:
            paint(px, py)
            if px == end_x and py == end_y:
                break
            twice = 2 * error
            if twice >= dy:
                error += dy
                px += step_x
            if twice <= dx:
                error += dx
                py += step_y


def value_pixel(world, canvas, column, down):
    entry = _canvas(_state(world), canvas)
    width, height = entry["size"]
    x = _whole(column, "The column", 0, width - 1)
    y = _whole(down, "The row", 0, height - 1)
    return Fraction(entry["pixels"][y * width + x])


def _show_canvas(state, binding):
    entry = _canvas(state, binding.thing)
    if not entry["dirty"]:
        return
    width, height = entry["size"]
    pixels = entry["pixels"]
    backend = state["backend"]
    if backend.remote_canvas is not None:
        backend.remote_canvas(binding.thing.serial, binding.thing.name, width, height, bytes(pixels))
    elif backend.browser:
        node = binding.node
        if binding.shown.get("canvas size") != (width, height):
            node.width, node.height = width, height
            binding.shown["canvas size"] = (width, height)
        context = node.getContext("2d")
        shades = ("#ffffff", "#aaaaaa", "#555555", "#000000")
        for y in range(height):
            x = 0
            while x < width:
                shade = pixels[y * width + x]
                end = x + 1
                while end < width and pixels[y * width + end] == shade:
                    end += 1
                context.fillStyle = shades[shade]
                context.fillRect(x, y, end - x, 1)
                x = end
    else:
        binding.node.setAttribute("width", width)
        binding.node.setAttribute("height", height)
    entry["dirty"] = False


def verb_remember(world, line, key):
    _state(world)["backend"].keep(key, line)


def value_memory(world, key):
    return _state(world)["backend"].kept(key)


def live(world):
    """The program's own sentences are done: show the page and start listening."""
    state = _state(world)
    state["live"] = True
    _settle(world)


def finish(world):
    state = world.libraries.get(NAME) or {}
    if state.get("live") and not state["backend"].browser and state["backend"].remote_canvas is None:
        world.out("")
        world.out("The page, as it stands (there is no browser here to show it):")
        for line in sketch(world).splitlines():
            world.out("  " + line)


# ------------------------------------------------- the stand-in page, for people


def sketch(world):
    """The page in plain text, one element to a line, as it would be laid out."""
    state = _state(world)
    lines = []

    def draw(binding, indent):
        thing = binding.thing
        if "hidden" in thing.marks:
            return
        fields, marks, kind = thing.fields, thing.marks, thing.kind
        pad = "  " * indent
        if kind == "panel":
            if fields.get("title") is not None:
                lines.append(f"{pad}-- {fields['title']} --")
            row, inner = [], state["order"].get(thing.serial, [])
            for child in inner:
                if "hidden" in child.thing.marks:
                    continue
                if child.thing.kind == "note" and not child.thing.fields["wording"]:
                    continue
                if child.thing.kind in ("field", "button", "note", "gauge", "picture", "link", "menu"):
                    row.append(_inline(child.thing) if child.thing.kind != "menu" else _menu(state, child.thing))
                else:
                    if row:
                        lines.append(pad + "  ".join(row))
                        row = []
                    draw(child, indent + (1 if child.thing.kind == "panel" else 0))
            if row:
                lines.append(pad + "  ".join(row))
        elif kind == "heading":
            lines.append(f"{pad}# {fields['wording']}")
        elif kind == "table":
            if fields.get("title") is not None:
                lines.append(f"{pad}-- {fields['title']} --")
            for row in state["order"].get(thing.serial, []):
                if "hidden" in row.thing.marks:
                    continue
                cells = [cell.thing.fields["wording"] for cell in state["order"].get(row.thing.serial, [])]
                lines.append(f"{pad}| " + " | ".join(cells) + " |")
                if "leading" in row.thing.marks:
                    lines.append(f"{pad}|" + "|".join("-" * (len(cell) + 2) for cell in cells) + "|")
        elif kind == "note" and not fields["wording"]:
            return  # a note with nothing to say takes no room
        elif kind == "card":
            star = "* " if "starred" in marks else ""
            tag = f"  #{fields['tag']}" if fields.get("tag") else ""
            lines.append(f"{pad}[{'x' if 'ticked' in marks else ' '}] {star}{fields['wording']}{tag}")
        elif kind == "menu":
            lines.append(pad + _menu(state, thing))
        else:
            lines.append(pad + _inline(thing))

    for binding in state["order"].get(ROOT, []):
        draw(binding, 0)
    return "\n".join(lines)


def _menu(state, thing):
    picked = [each.thing.fields["wording"] for each in state["order"].get(thing.serial, [])
              if "picked" in each.thing.marks]
    return "{" + (picked[0] if picked else f"({thing.fields.get('hint') or 'choose'})") + " v}"


def _inline(thing):
    fields, kind = thing.fields, thing.kind
    if kind == "canvas":
        return f"(canvas: {_plain(fields['width'])} by {_plain(fields['height'])})"
    if kind == "picture":
        return f"(picture: {fields.get('caption') or fields['source']})"
    if kind == "link":
        return f"{fields['wording']} -> {_safe(fields['target']) or '(nowhere)'}"
    if kind == "field":
        words = fields["wording"] or (f"({fields['hint']})" if fields.get("hint") else "")
        return f"[_{words}_]"
    if kind == "button":
        return f"<{fields['label']}>" if "chosen" in thing.marks else f"[{fields['label']}]"
    if kind == "gauge":
        filled = _share(thing) // 10
        return "|" + "=" * filled + "." * (10 - filled) + "|"
    return fields["wording"]


def element(world, thing_or_name):
    """The stand-in element of a thing, given the thing or its name."""
    state = _state(world)
    for binding in state["bound"].values():
        thing = binding.thing
        if thing is thing_or_name or thing.name.lower() == str(thing_or_name).lower():
            return binding
    raise LookupError(f"nothing on the page is called {thing_or_name}")


def press(world, name):
    """Press a button, as a person would."""
    element(world, name).node.fire("click")


def type_in(world, name, words, enter=False):
    """Type into a field, and press Enter if asked."""
    node = element(world, name).node
    node.value = words
    node.fire("input")
    if enter:
        node.fire("keydown", key="Enter")


def tick(world, name, ticked=True):
    """Tick or untick a card's box."""
    box = element(world, name).parts["box"]
    box.checked = ticked
    box.fire("change")


def star(world, name):
    """Press a card's star: on if it was off, off if it was on."""
    element(world, name).parts["star"].fire("click")


def reword(world, name, words):
    """Edit a card's words where they stand, and leave them."""
    node = element(world, name).parts["words"]
    node.textContent = words
    node.fire("blur")


def pick(world, name):
    """Choose an option from its menu, as a person would."""
    option = element(world, name)
    menu = option.thing.fields["menu"]
    node = element(world, menu).node
    node.value = str(option.thing.serial)
    node.fire("change")


def dismiss(world, name):
    """Press a card's cross."""
    element(world, name).parts["cross"].fire("click")

"""The vulkan library: draw triangles on the graphics card, from EnglishScript.

    Use the vulkan library.

SOURCE below is what a program gains by saying that: a few kinds, some named
colours, the driver called Vulkan, and five verbs and one worked-out value that
are carried out here, by the real Vulkan API (see _vk.py). Pictures are drawn
off screen and saved as PNG files; there is no window.

Each verb stands for the Vulkan calls named beside it in SOURCE.
"""
from __future__ import annotations

from ..lexer import EnglishError
from ..runtime import alive
from . import _vk

NAME = "vulkan"
LARGEST = 8192  # pixels along one side of a picture

SOURCE = '''
A colour has a red (number), a green (number), and a blue (number).
There is a colour called Red whose red is 1, whose green is 0, and whose blue is 0.
There is a colour called Green whose red is 0, whose green is 1, and whose blue is 0.
There is a colour called Blue whose red is 0, whose green is 0, and whose blue is 1.
There is a colour called Black whose red is 0, whose green is 0, and whose blue is 0.
There is a colour called White whose red is 1, whose green is 1, and whose blue is 1.

A driver has a card (text).
There is a driver called Vulkan whose card is "not started".

A picture has a width (number), a height (number), and a background (colour).
A vertex has an x (number), a y (number), and a colour (colour).
A triangle has a top corner (vertex), a right corner (vertex), and a left corner (vertex).

# vkCreateInstance, vkEnumeratePhysicalDevices, vkCreateDevice, vkCreateCommandPool
To start a driver is done by the library.

# vkCreateImage, vkCreateImageView, vkCreateRenderPass, vkCreateFramebuffer,
# vkCreateShaderModule (twice), vkCreateGraphicsPipelines
To prepare a picture is done by the library.

# vkCreateBuffer (the vertex buffer), vkCmdBeginRenderPass, vkCmdBindPipeline,
# vkCmdBindVertexBuffers, vkCmdDraw, vkCmdEndRenderPass, vkQueueSubmit
To draw a triangle on a picture is done by the library.

# vkCmdCopyImageToBuffer, vkMapMemory, then a PNG file
To save a picture as a file (text) is done by the library.

# vkDestroy... for everything, then vkDestroyDevice and vkDestroyInstance
To close a driver is done by the library.

# One pixel read back from the card, as "red, green, blue", each from 0 to 255.
To work out the pixel (text) of a picture at an across (number) by a down (number) is done by the library.
'''


def problem(message):
    """Something wrong in the world, which a program's "Try:" may recover from."""
    return EnglishError(message, stage="run", recoverable=True)


def _state(world):
    return world.libraries[NAME]


def _card(world):
    card = _state(world).get("card")
    if card is None:
        raise problem('Vulkan has not been started. Say "Start Vulkan." first.')
    return card


def _whole(value, what, least, most):
    if value.denominator != 1 or not least <= value <= most:
        raise problem(f"{what} has to be a whole number from {least} to {most:,}, not {float(value):g}.")
    return int(value)


def _target(world, picture):
    _card(world)
    found = _state(world)["pictures"].get(alive(picture))
    if found is None:
        raise problem(f'{picture.name} has not been prepared. Say "Prepare {picture.name}." first.')
    return found


def _rgb(colour):
    fields = alive(colour).fields
    return float(fields["red"]), float(fields["green"]), float(fields["blue"])


def verb_start(world, driver):
    state = _state(world)
    if state.get("card") is not None:
        raise problem("Vulkan is already started.")
    try:
        card = _vk.Card("EnglishScript")
    except _vk.VulkanError as error:
        raise problem(f"I couldn't start Vulkan: {error}.") from None
    state["card"] = card
    state["pictures"] = {}  # picture -> {"target": ..., "pixels": cached read-back or None}
    alive(driver).fields["card"] = card.name


def verb_prepare(world, picture):
    card = _card(world)
    pictures = _state(world)["pictures"]
    if alive(picture) in pictures:
        raise problem(f"{picture.name} is already prepared.")
    width = _whole(picture.fields["width"], f"The width of {picture.name}", 1, LARGEST)
    height = _whole(picture.fields["height"], f"The height of {picture.name}", 1, LARGEST)
    try:
        target = card.target(width, height)
    except _vk.VulkanError as error:
        raise problem(f"I couldn't prepare {picture.name}: {error}.") from None
    pictures[picture] = {"target": target, "pixels": None}


def verb_draw(world, triangle, picture):
    entry = _target(world, picture)
    corners = alive(triangle).fields
    vertices = []
    for corner in ("top corner", "right corner", "left corner"):
        vertex = alive(corners[corner]).fields
        vertices.append((float(vertex["x"]), float(vertex["y"])) + _rgb(vertex["colour"]))
    try:
        entry["target"].draw(vertices, clear=_rgb(picture.fields["background"]))
    except _vk.VulkanError as error:
        raise problem(f"I couldn't draw {triangle.name}: {error}.") from None
    entry["pixels"] = None


def _pixels(world, picture):
    entry = _target(world, picture)
    if entry["pixels"] is None:
        target = entry["target"]
        try:
            if not target.drawn:  # nothing drawn yet: the picture is just its background
                target.draw([], clear=_rgb(picture.fields["background"]))
            entry["pixels"] = target.read()
        except _vk.VulkanError as error:
            raise problem(f"I couldn't read {picture.name} back from the card: {error}.") from None
    return entry["target"], entry["pixels"]


def verb_save(world, picture, file):
    target, pixels = _pixels(world, picture)
    try:
        with open(file, "wb") as handle:
            handle.write(_vk.png(target.width, target.height, pixels))
    except (OSError, ValueError) as error:
        reason = getattr(error, "strerror", None) or str(error)
        raise problem(f"I couldn't write to the file {file}: {reason}.") from None


def value_pixel(world, picture, across, down):
    target, pixels = _pixels(world, picture)
    x = _whole(across, "The place across", 0, target.width - 1)
    y = _whole(down, "The place down", 0, target.height - 1)
    start = (y * target.width + x) * 4
    return ", ".join(str(part) for part in pixels[start:start + 3])


def verb_close(world, driver):
    _card(world)
    finish(world)
    alive(driver).fields["card"] = "not started"


def finish(world):
    """Give the card back. Called when the program ends, however it ends."""
    state = world.libraries.get(NAME) or {}
    card = state.pop("card", None)
    state.pop("pictures", None)
    if card is not None:
        card.close()

"""The two shaders of the triangle, assembled into SPIR-V by hand.

Vulkan takes shaders as SPIR-V, a binary form that is normally produced by a
shader compiler from GLSL. A machine with only a graphics driver has no such
compiler, so this module writes the SPIR-V itself. Each function is the
SPIR-V for the GLSL shown in its docstring.

A SPIR-V module is a list of 32-bit words: a five-word header, then
instructions. Each instruction starts with a word holding its length (high 16
bits) and its opcode (low 16 bits).
"""
from __future__ import annotations

import struct

MAGIC, VERSION_1_0 = 0x07230203, 0x00010000

# Opcodes
CAPABILITY, MEMORY_MODEL, ENTRY_POINT, EXECUTION_MODE = 17, 14, 15, 16
DECORATE, MEMBER_DECORATE = 71, 72
TYPE_VOID, TYPE_INT, TYPE_FLOAT, TYPE_VECTOR, TYPE_STRUCT, TYPE_POINTER, TYPE_FUNCTION = 19, 21, 22, 23, 30, 32, 33
CONSTANT, VARIABLE, LOAD, STORE, ACCESS_CHAIN = 43, 59, 61, 62, 65
COMPOSITE_CONSTRUCT, COMPOSITE_EXTRACT = 80, 81
FUNCTION, FUNCTION_END, LABEL, RETURN = 54, 56, 248, 253

# Operands
SHADER, LOGICAL, GLSL450 = 1, 0, 1
VERTEX, FRAGMENT = 0, 4
ORIGIN_UPPER_LEFT = 7
BLOCK, BUILT_IN, LOCATION = 2, 11, 30
POSITION = 0
INPUT, OUTPUT = 1, 3


def text(string):
    """A string as SPIR-V wants it: UTF-8, ended by a zero byte, padded to whole words."""
    data = string.encode("utf-8") + b"\0"
    data += b"\0" * (-len(data) % 4)
    return list(struct.unpack(f"<{len(data) // 4}I", data))


def real(value):
    """A 32-bit float as one word."""
    return struct.unpack("<I", struct.pack("<f", value))[0]


class Module:
    def __init__(self):
        self.words = []
        self.bound = 1

    def new(self):
        """A fresh id."""
        self.bound += 1
        return self.bound - 1

    def op(self, opcode, *operands):
        self.words.append(((len(operands) + 1) << 16) | opcode)
        self.words.extend(operands)

    def finish(self):
        return [MAGIC, VERSION_1_0, 0, self.bound, 0] + self.words


def vertex_shader():
    """
    #version 450
    layout(location = 0) in vec2 inPosition;
    layout(location = 1) in vec3 inColour;
    layout(location = 0) out vec3 fragColour;
    void main() {
        gl_Position = vec4(inPosition, 0.0, 1.0);
        fragColour = inColour;
    }
    """
    m = Module()
    (void, function, float_, vec2, vec3, vec4, per_vertex, per_vertex_out, gl_out, int_, zero,
     vec2_in, in_position, vec3_in, in_colour, vec3_out, frag_colour, vec4_out, f0, f1,
     main, entry, position, x, y, full, where, colour) = (m.new() for _ in range(28))

    m.op(CAPABILITY, SHADER)
    m.op(MEMORY_MODEL, LOGICAL, GLSL450)
    m.op(ENTRY_POINT, VERTEX, main, *text("main"), in_position, in_colour, frag_colour, gl_out)
    m.op(DECORATE, in_position, LOCATION, 0)
    m.op(DECORATE, in_colour, LOCATION, 1)
    m.op(DECORATE, frag_colour, LOCATION, 0)
    m.op(MEMBER_DECORATE, per_vertex, 0, BUILT_IN, POSITION)
    m.op(DECORATE, per_vertex, BLOCK)

    m.op(TYPE_VOID, void)
    m.op(TYPE_FUNCTION, function, void)
    m.op(TYPE_FLOAT, float_, 32)
    m.op(TYPE_VECTOR, vec2, float_, 2)
    m.op(TYPE_VECTOR, vec3, float_, 3)
    m.op(TYPE_VECTOR, vec4, float_, 4)
    m.op(TYPE_STRUCT, per_vertex, vec4)                 # gl_PerVertex { vec4 gl_Position; }
    m.op(TYPE_POINTER, per_vertex_out, OUTPUT, per_vertex)
    m.op(VARIABLE, per_vertex_out, gl_out, OUTPUT)
    m.op(TYPE_INT, int_, 32, 1)
    m.op(CONSTANT, int_, zero, 0)
    m.op(TYPE_POINTER, vec2_in, INPUT, vec2)
    m.op(VARIABLE, vec2_in, in_position, INPUT)
    m.op(TYPE_POINTER, vec3_in, INPUT, vec3)
    m.op(VARIABLE, vec3_in, in_colour, INPUT)
    m.op(TYPE_POINTER, vec3_out, OUTPUT, vec3)
    m.op(VARIABLE, vec3_out, frag_colour, OUTPUT)
    m.op(TYPE_POINTER, vec4_out, OUTPUT, vec4)
    m.op(CONSTANT, float_, f0, real(0.0))
    m.op(CONSTANT, float_, f1, real(1.0))

    m.op(FUNCTION, void, main, 0, function)
    m.op(LABEL, entry)
    m.op(LOAD, vec2, position, in_position)
    m.op(COMPOSITE_EXTRACT, float_, x, position, 0)
    m.op(COMPOSITE_EXTRACT, float_, y, position, 1)
    m.op(COMPOSITE_CONSTRUCT, vec4, full, x, y, f0, f1)
    m.op(ACCESS_CHAIN, vec4_out, where, gl_out, zero)
    m.op(STORE, where, full)                            # gl_Position = vec4(inPosition, 0.0, 1.0)
    m.op(LOAD, vec3, colour, in_colour)
    m.op(STORE, frag_colour, colour)                    # fragColour = inColour
    m.op(RETURN)
    m.op(FUNCTION_END)
    return m.finish()


def fragment_shader():
    """
    #version 450
    layout(location = 0) in vec3 fragColour;
    layout(location = 0) out vec4 outColour;
    void main() {
        outColour = vec4(fragColour, 1.0);
    }
    """
    m = Module()
    (void, function, float_, vec3, vec4, vec3_in, frag_colour, vec4_out, out_colour, f1,
     main, entry, colour, red, green, blue, full) = (m.new() for _ in range(17))

    m.op(CAPABILITY, SHADER)
    m.op(MEMORY_MODEL, LOGICAL, GLSL450)
    m.op(ENTRY_POINT, FRAGMENT, main, *text("main"), frag_colour, out_colour)
    m.op(EXECUTION_MODE, main, ORIGIN_UPPER_LEFT)
    m.op(DECORATE, frag_colour, LOCATION, 0)
    m.op(DECORATE, out_colour, LOCATION, 0)

    m.op(TYPE_VOID, void)
    m.op(TYPE_FUNCTION, function, void)
    m.op(TYPE_FLOAT, float_, 32)
    m.op(TYPE_VECTOR, vec3, float_, 3)
    m.op(TYPE_VECTOR, vec4, float_, 4)
    m.op(TYPE_POINTER, vec3_in, INPUT, vec3)
    m.op(VARIABLE, vec3_in, frag_colour, INPUT)
    m.op(TYPE_POINTER, vec4_out, OUTPUT, vec4)
    m.op(VARIABLE, vec4_out, out_colour, OUTPUT)
    m.op(CONSTANT, float_, f1, real(1.0))

    m.op(FUNCTION, void, main, 0, function)
    m.op(LABEL, entry)
    m.op(LOAD, vec3, colour, frag_colour)
    m.op(COMPOSITE_EXTRACT, float_, red, colour, 0)
    m.op(COMPOSITE_EXTRACT, float_, green, colour, 1)
    m.op(COMPOSITE_EXTRACT, float_, blue, colour, 2)
    m.op(COMPOSITE_CONSTRUCT, vec4, full, red, green, blue, f1)
    m.op(STORE, out_colour, full)                       # outColour = vec4(fragColour, 1.0)
    m.op(RETURN)
    m.op(FUNCTION_END)
    return m.finish()

"""Vulkan through ctypes: just enough to draw coloured triangles into an off-screen picture.

Nothing here is installed or downloaded. It talks to the Vulkan loader that
comes with the graphics driver (vulkan-1.dll on Windows, libvulkan.so.1 on
Linux) using Python's built-in ctypes, and it carries its two shaders as
SPIR-V that it assembles itself (see _spirv.py), because there is no shader
compiler on a machine without the Vulkan SDK.

The picture is drawn off screen and read back, so no window is needed:

    card = Card("Hello Triangle")           # vkCreateInstance, vkCreateDevice
    target = card.target(800, 600)          # vkCreateImage ... vkCreateGraphicsPipelines
    target.draw([(0, -0.5, 1, 0, 0), ...], clear=(0, 0, 0))   # vkCmdDraw
    pixels = target.read()                  # vkCmdCopyImageToBuffer: RGBA bytes
    card.close()
"""
from __future__ import annotations

import ctypes
import struct
import sys
import zlib
from ctypes import (
    POINTER, Structure, byref, c_char, c_char_p, c_float, c_int32, c_size_t,
    c_uint8, c_uint32, c_uint64, c_void_p, pointer,
)

from . import _spirv


class VulkanError(Exception):
    """Vulkan is missing, or refused something."""


# ------------------------------------------------------------------ the C side

HANDLE = c_void_p  # dispatchable handles are pointers
OBJECT = c_uint64  # the others are 64-bit numbers on every platform


def _struct(name, **fields):
    return type(name, (Structure,), {"_fields_": list(fields.items())})


def _info(name, **fields):
    """A struct that starts with sType and pNext, as nearly all "create info" structs do."""
    return _struct(name, sType=c_uint32, pNext=c_void_p, **fields)


VkExtent2D = _struct("VkExtent2D", width=c_uint32, height=c_uint32)
VkExtent3D = _struct("VkExtent3D", width=c_uint32, height=c_uint32, depth=c_uint32)
VkOffset2D = _struct("VkOffset2D", x=c_int32, y=c_int32)
VkOffset3D = _struct("VkOffset3D", x=c_int32, y=c_int32, z=c_int32)
VkRect2D = _struct("VkRect2D", offset=VkOffset2D, extent=VkExtent2D)

VkApplicationInfo = _info(
    "VkApplicationInfo", pApplicationName=c_char_p, applicationVersion=c_uint32,
    pEngineName=c_char_p, engineVersion=c_uint32, apiVersion=c_uint32)
VkInstanceCreateInfo = _info(
    "VkInstanceCreateInfo", flags=c_uint32, pApplicationInfo=POINTER(VkApplicationInfo),
    enabledLayerCount=c_uint32, ppEnabledLayerNames=c_void_p,
    enabledExtensionCount=c_uint32, ppEnabledExtensionNames=c_void_p)
VkPhysicalDeviceProperties = _struct(  # only the head is read; the rest is room for the limits
    "VkPhysicalDeviceProperties", apiVersion=c_uint32, driverVersion=c_uint32, vendorID=c_uint32,
    deviceID=c_uint32, deviceType=c_uint32, deviceName=c_char * 256, rest=c_uint8 * 2048)
VkQueueFamilyProperties = _struct(
    "VkQueueFamilyProperties", queueFlags=c_uint32, queueCount=c_uint32,
    timestampValidBits=c_uint32, minImageTransferGranularity=VkExtent3D)
VkMemoryType = _struct("VkMemoryType", propertyFlags=c_uint32, heapIndex=c_uint32)
VkMemoryHeap = _struct("VkMemoryHeap", size=c_uint64, flags=c_uint32)
VkPhysicalDeviceMemoryProperties = _struct(
    "VkPhysicalDeviceMemoryProperties", memoryTypeCount=c_uint32, memoryTypes=VkMemoryType * 32,
    memoryHeapCount=c_uint32, memoryHeaps=VkMemoryHeap * 16)
VkDeviceQueueCreateInfo = _info(
    "VkDeviceQueueCreateInfo", flags=c_uint32, queueFamilyIndex=c_uint32, queueCount=c_uint32,
    pQueuePriorities=POINTER(c_float))
VkDeviceCreateInfo = _info(
    "VkDeviceCreateInfo", flags=c_uint32, queueCreateInfoCount=c_uint32,
    pQueueCreateInfos=POINTER(VkDeviceQueueCreateInfo),
    enabledLayerCount=c_uint32, ppEnabledLayerNames=c_void_p,
    enabledExtensionCount=c_uint32, ppEnabledExtensionNames=c_void_p, pEnabledFeatures=c_void_p)

VkImageCreateInfo = _info(
    "VkImageCreateInfo", flags=c_uint32, imageType=c_uint32, format=c_uint32, extent=VkExtent3D,
    mipLevels=c_uint32, arrayLayers=c_uint32, samples=c_uint32, tiling=c_uint32, usage=c_uint32,
    sharingMode=c_uint32, queueFamilyIndexCount=c_uint32, pQueueFamilyIndices=c_void_p,
    initialLayout=c_uint32)
VkMemoryRequirements = _struct("VkMemoryRequirements", size=c_uint64, alignment=c_uint64, memoryTypeBits=c_uint32)
VkMemoryAllocateInfo = _info("VkMemoryAllocateInfo", allocationSize=c_uint64, memoryTypeIndex=c_uint32)
VkComponentMapping = _struct("VkComponentMapping", r=c_uint32, g=c_uint32, b=c_uint32, a=c_uint32)
VkImageSubresourceRange = _struct(
    "VkImageSubresourceRange", aspectMask=c_uint32, baseMipLevel=c_uint32, levelCount=c_uint32,
    baseArrayLayer=c_uint32, layerCount=c_uint32)
VkImageViewCreateInfo = _info(
    "VkImageViewCreateInfo", flags=c_uint32, image=OBJECT, viewType=c_uint32, format=c_uint32,
    components=VkComponentMapping, subresourceRange=VkImageSubresourceRange)
VkBufferCreateInfo = _info(
    "VkBufferCreateInfo", flags=c_uint32, size=c_uint64, usage=c_uint32, sharingMode=c_uint32,
    queueFamilyIndexCount=c_uint32, pQueueFamilyIndices=c_void_p)

VkAttachmentDescription = _struct(
    "VkAttachmentDescription", flags=c_uint32, format=c_uint32, samples=c_uint32, loadOp=c_uint32,
    storeOp=c_uint32, stencilLoadOp=c_uint32, stencilStoreOp=c_uint32,
    initialLayout=c_uint32, finalLayout=c_uint32)
VkAttachmentReference = _struct("VkAttachmentReference", attachment=c_uint32, layout=c_uint32)
VkSubpassDescription = _struct(
    "VkSubpassDescription", flags=c_uint32, pipelineBindPoint=c_uint32,
    inputAttachmentCount=c_uint32, pInputAttachments=c_void_p,
    colorAttachmentCount=c_uint32, pColorAttachments=POINTER(VkAttachmentReference),
    pResolveAttachments=c_void_p, pDepthStencilAttachment=c_void_p,
    preserveAttachmentCount=c_uint32, pPreserveAttachments=c_void_p)
VkRenderPassCreateInfo = _info(
    "VkRenderPassCreateInfo", flags=c_uint32, attachmentCount=c_uint32,
    pAttachments=POINTER(VkAttachmentDescription), subpassCount=c_uint32,
    pSubpasses=POINTER(VkSubpassDescription), dependencyCount=c_uint32, pDependencies=c_void_p)
VkFramebufferCreateInfo = _info(
    "VkFramebufferCreateInfo", flags=c_uint32, renderPass=OBJECT, attachmentCount=c_uint32,
    pAttachments=POINTER(OBJECT), width=c_uint32, height=c_uint32, layers=c_uint32)

VkShaderModuleCreateInfo = _info(
    "VkShaderModuleCreateInfo", flags=c_uint32, codeSize=c_size_t, pCode=POINTER(c_uint32))
VkPipelineShaderStageCreateInfo = _info(
    "VkPipelineShaderStageCreateInfo", flags=c_uint32, stage=c_uint32, module=OBJECT,
    pName=c_char_p, pSpecializationInfo=c_void_p)
VkVertexInputBindingDescription = _struct(
    "VkVertexInputBindingDescription", binding=c_uint32, stride=c_uint32, inputRate=c_uint32)
VkVertexInputAttributeDescription = _struct(
    "VkVertexInputAttributeDescription", location=c_uint32, binding=c_uint32, format=c_uint32, offset=c_uint32)
VkPipelineVertexInputStateCreateInfo = _info(
    "VkPipelineVertexInputStateCreateInfo", flags=c_uint32,
    vertexBindingDescriptionCount=c_uint32, pVertexBindingDescriptions=POINTER(VkVertexInputBindingDescription),
    vertexAttributeDescriptionCount=c_uint32,
    pVertexAttributeDescriptions=POINTER(VkVertexInputAttributeDescription))
VkPipelineInputAssemblyStateCreateInfo = _info(
    "VkPipelineInputAssemblyStateCreateInfo", flags=c_uint32, topology=c_uint32, primitiveRestartEnable=c_uint32)
VkViewport = _struct(
    "VkViewport", x=c_float, y=c_float, width=c_float, height=c_float, minDepth=c_float, maxDepth=c_float)
VkPipelineViewportStateCreateInfo = _info(
    "VkPipelineViewportStateCreateInfo", flags=c_uint32, viewportCount=c_uint32,
    pViewports=POINTER(VkViewport), scissorCount=c_uint32, pScissors=POINTER(VkRect2D))
VkPipelineRasterizationStateCreateInfo = _info(
    "VkPipelineRasterizationStateCreateInfo", flags=c_uint32, depthClampEnable=c_uint32,
    rasterizerDiscardEnable=c_uint32, polygonMode=c_uint32, cullMode=c_uint32, frontFace=c_uint32,
    depthBiasEnable=c_uint32, depthBiasConstantFactor=c_float, depthBiasClamp=c_float,
    depthBiasSlopeFactor=c_float, lineWidth=c_float)
VkPipelineMultisampleStateCreateInfo = _info(
    "VkPipelineMultisampleStateCreateInfo", flags=c_uint32, rasterizationSamples=c_uint32,
    sampleShadingEnable=c_uint32, minSampleShading=c_float, pSampleMask=c_void_p,
    alphaToCoverageEnable=c_uint32, alphaToOneEnable=c_uint32)
VkPipelineColorBlendAttachmentState = _struct(
    "VkPipelineColorBlendAttachmentState", blendEnable=c_uint32, srcColorBlendFactor=c_uint32,
    dstColorBlendFactor=c_uint32, colorBlendOp=c_uint32, srcAlphaBlendFactor=c_uint32,
    dstAlphaBlendFactor=c_uint32, alphaBlendOp=c_uint32, colorWriteMask=c_uint32)
VkPipelineColorBlendStateCreateInfo = _info(
    "VkPipelineColorBlendStateCreateInfo", flags=c_uint32, logicOpEnable=c_uint32, logicOp=c_uint32,
    attachmentCount=c_uint32, pAttachments=POINTER(VkPipelineColorBlendAttachmentState),
    blendConstants=c_float * 4)
VkPipelineLayoutCreateInfo = _info(
    "VkPipelineLayoutCreateInfo", flags=c_uint32, setLayoutCount=c_uint32, pSetLayouts=c_void_p,
    pushConstantRangeCount=c_uint32, pPushConstantRanges=c_void_p)
VkGraphicsPipelineCreateInfo = _info(
    "VkGraphicsPipelineCreateInfo", flags=c_uint32, stageCount=c_uint32,
    pStages=POINTER(VkPipelineShaderStageCreateInfo),
    pVertexInputState=POINTER(VkPipelineVertexInputStateCreateInfo),
    pInputAssemblyState=POINTER(VkPipelineInputAssemblyStateCreateInfo),
    pTessellationState=c_void_p,
    pViewportState=POINTER(VkPipelineViewportStateCreateInfo),
    pRasterizationState=POINTER(VkPipelineRasterizationStateCreateInfo),
    pMultisampleState=POINTER(VkPipelineMultisampleStateCreateInfo),
    pDepthStencilState=c_void_p,
    pColorBlendState=POINTER(VkPipelineColorBlendStateCreateInfo),
    pDynamicState=c_void_p,
    layout=OBJECT, renderPass=OBJECT, subpass=c_uint32, basePipelineHandle=OBJECT, basePipelineIndex=c_int32)

VkCommandPoolCreateInfo = _info("VkCommandPoolCreateInfo", flags=c_uint32, queueFamilyIndex=c_uint32)
VkCommandBufferAllocateInfo = _info(
    "VkCommandBufferAllocateInfo", commandPool=OBJECT, level=c_uint32, commandBufferCount=c_uint32)
VkCommandBufferBeginInfo = _info("VkCommandBufferBeginInfo", flags=c_uint32, pInheritanceInfo=c_void_p)
VkClearValue = _struct("VkClearValue", color=c_float * 4)
VkRenderPassBeginInfo = _info(
    "VkRenderPassBeginInfo", renderPass=OBJECT, framebuffer=OBJECT, renderArea=VkRect2D,
    clearValueCount=c_uint32, pClearValues=POINTER(VkClearValue))
VkImageSubresourceLayers = _struct(
    "VkImageSubresourceLayers", aspectMask=c_uint32, mipLevel=c_uint32, baseArrayLayer=c_uint32, layerCount=c_uint32)
VkBufferImageCopy = _struct(
    "VkBufferImageCopy", bufferOffset=c_uint64, bufferRowLength=c_uint32, bufferImageHeight=c_uint32,
    imageSubresource=VkImageSubresourceLayers, imageOffset=VkOffset3D, imageExtent=VkExtent3D)
VkSubmitInfo = _info(
    "VkSubmitInfo", waitSemaphoreCount=c_uint32, pWaitSemaphores=c_void_p, pWaitDstStageMask=c_void_p,
    commandBufferCount=c_uint32, pCommandBuffers=POINTER(HANDLE),
    signalSemaphoreCount=c_uint32, pSignalSemaphores=c_void_p)

# VkStructureType
ST_APPLICATION, ST_INSTANCE, ST_QUEUE, ST_DEVICE, ST_SUBMIT, ST_ALLOCATE = 0, 1, 2, 3, 4, 5
ST_BUFFER, ST_IMAGE, ST_IMAGE_VIEW, ST_SHADER = 12, 14, 15, 16
ST_STAGE, ST_VERTEX_INPUT, ST_INPUT_ASSEMBLY, ST_VIEWPORT, ST_RASTER, ST_MULTISAMPLE = 18, 19, 20, 22, 23, 24
ST_BLEND, ST_PIPELINE, ST_LAYOUT, ST_FRAMEBUFFER, ST_RENDER_PASS = 26, 28, 30, 37, 38
ST_POOL, ST_COMMAND_BUFFERS, ST_BEGIN, ST_PASS_BEGIN = 39, 40, 42, 43

FORMAT_RGBA8, FORMAT_VEC2, FORMAT_VEC3 = 37, 103, 106  # R8G8B8A8_UNORM, R32G32_SFLOAT, R32G32B32_SFLOAT
LAYOUT_UNDEFINED, LAYOUT_COLOR, LAYOUT_TRANSFER_SRC = 0, 2, 6
IMAGE_USAGE_TRANSFER_SRC, IMAGE_USAGE_COLOR = 0x1, 0x10
BUFFER_USAGE_TRANSFER_DST, BUFFER_USAGE_VERTEX = 0x2, 0x80
MEMORY_DEVICE_LOCAL, MEMORY_HOST_VISIBLE, MEMORY_HOST_COHERENT = 0x1, 0x2, 0x4
QUEUE_GRAPHICS = 0x1
STAGE_VERTEX, STAGE_FRAGMENT = 0x1, 0x10
LOAD_OP_LOAD, LOAD_OP_CLEAR, LOAD_OP_DONT_CARE = 0, 1, 2
STORE_OP_STORE, STORE_OP_DONT_CARE = 0, 1
VERTEX_SIZE = 20  # two floats of position, three of colour

RESULTS = {
    -1: "out of host memory", -2: "out of device memory", -3: "initialization failed",
    -4: "the device was lost", -6: "a layer is not present", -7: "an extension is not present",
    -8: "a feature is not present", -9: "the driver is incompatible", -11: "the format is not supported",
}

FUNCTIONS = {
    # name: (result, arguments)
    "vkCreateInstance": (c_int32, [c_void_p, c_void_p, POINTER(HANDLE)]),
    "vkDestroyInstance": (None, [HANDLE, c_void_p]),
    "vkEnumeratePhysicalDevices": (c_int32, [HANDLE, POINTER(c_uint32), c_void_p]),
    "vkGetPhysicalDeviceProperties": (None, [HANDLE, c_void_p]),
    "vkGetPhysicalDeviceQueueFamilyProperties": (None, [HANDLE, POINTER(c_uint32), c_void_p]),
    "vkGetPhysicalDeviceMemoryProperties": (None, [HANDLE, c_void_p]),
    "vkCreateDevice": (c_int32, [HANDLE, c_void_p, c_void_p, POINTER(HANDLE)]),
    "vkDestroyDevice": (None, [HANDLE, c_void_p]),
    "vkGetDeviceQueue": (None, [HANDLE, c_uint32, c_uint32, POINTER(HANDLE)]),
    "vkDeviceWaitIdle": (c_int32, [HANDLE]),
    "vkCreateImage": (c_int32, [HANDLE, c_void_p, c_void_p, POINTER(OBJECT)]),
    "vkDestroyImage": (None, [HANDLE, OBJECT, c_void_p]),
    "vkGetImageMemoryRequirements": (None, [HANDLE, OBJECT, c_void_p]),
    "vkAllocateMemory": (c_int32, [HANDLE, c_void_p, c_void_p, POINTER(OBJECT)]),
    "vkFreeMemory": (None, [HANDLE, OBJECT, c_void_p]),
    "vkBindImageMemory": (c_int32, [HANDLE, OBJECT, OBJECT, c_uint64]),
    "vkCreateImageView": (c_int32, [HANDLE, c_void_p, c_void_p, POINTER(OBJECT)]),
    "vkDestroyImageView": (None, [HANDLE, OBJECT, c_void_p]),
    "vkCreateBuffer": (c_int32, [HANDLE, c_void_p, c_void_p, POINTER(OBJECT)]),
    "vkDestroyBuffer": (None, [HANDLE, OBJECT, c_void_p]),
    "vkGetBufferMemoryRequirements": (None, [HANDLE, OBJECT, c_void_p]),
    "vkBindBufferMemory": (c_int32, [HANDLE, OBJECT, OBJECT, c_uint64]),
    "vkMapMemory": (c_int32, [HANDLE, OBJECT, c_uint64, c_uint64, c_uint32, POINTER(c_void_p)]),
    "vkUnmapMemory": (None, [HANDLE, OBJECT]),
    "vkCreateRenderPass": (c_int32, [HANDLE, c_void_p, c_void_p, POINTER(OBJECT)]),
    "vkDestroyRenderPass": (None, [HANDLE, OBJECT, c_void_p]),
    "vkCreateFramebuffer": (c_int32, [HANDLE, c_void_p, c_void_p, POINTER(OBJECT)]),
    "vkDestroyFramebuffer": (None, [HANDLE, OBJECT, c_void_p]),
    "vkCreateShaderModule": (c_int32, [HANDLE, c_void_p, c_void_p, POINTER(OBJECT)]),
    "vkDestroyShaderModule": (None, [HANDLE, OBJECT, c_void_p]),
    "vkCreatePipelineLayout": (c_int32, [HANDLE, c_void_p, c_void_p, POINTER(OBJECT)]),
    "vkDestroyPipelineLayout": (None, [HANDLE, OBJECT, c_void_p]),
    "vkCreateGraphicsPipelines": (c_int32, [HANDLE, OBJECT, c_uint32, c_void_p, c_void_p, POINTER(OBJECT)]),
    "vkDestroyPipeline": (None, [HANDLE, OBJECT, c_void_p]),
    "vkCreateCommandPool": (c_int32, [HANDLE, c_void_p, c_void_p, POINTER(OBJECT)]),
    "vkDestroyCommandPool": (None, [HANDLE, OBJECT, c_void_p]),
    "vkAllocateCommandBuffers": (c_int32, [HANDLE, c_void_p, POINTER(HANDLE)]),
    "vkFreeCommandBuffers": (None, [HANDLE, OBJECT, c_uint32, POINTER(HANDLE)]),
    "vkBeginCommandBuffer": (c_int32, [HANDLE, c_void_p]),
    "vkEndCommandBuffer": (c_int32, [HANDLE]),
    "vkCmdBeginRenderPass": (None, [HANDLE, c_void_p, c_uint32]),
    "vkCmdEndRenderPass": (None, [HANDLE]),
    "vkCmdBindPipeline": (None, [HANDLE, c_uint32, OBJECT]),
    "vkCmdBindVertexBuffers": (None, [HANDLE, c_uint32, c_uint32, POINTER(OBJECT), POINTER(c_uint64)]),
    "vkCmdDraw": (None, [HANDLE, c_uint32, c_uint32, c_uint32, c_uint32]),
    "vkCmdCopyImageToBuffer": (None, [HANDLE, OBJECT, c_uint32, OBJECT, c_uint32, c_void_p]),
    "vkQueueSubmit": (c_int32, [HANDLE, c_uint32, c_void_p, OBJECT]),
    "vkQueueWaitIdle": (c_int32, [HANDLE]),
}


def load():
    """The Vulkan loader, with every function this module calls given its C types."""
    try:
        if sys.platform == "win32":
            lib = ctypes.WinDLL("vulkan-1")
        else:
            lib = ctypes.CDLL("libvulkan.so.1")
    except OSError:
        raise VulkanError("Vulkan isn't installed on this computer") from None
    for name, (result, arguments) in FUNCTIONS.items():
        try:
            function = getattr(lib, name)
        except AttributeError:
            raise VulkanError(f"this computer's Vulkan has no {name}") from None
        function.restype = result
        function.argtypes = arguments
    return lib


# ------------------------------------------------------------------- the card


class Card:
    """One graphics card, ready to draw: an instance, a device, a queue and a command pool."""

    def __init__(self, title="EnglishScript"):
        self.vk = load()
        self.instance = self.device = None
        self.pool = OBJECT(0)
        self.targets = []
        self._title = title.encode("utf-8")
        try:
            self._open()
        except Exception:
            self.close()
            raise

    def check(self, result, doing):
        if result != 0:
            why = RESULTS.get(result, f"error {result}")
            raise VulkanError(f"Vulkan could not {doing}: {why}")

    def _open(self):
        vk = self.vk
        app = VkApplicationInfo(ST_APPLICATION, None, self._title, 1, b"EnglishScript", 1, 1 << 22)
        info = VkInstanceCreateInfo(ST_INSTANCE, None, 0, pointer(app), 0, None, 0, None)
        instance = HANDLE()
        self.check(vk.vkCreateInstance(byref(info), None, byref(instance)), "start")  # vkCreateInstance
        self.instance = instance

        count = c_uint32(0)
        self.check(vk.vkEnumeratePhysicalDevices(instance, byref(count), None), "list the graphics cards")
        if not count.value:
            raise VulkanError("this computer has no graphics card that Vulkan can use")
        cards = (HANDLE * count.value)()
        self.check(vk.vkEnumeratePhysicalDevices(instance, byref(count), cards), "list the graphics cards")
        best = None
        for index in range(count.value):
            card = HANDLE(cards[index])
            props = VkPhysicalDeviceProperties()
            vk.vkGetPhysicalDeviceProperties(card, byref(props))
            name = props.deviceName.decode("utf-8", "replace")
            family = self._graphics_family(card)
            if family is None:
                continue
            # A real card first, then one built into the processor, then software.
            rank = {2: 0, 1: 1, 3: 2, 0: 3, 4: 4}.get(props.deviceType, 5)
            if best is None or rank < best[0]:
                best = (rank, card, name, family)
        if best is None:
            raise VulkanError("no graphics card here can draw")
        _, self.physical, self.name, self.family = best

        priority = c_float(1.0)
        queue_info = VkDeviceQueueCreateInfo(ST_QUEUE, None, 0, self.family, 1, pointer(priority))
        device_info = VkDeviceCreateInfo(ST_DEVICE, None, 0, 1, pointer(queue_info), 0, None, 0, None, None)
        device = HANDLE()
        self.check(vk.vkCreateDevice(self.physical, byref(device_info), None, byref(device)),
                   "open the graphics card")  # vkCreateDevice
        self.device = device
        self.queue = HANDLE()
        vk.vkGetDeviceQueue(device, self.family, 0, byref(self.queue))
        self.memory = VkPhysicalDeviceMemoryProperties()
        vk.vkGetPhysicalDeviceMemoryProperties(self.physical, byref(self.memory))
        pool_info = VkCommandPoolCreateInfo(ST_POOL, None, 0, self.family)
        self.check(vk.vkCreateCommandPool(device, byref(pool_info), None, byref(self.pool)), "make a command pool")

    def _graphics_family(self, card):
        vk = self.vk
        count = c_uint32(0)
        vk.vkGetPhysicalDeviceQueueFamilyProperties(card, byref(count), None)
        families = (VkQueueFamilyProperties * count.value)()
        vk.vkGetPhysicalDeviceQueueFamilyProperties(card, byref(count), families)
        for index in range(count.value):
            if families[index].queueFlags & QUEUE_GRAPHICS:
                return index
        return None

    def memory_type(self, allowed, wanted):
        for index in range(self.memory.memoryTypeCount):
            flags = self.memory.memoryTypes[index].propertyFlags
            if allowed & (1 << index) and flags & wanted == wanted:
                return index
        raise VulkanError("the graphics card has no memory of the kind needed")

    def allocate(self, requirements, wanted):
        info = VkMemoryAllocateInfo(ST_ALLOCATE, None, requirements.size,
                                    self.memory_type(requirements.memoryTypeBits, wanted))
        memory = OBJECT(0)
        self.check(self.vk.vkAllocateMemory(self.device, byref(info), None, byref(memory)), "set memory aside")
        return memory

    def buffer(self, size, usage):
        """A buffer the processor can read and write. Returns (buffer, memory)."""
        vk = self.vk
        info = VkBufferCreateInfo(ST_BUFFER, None, 0, size, usage, 0, 0, None)
        buffer = OBJECT(0)
        self.check(vk.vkCreateBuffer(self.device, byref(info), None, byref(buffer)), "make a buffer")
        needs = VkMemoryRequirements()
        vk.vkGetBufferMemoryRequirements(self.device, buffer, byref(needs))
        try:
            memory = self.allocate(needs, MEMORY_HOST_VISIBLE | MEMORY_HOST_COHERENT)
        except VulkanError:
            vk.vkDestroyBuffer(self.device, buffer, None)
            raise
        self.check(vk.vkBindBufferMemory(self.device, buffer, memory, 0), "attach memory to a buffer")
        return buffer, memory

    def free_buffer(self, buffer, memory):
        self.vk.vkDestroyBuffer(self.device, buffer, None)
        self.vk.vkFreeMemory(self.device, memory, None)

    def run(self, record):
        """Record commands with `record(command_buffer)`, hand them to the card, and wait for it."""
        vk = self.vk
        info = VkCommandBufferAllocateInfo(ST_COMMAND_BUFFERS, None, self.pool, 0, 1)
        commands = HANDLE()
        self.check(vk.vkAllocateCommandBuffers(self.device, byref(info), byref(commands)), "make a command buffer")
        try:
            begin = VkCommandBufferBeginInfo(ST_BEGIN, None, 0x1, None)  # used once
            self.check(vk.vkBeginCommandBuffer(commands, byref(begin)), "begin recording commands")
            record(commands)
            self.check(vk.vkEndCommandBuffer(commands), "finish recording commands")
            submit = VkSubmitInfo(ST_SUBMIT, None, 0, None, None, 1, pointer(commands), 0, None)
            self.check(vk.vkQueueSubmit(self.queue, 1, byref(submit), 0), "send commands to the card")
            self.check(vk.vkQueueWaitIdle(self.queue), "wait for the card")
        finally:
            vk.vkFreeCommandBuffers(self.device, self.pool, 1, byref(commands))

    def target(self, width, height):
        target = Target(self, width, height)
        self.targets.append(target)
        return target

    def close(self):
        """Give everything back. Safe to call twice, and after a failed start."""
        vk = self.vk
        if self.device is not None:
            vk.vkDeviceWaitIdle(self.device)
            for target in self.targets:
                target.close()
            self.targets = []
            if self.pool.value:
                vk.vkDestroyCommandPool(self.device, self.pool, None)
                self.pool = OBJECT(0)
            vk.vkDestroyDevice(self.device, None)
            self.device = None
        if self.instance is not None:
            vk.vkDestroyInstance(self.instance, None)
            self.instance = None


# ---------------------------------------------------------------- the picture


class Target:
    """An off-screen picture on the card, with everything needed to draw triangles into it."""

    def __init__(self, card, width, height):
        self.card, self.width, self.height = card, width, height
        self.image = self.memory = self.view = OBJECT(0)
        self.clear_pass = self.keep_pass = self.framebuffer = OBJECT(0)
        self.layout = self.pipeline = OBJECT(0)
        self.shaders = []
        self.drawn = False
        try:
            self._image()
            self.clear_pass = self._render_pass(LOAD_OP_CLEAR, LAYOUT_UNDEFINED)
            self.keep_pass = self._render_pass(LOAD_OP_LOAD, LAYOUT_TRANSFER_SRC)
            self._framebuffer()
            self._pipeline()
        except Exception:
            self.close()
            raise

    def _image(self):
        card, vk = self.card, self.card.vk
        info = VkImageCreateInfo(
            ST_IMAGE, None, 0, 1, FORMAT_RGBA8, VkExtent3D(self.width, self.height, 1), 1, 1, 1, 0,
            IMAGE_USAGE_COLOR | IMAGE_USAGE_TRANSFER_SRC, 0, 0, None, LAYOUT_UNDEFINED)
        image = OBJECT(0)
        card.check(vk.vkCreateImage(card.device, byref(info), None, byref(image)), "make a picture")  # vkCreateImage
        self.image = image
        needs = VkMemoryRequirements()
        vk.vkGetImageMemoryRequirements(card.device, image, byref(needs))
        try:
            self.memory = card.allocate(needs, MEMORY_DEVICE_LOCAL)
        except VulkanError:
            self.memory = card.allocate(needs, 0)
        card.check(vk.vkBindImageMemory(card.device, image, self.memory, 0), "attach memory to a picture")
        view_info = VkImageViewCreateInfo(
            ST_IMAGE_VIEW, None, 0, image, 1, FORMAT_RGBA8, VkComponentMapping(0, 0, 0, 0),
            VkImageSubresourceRange(0x1, 0, 1, 0, 1))
        view = OBJECT(0)
        card.check(vk.vkCreateImageView(card.device, byref(view_info), None, byref(view)), "make a view of a picture")
        self.view = view

    def _render_pass(self, load, start):
        card, vk = self.card, self.card.vk
        attachment = VkAttachmentDescription(
            0, FORMAT_RGBA8, 1, load, STORE_OP_STORE, LOAD_OP_DONT_CARE, STORE_OP_DONT_CARE,
            start, LAYOUT_TRANSFER_SRC)
        colour = VkAttachmentReference(0, LAYOUT_COLOR)
        subpass = VkSubpassDescription(0, 0, 0, None, 1, pointer(colour), None, None, 0, None)
        info = VkRenderPassCreateInfo(ST_RENDER_PASS, None, 0, 1, pointer(attachment), 1, pointer(subpass), 0, None)
        render_pass = OBJECT(0)
        card.check(vk.vkCreateRenderPass(card.device, byref(info), None, byref(render_pass)),
                   "make a render pass")  # vkCreateRenderPass
        return render_pass

    def _framebuffer(self):
        card, vk = self.card, self.card.vk
        view = OBJECT(self.view.value)
        info = VkFramebufferCreateInfo(
            ST_FRAMEBUFFER, None, 0, self.clear_pass, 1, pointer(view), self.width, self.height, 1)
        framebuffer = OBJECT(0)
        card.check(vk.vkCreateFramebuffer(card.device, byref(info), None, byref(framebuffer)), "make a framebuffer")
        self.framebuffer = framebuffer

    def _shader(self, words):
        card, vk = self.card, self.card.vk
        code = (c_uint32 * len(words))(*words)
        info = VkShaderModuleCreateInfo(ST_SHADER, None, 0, len(words) * 4, code)
        module = OBJECT(0)
        card.check(vk.vkCreateShaderModule(card.device, byref(info), None, byref(module)),
                   "load a shader")  # vkCreateShaderModule
        self.shaders.append(module)
        return module

    def _pipeline(self):
        card, vk = self.card, self.card.vk
        vertex = self._shader(_spirv.vertex_shader())
        fragment = self._shader(_spirv.fragment_shader())
        stages = (VkPipelineShaderStageCreateInfo * 2)(
            VkPipelineShaderStageCreateInfo(ST_STAGE, None, 0, STAGE_VERTEX, vertex, b"main", None),
            VkPipelineShaderStageCreateInfo(ST_STAGE, None, 0, STAGE_FRAGMENT, fragment, b"main", None))
        binding = VkVertexInputBindingDescription(0, VERTEX_SIZE, 0)
        attributes = (VkVertexInputAttributeDescription * 2)(
            VkVertexInputAttributeDescription(0, 0, FORMAT_VEC2, 0),   # position
            VkVertexInputAttributeDescription(1, 0, FORMAT_VEC3, 8))   # colour
        vertex_input = VkPipelineVertexInputStateCreateInfo(
            ST_VERTEX_INPUT, None, 0, 1, pointer(binding), 2, attributes)
        assembly = VkPipelineInputAssemblyStateCreateInfo(ST_INPUT_ASSEMBLY, None, 0, 3, 0)  # a list of triangles
        viewport = VkViewport(0.0, 0.0, float(self.width), float(self.height), 0.0, 1.0)
        scissor = VkRect2D(VkOffset2D(0, 0), VkExtent2D(self.width, self.height))
        viewports = VkPipelineViewportStateCreateInfo(ST_VIEWPORT, None, 0, 1, pointer(viewport), 1, pointer(scissor))
        raster = VkPipelineRasterizationStateCreateInfo(
            ST_RASTER, None, 0, 0, 0, 0, 0, 1, 0, 0.0, 0.0, 0.0, 1.0)  # filled, both faces drawn
        multisample = VkPipelineMultisampleStateCreateInfo(ST_MULTISAMPLE, None, 0, 1, 0, 1.0, None, 0, 0)
        blend_attachment = VkPipelineColorBlendAttachmentState(0, 0, 0, 0, 0, 0, 0, 0xF)
        blend = VkPipelineColorBlendStateCreateInfo(
            ST_BLEND, None, 0, 0, 0, 1, pointer(blend_attachment), (c_float * 4)(0, 0, 0, 0))
        layout_info = VkPipelineLayoutCreateInfo(ST_LAYOUT, None, 0, 0, None, 0, None)
        layout = OBJECT(0)
        card.check(vk.vkCreatePipelineLayout(card.device, byref(layout_info), None, byref(layout)),
                   "make a pipeline layout")
        self.layout = layout
        info = VkGraphicsPipelineCreateInfo(
            ST_PIPELINE, None, 0, 2, stages, pointer(vertex_input), pointer(assembly), None,
            pointer(viewports), pointer(raster), pointer(multisample), None, pointer(blend), None,
            layout, self.clear_pass, 0, 0, -1)
        pipeline = OBJECT(0)
        card.check(vk.vkCreateGraphicsPipelines(card.device, 0, 1, byref(info), None, byref(pipeline)),
                   "build the pipeline")  # vkCreateGraphicsPipelines
        self.pipeline = pipeline

    def draw(self, vertices, clear=(0.0, 0.0, 0.0)):
        """Draw triangles. `vertices` is a list of (x, y, red, green, blue), three per triangle.

        The first draw clears the picture to `clear`; later draws add to it.
        """
        card, vk = self.card, self.card.vk
        if len(vertices) % 3:
            raise VulkanError("a triangle needs three corners")
        data = b"".join(struct.pack("<5f", *corner) for corner in vertices)
        buffer = memory = None
        if data:
            buffer, memory = card.buffer(len(data), BUFFER_USAGE_VERTEX)
        try:
            if data:
                where = c_void_p()
                card.check(vk.vkMapMemory(card.device, memory, 0, len(data), 0, byref(where)), "reach a buffer")
                ctypes.memmove(where, data, len(data))
                vk.vkUnmapMemory(card.device, memory)
            first = not self.drawn
            value = VkClearValue((c_float * 4)(clear[0], clear[1], clear[2], 1.0))
            area = VkRect2D(VkOffset2D(0, 0), VkExtent2D(self.width, self.height))
            begin = VkRenderPassBeginInfo(
                ST_PASS_BEGIN, None, self.clear_pass if first else self.keep_pass, self.framebuffer, area,
                1 if first else 0, pointer(value) if first else None)

            def record(commands):
                vk.vkCmdBeginRenderPass(commands, byref(begin), 0)
                if data:
                    vk.vkCmdBindPipeline(commands, 0, self.pipeline)
                    offset = c_uint64(0)
                    vk.vkCmdBindVertexBuffers(commands, 0, 1, byref(buffer), byref(offset))
                    vk.vkCmdDraw(commands, len(vertices), 1, 0, 0)  # vkCmdDraw
                vk.vkCmdEndRenderPass(commands)
            card.run(record)
            self.drawn = True
        finally:
            if buffer is not None:
                card.free_buffer(buffer, memory)

    def read(self):
        """The picture as RGBA bytes, top row first."""
        card, vk = self.card, self.card.vk
        if not self.drawn:
            self.draw([])  # nothing drawn yet: just clear it, so there is something to read
        size = self.width * self.height * 4
        buffer, memory = card.buffer(size, BUFFER_USAGE_TRANSFER_DST)
        try:
            region = VkBufferImageCopy(
                0, 0, 0, VkImageSubresourceLayers(0x1, 0, 0, 1), VkOffset3D(0, 0, 0),
                VkExtent3D(self.width, self.height, 1))
            card.run(lambda commands: vk.vkCmdCopyImageToBuffer(
                commands, self.image, LAYOUT_TRANSFER_SRC, buffer, 1, byref(region)))  # vkCmdCopyImageToBuffer
            where = c_void_p()
            card.check(vk.vkMapMemory(card.device, memory, 0, size, 0, byref(where)), "reach a buffer")
            pixels = ctypes.string_at(where, size)
            vk.vkUnmapMemory(card.device, memory)
            return pixels
        finally:
            card.free_buffer(buffer, memory)

    def close(self):
        card, vk = self.card, self.card.vk
        device = card.device
        if device is None:
            return
        for destroy, name in (
            (vk.vkDestroyPipeline, "pipeline"), (vk.vkDestroyPipelineLayout, "layout"),
            (vk.vkDestroyFramebuffer, "framebuffer"), (vk.vkDestroyRenderPass, "clear_pass"),
            (vk.vkDestroyRenderPass, "keep_pass"), (vk.vkDestroyImageView, "view"),
            (vk.vkDestroyImage, "image"),
        ):
            handle = getattr(self, name)
            if handle.value:
                destroy(device, handle, None)
                setattr(self, name, OBJECT(0))
        for module in self.shaders:
            vk.vkDestroyShaderModule(device, module, None)
        self.shaders = []
        if self.memory.value:
            vk.vkFreeMemory(device, self.memory, None)
            self.memory = OBJECT(0)


# -------------------------------------------------------------------- saving


def png(width, height, rgba):
    """The bytes of a PNG file holding an RGBA picture."""
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    row = width * 4
    raw = b"".join(b"\0" + rgba[y * row:(y + 1) * row] for y in range(height))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))

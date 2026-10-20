bl_info = {
    "name": "GEM-X 视频动作桥接",
    "author": "GEM Blender Bridge contributors",
    "version": (0, 1, 4),
    "blender": (4, 2, 0),
    "location": "3D 视图 > 侧栏 > GEM-X",
    "description": "选择本地视频，通过独立 GEM-X 服务推理并导入 SOMA 动作",
    "category": "Animation",
}

import bpy
from . import operators, properties, panels


def register():
    properties.register()
    operators.register()
    panels.register()


def unregister():
    operators.stop_workers()
    panels.unregister()
    operators.unregister()
    properties.unregister()

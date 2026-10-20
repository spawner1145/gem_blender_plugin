import bpy
from bpy.props import StringProperty, BoolProperty, IntProperty, EnumProperty, PointerProperty, FloatProperty


class GEM_Settings(bpy.types.PropertyGroup):
    server_url: StringProperty(name="服务地址", default="http://127.0.0.1:6700")
    video_path: StringProperty(name="视频", subtype="FILE_PATH")
    mode: EnumProperty(name="推理模式", items=[("regression", "回归（快速）", "官方单步回归"), ("ddim", "DDIM（50 步）", "关闭图像特征时建议使用")], default="regression")
    image_features: BoolProperty(name="SAM-3D-Body 图像特征", default=True)
    batch_size: IntProperty(name="批大小", default=1, min=1, max=8)
    max_frames: IntProperty(name="最大处理帧数", default=300, min=4, max=1800, description="从视频开头处理到指定帧数")
    target_fps: IntProperty(name="目标帧率", default=30, min=1, max=60)
    max_edge: IntProperty(name="最长边像素", default=720, min=256, max=1920)
    seed: IntProperty(name="随机种子", default=42, min=0)
    postprocess: BoolProperty(name="官方动作后处理", default=True)
    start_frame: IntProperty(name="起始帧", default=0, min=0)
    rotation_degrees: FloatProperty(name="旋转角度（°）", default=180., soft_min=-180., soft_max=180.,
        description="整段动作绕世界原点的 Z 轴额外旋转，保留原始侧向和转身；180° 翻转 X/Y，0° 保留原始朝向")
    status: StringProperty(default="未连接", options={"SKIP_SAVE"})
    error: StringProperty(default="", options={"SKIP_SAVE"})
    job_id: StringProperty(default="", options={"SKIP_SAVE"})
    busy: BoolProperty(default=False, options={"SKIP_SAVE"})
    progress: FloatProperty(default=0, min=0, max=1, subtype="FACTOR", options={"SKIP_SAVE"})


def register():
    bpy.utils.register_class(GEM_Settings)
    bpy.types.Scene.gem_x_bridge = PointerProperty(type=GEM_Settings)


def unregister():
    del bpy.types.Scene.gem_x_bridge
    bpy.utils.unregister_class(GEM_Settings)

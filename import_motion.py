"""Import exact joint world transforms; no optional BVH addon is needed."""
import json
import math
from pathlib import Path
import bpy
from mathutils import Matrix, Vector


def heading_alignment(names, rest, frames, mode):
    """One rigid yaw for the whole clip; leave the bind pose and later turns intact."""
    if mode == "ORIGINAL":
        return Matrix.Identity(4), 0.0
    if mode != "FRONT":
        raise ValueError("未知的起始朝向模式")
    if "Hips" not in names:
        return Matrix.Identity(4), 0.0
    hip = names.index("Hips")
    # Joint matrices include SOMA's joint orient; remove the bind rotation
    # before using its anatomical +Z forward vector.
    delta = Matrix(frames[0][hip]).to_quaternion() @ Matrix(rest[hip]).to_quaternion().inverted()
    forward = delta @ Vector((0, 0, 1))
    if math.hypot(forward.x, forward.z) < 1e-5:
        # A vertical pelvis has no horizontal heading. Try the shoulder line.
        if not all(n in names for n in ("LeftShoulder", "RightShoulder")):
            return Matrix.Identity(4), 0.0
        left = Matrix(frames[0][names.index("LeftShoulder")]).translation
        right = Matrix(frames[0][names.index("RightShoulder")]).translation
        forward = (left - right).cross(Vector((0, 1, 0)))
        if math.hypot(forward.x, forward.z) < 1e-5:
            return Matrix.Identity(4), 0.0
    angle = -math.atan2(forward.x, forward.z)
    pivot = Matrix(frames[0][hip]).translation
    pivot.y = 0
    align = Matrix.Translation(pivot) @ Matrix.Rotation(angle, 4, "Y") @ Matrix.Translation(-pivot)
    return align, angle


def import_motion(filepath, context, start_frame=1, heading="FRONT"):
    motion = json.loads(Path(filepath).read_text("utf-8"))
    if motion.get("schema") != "gem-soma-motion-v1" or motion.get("unit") != "meters" or motion.get("up_axis") != "Y":
        raise ValueError("不支持的 GEM 动作格式")
    names, parents = motion["names"], motion["parents"]
    rest, frames = motion["rest_world"], motion["pose_world"]
    fps = float(motion["fps"])
    count = len(names)
    if not 1 <= count <= 256 or len(set(names)) != count or not frames or len(frames) > 1800:
        raise ValueError("骨架或动作数据无效")
    if len(rest) != count or len(parents) != count or parents[0] != -1:
        raise ValueError("骨架层级无效")
    if not math.isfinite(fps) or fps <= 0 or fps > 240:
        raise ValueError("帧率无效")
    for j in range(1, count):
        if not 0 <= parents[j] < j:
            raise ValueError("骨骼必须按父级优先顺序排列")
    for frame in [rest, *frames]:
        if len(frame) != count:
            raise ValueError("帧与骨骼数量不一致")
        for mat in frame:
            if len(mat) != 4 or any(len(row) != 4 or any(not math.isfinite(x) for x in row) for row in mat):
                raise ValueError("动作矩阵无效")
    # SOMA Y-up -> Blender Z-up, proper rotation (no reflection).
    convert = Matrix.Rotation(math.pi / 2, 4, "X")
    inverse = convert.inverted()
    alignment, heading_angle = heading_alignment(names, rest, frames, heading)
    rest_m = [convert @ Matrix(mat) @ inverse for mat in rest]
    rest_inv = [mat.inverted() for mat in rest_m]
    children = [[] for _ in names]
    for j, p in enumerate(parents):
        if p >= 0:
            children[p].append(j)
    scene = context.scene
    old_frame = scene.frame_current
    old_active = context.view_layer.objects.active
    old_selected = list(context.selected_objects)
    if context.object and context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    arm = bpy.data.armatures.new("GEM_SOMA")
    obj = bpy.data.objects.new("GEM_Video_Motion", arm)
    collection = bpy.data.collections.get("GEM Results")
    if collection is None:
        collection = bpy.data.collections.new("GEM Results")
        scene.collection.children.link(collection)
    collection.objects.link(obj)
    try:
        for item in context.selected_objects:
            item.select_set(False)
        obj.select_set(True)
        context.view_layer.objects.active = obj
        obj.show_in_front = True
        bpy.ops.object.mode_set(mode="EDIT")
        for j, name in enumerate(names):
            bone = arm.edit_bones.new(name)
            head = rest_m[j].translation
            candidates = [rest_m[c].translation - head for c in children[j]]
            direction = max(candidates, key=lambda v: v.length) if candidates else Vector((0, .035, 0))
            if direction.length < 0.005:
                direction = Vector((0, .035, 0))
            bone.head, bone.tail = head, head + direction
            if parents[j] >= 0:
                bone.parent = arm.edit_bones[names[parents[j]]]
            bone.use_connect = False
        bpy.ops.object.mode_set(mode="OBJECT")
        base_m = [arm.bones[name].matrix_local.copy() for name in names]
        for pb in obj.pose.bones:
            pb.rotation_mode = "QUATERNION"
        scene_fps = scene.render.fps / scene.render.fps_base
        prev_quats = [None] * count
        for index, matrices in enumerate(frames):
            frame = start_frame + index * scene_fps / fps
            targets = [(convert @ alignment @ Matrix(mat) @ inverse) @ rest_inv[j] @ base_m[j] for j, mat in enumerate(matrices)]
            for j, name in enumerate(names):
                pb = obj.pose.bones[name]
                kwargs = {"parent_matrix": targets[parents[j]], "parent_matrix_local": base_m[parents[j]]} if parents[j] >= 0 else {}
                basis = arm.bones[name].convert_local_to_pose(targets[j], base_m[j], invert=True, **kwargs)
                location, quat, scale = basis.decompose()
                if prev_quats[j] is not None and quat.dot(prev_quats[j]) < 0:
                    quat.negate()
                prev_quats[j] = quat.copy()
                pb.location, pb.rotation_quaternion, pb.scale = location, quat, scale
                pb.keyframe_insert("location", frame=frame, group=name)
                pb.keyframe_insert("rotation_quaternion", frame=frame, group=name)
                pb.keyframe_insert("scale", frame=frame, group=name)
        action = obj.animation_data.action
        action.name = "GEM_Video_Action"
        curves = []
        if hasattr(action, "fcurves"):
            curves = list(action.fcurves)
        else:
            for layer in action.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        curves.extend(bag.fcurves)
        for curve in curves:
            for key in curve.keyframe_points:
                key.interpolation = "LINEAR"
        scene.frame_end = max(scene.frame_end, math.ceil(start_frame + (len(frames) - 1) * scene_fps / fps))
        obj["gem_source_fps"] = fps
        obj["gem_timeline_fps"] = scene_fps
        obj["gem_start_frame"] = start_frame
        obj["gem_frames"] = len(frames)
        obj["gem_heading_mode"] = heading
        obj["gem_heading_degrees"] = math.degrees(heading_angle)
        scene.frame_set(start_frame)
        return obj
    except Exception:
        if obj.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.armatures.remove(arm)
        scene.frame_set(old_frame)
        for item in old_selected:
            item.select_set(True)
        context.view_layer.objects.active = old_active
        raise

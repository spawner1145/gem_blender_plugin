"""Run with Blender --background --factory-startup --python-exit-code 1 --python ..."""
import json
import math
from pathlib import Path
import sys
import tempfile
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import gem_blender_plugin
from gem_blender_plugin.import_motion import import_motion

gem_blender_plugin.register()
rest = [Matrix.Identity(4), Matrix.Translation((0, 1, 0)) @ Matrix.Rotation(.3, 4, "Y"),
        Matrix.Translation((.4, 1.5, 0)) @ Matrix.Rotation(-.6, 4, "X")]
frames = []
for i in range(4):
    transform = Matrix.Translation((i * .15, .2, .3)) @ Matrix.Rotation(i * .2, 4, "Z")
    frames.append([transform @ mat for mat in rest])
motion = {"schema": "gem-soma-motion-v1", "unit": "meters", "up_axis": "Y", "fps": 29.97,
          "frames": 4, "names": ["Root", "Spine", "Hand"], "parents": [-1, 0, 1],
          "rest_world": [list(map(list, mat)) for mat in rest],
          "pose_world": [[list(map(list, mat)) for mat in frame] for frame in frames]}
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "motion.json"
    path.write_text(json.dumps(motion), "utf-8")
    bpy.context.scene.render.fps = 60
    bpy.context.scene.render.fps_base = 1.001
    original_fps = (bpy.context.scene.render.fps, bpy.context.scene.render.fps_base)
    obj = import_motion(path, bpy.context, heading="ORIGINAL")
    assert (bpy.context.scene.render.fps, bpy.context.scene.render.fps_base) == original_fps
    convert = Matrix.Rotation(math.pi / 2, 4, "X")
    error = 0.
    for i, frame in enumerate(frames):
        frame_number = 1 + i * (original_fps[0] / original_fps[1]) / motion["fps"]
        bpy.context.scene.frame_set(math.floor(frame_number), subframe=frame_number % 1)
        bpy.context.view_layer.update()
        for j, mat in enumerate(frame):
            pb = obj.pose.bones[motion["names"][j]]
            error = max(error, (pb.matrix.translation - convert @ mat.translation).length)
            target = convert @ mat @ rest[j].inverted() @ convert.inverted() @ obj.data.bones[pb.name].matrix_local
            error = max(error, max(abs(pb.matrix[r][c] - target[r][c]) for r in range(4) for c in range(4)))
    assert error < 1e-4, error
    assert len(obj.pose.bones) == 3
    print("GEM_BLENDER_IMPORT_OK max_matrix_error=", error)
    motion["fps"] = 12.5
    path.write_text(json.dumps(motion), "utf-8")
    bpy.context.scene.render.fps = 60
    bpy.context.scene.render.fps_base = 1.
    low_fps_obj = import_motion(path, bpy.context, start_frame=10, heading="ORIGINAL")
    assert bpy.context.scene.render.fps == 60 and bpy.context.scene.render.fps_base == 1.
    expected_end = 10 + (len(frames) - 1) * 60 / 12.5
    assert abs(low_fps_obj.animation_data.action.frame_range[1] - expected_end) < 1e-4
    assert abs((expected_end - 10) / 60 - (len(frames) - 1) / 12.5) < 1e-6
    print("GEM_PRESERVES_60_FPS_AND_DURATION_OK", list(low_fps_obj.animation_data.action.frame_range))

    # A backwards clip with nontrivial SOMA joint-orient. Correct only the
    # initial yaw, retain its first position and subsequent turns/trajectory.
    names = ["Root", "Hips", "Head", "LeftEye", "RightEye"]
    rest = [Matrix.Identity(4), Matrix.Rotation(.8, 4, "Z"),
            Matrix.Translation((0, .6, 0)), Matrix.Translation((.03, .65, .1)),
            Matrix.Translation((-.03, .65, .1))]
    motion.update(names=names, parents=[-1, 0, 1, 2, 2], fps=30,
                  rest_world=[list(map(list, mat)) for mat in rest])
    frames = [[Matrix.Translation((2 + i * .1, 1, 3)) @ Matrix.Rotation(math.pi + i * .2, 4, "Y") @ mat
               for mat in rest] for i in range(4)]
    motion['pose_world'] = [[list(map(list, mat)) for mat in frame] for frame in frames]
    path.write_text(json.dumps(motion), 'utf-8')
    obj = import_motion(path, bpy.context)
    aligned_rest = [b.matrix_local.copy() for b in obj.data.bones]
    pivot = Vector((2, 0, 3))
    align = Matrix.Translation(pivot) @ Matrix.Rotation(math.pi, 4, "Y") @ Matrix.Translation(-pivot)
    for i, frame in enumerate(frames):
        bpy.context.scene.frame_set(1 + i * 2)
        bpy.context.view_layer.update()
        for j, name in enumerate(names):
            got = obj.pose.bones[name].matrix.translation
            expected = convert @ align @ frame[j].translation
            assert (got - expected).length < 1e-4, (name, got, expected)
        face = ((obj.pose.bones['LeftEye'].head + obj.pose.bones['RightEye'].head) / 2
                - obj.pose.bones['Head'].head).normalized()
        expected_forward = (convert.to_3x3() @ Matrix.Rotation(i * .2, 3, 'Y') @ Vector((0, 0, 1))).normalized()
        face.z = 0
        assert face.normalized().dot(expected_forward) > .9999
    original = import_motion(path, bpy.context, heading='ORIGINAL')
    assert all(max(abs(a[r][c] - b.matrix_local[r][c]) for r in range(4) for c in range(4)) < 1e-5
               for a, b in zip(aligned_rest, original.data.bones))
    assert (obj.pose.bones['Hips'].head - original.pose.bones['Hips'].head).length < 1e-4
    assert bpy.context.scene.render.fps == 60
    print('GEM_HEADING_FRONT_TURNS_TRANSLATION_BIND_POSE_OK')
gem_blender_plugin.unregister()

if "--" in sys.argv:
    actual_path = Path(sys.argv[sys.argv.index("--") + 1])
    actual = json.loads(actual_path.read_text("utf-8"))
    obj = import_motion(actual_path, bpy.context, heading="ORIGINAL")
    convert = Matrix.Rotation(math.pi / 2, 4, "X")
    error = 0.
    for i, frame in enumerate(actual["pose_world"]):
        frame_number = 1 + i * (bpy.context.scene.render.fps / bpy.context.scene.render.fps_base) / actual["fps"]
        bpy.context.scene.frame_set(math.floor(frame_number), subframe=frame_number % 1)
        bpy.context.view_layer.update()
        for j, mat in enumerate(frame):
            got = obj.pose.bones[actual["names"][j]].matrix.translation
            expected = convert @ Matrix(mat).translation
            error = max(error, (got - expected).length)
    assert error < 1e-4, error
    print("GEM_ACTUAL_IMPORT_OK", len(actual["names"]), len(actual["pose_world"]), "max_joint_error_m=", error)
    obj = import_motion(actual_path, bpy.context)
    bpy.context.scene.frame_set(1)
    left = obj.pose.bones['LeftLeg'].head
    right = obj.pose.bones['RightLeg'].head
    forward = (left - right).cross(Vector((0, 0, 1))).normalized()
    forward.z = 0
    assert forward.normalized().dot(Vector((0, -1, 0))) > .99, list(forward)
    print('GEM_ACTUAL_START_FACING_MINUS_Y_OK', list(forward), obj['gem_heading_degrees'])

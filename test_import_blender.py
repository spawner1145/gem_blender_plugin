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
    assert bpy.context.scene.gem_x_bridge.rotation_degrees == 180.
    assert bpy.context.scene.gem_x_bridge.start_frame == 0
    obj = import_motion(path, bpy.context, rotation_degrees=0)
    assert (bpy.context.scene.render.fps, bpy.context.scene.render.fps_base) == original_fps
    convert = Matrix.Rotation(math.pi / 2, 4, "X")
    error = 0.
    for i, frame in enumerate(frames):
        frame_number = i * (original_fps[0] / original_fps[1]) / motion["fps"]
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
    low_fps_obj = import_motion(path, bpy.context, start_frame=10, rotation_degrees=0)
    assert bpy.context.scene.render.fps == 60 and bpy.context.scene.render.fps_base == 1.
    expected_end = 10 + (len(frames) - 1) * 60 / 12.5
    assert abs(low_fps_obj.animation_data.action.frame_range[1] - expected_end) < 1e-4
    assert abs((expected_end - 10) / 60 - (len(frames) - 1) / 12.5) < 1e-6
    print("GEM_PRESERVES_60_FPS_AND_DURATION_OK", list(low_fps_obj.animation_data.action.frame_range))

    # Different initial body headings receive exactly the same configured yaw.
    # Verify full matrices, trajectory, side-facing poses and later turns.
    names = ["Root", "Hips", "Head", "LeftEye", "RightEye"]
    rest = [Matrix.Identity(4), Matrix.Rotation(.8, 4, "Z"),
            Matrix.Translation((0, .6, 0)), Matrix.Translation((.03, .65, .1)),
            Matrix.Translation((-.03, .65, .1))]
    motion.update(names=names, parents=[-1, 0, 1, 2, 2], fps=30,
                  rest_world=[list(map(list, mat)) for mat in rest])
    fixed_error = 0.
    bind_reference = None
    for initial in (0., math.pi / 2, -math.pi / 2, math.pi):
        frames = [[Matrix.Translation((2 + i * .1, 1, 3 + i * .05)) @ Matrix.Rotation(initial + i * .2, 4, "Y") @ mat
                   for mat in rest] for i in range(4)]
        motion['pose_world'] = [[list(map(list, mat)) for mat in frame] for frame in frames]
        path.write_text(json.dumps(motion), 'utf-8')
        for degrees in (0., 90., -90., 180.):
            obj = import_motion(path, bpy.context, rotation_degrees=degrees)
            yaw = Matrix.Rotation(math.radians(degrees), 4, 'Z')
            if bind_reference is None:
                bind_reference = [obj.data.bones[n].matrix_local.copy() for n in names]
            for j, name in enumerate(names):
                bind = obj.data.bones[name].matrix_local
                assert max(abs(bind_reference[j][r][c] - bind[r][c]) for r in range(4) for c in range(4)) < 1e-5
            for i, frame in enumerate(frames):
                bpy.context.scene.frame_set(i * 2)
                bpy.context.view_layer.update()
                for j, name in enumerate(names):
                    expected = yaw @ convert @ frame[j] @ rest[j].inverted() @ convert.inverted() @ obj.data.bones[name].matrix_local
                    got = obj.pose.bones[name].matrix
                    fixed_error = max(fixed_error, max(abs(got[r][c] - expected[r][c]) for r in range(4) for c in range(4)))
                face = (obj.pose.bones['LeftEye'].head + obj.pose.bones['RightEye'].head) / 2 - obj.pose.bones['Head'].head
                face.z = 0
                expected_forward = yaw.to_3x3() @ convert.to_3x3() @ Matrix.Rotation(initial + i * .2, 3, 'Y') @ Vector((0, 0, 1))
                assert face.normalized().dot(expected_forward.normalized()) > .9999
            assert obj['gem_rotation_degrees'] == degrees
        default = import_motion(path, bpy.context)
        assert default['gem_rotation_degrees'] == 180.
        for name in names:
            got = default.pose.bones[name].head
            expected = Matrix.Rotation(math.pi, 4, 'Z') @ convert @ frames[0][names.index(name)].translation
            assert (got - expected).length < 1e-4
    assert fixed_error < 1e-4, fixed_error
    for invalid in (float('nan'), float('inf')):
        before_objects = len(bpy.data.objects)
        try:
            import_motion(path, bpy.context, rotation_degrees=invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('Invalid rotation accepted')
        assert len(bpy.data.objects) == before_objects
    assert bpy.context.scene.render.fps == 60
    print('GEM_FIXED_ROTATION_SIDEWAYS_TURNS_TRANSLATION_BIND_POSE_OK', fixed_error)
gem_blender_plugin.unregister()

if "--" in sys.argv:
    actual_path = Path(sys.argv[sys.argv.index("--") + 1])
    actual = json.loads(actual_path.read_text("utf-8"))
    obj = import_motion(actual_path, bpy.context, rotation_degrees=0)
    convert = Matrix.Rotation(math.pi / 2, 4, "X")
    error = 0.
    for i, frame in enumerate(actual["pose_world"]):
        frame_number = i * (bpy.context.scene.render.fps / bpy.context.scene.render.fps_base) / actual["fps"]
        bpy.context.scene.frame_set(math.floor(frame_number), subframe=frame_number % 1)
        bpy.context.view_layer.update()
        for j, mat in enumerate(frame):
            got = obj.pose.bones[actual["names"][j]].matrix.translation
            expected = convert @ Matrix(mat).translation
            error = max(error, (got - expected).length)
    assert error < 1e-4, error
    print("GEM_ACTUAL_IMPORT_OK", len(actual["names"]), len(actual["pose_world"]), "max_joint_error_m=", error)
    obj = import_motion(actual_path, bpy.context)
    yaw = Matrix.Rotation(math.pi, 4, 'Z')
    error = 0.
    for i, frame in enumerate(actual['pose_world']):
        frame_number = i * (bpy.context.scene.render.fps / bpy.context.scene.render.fps_base) / actual['fps']
        bpy.context.scene.frame_set(math.floor(frame_number), subframe=frame_number % 1)
        bpy.context.view_layer.update()
        for j, mat in enumerate(frame):
            got = obj.pose.bones[actual['names'][j]].matrix.translation
            expected = yaw @ convert @ Matrix(mat).translation
            error = max(error, (got - expected).length)
    assert error < 1e-4, error
    print('GEM_ACTUAL_FIXED_180_ROTATION_OK', obj['gem_rotation_degrees'], 'max_joint_error_m=', error)

import os
from pathlib import Path
import queue
import tempfile
import threading
import uuid
import webbrowser

import bpy
from bpy.props import StringProperty
from bpy_extras.io_utils import ImportHelper
from .api_client import Client, Cancelled
from .import_motion import import_motion

_workers = {}
_registered = False


def worker(url, video, options, events, cancel):
    job_id = None
    client = None
    try:
        client = Client(url)
        events.put(("status", "上传视频", 0.))
        job = client.upload(video, options, cancel, lambda value: events.put(("status", "上传视频", value)))
        job_id = job["id"]
        events.put(("job", job_id))
        while True:
            if cancel.is_set():
                client.request("POST", f"/v1/jobs/{job_id}/cancel")
                raise Cancelled()
            job = client.request("GET", f"/v1/jobs/{job_id}")
            if job["status"] == "succeeded":
                folder = Path(tempfile.gettempdir()) / "gem_blender_bridge" / job_id
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / "motion.json"
                client.download_motion(job_id, path)
                if cancel.is_set():
                    raise Cancelled()
                events.put(("done", str(path)))
                return
            if job["status"] == "failed":
                raise RuntimeError(job.get("error") or "服务端推理失败")
            if job["status"] == "cancelled":
                raise Cancelled()
            events.put(("status", job.get("stage", job["status"]), job.get("progress", 0.)))
            cancel.wait(1.5)
    except Cancelled:
        events.put(("cancelled",))
    except Exception as exc:
        events.put(("error", str(exc)))


class GEM_OT_choose_video(bpy.types.Operator, ImportHelper):
    bl_idname = "gem_x.choose_video"
    bl_label = "选择视频"
    filename_ext = ".mp4"
    filter_glob: StringProperty(default="*.mp4;*.mov;*.mkv;*.avi;*.webm;*.m4v;*.gif", options={"HIDDEN"})

    def execute(self, context):
        context.scene.gem_x_bridge.video_path = self.filepath
        return {"FINISHED"}


class GEM_OT_generate(bpy.types.Operator):
    bl_idname = "gem_x.generate"
    bl_label = "视频推理并导入动作"
    bl_description = "上传所选视频至 GEM-X 服务，完成后创建新的 SOMA 动作骨架"

    @classmethod
    def poll(cls, context):
        return context.scene is not None and not context.scene.gem_x_bridge.busy

    def execute(self, context):
        props = context.scene.gem_x_bridge
        video = bpy.path.abspath(props.video_path)
        if not os.path.isfile(video):
            self.report({"ERROR"}, "请先选择有效的视频文件")
            return {"CANCELLED"}
        keys = ("mode", "image_features", "batch_size", "max_frames", "target_fps", "max_edge", "seed", "postprocess")
        options = {key: getattr(props, key) for key in keys}
        self._events, self._cancel = queue.Queue(), threading.Event()
        self._key = uuid.uuid4().hex
        self._scene = context.scene
        self._start = props.start_frame
        self._heading = props.heading
        _workers[self._key] = (self._cancel, context.scene.as_pointer())
        props.busy, props.error, props.job_id = True, "", ""
        props.status, props.progress = "准备上传", 0.
        threading.Thread(target=worker, args=(props.server_url, video, options, self._events, self._cancel), daemon=True).start()
        self._timer = context.window_manager.event_timer_add(.25, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def finish(self, context):
        context.window_manager.event_timer_remove(self._timer)
        _workers.pop(self._key, None)
        if _registered and self._scene.name in bpy.data.scenes:
            self._scene.gem_x_bridge.busy = False
        for area in context.screen.areas:
            area.tag_redraw()

    def modal(self, context, event):
        if not _registered or self._scene.name not in bpy.data.scenes:
            self._cancel.set()
            self.finish(context)
            return {"CANCELLED"}
        if event.type == "ESC":
            self._cancel.set()
        if event.type != "TIMER":
            return {"PASS_THROUGH"}
        props = self._scene.gem_x_bridge
        try:
            while True:
                item = self._events.get_nowait()
                if item[0] == "status":
                    props.status, props.progress = item[1], item[2]
                elif item[0] == "job":
                    props.job_id = item[1]
                elif item[0] == "done":
                    if self._cancel.is_set():
                        props.status = "已取消导入"
                        self.finish(context)
                        return {"CANCELLED"}
                    if context.scene != self._scene:
                        raise RuntimeError("当前场景已切换，请切回原场景并使用“导入动作 JSON”导入下载结果：" + item[1])
                    props.status = "导入动作"
                    obj = import_motion(item[1], context, self._start, self._heading)
                    props.status, props.progress = "已导入：" + obj.name, 1.
                    self.report({"INFO"}, "GEM 动作已导入")
                    self.finish(context)
                    return {"FINISHED"}
                elif item[0] == "cancelled":
                    props.status = "任务已取消"
                    self.finish(context)
                    return {"CANCELLED"}
                elif item[0] == "error":
                    raise RuntimeError(item[1])
        except queue.Empty:
            pass
        except Exception as exc:
            props.status, props.error = "任务失败", str(exc)
            self.report({"ERROR"}, str(exc)[-500:])
            self.finish(context)
            return {"CANCELLED"}
        for area in context.screen.areas:
            area.tag_redraw()
        return {"RUNNING_MODAL"}

    def cancel(self, context):
        self._cancel.set()
        self.finish(context)


class GEM_OT_cancel(bpy.types.Operator):
    bl_idname = "gem_x.cancel"
    bl_label = "取消任务"

    def execute(self, context):
        stop_workers(context.scene)
        context.scene.gem_x_bridge.status = "正在取消…"
        return {"FINISHED"}


class GEM_OT_webui(bpy.types.Operator):
    bl_idname = "gem_x.open_webui"
    bl_label = "打开服务管理页面"

    def execute(self, context):
        webbrowser.open(context.scene.gem_x_bridge.server_url)
        return {"FINISHED"}


class GEM_OT_import_motion(bpy.types.Operator, ImportHelper):
    bl_idname = "gem_x.import_motion"
    bl_label = "导入动作 JSON"
    filename_ext = ".json"
    filter_glob: StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        try:
            props = context.scene.gem_x_bridge
            import_motion(self.filepath, context, props.start_frame, props.heading)
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


CLASSES = (GEM_OT_choose_video, GEM_OT_generate, GEM_OT_cancel, GEM_OT_webui, GEM_OT_import_motion)


def stop_workers(scene=None):
    for event, pointer in list(_workers.values()):
        if scene is None or scene.as_pointer() == pointer:
            event.set()


def register():
    global _registered
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    _registered = True


def unregister():
    global _registered
    _registered = False
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)

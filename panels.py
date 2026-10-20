import bpy


class GEM_PT_main(bpy.types.Panel):
    bl_label = "GEM-X 视频转动作"
    bl_idname = "GEM_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "GEM-X"

    def draw(self, context):
        layout = self.layout
        props = context.scene.gem_x_bridge
        settings = layout.column()
        settings.enabled = not props.busy
        settings.prop(props, "server_url")
        settings.operator("gem_x.open_webui", icon="URL")
        row = settings.row(align=True)
        row.prop(props, "video_path", text="视频")
        row.operator("gem_x.choose_video", text="", icon="FILE_FOLDER")
        settings.prop(props, "mode")
        settings.prop(props, "image_features")
        if not props.image_features:
            settings.label(text="无图像特征建议使用 DDIM", icon="INFO")
        settings.prop(props, "max_frames")
        settings.prop(props, "target_fps")
        settings.prop(props, "max_edge")
        settings.prop(props, "batch_size")
        settings.prop(props, "seed")
        settings.prop(props, "postprocess")
        settings.separator()
        settings.prop(props, "start_frame")
        settings.prop(props, "heading")
        settings.label(text="保留项目帧率，按时间导入", icon="TIME")
        settings.operator("gem_x.generate", icon="PLAY")
        if props.busy:
            layout.prop(props, "progress", text=props.status, slider=True)
            layout.operator("gem_x.cancel", icon="CANCEL")
        else:
            layout.label(text=props.status, icon="INFO")
        if props.error:
            box = layout.box()
            box.alert = True
            box.label(text="任务失败，详情见服务端日志", icon="ERROR")
            for line in props.error.splitlines()[-3:]:
                box.label(text=line[:80])
        layout.separator()
        layout.operator("gem_x.import_motion", icon="IMPORT")
        layout.label(text="结果为新骨架；现有角色需重定向", icon="ARMATURE_DATA")


def register():
    bpy.utils.register_class(GEM_PT_main)


def unregister():
    bpy.utils.unregister_class(GEM_PT_main)

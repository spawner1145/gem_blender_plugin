# GEM-X Blender 插件

用于连接独立 `gem_inference_server` 的轻量插件，支持 Blender 4.2+。只有 Python 标准库和 Blender 自带模块依赖。

需要先在[gem_inference_server](https://github.com/spawner1145/gem_inference_server)这个项目部署并开启api对接使用

## 安装

1. 在 Blender 中打开“编辑 → 偏好设置 → 插件 → 从磁盘安装”。
2. 选择 `gem_blender_plugin.zip`，启用 **GEM-X 视频动作桥接**。
3. 在 3D 视图按 `N`，切换到 **GEM-X** 标签页。

也可以把本文件夹放入 Blender 的用户 `scripts/addons` 目录，然后在偏好设置中启用。

## 使用

1. 运行服务端的 `start.bat` / `start.sh`，在管理页面确认模型就绪。
2. 插件中填写服务地址，默认 `http://127.0.0.1:6700`。“打开服务管理页面”可以管理模型、端口和日志。
3. 点击视频旁的文件夹按钮，在 Blender 文件浏览器中选择 MP4 / MOV / MKV / AVI / WebM / M4V / GIF。
4. 建议先用短片段：批大小 1、最长边 720、保留 SAM 图像特征、回归模式。按“最大处理帧数”从视频开头截取；目标帧率不会提高原视频帧率。
5. 点击“视频推理并导入动作”。上传和轮询在后台线程执行，Blender 可以继续操作；取消按钮 / Esc 可取消任务。
6. 完成后，场景的 **GEM Results** 集合中会新增 `GEM_Video_Motion` 骨架和关键帧动作。按空格播放。

导入始终保留项目帧率，按实际时间换算关键帧位置。比如 12.5 FPS 的结果导入 60 FPS 项目，相邻结果帧相隔 4.8 个项目帧，动作时长保持不变，中间由 Blender 插值。动作默认从第 0 帧开始，也可以指定其他起始帧。“目标帧率”仅控制服务端的视频采样，不会修改 Blender 项目帧率。

“旋转角度（°）”对整段动作施加固定的相对旋转，不根据首帧身体朝向自动转正。默认 **180°**，在 Y-up 转 Z-up 后，等效于绕 Blender 世界原点的 Z 轴旋转半圈，将 +Y 转成 −Y、+X 转成 −X；侧身开场仍保持侧身，动作中的转身关系不变，位移轨迹一起旋转。设为 **0°** 保留原始朝向，也可以填写 **90° / −90°** 等角度。静止骨架保持不变。此设置用于自动导入和离线 JSON 导入，修改后重新导入已有 JSON 即可，无需重新推理；已有场景里的骨架不会被自动改动。

服务端导出的 `motion.json` 也可以用“导入动作 JSON”离线导入，不依赖 Blender 的可选 BVH 扩展。

结果是 SOMA 骨架。要驱动现有 Steve 或其他角色，需要再做骨骼重定向；该插件不包含当前角色专用映射。切换场景后不会把后台结果自动导入另一个场景，可以从服务端下载 JSON 后手动导入。

## 打包

ZIP 中应包含一层 `gem_blender_plugin/` 文件夹，其下是 `__init__.py`、其他 Python 文件与 README / LICENSE。不要把服务端、模型和 `.venv` 放进插件 ZIP。

服务端与插件可分别建 Git 仓库，两边各有 `.gitignore`。插件采用 GPL-2.0-or-later；模型和服务端依赖遵循其各自许可。

## 离线导入检查

在本插件文件夹中执行，测试会构造动作验证坐标、朝向、转身和 60 FPS 换算，不依赖服务端源码或权重：

```text
blender --background --factory-startup --python-exit-code 1 --python test_import_blender.py
```

还可以在命令后追加 `-- /path/to/motion.json` 检查已有结果。测试在独立 Blender 进程运行，不修改当前项目。

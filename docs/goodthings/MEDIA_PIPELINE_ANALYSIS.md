# 媒体链路分析

审计日期：2026-11-19。范围是用户素材、AI 媒体、TTS、BGM、字幕和最终合成。不把 README 中的能力当成已经实现。

## 1. 总链路

标准主题视频：

```text
主题文本
  -> LLM 旁白与图片提示词
  -> 每帧 TTS
  -> ComfyUI 或 API 出图/出视频
  -> HTML 字幕帧
  -> 静图转视频，或视频叠字幕并替换音轨
  -> concat + 可选 BGM
  -> output/{task_id}/final.mp4
```

用户素材视频：

```text
上传文件 -> temp/assets_{session}/
  -> VLM 或 Comfy 分析，得到文字描述
  -> LLM 分配 asset_path 并写口播
  -> 每镜头多段 TTS 再拼接音频
  -> 可选：图片再送 API 图生视频
  -> FrameProcessor 合成
  -> concat + 可选 BGM
```

两条链路在 `FrameProcessor` 之后合流。商品第一版应走第二条的「已有媒体」分支，只在环境镜头上可选地进入第一条的出图分支。

## 2. 用户上传

实现位置：`web/pipelines/asset_based.py` `_render_asset_input()`。

```text
uploaded_files = st.file_uploader(...)
temp_dir = Path(f"temp/assets_{session_id}")
file_path = temp_dir / uploaded_file.name
```

动作迁移、图生视频、数字人使用同一临时目录模式。参考音频在 `web/components/style_config.py`。

存储特点：

- 路径是进程工作目录下的 `temp/`，不是 `output/{task_id}`。
- 文件名来自上传原名，同名覆盖。
- 当前未发现素材 ID、哈希、授权、所属商品、使用状态。
- 任务成功后，`metadata.json` 的 `input.assets` 只保存当时的路径字符串（`AssetBasedPipeline._persist_task_data()`）。文件仍留在 `temp/`。清理临时目录的逻辑当前未发现。
- API 当前未发现上传端点。`api/config.py` 的 `max_upload_size = 100MB` 没有被路由使用。

这足够做一次会话内成片，不够做商品档案。

## 3. 素材如何进入模型

分析服务只接收本地路径：

| 服务 | 函数 | 输出 |
| --- | --- | --- |
| `ImageAnalysisService` | `__call__(image_path, source, workflow)` | 描述字符串 |
| `VideoAnalysisService` | `__call__(video_path, source, workflow)` | 描述字符串 |
| `APIAssetAnalysisService` | `analyze_image()` / `analyze_video()` | 描述字符串 |

`AssetBasedPipeline.setup_environment()` 把描述放进 `asset_index`。随后 `build_asset_script_prompt()` 把路径和描述拼进 LLM prompt。LLM 看到的是文字，不是原始像素。像素只在分析那一步进入视觉模型。

出图时，`MediaService.__call__()` 可另收 `image_path`，用于图生视频或参考图。`FrameProcessor._prepare_api_video_inputs()` 会在 API 视频缺少首帧时，先用 `image_prompt` 生成一张首帧。

当前未发现把商品详情图、包装背面、说明书分页送入一个专用分析协议。现有接口是「一个文件进，一段描述出」。

## 4. 素材与分镜的关联

关联发生在 LLM 结构化输出，不发生在数据库。

`SceneScript` 字段：`scene_number`、`asset_path`、`narrations`、`duration`。

`initialize_storyboard()` 把路径抄到 `StoryboardFrame.image_path` 或 `video_path`，并临时挂 `frame._scene_data`。`_scene_data` 不是 `StoryboardFrame` 的声明字段，持久化时不一定保留。`persistence.py` `_frame_to_dict()` 只序列化声明过的字段。

因此重启后可以从 `storyboard.json` 看到每帧的媒体路径和旁白，当前未发现看到「这是第几段商品镜头、来源是真实还是 AI、授权状态是什么」。

路径匹配失败时回退到第一个素材。这会把错误素材放进镜头，且只打 warning。

## 5. 生成媒体与用户媒体如何区分

运行时区分：

| 条件 | 行为 | 代码 |
| --- | --- | --- |
| `image_prompt is not None` | 生成新媒体 | `FrameProcessor.__call__` `needs_generation` |
| 已有 `image_path` 或 `video_path` | 使用现有文件 | `has_existing_media` |
| 两者都没有 | 纯文字模板 | `media_type = None` |

文件名区分：

- 生成文件：`output/{task_id}/frames/{nn}_image.png`、`{nn}_video.mp4`，由 `get_task_frame_path()` 分配。
- 用户文件：仍是 `temp/assets_.../原名`，直到合成时被读取。合成结果是 `{nn}_segment.mp4`。

没有 `source` 枚举。商品模块如果要执行「真实图优先于 AI 图」，必须自己在调用 `FrameProcessor` 之前填好路径并保持 `image_prompt is None`。一旦填了 `image_prompt`，处理器会再生成一张图并覆盖 `image_path`（`_step_generate_media()` 下载后赋值）。

## 6. 已有视频片段能否直接合成

能，但是按「整段视频当一个镜头背景」处理。

`FrameProcessor._step_create_video_segment()` 视频分支：

1. `overlay_image_on_video(scale_mode="contain")`。视频被缩进模板尺寸，不足部分黑边。另有 `cover`、`stretch`，调用点写死 `contain`。
2. `merge_audio_video(replace_audio=True, audio_volume=1.0)`。用户视频原声被 TTS 替换。
3. 时长差由冻结尾帧或裁尾处理。容差 0.3 秒。

不能：

- 当前未发现按入点/出点截取用户视频。
- 当前未发现一个镜头内拼接多段用户视频。
- 当前未发现保留原声并压低音量。`merge_audio_video` 有 `replace_audio=False` 和 `video_volume`，但分镜调用没有使用。
- 当前未发现把用户视频当作画中画。

所以「真实使用视频优先」在技术上可以落到现有合成器，但要在进入 `FrameProcessor` 之前完成裁切和优先级选择。合成器本身不做这个选择。

## 7. AI 图片与 AI 视频

出图：

- Comfy 工作流：`workflows/runninghub/image_*.json`、`workflows/selfhost/image_flux.json`、`image_qwen.json`、`image_nano_banana.json`。
- 直连：`DashScopeClient.generate_image()`、`ImageGPT`、`SeedreamClient`。
- 默认工作流来自 `config.yaml` 的 `comfyui.image.default_workflow`。示例是 `runninghub/image_flux.json`。
- 所有出图都会加 `prompt_prefix`。示例前缀是火柴人简笔画。这个前缀不适合商品实拍风格。

出视频：

- Comfy：`video_wan2.1_fusionx.json`、`video_wan2.2.json`、`video_qwen_wan2.2.json` 等。
- 直连：DashScope、Kling、Seedance。`APIProviderMediaService._generate_video()` 对内容审核失败会改写 prompt 再试一次。
- 素材管线可选动画：UI 文案是「不启用时保留原素材静态合成」。默认选项包含 `none`。

成本相关事实：

- 标准 `image_*` 模板每个镜头至少一次 LLM 提示词加一次出图。
- `static_*` 模板在 `StandardPipeline.plan_visuals()` 里跳过提示词和出图。
- 商品默认链路可以模仿 static/asset 路径，只在明确的环境镜头调用 `MediaService`。

当前未发现禁止生成「清洁前后对比」「用户评价截图」「功效证明」的代码或提示词。约束必须加在新的商品提示词和素材选择里。现有出图函数不会拒绝这类 prompt。

## 8. TTS、字幕、BGM

TTS 输出路径：

- 标准分镜：`get_task_frame_path(task_id, index, "audio")` → `frames/01_audio.mp3`。
- 素材分镜：先写 `frames/{i:02d}_narration_{j}.mp3`，多句时用 ffmpeg concat 成 `frames/{i:02d}_audio.mp3`。

字幕不是单独的媒体文件。它是 HTML 文本，烧进 `frames/{nn}_composed.png`，再进片段视频。编辑字幕等于改 `StoryboardFrame.narration` 后重跑合成步骤。若口播文本和字幕文本需要分离，现有模型只有一个 `narration` 字段，当前未发现第二个字幕字段。

BGM：

- 仓库只带 `bgm/default.mp3`。
- 用户可选自定义文件，解析顺序见 `VideoService._resolve_bgm_path()`。
- `bgm_mode` 支持 `loop` 和 `once`。
- `add_bgm()` 还有 `fade_in`；`fade_out` 在注释里写明尚未实现。
- 拼接函数使用的是 `_add_bgm_to_video()`，不是带 fade 的 `add_bgm()`。标准管线因此没有 BGM 淡入。

## 9. 合成能力对照

| 任务书要求 | 源码 |
| --- | --- |
| 用户真实视频 | 有。`frame.video_path` 已设且 `image_prompt is None` |
| 商品图片 | 有。`frame.image_path` 同样跳过生成 |
| AI 场景图片 | 有。`MediaService` / API 出图 |
| AI 视频片段 | 有。默认不应打开 |
| TTS | 有。Edge TTS 与 Comfy TTS |
| BGM | 有。整片一个音量 |
| 字幕 | 有，烧录。当前未发现 SRT |
| 镜头时长 | 只有结果字段 `duration`，由音频决定。当前未发现目标时长输入 |
| 缩放和移动 | 当前未发现 |
| 转场 | 当前未发现。拼接是硬切 |
| 音量控制 | 整片 BGM 音量有。口播在分镜里固定 `1.0`。逐镜头音量当前未发现 |

`VideoService` 已有的 FFmpeg 操作足够做「静图 + 口播 + 硬切 + BGM」。商品模板里的推近和局部特写需要新增可选滤镜，不应重写 `concat_videos()`。

## 10. 失败与部分产物

单帧失败会从 `FrameProcessor.__call__` 抛出，整条管线中断。已经生成的 `frames/01_*` 会留在任务目录里，因为 `create_task_output_dir()` 在开头就建了目录。

当前未发现：

- 从最后一个成功帧继续。
- 只重跑失败帧。
- 把失败状态写入 `metadata.json`。成功路径才调用 `save_task_metadata()`。

这些半成品文件可以作为以后重试的原料，但现有代码不会读取它们来恢复。

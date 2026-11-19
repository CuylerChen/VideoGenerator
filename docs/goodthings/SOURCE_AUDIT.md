# Pixelle-Video 源码审计

审计日期：2026-11-19  
审计范围：本地仓库 `/Users/chenkaile/Documents/ai_code/VideoGenerator`  
项目版本：`pyproject.toml` 中 `pixelle-video` `0.2.0`；`api/app.py` 的 FastAPI `version` 仍写 `0.1.0`  
方法：只读源码。结论均对应到文件、类或函数。源码中未出现的能力写「当前未发现」。  
本次未修改任何业务代码。

## 1. 仓库与许可证

| 文件 | 结论 |
| --- | --- |
| `LICENSE` | Apache License 2.0 |
| `NOTICE` | 版权声明为 `Copyright (C) 2025 AIDC-AI`，并列出 pillow、httpx、streamlit 等第三方许可证 |
| `pyproject.toml` | Python `>=3.11`；作者字段为 Pixelle.AI；许可证文本 `Apache-2.0` |
| 源文件头 | `web/`、`api/`、`pixelle_video/` 多数文件头为 `Copyright (C) 2025 AIDC-AI`，Apache-2.0 |

主要运行时依赖（`pyproject.toml`）：`streamlit`、`fastapi`、`uvicorn`、`openai`、`edge-tts==7.2.7`、`ffmpeg-python`、`moviepy==1.0.3`、`playwright`、`comfykit`、`dashscope`、`pillow`、`pydantic`、`httpx`。

`tests/` 目录和 `test_*.py`：**当前未发现**。`pyproject.toml` 的 pytest 配置 `testpaths = ["tests"]`，但仓库内没有对应测试文件。

## 2. 目录地图

| 目录 | 实际作用 | 依据 |
| --- | --- | --- |
| `pixelle_video/` | 核心服务与视频生成管线 | `pixelle_video/service.py` `PixelleVideoCore` |
| `web/` | Streamlit 多页 UI | `web/app.py` `main()` |
| `api/` | FastAPI 接口与内存任务管理 | `api/app.py` |
| `templates/` | 按分辨率分目录的 HTML 画幅模板 | `templates/1080x1920/` 等 |
| `workflows/` | ComfyUI / RunningHub JSON 工作流 | `workflows/runninghub/`、`workflows/selfhost/` |
| `bgm/` | 默认背景音乐，当前只有 `default.mp3` | 目录列举 |
| `resources/` | README / 文档用图片，不是运行时素材库 | `resources/*.png` |
| `docs/` | 上游中英文文档 | `docs/zh/`、`docs/en/` |
| `packaging/windows/` | Windows 打包脚本 | `packaging/windows/build.py` |

商品、商品链接、卖点分级、六段式固定时间轴、用户账号：**当前未发现**对应业务模块。

## 3. 视频生成入口

存在两条正式成片链路，以及三条只在 Web UI 内直接调用媒体服务的旁路。

### 3.1 Web 应用入口

| 项 | 内容 |
| --- | --- |
| 文件 | `web/app.py` |
| 函数 | `main()` |
| 输入 | 无业务参数。`st.set_page_config` 后用 `st.Page` 注册页面 |
| 输出 | Streamlit 导航。默认页 `pages/1_🎬_Home.py`，历史页 `pages/2_📚_History.py` |
| 调用 | `pg = st.navigation([home_page, history_page]); pg.run()` |
| 启动 | `start_web.sh`；Docker 中 `streamlit run web/app.py`（`docker-compose.yml`） |
| 复用 | 适合作为第一版 UI 宿主。新增页面应继续用 `st.Page`，不要重写前端框架 |
| 影响 | 改导航会影响 Home 与 History |

Home 页本身不生成视频。`web/pages/1_🎬_Home.py` 的 `main()` 只做会话初始化、设置和管线 Tab 分发：

```python
pipelines = get_all_pipeline_uis()
tabs = st.tabs(...)
pipeline.render(pixelle_video)
```

UI 管线注册在 `web/pipelines/__init__.py`：`standard`、`asset_based`、`digital_human`、`i2v`、`action_transfer`。

### 3.2 视频生成按钮

标准主题成片按钮：

| 项 | 内容 |
| --- | --- |
| 文件 | `web/components/output_preview.py` |
| 函数 | `render_single_output()` |
| 触发 | `st.button(tr("btn.generate"))`，约第 74 行 |
| 输入 | `video_params`：`text`、`mode`、`title`、`n_scenes`、`split_mode`、TTS、模板、工作流、BGM |
| 输出 | `VideoGenerationResult`，随后 `st.video()` 预览和 `st.download_button` 下载 MP4 |
| 调用 | `run_async(pixelle_video.generate_video(**video_params))` |
| 复用 | 按钮和进度条可复用。参数组装是主题视频专用，商品工作台不应把业务规则写进这个函数 |
| 影响 | 改这个函数会同时影响标准单条生成和它内部重建的参数字典 |

注意：`web/pipelines/standard.py` 的 `StandardPipelineUI.name` 是 `"quick_create"`，并放进 `video_params["pipeline"]`。`render_single_output()` 会重新组装参数，**没有把 `pipeline` 传下去**。因此 Web 标准按钮实际走 `generate_video()` 的默认管线 `"standard"`。

素材成片按钮：

| 项 | 内容 |
| --- | --- |
| 文件 | `web/pipelines/asset_based.py` |
| 函数 | `_render_output_preview()` 内 `st.button(..., key="asset_generate")` |
| 调用 | 直接 `AssetBasedPipeline(pixelle_video)`，再 `pipeline(assets=..., intent=..., duration=...)` |
| 返回 | `PipelineContext`，不是 `VideoGenerationResult` |

数字人、图生视频、动作迁移各自在 `web/pipelines/digital_human.py`、`i2v.py`、`action_transfer.py` 里有独立生成按钮，直接 `await pixelle_video.media(...)`，不经过 `generate_video()`。

### 3.3 视频生成任务调用入口

| 项 | 内容 |
| --- | --- |
| 文件 | `pixelle_video/service.py` |
| 类 | `PixelleVideoCore` |
| 注册 | `initialize()` 注册 `standard`、`custom`、`asset_based` |
| 入口 | `_create_generate_video_wrapper()` 赋给 `self.generate_video` |
| 输入 | `text: str`，`pipeline: str = "standard"`，其余 `**kwargs` |
| 输出 | 对应管线的返回值。`StandardPipeline` 返回 `VideoGenerationResult`；`AssetBasedPipeline.__call__` 返回 `PipelineContext` |
| 调用 | `self.pipelines[pipeline](text=text, **kwargs)` |
| 复用 | 这是应保留的统一入口。商品管线应新增注册项，不要替换 `standard` |
| 影响 | 改 wrapper 签名会影响 Web 标准流、批量流和 API |

API 入口：

| 项 | 内容 |
| --- | --- |
| 文件 | `api/routers/video.py` |
| 函数 | `generate_video_sync()`、`generate_video_async()` |
| 输入 | `VideoGenerateRequest`（`api/schemas/video.py`） |
| 输出 | 同步返回 `video_url`、`duration`、`file_size`；异步返回 `task_id` |
| 调用 | 两者都调用 `pixelle_video.generate_video(**video_params)`，且请求体没有 `pipeline` 字段，因此固定走 `standard` |
| 复用 | 可复用同步/异步模式，但不能直接当成商品视频 API |
| 影响 | 给现有请求体加必填字段会破坏上游 API |

`VideoGenerateRequest` 当前字段：`text`、`mode`（`generate`/`fixed`）、`title`、`n_scenes`、`tts_workflow`、`ref_audio`、`voice_id`、文案长度限制、`media_workflow`、`video_fps`、`frame_template`、`template_params`、`prompt_prefix`、`bgm_path`、`bgm_volume`。

当前未发现：`pipeline`、`tts_inference_mode`、`tts_speed`、`split_mode`、商品 ID、素材列表、分镜时间轴。

### 3.4 文案生成

| 项 | 内容 |
| --- | --- |
| 文件 | `pixelle_video/utils/content_generators.py` |
| 函数 | `generate_title()`、`generate_narrations_from_topic()`、`split_narration_script()`、`generate_image_prompts()` |
| 输入 | LLM 服务、主题或固定文案、场景数、字数限制 |
| 输出 | 标题字符串、旁白列表、图片提示词列表 |
| 提示词 | `pixelle_video/prompts/title_generation.py`、`topic_narration.py`、`content_narration.py`、`image_generation.py` |
| 调用方 | `StandardPipeline.generate_content()` / `determine_title()` / `plan_visuals()`；API `api/routers/content.py` |
| LLM | `pixelle_video/services/llm_service.py` `LLMService.__call__()`。支持 OpenAI 兼容接口，可选 `response_type` 做结构化输出 |
| 复用 | LLM 客户端和结构化输出可直接复用。主题口播提示词不能直接当商品口播，因为它不区分事实、宣传说法和推测 |
| 影响 | 改 `content_generators.py` 会同时影响标准管线和 `/api/content/*` |

素材脚本是另一条文案路径：

| 项 | 内容 |
| --- | --- |
| 文件 | `pixelle_video/pipelines/asset_based.py` |
| 函数 | `AssetBasedPipeline.generate_content()` |
| 模型 | `SceneScript`、`VideoScript` |
| 提示词 | `pixelle_video/prompts/asset_script_generation.py` `build_asset_script_prompt()` |
| 输入 | `intent`、`duration`、素材描述文本、可选标题 |
| 输出 | 场景列表。每个场景含 `scene_number`、`asset_path`、`narrations`、`duration` |
| 复用 | 最接近商品视频的现有文案能力。仍缺少事实分级和禁止表述约束 |
| 影响 | 只被素材管线使用，改动不影响标准主题流，但会影响现有「素材成片」Tab |

### 3.5 图片生成

| 项 | 内容 |
| --- | --- |
| 文件 | `pixelle_video/services/media.py` |
| 类 | `MediaService` |
| 函数 | `__call__(prompt, workflow=None, media_type="image", width, height, duration, output_path, image_path, ...)` |
| 输出 | `pixelle_video/models/media.py` `MediaResult`（`media_type` + `url`） |
| 调用 | 工作流名以 `api/` 开头时转给 `APIProviderMediaService`；否则走 ComfyKit |
| 直连 API | `pixelle_video/services/api_media.py` `APIProviderMediaService._generate_image()` |
| 供应商 | `api_services/image_dashscope.py`、`image_gpt.py`、`image_seedream.py` |
| API 路由 | `api/routers/image.py` `image_generate()` |
| 复用 | 适合按需生成环境图。商品外观图不应默认走这条链路 |
| 影响 | `MediaService` 同时服务图片和视频。改参数会波及标准分镜、图生视频、数字人和动作迁移 |

### 3.6 视频生成

这里的「视频生成」指 AI 片段，不是最终合成。

| 项 | 内容 |
| --- | --- |
| 入口 | `MediaService.__call__(media_type="video")` 或 `APIProviderMediaService._generate_video()` |
| Comfy 工作流 | `workflows/runninghub/video_*.json`、`workflows/selfhost/video_wan2.1_fusionx.json` |
| 直连供应商 | `api_services/video_dashscope.py` `DashscopeVideoClient`、`video_kling.py` `KlingVideoClient`、`video_seedance.py`、`video_client.py` |
| 调用方 | `FrameProcessor._step_generate_media()`；`AssetBasedPipeline.produce_assets()` 可选把图片动画化；`web/pipelines/i2v.py`、`digital_human.py`、`action_transfer.py` |
| 输入 | prompt、宽高、时长、首帧 `image_path`、可选驱动音频 |
| 输出 | 视频 URL 或本地路径，下载后写入分镜 `video_path` |
| 复用 | 能力存在，但任务书要求默认不调用昂贵 AI 视频。应保持可选，不放进默认商品链路 |
| 影响 | 改 `api_media.py` 的时长换算和内容审核重试会影响所有 API 视频模型 |

### 3.7 TTS

| 项 | 内容 |
| --- | --- |
| 文件 | `pixelle_video/services/tts_service.py` |
| 类 | `TTSService` |
| 函数 | `__call__(text, workflow, voice, speed, inference_mode, output_path, **params) -> str` |
| 本地实现 | `_call_local_tts()` → `pixelle_video/utils/tts_util.py` `edge_tts()` |
| Comfy 实现 | `_call_comfyui_workflow()` |
| 音色表 | `pixelle_video/tts_voices.py` `EDGE_TTS_VOICES` |
| 语速换算 | `speed_to_rate()` |
| 默认音色 | `schema.py` `TTSLocalConfig.voice = "zh-CN-YunjianNeural"`，男声 |
| 女声 | 已有 `zh-CN-XiaoxiaoNeural`、`zh-CN-XiaoyiNeural`，`gender="female"` |
| 语速范围 | `0.5` 到 `2.0`，默认 `1.2`。UI 滑块步长 `0.1`（`web/pipelines/asset_based.py`） |
| API | `api/routers/tts.py` `tts_synthesize()` |
| 复用 | 直接复用。商品模板只要把 `voice_id` 设为女声、`tts_speed` 设为 `1.2` 即可落在 1.15–1.25 |
| 影响 | 改默认音色会影响所有未显式传 voice 的调用，包括标准管线和素材管线 |

`edge_tts()` 自带最多 5 次指数退避重试（`tts_util.py` `_RETRY_COUNT = 5`）。这是网络重试，不是业务任务重试。

### 3.8 BGM

| 项 | 内容 |
| --- | --- |
| 处理 | `pixelle_video/services/video.py` `VideoService.concat_videos()` 的 `bgm_path` / `bgm_volume` / `bgm_mode`；内部 `_add_bgm_to_video()`；另有独立 `add_bgm()` |
| 路径解析 | `_resolve_bgm_path()`：绝对/相对路径，其次 `data/bgm/`，再次 `bgm/` |
| 默认文件 | `bgm/default.mp3` |
| UI | `web/components/content_input.py` `render_bgm_section()` |
| 列表 API | `api/routers/resources.py` `list_bgm()` |
| 复用 | 直接复用。音量是整片一个值，不是逐镜头 |
| 影响 | 改混音逻辑会影响所有成片 |

### 3.9 视频合成

| 项 | 内容 |
| --- | --- |
| 单镜头编排 | `pixelle_video/services/frame_processor.py` `FrameProcessor.__call__()` |
| 步骤 | 1 TTS；2 生成或跳过媒体；3 HTML 合成字幕画面；4 做成镜头 MP4 |
| 静图成片 | `VideoService.create_video_from_image()` |
| 视频叠字幕 | `VideoService.overlay_image_on_video()` + `merge_audio_video(replace_audio=True)` |
| 整片拼接 | `VideoService.concat_videos()`，默认 `method="demuxer"` |
| HTML 渲染 | `pixelle_video/services/frame_html.py` `HTMLFrameGenerator.generate_frame()`，Playwright 截图 |
| 复用 | 这是应保留的合成引擎。不要另写一套 FFmpeg 主流程 |
| 缺口 | 当前未发现镜头缩放、推近、硬切以外的转场、逐镜头音量、独立字幕文件 |

## 4. 素材处理机制

### 4.1 上传入口

| 入口 | 文件与函数 | 接受类型 | 存储 |
| --- | --- | --- | --- |
| 素材成片 | `web/pipelines/asset_based.py` `_render_asset_input()` | `st.file_uploader`，多文件 | `temp/assets_{session_id}/原文件名` |
| 动作迁移 | `web/pipelines/action_transfer.py` `render_action_transfer_video_input()`、`render_action_transfer_assets_input()` | 视频、图片 | 同上 |
| 图生视频 | `web/pipelines/i2v.py` `render_audio_visual_input()` | 图片 | 同上 |
| 数字人 | `web/pipelines/digital_human.py` `render_digital_human_input()` | 人物图、参考视频/音频 | 同上 |
| 声音克隆参考音 | `web/components/style_config.py`、`digital_tts_config.py` | 音频 | 临时文件 |
| API 上传 | **当前未发现**通用上传接口。`api/config.py` 有 `max_upload_size`，但路由里没有对应 uploader |

上传文件按浏览器原始文件名保存。同名文件会覆盖。当前未发现素材 ID、授权状态、所属商品字段。

### 4.2 如何交给视觉模型

`AssetBasedPipeline.setup_environment()`：

- 图片：`source=="api"` 时 `APIAssetAnalysisService.analyze_image()`；否则 `ImageAnalysisService.__call__()`。
- 视频：`source=="api"` 时 `analyze_video()`；否则 `VideoAnalysisService.__call__()`。
- 工作流文件：`workflows/*/analyse_image.json`、`workflows/selfhost/analyse_video.json`。RunningHub 目录有 `analyse_image.json`、`video_understanding.json`。
- 返回值是一段文字描述，放进内存字典 `self.asset_index[path]`。

`APIAssetAnalysisService`（`pixelle_video/services/api_asset_analysis.py`）把本地文件发给 VLM。这是用户主动上传后的分析，不是抓取平台页面。

当前未发现商品链接解析、登录绕过或平台爬虫。

### 4.3 素材与分镜如何关联

`AssetBasedPipeline.generate_content()` 把素材路径和描述交给 LLM，要求返回 `VideoScript.scenes[].asset_path`。`plan_visuals()` 把它抄成 `matched_asset`。`initialize_storyboard()` 按素材类型写入：

- 视频：`frame.media_type = "video"`，`frame.video_path = asset_path`
- 图片：`frame.media_type = "image"`，`frame.image_path = asset_path`
- `image_prompt = None`，表示不要再生成媒体

路径对不上时，先按文件名纠正，再回退到 `asset_index` 的第一个素材。这是静默回退，不是人工确认。

### 4.4 生成图与用户图如何区分

`FrameProcessor.__call__()`：

- `frame.image_prompt is not None`：调用 `_step_generate_media()` 生成。
- `frame.image_path` 或 `frame.video_path` 已有值：跳过生成，打日志 `Using existing image/video`。
- 两者都没有：`media_type = None`，走纯文字模板。

没有独立的 `source_type` 字段。区分只靠「有没有 `image_prompt`」和「路径是否预先填好」。历史 JSON 里也不会标记授权状态。

### 4.5 已有视频能否直接参与合成

能。素材管线把用户视频路径写入 `StoryboardFrame.video_path` 后，`FrameProcessor._step_create_video_segment()` 走视频分支：

1. `overlay_image_on_video(scale_mode="contain")` 把 HTML 字幕层叠到视频上。
2. `merge_audio_video(replace_audio=True)` 用 TTS 替换原视频音轨。
3. 若视频短于音频，`_pad_video_to_duration()` 冻结最后一帧；若长于音频超过 0.3 秒，`_trim_video_to_duration()` 裁掉尾部。

因此用户视频可以进成片，但原声会被替换，时长会被口播音频支配。当前未发现保留原声、按指定入点出点裁切、或多段用户视频拼进同一镜头的接口。

## 5. 模板系统摘要

详见 `TEMPLATE_ANALYSIS.md`。审计结论：

- 模板是 HTML，按 `WIDTHxHEIGHT/文件名.html` 放置。
- `1080x1920` 已存在，最终画面尺寸来自目录名，不是 meta 标签。
- meta 标签 `template:media-width/height` 只决定 AI 出图尺寸。`image_default.html` 与 `asset_default.html` 的 meta 都是 `1024`，页面 CSS 仍是 `1080x1920`。
- 字幕烧进 HTML 截图，不是 SRT。
- 单镜头时长由 TTS 音频决定。当前未发现每个镜头独立时长配置，也未发现六段式时间轴对象。
- 现有模板能做竖屏带字幕成片，不能满足「0–3 / 3–7 / 7–13 / 13–21 / 21–25 / 25–30」这种固定时间轴。

## 6. 任务机制摘要

详见 `DATABASE_AND_STORAGE_ANALYSIS.md`。审计结论：

- 当前未发现数据库、Redis、Celery 或持久化任务队列。
- Web 生成在当前 Streamlit 会话里同步等待。
- API 有内存任务管理器 `api/tasks/manager.py` `TaskManager`。进程退出后任务丢失。
- 成功的成片会写 `output/{task_id}/metadata.json` 和 `storyboard.json`。
- 失败任务当前未发现落盘。`StandardPipeline.handle_exception()` 只记日志后重新抛出。
- `HistoryManager.regenerate_frame()` 明确写着 `not implemented yet`。
- 当前未发现任务中断后的恢复，也未发现生成任务级重试接口。

## 7. 与商品短视频目标的差距

| 任务书能力 | 源码现状 |
| --- | --- |
| 商品档案 | 当前未发现 |
| 商品链接解析 | 当前未发现。已有上传和手动文本，可作备用入口 |
| 卖点 / 事实 / 推测分级 | 当前未发现 |
| 三个钩子、标题、口播、六段分镜、封面文案、发布描述 | 当前未发现这组固定输出。现有能力是主题旁白或素材脚本 |
| 六段固定时间轴 | 当前未发现。`n_scenes` 可以设为 6，但时长不按秒锁死 |
| 真实素材优先于 AI | 素材管线可以只用用户素材；标准管线默认生成 AI 图。没有统一优先级策略 |
| 禁止 AI 伪造前后对比 | 当前未发现约束 |
| 逐镜头改完只重合成该镜头 | 当前未发现。`regenerate_frame()` 是空实现 |
| 1080×1920、30fps | 模板目录和 `video_fps=30` 已支持 |
| 女声普通话、约 1.2 倍速 | Edge TTS 已支持，默认却是男声 |
| 原项目主题成片仍可用 | 可以，前提是商品改造新增管线，不改 `StandardPipeline` 的默认行为 |

## 8. 审计边界

本次只读取源码并写文档。没有运行生成，没有改 `pixelle_video/`、`web/`、`api/`、模板或工作流。阶段 B 及之后的设计与开发应等人工审核后再开始。

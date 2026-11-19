# Pixelle-Video 架构分析

审计日期：2026-11-19。依据为当前仓库源码，不依据 README 推断。

## 1. 分层

```text
Streamlit Web                         FastAPI
web/app.py                            api/app.py
  pages/1_Home.py                       routers/video.py
  pages/2_History.py                    routers/content|image|tts|frame|tasks|files
  pipelines/*_ui                        tasks/manager.py   （进程内内存）
        |                                      |
        +------------------+-------------------+
                           |
                 pixelle_video/service.py
                 PixelleVideoCore.generate_video()
                           |
        +------------------+-------------------+
        |                  |                   |
 StandardPipeline    AssetBasedPipeline    CustomPipeline
 pixelle_video/pipelines/standard.py      asset_based.py    custom.py
        |                  |
        +-------- FrameProcessor --------+
                 frame_processor.py
            TTS  Media  HTML  VideoService
                           |
              output/{task_id}/  文件系统
```

`PixelleVideoCore.initialize()`（`pixelle_video/service.py`）创建的服务：

- `LLMService`
- `TTSService`
- `MediaService`
- `APIProviderMediaService`
- `ImageAnalysisService`
- `VideoAnalysisService`
- `APIAssetAnalysisService`
- `VideoService`
- `FrameProcessor`
- `PersistenceService(output_dir="output")`
- `HistoryManager`

全局单例是模块底部的 `pixelle_video = PixelleVideoCore()`。Web 通过 `web/state/session.py` `get_pixelle_video()` 取它。API 通过 `api/dependencies.py` `get_pixelle_video()` 取它。

ComfyKit 不在 `initialize()` 里创建，而是 `_get_or_create_comfykit()` 第一次用到时创建。配置哈希变化会关掉旧实例再建。

## 2. 已注册管线与仅 UI 管线

核心字典只有三项（`service.py` `initialize()`）：

| 键 | 类 | 基类 | Web 是否暴露 |
| --- | --- | --- | --- |
| `standard` | `StandardPipeline` | `LinearVideoPipeline` | 是，Tab 名来自 `StandardPipelineUI`，内部名 `quick_create` |
| `custom` | `CustomPipeline` | `BasePipeline` | 当前未发现对应 UI |
| `asset_based` | `AssetBasedPipeline` | `LinearVideoPipeline` | 是，但 UI 自己 new 管线，不走 `generate_video(pipeline="asset_based")` |

`web/pipelines/` 另外三个类没有注册进 `PixelleVideoCore.pipelines`：

| UI 类 | 文件 | 实际调用 |
| --- | --- | --- |
| `DigitalHumanPipelineUI` | `web/pipelines/digital_human.py` | `pixelle_video.media(**media_params)` |
| `ImageToVideoPipelineUI` | `web/pipelines/i2v.py` | `pixelle_video.media(...)` |
| `ActionTransferPipelineUI` | `web/pipelines/action_transfer.py` | `pixelle_video.media(...)` |

这三条旁路成功后用 `web/utils/history_persistence.py` `save_web_generation_history()` 补写历史。它们不经过 `FrameProcessor` 的四步分镜。

`custom.py` 末尾还有 `MySpecialPipeline`、`QuickPipeline`。它们是示例类，`service.py` 没有注册。

## 3. 标准主题成片调用链

1. `web/app.py` `main()` 打开 Home。
2. `web/pages/1_🎬_Home.py` `main()` 渲染全部 UI 管线 Tab。
3. `web/pipelines/standard.py` `StandardPipelineUI.render()` 拼三列：`render_content_input()`、`render_bgm_section()`、`render_style_config()`、`render_output_preview()`。
4. 用户点 `web/components/output_preview.py` `render_single_output()` 里的生成按钮。
5. `web/utils/async_helpers.py` `run_async()` 执行协程。
6. `PixelleVideoCore.generate_video()` 默认进入 `StandardPipeline`。
7. `LinearVideoPipeline.__call__()`（`pipelines/linear.py`）按固定顺序调用：
   - `setup_environment`：`create_task_output_dir()`
   - `generate_content`：主题生成旁白，或按 paragraph/line/sentence 切固定稿
   - `determine_title`
   - `plan_visuals`：按模板类型决定是否生成图片提示词
   - `initialize_storyboard`：建 `StoryboardConfig` 和 `StoryboardFrame`
   - `produce_assets`：逐帧或 RunningHub 限流并行调用 `FrameProcessor`
   - `post_production`：`VideoService.concat_videos()`，可选 BGM
   - `finalize`：`VideoGenerationResult`，再 `_persist_task_data()`
8. 异常进 `handle_exception()`，只记日志并重新抛出。

批量模式在 `web/utils/batch_manager.py` `SimpleBatchManager.execute_batch()`。它串行循环调用同一个 `generate_video()`，只支持 `mode="generate"`。注释写明没有 CSV、没有复杂校验。

## 4. 素材成片调用链

这是和商品视频最接近的现有链路。

1. `web/pipelines/asset_based.py` `AssetBasedPipelineUI.render()`。
2. 上传文件写入 `temp/assets_{session_id}/`。
3. 生成按钮创建 `AssetBasedPipeline`，调用其自定义 `__call__()`。
4. 自定义 `__call__()` **不使用**基类把第一个参数当 `text` 的约定。它接收 `assets`、`video_title`、`intent`、`duration`、`source`。
5. `setup_environment()` 分析每个文件，建立 `asset_index`。
6. `generate_content()` 用 `LLMService.__call__(response_type=VideoScript)` 生成脚本，并由模型指定 `asset_path`。
7. `initialize_storyboard()` 写死模板 `1080x1920/asset_default.html`，`video_fps=30`，本地 TTS。
8. `produce_assets()` 先为每段旁白生成 MP3，再用 ffmpeg concat 合并该镜头音频，然后调用 `FrameProcessor`。
9. 若 UI 打开了 API 图生视频，图片镜头会先 `core.media(media_type="video")`，再交给 `FrameProcessor`。
10. `post_production()` 拼接分镜并加 BGM。
11. `finalize()` 写 metadata 和 storyboard，返回 `PipelineContext`。

`duration` 只传给 LLM 提示词（`build_asset_script_prompt()`）。最终成片时长是各镜头 TTS 音频时长之和，不是这个整数秒。

## 5. 单镜头处理

`FrameProcessor.__call__()` 是所有分镜成片的共用步骤：

```text
StoryboardFrame
  -> TTSService                frames/{nn}_audio.mp3
  -> MediaService              frames/{nn}_image.png 或 {nn}_video.mp4
  -> HTMLFrameGenerator        frames/{nn}_composed.png
  -> VideoService              frames/{nn}_segment.mp4
```

已有 `audio_path` 会跳过 TTS。已有 `image_path`/`video_path` 且 `image_prompt is None` 会跳过媒体生成。商品改造应沿用这个跳过条件，而不是在 `FrameProcessor` 里加商品判断。

RunningHub 并行只在 `StandardPipeline.produce_assets()` 里出现，条件是工作流键以 `runninghub/` 开头，且 `runninghub_concurrent_limit > 1`。素材管线是串行 for 循环。

## 6. 配置如何流到服务

`pixelle_video/config/schema.py` `PixelleVideoConfig` 只有四块：`project_name`、`llm`、`api_providers`、`comfyui`、`template`。

`config.example.yaml` 的 `comfyui.tts.default_workflow` 写在 `tts` 下。`TTSSubConfig` 的字段是 `inference_mode`、`local`、`comfyui`。`default_workflow` 是 `@property`，读的是 `self.comfyui.default_workflow`。Pydantic 默认忽略多余字段。因此示例 YAML 里的 TTS `default_workflow` 不会进入 `TTSComfyUIConfig`。本地 TTS 默认 `inference_mode="local"`，不依赖这个工作流；ComfyUI TTS 模式才会受影响。

密钥只从 `config.yaml` 读取。源码中当前未发现硬编码 API Key。`config.yaml` 被 `.gitignore` 预期忽略（示例文件头部写明不要提交）。

## 7. 进度模型

`pixelle_video/models/progress.py` `ProgressEvent` 字段：`event_type`、`progress`（0–1）、可选 `frame_current`、`frame_total`、`step`、`action`、`extra_info`。

Web 把回调直接传进管线，能更新 Streamlit 进度条。

API `TaskManager.update_progress()` 存在，但 `api/routers/video.py` `generate_video_async()` 的注释写着进度回调可以以后再加，当前 `video_params` 没有传入 `progress_callback`。所以 API 任务状态只有 pending/running/completed/failed/cancelled，进度百分比当前不会随分镜前进。

## 8. 适合商品工作台的扩展点

应新增，不应改默认行为的位置：

| 扩展点 | 原因 |
| --- | --- |
| 新管线类，注册为 `pipelines["goodthings"]` | `generate_video(pipeline=...)` 已支持按名分发 |
| 新的 Web Tab 或 `st.Page` | Home 已按 UI 类分发，加页面不需要改标准三列 |
| 新的 prompt 模块 | 现有 prompt 是主题/素材营销，不是事实分级 |
| 扩展 `StoryboardFrame` 或在旁路保存时间轴 JSON | 现有帧没有 `start_time`、`source_type`、`transition` |
| 在 `VideoService` 上增加可选滤镜 | 拼接、叠图、静图成片已可用 |

不应作为扩展点的位置：

- 不要把商品字段塞进 `VideoGenerateRequest`。那是主题视频 API。
- 不要改 `StandardPipeline.produce_assets()` 的并行条件来承载商品任务。
- 不要让数字人 / i2v / 动作迁移按钮走商品管线。

## 9. 架构约束对第一版的含义

原项目是单进程 Python 应用。Web 和 API 是两个进程，共享同一套 `pixelle_video` 包、同一份 `config.yaml` 和挂载的 `output/`、`data/`。Docker Compose 没有数据库服务。

第一版商品工作台应继续是这个进程内的业务层。当前未发现必须引入 Redis、消息队列或第二个前端框架的技术缺口。缺的是业务实体和可恢复任务记录，不是算力调度框架。

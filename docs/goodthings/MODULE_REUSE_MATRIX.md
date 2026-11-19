# 模块复用矩阵

审计日期：2026-11-19。判定只基于当前源码，不假设上游计划中的能力已经实现。

判定含义：

- **直接复用**：按现有签名调用，不改实现。
- **包装复用**：外面加商品业务层，内部继续调用。
- **谨慎扩展**：可以加可选参数或新方法，不能改变默认行为。
- **不要复用为商品主路径**：能力存在，但和商品约束冲突，或成本过高。
- **当前缺失**：源码中没有对应实现，需要新增。

## 1. 生成与合成

| 模块 | 路径 / 符号 | 输入 | 输出 | 判定 | 改动会波及 |
| --- | --- | --- | --- | --- | --- |
| 核心入口 | `pixelle_video/service.py` `PixelleVideoCore.generate_video` | `text`、`pipeline`、kwargs | 管线返回值 | 包装复用。新增管线名，不改默认 `standard` | Web 标准流、批量流、`/api/video/generate/*` |
| 线性骨架 | `pipelines/linear.py` `LinearVideoPipeline` | `PipelineContext` | `VideoGenerationResult` | 直接复用为新管线基类 | 所有继承它的管线 |
| 标准主题管线 | `pipelines/standard.py` `StandardPipeline` | 主题或固定稿 | `VideoGenerationResult` | 不要改。保留原功能 | Web 标准按钮、API、批量 |
| 素材管线 | `pipelines/asset_based.py` `AssetBasedPipeline` | 素材路径、intent、duration | `PipelineContext` | 包装参考，不直接当商品管线。它会让 LLM 自由写口播，时长不被秒数锁死 | 素材成片 Tab |
| 自定义示例管线 | `pipelines/custom.py` `CustomPipeline` | `text` 加一组标准参数 | `VideoGenerationResult` | 不要在这个示例类上堆商品逻辑。它已注册为 `custom` | `generate_video(pipeline="custom")` |
| 分镜处理器 | `services/frame_processor.py` `FrameProcessor.__call__` | `StoryboardFrame`、`Storyboard`、`StoryboardConfig` | 填好路径的帧 | 直接复用。已支持跳过已有音频和已有媒体 | 标准管线、素材管线 |
| HTML 画幅 | `services/frame_html.py` `HTMLFrameGenerator` | 模板路径、title、text、image、ext | PNG | 直接复用。新模板放到 `templates/1080x1920/` | 所有分镜字幕 |
| 合成 | `services/video.py` `VideoService` | 片段、音频、BGM | MP4 | 直接复用 `concat_videos`、`create_video_from_image`、`overlay_image_on_video`、`merge_audio_video` | 所有成片 |
| 镜头缩放 / 推近 | `VideoService` | — | — | 当前缺失。`create_video_from_image()` 是静止画面 | 若新增，应是可选参数，默认保持静止 |
| 转场 | `VideoService.concat_videos` | 片段列表 | 一条 MP4 | 当前缺失。默认 demuxer 硬拼接，无 `xfade` | 不要改默认 demuxer 行为 |
| TTS | `services/tts_service.py` `TTSService.__call__` | 文本、voice、speed、mode | MP3 路径 | 直接复用。女声用 `zh-CN-XiaoxiaoNeural` 或 `zh-CN-XiaoyiNeural` | 所有口播 |
| Edge 重试 | `utils/tts_util.py` `edge_tts` | 文本、voice、rate | 音频字节并写文件 | 直接复用 | 本地 TTS |
| BGM | `VideoService._resolve_bgm_path`、`concat_videos` | 路径或文件名、音量、loop/once | 混音后的 MP4 | 直接复用。音量是整片级 | 所有成片 |
| LLM | `services/llm_service.py` `LLMService.__call__` | prompt、可选 `response_type` | 字符串或 Pydantic 对象 | 直接复用。商品分析用新的 response model | 所有文案 |
| 主题文案 | `utils/content_generators.py` | 主题、场景数 | 旁白、标题、图片提示词 | 不要复用为商品口播。可复用标题清洗思路 | 标准管线、`/api/content/*` |
| 素材脚本提示词 | `prompts/asset_script_generation.py` | intent、时长、素材描述 | prompt 字符串 | 不要直接复用。没有事实分级 | 素材管线 |
| 图片提示词 | `prompts/image_generation.py`、`utils/prompt_helper.py` `build_image_prompt` | 旁白、前缀 | 英文/风格化提示词 | 只适合环境镜头。不能用来生成功效对比图 | 标准管线出图 |
| Comfy 媒体 | `services/media.py` `MediaService` | prompt、workflow、宽高、时长 | `MediaResult` | 谨慎扩展。商品默认链路不应依赖它 | 标准出图、数字人、i2v、动作迁移 |
| API 媒体 | `services/api_media.py` `APIProviderMediaService` | `api/...` 工作流键 | `MediaResult` | 不要作为默认路径。保留为可选环境视频 | 所有 API 出图出视频 |
| 图片理解 | `services/image_analysis.py` `ImageAnalysisService` | 本地图片路径、source、workflow | 描述字符串 | 包装复用。描述不能直接进最终口播 | 素材成片 |
| 视频理解 | `services/video_analysis.py` `VideoAnalysisService` | 本地视频路径 | 描述字符串 | 包装复用 | 素材成片 |
| API 视觉理解 | `services/api_asset_analysis.py` `APIAssetAnalysisService` | 图片或视频、model | 描述字符串 | 包装复用。比 Comfy 分析更符合低成本约束，仍需人工核对 | 素材成片的 `source="api"` |

## 2. 数据、任务、界面

| 模块 | 路径 / 符号 | 判定 | 说明 |
| --- | --- | --- | --- |
| 分镜模型 | `models/storyboard.py` `Storyboard`、`StoryboardFrame`、`StoryboardConfig` | 谨慎扩展 | 已有 `narration`、`image_prompt`、`duration`、媒体路径。没有 `start_time`、`source_type`、`transition`、`effect`、`asset_id`。加可选字段比另起一套渲染模型安全 |
| 进度事件 | `models/progress.py` `ProgressEvent` | 直接复用 | Web 已经消费它 |
| 成片结果 | `models/storyboard.py` `VideoGenerationResult` | 直接复用 | `video_path`、`duration`、`file_size`、`storyboard` |
| 文件持久化 | `services/persistence.py` `PersistenceService` | 包装参考 | 只保存成片任务的 `metadata.json` / `storyboard.json`。不能表达商品、项目、授权 |
| 历史 | `services/history_manager.py` `HistoryManager` | 直接复用现有历史页 | `regenerate_frame()`、`export_task()` 是空实现，不能当成可重合成能力 |
| API 任务 | `api/tasks/manager.py` `TaskManager` | 不要当成商品任务库 | 内存字典，无重试，无恢复，进度回调未接入视频接口 |
| 任务模型 | `api/tasks/models.py` `Task`、`TaskStatus` | 可参考状态枚举 | 只有 `video_generation` 一种 `TaskType` |
| 配置 | `config/schema.py` `PixelleVideoConfig` | 谨慎扩展 | 可加商品模板默认音色。不要把商品库放进 YAML |
| 路径工具 | `utils/os_util.py` `create_task_output_dir`、`get_task_frame_path` | 直接复用 | 任务目录隔离已经做好 |
| 模板工具 | `utils/template_util.py` | 直接复用 | 尺寸、列表、类型判断 |
| 标准 UI | `web/pipelines/standard.py`、`web/components/output_preview.py` | 不要改主流程 | 原主题成片按钮在这里 |
| 素材 UI | `web/pipelines/asset_based.py` | 可参考上传写法 | 业务规则在 UI 里，商品版不应照搬 |
| 历史页 | `web/pages/2_📚_History.py` | 直接复用 | 继续服务原成片。商品项目需要自己的列表 |
| 设置页 | `web/components/settings.py` `render_advanced_settings` | 直接复用 | LLM 与 ComfyUI 配置已在这里 |
| 批量 | `web/utils/batch_manager.py` `SimpleBatchManager` | 第一版不要复用为商品批量 | 只循环主题，失败不恢复 |
| 文件服务 | `api/routers/files.py` `get_file` | 谨慎复用 | 能读 `output/`，但是路径拼接，没有鉴权 |
| 健康检查 | `api/routers/health.py` | 直接复用 | 不承载业务 |

## 3. 旁路，商品第一版不要接入

| 模块 | 路径 | 原因 |
| --- | --- | --- |
| 数字人 | `web/pipelines/digital_human.py` | 直接调 `media()`，面向人物口型，不是商品六段 |
| 图生视频 Tab | `web/pipelines/i2v.py` | 单素材 AI 视频，成本高 |
| 动作迁移 | `web/pipelines/action_transfer.py` | 用参考视频驱动图片，不适合真实使用过程 |
| RunningHub 工作流 | `workflows/runninghub/*.json` | 可用，但依赖外部额度和并发限制 |
| moviepy 依赖 | `pyproject.toml` 有 `moviepy==1.0.3` | 成片主路径实际是 `ffmpeg-python`。当前未发现商品可复用的 moviepy 合成入口 |

## 4. 商品目标对照

| 商品能力 | 最接近的现有模块 | 能否直接满足 | 建议 |
| --- | --- | --- | --- |
| 商品信息识别 | `ImageAnalysisService` / `APIAssetAnalysisService` | 否。只返回自由描述 | 新分析服务，输出事实分级 |
| 卖点提取 | `LLMService` 结构化输出 | 调用方式能复用，提示词不能复用 | 新 Pydantic 模型 |
| 带货策划 | `generate_narrations_from_topic`、`VideoScript` | 否 | 新策划服务 |
| 六段分镜 | `StoryboardFrame` | 数据结构不够 | 新时间轴，渲染时再映射到 `StoryboardFrame` |
| 真实素材 | 素材管线上传 + `FrameProcessor` 跳过生成 | 上传和合成可复用 | 新素材表，带类型和授权 |
| AI 场景图 | `MediaService` | 可复用，必须默认关闭关键镜头 | 只允许环境镜头调用 |
| 配音字幕 | `TTSService` + HTML 模板 | 配音可复用；独立字幕文件当前缺失 | 口播进 TTS，字幕继续烧进模板，另存文本供编辑 |
| 合成导出 | `VideoService` + `st.video` / `st.download_button` | 合成可复用；逐镜头替换当前缺失 | 新预览页调用现有合成 |
| 可追踪可重试 | `PersistenceService` 成功记录；API 内存任务 | 否 | 新的任务记录。第一版用 SQLite 或 JSON 文件，不引入 Redis |

## 5. 复用原则

1. `StandardPipeline`、标准 UI 按钮、`/api/video/generate/sync|async` 保持原参数和行为。
2. 商品链路新增独立模块，通过新的 pipeline 名或新的服务类调用现有 TTS、HTML、FFmpeg。
3. 只有在现有函数无法表达商品时间轴时，才给 `VideoService` 加可选参数。默认参数必须保持今天的静止画面和硬拼接。
4. 不把商品规则写进 `output_preview.py` 或 `asset_based.py`。

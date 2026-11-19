# 模板系统分析

审计日期：2026-11-19。结论来自 `templates/`、`pixelle_video/services/frame_html.py`、`pixelle_video/utils/template_util.py` 和调用它们的管线。

## 1. 目录结构

模板按成片分辨率分目录，不是按业务场景分目录。

`templates/1080x1920/`（竖屏，商品短视频需要的比例）：

- 图片类：`image_default.html`、`image_modern.html`、`image_elegant.html`、`image_full.html`、`image_book.html`、`image_cartoon.html`、`image_blur_card.html`、`image_excerpt.html`、`image_fashion_vintage.html`、`image_healing.html`、`image_health_preservation.html`、`image_life_insights.html`、`image_life_insights_light.html`、`image_long_text.html`、`image_neon.html`、`image_psychology_card.html`、`image_purple.html`、`image_satirical_cartoon.html`、`image_simple_black.html`、`image_simple_line_drawing.html`
- 静态类：`static_default.html`、`static_excerpt.html`
- 视频类：`video_default.html`、`video_healing.html`
- 素材类：`asset_default.html`

`templates/1080x1080/`：`image_minimal_framed.html`。

`templates/1920x1080/`：`image_book.html`、`image_film.html`、`image_full.html`、`image_ultrawide_minimal.html`、`image_wide_darktech.html`。

自定义模板覆盖规则在 `template_util.py`：先查 `data/templates/`，再查 `templates/`。`get_template_full_path()` 和 `resolve_template_path()` 都走这套资源查找。

预览图在 `docs/images/{size}/`，由 `web/components/style_config.py` `get_template_preview_path()` 使用。它们不是渲染模板。

当前未发现 `goodthings_fast_30s` 或任何带货专用模板。

## 2. HTML 如何加载

`HTMLFrameGenerator.__init__(template_path)`：

1. `_load_template()` 按 UTF-8 读整个 HTML。
2. `parse_template_size(template_path)` 从父目录名解析成片宽高。目录名必须是 `WIDTHxHEIGHT`。
3. `generate_frame()` 替换占位符后，用 Playwright 开页面，viewport 设为解析出的宽高，截 PNG。

调用点：

- `FrameProcessor._compose_frame_html()`：`resolve_template_path(config.frame_template)` 后 `HTMLFrameGenerator(template_path).generate_frame(...)`。
- `api/routers/frame.py` `render_frame()`：单独渲染一帧，不合成视频。
- `api/routers/video.py`：用同一个类的 `get_media_size()` 填 AI 媒体宽高。

`generate_frame()` 输入：`title`、`text`、`image`、`ext`、`output_path`。输出：PNG 路径。

本地图片会被转成 `file://` URI。视频路径也可以传进 `image` 参数，但 `asset_default.html` 的脚本只在值像图片时插入 `<img>`。视频画面不是由 HTML 播放的，而是后面 `overlay_image_on_video()` 把透明字幕 PNG 叠到视频上。

## 3. 参数如何传递

内置占位符在 `HTMLFrameGenerator.parse_template_parameters()` 里被排除：`title`、`text`、`image`、`index`。

自定义占位符语法：

```text
{{param}}
{{param=默认值}}
{{param:type}}
{{param:type=默认值}}
```

`type` 只支持 `text`、`number`、`color`、`bool`。

传递路径：

1. Web `style_config.py` 解析模板参数，放进 `template_params`。
2. `StoryboardConfig.template_params` 保存。
3. `FrameProcessor._compose_frame_html()` 把 `template_params` 放进 `ext`。
4. `generate_frame()` 把 `ext` 合并进替换字典。
5. `_replace_parameters()` 替换占位符。

API 对应字段是 `VideoGenerateRequest.template_params`。发现接口是 `GET` 模板参数，实现于 `api/routers/frame.py` `get_template_params()`。

当前未发现把「镜头时长」「转场」「缩放」作为模板参数。模板参数是视觉样式，不是时间轴。

## 4. 视频尺寸

有两套尺寸，不能混用。

| 尺寸 | 来源 | 作用 |
| --- | --- | --- |
| 成片尺寸 | 目录名，`parse_template_size()` | Playwright viewport，最终 PNG/视频宽高 |
| AI 媒体尺寸 | HTML meta `template:media-width`、`template:media-height` | 传给 `MediaService` 的 `width`/`height` |

`HTMLFrameGenerator.get_media_size()` 读 meta。没有 meta 时回退 `1024x1024`。

抽查：

- `templates/1080x1920/image_default.html`：body/page 为 `1080x1920`，meta 为 `1024`。
- `templates/1080x1920/asset_default.html`：同样是页面 `1080x1920`，meta `1024`。

因此现有竖屏模板可以输出 1080×1920 画面。AI 出图默认不是 1080×1920，而是模板 meta 里的 1024×1024，再由 HTML `object-fit` 放进竖屏。商品模板如果要让真实商品图按 9:16 生成，必须单独写 meta，不能假设目录名会传给出图接口。

`StoryboardConfig.video_fps` 默认 30。`create_video_from_image()` 使用这个 fps。API `video_fps` 范围 15–60，默认 30。

当前未发现在模板里配置帧率。帧率来自管线参数，不来自 HTML。

## 5. 单镜头时长

当前未发现每个镜头单独配置时长的模板字段或渲染参数。

实际规则：

1. `FrameProcessor._step_generate_audio()` 用 TTS 音频时长写入 `frame.duration`。
2. 视频类工作流把这个时长传给 `MediaService` 的 `duration`。
3. `create_video_from_image()` 用 `-t audio_duration` 让静图视频等于音频长度。
4. `merge_audio_video()` 在视频短于音频时冻结尾帧，长于音频超过 `duration_tolerance=0.3` 秒时裁切。

`AssetBasedPipeline` 的 `SceneScript.duration` 是 LLM 估计值。`initialize_storyboard()` 没有把它写入 `StoryboardFrame`。后面 `produce_assets()` 用 ffprobe 重写 `frame.duration`。所以脚本里的秒数不控制成片。

`n_scenes` 只控制段数。标准 UI 滑块是 3–30，默认 5。设成 6 只能得到 6 段口播，不能得到 3 秒、4 秒、6 秒这种固定槽位。

## 6. 字幕和音频如何渲染

字幕：

- 没有 SRT、ASS 或独立字幕轨。全仓库 `*.py` / `*.html` / `*.yaml` 中当前未发现 `.srt`。
- 旁白文本放进 HTML `{{text}}`。
- Playwright 把整页截成 PNG，字幕成为画面像素。
- `asset_default.html` 使用 `PingFang SC`、`Source Han Sans`、`Microsoft YaHei`。字号 52px，居中，底部。
- Docker 安装了 `fonts-noto-cjk`（`Dockerfile`）。macOS 本机是否有这些字体，源码不检查，只在 Linux 上调用 `_check_linux_dependencies()`。

音频：

- 口播是每镜头一个 MP3，再和画面合成。
- 用户视频原声在 `replace_audio=True` 时被替换。
- BGM 在全部镜头拼接之后混入，音量是整片一个浮点。
- 当前未发现口播和 BGM 的逐镜头音量。

字幕修改意味着重新渲染该镜头 HTML，再重新合成该镜头 MP4。当前没有只改字幕、不重跑 TTS 的公开函数。技术上可以手动保留 `audio_path` 再调用 `FrameProcessor`，因为已有 `audio_path` 会跳过 TTS。这个跳过逻辑存在，但没有产品级「只重渲染字幕」入口。

## 7. 能否实现六段式时间轴

现有模板系统能提供：

- 9:16 画布：`1080x1920`。
- 30fps：`StoryboardConfig.video_fps`。
- 大字短句：靠 HTML/CSS，不靠渲染引擎。
- 硬切：`concat_videos()` 的 demuxer 本身就是硬拼。
- 女声和 1.2 倍速：TTS 参数，与模板无关。

现有模板系统不能提供：

- 镜头一 0–3 秒、镜头二 3–7 秒这类固定槽位。
- 每镜头独立时长编辑，且编辑后不重写口播分析。
- 推近、局部特写、镜头缩放。`create_video_from_image()` 没有 zoompan 或 crop 动画。
- 把时间轴写在模板外、渲染时读取。模板只决定一帧的版式。

`asset_default.html` 适合作为商品竖屏字幕层的起点：它已经区分「图片放进背景层」和「视频留空、稍后叠加」。它不适合作为六段式时间轴本身。

## 8. 对商品模板的判断

原有模板系统能满足画幅、字幕烧录和单帧参数，不能满足商品视频的时间结构。

建议在阶段 B 确认后新增模板文件，例如 `templates/1080x1920/goodthings_fast_30s.html`，只负责版式和账号口号样式。六段时长放在独立的分镜数据里，不写进这个 HTML，也不写进 `FrameProcessor` 的常量。

在那之前，不要改 `image_default.html` 或 `asset_default.html`。标准管线默认模板是 `config.example.yaml` 的 `1080x1920/image_default.html`。

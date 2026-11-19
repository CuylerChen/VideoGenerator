# GoodThings Studio 改造计划（审计草案）

状态：阶段 A 草案，供人工审核。本文不是实施许可。审核通过前不改业务代码，不进入阶段 B 的详细设计确认，也不开始阶段 C。

依据：`SOURCE_AUDIT.md`、`ARCHITECTURE_ANALYSIS.md`、`MODULE_REUSE_MATRIX.md`、`TEMPLATE_ANALYSIS.md`、`MEDIA_PIPELINE_ANALYSIS.md`、`DATABASE_AND_STORAGE_ANALYSIS.md`。

## 1. 审计后的判断

Pixelle-Video 已经有一条可复用的成片引擎：

```text
TTSService -> FrameProcessor -> HTMLFrameGenerator -> VideoService.concat_videos
```

它还有一条更接近商品视频的入口：用户上传素材、视觉模型描述、LLM 分配镜头、再进入同一合成器。这条入口是 `AssetBasedPipeline`。

它没有商品业务层。直接把「好物研究所」的规则写进 `StandardPipeline` 或 `AssetBasedPipeline`，会破坏原有主题成片和素材成片。

第一版应新增独立业务包，在渲染前把商品时间轴映射成现有 `StoryboardFrame`，然后调用现有 `FrameProcessor` 和 `VideoService`。

## 2. 不应改动的部分

| 对象 | 原因 |
| --- | --- |
| `StandardPipeline` 的步骤顺序和默认参数 | API 与标准按钮依赖它 |
| `web/components/output_preview.py` 的标准生成参数 | 原「生成」按钮 |
| `/api/video/generate/sync` 与 `/async` 的请求体 | 上游调用方 |
| `web/pipelines/digital_human.py`、`i2v.py`、`action_transfer.py` | 旁路功能，与商品六段无关 |
| `LICENSE`、`NOTICE` | 任务书要求保留 |
| 内置 `templates/1080x1920/image_default.html` | 配置示例的默认模板 |

允许的最小触点，且必须在阶段 B 确认后才做：

- `PixelleVideoCore.initialize()` 增加一个新管线注册项。
- `web/app.py` 或 `web/pipelines/__init__.py` 增加新页面或新 Tab。
- `VideoService` 仅在确需推近时增加可选参数，默认行为不变。

## 3. 建议的新增边界

新代码放在独立包，例如 `goodthings/`，不要散进 `web/components/`。

```text
goodthings/
  models.py              Product、VideoProject、StoryboardSegment、MediaAsset、RenderTask
  store.py               SQLite 或 JSON 存储，带 owner_id 空字段
  analysis.py            商品分析。输出事实 / 宣传说法 / 推测 / 未知
  planning.py            钩子、标题、口播、六段分镜、封面文案、发布描述
  assets.py              上传、绑定、来源、授权、优先级
  timeline.py            时间轴。时长可编辑，不写死在渲染器
  pipeline.py            只负责把时间轴交给现有 FrameProcessor 和 VideoService
  prompts.py             商品提示词。禁止未证实功效进入口播
web/pages/               五个业务页，只调用 goodthings 服务
templates/1080x1920/goodthings_fast_30s.html
```

`pipeline.py` 可以继承 `LinearVideoPipeline`，也可以作为普通服务调用 `self.core.tts`、`self.core.frame_processor`、`self.core.video`。继承与否在阶段 B 再定。无论哪种，都不要注册成默认管线。

## 4. 业务模块与现有能力的接法

### 4.1 商品档案

新增。字段按任务书：名称、分类、规格、介绍、卖点、场景、用法、注意事项、图片、视频、来源、授权。

链接解析做成可替换适配器接口。第一版实现「粘贴文本后人工确认」和「上传图片」。当前未发现可合法复用的抖音抓取器，也不应新增绕过登录的抓取。

### 4.2 商品分析

复用 `LLMService.__call__(response_type=...)`。视觉描述可调用 `APIAssetAnalysisService`，因为它不强制 ComfyUI。

输出必须分四类：已确认事实、宣传资料说法、AI 推测、未知。口播生成函数只读取已确认事实，以及用户明确勾选采用的宣传说法。这个过滤放在 `planning.py`，不放在 UI。

### 4.3 内容策划

新增结构化输出，至少包括：3 个钩子、3 个标题、1 个主题、1 条口播、6 段分镜、6 段字幕、6 段镜头描述、环境图提示词、补拍清单、封面文案、发布描述。

不要调用 `generate_narrations_from_topic()` 充当口播。那个函数的合同是主题短视频，没有事实边界。

所有字段落在项目记录里，允许单独修改。修改一段时只更新该段，不重新调用分析。

### 4.4 时间轴

新增 `StoryboardSegment`，字段按任务书：`segment_id`、`sequence`、`start_time`、`duration`、`asset_id`、`asset_type`、`caption`、`voice_text`、`transition`、`effect`、`source_type`。

默认六段时长：3、4、6、8、4、5 秒，对应 0–3、3–7、7–13、13–21、21–25、25–30。这些数字放在模板配置数据里，不放在 `FrameProcessor`。

渲染时的映射：

- 有真实图片或真实视频：`image_prompt=None`，填 `image_path` 或 `video_path`。
- 只有环境镜头才填 `image_prompt`。
- `voice_text` 送 TTS。`caption` 送 HTML `text`。现有 `StoryboardFrame` 只有 `narration`，所以要在调用 `FrameProcessor` 之前决定这一帧烧录哪一段文字。若口播和字幕必须同时存在，阶段 B 需要决定是扩展帧字段，还是先合成字幕帧再把已有 `audio_path` 交给处理器。后者可以不改 `FrameProcessor`。

时长缺口是本计划的最大技术风险。现有合成让音频决定画面时长。固定 3 秒镜头需要一层适配：

- 口播短于槽位：静图继续显示，或视频冻结尾帧。`merge_audio_video(pad_strategy="freeze")` 已能垫视频，但是它垫的是「音频更长」的情况。槽位长于音频时，需要先按目标秒数生成画面，再把音频尾部补静音。当前未发现现成的「按目标秒数拉长静图」参数。`create_video_from_image()` 的时长来自音频。
- 口播长于槽位：裁音频或提示用户缩短文案。当前未发现按业务槽位裁 TTS 的函数。`_trim_video_to_duration()` 裁的是视频。

阶段 B 应先选定一种策略再写代码。建议默认「文案过长则拒绝合成并提示缩短」，避免把卖点从句中截断。不要在渲染器里写死 28 秒。

### 4.5 素材

新素材记录至少包含任务书列出的 ID、商品、项目、类型、路径、来源、授权、创建时间、使用状态。

优先级放在 `assets.py`：

1. 真实商品图优先于 AI 商品图。
2. 真实使用视频优先于 AI 演示。
3. AI 只生成环境、氛围、非关键镜头。
4. 不调用出图来做清洁前后对比、评价截图或功效证明。

文件仍可放在 `output/` 或 `data/goodthings/assets/`。不要写死某一台机器的绝对路径。引用存相对路径或素材 ID。

### 4.6 合成与预览

复用：

- `TTSService`，音色 `zh-CN-XiaoxiaoNeural` 或 `zh-CN-XiaoyiNeural`，语速 `1.2`。
- `HTMLFrameGenerator`，新模板 `1080x1920/goodthings_fast_30s.html`。
- `VideoService.create_video_from_image()`、`overlay_image_on_video()`、`concat_videos()`。
- `st.video()` 与 `st.download_button` 的预览下载方式。

推近和局部特写：阶段 B 评估是否给 `VideoService` 加可选 zoom。做不到之前，第一版可以用硬切和真实特写素材满足「镜头切换」，不要假装已经有 Ken Burns。

转场：现有拼接就是硬切。第一版使用硬切，不新增 `xfade`，除非审核明确要求。

重合成：按段读取时间轴，只对改动段重跑 TTS 或 HTML。不要调用整次商品分析。`HistoryManager.regenerate_frame()` 是空函数，不要依赖它。

## 5. 页面

继续用 Streamlit。`web/app.py` 已用 `st.navigation`。五个页面作为新的 `st.Page`，不重写 Home。

| 页面 | 第一版数据来源 |
| --- | --- |
| 商品工作台 | 新存储的商品数、项目数、最近成片、进行中和失败任务 |
| 商品创建 | 表单、上传、分析服务 |
| 脚本工作台 | 策划结果，逐段保存 |
| 素材工作台 | 素材记录与授权 |
| 预览导出 | 成片路径、逐段替换、重合成、下载 |

原 Home 和 History 保留。

## 6. 存储建议

审核时二选一：

| 方案 | 优点 | 代价 |
| --- | --- | --- |
| SQLite 单文件，放在 `data/goodthings/goodthings.db` | 状态更新、按商品查询、失败任务保留都直接 | 新增驱动依赖，需记录许可证 |
| `data/goodthings/` JSON 文件 | 零新基础设施 | 并发写入和查询更容易出错 |

不建议第一版使用 Postgres、Redis 或消息队列。原项目没有这些服务，任务书也要求不做未经必要的基础设施。

任务记录至少保存：输入快照、当前步骤、错误、已完成帧路径、可重试标记。进程退出后靠这条记录恢复，不靠 `api/tasks/manager.py`。

## 7. 原功能回归范围

每完成一个商品模块后，至少手动确认：

1. Home 标准 Tab 仍能用主题文本调用 `generate_video()`。
2. 素材成片 Tab 仍走 `AssetBasedPipeline`。
3. History 仍能列出旧的 `output/.index.json`。
4. `/api/video/generate/sync` 的请求体无需新字段。

当前仓库没有 `tests/`。商品关键模块需要新测试。原项目没有可直接跑的自动化回归，这一点要在实施时补，而不能假装上游测试会兜住。

## 8. 风险

| 风险 | 证据 | 处理 |
| --- | --- | --- |
| 时长锁不住 | `frame.duration` 来自 TTS；`SceneScript.duration` 未被渲染使用 | 阶段 B 先定超时策略，再写合成适配 |
| LLM 编造功效 | 现有提示词没有事实分级 | 新提示词加输出过滤，不改旧提示词 |
| 错误素材被静默替换 | `AssetBasedPipeline.generate_content()` 回退到第一个素材 | 商品链路匹配失败则停下来，不回退 |
| 用户视频原声丢失 | `replace_audio=True` | 商品默认接受口播覆盖；若要保留原声，阶段 B 单独设计 |
| AI 出图前缀是火柴人 | `config.example.yaml` `prompt_prefix` | 商品环境图使用自己的前缀，不改全局默认 |
| 默认音色是男声 | `TTSLocalConfig.voice` | 只在商品配置里指定女声 |
| API 任务不能恢复 | `TaskManager` 内存字典 | 商品任务不使用它作为账本 |
| 无鉴权文件接口 | `api/routers/files.py` | 第一版本机预览，不把商品库挂到该路由 |
| 半成品目录残留 | 失败不写 metadata | 新任务记录指向任务目录，失败也落盘 |
| 字幕字体在 macOS 依赖本机字体 | HTML 指定 PingFang / 思源黑体；Docker 才安装 Noto CJK | 模板使用已安装的 CJK 字体栈，并在验收时看中文 |

## 9. 成本边界

默认路径：

- LLM 使用现有 OpenAI 兼容配置，优先已有的低价模型。
- TTS 使用 Edge TTS。
- 画面使用真实图片、真实视频和静图合成。
- 不出 AI 商品视频。
- 只有环境镜头、且用户确认后才调用 `MediaService`。

这与源码能力一致，不需要新的视频供应商。

## 10. 阶段门槛

阶段 A：本文档组已写完。停止。

阶段 B：审核通过后，再写出最终文件清单、表结构、API 和模板稿。仍不写实现，直到用户确认。

阶段 C 及以后：按确认后的清单逐模块实现、测试、提交。验收商品是「净浮生油污净」。那一步现在不做。

## 11. 本次没有做的事

- 没有修改 `pixelle_video/`、`web/`、`api/`、`templates/`、`workflows/`。
- 没有新增依赖。
- 没有克隆远程仓库之外的代码。本地目录已经是源码。
- 没有运行视频生成。审计结论来自阅读实现，不是来自一次成功成片。

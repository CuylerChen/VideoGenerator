# 数据与存储分析

审计日期：2026-11-19。检索范围包括 `*.py`、`*.yaml`、`*.yml`、`*.toml`。

## 1. 结论

当前未发现数据库。全仓库没有 `sqlite`、`sqlalchemy`、`postgres`、`redis`、`celery` 的实现引用。

当前未发现业务实体：`Product`、`ProductImage`、`VideoProject`、`VideoScript`、`MediaAsset`、`RenderTask`、`GeneratedVideo` 均不存在。现有最接近的对象是一次成片的 `Storyboard`。

当前未发现 `user_id` 或 `owner_id`。`docker-compose.yml` 注释写 `data/` 包含 `users/`，源码中没有读写 `data/users` 的逻辑。多租户当前未发现。

原项目的持久化不适合直接承载商品档案。商品模块需要新增存储。第一版不需要 Redis 或消息队列。

## 2. 现有存储

### 2.1 配置

| 项 | 位置 |
| --- | --- |
| 示例 | `config.example.yaml` |
| 运行时 | `config.yaml`，由 `pixelle_video/config/loader.py` `load_config_dict()` 读取 |
| 模型 | `pixelle_video/config/schema.py` `PixelleVideoConfig` |
| 管理 | `config/manager.py` `ConfigManager` 单例，`save()` / `update()` |

内容是 LLM、供应商密钥、ComfyUI、默认模板。不是业务数据。

### 2.2 成片目录

`utils/os_util.py` `create_task_output_dir()` 创建：

```text
output/{YYYYMMDD_HHMMSS_xxxx}/
  frames/
    01_audio.mp3
    01_image.png
    01_video.mp4
    01_composed.png
    01_segment.mp4
  final.mp4          # 标准管线
  metadata.json
  storyboard.json
```

任务 ID 由 `create_task_id()` 生成：时间戳加 4 位十六进制。不是 UUID，也不是商品 ID。

素材管线的最终文件名是 `{title}.mp4` 或 `{task_id}.mp4`，放在同一任务目录，不一定叫 `final.mp4`（`AssetBasedPipeline.post_production()`）。

### 2.3 元数据

`PersistenceService`（`pixelle_video/services/persistence.py`）：

| 方法 | 作用 |
| --- | --- |
| `save_task_metadata()` | 写 `metadata.json`，并更新 `output/.index.json` |
| `load_task_metadata()` | 读取 |
| `save_storyboard()` / `load_storyboard()` | `storyboard.json` |
| `list_tasks()` / `list_tasks_paginated()` | 读索引 |
| `update_task_status()` | 能改状态字段 |
| `delete_task()` | 删任务目录和索引项 |
| `get_statistics()` | 数量、时长、体积汇总 |
| `rebuild_index()` | 扫描目录重建索引 |

`metadata.json` 结构由调用方组装，不是数据库表。标准管线写入 `task_id`、`created_at`、`completed_at`、`status="completed"`、`input`、`result`、`config`。素材管线额外写 `assets`、`intent`、`duration`、`source`。

`storyboard.json` 由 `_storyboard_to_dict()` 序列化 `Storyboard`、`StoryboardConfig`、`StoryboardFrame`。帧字段包括 `narration`、`image_prompt`、`audio_path`、`media_type`、`image_path`、`video_path`、`composed_image_path`、`video_segment_path`、`duration`。

当前未发现在失败时调用 `update_task_status()`。两个管线都只在 `finalize()` 成功后保存，状态写死 `"completed"`。

### 2.4 历史索引

`output/.index.json` 是列表缓存。`HistoryManager` 是它的薄封装：

- `get_task_list()`
- `get_task_detail()`
- `get_statistics()`
- `delete_task()`
- `duplicate_task()`：只返回原任务的 `input` 参数，不复制文件，不重新生成。
- `regenerate_frame()`：记录 warning 并返回 `None`。注释写 FUTURE FEATURE。
- `export_task()`：同样未实现。

Web 历史页 `web/pages/2_📚_History.py` 读取这个索引，提供卡片、详情和删除。它是成片历史，不是商品项目历史。

### 2.5 临时文件与资源覆盖

| 路径 | 用途 |
| --- | --- |
| `temp/` | 上传素材、TTS 临时文件、ffmpeg 临时片段 |
| `data/templates/` | 覆盖内置 HTML |
| `data/bgm/` | 覆盖或追加 BGM |
| `data/workflows/` | 自定义工作流，由资源查找函数支持 |
| `bgm/` | 内置 BGM，当前只有 `default.mp3` |
| `workflows/` | 内置 Comfy JSON |
| `resources/` | 文档图片，不是素材库 |

`os_util.py` 的资源函数约定：自定义目录优先于内置目录。

## 3. 任务机制

这里有两套互不相通的「任务」。

### 3.1 成片任务

ID 是输出目录名。生命周期：

1. `create_task_output_dir()` 建目录。
2. 管线在内存中的 `PipelineContext` 里推进。
3. 成功后写 JSON。
4. 失败则目录可能留下半成品，索引里没有这条记录。

并发：

- Web 标准生成一次一个按钮请求。
- 批量 `SimpleBatchManager.execute_batch()` 是 for 循环，串行。
- `StandardPipeline` 在 RunningHub 工作流且 `runninghub_concurrent_limit > 1` 时，用 `asyncio.Semaphore` 并行处理帧。限制来自配置，范围 1–10。
- 素材管线帧处理是串行。

进度：

- Web 有 `ProgressEvent` 回调，只活在当前页面会话。
- 刷新页面后，当前未发现恢复进度条或接着跑。

重试：

- Edge TTS、DashScope 视频客户端、Kling HTTP 适配器、出图客户端有网络级重试。
- 当前未发现「把失败的成片任务按原参数再跑一遍」的服务方法。历史页的复制只是把输入参数交还 UI。

中断恢复：

- 当前未发现检查点。
- 当前未发现读取已有 `01_audio.mp3` 并跳过该帧的恢复器。`FrameProcessor` 只会在同一次调用里、对象上已经有 `audio_path` 时跳过。进程重启后没有代码重新装载半成品帧并继续。

### 3.2 API 内存任务

`api/tasks/manager.py` `TaskManager`：

| 能力 | 现状 |
| --- | --- |
| 存储 | `self._tasks: Dict[str, Task]`，注释写 in-memory，可以后换 Redis。当前未发现 Redis 实现 |
| 创建 | `create_task()`，UUID |
| 执行 | `execute_task()`，`asyncio.create_task` |
| 状态 | `pending`、`running`、`completed`、`failed`、`cancelled` |
| 进度 | `update_progress()` 存在 |
| 视频接口是否上报进度 | 否。`api/routers/video.py` 没有把回调接进去 |
| 取消 | `cancel_task()` 会 cancel future。已经在跑的 ffmpeg 子进程是否随之停止，当前代码没有额外处理 |
| 并发上限 | `api/config.py` `max_concurrent_tasks = 5`。全仓库只有这一处赋值，`TaskManager` 没有读取它 |
| 清理 | 完成、失败、取消的任务在 `task_retention_time`（86400 秒）后从内存删除 |
| 重启 | `stop()` 清空字典。进程退出即丢失 |
| 重试 | 当前未发现 |
| 与成片目录的关系 | 不持久绑定。成功结果只留在内存 `task.result` 里，同时成片目录仍会由管线自己写入 |

API 路由：

- `GET /api/tasks`
- `GET /api/tasks/{task_id}`
- `POST /api/tasks/{task_id}/cancel`

实现文件：`api/routers/tasks.py`。

这套机制能跟踪一次 API 请求的生死，不能作为商品生产台的任务账本。

## 4. 和任务书数据模型的差距

| 建议实体 | 源码对应 | 判断 |
| --- | --- | --- |
| Product | 当前未发现 | 必须新增 |
| ProductImage | 当前未发现。上传文件只有临时路径 | 必须新增 |
| ProductAsset | 当前未发现 | 必须新增 |
| VideoProject | 成片任务目录近似一次渲染，不是可编辑项目 | 必须新增 |
| VideoScript | `asset_based.VideoScript` 是一次 LLM 响应模型，不落库 | 可借鉴字段，不能当存储 |
| Storyboard | `models/storyboard.py` `Storyboard` | 可作渲染输入。缺少商品时间轴字段 |
| StoryboardSegment | `StoryboardFrame` 接近，但时长、来源、转场、效果不完整 | 建议新结构，渲染前映射到 `StoryboardFrame` |
| MediaAsset | 当前未发现统一素材记录 | 必须新增 |
| VoiceConfig | 分散在 `TTSLocalConfig` 和调用参数 | 可先复用配置，不必单独建复杂系统 |
| VideoTemplate | 文件系统中的 HTML | 第一版继续用文件。模板注册表当前未发现 |
| RenderTask | API `Task` 或输出目录，二者都不完整 | 必须新增可恢复记录 |
| GeneratedVideo | `metadata.result.video_path` | 只有成功成片路径，没有版本和导出记录 |

## 5. 是否需要迁移

没有旧业务库，所以不存在从 Pixelle 业务表迁出的问题。

不能把商品数据塞进 `metadata.json`。那个文件的读者是历史页和 `HistoryManager`，字段约定是一次主题成片。混进去会让原历史页出现无法展示的记录，或者在删除任务时连带删掉商品档案。

建议：

- 成片文件继续放在 `output/`，继续复用 `create_task_output_dir()`。
- 商品、项目、分镜、素材索引新增独立存储。
- 第一版用 SQLite 单文件即可满足关系查询、状态更新和 `owner_id` 预留。当前项目没有数据库驱动，这会是一个新依赖。
- 若审核阶段希望零新依赖，可以用 `data/goodthings/*.json`。它能跑通 MVP，但任务状态更新和按商品查询会更脆。
- 当前未发现引入 Redis、消息队列的必要性。Web 本来就是进程内等待；失败重试可以由新的任务记录加上再次调用现有管线完成。

无论选哪种，实体里应保留可空的 `owner_id`。现在没有用户系统，不要在第一版实现登录。

## 6. 文件服务风险

`api/routers/files.py` `get_file()` 按允许前缀读文件：`output/`、`workflows/`、`templates/`、`bgm/`、`data/bgm/`、`data/templates/`、`resources/`。没有身份校验。

商品素材如果以后要通过这个接口预览，需要单独的访问规则。不要把私有商品视频放进现有无鉴权文件路由而不加限制。第一版若只在本机 Streamlit 用 `st.video(path)`，可以不暴露新的公网文件路径。

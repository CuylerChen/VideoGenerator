"""好物研究所：一页完成分镜和出片。成片不留在服务器。"""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

st.set_page_config(page_title="好物研究所", page_icon="🛍️", layout="wide")

from goodthings.ephemeral import cleanup_older_than, release_video, session_dir
from goodthings.fast_cut import TAG_LABELS, build_fast_storyboard, materialize_file
from goodthings.portraits import contains_face, exclude_portraits
from web.goodthings_ui import page_shell
from web.state.session import get_pixelle_video
from web.utils.async_helpers import run_async

TEMP_ROOT = Path("temp/goodthings")
cleanup_older_than(TEMP_ROOT)

service = page_shell("好物研究所")
st.caption("一条 28 秒快节奏成片。服务器不保存视频，生成后请立即下载，下载开始后服务器上的成片和参考视频会删除。")

if "gt_session" not in st.session_state:
    st.session_state["gt_session"] = uuid.uuid4().hex[:12]

name = st.text_input("商品名称", value=st.session_state.get("gt_name", "净浮生油污净"))
usage = st.text_area(
    "真实用法",
    value=st.session_state.get("gt_usage", "对准需要清洁的油污区域，按照说明喷洒，等待后再擦拭。"),
    help="只写实际步骤。夸大效果的句子不会进入口播。",
)
uploads = st.file_uploader(
    "商品图和参考视频",
    accept_multiple_files=True,
    type=["jpg", "jpeg", "png", "webp", "mp4", "mov", "webm"],
)

tag_options = list(TAG_LABELS)
pending = []
if uploads:
    st.write("给每个文件标一下画面里实际是什么。")
    for item in uploads:
        tag = st.selectbox(
            item.name,
            tag_options,
            format_func=lambda key: TAG_LABELS[key],
            key=f"tag-{item.name}-{item.size}",
        )
        allow_self = st.checkbox(
            "这是我本人出镜，允许使用",
            value=False,
            key=f"self-{item.name}-{item.size}",
        )
        pending.append((item, tag, allow_self))

use_bgm = st.checkbox("加轻快背景音乐，音量低于旁白", value=True)

if st.button("生成分镜"):
    folder = session_dir(TEMP_ROOT, st.session_state["gt_session"])
    upload_dir = folder / "uploads"
    clip_dir = folder / "clips"
    upload_dir.mkdir(parents=True, exist_ok=True)
    materials = []
    try:
        allowed_paths = set()
        for index, (item, tag, allow_self) in enumerate(pending):
            suffix = Path(item.name).suffix.lower()
            saved = upload_dir / f"{index:02d}{suffix}"
            saved.write_bytes(item.getvalue())
            made = materialize_file(str(saved), tag, str(clip_dir), f"m{index}")
            if allow_self:
                allowed_paths.update(piece.clip_path for piece in made)
            materials.extend(made)
        kept, dropped = exclude_portraits(
            materials,
            contains_face=lambda path: path not in allowed_paths and contains_face(path),
        )
        board = build_fast_storyboard(name.strip(), usage, kept)
        if dropped:
            board.notes.insert(0, f"已去掉 {dropped} 个含有别人人像的画面，这些镜头不会进入成片。")
    except Exception as exc:
        st.error(str(exc))
    else:
        st.session_state["gt_name"] = name.strip()
        st.session_state["gt_usage"] = usage
        st.session_state["gt_board"] = board
        st.session_state.pop("gt_download", None)

board = st.session_state.get("gt_board")
if board:
    for note in board.notes:
        st.warning(note)
    st.subheader("28 秒分镜")
    for shot in board.shots:
        label = TAG_LABELS.get(shot.slot, shot.slot)
        source = Path(shot.asset_path).name if shot.asset_path else "商品名卡片"
        st.write(f"{shot.start:.1f}–{shot.start + shot.duration:.1f} 秒 · {label} · {source}")
        st.caption(shot.caption)
    st.write("口播")
    st.write(board.voice_text)

    if st.button("生成视频并准备下载"):
        folder = session_dir(TEMP_ROOT, st.session_state["gt_session"])
        output = folder / "final.mp4"
        core = get_pixelle_video()

        async def speak(text: str, output_path: str) -> str:
            return await core.tts(
                text=text,
                inference_mode="local",
                voice="zh-CN-XiaoxiaoNeural",
                speed=1.2,
                output_path=output_path,
            )

        try:
            from goodthings.compose import compose_fast

            bgm = "bgm/default.mp3" if use_bgm else None
            final, warnings = run_async(
                compose_fast(board, str(output), str(folder / "render"), speak, bgm_path=bgm)
            )
            data = release_video(final, extra_paths=[str(folder)])
            st.session_state["gt_download"] = data
            st.session_state["gt_download_name"] = f"{board.product_name or '好物'}.mp4"
            st.session_state["gt_warnings"] = warnings
            st.session_state["gt_session"] = uuid.uuid4().hex[:12]
        except Exception as exc:
            st.error(str(exc))

if st.session_state.get("gt_download"):
    st.success("视频已生成。请立即下载。服务器上的成片和参考视频已经删除。")
    for note in st.session_state.get("gt_warnings") or []:
        st.caption(note)
    st.download_button(
        "下载 MP4",
        data=st.session_state["gt_download"],
        file_name=st.session_state.get("gt_download_name", "好物.mp4"),
        mime="video/mp4",
    )
    st.video(st.session_state["gt_download"])

_ = service

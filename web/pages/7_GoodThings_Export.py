"""按脚本合成并导出。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

st.set_page_config(page_title="预览导出", page_icon="🎬", layout="wide")

from web.goodthings_ui import page_shell, select_product
from web.state.session import get_pixelle_video
from web.utils.async_helpers import run_async

service = page_shell("预览和导出")
product_id = select_product(service)
if not product_id:
    st.stop()

project = service.latest_project(product_id)
if not project:
    st.info("先在脚本工作台生成脚本。")
    st.stop()

st.write(f"模板：{project['template_id']}")
st.write(f"状态：{project['status']}")
if project.get("error"):
    st.warning(project["error"])

use_bgm = st.checkbox("使用默认背景音乐", value=False)
if st.button("按脚本重新合成"):
    bgm = "bgm/default.mp3" if use_bgm else None

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
        path = run_async(service.compose(project["project_id"], speak, bgm_path=bgm))
        st.success(f"已导出 {path}")
        st.rerun()
    except Exception as exc:
        st.error(str(exc))

video_path = project.get("video_path")
if video_path and Path(video_path).exists():
    st.video(video_path)
    st.download_button(
        "下载 MP4",
        data=Path(video_path).read_bytes(),
        file_name=Path(video_path).name,
        mime="video/mp4",
    )

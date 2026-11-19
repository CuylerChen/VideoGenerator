"""剪辑素材。参考视频只以短片段出现。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

st.set_page_config(page_title="素材工作台", page_icon="🎞️", layout="wide")

from web.goodthings_ui import page_shell, select_product

service = page_shell("素材工作台")
product_id = select_product(service)
if not product_id:
    st.stop()

st.caption("参考视频会切成不超过 2 秒的片段。原视频不会进入成片。")
if st.button("从图片和参考视频生成剪辑素材"):
    try:
        materials = service.generate_materials(product_id)
        st.success(f"已生成 {len(materials)} 条剪辑素材")
    except Exception as exc:
        st.error(str(exc))

materials = service.list_materials(product_id)
if not materials:
    st.info("还没有剪辑素材。")
    st.stop()

for item in materials:
    st.markdown(f"**{item.kind}** · {item.start:.1f}–{item.end:.1f} 秒")
    st.caption(item.clip_path)
    if item.kind == "video_clip" and item.clip_path == item.source_path:
        st.error("这条素材仍指向整段参考视频，不能用于合成。")
    shows = st.checkbox(
        "画面里看得到使用结果",
        value=item.shows_effect,
        key=f"effect-{item.material_id}",
    )
    if st.button("保存标记", key=f"mark-{item.material_id}"):
        service.set_material_shows_effect(item.material_id, shows)
        st.rerun()

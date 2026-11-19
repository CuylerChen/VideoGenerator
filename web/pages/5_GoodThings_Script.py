"""剪辑脚本。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

st.set_page_config(page_title="脚本工作台", page_icon="📝", layout="wide")

from goodthings.service import role_label
from web.goodthings_ui import page_shell, select_product

service = page_shell("脚本工作台")
product_id = select_product(service)
if not product_id:
    st.stop()

if st.button("根据已确认事实生成脚本"):
    try:
        project_id = service.generate_script(product_id)
        st.session_state["gt_project_id"] = project_id
        st.success("已生成。未确认的效果句不会出现。")
    except Exception as exc:
        st.error(str(exc))

project = service.latest_project(product_id)
if not project:
    st.info("还没有脚本。")
    st.stop()

st.session_state["gt_project_id"] = project["project_id"]
st.caption(f"模板 {project['template_id']} · 状态 {project['status']}")
for segment in project["script"].segments:
    st.subheader(f"{role_label(segment.role)} · {segment.duration:.0f} 秒")
    text = st.text_area(
        "口播",
        value="\n".join(segment.voice_lines),
        key=f"lines-{project['project_id']}-{segment.role}",
    )
    duration = st.number_input(
        "时长（秒）",
        min_value=0.5,
        max_value=30.0,
        value=float(segment.duration),
        step=0.5,
        key=f"dur-{project['project_id']}-{segment.role}",
    )
    if st.button("保存这段", key=f"save-seg-{segment.role}"):
        try:
            service.update_segment(
                project["project_id"],
                segment.role,
                [line for line in text.splitlines() if line.strip()],
                duration=duration,
            )
            st.success("已保存")
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

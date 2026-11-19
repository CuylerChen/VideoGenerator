"""商品工作台。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

st.set_page_config(page_title="商品工作台", page_icon="🛍️", layout="wide")

from web.goodthings_ui import page_shell, remember_product

service = page_shell("商品工作台")
counts = service.counts()
left, middle, right = st.columns(3)
left.metric("商品", counts["products"])
middle.metric("视频项目", counts["projects"])
right.metric("失败任务", counts["failed"])

st.subheader("商品")
products = service.list_products()
if not products:
    st.write("还没有商品。")
else:
    for product in products:
        if st.button(product["name"], key=f"open-{product['product_id']}"):
            remember_product(product["product_id"])
            st.switch_page("pages/4_GoodThings_Product.py")

st.subheader("视频项目")
projects = service.list_projects()
if not projects:
    st.write("还没有视频项目。")
else:
    for project in projects[:8]:
        st.write(
            f"{project['created_at']} · {project['status']} · {project.get('video_path') or project.get('error') or '未导出'}"
        )

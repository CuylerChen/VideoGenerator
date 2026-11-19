"""商品创建和事实确认。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

st.set_page_config(page_title="商品创建", page_icon="📦", layout="wide")

from web.goodthings_ui import page_shell, remember_product, select_product

service = page_shell("商品创建")

with st.form("create-product"):
    st.subheader("新建商品")
    name = st.text_input("商品名称")
    category = st.text_input("分类")
    spec = st.text_input("规格")
    intro = st.text_area("简介", help="只写已知情况。未确认前不会进入口播。")
    selling_points = st.text_area("资料中的卖点")
    usage = st.text_area("使用方法")
    cautions = st.text_area("注意事项")
    if st.form_submit_button("创建商品"):
        if not name.strip():
            st.error("请填写商品名称")
        else:
            product_id = service.create_product(
                name,
                category=category,
                spec=spec,
                intro=intro,
                selling_points=selling_points,
                usage=usage,
                cautions=cautions,
            )
            remember_product(product_id)
            st.success("已创建。简介和卖点需要你确认后才能进入口播。")
            st.rerun()

product_id = select_product(service)
if not product_id:
    st.stop()

product = service.get_product(product_id)
st.subheader(product["name"])
uploads = st.file_uploader("上传商品图片或参考视频", accept_multiple_files=True)
if uploads and st.button("保存上传"):
    try:
        for item in uploads:
            service.save_upload(product_id, item.name, item.getvalue())
        st.success(f"已保存 {len(uploads)} 个文件")
    except Exception as exc:
        st.error(str(exc))

st.write("已上传")
for asset in service.list_assets(product_id):
    st.caption(f"{asset['kind']} · {Path(asset['path']).name}")

st.subheader("事实确认")
st.caption("未确认的资料说法、推测和夸大表述不会进入口播。使用效果必须是你看到的实际情况。")
if st.button("按当前资料重新分析"):
    service.analyze(product_id)
    st.rerun()

for fact in service.list_facts(product_id):
    st.markdown(f"**{fact.text}**")
    st.caption(f"{fact.level.value} · {fact.kind} · {'已允许进入口播' if fact.approved else '未进入口播'}")
    choice = st.radio(
        "采用方式",
        ["unused", "source", "observed"],
        format_func=lambda item: {
            "unused": "不采用",
            "source": "按资料原文采用",
            "observed": "这是看到的事实",
        }[item],
        key=f"fact-{fact.fact_id}",
        horizontal=True,
        index=0 if not fact.approved else (2 if fact.level.value == "confirmed" else 1),
    )
    if st.button("保存这条", key=f"save-fact-{fact.fact_id}"):
        service.set_fact_use(fact.fact_id, choice)
        st.rerun()

with st.form("observation"):
    st.subheader("补充画面里实际看到的内容")
    observed = st.text_area("只写镜头里看得到的动作或结果")
    shows_effect = st.checkbox("这段话描述的是画面里看得到的使用结果")
    if st.form_submit_button("加入事实"):
        try:
            service.add_observation(product_id, observed, shows_effect)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

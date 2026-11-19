"""GoodThings 页面共用外壳。页面只调用服务，不写事实规则。"""

from pathlib import Path

import streamlit as st

from web.components.header import render_header
from web.state.session import init_i18n, init_session_state


def get_service():
    from goodthings.service import GoodThingsService

    return GoodThingsService(Path("data/goodthings"))


def page_shell(title: str):
    init_session_state()
    init_i18n()
    render_header()
    st.title(title)
    return get_service()


def remember_product(product_id: str) -> None:
    st.session_state["gt_product_id"] = product_id


def selected_product_id() -> str | None:
    return st.session_state.get("gt_product_id")


def select_product(service) -> str | None:
    products = service.list_products()
    if not products:
        st.info("还没有商品。先在「商品创建」里建立档案。")
        return None
    labels = {item["product_id"]: item["name"] for item in products}
    current = selected_product_id()
    ids = list(labels)
    index = ids.index(current) if current in ids else 0
    chosen = st.selectbox("当前商品", ids, index=index, format_func=lambda item: labels[item])
    remember_product(chosen)
    return chosen

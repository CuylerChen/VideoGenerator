"""从用户填写的商品资料生成事实，不补充效果。"""

import re
from typing import Dict, List

from goodthings.fact_policy import ClaimLevel, Fact

FIELD_KIND = {
    "intro": "description",
    "selling_points": "claim",
    "usage": "usage",
    "cautions": "caution",
    "spec": "spec",
}


def split_sentences(text: str) -> List[str]:
    parts = re.split(r"[。！？!?；;\n]+", text or "")
    return [part.strip(" ，,、") for part in parts if part.strip(" ，,、")]


def facts_from_product(product: Dict) -> List[Fact]:
    product_id = product["product_id"]
    facts: List[Fact] = []
    name = (product.get("name") or "").strip()
    if name:
        facts.append(
            Fact(
                fact_id=f"{product_id}:name",
                text=f"商品名称是{name}",
                level=ClaimLevel.CONFIRMED,
                kind="identity",
                approved=True,
                source="user_name",
            )
        )
    for field, kind in FIELD_KIND.items():
        for index, sentence in enumerate(split_sentences(product.get(field) or "")):
            facts.append(
                Fact(
                    fact_id=f"{product_id}:{field}:{index}",
                    text=sentence,
                    level=ClaimLevel.SOURCE_CLAIM,
                    kind=kind,
                    approved=False,
                    source=field,
                )
            )
    return facts

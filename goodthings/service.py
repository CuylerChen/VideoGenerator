"""商品短视频工作台。业务规则在这里，不在页面里。"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from goodthings.analysis import facts_from_product
from goodthings.compose import compose_script
from goodthings.fact_policy import ClaimLevel, Fact, build_script_copy
from goodthings.materials import Material, extract_clip, plan_clip_windows, probe_duration
from goodthings.scripting import ROLE_KINDS, generate_editing_script
from goodthings.store import GoodThingsStore, script_from_json, script_to_json

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


class GoodThingsService:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = GoodThingsStore(self.root / "goodthings.db")
        self.asset_dir = self.root / "assets"
        self.clip_dir = self.root / "clips"
        self.output_dir = self.root / "output"
        for folder in (self.asset_dir, self.clip_dir, self.output_dir):
            folder.mkdir(parents=True, exist_ok=True)

    def create_product(self, name: str, **fields) -> str:
        product_id = uuid.uuid4().hex[:12]
        self.store.save_product(
            {
                "product_id": product_id,
                "owner_id": fields.get("owner_id"),
                "name": name.strip(),
                "category": fields.get("category") or "",
                "spec": fields.get("spec") or "",
                "intro": fields.get("intro") or "",
                "selling_points": fields.get("selling_points") or "",
                "usage": fields.get("usage") or "",
                "cautions": fields.get("cautions") or "",
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        self.analyze(product_id)
        return product_id

    def update_product(self, product_id: str, **fields) -> None:
        current = self._require_product(product_id)
        current.update({key: value for key, value in fields.items() if value is not None})
        self.store.save_product(current)
        self.analyze(product_id)

    def list_products(self) -> List[Dict]:
        return self.store.list_products()

    def get_product(self, product_id: str) -> Dict:
        return self._require_product(product_id)

    def analyze(self, product_id: str) -> List[Fact]:
        product = self._require_product(product_id)
        previous = {fact.fact_id: fact for fact in self.store.list_facts(product_id)}
        fresh = facts_from_product(product)
        for fact in fresh:
            old = previous.get(fact.fact_id)
            if old and old.text == fact.text and old.approved:
                fact.approved = True
                fact.level = old.level
                fact.kind = old.kind
        self.store.replace_generated_facts(product_id, fresh)
        return self.store.list_facts(product_id)

    def set_fact_use(self, fact_id: str, mode: str) -> None:
        facts = self._all_facts()
        fact = next((item for item in facts if item.fact_id == fact_id), None)
        if fact is None:
            raise KeyError("找不到这条事实")
        if mode == "unused":
            self.store.set_fact_approval(fact_id, False, ClaimLevel.SOURCE_CLAIM, fact.kind)
            return
        if mode == "source":
            self.store.set_fact_approval(fact_id, True, ClaimLevel.SOURCE_CLAIM, fact.kind)
            return
        if mode == "observed":
            kind = "observed_effect" if fact.kind in {"claim", "effect", "observed_effect"} else fact.kind
            self.store.set_fact_approval(fact_id, True, ClaimLevel.CONFIRMED, kind)
            return
        raise ValueError("未知的采用方式")

    def add_observation(self, product_id: str, text: str, shows_effect: bool) -> str:
        sentence = text.strip()
        if not sentence:
            raise ValueError("请填写画面里实际看到的内容")
        fact_id = uuid.uuid4().hex[:12]
        self.store.upsert_fact(
            product_id,
            Fact(
                fact_id=fact_id,
                text=sentence,
                level=ClaimLevel.CONFIRMED,
                kind="observed_effect" if shows_effect else "usage",
                approved=True,
                source="user_observation",
            ),
        )
        return fact_id

    def save_upload(self, product_id: str, filename: str, data: bytes) -> str:
        self._require_product(product_id)
        suffix = Path(filename).suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            kind = "image"
        elif suffix in VIDEO_SUFFIXES:
            kind = "reference_video"
        else:
            raise ValueError("只接受 jpg、png、webp 图片，或 mp4、mov、webm 视频")
        asset_id = uuid.uuid4().hex[:12]
        folder = self.asset_dir / product_id
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{asset_id}{suffix}"
        path.write_bytes(data)
        self.store.add_asset(
            {
                "asset_id": asset_id,
                "product_id": product_id,
                "kind": kind,
                "path": str(path),
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        return asset_id

    def list_assets(self, product_id: str) -> List[Dict]:
        return self.store.list_assets(product_id)

    def list_facts(self, product_id: str) -> List[Fact]:
        return self.store.list_facts(product_id)

    def generate_materials(self, product_id: str) -> List[Material]:
        self._require_product(product_id)
        materials: List[Material] = []
        for asset in self.store.list_assets(product_id):
            if asset["kind"] == "image":
                materials.append(
                    Material(
                        material_id=f"{asset['asset_id']}-image",
                        source_path=asset["path"],
                        clip_path=asset["path"],
                        kind="image",
                    )
                )
                continue
            if asset["kind"] != "reference_video":
                continue
            duration = probe_duration(asset["path"])
            windows = plan_clip_windows(duration)
            for index, window in enumerate(windows):
                material_id = f"{asset['asset_id']}-clip-{index}"
                clip_path = self.clip_dir / product_id / f"{material_id}.mp4"
                extract_clip(asset["path"], window.start, window.end, str(clip_path))
                materials.append(
                    Material(
                        material_id=material_id,
                        source_path=asset["path"],
                        clip_path=str(clip_path),
                        kind="video_clip",
                        shows_effect=False,
                        start=window.start,
                        end=window.end,
                    )
                )
        self.store.replace_materials(product_id, materials)
        return materials

    def list_materials(self, product_id: str) -> List[Material]:
        return self.store.list_materials(product_id)

    def set_material_shows_effect(self, material_id: str, shows_effect: bool) -> None:
        self.store.set_shows_effect(material_id, shows_effect)

    def generate_script(self, product_id: str, template_id: str = "goodthings_fast_30s") -> str:
        product = self._require_product(product_id)
        facts = self.store.list_facts(product_id)
        materials = self.store.list_materials(product_id)
        script = generate_editing_script(product["name"], facts, materials, template_id)
        project_id = uuid.uuid4().hex[:12]
        self.store.save_project(
            {
                "project_id": project_id,
                "product_id": product_id,
                "template_id": template_id,
                "script_json": script_to_json(script),
                "status": "draft",
                "video_path": None,
                "error": None,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }
        )
        return project_id

    def get_project(self, project_id: str) -> Dict:
        project = self.store.get_project(project_id)
        if project is None:
            raise KeyError("找不到视频项目")
        project["script"] = script_from_json(project["script_json"])
        return project

    def latest_project(self, product_id: str) -> Optional[Dict]:
        projects = self.store.list_projects(product_id)
        if not projects:
            return None
        return self.get_project(projects[0]["project_id"])

    def update_segment(self, project_id: str, role: str, lines: List[str], duration: Optional[float] = None) -> List[str]:
        project = self.get_project(project_id)
        script = project["script"]
        facts = self.store.list_facts(project["product_id"])
        segment = next((item for item in script.segments if item.role == role), None)
        if segment is None:
            raise KeyError("找不到这一段")
        decision = build_script_copy(
            segment_role=role,
            candidate_lines=[line.strip() for line in lines if line.strip()],
            facts=facts,
            bound_material_shows_effect=segment.shows_effect,
        )
        if decision.rejected:
            raise ValueError("；".join(decision.rejected))
        segment.voice_lines = decision.accepted
        segment.caption = decision.accepted[0] if decision.accepted else segment.caption
        if duration is not None:
            if duration <= 0:
                raise ValueError("镜头时长必须大于 0")
            segment.duration = float(duration)
        project["script_json"] = script_to_json(script)
        project["status"] = "draft"
        self.store.save_project(project)
        return decision.accepted

    async def compose(self, project_id: str, tts, bgm_path: Optional[str] = None) -> str:
        project = self.get_project(project_id)
        product = self._require_product(project["product_id"])
        script = project["script"]
        facts = self.store.list_facts(project["product_id"])
        for segment in script.segments:
            if segment.role == "outro":
                spoken = [line for line in segment.voice_lines if line != "每天发现一个实用好物，这里是好物研究所！"]
            else:
                spoken = list(segment.voice_lines)
            decision = build_script_copy(
                segment.role,
                spoken,
                facts,
                segment.shows_effect,
            )
            if decision.rejected:
                raise ValueError("；".join(decision.rejected))
            segment.voice_lines = decision.accepted
            if segment.role == "outro":
                segment.voice_lines.append("每天发现一个实用好物，这里是好物研究所！")
        project["status"] = "rendering"
        project["error"] = None
        self.store.save_project({**project, "script_json": script_to_json(script)})
        work_dir = self.output_dir / project_id
        output = work_dir / "final.mp4"
        try:
            final, warnings = await compose_script(
                script,
                str(output),
                str(work_dir),
                tts,
                product["name"],
                bgm_path=bgm_path,
            )
        except Exception as exc:
            project["status"] = "failed"
            project["error"] = str(exc)
            project["script_json"] = script_to_json(script)
            self.store.save_project(project)
            raise
        project["status"] = "completed"
        project["video_path"] = final
        project["error"] = "；".join(warnings) if warnings else None
        project["script_json"] = script_to_json(script)
        self.store.save_project(project)
        return final

    def counts(self) -> Dict[str, int]:
        return self.store.counts()

    def list_projects(self) -> List[Dict]:
        return self.store.list_projects()

    def _require_product(self, product_id: str) -> Dict:
        product = self.store.get_product(product_id)
        if product is None:
            raise KeyError("找不到商品")
        return product

    def _all_facts(self) -> List[Fact]:
        facts: List[Fact] = []
        for product in self.store.list_products():
            facts.extend(self.store.list_facts(product["product_id"]))
        return facts


def role_label(role: str) -> str:
    labels = {
        "hook": "痛点钩子",
        "reveal": "商品亮相",
        "feature": "产品特点",
        "usage": "使用过程",
        "effect": "使用效果",
        "outro": "收尾",
    }
    return labels.get(role, role)


def allowed_fact_kinds(role: str):
    return ROLE_KINDS.get(role, set())

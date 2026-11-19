"""商品、素材和项目的 SQLite 存储。"""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from goodthings.fact_policy import ClaimLevel, Fact
from goodthings.materials import Material
from goodthings.scripting import EditingScript, ScriptSegment


class GoodThingsStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS products (
                    product_id TEXT PRIMARY KEY,
                    owner_id TEXT,
                    name TEXT NOT NULL,
                    category TEXT,
                    spec TEXT,
                    intro TEXT,
                    selling_points TEXT,
                    usage_text TEXT,
                    cautions TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS facts (
                    fact_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    level TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    approved INTEGER NOT NULL,
                    source TEXT
                );
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS materials (
                    material_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    source_asset_id TEXT,
                    source_path TEXT NOT NULL,
                    clip_path TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    shows_effect INTEGER NOT NULL,
                    start_sec REAL,
                    end_sec REAL
                );
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    product_id TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    script_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    video_path TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_product(self, product: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO products (
                    product_id, owner_id, name, category, spec, intro,
                    selling_points, usage_text, cautions, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    name=excluded.name,
                    category=excluded.category,
                    spec=excluded.spec,
                    intro=excluded.intro,
                    selling_points=excluded.selling_points,
                    usage_text=excluded.usage_text,
                    cautions=excluded.cautions
                """,
                (
                    product["product_id"],
                    product.get("owner_id"),
                    product.get("name") or "",
                    product.get("category") or "",
                    product.get("spec") or "",
                    product.get("intro") or "",
                    product.get("selling_points") or "",
                    product.get("usage") or "",
                    product.get("cautions") or "",
                    product["created_at"],
                ),
            )

    def list_products(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM products ORDER BY created_at DESC").fetchall()
        return [self._product_row(row) for row in rows]

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM products WHERE product_id = ?", (product_id,)
            ).fetchone()
        return self._product_row(row) if row else None

    def _product_row(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "product_id": row["product_id"],
            "owner_id": row["owner_id"],
            "name": row["name"],
            "category": row["category"],
            "spec": row["spec"],
            "intro": row["intro"],
            "selling_points": row["selling_points"],
            "usage": row["usage_text"],
            "cautions": row["cautions"],
            "created_at": row["created_at"],
        }

    def replace_generated_facts(self, product_id: str, facts: List[Fact]) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM facts WHERE product_id = ? AND source != ?",
                (product_id, "user_observation"),
            )
            for fact in facts:
                conn.execute(
                    """
                    INSERT INTO facts (fact_id, product_id, text, level, kind, approved, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(fact_id) DO UPDATE SET
                        text=excluded.text,
                        level=excluded.level,
                        kind=excluded.kind,
                        approved=excluded.approved,
                        source=excluded.source
                    """,
                    (
                        fact.fact_id,
                        product_id,
                        fact.text,
                        fact.level.value,
                        fact.kind,
                        int(fact.approved),
                        fact.source,
                    ),
                )

    def upsert_fact(self, product_id: str, fact: Fact) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO facts (fact_id, product_id, text, level, kind, approved, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(fact_id) DO UPDATE SET
                    text=excluded.text,
                    level=excluded.level,
                    kind=excluded.kind,
                    approved=excluded.approved,
                    source=excluded.source
                """,
                (
                    fact.fact_id,
                    product_id,
                    fact.text,
                    fact.level.value,
                    fact.kind,
                    int(fact.approved),
                    fact.source,
                ),
            )

    def list_facts(self, product_id: str) -> List[Fact]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM facts WHERE product_id = ? ORDER BY fact_id",
                (product_id,),
            ).fetchall()
        return [
            Fact(
                fact_id=row["fact_id"],
                text=row["text"],
                level=ClaimLevel(row["level"]),
                kind=row["kind"],
                approved=bool(row["approved"]),
                source=row["source"] or "",
            )
            for row in rows
        ]

    def set_fact_approval(self, fact_id: str, approved: bool, level: ClaimLevel, kind: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE facts SET approved = ?, level = ?, kind = ? WHERE fact_id = ?",
                (int(approved), level.value, kind, fact_id),
            )

    def add_asset(self, asset: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO assets (asset_id, product_id, kind, path, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    asset["asset_id"],
                    asset["product_id"],
                    asset["kind"],
                    asset["path"],
                    asset["created_at"],
                ),
            )

    def list_assets(self, product_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM assets WHERE product_id = ? ORDER BY created_at",
                (product_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def replace_materials(self, product_id: str, materials: List[Material]) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM materials WHERE product_id = ?", (product_id,))
            for item in materials:
                conn.execute(
                    """
                    INSERT INTO materials (
                        material_id, product_id, source_asset_id, source_path, clip_path,
                        kind, shows_effect, start_sec, end_sec
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.material_id,
                        product_id,
                        None,
                        item.source_path,
                        item.clip_path,
                        item.kind,
                        int(item.shows_effect),
                        item.start,
                        item.end,
                    ),
                )

    def list_materials(self, product_id: str) -> List[Material]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM materials WHERE product_id = ?",
                (product_id,),
            ).fetchall()
        return [
            Material(
                material_id=row["material_id"],
                source_path=row["source_path"],
                clip_path=row["clip_path"],
                kind=row["kind"],
                shows_effect=bool(row["shows_effect"]),
                start=row["start_sec"] or 0,
                end=row["end_sec"] or 0,
            )
            for row in rows
        ]

    def set_shows_effect(self, material_id: str, shows_effect: bool) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE materials SET shows_effect = ? WHERE material_id = ?",
                (int(shows_effect), material_id),
            )

    def save_project(self, project: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    project_id, product_id, template_id, script_json, status,
                    video_path, error, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    script_json=excluded.script_json,
                    status=excluded.status,
                    video_path=excluded.video_path,
                    error=excluded.error,
                    template_id=excluded.template_id
                """,
                (
                    project["project_id"],
                    project["product_id"],
                    project["template_id"],
                    project["script_json"],
                    project["status"],
                    project.get("video_path"),
                    project.get("error"),
                    project["created_at"],
                ),
            )

    def list_projects(self, product_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if product_id:
                rows = conn.execute(
                    "SELECT * FROM projects WHERE product_id = ? ORDER BY created_at DESC",
                    (product_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        return dict(row) if row else None

    def counts(self) -> Dict[str, int]:
        with self._connect() as conn:
            products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
            projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            failed = conn.execute(
                "SELECT COUNT(*) FROM projects WHERE status = 'failed'"
            ).fetchone()[0]
            running = conn.execute(
                "SELECT COUNT(*) FROM projects WHERE status = 'rendering'"
            ).fetchone()[0]
        return {
            "products": products,
            "projects": projects,
            "failed": failed,
            "rendering": running,
        }


def script_to_json(script: EditingScript) -> str:
    payload = {
        "template_id": script.template_id,
        "segments": [
            {
                "role": segment.role,
                "duration": segment.duration,
                "voice_lines": segment.voice_lines,
                "caption": segment.caption,
                "asset_path": segment.asset_path,
                "material_id": segment.material_id,
                "shows_effect": segment.shows_effect,
                "source_path": segment.source_path,
            }
            for segment in script.segments
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def script_from_json(raw: str) -> EditingScript:
    payload = json.loads(raw)
    segments = [
        ScriptSegment(
            role=item["role"],
            duration=float(item["duration"]),
            voice_lines=list(item.get("voice_lines") or []),
            caption=item.get("caption") or "",
            asset_path=item.get("asset_path"),
            material_id=item.get("material_id"),
            shows_effect=bool(item.get("shows_effect")),
            source_path=item.get("source_path"),
        )
        for item in payload["segments"]
    ]
    return EditingScript(template_id=payload["template_id"], segments=segments)

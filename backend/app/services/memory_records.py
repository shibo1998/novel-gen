"""Durable long-term memory storage and deterministic retrieval."""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Chapter, MemoryRecord, Scene

logger = logging.getLogger(__name__)


class MemoryRecordStore:
    """Use PostgreSQL as the source of truth; vector indexes remain optional."""

    MAX_CANDIDATES = 500

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def content_hash(memory_type: str, content: str) -> str:
        payload = f"{memory_type}\n{content.strip()}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def summarize(content: str, title: str | None = None, limit: int = 360) -> str:
        compact = re.sub(r"\s+", " ", content).strip()
        excerpt = compact if len(compact) <= limit else f"{compact[:limit].rstrip()}..."
        return f"{title}: {excerpt}" if title else excerpt

    async def add(
        self,
        *,
        project_id: UUID,
        memory_type: str,
        content: str,
        chapter_number: int | None,
        summary: str | None = None,
        scene_id: UUID | None = None,
        entity_id: UUID | None = None,
        salience: float = 0.5,
        emotional_intensity: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord:
        normalized = content.strip()
        digest = self.content_hash(memory_type, normalized)
        existing = (
            await self.db.execute(
                select(MemoryRecord).where(
                    MemoryRecord.project_id == project_id,
                    MemoryRecord.content_hash == digest,
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing

        # 写入即嵌入：embedding 与记录同事务落库，失败降级为 failed 不阻断业务
        embedding, index_status = await self._embed_for_index(summary or normalized)

        await self.db.execute(
            insert(MemoryRecord)
            .values(
                project_id=project_id,
                scene_id=scene_id,
                entity_id=entity_id,
                memory_type=memory_type,
                content=normalized,
                summary=summary or self.summarize(normalized),
                chapter_number=chapter_number,
                salience=max(0.0, min(1.0, salience)),
                emotional_intensity=max(0.0, min(2.0, emotional_intensity)),
                metadata_json=metadata or {},
                content_hash=digest,
                embedding=embedding,
                index_status=index_status,
            )
            .on_conflict_do_nothing()
        )
        return (
            await self.db.execute(
                select(MemoryRecord).where(
                    MemoryRecord.project_id == project_id,
                    MemoryRecord.content_hash == digest,
                )
            )
        ).scalar_one()

    @staticmethod
    async def _embed_for_index(text: str) -> tuple[list[float] | None, str]:
        """为记录生成 embedding。失败时降级返回 (None, "failed")，不抛出。

        embedding 服务（本地 Ollama bge-m3）不可用时，业务不应中断——
        记录仍以 index_status="failed" 落库，后续可由 reindex_pending 补偿。
        """
        from app.llm.embedding import EmbeddingError, get_embedding_client

        try:
            vector = await get_embedding_client().embed_text(text)
            return vector, "indexed"
        except (EmbeddingError, Exception) as exc:  # noqa: BLE001 - 降级不阻断
            logger.warning("memory embedding failed, degrade to failed: %s", exc)
            return None, "failed"

    async def reindex_pending(self, batch_size: int = 25) -> tuple[int, int]:
        """Claim and retry one bounded batch of missing memory embeddings."""
        from app.llm.embedding import EmbeddingError, get_embedding_client

        limit = max(1, min(batch_size, 500))
        records = (
            await self.db.execute(
                select(MemoryRecord)
                .where(
                    or_(
                        MemoryRecord.embedding.is_(None),
                        MemoryRecord.index_status != "indexed",
                    )
                )
                .order_by(MemoryRecord.created_at.asc(), MemoryRecord.id.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).scalars().all()
        if not records:
            return 0, 0

        texts = [record.summary or record.content for record in records]
        try:
            vectors = await get_embedding_client().embed_texts(texts)
            if len(vectors) != len(records):
                raise EmbeddingError(
                    f"embedding result count mismatch: got {len(vectors)}, expected {len(records)}"
                )
        except EmbeddingError as exc:
            logger.warning("memory reindex batch failed: %s", exc)
            for record in records:
                record.embedding = None
                record.index_status = "failed"
            await self.db.flush()
            return 0, len(records)

        for record, vector in zip(records, vectors):
            record.embedding = vector
            record.index_status = "indexed"
        await self.db.flush()
        return len(records), 0

    async def sync_chapter(self, chapter_id: UUID) -> list[MemoryRecord]:
        chapter = (
            await self.db.execute(select(Chapter).where(Chapter.id == chapter_id))
        ).scalar_one()
        scenes = (
            await self.db.execute(
                select(Scene).where(Scene.chapter_id == chapter_id).order_by(Scene.scene_number)
            )
        ).scalars().all()

        saved: list[MemoryRecord] = []
        scene_summaries: list[str] = []
        for scene in scenes:
            if scene.status not in ("confirmed", "completed") or not scene.content:
                continue
            summary = self.summarize(scene.content, scene.title)
            scene_summaries.append(f"场景{scene.scene_number} {summary}")
            saved.append(
                await self.add(
                    project_id=chapter.project_id,
                    scene_id=scene.id,
                    entity_id=scene.pov_character_id,
                    memory_type="scene_event",
                    content=scene.content,
                    summary=summary,
                    chapter_number=chapter.chapter_number,
                    salience=0.65,
                    emotional_intensity=0.5,
                    metadata={
                        "scene_number": scene.scene_number,
                        "title": scene.title,
                    },
                )
            )

        if scene_summaries:
            chapter_summary = "\n".join(scene_summaries)
            saved.append(
                await self.add(
                    project_id=chapter.project_id,
                    memory_type="chapter_summary",
                    content=chapter_summary,
                    summary=self.summarize(chapter_summary, chapter.title, limit=600),
                    chapter_number=chapter.chapter_number,
                    salience=0.75,
                    emotional_intensity=0.5,
                    metadata={"chapter_id": str(chapter.id), "title": chapter.title},
                )
            )
        return saved

    async def retrieve(
        self,
        *,
        project_id: UUID | str,
        current_chapter: int,
        query: str = "",
        entity_id: UUID | None = None,
        memory_types: tuple[str, ...] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """三路召回并集 + 语义分融合。

        召回三路取并集，消除旧「LIMIT 500 ORDER BY chapter DESC」的死角
        （第 3 章设定在 80 章后连候选集都进不了）：
          1. 语义路：pgvector 按 query embedding 取 cosine top-K，**不受章节窗口限制**；
          2. 时近路：最近若干章的记录（保证前情连续性）；
          3. 结构路：lexical 命中兜底（embedding 不可用时仍可召回）。
        打分融合语义维度：
          salience 0.30 + semantic 0.30 + recency 0.20 + lexical 0.10 + emotional 0.10
        """
        candidates: dict[Any, MemoryRecord] = {}

        # ── 路 1：语义 top-K（pgvector），不受章节窗口限制 ──
        semantic_by_id: dict[Any, float] = {}
        query_vec = await self._embed_query(query)
        if query_vec is not None:
            sem_records = await self._semantic_candidates(
                project_id=project_id,
                current_chapter=current_chapter,
                query_vec=query_vec,
                entity_id=entity_id,
                memory_types=memory_types,
                k=max(limit * 3, 30),
            )
            for record, similarity in sem_records:
                candidates[record.id] = record
                semantic_by_id[record.id] = similarity

        # ── 路 2 + 3：时近 + 结构（一条 SQL 拉候选，Python 内打分）──
        statement = select(MemoryRecord).where(
            MemoryRecord.project_id == project_id,
            MemoryRecord.chapter_number.isnot(None),
            MemoryRecord.chapter_number < current_chapter,
        )
        if entity_id is not None:
            statement = statement.where(MemoryRecord.entity_id == entity_id)
        if memory_types:
            statement = statement.where(MemoryRecord.memory_type.in_(memory_types))
        recent_records = (
            await self.db.execute(
                statement.order_by(MemoryRecord.chapter_number.desc()).limit(self.MAX_CANDIDATES)
            )
        ).scalars().all()
        for record in recent_records:
            candidates.setdefault(record.id, record)

        # ── 融合打分 ──
        terms = self._query_terms(query)
        ranked = []
        for record in candidates.values():
            distance = max(0, current_chapter - (record.chapter_number or current_chapter))
            recency = 1.0 / (1.0 + distance / 12.0)
            haystack = f"{record.summary or ''} {record.content}".lower()
            matched = sum(1 for term in terms if term in haystack)
            lexical = matched / len(terms) if terms else 0.0
            semantic = semantic_by_id.get(record.id, 0.0)
            score = (
                float(record.salience or 0.0) * 0.30
                + semantic * 0.30
                + recency * 0.20
                + lexical * 0.10
                + min(float(record.emotional_intensity or 0.0), 2.0) / 2.0 * 0.10
            )
            ranked.append((score, record))

        ranked.sort(key=lambda item: (item[0], item[1].chapter_number or 0), reverse=True)
        return [self._as_dict(record, score) for score, record in ranked[:limit]]

    @staticmethod
    async def _embed_query(query: str) -> list[float] | None:
        """把查询串嵌入为向量；embedding 不可用时返回 None（降级为无语义路）。"""
        if not query or not query.strip():
            return None
        from app.llm.embedding import EmbeddingError, get_embedding_client

        try:
            return await get_embedding_client().embed_text(query)
        except (EmbeddingError, Exception) as exc:  # noqa: BLE001 - 降级不阻断
            logger.warning("query embedding failed, skip semantic recall: %s", exc)
            return None

    async def _semantic_candidates(
        self,
        *,
        project_id: UUID | str,
        current_chapter: int,
        query_vec: list[float],
        entity_id: UUID | None,
        memory_types: tuple[str, ...] | None,
        k: int,
    ) -> list[tuple[MemoryRecord, float]]:
        """pgvector cosine top-k：返回 (record, similarity)，similarity ∈ [0,1]。"""
        from sqlalchemy import text

        conditions = [
            "project_id = :project_id",
            "chapter_number IS NOT NULL",
            "chapter_number < :current_chapter",
            "embedding IS NOT NULL",
        ]
        params: dict[str, Any] = {
            "project_id": str(project_id),
            "current_chapter": current_chapter,
            "query_vec": "[" + ",".join(str(x) for x in query_vec) + "]",
            "k": k,
        }
        if entity_id is not None:
            conditions.append("entity_id = :entity_id")
            params["entity_id"] = str(entity_id)
        if memory_types:
            placeholders = ",".join(f":mt{i}" for i in range(len(memory_types)))
            conditions.append(f"memory_type IN ({placeholders})")
            for i, mt in enumerate(memory_types):
                params[f"mt{i}"] = mt

        where_clause = " AND ".join(conditions)
        # cosine 距离 <=> ∈ [0,2]，similarity = 1 - distance/2 ∈ [0,1]
        sql = text(
            f"SELECT id, 1.0 - (embedding <=> CAST(:query_vec AS vector)) / 2.0 AS similarity "
            f"FROM memory_records WHERE {where_clause} "
            f"ORDER BY embedding <=> CAST(:query_vec AS vector) ASC LIMIT :k"
        )
        rows = (await self.db.execute(sql, params)).all()
        if not rows:
            return []
        id_to_sim = {row[0]: float(row[1]) for row in rows}
        records = (
            await self.db.execute(
                select(MemoryRecord).where(MemoryRecord.id.in_(list(id_to_sim.keys())))
            )
        ).scalars().all()
        return [(r, id_to_sim.get(r.id, 0.0)) for r in records]

    async def previous_summaries(
        self,
        *,
        project_id: UUID | str,
        current_chapter: int,
        current_scene: int,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        records = (
            await self.db.execute(
                select(MemoryRecord)
                .where(
                    MemoryRecord.project_id == project_id,
                    MemoryRecord.memory_type == "scene_event",
                    MemoryRecord.chapter_number.isnot(None),
                    MemoryRecord.chapter_number <= current_chapter,
                )
                .order_by(MemoryRecord.chapter_number, MemoryRecord.created_at)
            )
        ).scalars().all()
        summaries = []
        for record in records:
            scene_number = int((record.metadata_json or {}).get("scene_number", 0))
            if record.chapter_number == current_chapter and scene_number >= current_scene:
                continue
            summaries.append(
                {
                    "chapter": record.chapter_number,
                    "scene": scene_number,
                    "summary": record.summary or self.summarize(record.content),
                }
            )
        return summaries[-limit:]

    @staticmethod
    def _query_terms(query: str) -> set[str]:
        lowered = query.lower()
        latin = re.findall(r"[a-z0-9_]{2,}", lowered)
        chinese = re.findall(r"[\u4e00-\u9fff]{2,}", lowered)
        terms = set(latin)
        for block in chinese:
            terms.add(block)
            terms.update(block[index:index + 2] for index in range(len(block) - 1))
        return terms

    @staticmethod
    def _as_dict(record: MemoryRecord, score: float) -> dict[str, Any]:
        return {
            "id": str(record.id),
            "chapter": record.chapter_number,
            "scene": (record.metadata_json or {}).get("scene_number"),
            "memory_type": record.memory_type,
            "content": record.content,
            "summary": record.summary or record.content,
            "entity_id": str(record.entity_id) if record.entity_id else None,
            "salience": record.salience,
            "emotional_intensity": record.emotional_intensity,
            "strength": round(score, 6),
            "index_status": record.index_status,
        }

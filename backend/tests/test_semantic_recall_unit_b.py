"""单元 B 语义召回集成测试（问题 3 的核心验证）。

证明：第 3 章埋的设定，在第 80 章用**不同措辞**的查询也能被语义召回。
旧实现（LIMIT 500 ORDER BY chapter DESC + 字面匹配）在这种场景下召回为空。

依赖真实 embedding（本地 Ollama bge-m3）+ 真实 pgvector，标记 integration。
Ollama / pgvector 不可用时自动 skip，不阻断其他测试。
"""
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db.session import async_session_maker
from app.llm.embedding import get_embedding_client, reset_embedding_client
from app.services.memory_records import MemoryRecordStore

pytestmark = pytest.mark.integration


async def _embedding_available() -> bool:
    """探测 embedding 服务是否可用；不可用则 skip 整个模块。"""
    reset_embedding_client()
    try:
        vec = await get_embedding_client().embed_text("探测")
        return len(vec) > 0
    except Exception:
        return False


@pytest_asyncio.fixture
async def project_with_memories():
    """建一个临时项目 + 一批跨章记忆，测试后清理。"""
    if not await _embedding_available():
        pytest.skip("embedding 服务（Ollama bge-m3）不可用，跳过语义召回集成测试")

    project_id = uuid.uuid4()
    async with async_session_maker() as db:
        # 建 project（外键需要）+ user
        user_id = uuid.uuid4()
        await db.execute(
            text(
                "INSERT INTO users (id, email, username, password_hash) "
                "VALUES (:id, :email, :username, 'x')"
            ),
            {"id": str(user_id), "email": f"{user_id}@t.test", "username": str(user_id)[:8]},
        )
        await db.execute(
            text(
                "INSERT INTO projects (id, user_id, title, core_idea) "
                "VALUES (:id, :uid, '测试书', '测试')"
            ),
            {"id": str(project_id), "uid": str(user_id)},
        )
        await db.commit()

        store = MemoryRecordStore(db)
        # 第 3 章：埋一条设定（用「师父赠剑」措辞）
        await store.add(
            project_id=project_id,
            memory_type="scene_event",
            content="第三章，玄清子将一柄古朴长剑郑重交到少年手中，叮嘱他此剑认主，非到生死关头不可出鞘。",
            chapter_number=3,
            summary="玄清子赠予少年一柄认主的长剑，嘱咐非生死关头不出鞘",
            salience=0.6,
            metadata={"scene_number": 1},
        )
        # 填充若干无关的近章记忆，把候选集撑过章节窗口
        for ch in range(4, 82):
            await store.add(
                project_id=project_id,
                memory_type="scene_event",
                content=f"第{ch}章，主角在城中处理了一些琐碎事务，与剧情主线无关的日常片段。",
                chapter_number=ch,
                summary=f"第{ch}章日常片段",
                salience=0.5,
                metadata={"scene_number": 1},
            )
        await db.commit()

        yield project_id, store, db

        # 清理
        await db.execute(
            text("DELETE FROM memory_records WHERE project_id = :pid"), {"pid": str(project_id)}
        )
        await db.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": str(project_id)})
        await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": str(user_id)})
        await db.commit()


async def test_semantic_recall_finds_old_setup_with_different_wording(project_with_memories):
    """第 80 章用不同措辞查询，应召回第 3 章的赠剑设定。"""
    project_id, store, _ = project_with_memories

    # 查询用完全不同的措辞：不含「玄清子/赠/长剑」等原文词
    results = await store.retrieve(
        project_id=project_id,
        current_chapter=80,
        query="少年手里那把传承下来的兵器有什么来历和使用禁忌",
        limit=5,
    )

    # 断言：第 3 章的赠剑记忆被召回（语义路生效）
    chapters = [r["chapter"] for r in results]
    assert 3 in chapters, f"第 3 章赠剑设定未被召回，仅得到章节 {chapters}"


async def test_embedding_written_on_add(project_with_memories):
    """add() 写入即嵌入：记录的 index_status 应为 indexed，embedding 非空。"""
    project_id, store, db = project_with_memories

    row = (
        await db.execute(
            text(
                "SELECT index_status, (embedding IS NOT NULL) AS has_vec "
                "FROM memory_records WHERE project_id = :pid AND chapter_number = 3 LIMIT 1"
            ),
            {"pid": str(project_id)},
        )
    ).first()
    assert row is not None
    assert row[0] == "indexed", f"index_status 应为 indexed，实际 {row[0]}"
    assert row[1] is True, "embedding 列应已写入"

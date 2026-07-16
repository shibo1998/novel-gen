"""一次性清理脚本：清空所有项目的 chapters / foreshadowings / scenes。

不动 projects 表（保留 setting_document / constraints / 用户账号）。
触发场景：用户主动要求"重新生成大纲"时跑一次。
"""
import asyncio
import sys
import os

# 让脚本能 import app.*（poetry run 会把 cwd 加入 sys.path，但 Windows 下偶尔失效）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete as sql_delete, select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import settings
from app.models.domain import Chapter, Foreshadowing, Scene, Project


async def main() -> int:
    # pydantic-settings 没暴露 DATABASE_URL，从 .env 拼装
    db_url = os.getenv(
        "DATABASE_URL",
        f"postgresql+asyncpg://{os.getenv('DB_USER','novel')}:{os.getenv('DB_PASSWORD','novel123')}"
        f"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}/{os.getenv('DB_NAME','novel_gen')}",
    )
    print(f"using db: {db_url.replace(os.getenv('DB_PASSWORD','novel123'),'***')}")
    engine = create_async_engine(db_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with Session() as s:
            # before
            for model, label in [(Chapter, "chapters"), (Foreshadowing, "foreshadowings"), (Scene, "scenes")]:
                n = (await s.execute(select(func.count()).select_from(model))).scalar()
                print(f"before  {label:<15} = {n}")
            proj_n = (await s.execute(select(func.count()).select_from(Project))).scalar()
            print(f"before  projects (untouched) = {proj_n}")

            # clear (顺序：场景 → 伏笔 → 章节)
            await s.execute(sql_delete(Scene))
            await s.execute(sql_delete(Foreshadowing))
            await s.execute(sql_delete(Chapter))
            await s.commit()

            # after
            for model, label in [(Chapter, "chapters"), (Foreshadowing, "foreshadowings"), (Scene, "scenes")]:
                n = (await s.execute(select(func.count()).select_from(model))).scalar()
                print(f"after   {label:<15} = {n}")
            proj_n_after = (await s.execute(select(func.count()).select_from(Project))).scalar()
            print(f"after   projects (untouched) = {proj_n_after}")
            print("OK: 章节/伏笔/场景 已清空，项目数据保留。")
            return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
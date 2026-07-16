import asyncio
import httpx
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 这是用户日志里出现的项目 ID
PROJECT_ID = '7307b914-14b3-45e9-b7a1-959ee4ebd60e'

# 任务 ID - 用户已经生成过世界观(任务返回 200)
TASK_ID = '43bc0436-8a93-4962-a119-c8fa5842a70a'

async def test():
    async with httpx.AsyncClient(base_url='http://localhost:8000', timeout=30.0) as client:
        # 测试 1: 能否无需认证直接访问（看你是否是登录态问题）
        print(f'[1] Health check')
        resp = await client.get('/api/health')
        print(f'    Status: {resp.status_code}')

        # 测试 2: 直接访问你的项目(无认证)
        print(f'\n[2] GET project (no auth): {PROJECT_ID}')
        resp = await client.get(f'/api/projects/{PROJECT_ID}')
        print(f'    Status: {resp.status_code}')
        print(f'    Body: {resp.text[:300]}')

        # 测试 3: 不带 token 的任务查询
        print(f'\n[3] GET task status (no auth): {TASK_ID}')
        resp = await client.get(f'/api/tasks/{TASK_ID}')
        print(f'    Status: {resp.status_code}')
        print(f'    Body: {resp.text[:300]}')

asyncio.run(test())
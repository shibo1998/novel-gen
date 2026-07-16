import asyncio
import httpx
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')

BASE = 'http://localhost:8000'

async def test():
    async with httpx.AsyncClient(base_url=BASE, timeout=60.0) as client:
        # 登录
        print('[1] Login')
        resp = await client.post('/api/auth/login', json={
            'email': 'test4@example.com',
            'password': 'test123456'
        })
        print(f'    Status: {resp.status_code}')
        if resp.status_code != 200:
            print(resp.text)
            return
        token = resp.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}

        # 创建一个新项目
        print('\n[2] Create new project')
        resp = await client.post('/api/projects', headers=headers, json={
            'title': '测试项目-Bug复现',
            'core_idea': '一个用来测试后端世界观生成bug修复的全新测试小说故事',
            'genre': '玄幻',
            'tone_style': '严肃',
            'target_word_count': 100000
        })
        print(f'    Status: {resp.status_code}')
        project = resp.json()
        pid = project['id']
        print(f'    Project ID: {pid}')

        # 触发世界观
        print(f'\n[3] Trigger worldbuilding for {pid}')
        resp = await client.post(f'/api/projects/{pid}/worldbuilding', headers=headers, json={'regenerate': False})
        print(f'    Status: {resp.status_code}')
        print(f'    Body: {resp.text[:300]}')
        if resp.status_code != 200:
            return
        task_id = resp.json()['task_id']

        # 轮询任务状态
        print(f'\n[4] Poll task status: {task_id}')
        for i in range(60):
            await asyncio.sleep(2)
            r = await client.get(f'/api/projects/tasks/{task_id}', headers=headers)
            if r.status_code != 200:
                print(f'    [{i}] Poll failed: {r.status_code}')
                continue
            status = r.json()
            print(f'    [{i}] status={status.get("status")}, error={status.get("error")}')
            if status.get('status') in ('completed', 'failed'):
                break

        # 验证 GET 能否拿到
        print(f'\n[5] GET worldbuilding after generation')
        resp = await client.get(f'/api/projects/{pid}/worldbuilding', headers=headers)
        print(f'    Status: {resp.status_code}')
        print(f'    Body length: {len(resp.text)}')
        print(f'    Body preview: {resp.text[:500]}')

asyncio.run(test())
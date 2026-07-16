import asyncio
import httpx
import sys

sys.stdout.reconfigure(encoding='utf-8')

async def test():
    async with httpx.AsyncClient(base_url='http://localhost:8000', timeout=30.0) as client:
        # 登录
        resp = await client.post('/api/auth/login', json={
            'email': 'test4@example.com',
            'password': 'test123456'
        })
        print(f'Login: {resp.status_code}')
        if resp.status_code != 200:
            return
        token = resp.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}

        # 模拟用户场景：访问项目 ID 7307b914
        pid = '7307b914-14b3-45e9-b7a1-959ee4ebd60e'

        print(f'\n[1] GET /api/projects/{pid}')
        resp = await client.get(f'/api/projects/{pid}', headers=headers)
        print(f'    Status: {resp.status_code}')
        print(f'    Body: {resp.text[:500]}')

        print(f'\n[2] GET /api/projects/{pid}/worldbuilding')
        resp = await client.get(f'/api/projects/{pid}/worldbuilding', headers=headers)
        print(f'    Status: {resp.status_code}')
        print(f'    Body: {resp.text[:500]}')

        # 列出所有项目，找一下这个 ID
        print(f'\n[3] List all projects')
        resp = await client.get('/api/projects', headers=headers)
        print(f'    Status: {resp.status_code}')
        if resp.status_code == 200:
            projects = resp.json()
            for p in projects:
                print(f'    - {p["id"]} : {p.get("title", "N/A")}')

asyncio.run(test())
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

        # 获取所有项目
        resp = await client.get('/api/projects', headers=headers)
        print(f'List projects: {resp.status_code}')
        projects = resp.json()
        print(f'Projects count: {len(projects)}')

        if projects:
            pid = projects[0]['id']
            print(f'\nTest project: {pid}')
            print(f'Project status: {projects[0]["status"]}')
            print(f'Project data keys: {list(projects[0].get("data", {}).keys())}')

            # 测试 worldbuilding 路由
            print(f'\n[1] GET /api/projects/{pid}/worldbuilding')
            resp = await client.get(f'/api/projects/{pid}/worldbuilding', headers=headers)
            print(f'    Status: {resp.status_code}')
            print(f'    Body: {resp.text[:300]}')

            print(f'\n[2] GET /api/projects/{pid}/outline')
            resp = await client.get(f'/api/projects/{pid}/outline', headers=headers)
            print(f'    Status: {resp.status_code}')
            print(f'    Body: {resp.text[:300]}')

asyncio.run(test())

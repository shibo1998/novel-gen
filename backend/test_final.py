import asyncio
import httpx
import sys

sys.stdout.reconfigure(encoding='utf-8')

async def test():
    async with httpx.AsyncClient(base_url='http://localhost:8000', timeout=30.0) as client:
        # 1. 登录
        print('[1] Login with test4@example.com')
        resp = await client.post('/api/auth/login', json={
            'email': 'test4@example.com',
            'password': 'test123456'
        })
        print(f'    Status: {resp.status_code}')
        if resp.status_code != 200:
            return
        token = resp.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}

        # 2. 列出所有项目
        print(f'\n[2] List projects')
        resp = await client.get('/api/projects', headers=headers)
        print(f'    Status: {resp.status_code}')
        if resp.status_code != 200:
            print(f'    Body: {resp.text[:300]}')
            return
        projects = resp.json()
        print(f'    Count: {len(projects)}')
        for p in projects:
            print(f'    - {p["id"]} : {p.get("title", "N/A")}')

        # 3. 把 7307b914 直接 GET 试一下
        print(f'\n[3] GET project 7307b914')
        resp = await client.get('/api/projects/7307b914-14b3-45e9-b7a1-959ee4ebd60e', headers=headers)
        print(f'    Status: {resp.status_code}')
        print(f'    Body: {resp.text[:300]}')

asyncio.run(test())
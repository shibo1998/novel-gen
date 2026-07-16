"""完整流程测试"""
import asyncio
import httpx
import sys

async def full_test():
    base_url = "http://localhost:8000"
    
    async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
        print("=== 完整流程测试 ===\n")
        
        # 1. 注册用户
        print("1. 注册用户...")
        resp = await client.post("/api/auth/register", json={
            "email": "fulltest@example.com",
            "username": "fulltest",
            "password": "test123456"
        })
        print(f"   Register: {resp.status_code}")
        
        # 2. 登录
        print("\n2. 登录...")
        resp = await client.post("/api/auth/login", json={
            "email": "fulltest@example.com",
            "password": "test123456"
        })
        print(f"   Login: {resp.status_code}")
        if resp.status_code != 200:
            print("   [SKIP] Login failed, skipping remaining tests")
            return
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # 3. 创建项目
        print("\n3. 创建项目...")
        resp = await client.post("/api/projects",
            json={
                "title": "完整测试小说",
                "core_idea": "一个年轻剑客在修仙世界中追求至高剑道的故事。他出身寒门，机缘巧合拜入名门正派，却发现自己身怀上古邪功血脉。他在正邪两道之间挣扎，最终选择以剑证道，斩断命运的枷锁。故事包含门派恩怨、天下纷争、爱恨情仇，最终主角领悟剑道真谛，成为一代宗师。",
                "genre": "玄幻",
                "tone_style": "热血"
            },
            headers=headers
        )
        print(f"   Create Project: {resp.status_code}")
        if resp.status_code != 201:
            print("   [SKIP] Create project failed")
            return
        project_id = resp.json()["id"]
        print(f"   Project ID: {project_id}")
        
        # 4. 生成世界观
        print("\n4. 生成世界观...")
        resp = await client.post(f"/api/projects/{project_id}/worldbuilding",
            json={"regenerate": False},
            headers=headers
        )
        print(f"   Trigger: {resp.status_code}")
        if resp.status_code != 200:
            print(f"   [ERROR] {resp.text}")
            return
        task_id = resp.json()["task_id"]
        
        # 轮询
        print("   等待完成...")
        for i in range(60):
            await asyncio.sleep(3)
            resp = await client.get(f"/api/projects/tasks/{task_id}", headers=headers)
            status = resp.json()
            print(f"   [{i+1}] {status['status']}")
            if status["status"] in ["completed", "failed"]:
                if status["status"] == "completed":
                    print("   [OK] 世界观生成完成!")
                    # 获取结果
                    resp = await client.get(f"/api/projects/{project_id}/worldbuilding", headers=headers)
                    wb = resp.json()
                    print(f"   - Setting doc: {len(wb.get('setting_document', ''))} chars")
                    print(f"   - Hard constraints: {len(wb.get('constraints', {}).get('hard', []))}")
                    print(f"   - Conflict seeds: {len(wb.get('conflict_seeds', []))}")
                else:
                    print(f"   [ERROR] {status.get('error')}")
                break
        
        # 5. 生成大纲
        print("\n5. 生成大纲...")
        resp = await client.post(f"/api/projects/{project_id}/outline",
            json={"regenerate": False},
            headers=headers
        )
        print(f"   Trigger: {resp.status_code}")
        if resp.status_code != 200:
            print(f"   [ERROR] {resp.text}")
            return
        task_id = resp.json()["task_id"]
        
        # 轮询
        print("   等待完成...")
        for i in range(60):
            await asyncio.sleep(3)
            resp = await client.get(f"/api/projects/tasks/{task_id}", headers=headers)
            status = resp.json()
            print(f"   [{i+1}] {status['status']}")
            if status["status"] in ["completed", "failed"]:
                if status["status"] == "completed":
                    print("   [OK] 大纲生成完成!")
                    # 获取结果
                    resp = await client.get(f"/api/projects/{project_id}/outline", headers=headers)
                    outline = resp.json()
                    print(f"   - Volumes: {len(outline.get('volumes', []))}")
                    print(f"   - Chapters: {len(outline.get('chapters', []))}")
                    print(f"   - Foreshadowings: {len(outline.get('foreshadowing_registry', []))}")
                else:
                    print(f"   [ERROR] {status.get('error')}")
                break
        
        print("\n=== 测试完成 ===")

asyncio.run(full_test())

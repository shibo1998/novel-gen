import asyncio
import httpx
import sys

async def test():
    try:
        async with httpx.AsyncClient(base_url='http://localhost:8000', timeout=60.0) as client:
            resp = await client.post('/api/auth/register', json={
                'email': 'test4@example.com',
                'username': 'testuser4',
                'password': 'test123456'
            })
            print(f'Register: {resp.status_code}')

            resp = await client.post('/api/auth/login', json={
                'email': 'test4@example.com',
                'password': 'test123456'
            })
            print(f'Login: {resp.status_code}')
            if resp.status_code == 200:
                token = resp.json()['access_token']
                headers = {'Authorization': f'Bearer {token}'}

                resp = await client.post('/api/projects',
                    json={
                        'title': 'Test Novel',
                        'core_idea': 'A young swordsman in a cultivation world seeking the ultimate sword path. He faces powerful enemies, discovers ancient secrets, and must choose between power and righteousness.',
                        'genre': 'Fantasy',
                        'tone_style': 'Epic'
                    },
                    headers=headers
                )
                print(f'Create Project: {resp.status_code}')
                project = resp.json()
                project_id = project['id']
                print(f'Project ID: {project_id}')

                resp = await client.post(f'/api/projects/{project_id}/worldbuilding',
                    json={'regenerate': False},
                    headers=headers
                )
                result = resp.json()
                print(f'Trigger WB: {resp.status_code}, task_id={result.get("task_id")}')
                
                if resp.status_code == 200:
                    task_id = result['task_id']
                    # Poll for completion
                    for i in range(30):
                        await asyncio.sleep(5)
                        resp = await client.get(f'/api/projects/tasks/{task_id}', headers=headers)
                        status = resp.json()
                        print(f'Poll {i+1}: status={status["status"]}')
                        if status['status'] in ['completed', 'failed']:
                            if status['status'] == 'completed':
                                print('SUCCESS! Worldbuilding completed!')
                                # Get result
                                resp = await client.get(f'/api/projects/{project_id}/worldbuilding', headers=headers)
                                wb = resp.json()
                                print(f'Setting doc length: {len(wb.get("setting_document", ""))}')
                                print(f'Hard constraints: {len(wb.get("constraints", {}).get("hard", []))}')
                                print(f'Conflict seeds: {len(wb.get("conflict_seeds", []))}')
                            else:
                                print(f'FAILED: {status.get("error")}')
                            break
    except Exception as e:
        import traceback
        print(f'Error: {e}')
        traceback.print_exc()

asyncio.run(test())

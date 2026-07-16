import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.main import app

routes = []
for r in app.routes:
    if hasattr(r, 'methods') and hasattr(r, 'path'):
        methods = list(r.methods)[0] if r.methods else '?'
        routes.append(f'{methods:6} {r.path}')

print('\n'.join(sorted(routes)))
print(f'\nTotal: {len(routes)} routes')

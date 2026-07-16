@echo off
echo === 停止旧的后端进程 ===
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *uvicorn*" 2>nul
taskkill /F /IM python.exe /FI "MEMORY gt 50000" 2>nul

echo === 启动后端 ===
cd /d d:\1-Study\Ai_project\AI-Novel\code\novel-gen\backend
poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

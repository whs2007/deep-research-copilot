@echo off
:: 杀掉旧进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8002"') do taskkill /F /PID %%a 2>nul
:: 启动
cd /d "%~dp0"
python -m uvicorn app.api.server:app --host 0.0.0.0 --port 8002
pause

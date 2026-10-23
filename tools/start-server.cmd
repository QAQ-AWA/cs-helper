@echo off
setlocal
cd /d "%~dp0.."

set "PY=%~dp0..\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [x] 未找到 .venv
  echo     请先执行: python -m venv .venv
  echo              .venv\Scripts\pip install -r server\requirements.txt
  exit /b 1
)

if "%CS_HELPER_SERVER_SECRET%"=="" set "CS_HELPER_SERVER_SECRET=change-me-before-sharing"
if "%CS_HELPER_DEMO%"=="" set "CS_HELPER_DEMO=1"
if "%CS_HELPER_DEV%"=="" set "CS_HELPER_DEV=0"
if not "%CS_HELPER_AI_KEY%"=="" echo [i] AI 已配置: %CS_HELPER_AI_MODEL%

echo.
echo   房间服务: http://127.0.0.1:8787
echo   手机访问: http://^<本机内网IP^>:8787   (单房间，输昵称即可)
echo   健康检查: http://127.0.0.1:8787/healthz
echo   开发模式: %CS_HELPER_DEV%  (设为 1 可开放 /api/v1/dev/seed-paths)
echo.

"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8787 --app-dir server

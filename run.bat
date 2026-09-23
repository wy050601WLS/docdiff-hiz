@echo off
REM 一键启动（Windows）。首次使用请先执行 install.bat 或按 README 安装依赖。
setlocal

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] 未找到虚拟环境，请先执行：
  echo     python -m venv .venv
  echo     .venv\Scripts\python.exe -m pip install -e ".[dev]"
  exit /b 1
)

echo 启动 DocDiff HIZ，浏览器访问 http://127.0.0.1:8000
.venv\Scripts\python.exe -m uvicorn docdiff.main:app --app-dir src --port 8000

.PHONY: help venv install dev samples verify test lint clean

help:
	@echo "make venv     - 创建虚拟环境 .venv"
	@echo "make install  - 安装运行依赖 + 开发依赖"
	@echo "make docling  - 额外安装 Docling（结构化 PDF 解析，可选但推荐）"
	@echo "make samples  - 生成两份示例 PDF 到 samples/"
	@echo "make verify   - 离线跑通 解析→比对→报告 全链路"
	@echo "make dev      - 启动开发服务 http://127.0.0.1:8000"
	@echo "make test     - 运行单元测试"
	@echo "make lint     - Ruff 检查"

venv:
	python -m venv .venv

install:
	.venv\Scripts\python.exe -m pip install -e ".[dev]"

docling:
	.venv\Scripts\python.exe -m pip install -e ".[docling]"

samples:
	.venv\Scripts\python.exe scripts\make_samples.py

verify:
	.venv\Scripts\python.exe scripts\verify_pipeline.py

dev:
	.venv\Scripts\python.exe -m uvicorn docdiff.main:app --app-dir src --reload --port 8000

test:
	.venv\Scripts\python.exe -m pytest -v

lint:
	.venv\Scripts\python.exe -m ruff check src tests

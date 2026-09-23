"""FastAPI 应用入口。"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from docdiff.api.routes import router
from docdiff.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    """应用生命周期管理。"""
    # startup
    Path("uploads").mkdir(exist_ok=True)
    yield
    # shutdown


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="海致星图面试作业：PDF 文档差异比对系统",
    lifespan=lifespan,
)

# 允许前端跨域（本地开发用）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

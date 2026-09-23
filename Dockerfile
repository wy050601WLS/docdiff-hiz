# 基础镜像用 slim，不装 torch，镜像体积控制在几百 MB。
# 需要 Docling 结构化解析时用 --build-arg WITH_DOCLING=true，届时会自动拉 torch（镜像会大很多）。
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --upgrade pip && pip install .

ARG WITH_DOCLING=false
RUN if [ "$WITH_DOCLING" = "true" ]; then pip install ".[docling]"; fi

# 会话存档目录，挂卷持久化，容器重建不丢
VOLUME ["/app/data"]
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "docdiff.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/root/.cache/huggingface

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY data ./data
COPY scripts ./scripts

# Torch CPU-only cài trước (pod chạy CPU, không cần CUDA): tránh kéo bản CUDA
# mặc định trên PyPI + chùm wheel nvidia-* nhiều GB — build nhanh, image nhỏ,
# đỡ đứt mạng giữa chừng. sentence-transformers/docling thấy torch đã có sẽ không cài lại.
RUN pip install --upgrade pip && \
    pip install --retries 10 --timeout 120 torch torchvision --index-url https://download.pytorch.org/whl/cpu && \
    pip install --retries 10 --timeout 120 -e ".[medical]"

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --retries=5 --start-period=60s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

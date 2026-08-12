FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# No LibreOffice: Pandoc covers the document conversions we need and keeps
# the image ~500MB smaller.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       pandoc \
       tesseract-ocr \
       poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock* ./

RUN pip install --no-cache-dir uv \
    && uv sync --frozen --no-install-project || uv sync --no-install-project

COPY src ./src
COPY apps ./apps
COPY configs ./configs
COPY prompts ./prompts

ENV PYTHONPATH=/app

CMD ["uv", "run", "uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

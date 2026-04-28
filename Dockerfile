FROM python:3.11-slim

RUN DEBIAN_FRONTEND=noninteractive apt-get update && apt-get install -y \
    ca-certificates \
    ffmpeg \
    procps \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /usr/src/app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/usr/src/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock /usr/src/app/
RUN uv sync --frozen --no-dev

COPY . /usr/src/app

CMD ["uv", "run", "python", "asmrone_crawler.py"]

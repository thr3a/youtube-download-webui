# ref: https://docs.astral.sh/uv/guides/integration/docker/
# ref: https://github.com/astral-sh/uv-fastapi-example/blob/main/Dockerfile
FROM python:3.13-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Tokyo
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=on
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ffmpeg ca-certificates crontab && \
    rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

ADD https://raw.githubusercontent.com/smalltownjj/yt-dlp-plugin-missav/refs/heads/main/yt_dlp_plugins/extractor/missav.py /etc/yt-dlp-plugins/yt-dlp-plugin-missav/yt_dlp_plugins/extractor/missav.py
RUN sed -i 's/ws/ai/g' /etc/yt-dlp-plugins/yt-dlp-plugin-missav/yt_dlp_plugins/extractor/missav.py

COPY . /app

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

CMD ["/app/.venv/bin/fastapi", "run", "app/main.py", "--port", "3000"]

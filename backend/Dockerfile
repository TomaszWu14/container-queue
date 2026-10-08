# Obraz API do lokalnego docker-compose.yml (prod: Dockerfile.coolify w katalogu głównym).
FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d

ENV PIP_DISABLE_PIP_VERSION_CHECK=1

# tesseract: OCR skanów faktur (moduł Faktury → Excel); pol+eng jak OCR_LANG
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-pol tesseract-ocr-eng

# uruchamiamy bez roota (zasada najmniejszych uprawnień); użytkownik przed COPY --chown
RUN useradd --create-home --uid 1000 timporye \
    && mkdir -p /app /data/uploads \
    && chown timporye:timporye /app /data /data/uploads

WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --require-hashes -r requirements.txt

COPY --chown=timporye:timporye alembic.ini .
COPY --chown=timporye:timporye migrations ./migrations
COPY --chown=timporye:timporye scripts ./scripts
COPY --chown=timporye:timporye app ./app
USER timporye

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status == 200 else 1)"]
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

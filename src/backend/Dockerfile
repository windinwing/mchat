# Full backend image (includes pymilvus). Build from repo root.
FROM python:3.12-slim AS builder

WORKDIR /app

COPY src/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libfreetype6 \
        libpng16-16 \
        libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r mchat && useradd -r -g mchat mchat -d /app

WORKDIR /app

COPY --from=builder /root/.local /app/.local
COPY src/backend/app/ ./app/
COPY skills/ ./skills/
COPY src/backend/.env.example ./.env.example

ENV PATH=/app/.local/bin:$PATH
ENV UPLOAD_DIR=/app/uploads
ENV SKILLS_DIR=/app/skills

RUN mkdir -p uploads skills logs && chown -R mchat:mchat /app

USER mchat

RUN python -c "from app.main import app; print('app import ok')"

EXPOSE 3001

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3001/api/health')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3001"]

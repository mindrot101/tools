# VXLAN Validator for Aruba CX — single self-contained image.
# One process (uvicorn) serves both the JSON API and the static UI.
# No nginx, no supervisord, no external database, no message broker.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VXV_DATA_DIR=/data \
    VXV_PORT=8080

WORKDIR /app

# Dependencies first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application + UI.
COPY app ./app
COPY web ./web

# Persistent data (SQLite, audit log, generated API key) and switch CA bundle.
RUN mkdir -p /data /certs && \
    useradd -r -u 10001 -d /app vxv && \
    chown -R vxv:vxv /app /data /certs
USER vxv

VOLUME ["/data", "/certs"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=4s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=3).status==200 else 1)"

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ARG UID=1002
ARG GID=1002

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# libcap lets us grant raw-socket capability to the Python binary so the
# non-root app user can perform live capture (only effective when the
# container is started with cap_add: NET_RAW and ENABLE_LIVE_CAPTURE=true).
RUN apt-get update && apt-get install -y --no-install-recommends libcap2-bin \
    && setcap cap_net_raw+eip "$(readlink -f "$(which python3)")" \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd -g ${GID} appuser \
    && useradd -m -u ${UID} -g ${GID} appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

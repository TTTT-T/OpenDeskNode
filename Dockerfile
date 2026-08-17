FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STOCK_GATEWAY_DB_PATH=/data/stock-gateway.sqlite3 \
    STOCK_GATEWAY_LOG_PATH=/data/logs/stock-gateway.log

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --disable-pip-version-check --retries 5 --timeout 120 -r requirements.txt \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin gateway \
    && mkdir -p /data/logs \
    && chown -R gateway:gateway /app /data

COPY gateway ./gateway

USER gateway
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"

CMD ["uvicorn", "gateway.app:app", "--host", "0.0.0.0", "--port", "8000"]

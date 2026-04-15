FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
COPY wheelhouse/openshift-py310 /wheelhouse

RUN pip install --no-cache-dir --no-index --find-links=/wheelhouse -r requirements.txt \
    && rm -rf /wheelhouse

COPY app ./app

RUN adduser --disabled-password --gecos "" appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

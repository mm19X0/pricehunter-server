FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py stores.py ./
RUN useradd --system --uid 10001 app \
    && mkdir /data \
    && chown app:app /data

ENV PRICEHUNTER_DB=/data/prices.db
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
USER app

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app
RUN useradd -r -u 10001 app && mkdir -p /app/data && chown -R app /app/data
USER app
ENV HOST=0.0.0.0 PORT=8080 DB_PATH=/app/data/dhankhoj.db TRUST_PROXY=1
VOLUME /app/data
EXPOSE 8080
CMD ["python3", "server.py"]

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
RUN mkdir -p /data
ENV SENTINEL_DATABASE_PATH=/data/sentinel.db
EXPOSE 8090
CMD ["powersite-sentinel", "serve"]

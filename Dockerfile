FROM python:3.12-alpine

# Install ffmpeg + jq + yt-dlp + FastAPI stack
RUN apk add --no-cache ffmpeg jq && \
    pip install --no-cache-dir yt-dlp fastapi "uvicorn[standard]" aiofiles pydantic

WORKDIR /app

# App files
COPY app /app/app
COPY watch.sh /app/watch.sh
RUN chmod +x /app/watch.sh

ENV CHANNEL_URL=""
ENV INTERVAL_SECONDS=60
ENV OUTPUT_DIR=/downloads
ENV DATA_DIR=/data
ENV GOTIFY_URL=""
ENV GOTIFY_TOKEN=""
ENV TZ="UTC"

# Volumes for data and downloads
VOLUME ["/downloads", "/data"]

EXPOSE 8080

# Run FastAPI app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]

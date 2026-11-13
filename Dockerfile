FROM python:3.15-slim
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
RUN pip install --no-cache-dir '.[dev]'
ENTRYPOINT ["python", "-m", "selfagent"]

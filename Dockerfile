FROM python:3.15-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
RUN pip install --no-cache-dir '.[dev]'
ENTRYPOINT ["python", "-m", "selfagent"]

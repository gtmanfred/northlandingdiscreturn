FROM docker.io/python:3.12-slim
WORKDIR /srv
RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev
COPY . .
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]

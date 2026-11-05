# ============================================================
# Korra (Project 10, Section 4) - the application container.
# Same graph and tools as Section 3; the tools reach PostgreSQL in the
# "db" container because docker-compose sets DATABASE_URL at run time.
# No key or password is copied into this image (.env is in .dockerignore).
# ============================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml langgraph.json ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps -e .

EXPOSE 2024
CMD ["langgraph", "dev", "--host", "0.0.0.0", "--port", "2024", "--no-browser"]

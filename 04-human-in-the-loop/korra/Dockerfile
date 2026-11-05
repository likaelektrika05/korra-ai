# ============================================================
# Supervised Korra (Project 11). Each command runs in a fresh container:
#   docker compose run --rm korra ask --thread t1 "..."
# All state (checkpoints, decisions, audit) lives in the db container's
# volume, so nothing is lost when this container exits or is rebuilt.
# No key or password is copied into the image (.env is in .dockerignore).
# ============================================================
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps -e .
ENTRYPOINT ["python", "-m", "korra_hitl"]
CMD ["pending"]

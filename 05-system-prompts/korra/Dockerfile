# ============================================================
# Korra (Project 12): controlled ReAct CLI.
# The prompts and the behavior cases are mounted read-only by compose
# (/app/prompts, /app/tests); evidence is written to /app/evidence.
# No key or password is copied into the image (.env is in .dockerignore).
# ============================================================
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PROMPTS_DIR=/app/prompts
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps -e .
ENTRYPOINT ["python", "-m", "korra_react"]
CMD ["show-prompt"]

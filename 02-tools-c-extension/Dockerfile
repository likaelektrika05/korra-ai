# ============================================================
# Korra (Project 08): two-stage build
# Stage 1 compiles and tests the C tool for Linux.
# Stage 2 is the runtime image: Python + wrapper + binary, no compiler.
# ============================================================

# ---------- Stage 1: build and test the C tool ----------
FROM python:3.11-slim AS c-build

RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc make libc6-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY tools/ ./

# Compile with the Makefile, then run the 28 checks.
# If any check fails, make exits non-zero and no image is produced.
RUN make rebuild && make test

# ---------- Stage 2: runtime ----------
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Wrapper, test fixtures, and the Linux binary in the SAME folder,
# so file_stats_tool.py finds ./file_stats next to itself
COPY tools/file_stats_tool.py tools/test.txt ./tools/
COPY tools/tests/ ./tools/tests/
COPY --from=c-build /build/file_stats ./tools/file_stats

# .env is included on purpose (see the supplied .dockerignore):
# this image is for local use only and must not be pushed to a registry
COPY FA26_MD_06_S03_chatbot.py .env ./

CMD ["python", "FA26_MD_06_S03_chatbot.py"]
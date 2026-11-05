FROM python:3.11-slim

WORKDIR /korra
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

# No credentials in the image: supply them at runtime with --env-file .env
CMD ["python", "-m", "app.main"]
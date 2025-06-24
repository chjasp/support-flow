# ────────────────────────────────
#  Build image
# ────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# 1) install pip deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) copy app code
COPY app/ ./app/

# 3) conventional Cloud Run port
ENV PORT=8080
EXPOSE 8080

# 4) start API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
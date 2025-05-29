# ────────────────────────────────
#  Build image
# ────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# 1) install pip deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) copy *all* source code
COPY . .

# 3) conventional Cloud Run port
ENV PORT=8080
EXPOSE 8080

# 4) start API
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
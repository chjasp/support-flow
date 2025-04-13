FROM python:3.10-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./main.py /app/

# Expose the port the app runs on
EXPOSE 8080

# Set environment variable for the port
ENV PORT=8080
# Set GCP_PROJECT environment variable during Cloud Run deployment or here if static
# ENV GCP_PROJECT="your-gcp-project-id"

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
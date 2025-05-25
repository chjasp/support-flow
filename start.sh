#!/bin/bash

echo "🚀 Starting Support Flow..."

# Start backend in background
echo "Starting backend..."
cd 02-backend
source venv/bin/activate
uvicorn main:app --reload --port 8000 &

# Start frontend
echo "Starting frontend..."
cd ../01-frontend
npm run dev 
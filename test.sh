curl -X POST "http://127.0.0.1:8000/process-file" \
     -H "Content-Type: application/json" \
     -d '{
           "gcs_uri": "gs://knowledge-base-431619/uploads/70ab452c-c3a5-43c2-b1d5-bc1240a79c31-what-is-an-ai-agent.pdf",
           "original_filename": "what-is-an-ai-agent.pdf"
         }'

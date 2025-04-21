curl -X POST "http://127.0.0.1:5147/process-file" \
     -H "Content-Type: application/json" \
     -d '{
           "gcs_uri": "gs://knowledge-base-431619/uploads/85fea484-1306-4f94-806e-4b28cad6e581-mckinsey-1.pdf",
           "original_filename": "mckinsey-1.pdf"
         }'

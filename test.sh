curl -X POST "http://127.0.0.1:5147/process-file" \
     -H "Content-Type: application/json" \
     -d '{
           "gcs_uri": "gs://knowledge-base-431619/uploads/aed5211a-d320-4f1e-94a9-db18e166faf3-test-form-456.pdf",
           "original_filename": "test-form-456.pdf"
         }'

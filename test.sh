curl -X POST "http://127.0.0.1:5147/process-file" \
     -H "Content-Type: application/json" \
     -d '{
           "gcs_uri": "gs://knowledge-base-431619/uploads/103a8880-568d-468a-a11d-765e869cf6bb-cv_christoph_jasper.pdf",
           "original_filename": "cv_christoph_jasper.pdf"
         }'

curl -X POST "http://127.0.0.1:5147/process-pdf" \
     -H "Content-Type: application/json" \
     -d '{
           "gcs_uri": "gs://knowledge-base-431619/uploads/76abf449-62ae-4f85-b84b-abd79ffb712f-Sinn-Online-Bestellung.pdf",
           "original_filename": "Sinn-Online-Bestellung.pdf"
         }'

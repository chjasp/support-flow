# 3D Document Visualization Implementation

This document describes the implementation of the 3D coordinate system for visualizing documents based on their semantic embeddings.

## Overview

The 3D visualization system allows you to:
1. **Scrape web content** (like Google Cloud documentation) and process it for both RAG and 3D visualization
2. **Generate embeddings** using Google's text-embedding-004 model
3. **Reduce dimensionality** from 768D to 3D using UMAP for visualization
4. **Store 3D coordinates** in the database alongside regular embeddings
5. **Visualize documents** in a 3D space where similar content clusters together

## Architecture

### Database Schema
- `documents`: Stores document metadata
- `chunks`: Stores text chunks with 768D embeddings for RAG
- `chunks_3d`: Stores 3D coordinates (x, y, z) for visualization

### Services
- **Processing Service** (`03-processing/`): Handles web scraping, embedding generation, and 3D coordinate calculation
- **Backend API** (`02-backend/`): Provides endpoints for URL processing and 3D data retrieval
- **Frontend** (`01-frontend/`): 3D visualization using Three.js and React Three Fiber

## Setup Instructions

### 1. Database Setup
Run the updated bootstrap script to create the 3D tables:
```bash
cd 03-processing
psql -h YOUR_CLOUD_SQL_IP -U YOUR_USER -d docs -f bootstrap.sql
```

### 2. Install Dependencies
Update the processing service dependencies:
```bash
cd 03-processing
pip install -r requirements.txt
```

### 3. Environment Variables
Ensure these environment variables are set:
```bash
GOOGLE_CLOUD_PROJECT=your-project-id
CLOUD_SQL_INSTANCE=your-instance-connection-name
CLOUD_SQL_USER=your-db-user
CLOUD_SQL_PASSWORD=your-db-password
CLOUD_SQL_DB=docs
EMBED_MODEL=text-embedding-004
PROCESSING_SERVICE_URL=http://localhost:8080  # For backend config
```

## Usage

### One-Time Population with Google Cloud Docs

To populate your database with Google Cloud documentation:

```bash
cd 03-processing
python populate_gcp_docs.py
```

This script will:
- Scrape ~50 Google Cloud documentation pages
- Generate embeddings for all content chunks
- Calculate 3D coordinates using UMAP dimensionality reduction
- Store everything in your database

### Processing Individual URLs

#### Via API (Recommended for Integration)
```bash
curl -X POST "http://localhost:8000/web/process-urls" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://cloud.google.com/docs/overview",
      "https://cloud.google.com/compute/docs/instances/create-start-instance"
    ],
    "description": "GCP core documentation"
  }'
```

#### Via Processing Service Directly
```bash
curl -X POST "http://localhost:8080/process-urls" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://cloud.google.com/docs/overview"
    ]
  }'
```

### Viewing 3D Visualization

1. Start your frontend application
2. Navigate to the main page
3. The 3D visualization will automatically load documents with their real coordinates
4. Documents will be positioned based on semantic similarity
5. You can interact with the 3D space:
   - **Rotate**: Click and drag
   - **Zoom**: Mouse wheel
   - **Pan**: Right-click and drag
   - **Hover**: See document details
   - **Click**: Select documents

## API Endpoints

### Backend API (`/web` prefix)

- `POST /web/process-urls`: Process a list of URLs
- `GET /web/tasks/{task_id}`: Check processing status
- `GET /web/documents-3d`: Get all documents with 3D coordinates
- `GET /web/google-cloud-urls`: Get predefined GCP documentation URLs
- `DELETE /web/tasks/{task_id}`: Clean up completed tasks

### Processing Service

- `POST /process-urls`: Direct URL processing
- `POST /`: Original GCS blob processing (unchanged)

### Global Coordinate Recompute

To keep the 3D layout stable across all documents, run the mapping script after
new files or URLs are ingested:

```bash
python 04-mapping/main.py
```

This script loads every embedding from the database, performs UMAP reduction in
one batch, and updates the `chunks_3d` table with fresh coordinates.

## Technical Details

### Dimensionality Reduction
- **Algorithm**: UMAP (Uniform Manifold Approximation and Projection)
- **Parameters**:
  - `n_components=3`: Reduce to 3D
  - `n_neighbors=15`: Local neighborhood size
  - `min_dist=0.1`: Minimum distance between points
  - `metric='cosine'`: Distance metric for embeddings
  - `random_state=42`: Reproducible results

### Coordinate Scaling
- Coordinates are scaled to fit approximately in the range [-10, 10]
- This ensures good visualization in the 3D space
- Similar documents cluster together naturally

### Performance Considerations
- **Batch Processing**: URLs are processed in batches to avoid overwhelming the system
- **Rate Limiting**: 100ms delay between embedding API calls
- **Error Handling**: Failed URLs are logged but don't stop the entire process
- **Memory Management**: Large batches are processed in chunks

## Customization

### Adding New Document Sources
1. Extend the `WebDocumentProcessor` class in `scraper.py`
2. Add new URL patterns or content extraction logic
3. Update the `get_comprehensive_gcp_urls()` function with new URLs

### Adjusting 3D Positioning
1. Modify UMAP parameters in `reduce_to_3d()` method
2. Experiment with different `n_neighbors` and `min_dist` values
3. Try different distance metrics (`cosine`, `euclidean`, `manhattan`)

### Frontend Customization
1. Adjust document colors in `getDocumentColorByType()`
2. Modify sphere sizes based on different criteria
3. Add new interaction modes or filters

## Troubleshooting

### Common Issues

1. **No 3D coordinates showing**
   - Check if `chunks_3d` table exists and has data
   - Verify the API endpoint `/web/documents-3d` returns data
   - Check browser console for JavaScript errors

2. **Processing fails**
   - Verify all environment variables are set
   - Check database connectivity
   - Ensure the embedding model is accessible

3. **Poor clustering in 3D space**
   - Try different UMAP parameters
   - Ensure you have enough diverse content
   - Check if embeddings are being generated correctly

### Debugging
- Check processing service logs: `docker logs <processing-container>`
- Check backend API logs: `docker logs <backend-container>`
- Use browser dev tools to inspect API calls
- Query the database directly to verify data

## Future Enhancements

1. **Real-time Updates**: WebSocket connections for live processing status
2. **Advanced Clustering**: K-means or hierarchical clustering overlays
3. **Interactive Filtering**: Filter by date, source, topic, etc.
4. **Chunk-level Visualization**: Show individual chunks instead of document averages
5. **Collaborative Features**: Multiple users exploring the same 3D space
6. **Export Capabilities**: Save 3D views or export coordinate data

## Performance Metrics

Expected processing times (approximate):
- **Single URL**: 5-15 seconds
- **Batch of 5 URLs**: 30-60 seconds  
- **Full GCP docs (~50 URLs)**: 10-20 minutes
- **3D coordinate calculation**: 1-5 seconds per batch

Storage requirements:
- **Text chunks**: ~1KB per chunk
- **768D embeddings**: ~3KB per chunk
- **3D coordinates**: ~12 bytes per chunk
- **Metadata**: ~200 bytes per document 
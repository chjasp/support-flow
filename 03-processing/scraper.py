import asyncio
import logging
import os
import uuid
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urljoin, urlparse
import time

import requests
from bs4 import BeautifulSoup
import tiktoken
import numpy as np
from sklearn.preprocessing import StandardScaler
import umap

import vertexai
from vertexai.language_models import TextEmbeddingModel
from google.cloud.sql.connector import Connector, IPTypes
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Environment setup
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "test-project")
LOCATION = os.environ.get("LOCATION", "europe-west3")
INSTANCE_CONNECTION_NAME = os.environ.get("CLOUD_SQL_INSTANCE", "test:instance")
DB_USER = os.environ.get("CLOUD_SQL_USER", "test-user")
DB_PASS = os.environ.get("CLOUD_SQL_PASSWORD", "test-pass")
DB_NAME = os.environ.get("CLOUD_SQL_DB", "test-db")
IP_TYPE_ENV = os.environ.get("CLOUD_SQL_IP_TYPE", "PRIVATE").upper()
IP_TYPE = IPTypes.PRIVATE if IP_TYPE_ENV == "PRIVATE" else IPTypes.PUBLIC
EMBED_MODEL = os.environ.get("EMBED_MODEL", "text-embedding-004")

# Configure logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info(f"🚀 Initializing WebDocumentProcessor with PROJECT_ID: {PROJECT_ID}")

# Initialize Vertex AI only if we have real credentials
embedding_model = None
try:
    logger.info(f"🔑 Attempting to initialize Vertex AI with project: {PROJECT_ID}, location: {LOCATION}")
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    embedding_model = TextEmbeddingModel.from_pretrained(EMBED_MODEL)
    logger.info(f"✅ Successfully initialized Vertex AI with model: {EMBED_MODEL}")
except Exception as e:
    logger.warning(f"⚠️ Could not initialize Vertex AI: {e}")
    logger.info("💡 Tip: Run 'gcloud auth application-default login' if you see auth errors")
    embedding_model = None

tokenizer = tiktoken.get_encoding("cl100k_base")
connector = Connector()

class WebDocumentProcessor:
    """Processes web documents for both RAG and 3D visualization."""
    
    def __init__(self):
        logger.info("🌐 Initializing web session...")
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; DocumentProcessor/1.0)'
        })
        logger.info("✅ Web session initialized")

    def _fetch_with_js_fallback(self, url: str) -> requests.Response:
        """Fetch a URL and retry via a prerender service if JS is required."""
        logger.info(f"📡 Sending HTTP request to {url}")

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.warning(f"⚠️ Initial request failed: {e}")
            response = None

        needs_fallback = (
            response is None
            or b"Please enable Javascript" in response.content
        )

        if needs_fallback:
            logger.info("🔄 Detected JavaScript-only page, using r.jina.ai fallback")
            fallback_url = f"https://r.jina.ai/{url}"
            try:
                response = self.session.get(fallback_url, timeout=30)
                response.raise_for_status()
                if b"Please enable Javascript" in response.content:
                    raise ValueError("Fallback did not return usable content")
            except Exception as fallback_err:
                logger.error(f"❌ Error using JS fallback: {fallback_err}")
                raise

        return response
    
    @contextmanager
    def _connect(self):
        """Database connection context manager."""
        logger.info(f"🔌 Connecting to database: {INSTANCE_CONNECTION_NAME}")
        conn = None
        try:
            conn = connector.connect(
                INSTANCE_CONNECTION_NAME,
                "pg8000",
                user=DB_USER,
                password=DB_PASS,
                db=DB_NAME,
                ip_type=IPTypes.PUBLIC,  # Use PUBLIC IP like the backend service
            )
            logger.info("✅ Database connection established")
            yield conn
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
        finally:
            if conn:  # Only close if connection was established
                conn.close()
                logger.info("🔌 Database connection closed")
    
    def scrape_url(self, url: str) -> Dict[str, Any]:
        """Scrape content from a URL."""
        logger.info(f"🌐 Starting to scrape URL: {url}")
        try:
            response = self._fetch_with_js_fallback(url)
            logger.info(f"✅ HTTP request successful, status: {response.status_code}")
            
            logger.info("🔍 Parsing HTML content...")
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract meaningful content
            logger.info("🧹 Cleaning up HTML content...")
            # Remove script, style, nav, footer, and sidebar elements
            for element in soup(["script", "style", "nav", "footer", "aside", "header"]):
                element.decompose()
            
            # Try to find main content areas
            logger.info("🎯 Looking for main content area...")
            main_content = (
                soup.find('main') or
                soup.find('article') or
                soup.find('div', class_=lambda x: x and 'content' in x.lower()) or
                soup.find('div', class_=lambda x: x and 'main' in x.lower()) or
                soup.find('div', id=lambda x: x and 'content' in x.lower()) or
                soup.body or
                soup
            )
            
            if main_content:
                # Extract title
                logger.info("📄 Extracting title...")
                title = (
                    soup.find('h1') or 
                    soup.find('title')
                )
                title_text = title.get_text().strip() if title else urlparse(url).path
                logger.info(f"📄 Found title: {title_text}")
                
                # Extract text content
                logger.info("📝 Extracting text content...")
                text_content = main_content.get_text(separator='\n', strip=True)
                
                # Clean up the text
                lines = [line.strip() for line in text_content.split('\n') if line.strip()]
                clean_text = '\n'.join(lines)
                
                logger.info(f"✅ Successfully scraped {len(clean_text)} characters from {url}")
                
                return {
                    'url': url,
                    'title': title_text,
                    'content': clean_text,
                    'length': len(clean_text),
                    'status': 'success'
                }
            else:
                raise ValueError("No main content found")
                
        except Exception as e:
            logger.error(f"❌ Error scraping {url}: {e}")
            return {
                'url': url,
                'title': url,
                'content': '',
                'length': 0,
                'status': 'error',
                'error': str(e)
            }
    
    def chunk_text(self, text: str, max_tokens: int = 800, overlap: int = 200) -> List[str]:
        """Chunk text into smaller pieces for embedding."""
        logger.info(f"✂️ Chunking text of {len(text)} characters...")
        logger.info(f"📐 Using max_tokens={max_tokens}, overlap={overlap}")
        
        tokens = tokenizer.encode(text)
        logger.info(f"🎯 Text encoded to {len(tokens)} tokens")
        
        segments = []
        start = 0
        
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            chunk = tokenizer.decode(tokens[start:end])
            segments.append(chunk)
            
            if end == len(tokens):
                break
            start = end - overlap if overlap else end
        
        logger.info(f"✅ Created {len(segments)} chunks from text")
        return segments
    
    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for a list of texts."""
        logger.info(f"🧠 Getting embeddings for {len(texts)} texts...")
        
        if embedding_model is None:
            logger.warning("⚠️ Embedding model not available, returning dummy embeddings")
            logger.info("💡 This is fine for testing 3D reduction, but you won't get real semantic embeddings")
            dummy_embeddings = [[0.1] * 768 for _ in range(len(texts))]
            logger.info(f"🎭 Generated {len(dummy_embeddings)} dummy embeddings")
            return dummy_embeddings
            
        all_embeddings = []
        batch_size = 100  # text-embedding-004 limit
        total_batches = (len(texts) + batch_size - 1) // batch_size
        
        for i in range(0, len(texts), batch_size):
            batch_num = i // batch_size + 1
            batch = texts[i:i + batch_size]
            
            logger.info(f"🔄 Processing batch {batch_num}/{total_batches} ({len(batch)} texts)")
            
            try:
                embeddings = embedding_model.get_embeddings(batch)
                all_embeddings.extend([emb.values for emb in embeddings])
                logger.info(f"✅ Successfully processed batch {batch_num}")
                time.sleep(0.1)  # Rate limiting
            except Exception as e:
                logger.error(f"❌ Error getting embeddings for batch {batch_num}: {e}")
                # Add zero vectors for failed embeddings
                zero_embeddings = [[0.0] * 768] * len(batch)
                all_embeddings.extend(zero_embeddings)
                logger.warning(f"⚠️ Using zero embeddings for failed batch {batch_num}")
        
        logger.info(f"✅ Generated {len(all_embeddings)} embeddings total")
        return all_embeddings
    
    def reduce_to_3d(self, embeddings: List[List[float]], method: str = 'umap') -> List[Tuple[float, float, float]]:
        """Reduce high-dimensional embeddings to 3D coordinates."""
        logger.info(f"🎯 Reducing {len(embeddings)} embeddings to 3D using {method}...")
        
        if not embeddings:
            logger.warning("⚠️ No embeddings provided for 3D reduction")
            return []
        
        logger.info("📊 Converting embeddings to numpy array...")
        embeddings_array = np.array(embeddings)
        logger.info(f"📐 Embeddings shape: {embeddings_array.shape}")
        
        # Standardize the embeddings
        logger.info("📏 Standardizing embeddings...")
        scaler = StandardScaler()
        embeddings_scaled = scaler.fit_transform(embeddings_array)
        logger.info("✅ Embeddings standardized")
        
        # For very small datasets, use PCA instead of UMAP
        n_samples = len(embeddings)
        if n_samples < 10:
            logger.info(f"📊 Small dataset ({n_samples} samples), using PCA instead of UMAP for better stability")
            from sklearn.decomposition import PCA
            reducer = PCA(n_components=min(3, n_samples), random_state=42)
        elif method == 'umap':
            logger.info("🗺️ Initializing UMAP reducer...")
            # Adjust parameters for small datasets
            n_neighbors = min(15, max(2, n_samples - 1))
            logger.info(f"📐 Using n_neighbors={n_neighbors} for dataset of size {n_samples}")
            
            reducer = umap.UMAP(
                n_components=3,
                n_neighbors=n_neighbors,
                min_dist=0.1,
                metric='cosine',
                random_state=42
            )
        else:
            raise ValueError(f"Unsupported reduction method: {method}")
        
        logger.info("🔄 Fitting reducer and transforming to 3D...")
        coords_3d = reducer.fit_transform(embeddings_scaled)
        logger.info(f"✅ Reduction completed, shape: {coords_3d.shape}")
        
        # Handle cases where we get fewer dimensions than expected
        if coords_3d.shape[1] < 3:
            logger.info(f"📐 Got {coords_3d.shape[1]}D output, padding to 3D...")
            # Pad with zeros to make it 3D
            padding = np.zeros((coords_3d.shape[0], 3 - coords_3d.shape[1]))
            coords_3d = np.hstack([coords_3d, padding])
        
        # Scale coordinates to fit nicely in the 3D visualization
        logger.info("📏 Scaling coordinates to [-10, 10] range...")
        max_val = np.max(np.abs(coords_3d))
        if max_val > 0:
            coords_3d = coords_3d * 10 / max_val
        else:
            logger.warning("⚠️ All coordinates are zero, using random positions")
            # Generate small random positions for zero coordinates
            coords_3d = np.random.uniform(-1, 1, coords_3d.shape)
        
        result = [(float(x), float(y), float(z)) for x, y, z in coords_3d]
        logger.info(f"✅ Generated {len(result)} 3D coordinates")
        
        # Log some sample coordinates
        if len(result) > 0:
            logger.info(f"📍 Sample coordinates:")
            for i, (x, y, z) in enumerate(result[:3]):
                logger.info(f"   Point {i+1}: ({x:.2f}, {y:.2f}, {z:.2f})")
        
        return result
    
    def store_document_chunks(self, url: str, title: str, chunks: List[str], 
                            embeddings: List[List[float]], coords_3d: List[Tuple[float, float, float]]) -> str:
        """Store document chunks in the database."""
        doc_id = str(uuid.uuid4())
        logger.info(f"💾 Storing document with ID: {doc_id}")
        logger.info(f"📄 Title: {title}")
        logger.info(f"🔗 URL: {url}")
        logger.info(f"📊 Chunks: {len(chunks)}, Embeddings: {len(embeddings)}, Coordinates: {len(coords_3d)}")
        
        with self._connect() as conn:
            cur = None
            try:
                cur = conn.cursor()
                # Insert document
                logger.info("💾 Inserting document record...")
                cur.execute("""
                    INSERT INTO documents (id, filename, original_gcs, status)
                    VALUES (%s, %s, %s, %s)
                """, (doc_id, title, url, 'Ready'))
                logger.info("✅ Document record inserted")
                
                # Insert chunks and embeddings
                logger.info(f"💾 Inserting {len(chunks)} chunks...")
                for i, (chunk, embedding, (x, y, z)) in enumerate(zip(chunks, embeddings, coords_3d)):
                    if i % 10 == 0:  # Log progress every 10 chunks
                        logger.info(f"📝 Processing chunk {i+1}/{len(chunks)}")
                    
                    # Insert chunk
                    cur.execute("""
                        INSERT INTO chunks (doc_id, chunk_index, text, embedding)
                        VALUES (%s, %s, %s, %s::vector)
                        RETURNING id
                    """, (doc_id, i, chunk, str(embedding)))
                    
                    chunk_id = cur.fetchone()[0]
                    
                    # Insert 3D coordinates
                    cur.execute("""
                        INSERT INTO chunks_3d (chunk_id, x, y, z)
                        VALUES (%s, %s, %s, %s)
                    """, (chunk_id, x, y, z))
                
                conn.commit()
                logger.info(f"✅ Successfully stored document {doc_id} with {len(chunks)} chunks")
            finally:
                if cur:
                    cur.close()
        
        return doc_id
    
    def process_urls(self, urls: List[str]) -> Dict[str, Any]:
        """Process a list of URLs."""
        logger.info(f"🚀 Starting to process {len(urls)} URLs")
        
        results = {
            'processed': [],
            'failed': [],
            'total_chunks': 0
        }
        
        all_embeddings = []
        all_chunks_data = []
        
        # First pass: scrape and chunk all URLs
        logger.info("📡 Phase 1: Scraping and chunking URLs...")
        for i, url in enumerate(urls, 1):
            logger.info(f"🌐 Processing URL {i}/{len(urls)}: {url}")
            scraped = self.scrape_url(url)
            
            if scraped['status'] == 'error':
                logger.error(f"❌ Failed to scrape {url}: {scraped.get('error', 'Unknown error')}")
                results['failed'].append({
                    'url': url,
                    'error': scraped.get('error', 'Unknown error')
                })
                continue
            
            logger.info(f"✂️ Chunking content from {url}")
            chunks = self.chunk_text(scraped['content'])
            if not chunks:
                logger.error(f"❌ No content to chunk from {url}")
                results['failed'].append({
                    'url': url,
                    'error': 'No content to chunk'
                })
                continue
            
            logger.info(f"✅ Created {len(chunks)} chunks from {url}")
            
            for j, chunk in enumerate(chunks):
                all_chunks_data.append({
                    'url': url,
                    'title': scraped['title'],
                    'chunk_index': j,
                    'chunk': chunk
                })
        
        if not all_chunks_data:
            logger.error("❌ No chunks were created from any URLs")
            return results
        
        logger.info(f"📊 Total chunks created: {len(all_chunks_data)}")
        
        # Get embeddings for all chunks
        logger.info("🧠 Phase 2: Getting embeddings for all chunks...")
        all_chunk_texts = [data['chunk'] for data in all_chunks_data]
        all_embeddings = self.get_embeddings(all_chunk_texts)
        
        # Reduce all embeddings to 3D at once for better clustering
        logger.info("🎯 Phase 3: Reducing embeddings to 3D coordinates...")
        coords_3d = self.reduce_to_3d(all_embeddings)
        
        # Group chunks by URL and store
        logger.info("📦 Phase 4: Grouping chunks by URL...")
        url_chunks = {}
        for i, data in enumerate(all_chunks_data):
            url = data['url']
            if url not in url_chunks:
                url_chunks[url] = {
                    'title': data['title'],
                    'chunks': [],
                    'embeddings': [],
                    'coords_3d': []
                }
            
            url_chunks[url]['chunks'].append(data['chunk'])
            url_chunks[url]['embeddings'].append(all_embeddings[i])
            url_chunks[url]['coords_3d'].append(coords_3d[i])
        
        # Store each URL's data
        logger.info("💾 Phase 5: Storing data in database...")
        for j, (url, data) in enumerate(url_chunks.items(), 1):
            logger.info(f"💾 Storing URL {j}/{len(url_chunks)}: {url}")
            try:
                doc_id = self.store_document_chunks(
                    url, data['title'], data['chunks'], 
                    data['embeddings'], data['coords_3d']
                )
                results['processed'].append({
                    'url': url,
                    'doc_id': doc_id,
                    'chunks_count': len(data['chunks'])
                })
                results['total_chunks'] += len(data['chunks'])
                logger.info(f"✅ Successfully stored {url} with {len(data['chunks'])} chunks")
            except Exception as e:
                logger.error(f"❌ Error storing data for {url}: {e}")
                results['failed'].append({
                    'url': url,
                    'error': str(e)
                })
        
        logger.info(f"🎉 Processing complete!")
        logger.info(f"✅ Successfully processed: {len(results['processed'])} URLs")
        logger.info(f"❌ Failed: {len(results['failed'])} URLs")
        logger.info(f"📊 Total chunks stored: {results['total_chunks']}")
        
        return results


def get_google_cloud_docs_urls() -> List[str]:
    """Get a comprehensive list of Google Cloud documentation URLs."""
    base_urls = [
        # Core documentation
        "https://cloud.google.com/docs",
        "https://cloud.google.com/architecture",
        
        # Key services
        "https://cloud.google.com/compute/docs",
        "https://cloud.google.com/storage/docs",
        "https://cloud.google.com/bigquery/docs",
        "https://cloud.google.com/kubernetes-engine/docs",
        "https://cloud.google.com/run/docs",
        "https://cloud.google.com/functions/docs",
        "https://cloud.google.com/sql/docs",
        "https://cloud.google.com/firestore/docs",
        "https://cloud.google.com/pubsub/docs",
        "https://cloud.google.com/dataflow/docs",
        "https://cloud.google.com/dataproc/docs",
        "https://cloud.google.com/ai-platform/docs",
        "https://cloud.google.com/vertex-ai/docs",
        "https://cloud.google.com/speech-to-text/docs",
        "https://cloud.google.com/text-to-speech/docs",
        "https://cloud.google.com/translate/docs",
        "https://cloud.google.com/vision/docs",
        "https://cloud.google.com/natural-language/docs",
        "https://cloud.google.com/monitoring/docs",
        "https://cloud.google.com/logging/docs",
        "https://cloud.google.com/iam/docs",
        "https://cloud.google.com/security/docs",
        "https://cloud.google.com/load-balancing/docs",
        "https://cloud.google.com/cdn/docs",
        "https://cloud.google.com/dns/docs",
        "https://cloud.google.com/vpc/docs",
        
        # Best practices and guides
        "https://cloud.google.com/docs/security",
        "https://cloud.google.com/docs/enterprise",
        "https://cloud.google.com/solutions",
        "https://cloud.google.com/architecture/cost-optimization"
    ]
    
    return base_urls


if __name__ == "__main__":
    processor = WebDocumentProcessor()
    
    # For testing, process a smaller subset
    test_urls = [
        "https://cloud.google.com/docs/overview",
        "https://cloud.google.com/compute/docs/instances/create-start-instance",
        "https://cloud.google.com/storage/docs/creating-buckets",
        "https://cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-service",
        "https://cloud.google.com/vertex-ai/docs/tutorials/text-classification-automl"
    ]
    
    results = processor.process_urls(test_urls)
    print(f"Processed: {len(results['processed'])} URLs")
    print(f"Failed: {len(results['failed'])} URLs") 
    print(f"Total chunks: {results['total_chunks']}") 
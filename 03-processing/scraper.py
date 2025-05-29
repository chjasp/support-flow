import logging
import os
import uuid
from contextlib import contextmanager
from typing import List, Dict, Any, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse
import time

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
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
USE_SELENIUM = os.environ.get("USE_SELENIUM", "true").lower() == "true"
GECKODRIVER_PATH = os.environ.get("GECKODRIVER_PATH")

# Constants for configuration
DEFAULT_RETRY_COUNT = 5
DEFAULT_RETRY_DELAY = 2
DEFAULT_REQUEST_TIMEOUT = 30
DEFAULT_CHUNK_MAX_TOKENS = 800
DEFAULT_CHUNK_OVERLAP = 200
SELENIUM_WAIT_TIMEOUT = 30
CONTENT_LOAD_DELAY = 2
URL_DELAY = 2
PREVIEW_LENGTH = 200

# Content selectors in order of preference
CONTENT_SELECTORS = [
    # Specific content areas
    ('main', {}),
    ('article', {}),
    ('[role="main"]', {}),
    ('.content', {}),
    ('.main-content', {}),
    ('.page-content', {}),
    ('.post-content', {}),
    ('.entry-content', {}),
    ('#content', {}),
    ('#main', {}),
    # Documentation-specific selectors
    ('.markdown-body', {}),
    ('.provider-docs-content', {}),
    ('.documentation', {}),
    ('.docs-content', {}),
    # Generic fallbacks
    ('div[class*="content"]', {}),
    ('div[class*="main"]', {}),
    ('body', {}),
]

# JavaScript detection indicators
JS_INDICATORS = [
    "please enable javascript",
    "javascript is required",
    "javascript must be enabled",
    "enable javascript",
    "javascript disabled",
    "requires javascript",
    "javascript is disabled"
]

# Selenium content indicators for dynamic content detection
SELENIUM_CONTENT_INDICATORS = [
    (By.TAG_NAME, 'main'),
    (By.TAG_NAME, 'article'),
    (By.CLASS_NAME, 'content'),
    (By.CLASS_NAME, 'main-content'),
    (By.CLASS_NAME, 'markdown-body'),
    (By.CLASS_NAME, 'provider-docs-content'),
]

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

    def __init__(self, use_selenium: bool = USE_SELENIUM):
        logger.info("🌐 Initializing web session...")
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'
        })
        logger.info("✅ Web session initialized")

        self.use_selenium = use_selenium
        self.driver = None
        self.selenium_available = True
        
        if self.use_selenium:
            self._initialize_selenium()

    def _initialize_selenium(self):
        """Initialize Selenium Firefox driver with proper configuration."""
        logger.info("🧭 Attempting to start Selenium Firefox driver...")
        
        # Firefox options configuration
        options = Options()
        options.add_argument("--headless")  # Run in headless mode
        options.add_argument("--width=1920")
        options.add_argument("--height=1080")
        
        # Additional options for better compatibility and stealth
        options.set_preference(
            "general.useragent.override",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/109.0"
        )
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        
        # Performance and stability options
        options.set_preference("browser.cache.disk.enable", False)
        options.set_preference("browser.cache.memory.enable", False)
        options.set_preference("browser.cache.offline.enable", False)
        options.set_preference("network.http.use-cache", False)
        
        try:
            if GECKODRIVER_PATH and os.path.exists(GECKODRIVER_PATH):
                logger.info(f"🔧 Using GeckoDriver from: {GECKODRIVER_PATH}")
                service = Service(executable_path=GECKODRIVER_PATH)
                self.driver = webdriver.Firefox(service=service, options=options)
            else:
                logger.info("🔧 Using GeckoDriver from PATH")
                self.driver = webdriver.Firefox(options=options)
            
            logger.info("✅ Selenium Firefox driver initialized successfully")
            
            # Test the driver with a simple page
            try:
                self.driver.get("data:text/html,<html><body>Test</body></html>")
                logger.info("✅ Selenium driver test successful")
            except Exception as test_e:
                logger.warning(f"⚠️ Selenium driver test failed: {test_e}")
                
        except Exception as e:
            logger.warning(f"⚠️ Could not initialize Selenium driver: {e}")
            logger.info("💡 Tip: Make sure Firefox and geckodriver are installed")
            logger.info("💡 You can install geckodriver with: brew install geckodriver (macOS)")
            self.driver = None
            self.use_selenium = False
            self.selenium_available = False

    def _find_content_element(self, soup) -> Tuple[Any, str]:
        """Find the main content element using the predefined selectors."""
        main_content = None
        used_selector = None
        
        for selector, attrs in CONTENT_SELECTORS:
            if selector.startswith('.'):
                # Class selector
                class_name = selector[1:]
                main_content = soup.find(attrs={'class': class_name}) if not attrs else soup.find(attrs=attrs)
            elif selector.startswith('#'):
                # ID selector
                id_name = selector[1:]
                main_content = soup.find(attrs={'id': id_name})
            elif selector.startswith('[') and selector.endswith(']'):
                # Attribute selector
                if 'role=' in selector:
                    main_content = soup.find(attrs={'role': 'main'})
                elif 'class*=' in selector:
                    # Partial class match
                    class_part = selector.split('class*="')[1].split('"')[0]
                    main_content = soup.find('div', class_=lambda x: x and class_part in ' '.join(x) if isinstance(x, list) else class_part in x if x else False)
            else:
                # Tag selector
                main_content = soup.find(selector, attrs) if attrs else soup.find(selector)
            
            if main_content:
                used_selector = selector
                logger.info(f"✅ Found content using selector: {selector}")
                break
        
        if not main_content:
            logger.warning("⚠️ No specific content area found, using body")
            main_content = soup.body or soup
            used_selector = "body (fallback)"
        
        return main_content, used_selector

    def _extract_clean_text(self, element) -> str:
        """Extract and clean text content from a BeautifulSoup element."""
        text_content = element.get_text(separator='\n', strip=True)
        lines = [line.strip() for line in text_content.split('\n') if line.strip()]
        return '\n'.join(lines)

    def _check_js_requirement(self, content: str) -> bool:
        """Check if the content indicates JavaScript is required."""
        content_lower = content.lower()
        needs_js = any(indicator in content_lower for indicator in JS_INDICATORS)
        return needs_js and len(content) < 200  # Short content that mentions JS

    def _log_content_preview(self, content: str) -> None:
        """Log a preview of the scraped content."""
        content_preview = content[:PREVIEW_LENGTH] + "..." if len(content) > PREVIEW_LENGTH else content
        logger.info(f"📄 Content preview: {content_preview}")

    def _retry_get(self, target: str, *, retries: int = DEFAULT_RETRY_COUNT, delay: int = DEFAULT_RETRY_DELAY) -> Optional[requests.Response]:
        """Helper to GET a URL with exponential backoff."""
        for attempt in range(1, retries + 1):
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'
                }
                resp = self.session.get(target, headers=headers, timeout=DEFAULT_REQUEST_TIMEOUT)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise requests.HTTPError(f"{resp.status_code} {resp.reason}")
                resp.raise_for_status()
                return resp
            except Exception as e:
                logger.warning(
                    f"⚠️ Request error for {target} (attempt {attempt}): {e}"
                )
                if attempt < retries:
                    logger.info(f"⏳ Retry after {delay}s")
                    time.sleep(delay)
                    delay *= 2
        return None

    def _scrape_with_requests(self, url: str) -> Dict[str, Any]:
        """Fallback method using requests + BeautifulSoup with smart content detection."""
        try:
            logger.info(f"📡 Trying requests method for {url}")
            response = self._retry_get(url)
            
            if response is None:
                raise ValueError("Failed to fetch page with requests")
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(["script", "style", "nav", "footer", "aside", "header"]):
                element.decompose()
            
            # Find content using helper method
            main_content, used_selector = self._find_content_element(soup)
            
            # Extract title
            title = soup.find('h1') or soup.find('title')
            title_text = title.get_text().strip() if title else urlparse(url).path.split('/')[-1]
            
            # Extract and clean text content
            clean_text = self._extract_clean_text(main_content)
            
            # Check if the content indicates JavaScript is required
            if self._check_js_requirement(clean_text):
                logger.warning(f"⚠️ Detected JavaScript-only content: {clean_text[:100]}...")
                raise ValueError("Page requires JavaScript - needs Selenium")
            
            logger.info(f"✅ Successfully scraped {len(clean_text)} characters using requests (selector: {used_selector})")
            self._log_content_preview(clean_text)
            
            return {
                'url': url,
                'title': title_text,
                'content': clean_text,
                'length': len(clean_text),
                'status': 'success',
                'method': 'requests',
                'selector_used': used_selector
            }
            
        except Exception as e:
            logger.error(f"❌ Requests method failed for {url}: {e}")
            return {
                'url': url,
                'title': url,
                'content': '',
                'length': 0,
                'status': 'error',
                'error': str(e),
                'method': 'requests'
            }

    def _parse_html(self, html: Union[bytes, str], url: str) -> Tuple[str, str]:
        """Parse HTML and extract title and cleaned text with improved content detection."""
        soup = BeautifulSoup(html, 'html.parser')

        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "footer", "aside", "header"]):
            element.decompose()

        # Find content using helper method
        main_content, used_selector = self._find_content_element(soup)

        # Extract title
        title = soup.find('h1') or soup.find('title')
        title_text = title.get_text().strip() if title else urlparse(url).path.split('/')[-1]

        # Extract and clean text content
        clean_text = self._extract_clean_text(main_content)

        return title_text, clean_text

    def _scrape_with_selenium(self, url: str) -> Dict[str, Any]:
        """Scrape a URL using Selenium and BeautifulSoup with improved waiting and content detection."""
        assert self.driver is not None
        
        try:
            logger.info(f"🧭 Loading page with Selenium: {url}")
            self.driver.get(url)
            
            # Wait for body to be present
            wait = WebDriverWait(self.driver, SELENIUM_WAIT_TIMEOUT)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, 'body')))
            
            # Additional wait for dynamic content to load
            time.sleep(CONTENT_LOAD_DELAY)
            
            # Try to wait for common content indicators
            content_loaded = False
            for by, value in SELENIUM_CONTENT_INDICATORS:
                try:
                    wait_short = WebDriverWait(self.driver, 5)
                    wait_short.until(EC.presence_of_element_located((by, value)))
                    logger.info(f"✅ Content indicator found: {by}={value}")
                    content_loaded = True
                    break
                except:
                    continue
            
            if not content_loaded:
                logger.info("⏳ No specific content indicators found, proceeding with general wait")
            
            # Get page source and parse
            page_html = self.driver.page_source
            title_text, clean_text = self._parse_html(page_html, url)
            
            logger.info(f"✅ Successfully scraped {len(clean_text)} characters using Selenium")
            self._log_content_preview(clean_text)
            
            return {
                'url': url,
                'title': title_text,
                'content': clean_text,
                'length': len(clean_text),
                'status': 'success',
                'method': 'selenium'
            }
            
        except Exception as e:
            logger.error(f"❌ Selenium method failed for {url}: {e}")
            raise
    
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
        """Scrape content from a URL using Selenium first, then requests fallback."""
        logger.info(f"🌐 Starting to scrape URL: {url}")

        # Try Selenium first if available
        if self.use_selenium and self.driver:
            try:
                result = self._scrape_with_selenium(url)
                return result
            except Exception as e:
                logger.warning(f"⚠️ Selenium scraping failed for {url}: {e}")
                logger.info("🔄 Falling back to requests method...")

        # Fallback to requests method
        try:
            result = self._scrape_with_requests(url)
            if result['status'] == 'success':
                return result
            else:
                logger.error(f"❌ Requests fallback also failed for {url}: {result.get('error', 'Unknown error')}")
                return result
        except ValueError as e:
            if "JavaScript" in str(e) and self.selenium_available and self.driver:
                logger.info("🔄 JavaScript detected, retrying with Selenium...")
                try:
                    result = self._scrape_with_selenium(url)
                    return result
                except Exception as selenium_e:
                    logger.error(f"❌ Selenium retry also failed for {url}: {selenium_e}")
                    return {
                        'url': url,
                        'title': url,
                        'content': '',
                        'length': 0,
                        'status': 'error',
                        'error': f"JavaScript required but Selenium failed: {selenium_e}",
                        'method': 'selenium_retry_failed'
                    }
            else:
                logger.error(f"❌ JavaScript required but Selenium not available for {url}: {e}")
                return {
                    'url': url,
                    'title': url,
                    'content': '',
                    'length': 0,
                    'status': 'error',
                    'error': str(e),
                    'method': 'js_required_no_selenium'
                }
        except Exception as e:
            logger.error(f"❌ All scraping methods failed for {url}: {e}")
            return {
                'url': url,
                'title': url,
                'content': '',
                'length': 0,
                'status': 'error',
                'error': str(e),
                'method': 'all_failed'
            }
    
    def chunk_text(self, text: str, max_tokens: int = DEFAULT_CHUNK_MAX_TOKENS, overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[str]:
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
        max_tokens = 18000  # keep some headroom below API limit
        batch: List[str] = []
        batch_tokens = 0
        batch_num = 1

        def _process_current(batch_num: int, batch: List[str]):
            nonlocal all_embeddings
            if not batch:
                return
            token_count = sum(len(tokenizer.encode(t)) for t in batch)
            logger.info(f"🔄 Processing batch {batch_num} ({len(batch)} texts, {token_count} tokens)")
            try:
                embeddings = embedding_model.get_embeddings(batch)
                all_embeddings.extend([emb.values for emb in embeddings])
                logger.info(f"✅ Successfully processed batch {batch_num}")
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"❌ Error getting embeddings for batch {batch_num}: {e}")
                zero_embeddings = [[0.0] * 768] * len(batch)
                all_embeddings.extend(zero_embeddings)
                logger.warning(f"⚠️ Using zero embeddings for failed batch {batch_num}")

        for text in texts:
            tokens = len(tokenizer.encode(text))
            if batch_tokens + tokens > max_tokens and batch:
                _process_current(batch_num, batch)
                batch_num += 1
                batch = []
                batch_tokens = 0
            batch.append(text)
            batch_tokens += tokens

        _process_current(batch_num, batch)
        
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
    
    def _process_single_url(self, url: str, url_index: int, total_urls: int) -> Tuple[Optional[Dict], List[Dict]]:
        """Process a single URL and return chunks data or None if failed."""
        logger.info(f"🌐 Processing URL {url_index}/{total_urls}: {url}")
        scraped = self.scrape_url(url)
        
        if scraped['status'] == 'error':
            logger.error(f"❌ Failed to scrape {url}: {scraped.get('error', 'Unknown error')}")
            return None, [{
                'url': url,
                'error': scraped.get('error', 'Unknown error')
            }]
        
        logger.info(f"✂️ Chunking content from {url}")
        chunks = self.chunk_text(scraped['content'])
        if not chunks:
            logger.error(f"❌ No content to chunk from {url}")
            return None, [{
                'url': url,
                'error': 'No content to chunk'
            }]
        
        logger.info(f"✅ Created {len(chunks)} chunks from {url}")
        
        chunks_data = []
        for j, chunk in enumerate(chunks):
            chunks_data.append({
                'url': url,
                'title': scraped['title'],
                'chunk_index': j,
                'chunk': chunk
            })
        
        return scraped, chunks_data
    
    def _add_url_delay(self, url_index: int, total_urls: int) -> None:
        """Add a polite delay between URL requests."""
        if url_index < total_urls:
            logger.info(f"⏳ Waiting {URL_DELAY} seconds before next URL...")
            time.sleep(URL_DELAY)
    
    def _group_chunks_by_url(self, all_chunks_data: List[Dict], all_embeddings: List[List[float]], 
                           coords_3d: List[Tuple[float, float, float]]) -> Dict[str, Dict]:
        """Group chunks, embeddings, and coordinates by URL."""
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
        
        return url_chunks
    
    def _store_url_chunks(self, url_chunks: Dict[str, Dict], results: Dict[str, Any]) -> None:
        """Store each URL's chunks in the database."""
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
    
    def process_urls(self, urls: List[str]) -> Dict[str, Any]:
        """Process a list of URLs."""
        logger.info(f"🚀 Starting to process {len(urls)} URLs")
        
        results = {
            'processed': [],
            'failed': [],
            'total_chunks': 0
        }
        
        all_chunks_data = []
        
        # First pass: scrape and chunk all URLs
        logger.info("📡 Phase 1: Scraping and chunking URLs...")
        for i, url in enumerate(urls, 1):
            scraped, chunks_data = self._process_single_url(url, i, len(urls))
            
            if scraped is None:
                # Failed to process URL
                results['failed'].extend(chunks_data)  # chunks_data contains error info
                self._add_url_delay(i, len(urls))
                continue
            
            all_chunks_data.extend(chunks_data)
            self._add_url_delay(i, len(urls))
        
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
        url_chunks = self._group_chunks_by_url(all_chunks_data, all_embeddings, coords_3d)
        
        # Store each URL's data
        self._store_url_chunks(url_chunks, results)
        
        logger.info(f"🎉 Processing complete!")
        logger.info(f"✅ Successfully processed: {len(results['processed'])} URLs")
        logger.info(f"❌ Failed: {len(results['failed'])} URLs")
        logger.info(f"📊 Total chunks stored: {results['total_chunks']}")

        return results

    def close(self) -> None:
        """Close any open resources like the Selenium driver."""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("🛑 Selenium driver closed successfully")
            except Exception as e:
                logger.warning(f"⚠️ Error closing Selenium driver: {e}")
            finally:
                self.driver = None
                self.selenium_available = False
        elif not self.selenium_available:
            logger.info("🛑 No Selenium driver to close (was not available)")
        else:
            logger.info("🛑 No Selenium driver to close")


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
    processor.close()

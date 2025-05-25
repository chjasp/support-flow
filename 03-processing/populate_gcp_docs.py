#!/usr/bin/env python3
"""
One-time script to populate the database with Google Cloud documentation.
This script scrapes, processes, and stores Google Cloud docs with 3D coordinates.
"""

import os
import sys
import logging
from typing import List
from scraper import WebDocumentProcessor, get_google_cloud_docs_urls

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)
logger = logging.getLogger("gcp_docs_populator")

def get_comprehensive_gcp_urls() -> List[str]:
    """Get a comprehensive list of Google Cloud documentation URLs."""
    urls = [
        # Core GCP Overview
        "https://cloud.google.com/docs/overview",
        "https://cloud.google.com/docs/get-started",
        
        # Compute Services
        "https://cloud.google.com/compute/docs/instances/create-start-instance",
        "https://cloud.google.com/compute/docs/machine-types",
        "https://cloud.google.com/compute/docs/disks",
        "https://cloud.google.com/kubernetes-engine/docs/quickstart",
        "https://cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-service",
        "https://cloud.google.com/functions/docs/quickstart-python",
        "https://cloud.google.com/appengine/docs/standard/python3/quickstart",
        
        # Storage Services
        "https://cloud.google.com/storage/docs/creating-buckets",
        "https://cloud.google.com/storage/docs/uploading-objects",
        "https://cloud.google.com/storage/docs/access-control",
        "https://cloud.google.com/filestore/docs/quickstart-console",
        
        # Database Services
        "https://cloud.google.com/sql/docs/mysql/quickstart",
        "https://cloud.google.com/sql/docs/postgres/quickstart",
        "https://cloud.google.com/firestore/docs/quickstart-servers",
        "https://cloud.google.com/bigtable/docs/quickstart-console",
        "https://cloud.google.com/spanner/docs/quickstart-console",
        
        # Data Analytics
        "https://cloud.google.com/bigquery/docs/quickstarts/load-data-console",
        "https://cloud.google.com/bigquery/docs/datasets",
        "https://cloud.google.com/dataflow/docs/quickstarts/quickstart-python",
        "https://cloud.google.com/dataproc/docs/quickstarts/quickstart-console",
        "https://cloud.google.com/pubsub/docs/quickstart-console",
        
        # AI/ML Services
        "https://cloud.google.com/vertex-ai/docs/tutorials/text-classification-automl",
        "https://cloud.google.com/vertex-ai/docs/start/introduction-unified-platform",
        "https://cloud.google.com/speech-to-text/docs/quickstart-console",
        "https://cloud.google.com/text-to-speech/docs/quickstart-console",
        "https://cloud.google.com/translate/docs/quickstart",
        "https://cloud.google.com/vision/docs/quickstart",
        "https://cloud.google.com/natural-language/docs/quickstart",
        
        # Networking
        "https://cloud.google.com/vpc/docs/create-modify-vpc-networks",
        "https://cloud.google.com/load-balancing/docs/https",
        "https://cloud.google.com/cdn/docs/quickstart",
        "https://cloud.google.com/dns/docs/quickstart",
        
        # Security & Identity
        "https://cloud.google.com/iam/docs/understanding-roles",
        "https://cloud.google.com/iam/docs/creating-managing-service-accounts",
        "https://cloud.google.com/security/security-design",
        "https://cloud.google.com/kms/docs/quickstart",
        
        # Monitoring & Operations
        "https://cloud.google.com/monitoring/docs/monitoring-overview",
        "https://cloud.google.com/logging/docs/quickstart-console",
        "https://cloud.google.com/trace/docs/quickstart",
        "https://cloud.google.com/debugger/docs/quickstart",
        
        # Best Practices & Architecture
        "https://cloud.google.com/architecture/framework",
        "https://cloud.google.com/docs/security/best-practices",
        "https://cloud.google.com/architecture/cost-optimization",
        "https://cloud.google.com/solutions/migration-center",
        
        # Developer Tools
        "https://cloud.google.com/build/docs/quickstart-build",
        "https://cloud.google.com/source-repositories/docs/quickstart",
        "https://cloud.google.com/deployment-manager/docs/quickstart",
        
        # Additional Important Pages
        "https://cloud.google.com/docs/enterprise",
        "https://cloud.google.com/solutions",
        "https://cloud.google.com/pricing",
        "https://cloud.google.com/support"
    ]
    
    return urls

def main():
    """Main function to populate the database with GCP documentation."""
    logger.info("Starting Google Cloud documentation population...")
    
    # Check environment variables
    required_env_vars = [
        "GOOGLE_CLOUD_PROJECT",
        "CLOUD_SQL_INSTANCE", 
        "CLOUD_SQL_USER",
        "CLOUD_SQL_PASSWORD",
        "CLOUD_SQL_DB",
        "EMBED_MODEL"
    ]
    
    missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
    if missing_vars:
        logger.error(f"Missing required environment variables: {missing_vars}")
        sys.exit(1)
    
    # Initialize processor
    processor = WebDocumentProcessor()
    
    # Get URLs to process
    urls = get_comprehensive_gcp_urls()
    logger.info(f"Processing {len(urls)} Google Cloud documentation URLs")
    
    # Process in batches to avoid overwhelming the system
    batch_size = 5
    total_processed = 0
    total_failed = 0
    total_chunks = 0
    
    for i in range(0, len(urls), batch_size):
        batch = urls[i:i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (len(urls) + batch_size - 1) // batch_size
        
        logger.info(f"Processing batch {batch_num}/{total_batches} ({len(batch)} URLs)")
        
        try:
            result = processor.process_urls(batch)
            
            batch_processed = len(result['processed'])
            batch_failed = len(result['failed'])
            batch_chunks = result['total_chunks']
            
            total_processed += batch_processed
            total_failed += batch_failed
            total_chunks += batch_chunks
            
            logger.info(f"Batch {batch_num} completed: {batch_processed} processed, {batch_failed} failed, {batch_chunks} chunks")
            
            # Log any failures
            for failure in result['failed']:
                logger.warning(f"Failed to process {failure['url']}: {failure['error']}")
                
        except Exception as e:
            logger.error(f"Error processing batch {batch_num}: {e}")
            total_failed += len(batch)
    
    # Final summary
    logger.info("=" * 60)
    logger.info("FINAL SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total URLs processed: {total_processed}")
    logger.info(f"Total URLs failed: {total_failed}")
    logger.info(f"Total chunks created: {total_chunks}")
    logger.info(f"Success rate: {(total_processed / len(urls)) * 100:.1f}%")
    
    if total_processed > 0:
        logger.info("✅ Google Cloud documentation successfully populated!")
        logger.info("You can now view the 3D visualization in your frontend.")
    else:
        logger.error("❌ No documents were successfully processed.")
        sys.exit(1)

if __name__ == "__main__":
    main() 
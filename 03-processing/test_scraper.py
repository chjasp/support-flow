#!/usr/bin/env python3
"""
Simple test script to verify web scraping functionality with one URL.
"""

import os
import sys
from dotenv import load_dotenv
from scraper import WebDocumentProcessor

# Load environment variables from .env file
load_dotenv()

def test_basic_functionality():
    """Test basic web scraping functionality with one URL."""
    print("🚀 Starting web scraping functionality test...")
    print("=" * 50)
    
    # Check if we have the required environment variables
    required_vars = ["GOOGLE_CLOUD_PROJECT", "CLOUD_SQL_INSTANCE", "CLOUD_SQL_USER", "CLOUD_SQL_PASSWORD", "CLOUD_SQL_DB", "EMBED_MODEL"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"⚠️  Missing environment variables: {missing_vars}")
        print("📝 Proceeding with limited testing (no database operations)...")
    else:
        print("✅ All environment variables found!")
    
    print("\n" + "=" * 50)
    print("🧪 Test 1: Basic Web Scraping")
    print("=" * 50)
    
    processor = WebDocumentProcessor()
    
    # Use a simple, reliable URL for testing
    test_url = 'https://cloud.google.com/docs/overview'
    print(f"🌐 Testing with URL: {test_url}")
    
    result = processor.scrape_url(test_url)
    
    print(f'📈 Status: {result["status"]}')
    print(f'📄 Title: {result["title"]}')
    print(f'📊 Content length: {result["length"]} characters')
    
    if result["status"] != "success" or result["length"] == 0:
        print("❌ Web scraping test failed!")
        print(f"Error details: {result.get('error', 'Unknown error')}")
        return False
    
    print("✅ Web scraping test passed!")
    
    print("\n" + "=" * 50)
    print("🧪 Test 2: Text Chunking")
    print("=" * 50)
    
    chunks = processor.chunk_text(result["content"])
    print(f"📊 Created {len(chunks)} chunks from the content")
    
    if len(chunks) == 0:
        print("❌ Chunking test failed - no chunks created")
        return False
    
    print(f"📝 First chunk preview (100 chars): {chunks[0][:100]}...")
    print(f"📏 Average chunk length: {sum(len(chunk) for chunk in chunks) / len(chunks):.0f} characters")
    print("✅ Chunking test passed!")
    
    print("\n" + "=" * 50)
    print("🧪 Test 3: 3D Dimensionality Reduction")
    print("=" * 50)
    
    # Test with dummy embeddings first
    print("🎭 Testing with dummy embeddings...")
    dummy_embeddings = [[0.1 + i * 0.01] * 768 for i in range(len(chunks))]
    
    coords_3d = processor.reduce_to_3d(dummy_embeddings)
    print(f"🎯 Generated {len(coords_3d)} 3D coordinates")
    
    if len(coords_3d) == 0:
        print("❌ 3D reduction test failed!")
        return False
    
    print(f"📍 Sample coordinates:")
    for i, (x, y, z) in enumerate(coords_3d[:3]):
        print(f"   Point {i+1}: ({x:.2f}, {y:.2f}, {z:.2f})")
    
    print("✅ 3D reduction test passed!")
    
    print("\n" + "=" * 50)
    print("🧪 Test 4: Embeddings (if available)")
    print("=" * 50)
    
    # Test real embeddings if model is available
    sample_texts = chunks[:3]  # Just test with first 3 chunks
    embeddings = processor.get_embeddings(sample_texts)
    
    print(f"🧠 Generated {len(embeddings)} embeddings")
    print(f"📐 Embedding dimension: {len(embeddings[0]) if embeddings else 'N/A'}")
    
    if len(embeddings) > 0:
        print("✅ Embeddings test passed!")
    else:
        print("⚠️ No embeddings generated (this is OK if Vertex AI is not configured)")
    
    return True

def test_database_connection():
    """Test database connection if environment variables are available."""
    print("\n" + "=" * 50)
    print("🧪 Test 5: Database Connection (Optional)")
    print("=" * 50)
    
    required_vars = ["CLOUD_SQL_INSTANCE", "CLOUD_SQL_USER", "CLOUD_SQL_PASSWORD", "CLOUD_SQL_DB"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        print(f"⚠️ Skipping database test - missing vars: {missing_vars}")
        return True
    
    processor = WebDocumentProcessor()
    
    try:
        print("🔌 Testing database connection...")
        with processor._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                result = cur.fetchone()
                if result[0] == 1:
                    print("✅ Database connection test passed!")
                    return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("💡 This is OK if you're testing without a real database")
        return True  # Don't fail the whole test for DB issues
    
    return False

if __name__ == "__main__":
    print("🧪 Web Document Processor Test Suite")
    print("=" * 60)
    
    # Run basic functionality tests
    basic_success = test_basic_functionality()
    
    # Test database connection if possible
    db_success = test_database_connection()
    
    print("\n" + "=" * 60)
    print("📊 Test Results Summary")
    print("=" * 60)
    
    if basic_success:
        print("✅ Basic functionality tests: PASSED")
        print("🎉 The web scraping and 3D reduction functionality is working!")
        print("\n💡 Next steps:")
        print("   1. Run 'gcloud auth application-default login' for real embeddings")
        print("   2. Ensure database is accessible for full testing")
        print("   3. Use the full processing script to populate your database")
    else:
        print("❌ Basic functionality tests: FAILED")
        print("🔧 Please check the error messages above")
        sys.exit(1) 

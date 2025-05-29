import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import os

# Chrome options with maximum compatibility for macOS Sequoia
chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--disable-web-security")
chrome_options.add_argument("--disable-features=VizDisplayCompositor")
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-plugins")
chrome_options.add_argument("--disable-images")
chrome_options.add_argument("--remote-debugging-port=9222")
chrome_options.add_argument("--single-process")
chrome_options.add_argument("--disable-background-timer-throttling")
chrome_options.add_argument("--disable-backgrounding-occluded-windows")
chrome_options.add_argument("--disable-renderer-backgrounding")
chrome_options.add_argument("--disable-background-networking")
chrome_options.add_argument("--disable-ipc-flooding-protection")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36")

# Test URLs
URLS_TO_SCRAPE = [
    "https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/access_context_manager_access_level_condition.html"
]

CONTENT_SELECTOR = (By.CLASS_NAME, "provider-docs-content")

print("Attempting to initialize Chrome with maximum compatibility options...")

try:
    driver = webdriver.Chrome(options=chrome_options)
    print("✅ Chrome WebDriver initialized successfully!")
    
    url = URLS_TO_SCRAPE[0]
    print(f"Testing with: {url}")
    
    driver.get(url)
    wait = WebDriverWait(driver, 30)
    content_element = wait.until(EC.presence_of_element_located(CONTENT_SELECTOR))
    
    page_html = driver.page_source
    soup = BeautifulSoup(page_html, 'html.parser')
    main_content_div = soup.find('article', class_='provider-docs-content')
    
    if main_content_div:
        content_text = main_content_div.get_text(separator='\n', strip=True)
        print(f"✅ Successfully scraped content: {len(content_text)} characters")
        print(f"Preview: {content_text[:200]}...")
    else:
        print("❌ Content element not found")
        
    driver.quit()
    
except Exception as e:
    print(f"❌ Chrome still fails with error: {e}")
 
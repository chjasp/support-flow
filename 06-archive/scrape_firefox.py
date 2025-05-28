import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import os
import requests
from urllib.parse import urljoin

# --- Configuration ---
# Option 1: GeckoDriver executable in PATH
# If geckodriver is in your PATH, you might not need to specify executable_path.
# Option 2: Specify the path to your GeckoDriver executable
# Ensure this path is correct for your system.
GECKODRIVER_PATH = None  # Set this if geckodriver is not in your PATH

# Scraping configuration - customize for different sites
SCRAPING_CONFIG = {
    "terraform": {
        "urls": [
            "https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/access_context_manager_access_level_condition.html",
            "https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/access_context_manager_access_levels.html",
            "https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/access_context_manager_access_policy.html",
        ],
        "selenium_selector": (By.CLASS_NAME, "provider-docs-content"),
        "bs4_selector": {"tag": "article", "attrs": {"class": "provider-docs-content"}},
        "fallback_selectors": [
            {"tag": "main", "attrs": {}},
            {"tag": "div", "attrs": {"class": "content"}},
            {"tag": "article", "attrs": {}}
        ]
    },
    "github": {
        "urls": [
            "https://docs.github.com/en/actions/learn-github-actions/understanding-github-actions"
        ],
        "selenium_selector": (By.CLASS_NAME, "markdown-body"),
        "bs4_selector": {"tag": "div", "attrs": {"class": "markdown-body"}},
        "fallback_selectors": [
            {"tag": "main", "attrs": {}},
            {"tag": "article", "attrs": {}},
            {"tag": "div", "attrs": {"id": "readme"}}
        ]
    },
    "generic": {
        "urls": [],  # Add your URLs here
        "selenium_selector": (By.TAG_NAME, "main"),
        "bs4_selector": {"tag": "main", "attrs": {}},
        "fallback_selectors": [
            {"tag": "article", "attrs": {}},
            {"tag": "div", "attrs": {"class": "content"}},
            {"tag": "div", "attrs": {"class": "main"}},
            {"tag": "body", "attrs": {}}
        ]
    }
}

# Choose which configuration to use
ACTIVE_CONFIG = "terraform"  # Change to "github", "generic", or add your own

# Example: Add custom site configurations
# add_site_config("stackoverflow", 
#                 ["https://stackoverflow.com/questions/123456"], 
#                 ".js-post-body")
# add_site_config("wikipedia", 
#                 ["https://en.wikipedia.org/wiki/Python"], 
#                 "#mw-content-text")

# Extract current configuration
current_config = SCRAPING_CONFIG[ACTIVE_CONFIG]
URLS_TO_SCRAPE = current_config["urls"]
CONTENT_SELECTOR = current_config["selenium_selector"]

def add_site_config(name, urls, primary_selector, fallback_selectors=None):
    """Helper function to easily add new site configurations"""
    if fallback_selectors is None:
        fallback_selectors = [
            {"tag": "main", "attrs": {}},
            {"tag": "article", "attrs": {}},
            {"tag": "div", "attrs": {"class": "content"}},
            {"tag": "body", "attrs": {}}
        ]
    
    # Convert CSS selector string to Selenium selector tuple
    if primary_selector.startswith('.'):
        selenium_sel = (By.CLASS_NAME, primary_selector[1:])
        bs4_sel = {"tag": "*", "attrs": {"class": primary_selector[1:]}}
    elif primary_selector.startswith('#'):
        selenium_sel = (By.ID, primary_selector[1:])
        bs4_sel = {"tag": "*", "attrs": {"id": primary_selector[1:]}}
    else:
        selenium_sel = (By.TAG_NAME, primary_selector)
        bs4_sel = {"tag": primary_selector, "attrs": {}}
    
    SCRAPING_CONFIG[name] = {
        "urls": urls,
        "selenium_selector": selenium_sel,
        "bs4_selector": bs4_sel,
        "fallback_selectors": fallback_selectors
    }

def scrape_with_requests(url, config):
    """Fallback method using requests + BeautifulSoup with configurable selectors"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Try primary selector first
        bs4_sel = config["bs4_selector"]
        main_content_div = soup.find(bs4_sel["tag"], bs4_sel["attrs"])
        
        # If primary fails, try fallback selectors
        if not main_content_div:
            for fallback in config["fallback_selectors"]:
                main_content_div = soup.find(fallback["tag"], fallback["attrs"])
                if main_content_div:
                    print(f"Found content using fallback selector: {fallback}")
                    break
        
        if main_content_div:
            content_text = main_content_div.get_text(separator='\n', strip=True)
            return content_text
        else:
            return "Error: Content element not found with requests method."
    except Exception as e:
        return f"Error with requests method: {e}"

# --- Firefox WebDriver Setup ---
firefox_options = Options()
firefox_options.add_argument("--headless")  # Run in headless mode (no browser window)
firefox_options.add_argument("--width=1920")
firefox_options.add_argument("--height=1080")

# Additional options for better compatibility
firefox_options.set_preference("general.useragent.override", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/109.0")
firefox_options.set_preference("dom.webdriver.enabled", False)
firefox_options.set_preference("useAutomationExtension", False)

driver = None
selenium_available = True

try:
    if GECKODRIVER_PATH and os.path.exists(GECKODRIVER_PATH):
        service = Service(executable_path=GECKODRIVER_PATH)
        driver = webdriver.Firefox(service=service, options=firefox_options)
    else:
        # Try to use GeckoDriver from PATH
        driver = webdriver.Firefox(options=firefox_options)
    print("Firefox WebDriver initialized successfully.")
except Exception as e:
    print(f"Error initializing Firefox WebDriver: {e}")
    print("Will use requests-only method as fallback.")
    selenium_available = False

# --- Main Scraping Logic ---
scraped_data = {}

try:
    for i, url in enumerate(URLS_TO_SCRAPE):
        print(f"Scraping URL {i+1}/{len(URLS_TO_SCRAPE)}: {url}")
        
        if not selenium_available:
            # Use requests method only
            content = scrape_with_requests(url, current_config)
            scraped_data[url] = content
            if not content.startswith("Error"):
                print(f"Successfully scraped with requests: {url}")
            else:
                print(f"Failed to scrape {url}: {content}")
            time.sleep(1)
            continue
            
        try:
            driver.get(url)

            # Wait for the main content element to be loaded
            wait = WebDriverWait(driver, 30)  # Increased timeout
            content_element = wait.until(EC.presence_of_element_located(CONTENT_SELECTOR))

            # Get the HTML of the loaded content element
            page_html = driver.page_source

            # Parse the HTML with BeautifulSoup
            soup = BeautifulSoup(page_html, 'html.parser')

            # Find the specific content using configurable selectors
            bs4_sel = current_config["bs4_selector"]
            main_content_div = soup.find(bs4_sel["tag"], bs4_sel["attrs"])
            
            # If primary fails, try fallback selectors
            if not main_content_div:
                for fallback in current_config["fallback_selectors"]:
                    main_content_div = soup.find(fallback["tag"], fallback["attrs"])
                    if main_content_div:
                        print(f"Found content using fallback selector: {fallback}")
                        break

            if main_content_div:
                # Extract text
                content_text = main_content_div.get_text(separator='\n', strip=True)
                scraped_data[url] = content_text
                print(f"Successfully scraped with Firefox: {url}")
                print(f"Content preview: {content_text[:200]}...")

            else:
                print(f"Could not find the content element for URL: {url} after page load.")
                scraped_data[url] = "Error: Content element not found."

        except Exception as e:
            print(f"Error scraping {url} with Firefox: {e}")
            print(f"Trying fallback method with requests...")
            
            # Try fallback method
            fallback_content = scrape_with_requests(url, current_config)
            if not fallback_content.startswith("Error"):
                scraped_data[url] = fallback_content
                print(f"Successfully scraped with fallback method: {url}")
            else:
                scraped_data[url] = f"Firefox Error: {e}. Fallback Error: {fallback_content}"
                print(f"Both methods failed for {url}")
        
        # Add a small delay to be polite to the server
        time.sleep(2)  # Increased delay for stability

finally:
    # Important to close the browser session
    if selenium_available and driver is not None:
        driver.quit()
        print("Firefox browser closed.")
    elif not selenium_available:
        print("No browser session to close (used requests-only method).")

# --- Process scraped data ---
print("\n\n--- Scraping Summary ---")
successful_scrapes = 0
for url, content in scraped_data.items():
    if not content.startswith("Error:") and not "Error:" in content:
        successful_scrapes += 1
        print(f"\n✅ SUCCESS: {url}")
        print(f"Content (first 200 chars): {content[:200].strip()}...")
    else:
        print(f"\n❌ FAILED: {url}")
        print(f"Error: {content}")

print(f"\n📊 SUMMARY: Successfully scraped {successful_scrapes}/{len(URLS_TO_SCRAPE)} URLs.")

# Save successful scrapes to files
if successful_scrapes > 0:
    print("\n💾 Saving successful scrapes to files...")
    for url, content in scraped_data.items():
        if not content.startswith("Error:") and not "Error:" in content:
            # Extract filename from URL
            filename = url.split("/")[-1].replace(".html", ".txt")
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"URL: {url}\n\n")
                f.write(content)
            print(f"Saved: {filename}") 
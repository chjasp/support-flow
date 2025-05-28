import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import os
import requests
from urllib.parse import urljoin

# --- Configuration ---
# Option 1: ChromeDriver executable in PATH
# If chromedriver is in your PATH, you might not need to specify executable_path.
# Option 2: Specify the path to your ChromeDriver executable
# Ensure this path is correct for your system.
# Example: CHROMEDRIVER_PATH = '/path/to/your/chromedriver'
CHROMEDRIVER_PATH = None  # Set this if chromedriver is not in your PATH

# List of URLs to scrape
URLS_TO_SCRAPE = [
    "https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/access_context_manager_access_level_condition.html",
    "https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/access_context_manager_access_levels.html",
    "https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/access_context_manager_access_policy.html",
    "https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/access_context_manager_access_policy_iam_binding.html",
    "https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/access_context_manager_access_policy_iam_member.html"
]

# CSS Selector for the main content area.
# From inspection, the documentation is within an article with class "provider-docs-content"
CONTENT_SELECTOR = (By.CLASS_NAME, "provider-docs-content")

def scrape_with_requests(url):
    """Fallback method using requests + BeautifulSoup"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        main_content_div = soup.find('article', class_='provider-docs-content')
        
        if main_content_div:
            content_text = main_content_div.get_text(separator='\n', strip=True)
            return content_text
        else:
            return "Error: Content element not found with requests method."
    except Exception as e:
        return f"Error with requests method: {e}"

# --- Selenium WebDriver Setup ---
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in headless mode (no browser window)
chrome_options.add_argument("--disable-gpu") # Optional, recommended for headless
chrome_options.add_argument("--window-size=1920,1080") # Optional, can help with some layouts
chrome_options.add_argument("--log-level=3") # Suppress unnecessary console logs from Chrome/ChromeDriver
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36") # Use a common user agent

# Additional options to fix macOS compatibility issues
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--disable-extensions")
chrome_options.add_argument("--disable-plugins")
chrome_options.add_argument("--disable-images")
chrome_options.add_argument("--disable-web-security")
chrome_options.add_argument("--disable-features=VizDisplayCompositor")
chrome_options.add_argument("--remote-debugging-port=9222")
chrome_options.add_argument("--single-process")  # This can help with crashes on some systems

driver = None
selenium_available = True

try:
    if CHROMEDRIVER_PATH and os.path.exists(CHROMEDRIVER_PATH):
        service = Service(executable_path=CHROMEDRIVER_PATH)
        driver = webdriver.Chrome(service=service, options=chrome_options)
    else:
        # Try to use ChromeDriver from PATH
        driver = webdriver.Chrome(options=chrome_options)
    print("Selenium WebDriver initialized successfully.")
except Exception as e:
    print(f"Error initializing ChromeDriver: {e}")
    print("Will use requests-only method as fallback.")
    selenium_available = False

# --- Main Scraping Logic ---
scraped_data = {}

try:
    for i, url in enumerate(URLS_TO_SCRAPE):
        print(f"Scraping URL {i+1}/{len(URLS_TO_SCRAPE)}: {url}")
        
        if not selenium_available:
            # Use requests method only
            content = scrape_with_requests(url)
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
            # Adjust timeout as needed, 10-20 seconds is usually enough
            wait = WebDriverWait(driver, 20) # Increased timeout for potentially slower loads
            content_element = wait.until(EC.presence_of_element_located(CONTENT_SELECTOR))

            # Get the HTML of the loaded content element
            # Sometimes it's better to get the outerHTML of the element
            # or just the page_source if the selector is specific enough.
            page_html = driver.page_source

            # Parse the HTML with BeautifulSoup
            soup = BeautifulSoup(page_html, 'html.parser')

            # Find the specific content article again using BeautifulSoup (optional, but good practice)
            # This ensures we are working with the element that Selenium waited for.
            main_content_div = soup.find('article', class_='provider-docs-content')

            if main_content_div:
                # Extract text. You might want to refine this to get structured data.
                # .get_text(separator=' ', strip=True) can be useful for cleaner text.
                content_text = main_content_div.get_text(separator='\n', strip=True)
                scraped_data[url] = content_text
                print(f"Successfully scraped: {url}")
                # print("\n--- Content Start ---\n")
                # print(content_text[:500] + "..." if len(content_text) > 500 else content_text) # Print a snippet
                # print("\n--- Content End ---\n")

                # --- Optional: Save to file ---
                # filename = url.split("/")[-1].replace(".html", ".txt")
                # with open(filename, "w", encoding="utf-8") as f:
                #    f.write(f"URL: {url}\n\n")
                #    f.write(content_text)
                # print(f"Saved content to {filename}")
                # ------------------------------

            else:
                print(f"Could not find the content element with class 'provider-docs-content' for URL: {url} after page load.")
                scraped_data[url] = "Error: Content element not found."

        except Exception as e:
            print(f"Error scraping {url} with Selenium: {e}")
            print(f"Trying fallback method with requests...")
            
            # Try fallback method
            fallback_content = scrape_with_requests(url)
            if not fallback_content.startswith("Error"):
                scraped_data[url] = fallback_content
                print(f"Successfully scraped with fallback method: {url}")
            else:
                scraped_data[url] = f"Selenium Error: {e}. Fallback Error: {fallback_content}"
                print(f"Both methods failed for {url}")
        
        # Add a small delay to be polite to the server, especially if scraping many pages
        time.sleep(1) # 1 second delay

finally:
    # Important to close the browser session
    if selenium_available and driver is not None:
        driver.quit()
        print("Browser closed.")
    elif not selenium_available:
        print("No browser session to close (used requests-only method).")

# --- You can now process scraped_data as needed ---
# For example, print all successfully scraped URLs and a snippet of their content
print("\n\n--- Scraping Summary ---")
for url, content in scraped_data.items():
    if not content.startswith("Error:"):
        print(f"\nURL: {url}")
        print(f"Content (first 200 chars): {content[:200].strip()}...")
    else:
        print(f"\nURL: {url}")
        print(f"Scraping failed: {content}")

print(f"\nProcessed {len(scraped_data)} URLs.")
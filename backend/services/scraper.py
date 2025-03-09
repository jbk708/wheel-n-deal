import re
import time
from urllib.parse import urlparse

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup


def get_website_type(url):
    """
    Determine the type of website based on the URL.
    """
    domain = urlparse(url).netloc.lower()
    
    if "amazon" in domain:
        return "amazon"
    elif "walmart" in domain:
        return "walmart"
    elif "bestbuy" in domain:
        return "bestbuy"
    elif "target" in domain:
        return "target"
    elif "ebay" in domain:
        return "ebay"
    else:
        return "generic"


def scrape_amazon(driver, soup):
    """
    Scrape product information from Amazon.
    """
    # Extract product title
    product_title = (
        soup.find("span", {"id": "productTitle"}).get_text(strip=True)
        if soup.find("span", {"id": "productTitle"})
        else "Unknown Product"
    )

    # Try to find the product price in different possible locations
    product_price = None
    price_selectors = [
        {"id": "priceblock_ourprice"},
        {"id": "priceblock_dealprice"},
        {"class": "a-offscreen"},
        {"class": "a-price-whole"},
    ]

    for selector in price_selectors:
        if "id" in selector:
            price_element = soup.find("span", {"id": selector["id"]})
        elif "class" in selector:
            price_element = soup.find("span", {"class": selector["class"]})

        if price_element:
            product_price = price_element.get_text(strip=True)
            break

    # If still not found, try another approach
    if not product_price:
        try:
            price_element = driver.find_element(By.CSS_SELECTOR, ".a-price .a-offscreen")
            product_price = price_element.get_attribute("innerText")
        except NoSuchElementException:
            pass

    if not product_price:
        product_price = "Price not found"

    return {"title": product_title, "price": product_price}


def scrape_walmart(driver, soup):
    """
    Scrape product information from Walmart.
    """
    # Extract product title
    product_title = (
        soup.find("h1", {"itemprop": "name"}).get_text(strip=True)
        if soup.find("h1", {"itemprop": "name"})
        else soup.find("h1", {"class": "prod-ProductTitle"}).get_text(strip=True)
        if soup.find("h1", {"class": "prod-ProductTitle"})
        else "Unknown Product"
    )

    # Try to find the product price
    product_price = None
    try:
        price_element = driver.find_element(By.CSS_SELECTOR, "[data-testid='price-wrap'] span[itemprop='price']")
        product_price = price_element.get_attribute("content")
    except NoSuchElementException:
        try:
            price_element = driver.find_element(By.CSS_SELECTOR, ".price-characteristic")
            product_price = price_element.get_attribute("content")
        except NoSuchElementException:
            product_price = "Price not found"

    return {"title": product_title, "price": product_price}


def scrape_bestbuy(driver, soup):
    """
    Scrape product information from Best Buy.
    """
    # Extract product title
    product_title = (
        soup.find("h1", {"class": "heading-5"}).get_text(strip=True)
        if soup.find("h1", {"class": "heading-5"})
        else "Unknown Product"
    )

    # Try to find the product price
    product_price = None
    try:
        price_element = driver.find_element(By.CSS_SELECTOR, ".priceView-customer-price span")
        product_price = price_element.text
    except NoSuchElementException:
        product_price = "Price not found"

    return {"title": product_title, "price": product_price}


def scrape_target(driver, soup):
    """
    Scrape product information from Target.
    """
    # Extract product title
    product_title = (
        soup.find("h1", {"data-test": "product-title"}).get_text(strip=True)
        if soup.find("h1", {"data-test": "product-title"})
        else "Unknown Product"
    )

    # Try to find the product price
    product_price = None
    try:
        price_element = driver.find_element(By.CSS_SELECTOR, "[data-test='product-price']")
        product_price = price_element.text
    except NoSuchElementException:
        product_price = "Price not found"

    return {"title": product_title, "price": product_price}


def scrape_ebay(driver, soup):
    """
    Scrape product information from eBay.
    """
    # Extract product title
    product_title = (
        soup.find("h1", {"id": "itemTitle"}).get_text(strip=True).replace("Details about", "").strip()
        if soup.find("h1", {"id": "itemTitle"})
        else "Unknown Product"
    )

    # Try to find the product price
    product_price = None
    try:
        price_element = driver.find_element(By.CSS_SELECTOR, "#prcIsum")
        product_price = price_element.get_attribute("content")
    except NoSuchElementException:
        try:
            price_element = driver.find_element(By.CSS_SELECTOR, "#mm-saleDscPrc")
            product_price = price_element.text
        except NoSuchElementException:
            product_price = "Price not found"

    return {"title": product_title, "price": product_price}


def scrape_generic(driver, soup):
    """
    Scrape product information from a generic website.
    """
    # Try to find the product title
    product_title = "Unknown Product"
    title_tags = soup.find_all(["h1", "h2"])
    for tag in title_tags:
        if tag.text.strip():
            product_title = tag.text.strip()
            break

    # Try to find the product price
    product_price = "Price not found"
    # Look for currency symbols followed by numbers
    price_pattern = r'[$€£¥](\d+(?:,\d+)*(?:\.\d+)?)'
    price_matches = re.findall(price_pattern, soup.text)
    if price_matches:
        product_price = f"${price_matches[0]}"

    return {"title": product_title, "price": product_price}


def scrape_product_info(url: str):
    """
    Scrape product information from a given URL.
    
    Args:
        url: The URL of the product page to scrape.
        
    Returns:
        A dictionary containing the product title, price, and URL.
    """
    # Set up Selenium with a headless Chrome browser
    options = Options()
    options.add_argument("--headless")  # Ensure Chrome runs in headless mode
    options.add_argument("--no-sandbox")  # Bypass OS security model, required for Docker
    options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
    options.add_argument("--disable-gpu")  # Disable GPU hardware acceleration
    options.add_argument("--window-size=1920x1080")  # Set a large enough window size
    options.add_argument("--disable-software-rasterizer")  # Disable 3D software rasterization
    options.add_argument("--remote-debugging-port=9222")  # Debugging for troubleshooting
    
    # Add user agent to avoid detection
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

    driver = webdriver.Chrome(options=options)
    
    try:
        # Fetch the page
        driver.get(url)
        
        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        # Add a small delay to ensure JavaScript has time to execute
        time.sleep(2)
        
        # Get the page source and parse it with BeautifulSoup
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        # Determine the website type
        website_type = get_website_type(url)
        
        # Scrape product information based on the website type
        if website_type == "amazon":
            product_info = scrape_amazon(driver, soup)
        elif website_type == "walmart":
            product_info = scrape_walmart(driver, soup)
        elif website_type == "bestbuy":
            product_info = scrape_bestbuy(driver, soup)
        elif website_type == "target":
            product_info = scrape_target(driver, soup)
        elif website_type == "ebay":
            product_info = scrape_ebay(driver, soup)
        else:
            product_info = scrape_generic(driver, soup)
        
        # Add the URL to the product information
        product_info["url"] = url
        
        # Clean up the price format
        if product_info["price"] != "Price not found":
            # Extract the first price found in the string
            price_match = re.search(r'[$€£¥]?(\d+(?:,\d+)*(?:\.\d+)?)', product_info["price"])
            if price_match:
                product_info["price"] = f"${price_match.group(1)}"
            else:
                product_info["price"] = "Price not found"
        
        return product_info
    
    except TimeoutException:
        return {"title": "Error: Page load timeout", "price": "Price not found", "url": url}
    except Exception as e:
        return {"title": f"Error: {str(e)}", "price": "Price not found", "url": url}
    finally:
        # Close the browser
        driver.quit()

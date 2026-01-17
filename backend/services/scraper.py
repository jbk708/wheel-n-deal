import json
import re
import time
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from utils.logging import get_logger
from utils.monitoring import ScraperMetrics
from utils.pricing import format_price, parse_price

# Setup logger
logger = get_logger("scraper")


def _find_product_in_json_ld(data) -> dict | None:
    """Recursively find a Product object in JSON-LD data."""
    if isinstance(data, dict):
        type_val = data.get("@type")
        # Handle @type as string or list
        is_product = type_val == "Product" or (isinstance(type_val, list) and "Product" in type_val)
        if is_product:
            return data
        # Check @graph for nested structures
        if "@graph" in data:
            return _find_product_in_json_ld(data["@graph"])
    elif isinstance(data, list):
        for item in data:
            result = _find_product_in_json_ld(item)
            if result:
                return result
    return None


def _extract_price_from_offers(offers) -> str | None:
    """Extract price from offers object (handles Offer, AggregateOffer, lists)."""
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    if isinstance(offers, dict):
        # Direct price
        price = offers.get("price")
        if price:
            return f"${price}"
        # Try lowPrice for AggregateOffer
        low_price = offers.get("lowPrice")
        if low_price:
            return f"${low_price}"
    return None


def extract_price_from_json_ld(soup) -> str | None:
    """Extract price from JSON-LD schema if present."""
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string)
            product = _find_product_in_json_ld(data)
            if product:
                offers = product.get("offers", {})
                price = _extract_price_from_offers(offers)
                if price:
                    return price
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def extract_title_from_json_ld(soup) -> str | None:
    """Extract product title from JSON-LD schema if present."""
    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string)
            product = _find_product_in_json_ld(data)
            if product and product.get("name"):
                return product["name"]
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def extract_og_title(soup) -> str | None:
    """Extract title from og:title meta tag if present."""
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        return og_title["content"]
    return None


def extract_og_price(soup) -> str | None:
    """Extract price from og:price:amount meta tag if present."""
    og_price = soup.find("meta", property="og:price:amount")
    if og_price and og_price.get("content"):
        return f"${og_price['content']}"
    return None


DOMAIN_TO_WEBSITE_TYPE = {
    "amazon": "amazon",
    "walmart": "walmart",
    "bestbuy": "bestbuy",
    "target": "target",
    "ebay": "ebay",
    "sephora": "sephora",
    "dedcool": "dedcool",
    "costco": "costco",
}


def get_website_type(url):
    """
    Determine the type of website based on the URL.
    """
    domain = urlparse(url).netloc.lower()
    for keyword, website_type in DOMAIN_TO_WEBSITE_TYPE.items():
        if keyword in domain:
            return website_type
    return "generic"


def scrape_amazon(driver, soup):
    """
    Scrape product information from Amazon.
    """
    logger.debug("Scraping Amazon product")
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
            logger.warning("Could not find price element on Amazon page")
            pass

    if not product_price:
        logger.warning("Price not found for Amazon product")
        product_price = "Price not found"

    logger.info(f"Scraped Amazon product: {product_title} at {product_price}")
    return {"title": product_title, "price": product_price}


def scrape_walmart(driver, soup):
    """
    Scrape product information from Walmart.
    """
    logger.debug("Scraping Walmart product")
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
        price_element = driver.find_element(
            By.CSS_SELECTOR, "[data-testid='price-wrap'] span[itemprop='price']"
        )
        product_price = price_element.get_attribute("content")
    except NoSuchElementException:
        try:
            price_element = driver.find_element(By.CSS_SELECTOR, ".price-characteristic")
            product_price = price_element.get_attribute("content")
        except NoSuchElementException:
            logger.warning("Could not find price element on Walmart page")
            product_price = "Price not found"

    logger.info(f"Scraped Walmart product: {product_title} at {product_price}")
    return {"title": product_title, "price": product_price}


def scrape_bestbuy(driver, soup):
    """
    Scrape product information from Best Buy.
    """
    logger.debug("Scraping Best Buy product")
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
        logger.warning("Could not find price element on Best Buy page")
        product_price = "Price not found"

    logger.info(f"Scraped Best Buy product: {product_title} at {product_price}")
    return {"title": product_title, "price": product_price}


def scrape_target(driver, soup):
    """
    Scrape product information from Target.
    """
    logger.debug("Scraping Target product")
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
        logger.warning("Could not find price element on Target page")
        product_price = "Price not found"

    logger.info(f"Scraped Target product: {product_title} at {product_price}")
    return {"title": product_title, "price": product_price}


def scrape_ebay(driver, soup):
    """
    Scrape product information from eBay.
    """
    logger.debug("Scraping eBay product")
    # Extract product title
    product_title = (
        soup.find("h1", {"id": "itemTitle"})
        .get_text(strip=True)
        .replace("Details about", "")
        .strip()
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
            logger.warning("Could not find price element on eBay page")
            product_price = "Price not found"

    logger.info(f"Scraped eBay product: {product_title} at {product_price}")
    return {"title": product_title, "price": product_price}


def scrape_sephora(driver, soup):
    """Scrape product information from Sephora."""
    logger.debug("Scraping Sephora product")

    # Extract product title - try Sephora-specific attributes first
    product_title = None
    title_elem = soup.find("span", {"data-at": "product_name"})
    if title_elem:
        product_title = title_elem.get_text(strip=True)
    if not product_title:
        title_elem = soup.find("h1", class_=lambda c: c and "ProductName" in c)
        if title_elem:
            product_title = title_elem.get_text(strip=True)
    if not product_title:
        og_title = extract_og_title(soup)
        if og_title:
            product_title = og_title.split("|")[0].strip()
    if not product_title:
        product_title = "Unknown Product"

    # Extract price - try Sephora-specific attributes first
    product_price = None
    price_elem = soup.find("span", {"data-at": "price"})
    if price_elem:
        product_price = price_elem.get_text(strip=True)
    if not product_price:
        product_price = extract_price_from_json_ld(soup)
    if not product_price:
        try:
            price_elem = driver.find_element(
                By.CSS_SELECTOR, "[data-comp='Price'] b, [data-at='price']"
            )
            product_price = price_elem.text
        except NoSuchElementException:
            pass
    if not product_price:
        product_price = "Price not found"

    logger.info(f"Scraped Sephora product: {product_title} at {product_price}")
    return {"title": product_title, "price": product_price}


def scrape_dedcool(driver, soup):
    """Scrape product information from DedCool (Shopify store)."""
    logger.debug("Scraping DedCool product")

    # Extract title - og:title is most reliable for Shopify stores
    product_title = extract_og_title(soup)
    if not product_title:
        title_elem = soup.find("h1", class_=lambda c: c and "product" in c.lower())
        if title_elem:
            product_title = title_elem.get_text(strip=True)
    if not product_title:
        title_elem = soup.find("h1")
        if title_elem:
            product_title = title_elem.get_text(strip=True)
    if not product_title:
        product_title = "Unknown Product"

    # Extract price - JSON-LD is most reliable for Shopify stores
    product_price = extract_price_from_json_ld(soup)
    if not product_price:
        price_elem = soup.find("span", class_=lambda c: c and "price" in c.lower())
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            if "$" in price_text:
                product_price = price_text
    if not product_price:
        product_price = extract_og_price(soup)
    if not product_price:
        product_price = "Price not found"

    logger.info(f"Scraped DedCool product: {product_title} at {product_price}")
    return {"title": product_title, "price": product_price}


def scrape_costco(driver, soup):
    """Scrape product information from Costco."""
    logger.debug("Scraping Costco product")

    # Extract title - try Costco-specific attributes first
    product_title = None
    title_elem = soup.find("h1", {"automation-id": "productName"})
    if title_elem:
        product_title = title_elem.get_text(strip=True)
    if not product_title:
        title_elem = soup.find("h1", {"id": "product-title"})
        if title_elem:
            product_title = title_elem.get_text(strip=True)
    if not product_title:
        product_title = extract_og_title(soup)
    if not product_title:
        product_title = "Unknown Product"

    # Extract price - try JSON-LD first
    product_price = extract_price_from_json_ld(soup)
    if not product_price:
        try:
            price_elem = driver.find_element(By.CSS_SELECTOR, "[automation-id='productPrice']")
            product_price = price_elem.text
        except NoSuchElementException:
            pass
    if not product_price:
        price_elem = soup.find("span", class_=lambda c: c and "price" in c.lower())
        if price_elem:
            price_text = price_elem.get_text(strip=True)
            if "$" in price_text:
                product_price = price_text
    if not product_price:
        product_price = "Price not found"

    logger.info(f"Scraped Costco product: {product_title} at {product_price}")
    return {"title": product_title, "price": product_price}


def scrape_generic(driver, soup):
    """Scrape product information from a generic website using multiple fallback strategies."""
    logger.debug("Scraping generic website product")

    # Title extraction with priority order
    product_title = extract_og_title(soup)
    if not product_title:
        product_title = extract_title_from_json_ld(soup)
    if not product_title:
        for attr in ["itemprop", "data-product", "data-name"]:
            elem = soup.find("h1", {attr: True})
            if elem:
                product_title = elem.get_text(strip=True)
                break
    if not product_title:
        skip_words = ["menu", "navigation", "cart", "search", "login", "sign", "list"]
        for h1 in soup.find_all("h1"):
            text = h1.get_text(strip=True)
            if text and len(text) > 5 and not any(w in text.lower() for w in skip_words):
                product_title = text
                break
    if not product_title:
        product_title = "Unknown Product"

    # Price extraction with priority order
    product_price = extract_price_from_json_ld(soup)
    if not product_price:
        price_elem = soup.find(attrs={"itemprop": "price"})
        if price_elem:
            price_content = price_elem.get("content") or price_elem.get_text(strip=True)
            if price_content:
                product_price = price_content if "$" in price_content else f"${price_content}"
    if not product_price:
        product_price = extract_og_price(soup)
    if not product_price:
        for attr in ["data-price", "data-product-price"]:
            elem = soup.find(attrs={attr: True})
            if elem:
                price_val = elem.get(attr)
                if price_val:
                    product_price = f"${price_val}"
                    break
    if not product_price:
        price_pattern = r"\$(\d+(?:,\d+)*(?:\.\d{2})?)"
        for selector in ["[class*='price']", "[id*='price']", "[data-price]"]:
            for elem in soup.select(selector):
                text = elem.get_text()
                match = re.search(price_pattern, text)
                if match:
                    product_price = f"${match.group(1)}"
                    break
            if product_price:
                break
    if not product_price:
        product_price = "Price not found"

    logger.info(f"Scraped generic website product: {product_title} at {product_price}")
    return {"title": product_title, "price": product_price}


def scrape_product_info(url: str):
    """
    Scrape product information from a given URL.

    Args:
        url: The URL of the product page to scrape.

    Returns:
        A dictionary containing the product title, price, and URL.
    """
    # Determine the website type
    website_type = get_website_type(url)
    logger.info(f"Scraping product from {website_type} website: {url}")

    # Use the ScraperMetrics context manager to track metrics
    with ScraperMetrics(website=website_type):
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
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36"
        )

        driver = webdriver.Chrome(options=options)

        try:
            # Fetch the page
            logger.debug(f"Fetching page: {url}")
            driver.get(url)

            # Wait for the page to load
            logger.debug("Waiting for page to load")
            WebDriverWait(driver, 10).until(
                expected_conditions.presence_of_element_located((By.TAG_NAME, "body"))
            )

            # Add a small delay to ensure JavaScript has time to execute
            time.sleep(2)

            # Get the page source and parse it with BeautifulSoup
            logger.debug("Parsing page source")
            soup = BeautifulSoup(driver.page_source, "html.parser")

            # Scrape product information based on the website type
            scraper_map = {
                "amazon": scrape_amazon,
                "walmart": scrape_walmart,
                "bestbuy": scrape_bestbuy,
                "target": scrape_target,
                "ebay": scrape_ebay,
                "sephora": scrape_sephora,
                "dedcool": scrape_dedcool,
                "costco": scrape_costco,
            }
            scraper_func = scraper_map.get(website_type, scrape_generic)
            product_info = scraper_func(driver, soup)

            # Add the URL to the product information
            product_info["url"] = url

            # Parse price to float and create consistent display string
            product_info["price_float"] = parse_price(product_info["price"])
            product_info["price"] = format_price(product_info["price_float"])

            logger.info(
                f"Successfully scraped product: {product_info['title']} at {product_info['price']}"
            )
            return product_info

        except TimeoutException:
            logger.error(f"Timeout while scraping {url}")
            return {
                "title": "Error: Page load timeout",
                "price": "Price not found",
                "price_float": None,
                "url": url,
            }
        except Exception as e:
            logger.error(f"Error scraping {url}: {e!s}", exc_info=True)
            return {
                "title": f"Error: {e!s}",
                "price": "Price not found",
                "price_float": None,
                "url": url,
            }
        finally:
            # Close the browser
            logger.debug("Closing browser")
            driver.quit()

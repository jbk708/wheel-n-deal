from selenium import webdriver
from bs4 import BeautifulSoup


def scrape_product_info(url: str):
    # Set up Selenium with a headless Chrome browser
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Ensure Chrome runs in headless mode
    options.add_argument(
        "--no-sandbox"
    )  # Bypass OS security model, required for Docker
    options.add_argument(
        "--disable-dev-shm-usage"
    )  # Overcome limited resource problems
    options.add_argument("--disable-gpu")  # Disable GPU hardware acceleration
    options.add_argument("--window-size=1920x1080")  # Set a large enough window size
    options.add_argument(
        "--disable-software-rasterizer"
    )  # Disable 3D software rasterization
    options.add_argument(
        "--remote-debugging-port=9222"
    )  # Debugging for troubleshooting

    driver = webdriver.Chrome(options=options)

    # Fetch the page
    driver.get(url)
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Close the browser after getting the page content
    driver.quit()

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
        {"class": "priceToPay"},
    ]

    for selector in price_selectors:
        if "id" in selector:
            price_element = soup.find("span", {"id": selector["id"]})
        elif "class" in selector:
            price_element = soup.find("span", {"class": selector["class"]})

        if price_element:
            product_price = price_element.get_text(strip=True)
            break

    if not product_price:
        product_price = "Price not found"

    return {"title": product_title, "price": product_price, "url": url}

import requests
from bs4 import BeautifulSoup


def scrape_product_info(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        raise Exception("Failed to fetch product page")

    soup = BeautifulSoup(response.content, "html.parser")

    # Extract product details (this will depend on the website's structure)
    product_title = (
        soup.find("span", {"id": "productTitle"}).get_text(strip=True)
        if soup.find("span", {"id": "productTitle"})
        else "Unknown Product"
    )
    product_price = (
        soup.find("span", {"id": "priceblock_ourprice"}).get_text(strip=True)
        if soup.find("span", {"id": "priceblock_ourprice"})
        else "Price not found"
    )

    return {"title": product_title, "price": product_price, "url": url}

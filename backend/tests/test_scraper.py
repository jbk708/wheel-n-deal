from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException

from services.scraper import (
    get_website_type,
    scrape_costco,
    scrape_dedcool,
    scrape_product_info,
    scrape_sephora,
)


# Test for website type detection
def test_get_website_type():
    assert get_website_type("https://www.amazon.com/product") == "amazon"
    assert get_website_type("https://amazon.co.uk/product") == "amazon"
    assert get_website_type("https://www.walmart.com/product") == "walmart"
    assert get_website_type("https://www.bestbuy.com/product") == "bestbuy"
    assert get_website_type("https://www.target.com/product") == "target"
    assert get_website_type("https://www.ebay.com/product") == "ebay"
    assert get_website_type("https://www.sephora.com/product") == "sephora"
    assert get_website_type("https://dedcool.com/product") == "dedcool"
    assert get_website_type("https://www.costco.com/product") == "costco"
    assert get_website_type("https://www.example.com/product") == "generic"


@pytest.mark.parametrize(
    "website_type,scraper_func,url,title,price,price_float",
    [
        ("amazon", "scrape_amazon", "https://amazon.com/product", "Test Product", "$10.99", 10.99),
        (
            "walmart",
            "scrape_walmart",
            "https://walmart.com/product",
            "Test Product",
            "$10.99",
            10.99,
        ),
        (
            "bestbuy",
            "scrape_bestbuy",
            "https://bestbuy.com/product",
            "Test Product",
            "$10.99",
            10.99,
        ),
        ("target", "scrape_target", "https://target.com/product", "Test Product", "$10.99", 10.99),
        ("ebay", "scrape_ebay", "https://ebay.com/product", "Test Product", "$10.99", 10.99),
        (
            "generic",
            "scrape_generic",
            "https://example.com/product",
            "Test Product",
            "$10.99",
            10.99,
        ),
        (
            "sephora",
            "scrape_sephora",
            "https://sephora.com/product",
            "Sunscreen SPF 50",
            "$48.00",
            48.00,
        ),
        (
            "dedcool",
            "scrape_dedcool",
            "https://dedcool.com/products/xtra-milk",
            "Xtra Milk Fragrance",
            "$98.00",
            98.00,
        ),
        (
            "costco",
            "scrape_costco",
            "https://costco.com/product",
            "Kirkland Olive Oil",
            "$24.99",
            24.99,
        ),
    ],
)
@patch("services.scraper.webdriver.Chrome")
@patch("services.scraper.BeautifulSoup")
def test_scrape_product_info(
    mock_soup, mock_chrome, website_type, scraper_func, url, title, price, price_float
):
    """Test scrape_product_info dispatches to the correct scraper and returns expected results."""
    mock_driver = MagicMock()
    mock_chrome.return_value = mock_driver

    with (
        patch("services.scraper.get_website_type", return_value=website_type),
        patch(
            f"services.scraper.{scraper_func}", return_value={"title": title, "price": price}
        ) as mock_scraper,
    ):
        result = scrape_product_info(url)

        assert result["title"] == title
        assert result["price"] == price
        assert result["price_float"] == price_float
        assert result["url"] == url

        mock_chrome.assert_called_once()
        mock_driver.get.assert_called_once_with(url)
        mock_driver.quit.assert_called_once()
        mock_scraper.assert_called_once()


def test_scrape_sephora_with_og_title():
    """Test Sephora scraper extracts title from og:title and price from JSON-LD."""
    html = """
    <html>
    <head>
        <meta property="og:title" content="Supergoop! Unseen Sunscreen | Sephora">
        <script type="application/ld+json">
        {"@type": "Product", "offers": {"price": "48.00"}}
        </script>
    </head>
    <body></body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = scrape_sephora(MagicMock(), soup)

    assert result["title"] == "Supergoop! Unseen Sunscreen"
    assert result["price"] == "$48.00"


def test_scrape_dedcool_with_json_ld():
    """Test DedCool scraper extracts title from og:title and price from JSON-LD."""
    html = """
    <html>
    <head>
        <meta property="og:title" content="XTRA MILK Fragrance">
        <script type="application/ld+json">
        {"@type": "Product", "offers": {"price": "98.00"}}
        </script>
    </head>
    <body></body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = scrape_dedcool(MagicMock(), soup)

    assert result["title"] == "XTRA MILK Fragrance"
    assert result["price"] == "$98.00"


def test_scrape_costco_with_og_title():
    """Test Costco scraper extracts title from og:title and price from JSON-LD."""
    html = """
    <html>
    <head>
        <meta property="og:title" content="Kirkland Signature Olive Oil, 3 L">
        <script type="application/ld+json">
        {"@type": "Product", "offers": {"price": "24.99"}}
        </script>
    </head>
    <body></body>
    </html>
    """
    soup = BeautifulSoup(html, "html.parser")
    result = scrape_costco(MagicMock(), soup)

    assert result["title"] == "Kirkland Signature Olive Oil, 3 L"
    assert result["price"] == "$24.99"


@patch("services.scraper.webdriver.Chrome")
@patch("services.scraper.WebDriverWait")
@patch("services.scraper.get_website_type")
def test_scrape_product_info_timeout(mock_get_website_type, mock_wait, mock_chrome):
    """Test that timeout exceptions are handled gracefully."""
    mock_driver = MagicMock()
    mock_chrome.return_value = mock_driver
    mock_wait.side_effect = TimeoutException("Timeout")

    url = "https://example.com/product"
    result = scrape_product_info(url)

    assert result["title"] == "Error: Page load timeout"
    assert result["price"] == "Price not found"
    assert result["url"] == url
    mock_chrome.assert_called_once()
    mock_driver.get.assert_called_once_with(url)
    mock_driver.quit.assert_called_once()


@patch("services.scraper.webdriver.Chrome")
@patch("services.scraper.get_website_type")
def test_scrape_product_info_exception(mock_get_website_type, mock_chrome):
    """Test that general exceptions are handled gracefully."""
    mock_driver = MagicMock()
    mock_chrome.return_value = mock_driver
    mock_driver.get.side_effect = Exception("Test exception")

    url = "https://example.com/product"
    result = scrape_product_info(url)

    assert result["title"] == "Error: Test exception"
    assert result["price"] == "Price not found"
    assert result["url"] == url
    mock_chrome.assert_called_once()
    mock_driver.quit.assert_called_once()

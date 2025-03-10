from unittest.mock import MagicMock, patch

from services.scraper import (
    get_website_type,
    scrape_product_info,
)


# Test for website type detection
def test_get_website_type():
    assert get_website_type("https://www.amazon.com/product") == "amazon"
    assert get_website_type("https://amazon.co.uk/product") == "amazon"
    assert get_website_type("https://www.walmart.com/product") == "walmart"
    assert get_website_type("https://www.bestbuy.com/product") == "bestbuy"
    assert get_website_type("https://www.target.com/product") == "target"
    assert get_website_type("https://www.ebay.com/product") == "ebay"
    assert get_website_type("https://www.example.com/product") == "generic"


# Test for successful scraping with Amazon
@patch("services.scraper.webdriver.Chrome")
@patch("services.scraper.BeautifulSoup")
@patch("services.scraper.get_website_type", return_value="amazon")
@patch("services.scraper.scrape_amazon")
def test_scrape_product_info_amazon(
    mock_scrape_amazon, mock_get_website_type, mock_soup, mock_chrome
):
    # Mock the Selenium WebDriver behavior
    mock_driver = MagicMock()
    mock_chrome.return_value = mock_driver

    # Mock the scrape_amazon function
    mock_scrape_amazon.return_value = {"title": "Test Product", "price": "$10.99"}

    # Call the function
    url = "https://amazon.com/product"
    result = scrape_product_info(url)

    # Verify the result
    assert result["title"] == "Test Product"
    assert result["price"] == "$10.99"
    assert result["url"] == url

    # Verify that the WebDriver was used correctly
    mock_chrome.assert_called_once()
    mock_driver.get.assert_called_once_with(url)
    mock_driver.quit.assert_called_once()

    # Verify that get_website_type was called
    mock_get_website_type.assert_called_once_with(url)

    # Verify that scrape_amazon was called
    mock_scrape_amazon.assert_called_once()


# Test for successful scraping with Walmart
@patch("services.scraper.webdriver.Chrome")
@patch("services.scraper.BeautifulSoup")
@patch("services.scraper.get_website_type", return_value="walmart")
@patch("services.scraper.scrape_walmart")
def test_scrape_product_info_walmart(
    mock_scrape_walmart, mock_get_website_type, mock_soup, mock_chrome
):
    # Mock the Selenium WebDriver behavior
    mock_driver = MagicMock()
    mock_chrome.return_value = mock_driver

    # Mock the scrape_walmart function
    mock_scrape_walmart.return_value = {"title": "Test Product", "price": "$10.99"}

    # Call the function
    url = "https://walmart.com/product"
    result = scrape_product_info(url)

    # Verify the result
    assert result["title"] == "Test Product"
    assert result["price"] == "$10.99"
    assert result["url"] == url

    # Verify that the WebDriver was used correctly
    mock_chrome.assert_called_once()
    mock_driver.get.assert_called_once_with(url)
    mock_driver.quit.assert_called_once()

    # Verify that get_website_type was called
    mock_get_website_type.assert_called_once_with(url)

    # Verify that scrape_walmart was called
    mock_scrape_walmart.assert_called_once()


# Test for successful scraping with Best Buy
@patch("services.scraper.webdriver.Chrome")
@patch("services.scraper.BeautifulSoup")
@patch("services.scraper.get_website_type", return_value="bestbuy")
@patch("services.scraper.scrape_bestbuy")
def test_scrape_product_info_bestbuy(
    mock_scrape_bestbuy, mock_get_website_type, mock_soup, mock_chrome
):
    # Mock the Selenium WebDriver behavior
    mock_driver = MagicMock()
    mock_chrome.return_value = mock_driver

    # Mock the scrape_bestbuy function
    mock_scrape_bestbuy.return_value = {"title": "Test Product", "price": "$10.99"}

    # Call the function
    url = "https://bestbuy.com/product"
    result = scrape_product_info(url)

    # Verify the result
    assert result["title"] == "Test Product"
    assert result["price"] == "$10.99"
    assert result["url"] == url

    # Verify that the WebDriver was used correctly
    mock_chrome.assert_called_once()
    mock_driver.get.assert_called_once_with(url)
    mock_driver.quit.assert_called_once()

    # Verify that get_website_type was called
    mock_get_website_type.assert_called_once_with(url)

    # Verify that scrape_bestbuy was called
    mock_scrape_bestbuy.assert_called_once()


# Test for successful scraping with Target
@patch("services.scraper.webdriver.Chrome")
@patch("services.scraper.BeautifulSoup")
@patch("services.scraper.get_website_type", return_value="target")
@patch("services.scraper.scrape_target")
def test_scrape_product_info_target(
    mock_scrape_target, mock_get_website_type, mock_soup, mock_chrome
):
    # Mock the Selenium WebDriver behavior
    mock_driver = MagicMock()
    mock_chrome.return_value = mock_driver

    # Mock the scrape_target function
    mock_scrape_target.return_value = {"title": "Test Product", "price": "$10.99"}

    # Call the function
    url = "https://target.com/product"
    result = scrape_product_info(url)

    # Verify the result
    assert result["title"] == "Test Product"
    assert result["price"] == "$10.99"
    assert result["url"] == url

    # Verify that the WebDriver was used correctly
    mock_chrome.assert_called_once()
    mock_driver.get.assert_called_once_with(url)
    mock_driver.quit.assert_called_once()

    # Verify that get_website_type was called
    mock_get_website_type.assert_called_once_with(url)

    # Verify that scrape_target was called
    mock_scrape_target.assert_called_once()


# Test for successful scraping with eBay
@patch("services.scraper.webdriver.Chrome")
@patch("services.scraper.BeautifulSoup")
@patch("services.scraper.get_website_type", return_value="ebay")
@patch("services.scraper.scrape_ebay")
def test_scrape_product_info_ebay(mock_scrape_ebay, mock_get_website_type, mock_soup, mock_chrome):
    # Mock the Selenium WebDriver behavior
    mock_driver = MagicMock()
    mock_chrome.return_value = mock_driver

    # Mock the scrape_ebay function
    mock_scrape_ebay.return_value = {"title": "Test Product", "price": "$10.99"}

    # Call the function
    url = "https://ebay.com/product"
    result = scrape_product_info(url)

    # Verify the result
    assert result["title"] == "Test Product"
    assert result["price"] == "$10.99"
    assert result["url"] == url

    # Verify that the WebDriver was used correctly
    mock_chrome.assert_called_once()
    mock_driver.get.assert_called_once_with(url)
    mock_driver.quit.assert_called_once()

    # Verify that get_website_type was called
    mock_get_website_type.assert_called_once_with(url)

    # Verify that scrape_ebay was called
    mock_scrape_ebay.assert_called_once()


# Test for successful scraping with generic website
@patch("services.scraper.webdriver.Chrome")
@patch("services.scraper.BeautifulSoup")
@patch("services.scraper.get_website_type", return_value="generic")
@patch("services.scraper.scrape_generic")
def test_scrape_product_info_generic(
    mock_scrape_generic, mock_get_website_type, mock_soup, mock_chrome
):
    # Mock the Selenium WebDriver behavior
    mock_driver = MagicMock()
    mock_chrome.return_value = mock_driver

    # Mock the scrape_generic function
    mock_scrape_generic.return_value = {"title": "Test Product", "price": "$10.99"}

    # Call the function
    url = "https://example.com/product"
    result = scrape_product_info(url)

    # Verify the result
    assert result["title"] == "Test Product"
    assert result["price"] == "$10.99"
    assert result["url"] == url

    # Verify that the WebDriver was used correctly
    mock_chrome.assert_called_once()
    mock_driver.get.assert_called_once_with(url)
    mock_driver.quit.assert_called_once()

    # Verify that get_website_type was called
    mock_get_website_type.assert_called_once_with(url)

    # Verify that scrape_generic was called
    mock_scrape_generic.assert_called_once()


# Test for timeout during scraping
@patch("services.scraper.webdriver.Chrome")
@patch("services.scraper.WebDriverWait")
@patch("services.scraper.get_website_type")
def test_scrape_product_info_timeout(mock_get_website_type, mock_wait, mock_chrome):
    # Mock the Selenium WebDriver behavior
    mock_driver = MagicMock()
    mock_chrome.return_value = mock_driver

    # Mock a timeout exception
    from selenium.common.exceptions import TimeoutException

    mock_wait.side_effect = TimeoutException("Timeout")

    # Call the function
    url = "https://example.com/product"
    result = scrape_product_info(url)

    # Verify the result
    assert result["title"] == "Error: Page load timeout"
    assert result["price"] == "Price not found"
    assert result["url"] == url

    # Verify that the WebDriver was used correctly
    mock_chrome.assert_called_once()
    mock_driver.get.assert_called_once_with(url)
    mock_driver.quit.assert_called_once()


# Test for exception during scraping
@patch("services.scraper.webdriver.Chrome")
@patch("services.scraper.get_website_type")
def test_scrape_product_info_exception(mock_get_website_type, mock_chrome):
    # Mock the Selenium WebDriver behavior
    mock_driver = MagicMock()
    mock_chrome.return_value = mock_driver

    # Mock an exception
    mock_driver.get.side_effect = Exception("Test exception")

    # Call the function
    url = "https://example.com/product"
    result = scrape_product_info(url)

    # Verify the result
    assert result["title"] == "Error: Test exception"
    assert result["price"] == "Price not found"
    assert result["url"] == url

    # Verify that the WebDriver was used correctly
    mock_chrome.assert_called_once()
    mock_driver.quit.assert_called_once()

from prometheus_client import Counter, Gauge, Histogram, Summary
import time
from contextlib import contextmanager
from utils.logging import get_logger

# Setup logger
logger = get_logger("monitoring")

# Define metrics
# Counters (only go up)
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total", 
    "Total number of HTTP requests", 
    ["method", "endpoint", "status"]
)
DATABASE_CONNECTIONS = Counter(
    "database_connections_total", 
    "Total number of database connections"
)
DATABASE_ERRORS = Counter(
    "database_errors_total", 
    "Total number of database errors"
)
SCRAPER_REQUESTS_TOTAL = Counter(
    "scraper_requests_total", 
    "Total number of scraper requests", 
    ["website"]
)
SCRAPER_ERRORS_TOTAL = Counter(
    "scraper_errors_total", 
    "Total number of scraper errors", 
    ["website", "error_type"]
)
SIGNAL_MESSAGES_SENT = Counter(
    "signal_messages_sent_total", 
    "Total number of Signal messages sent"
)
SIGNAL_MESSAGES_FAILED = Counter(
    "signal_messages_failed_total", 
    "Total number of Signal messages that failed to send"
)
PRICE_ALERTS_SENT = Counter(
    "price_alerts_sent_total", 
    "Total number of price alerts sent"
)

# Gauges (can go up and down)
TRACKED_PRODUCTS = Gauge(
    "tracked_products_total", 
    "Total number of products being tracked"
)
ACTIVE_REQUESTS = Gauge(
    "active_requests", 
    "Number of active requests"
)
BLOCKED_IPS = Gauge(
    "blocked_ips_total", 
    "Total number of blocked IPs"
)

# Histograms (distribution of values)
REQUEST_LATENCY = Histogram(
    "request_latency_seconds", 
    "Request latency in seconds", 
    ["method", "endpoint"]
)
SCRAPER_LATENCY = Histogram(
    "scraper_latency_seconds", 
    "Scraper latency in seconds", 
    ["website"]
)
DATABASE_QUERY_LATENCY = Histogram(
    "database_query_latency_seconds", 
    "Database query latency in seconds", 
    ["operation"]
)

# Summaries (similar to histograms but with quantiles)
REQUEST_SIZE = Summary(
    "request_size_bytes", 
    "Request size in bytes"
)
RESPONSE_SIZE = Summary(
    "response_size_bytes", 
    "Response size in bytes"
)


@contextmanager
def track_request_latency(method, endpoint):
    """
    Context manager to track request latency.
    """
    ACTIVE_REQUESTS.inc()
    start_time = time.time()
    try:
        yield
    finally:
        latency = time.time() - start_time
        REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(latency)
        ACTIVE_REQUESTS.dec()
        logger.debug(f"Request {method} {endpoint} took {latency:.4f} seconds")


@contextmanager
def track_database_query_latency(operation):
    """
    Context manager to track database query latency.
    """
    start_time = time.time()
    try:
        yield
    finally:
        latency = time.time() - start_time
        DATABASE_QUERY_LATENCY.labels(operation=operation).observe(latency)
        logger.debug(f"Database {operation} operation took {latency:.4f} seconds")


class ScraperMetrics:
    """
    Context manager to track scraper metrics.
    """
    def __init__(self, website):
        self.website = website
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        SCRAPER_REQUESTS_TOTAL.labels(website=self.website).inc()
        logger.debug(f"Starting scraper request for {self.website}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        latency = time.time() - self.start_time
        SCRAPER_LATENCY.labels(website=self.website).observe(latency)
        
        if exc_type is not None:
            error_type = exc_type.__name__
            SCRAPER_ERRORS_TOTAL.labels(website=self.website, error_type=error_type).inc()
            logger.warning(f"Scraper error for {self.website}: {error_type} - {exc_val}")
        else:
            logger.debug(f"Scraper request for {self.website} completed in {latency:.4f} seconds")
        
        return False  # Don't suppress exceptions 
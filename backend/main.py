import threading
from contextlib import asynccontextmanager

from celery_app import app as celery_app
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_wsgi_app
from wsgiref.simple_server import make_server
import uvicorn

from models import init_db
from routers import tracker
from services.listener import listen_to_group
from utils.logging import get_logger
from utils.monitoring import PrometheusMiddleware, TRACKED_PRODUCTS
from utils.security import setup_security

# Setup logger
logger = get_logger("main")

# Lifespan context manager for FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize the database and start the Signal listener
    logger.info("Starting application...")
    
    # Initialize the database
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized successfully")
    
    # Start the Signal listener in a separate thread
    logger.info("Starting Signal listener...")
    threading.Thread(target=listen_to_group, daemon=True).start()
    logger.info("Signal listener started successfully")
    
    # Start Prometheus metrics server
    logger.info("Starting Prometheus metrics server...")
    app_metrics = make_wsgi_app()
    httpd = make_server('', 8001, app_metrics)
    metrics_server = threading.Thread(target=httpd.serve_forever, daemon=True)
    metrics_server.start()
    logger.info("Prometheus metrics server started successfully on port 8001")
    
    yield
    
    # Shutdown: Clean up resources
    logger.info("Shutting down application...")
    # No cleanup needed for now


# Create FastAPI app
app = FastAPI(
    title="Wheel-n-Deal",
    description="An API for tracking product prices and sending alerts for flash sales.",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add Prometheus middleware
app.add_middleware(PrometheusMiddleware)

# Setup security
setup_security(app)

# Include routers
app.include_router(tracker.router, prefix="/api/v1/tracker", tags=["tracker"])

# Exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An unexpected error occurred. Please try again later."},
    )


@app.get("/")
async def root():
    """
    Root endpoint for checking the API status.
    """
    logger.info("Root endpoint accessed")
    return {"message": "Welcome to the Wheel-n-Deal Price Tracker API!"}


@app.get("/metrics")
async def metrics():
    """
    Endpoint to redirect to the Prometheus metrics server.
    """
    logger.info("Metrics endpoint accessed")
    return {"message": "Metrics available at http://localhost:8001"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

import threading

from backend.celery_app import Celery
from fastapi import FastAPI
from routers import tracker
from services.listener import listen_to_group  # Import the listener function

app = FastAPI(
    title="Wheel-n-Deal",
    description="An API for tracking product prices and sending alerts for flash sales.",
    version="0.1.0",
)

# Initialize Celery app for background tasks (if needed)
celery_app = Celery(
    "price_tracker",
    broker="redis://broker:6379/0",  # Use Redis or other broker
    backend="redis://broker:6379/0",
)

# Include the tracker router
app.include_router(tracker.router, prefix="/api/v1/tracker", tags=["tracker"])


@app.on_event("startup")
def start_signal_listener():
    """
    On FastAPI startup, this function starts the Signal listener in a separate thread.
    The listener will run as a background process and handle incoming Signal messages.
    """
    threading.Thread(target=listen_to_group, daemon=True).start()


@app.get("/")
async def root():
    """
    Root endpoint for checking the API status.
    """
    return {"message": "Welcome to the Wheel-n-Deal Price Tracker API!"}

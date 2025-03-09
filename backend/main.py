import threading

from celery_app import app as celery_app
from fastapi import FastAPI
from models import init_db
from routers import tracker
from services.listener import listen_to_group  # Import the listener function

app = FastAPI(
    title="Wheel-n-Deal",
    description="An API for tracking product prices and sending alerts for flash sales.",
    version="0.1.0",
)

# Include routers
app.include_router(tracker.router, prefix="/api/v1/tracker", tags=["tracker"])


@app.on_event("startup")
def start_signal_listener():
    """
    On FastAPI startup, this function starts the Signal listener in a separate thread.
    The listener will run as a background process and handle incoming Signal messages.
    """
    # Initialize the database
    init_db()
    
    # Start the Signal listener in a separate thread
    threading.Thread(target=listen_to_group, daemon=True).start()


@app.get("/")
async def root():
    """
    Root endpoint for checking the API status.
    """
    return {"message": "Welcome to the Wheel-n-Deal Price Tracker API!"}

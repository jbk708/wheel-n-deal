import threading
from fastapi import FastAPI
from routers import tracker
from services.listener import listen_to_group  # Import the listener function


app = FastAPI(
    title="Wheel-n-Deal",
    description="An API for tracking product prices and sending alerts for flash sales.",
    version="0.1.0",
)

# Include the tracker router
app.include_router(tracker.router, prefix="/api/v1/tracker", tags=["tracker"])


@app.on_event("startup")
def start_signal_listener():
    # Run the listener in a separate thread so it doesn't block the main FastAPI app
    threading.Thread(target=listen_to_group, daemon=True).start()


@app.get("/")
async def read_root():
    return {"message": "Welcome to the Price Tracker API!"}

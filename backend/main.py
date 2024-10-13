from fastapi import FastAPI
from routers import tracker

app = FastAPI(
    title="Wheel-n-Deal",
    description="An API for tracking product prices and sending alerts for flash sales.",
    version="0.1.0",
)

# Include the tracker router
app.include_router(tracker.router, prefix="/api/v1/tracker", tags=["tracker"])


@app.get("/")
async def read_root():
    return {"message": "Welcome to the Price Tracker API!"}

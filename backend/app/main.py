"""
Kisaan Mitra — FastAPI Backend
Entry point: registers all routers including crop recommendation.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.api import auth, prices, notifications, users, weather, crop_recommendation
from app.utils.database import connect_db, disconnect_db
from app.scheduler.price_scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    start_scheduler()
    yield
    stop_scheduler()
    await disconnect_db()


app = FastAPI(
    title="Kisaan Mitra API",
    description="Smart farmer assistant — prices, weather & AI crop recommendations",
    version="1.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,                prefix="/api/v1", tags=["Authentication"])
app.include_router(prices.router,              prefix="/api/v1", tags=["Prices"])
app.include_router(notifications.router,       prefix="/api/v1", tags=["Notifications"])
app.include_router(users.router,               prefix="/api/v1", tags=["Users"])
app.include_router(weather.router,             prefix="/api/v1", tags=["Weather"])
app.include_router(crop_recommendation.router, prefix="/api/v1", tags=["Crop Recommendation"])  # NEW


@app.get("/")
async def root():
    return {"message": "Kisaan Mitra API is running 🌾", "version": "1.2.0"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}

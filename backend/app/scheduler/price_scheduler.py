"""
Price + Weather Scheduler — UPDATED VERSION

Runs two jobs:
1. fetch_and_process_prices  — every 30 mins (AgMarket prices)
2. fetch_and_send_weather_alerts — every 30 mins (OpenWeatherMap alerts)
"""

import re
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime
from typing import List, Dict, Any, Optional

from app.config import settings
from app.utils.database import get_db

scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


async def fetch_and_process_prices():
    """
    Main scheduled job — runs every 30 minutes.

    Step 1: Get all unique crop+state combinations from active users
    Step 2: Fetch real prices from AgMarket API for those crops
    Step 3: Store prices in DB
    Step 4: Compare with previous prices and fire alerts if thresholds crossed
    """
    from app.services.agmarket_service import agmarket_service
    from app.services.alert_engine import alert_engine

    start_time = datetime.now()
    print(f"\n⏰ [{start_time.strftime('%H:%M:%S IST')}] Starting price fetch job...")

    user_crops = await _get_user_crop_preferences()

    if not user_crops:
        print("⚠️  No active user crop preferences found — nothing to fetch")
        return

    print(f"📋 Fetching prices for {len(user_crops)} unique crop+state combinations:")
    for crop in user_crops:
        print(f"   - {crop['commodity']} in {crop['state']}")

    total_stored = 0

    for crop_pref in user_crops:
        commodity = crop_pref.get("commodity")
        state = crop_pref.get("state")

        if not commodity or not state:
            continue

        try:
            stored = await agmarket_service.fetch_and_store(
                state=state,
                commodity=commodity,
            )
            total_stored += stored

            if stored == 0:
                print(f"  ⚠️  No new records for {commodity}/{state}")
                continue

            latest_records = await agmarket_service.get_latest_prices(
                commodity=commodity,
                state=state,
            )

            processed_markets = set()

            for record in latest_records:
                market = record.get("market")
                if not market:
                    continue

                market_key = (commodity.lower(), market.lower())
                if market_key in processed_markets:
                    continue
                processed_markets.add(market_key)

                previous_price = await _get_previous_price(
                    commodity=record["commodity"],
                    market=record["market"],
                    current_fetched_at=record.get("fetched_at"),
                )

                await alert_engine.process_price_update(
                    commodity=record["commodity"],
                    market=record["market"],
                    state=record["state"],
                    district=record.get("district", ""),
                    current_price=record["modal_price"],
                    previous_price=previous_price,
                )

        except Exception as e:
            print(f"❌ Error processing {commodity}/{state}: {e}")
            import traceback
            traceback.print_exc()

    elapsed = (datetime.now() - start_time).seconds
    print(f"✅ Price fetch complete. Stored {total_stored} records in {elapsed}s")


async def _get_user_crop_preferences() -> List[Dict[str, Any]]:
    db = get_db()

    pipeline = [
        {"$match": {"is_active": True}},
        {"$unwind": "$crops"},
        {"$match": {"crops.alert_enabled": True}},
        {
            "$group": {
                "_id": {
                    "commodity": {"$toLower": "$crops.commodity"},
                    "state": {"$toLower": "$crops.state"},
                },
                "commodity": {"$first": "$crops.commodity"},
                "state": {"$first": "$crops.state"},
            }
        },
    ]

    result = await db.users.aggregate(pipeline).to_list(length=100)

    crops = []
    for r in result:
        commodity = r.get("commodity")
        state = r.get("state")
        if commodity and state:
            crops.append({"commodity": commodity, "state": state})

    return crops


async def _get_previous_price(
    commodity: str,
    market: str,
    current_fetched_at: Optional[datetime],
) -> Optional[float]:
    db = get_db()

    query = {
        "commodity": {"$regex": f"^{re.escape(commodity)}$", "$options": "i"},
        "market": {"$regex": f"^{re.escape(market)}$", "$options": "i"},
    }

    if current_fetched_at:
        query["fetched_at"] = {"$lt": current_fetched_at}

    record = await db.prices.find_one(
        query,
        sort=[("fetched_at", -1)],
    )

    if record:
        return record.get("modal_price")
    return None


def start_scheduler():
    """Register jobs and start APScheduler."""

    # Job 1 — Price alerts
    scheduler.add_job(
        fetch_and_process_prices,
        trigger=IntervalTrigger(minutes=settings.PRICE_FETCH_INTERVAL_MINUTES),
        id="price_fetch",
        name="Fetch Mandi Prices from AgMarket",
        replace_existing=True,
        max_instances=1,
    )

    # Job 2 — Weather alerts
    scheduler.add_job(
        _run_weather_job,
        trigger=IntervalTrigger(minutes=settings.WEATHER_FETCH_INTERVAL_MINUTES),
        id="weather_fetch",
        name="Fetch Weather & Send Alerts",
        replace_existing=True,
        max_instances=1,
    )

    scheduler.start()
    print(
        f"🕐 Scheduler started — prices every {settings.PRICE_FETCH_INTERVAL_MINUTES} mins, "
        f"weather every {settings.WEATHER_FETCH_INTERVAL_MINUTES} mins"
    )


async def _run_weather_job():
    """Wrapper to import weather scheduler lazily."""
    from app.scheduler.weather_scheduler import fetch_and_send_weather_alerts
    await fetch_and_send_weather_alerts()


def stop_scheduler():
    """Stop the scheduler gracefully."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("🛑 Scheduler stopped")

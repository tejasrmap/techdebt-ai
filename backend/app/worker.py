"""
Dedicated background review worker process for TechDebt AI.
Can run as an independent replica or container alongside web API instances.
Protected with concurrency locking to prevent duplicate review execution.
"""
import time
import logging
import signal
import sys
from app.services.scheduler_service import start_scheduler, scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (worker) %(name)s: %(message)s"
)
logger = logging.getLogger("techdebt_worker")

def graceful_shutdown(signum, frame):
    logger.info("Received termination signal. Gracefully shutting down worker scheduler...")
    if scheduler.running:
        scheduler.shutdown(wait=True)
    sys.exit(0)

def main():
    logger.info("Starting TechDebt AI Dedicated Background Review Worker...")
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    start_scheduler()
    from app.services.scheduler_service import restore_all_scheduled_jobs
    scheduler.add_job(
        restore_all_scheduled_jobs,
        trigger="interval",
        seconds=30,
        id="worker_sync_schedules_from_db",
        replace_existing=True
    )
    logger.info("Worker scheduler operational with persistent schedule sync every 30s. Standing by for recurring review triggers.")

    # Keep worker thread alive
    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        graceful_shutdown(None, None)

if __name__ == "__main__":
    main()


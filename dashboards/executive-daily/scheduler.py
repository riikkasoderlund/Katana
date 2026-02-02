"""
Scheduler for Executive Daily Dashboard
Runs at 7 AM Helsinki time (Europe/Helsinki)
"""
import schedule
import time
from datetime import datetime
import pytz
import logging
import os
import sys

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'scheduler.log')),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('executive-dashboard-scheduler')

HELSINKI_TZ = pytz.timezone('Europe/Helsinki')


def get_helsinki_time() -> datetime:
    """Get current time in Helsinki timezone"""
    return datetime.now(HELSINKI_TZ)


def run_dashboard():
    """Execute the dashboard and handle any errors"""
    from dashboard import ExecutiveDashboard

    helsinki_now = get_helsinki_time()
    logger.info(f"Starting dashboard execution at {helsinki_now.strftime('%Y-%m-%d %H:%M:%S')} Helsinki time")

    try:
        dashboard = ExecutiveDashboard()
        report = dashboard.run(send_slack=True)
        logger.info(f"Dashboard completed successfully. Report date: {report['date']}")
        return True

    except Exception as e:
        logger.error(f"Dashboard execution failed: {str(e)}", exc_info=True)

        # Send error notification to Slack
        try:
            from connectors import SlackConnector
            slack = SlackConnector()
            slack.send_message(
                channel="@riikka",
                text=f":x: Executive Dashboard Failed\n\nError: {str(e)}\n\nTime: {helsinki_now.strftime('%Y-%m-%d %H:%M:%S')} Helsinki"
            )
        except Exception as slack_error:
            logger.error(f"Failed to send error notification: {str(slack_error)}")

        return False


def is_helsinki_7am() -> bool:
    """Check if it's currently 7 AM in Helsinki"""
    helsinki_now = get_helsinki_time()
    return helsinki_now.hour == 7 and helsinki_now.minute == 0


class HelsinkiScheduler:
    """
    Scheduler that runs jobs at specific Helsinki times.
    Handles DST transitions properly.
    """

    def __init__(self):
        self.last_run_date = None

    def should_run_now(self, target_hour: int = 7) -> bool:
        """Check if we should run the job now"""
        helsinki_now = get_helsinki_time()
        today = helsinki_now.date()

        # Only run once per day
        if self.last_run_date == today:
            return False

        # Check if it's the target hour (with 5-minute window)
        if helsinki_now.hour == target_hour and helsinki_now.minute < 5:
            return True

        return False

    def mark_run_complete(self):
        """Mark that we've run for today"""
        self.last_run_date = get_helsinki_time().date()


def start_scheduler():
    """Start the scheduler loop"""
    logger.info("Starting Executive Dashboard Scheduler")
    logger.info(f"Configured to run at 7:00 AM Helsinki time (Europe/Helsinki)")
    logger.info(f"Current Helsinki time: {get_helsinki_time().strftime('%Y-%m-%d %H:%M:%S')}")

    scheduler = HelsinkiScheduler()

    while True:
        try:
            if scheduler.should_run_now(target_hour=7):
                logger.info("Triggering scheduled dashboard run")
                success = run_dashboard()
                if success:
                    scheduler.mark_run_complete()
                else:
                    # Wait a bit and try again on failure
                    time.sleep(300)  # 5 minutes
                    continue

            # Check every minute
            time.sleep(60)

        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"Scheduler error: {str(e)}", exc_info=True)
            time.sleep(60)


def run_once():
    """Run the dashboard once immediately (for testing)"""
    logger.info("Running dashboard once (manual trigger)")
    return run_dashboard()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Executive Dashboard Scheduler')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--test', action='store_true', help='Generate test report without sending to Slack')
    args = parser.parse_args()

    if args.once:
        run_once()
    elif args.test:
        from dashboard import ExecutiveDashboard
        dashboard = ExecutiveDashboard()
        report = dashboard.run(send_slack=False)
        print("Test report generated (not sent to Slack)")
    else:
        start_scheduler()

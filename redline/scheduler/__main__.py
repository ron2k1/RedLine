"""Entry point for ``python -m redline.scheduler``."""

import logging

from redline.scheduler.polling import run_scheduler

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run_scheduler()

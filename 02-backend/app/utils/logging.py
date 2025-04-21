import logging
import os

def configure_logging(level: str | None = None) -> None:
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=level,
        format="%(levelname)s: %(message)s"
    )

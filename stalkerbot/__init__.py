import logging
from logging.config import dictConfig

dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "fmt": "%(asctime)s %(levelname)-8s %(name)-15s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        "handlers": {
            "default": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "filename": "stalkerbot.log",
                "maxBytes": 2048,
                "backupCount": 0,
            }
        },
        "disable_existing_loggers": True,
    }
)

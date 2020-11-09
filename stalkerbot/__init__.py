import logging
from logging.config import dictConfig
import keyring
import os

dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "fmt": "%(asctime)s %(levelname)-8s %(name)-15s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
        # "handlers": {
        #     "default": {
        #         "class": "logging.handlers.RotatingFileHandler",
        #         "formatter": "default",
        #         "filename": "stalkerbot.log",
        #         "maxBytes": 2048,
        #         "backupCount": 0,
        #     }
        # },
        # "disable_existing_loggers": True,
    }
)

root = logging.getLogger()
file_handler = logging.handlers.RotatingFileHandler('stalkerbot.log')
root.addHandler(file_handler)

try:
    with open('token') as fp:
        token = fp.read().strip()
        if len(token) > 0:
            os.environ["GITHUB_TOKEN"] = token
except Exception:
    pass
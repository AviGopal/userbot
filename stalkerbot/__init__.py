import logging
import logging
from logging.config import dictConfig
import keyring
import os

logging.getLogger().config = dictConfig(
    {
        "version": 1,
        "formatters": {
            "default": {
                "fmt": "%(asctime)s %(levelname)-8s %(name)-15s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            }
        },
    }
)

root = logging.getLogger()
root.setLevel(10)
file_handler = logging.handlers.RotatingFileHandler("stalkerbot.log")
root.addHandler(file_handler)

try:
    with open("token") as fp:
        token = fp.read().strip()
        if len(token) > 0:
            os.environ["GITHUB_TOKEN"] = token
except Exception:
    pass

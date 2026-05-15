import json
import logging
import logging.handlers
import os
import sys
import traceback
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
        }

        if hasattr(record, "trace_id"):
            log_data["trace_id"] = record.trace_id
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data

        if record.exc_info and record.exc_info[0]:
            log_data["exc_type"] = record.exc_info[0].__name__
            log_data["exc_msg"] = str(record.exc_info[1])
            log_data["exc_tb"] = traceback.format_exception(*record.exc_info)[-3:]

        return json.dumps(log_data, ensure_ascii=False)


def _console_formatter():
    return logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


logger = logging.getLogger("fbspider")

if not logger.handlers:
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_console_formatter())
    console.setLevel(logging.INFO)

    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "app.json.log"),
        maxBytes=20 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    file_handler.setFormatter(JSONFormatter())
    file_handler.setLevel(logging.DEBUG)

    error_handler = logging.handlers.RotatingFileHandler(
        os.path.join(log_dir, "error.json.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_handler.setFormatter(JSONFormatter())
    error_handler.setLevel(logging.ERROR)

    logger.addHandler(console)
    logger.addHandler(file_handler)
    logger.addHandler(error_handler)
    logger.setLevel(logging.DEBUG)

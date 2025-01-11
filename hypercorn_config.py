# hypercorn_config.py
import json
from hypercorn.logging import AccessLogAtoms
from datetime import datetime

class JSONAccessFormatter:
    def __call__(self, atoms: AccessLogAtoms) -> str:
        log_dict = {
            "timestamp": datetime.utcnow().isoformat(),
            "event": "request",
            "method": atoms["method"],
            "path": atoms["path"],
            "status": atoms["status"],
            "host": atoms["host"],
            "request_time": atoms["request_time"],
        }
        return json.dumps(log_dict)

logconfig = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "hypercorn_config.JSONAccessFormatter",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        }
    },
    "loggers": {
        "hypercorn.access": {
            "handlers": ["console"],
            "level": "INFO",
        },
        "hypercorn.error": {
            "handlers": ["console"],
            "level": "INFO",
        },
    }
}
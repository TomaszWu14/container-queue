"""Format logów z request-id i opcjonalny trwały plik z rotacją (OBS-007).

stdout (`docker logs`) ginie przy każdym Redeploy — `LOG_FILE=/data/logs/app.log`
(wolumen) dopisuje te same linie do pliku, który przeżywa redeploy.
"""
import contextvars
import logging
import logging.handlers
import os

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s rid=%(rid)s: %(message)s"
# root = logi aplikacji; uvicorn/uvicorn.access nie propagują do roota (dictConfig uvicorna)
FILE_LOGGERS = ("", "uvicorn", "uvicorn.access")

# ustawiany w RequestIDMiddleware; poza żądaniem (pętle tła, start) = "-"
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.rid = request_id_var.get()
        return True


def attach_file_handler(path: str, *filters: logging.Filter,
                        max_bytes: int = 10 * 1024 * 1024, backups: int = 10):
    """Plik z rotacją (domyślnie 10 × 10 MB) z tym samym formatem i filtrami co stdout."""
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=max_bytes,
                                                   backupCount=backups, encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    for f in (RequestIdFilter(), *filters):
        handler.addFilter(f)
    for name in FILE_LOGGERS:
        logging.getLogger(name).addHandler(handler)
    return handler

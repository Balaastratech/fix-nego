import logging
import logging.config
import os
from asgi_correlation_id.context import correlation_id
from pythonjsonlogger import jsonlogger


# ─── Log file path ────────────────────────────────────────────────────────────
_LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
_BACKEND_LOG_FILE = os.path.join(_LOG_DIR, "backend.jsonl")


class CorrelationIdFilter(logging.Filter):
    def filter(self, record):
        record.correlation_id = correlation_id.get()
        return True


# ─── Terminal formatter: concise human-readable ───────────────────────────────
class TerminalFormatter(logging.Formatter):
    """
    Clean terminal output — shows only the information needed to understand
    what is happening without JSON noise or repeated fields.

    Format: HH:MM:SS LEVEL [module_short] message
    """

    _SKIP_PREFIXES = (
        "AFC is enabled",
        "Starting receive()",
        "Validating message:",
        "DBG: GeminiClient Response #",
        "[STT] OUTGOING recognizer string",
        "[STT] Deepgram request prepared",
        "Companion PCM arrived",      # too frequent — tracked by finalized log
        "Companion audio capture started",
        "Routing message: CAPTURE_HEALTH",
        "Routing message: MEETING_BINDING",
        "Routing message: SCREEN_FRAME",
        "Routing message: VISION_FRAME",
        "[Vision] Pro analysis ok",
        "[Vision] Failed to parse",
        "connection closed",
        "connection opened",
        "HTTP Request:",
        "Intel injection successful",
        "Reusing pre-connected",
        "Starting receive() for turn",
        "Pre-query intel brief sent",
        "Flushing coalesced intel",
        "Injecting coalesced intel",
        "Copilot activated but no context",
        "Cleared pre-activation critical",
        "[DGStream] Recv error",
    )

    _MODULE_SHORT = {
        "app.services.negotiation_engine": "engine",
        "app.services.gemini_client":      "gemini",
        "app.services.stt_service":        "stt",
        "app.services.listener_agent":     "listener",
        "app.services.companion_runtime":  "companion",
        "app.services.deepgram_stream":    "dgstream",
        "app.api.websocket":               "ws",
        "app.services.session_store":      "store",
        "httpx":                           "httpx",
        "google_genai.models":             "genai",
    }

    _LEVEL_COLORS = {
        "DEBUG":    "\033[90m",   # dark gray
        "INFO":     "\033[0m",    # default
        "WARNING":  "\033[33m",   # yellow
        "ERROR":    "\033[31m",   # red
        "CRITICAL": "\033[35m",   # magenta
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()

        # Drop extremely high-frequency or low-value messages
        for prefix in self._SKIP_PREFIXES:
            if msg.startswith(prefix) or prefix in msg:
                return ""  # empty → handler won't emit

        mod = self._MODULE_SHORT.get(record.name, record.name.split(".")[-1])
        level = record.levelname
        color = self._LEVEL_COLORS.get(level, "")
        ts = self.formatTime(record, "%H:%M:%S")
        return f"{color}{ts} {level[0]} [{mod}] {msg}{self._RESET}"


class _SkipEmptyFilter(logging.Filter):
    """Drop records whose formatted message is empty (used by TerminalFormatter)."""
    def __init__(self, formatter):
        super().__init__()
        self._fmt = formatter

    def filter(self, record):
        return bool(self._fmt.format(record))


def get_logging_config(log_level: str = "INFO"):
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "correlation_id": {
                "()": CorrelationIdFilter,
            },
        },
        "formatters": {
            "json_file": {
                "()": jsonlogger.JsonFormatter,
                "format": "%(asctime)s %(levelname)s %(name)s %(correlation_id)s %(message)s",
            },
        },
        "handlers": {
            # File handler: full structured JSON, every log line
            "file": {
                "class": "logging.FileHandler",
                "filename": _BACKEND_LOG_FILE,
                "mode": "a",
                "encoding": "utf-8",
                "formatter": "json_file",
                "filters": ["correlation_id"],
                "level": "DEBUG",
            },
            # Console handler: clean human-readable, key events only
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json_file",   # replaced dynamically in setup_logging
                "filters": ["correlation_id"],
                "level": log_level,
            },
        },
        "loggers": {
            "frontend": {
                "handlers": ["console", "file"],
                "level": log_level,
                "propagate": False,
            },
        },
        "root": {
            "handlers": ["console", "file"],
            "level": log_level,
        },
    }


def setup_logging(log_level: str = "INFO"):
    config = get_logging_config(log_level)
    logging.config.dictConfig(config)

    # Replace the console handler's formatter with the clean terminal formatter
    root = logging.getLogger()
    terminal_fmt = TerminalFormatter()
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setFormatter(terminal_fmt)
            handler.addFilter(_SkipEmptyFilter(terminal_fmt))

    # Silence noisy third-party loggers in terminal (still written to file)
    for noisy in ("httpx", "google_genai.models", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

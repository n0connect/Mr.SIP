import logging
import os
import sys
from datetime import datetime

from src.core import theme

CONSOLE_FORMAT = "%(message)s"
FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

# Custom level for "a live target / valid extension was found" results.
# Sits between INFO and WARNING so it's a real, filterable log level instead
# of the old ad-hoc "[+]" string prefix buried inside .info() messages.
FOUND = 25
logging.addLevelName(FOUND, "FOUND")


def _found(self, message, *args, **kwargs):
    if self.isEnabledFor(FOUND):
        self._log(FOUND, message, args, **kwargs)


logging.Logger.found = _found

# levelno -> (short tag, color). Tags are padded to equal width in
# ColorFormatter so console output stays aligned regardless of level.
_LEVEL_STYLE = {
    logging.DEBUG: ("DEBUG", theme.MUTED),
    logging.INFO: ("INFO", theme.ACCENT),
    FOUND: ("FOUND", theme.SUCCESS),
    logging.WARNING: ("WARN", theme.WARNING),
    logging.ERROR: ("ERROR", theme.ERROR),
    logging.CRITICAL: ("CRIT", theme.CRITICAL),
}


class ColorFormatter(logging.Formatter):
    """Prefixes every console line with a colored '[ LEVEL ]' tag.

    Replaces the old convention of hardcoding ANSI color codes and ad-hoc
    "[!]"/"[+]" markers inline at each call site - callers now just log at
    the right level (.debug/.info/.found/.warning/.error) and this formatter
    is the single place that decides how that looks. Auto-disabled via
    theme.supports_color() (NO_COLOR, non-tty output).
    """

    def format(self, record):
        message = super().format(record)
        tag, color = _LEVEL_STYLE.get(record.levelno, (record.levelname, theme.ACCENT))
        prefix = theme.colorize(f"[ {tag:<5} ]", color)
        return "\n".join(f"{prefix} {line}" for line in message.split("\n"))


class StripAnsiFormatter(logging.Formatter):
    """Strips ANSI color codes before writing to the log file, so the on-disk
    log stays plain text (it's meant to double as pentest evidence/report
    material) while the console keeps its colored output untouched."""

    def format(self, record):
        message = super().format(record)
        return theme.strip_ansi(message)


class TqdmLoggingHandler(logging.Handler):
    """A logging handler that writes logs via tqdm.write to prevent progress bar corruption."""

    def emit(self, record):
        try:
            msg = self.format(record)
            from tqdm import tqdm
            tqdm.write(msg, file=sys.stdout)
            self.flush()
        except Exception:
            self.handleError(record)


def setup_logging(verbose: bool, log_dir: str = "logs") -> logging.Logger:
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # Log messages can echo back user-controlled strings (a target name, a
    # file path in an error message, ...) that may contain characters the
    # console can't encode - e.g. a lone surrogate from a CLI argument with
    # invalid-UTF-8 bytes (argv is decoded with errors="surrogateescape").
    # Without this, such a message crashes the stream's write() with
    # UnicodeEncodeError instead of printing a readable escaped fallback.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")

    console_handler = TqdmLoggingHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(ColorFormatter(CONSOLE_FORMAT))
    logger.addHandler(console_handler)

    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(log_dir, f"mrsip_{timestamp}.log")
    # Same rationale as the stdout.reconfigure() above - the log file must
    # not crash on a message containing characters invalid for its encoding.
    file_handler = logging.FileHandler(file_path, encoding="utf-8", errors="backslashreplace")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(StripAnsiFormatter(FILE_FORMAT))
    logger.addHandler(file_handler)

    logging.getLogger("scapy.runtime").setLevel(logging.ERROR)

    return logger

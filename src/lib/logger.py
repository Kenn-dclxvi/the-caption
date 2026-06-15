import logging
import logging.handlers
from typing import Final, Optional
from src.config.settings import LOG_FILE, LLM_TRACE_FILE

__BACKUP_COUNT: Final[int] = 30

def _build_rotating_logger(
    name: str,
    filename: str,
    *,
    level: int,
    include_stream: bool,
    file_formatter: logging.Formatter,
    stream_formatter: Optional[logging.Formatter] = None,
    stream_level: int = logging.INFO,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if logger.hasHandlers():
        return logger

    if include_stream:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(stream_level)
        stream_handler.setFormatter(stream_formatter or file_formatter)
        logger.addHandler(stream_handler)

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=filename,
        when='midnight',
        interval=1,
        backupCount=__BACKUP_COUNT,
        encoding='utf-8',
        delay=True
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    return logger

def setup_logger(name: str = __name__) -> logging.Logger:
    formatter = logging.Formatter("[%(asctime)s] [%(name)s] %(levelname)s: %(message)s")
    return _build_rotating_logger(
        name,
        LOG_FILE,
        level=logging.INFO,
        include_stream=True,
        file_formatter=formatter,
        stream_formatter=formatter,
    )

def setup_trace_logger() -> logging.Logger:
    formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
    return _build_rotating_logger(
        "llm_trace",
        LLM_TRACE_FILE,
        level=logging.DEBUG,
        include_stream=False,
        file_formatter=formatter,
    )

def setup_llm_logger(name: str = __name__) -> logging.Logger:
    stream_formatter = logging.Formatter("[%(asctime)s] [%(name)s] %(levelname)s: %(message)s")
    file_formatter = logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s")
    return _build_rotating_logger(
        name,
        LLM_TRACE_FILE,
        level=logging.DEBUG,
        include_stream=True,
        file_formatter=file_formatter,
        stream_formatter=stream_formatter,
    )

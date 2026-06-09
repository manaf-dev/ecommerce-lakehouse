"""Structured logging for Glue jobs.

Each adapter prefixes messages with [dataset][run_id] so CloudWatch log
streams are easy to grep per execution.
"""

import logging
from typing import Any


class DatasetAdapter(logging.LoggerAdapter):
    """Prepend [dataset][run_id] to every log message."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        dataset = self.extra.get("dataset", "")
        run_id = self.extra.get("run_id", "")
        parts = [p for p in (dataset, run_id) if p]
        prefix = "".join(f"[{p}]" for p in parts)
        return (f"{prefix} {msg}" if prefix else msg), kwargs


def get_logger(
    name: str,
    dataset: str = "",
    run_id: str = "",
) -> DatasetAdapter:
    """Return a DatasetAdapter logger for structured Glue/CloudWatch logging.

    Args:
        name: Logger name (typically __name__ of the calling module).
        dataset: Dataset identifier embedded in every log line.
        run_id: Step Functions execution name embedded in every log line.

    Returns:
        A DatasetAdapter that wraps a standard logging.Logger.
    """
    if not logging.root.handlers:
        logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(name)
    return DatasetAdapter(logger, {"dataset": dataset, "run_id": run_id})

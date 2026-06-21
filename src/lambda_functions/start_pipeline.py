import json
import logging
import os
import re
from typing import Any

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_MONTH_ABBR = {
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}


def _derive_order_month(keys: list[str]) -> str:
    """Derive YYYY-MM from filenames such as orders_apr_2025.xlsx."""
    for key in keys:
        match = re.search(r"_([a-z]{3})_(\d{4})", key.lower())
        if match:
            month = _MONTH_ABBR.get(match.group(1))
            if month:
                return f"{match.group(2)}-{month}"
        iso_match = re.search(r"(\d{4})-(\d{2})", key)
        if iso_match:
            return f"{iso_match.group(1)}-{iso_match.group(2)}"
    return "unknown"


def _extract_s3_events(records: list[dict[str, Any]]) -> tuple[str | None, list[str]]:
    bucket: str | None = None
    keys: list[str] = []

    for record in records:
        body = json.loads(record["body"])
        detail = body.get("detail", body)
        bucket = detail["bucket"]["name"]
        keys.append(detail["object"]["key"])

    return bucket, keys


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """Debounce S3 notifications and start one pipeline execution at a time."""
    sfn_arn = os.environ["STATE_MACHINE_ARN"]
    sfn = boto3.client("stepfunctions")

    running = sfn.list_executions(
        stateMachineArn=sfn_arn,
        statusFilter="RUNNING",
        maxResults=1,
    )
    if running.get("executions"):
        logger.info("Pipeline already running — skipping start")
        return {"started": False, "reason": "execution_in_progress"}

    bucket, keys = _extract_s3_events(event["Records"])
    if not bucket:
        return {"started": False, "reason": "no_bucket"}

    payload = {
        "bucket": bucket,
        "order_month": _derive_order_month(keys),
        "triggered_keys": keys,
    }

    response = sfn.start_execution(
        stateMachineArn=sfn_arn,
        input=json.dumps(payload),
    )
    logger.info("Started pipeline execution %s", response["executionArn"])
    return {"started": True, "executionArn": response["executionArn"], "input": payload}

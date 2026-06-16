"""
Fix stale delta.lastCommitTimestamp in the Glue Data Catalog.

The Glue crawler sets delta.lastCommitTimestamp to the Delta table's
metaData.createdTime (frozen at creation), never updating it on subsequent
crawls. Athena engine v3 uses this value as a cache key; a stale value means
Athena never invalidates its cached snapshot, causing DELTA_LAKE_INVALID_SCHEMA
errors for 20+ minutes after every crawl run.

This job runs immediately after the crawler finishes and sets
delta.lastCommitTimestamp to the current epoch ms, forcing Athena to re-read
the Delta log on its next query.
"""

import sys
import time
import boto3
from awsglue.utils import getResolvedOptions

args = getResolvedOptions(sys.argv, ["catalog_db", "tables"])
catalog_db = args["catalog_db"]
table_names = [t.strip() for t in args["tables"].split(",")]

glue = boto3.client("glue")
new_ts = str(int(time.time() * 1000))

failures = []
for table_name in table_names:
    try:
        resp = glue.get_table(DatabaseName=catalog_db, Name=table_name)
        tbl = resp["Table"]

        tbl["Parameters"]["delta.lastCommitTimestamp"] = new_ts
        sd_params = tbl.get("StorageDescriptor", {}).get("Parameters", {})
        if "delta.lastCommitTimestamp" in sd_params:
            sd_params["delta.lastCommitTimestamp"] = new_ts

        for field in (
            "DatabaseName", "CreateTime", "UpdateTime", "LastAccessTime",
            "CreatedBy", "IsRegisteredWithLakeFormation", "CatalogId",
            "VersionId", "IsMultiDialectView", "IsMaterializedView",
        ):
            tbl.pop(field, None)

        glue.update_table(DatabaseName=catalog_db, TableInput=tbl)
        print(f"Updated {table_name}: delta.lastCommitTimestamp = {new_ts}")
    except Exception as exc:
        print(f"ERROR: failed to update {table_name}: {exc}")
        failures.append((table_name, exc))

if failures:
    names = ", ".join(t for t, _ in failures)
    raise RuntimeError(f"Failed to update {len(failures)} table(s): {names}")

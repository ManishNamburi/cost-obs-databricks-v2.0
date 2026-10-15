# Databricks notebook source
# MAGIC %md
# MAGIC # 02c — Build gold
# MAGIC
# MAGIC Creates or refreshes warehouse gold tables and copies dashboard aggregates
# MAGIC into Lakebase. Fresh mode does a full rebuild. Migrate mode reuses existing
# MAGIC v1 materialized views (incremental) and still full-loads Lakebase.
# MAGIC
# MAGIC **Idempotent** — checks `setup_state.build_gold` before running.

# COMMAND ----------

import os
import sys

sys.path.insert(0, "/Workspace" + os.path.dirname(dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()).replace("/notebooks", "/python"))

from shared_setup_lib import build_gold

# COMMAND ----------

for _k in [
    "ENDPOINT_NAME",
    "DATABRICKS_WAREHOUSE_ID",
    "COST_OBS_CATALOG",
    "COST_OBS_SCHEMA",
    "DEPLOYMENT_MODE",
    "LOOKBACK_DAYS",
]:
    try:
        _v = dbutils.widgets.get(_k)
        if _v:
            os.environ[_k] = _v
    except Exception:
        pass

# COMMAND ----------

build_gold()

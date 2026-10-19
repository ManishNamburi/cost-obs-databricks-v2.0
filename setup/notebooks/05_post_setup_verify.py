# Databricks notebook source
# MAGIC %md
# MAGIC # 05 — Post-Setup Verification
# MAGIC
# MAGIC Runs smoke checks against Lakebase, system tables, and the app warehouse.
# MAGIC Writes the final `setup_complete` marker to `setup_state` on success.
# MAGIC
# MAGIC **Idempotent** — re-running re-validates and updates the marker timestamp.

# COMMAND ----------

import os
import sys

sys.path.insert(0, "/Workspace" + os.path.dirname(dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()).replace("/notebooks", "/python"))

from shared_setup_lib import verify

# COMMAND ----------

for _k in ["ENDPOINT_NAME", "DATABRICKS_WAREHOUSE_ID", "COST_OBS_CATALOG", "COST_OBS_SCHEMA", "APP_NAME"]:
    try:
        _v = dbutils.widgets.get(_k)
        if _v:
            os.environ[_k] = _v
    except Exception:
        pass

# COMMAND ----------

verify()

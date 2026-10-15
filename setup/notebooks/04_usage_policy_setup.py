# Databricks notebook source
# MAGIC %md
# MAGIC # 04 — Serverless Usage Policy Setup
# MAGIC
# MAGIC Creates or validates the serverless usage policy for cost attribution tagging.
# MAGIC Requires account-admin or workspace-admin with usage policy permissions.
# MAGIC
# MAGIC **Idempotent** — checks `setup_state.usage_policy` marker before running.

# COMMAND ----------

import os
import sys

sys.path.insert(0, "/Workspace" + os.path.dirname(dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()).replace("/notebooks", "/python"))

from shared_setup_lib import setup_usage_policy

# COMMAND ----------

for _k in ["ENDPOINT_NAME", "DATABRICKS_WAREHOUSE_ID", "COST_OBS_CATALOG", "COST_OBS_SCHEMA"]:
    try:
        _v = dbutils.widgets.get(_k)
        if _v:
            os.environ[_k] = _v
    except Exception:
        pass

# COMMAND ----------

setup_usage_policy()

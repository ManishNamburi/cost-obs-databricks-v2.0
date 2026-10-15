# Databricks notebook source
# MAGIC %md
# MAGIC # 01 — Validate Prerequisites
# MAGIC
# MAGIC Checks that all required environment variables, Unity Catalog permissions,
# MAGIC and SQL warehouse connectivity are in place before running setup.
# MAGIC
# MAGIC **Idempotent** — safe to re-run at any time.

# COMMAND ----------

import os
import sys

sys.path.insert(0, "/Workspace" + os.path.dirname(dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()).replace("/notebooks", "/python"))

from shared_setup_lib import validate

# COMMAND ----------

# Inject job base_parameters as env vars (App resource bindings are absent in job context)
for _k in ["ENDPOINT_NAME", "DATABRICKS_WAREHOUSE_ID", "COST_OBS_CATALOG", "COST_OBS_SCHEMA", "DEPLOYMENT_MODE"]:
    try:
        _v = dbutils.widgets.get(_k)
        if _v:
            os.environ[_k] = _v
    except Exception:
        pass

# COMMAND ----------

validate()

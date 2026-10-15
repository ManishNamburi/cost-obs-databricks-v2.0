# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Seed Genie Space
# MAGIC
# MAGIC Configures the Databricks Genie space with cost system tables and trusted assets.
# MAGIC Creates a `cost-obs` Genie space when `GENIE_SPACE_ID` is empty.
# MAGIC
# MAGIC **Idempotent** — checks `setup_state.seed_genie` marker before running.

# COMMAND ----------

import os
import sys

sys.path.insert(0, "/Workspace" + os.path.dirname(dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()).replace("/notebooks", "/python"))

from shared_setup_lib import seed_genie

# COMMAND ----------

for _k in ["ENDPOINT_NAME", "DATABRICKS_WAREHOUSE_ID", "COST_OBS_CATALOG", "COST_OBS_SCHEMA", "GENIE_SPACE_ID", "APP_NAME"]:
    try:
        _v = dbutils.widgets.get(_k)
        if _v:
            os.environ[_k] = _v
    except Exception:
        pass

# COMMAND ----------

seed_genie()

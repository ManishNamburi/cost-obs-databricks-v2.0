# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — Lakebase Bootstrap
# MAGIC
# MAGIC Creates the Lakebase schema, OAuth role, UC grants, ALTER DEFAULT PRIVILEGES,
# MAGIC and the `setup_state` idempotency table.
# MAGIC
# MAGIC **Idempotent** — uses `IF NOT EXISTS` and checks `setup_state` before each step.

# COMMAND ----------

import os
import sys

sys.path.insert(0, "/Workspace" + os.path.dirname(dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()).replace("/notebooks", "/python"))

from shared_setup_lib import bootstrap_lakebase

# COMMAND ----------

for _k in ["ENDPOINT_NAME", "DATABRICKS_WAREHOUSE_ID", "COST_OBS_CATALOG", "COST_OBS_SCHEMA", "APP_NAME"]:
    try:
        _v = dbutils.widgets.get(_k)
        if _v:
            os.environ[_k] = _v
    except Exception:
        pass

# COMMAND ----------

bootstrap_lakebase()

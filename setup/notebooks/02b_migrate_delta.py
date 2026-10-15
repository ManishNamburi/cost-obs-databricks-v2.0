# Databricks notebook source
# MAGIC %md
# MAGIC # 02b — Migrate Delta → Lakebase
# MAGIC
# MAGIC Migrates historical data from existing Delta tables into Lakebase.
# MAGIC Skipped automatically if no Delta source tables are found.
# MAGIC
# MAGIC **Idempotent** — checks `setup_state.migrate_delta` marker before running.

# COMMAND ----------

import os
import sys

sys.path.insert(0, "/Workspace" + os.path.dirname(dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()).replace("/notebooks", "/python"))

from migrate_delta_to_lakebase import migrate
from shared_setup_lib import detect_deployment_mode

# COMMAND ----------

for _k in ["ENDPOINT_NAME", "DATABRICKS_WAREHOUSE_ID", "COST_OBS_CATALOG", "COST_OBS_SCHEMA", "DEPLOYMENT_MODE"]:
    try:
        _v = dbutils.widgets.get(_k)
        if _v:
            os.environ[_k] = _v
    except Exception:
        pass

# COMMAND ----------

# Fresh installs have no 1.1 Delta state to migrate. Resolve the mode via an
# independent probe (the value set in the validate task's process does NOT
# cross to this separate notebook process), then skip cleanly so operators
# aren't confused by "source not found" logs on new deployments.
_mode = detect_deployment_mode()
if _mode == "fresh":
    print("[02b_migrate_delta] Deployment mode=fresh — skipping 1.1 -> 2.1 migration.")
else:
    migrate()

"""Contracts for the customer-facing fresh and upgrade DAB targets."""

from pathlib import Path

import yaml

BUNDLE = Path(__file__).resolve().parents[3] / "bundle"
FRESH = yaml.safe_load((BUNDLE / "targets" / "fresh.yml").read_text())["targets"]["fresh"]
UPGRADE = yaml.safe_load((BUNDLE / "targets" / "upgrade.yml").read_text())["targets"]["upgrade"]


def test_fresh_pins_clean_install_and_requires_customer_gold_names():
    vars_ = FRESH["variables"]
    assert vars_["deployment_mode"] == "fresh"
    assert vars_["app_name"] == "cost-observability"
    assert vars_["catalog"] == ""
    assert vars_["schema"] == ""
    assert vars_["warehouse_id"] == ""
    assert vars_["lakebase_project_name"] == "cost-obs-db"
    workspace = FRESH.get("workspace") or {}
    assert "host" not in workspace
    assert "${workspace.current_user.userName}" in workspace.get("root_path", "")


def test_upgrade_reuses_v1_gold_and_creates_new_lakebase():
    vars_ = UPGRADE["variables"]
    assert vars_["deployment_mode"] == "migrate"
    assert vars_["app_name"] == "cost-observability-v2"
    assert vars_["catalog"] == ""
    assert vars_["schema"] == ""
    assert vars_["warehouse_id"] == ""
    assert vars_["lakebase_project_name"] == "cost-obs-db-v2"
    assert vars_["lakebase_project_name"] != FRESH["variables"]["lakebase_project_name"]
    workspace = UPGRADE.get("workspace") or {}
    assert "host" not in workspace
    assert "${workspace.current_user.userName}" in workspace.get("root_path", "")


def test_customer_targets_do_not_put_variables_in_workspace_host():
    raw_fresh = (BUNDLE / "targets" / "fresh.yml").read_text()
    raw_upgrade = (BUNDLE / "targets" / "upgrade.yml").read_text()
    assert "${var.workspace_host}" not in raw_fresh
    assert "${var.workspace_host}" not in raw_upgrade

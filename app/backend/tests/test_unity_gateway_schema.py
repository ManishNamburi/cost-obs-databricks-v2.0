from unittest.mock import MagicMock, patch

from backend.unity_gateway import pick_usage_columns, usage_schema_label


def test_pick_usage_columns_prefers_unity_schema():
    rows = [
        {"col_name": "event_time"},
        {"col_name": "service_name"},
        {"col_name": "endpoint_name"},
        {"col_name": "destination_model"},
        {"col_name": "requester"},
        {"col_name": "input_tokens"},
        {"col_name": "output_tokens"},
        {"col_name": "status_code"},
        {"col_name": "service_type"},
    ]
    with patch("backend.unity_gateway.execute_query", return_value=rows):
        picked = pick_usage_columns("main.cost.ai_gateway")
        assert picked["event_ts"] == "event_time"
        assert picked["service"] == "service_name"
        assert picked["model"] == "destination_model"
        assert picked["requester"] == "requester"
        assert usage_schema_label("main.cost.ai_gateway") == "unity"


def test_pick_usage_columns_falls_back_to_legacy():
    rows = [
        {"col_name": "timestamp"},
        {"col_name": "route_name"},
        {"col_name": "model_name"},
        {"col_name": "client_user"},
        {"col_name": "input_token_count"},
        {"col_name": "output_token_count"},
        {"col_name": "total_token_count"},
        {"col_name": "request_duration_ms"},
        {"col_name": "http_status_code"},
    ]
    with patch("backend.unity_gateway.execute_query", return_value=rows):
        picked = pick_usage_columns("main.cost.ai_gateway")
        assert picked["event_ts"] == "timestamp"
        assert picked["service"] == "route_name"
        assert picked["model"] == "model_name"
        assert picked["requester"] == "client_user"
        assert picked["status_code"] == "http_status_code"
        assert usage_schema_label("main.cost.ai_gateway") == "legacy"


def test_list_genie_space_inventory_uses_sdk():
    space = MagicMock()
    space.space_id = "sp-1"
    space.title = "Cost Obs"
    space.description = ""
    space.warehouse_id = "wh-1"
    page = MagicMock()
    page.spaces = [space]
    conv = MagicMock()
    conv.conversations = [object(), object()]
    genie = MagicMock()
    genie.list_spaces.return_value = page
    genie.list_conversations.return_value = conv
    w = MagicMock()
    w.genie = genie
    with patch("backend.unity_gateway.get_workspace_client", return_value=w):
        from backend.unity_gateway import list_genie_space_inventory
        inv = list_genie_space_inventory("sp-1")
    assert inv["available"] is True
    assert inv["space_count"] == 1
    assert inv["spaces"][0]["configured"] is True
    genie.list_spaces.assert_called_once()
    genie.list_conversations.assert_called_once()

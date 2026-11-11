"""Unit tests for CLI shell and SessionRunnerBridge facade."""
import json
from pathlib import Path
import pytest

from src.conversation.adapters.facade.runner_bridge import SessionRunnerBridge
from src.conversation.adapters.cli.shell import CLISession


def test_session_runner_bridge():
    bridge = SessionRunnerBridge(":memory:")
    
    # 1. First turn: origin
    res1 = bridge.process_utterance("Đón tôi ở số 12 đường Giải Phóng")
    assert res1["status"] == "committed"
    assert "đến đâu" in res1["response"] or "đi đâu" in res1["response"]
    
    draft1 = bridge.get_draft()
    assert draft1["origin"] is not None
    assert "giải phóng" in draft1["origin"]["label"].lower()
    assert "12" in draft1["origin"]["label"]
    
    # 2. Second turn: destination
    res2 = bridge.process_utterance("Đi bến xe Giáp Bát")
    assert res2["status"] == "committed"
    draft2 = bridge.get_draft()
    assert draft2["destination"] is not None
    
    # 3. Reset
    bridge.reset_session()
    draft3 = bridge.get_draft()
    assert draft3["origin"] is None
    assert draft3["destination"] is None


def test_cli_session(tmp_path: Path):
    session = CLISession(":memory:")
    
    # 1. User turn
    session.execute_user_input("Cho tôi đi bờ hồ Hoàn Kiếm")
    assert session.latest_result is not None
    assert session.latest_result.status.value == "committed"
    
    # 2. Display functions should not crash
    session.display_state()
    session.display_history()
    session.display_trace()
    
    # 3. Export state
    export_file = tmp_path / "exported_state.json"
    session.export_state(str(export_file))
    assert export_file.exists()
    data = json.loads(export_file.read_text(encoding="utf-8"))
    assert "request_id" in data
    assert "draft" in data
    
    # 4. New request
    old_req = session.request_id
    session.new_request()
    assert session.request_id != old_req
    assert session.latest_result is None

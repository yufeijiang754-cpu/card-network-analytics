"""Smoke tests: each dashboard page runs end-to-end against the built warehouse without exceptions."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(not (ROOT / "warehouse/payments.duckdb").exists(),
                                reason="warehouse not built (run ./run_all.sh)")
sys.path.insert(0, str(ROOT / "dashboard"))

from streamlit.testing.v1 import AppTest  # noqa: E402


@pytest.mark.parametrize("page", ["network_performance.py", "data_quality_monitor.py"])
def test_page_renders(page):
    at = AppTest.from_file(str(ROOT / "dashboard" / page), default_timeout=120).run()
    assert not at.exception, [e.message for e in at.exception]
    assert len(at.metric) >= 5


def test_network_filters_change_kpis():
    at = AppTest.from_file(str(ROOT / "dashboard/network_performance.py"), default_timeout=120).run()
    before = at.metric[0].value
    at.multiselect[2].select("card_not_present").run()  # Channel filter
    assert not at.exception
    assert at.metric[0].value != before

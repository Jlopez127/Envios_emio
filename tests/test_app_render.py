"""Render de las 5 tabs del dashboard con AppTest (sin excepciones), en mock y excel."""

import importlib
import os

import pytest


def _run(env):
    from streamlit.testing.v1 import AppTest
    os.environ.update(env)
    import config
    importlib.reload(config)
    at = AppTest.from_file("app.py", default_timeout=60)
    at.run()
    return at


def test_render_mock_5_tabs():
    at = _run({"DATASOURCE_ASTRID": "mock", "DATASOURCE_DROPBOX": "mock",
               "EXCEL_DIRECTORIO_LOCAL": ""})
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.tabs) == 5


def test_render_excel_local_5_tabs():
    at = _run({"DATASOURCE_ASTRID": "excel", "EXCEL_DIRECTORIO_LOCAL": "tests/fixtures",
               "DATASOURCE_DROPBOX": "mock"})
    assert not at.exception, [e.value for e in at.exception]

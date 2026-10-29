"""Smoke-test the offline dashboard without calling external services."""
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


def test_offline_dashboard():
    with patch("road_network.ROAD_FILE", Path("cache/nonexistent-test-road.graphml")), \
         patch("road_network.COORDINATES", Path("cache/nonexistent-test-coordinates.json")):
        app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=180).run()
        assert not app.exception
        assert len(app.tabs) == 0
        assert app.selectbox[0].options == [
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        app.button[0].click().run()
        assert not app.exception
        assert any('Road routes are unavailable' in x.value for x in app.warning)


def test_real_cached_plan():
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / 'app.py', default_timeout=180).run()
    app.button[0].click().run()
    assert not app.exception
    assert not app.warning
    assert any(x.label == 'Buses needed' for x in app.metric)
    assert any(x.label == 'Passengers collected' for x in app.metric)
    assert app.number_input[0].value == 100
    app.number_input[1].set_value(0)
    app.button[0].click().run()
    assert not app.exception
    assert next(x.value for x in app.metric if x.label == 'Passengers collected') == '0'
    app.selectbox[3].set_value(app.selectbox[2].value)
    app.button[0].click().run()
    assert not app.exception
    assert any('two different stations' in x.value for x in app.error)

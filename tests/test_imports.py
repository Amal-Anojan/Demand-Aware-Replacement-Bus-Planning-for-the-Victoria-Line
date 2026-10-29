"""Verify the dashboard's project imports in a clean Python interpreter."""
import subprocess
import sys
from config import ROOT


def test_dashboard_imports():
    code = '''
from bus_allocation import demand_aware_allocation, fleet_needed
from data_loader import load_data, source_signature, interval_columns
from railway_graph import build_graph, close_section
from demand_estimator import estimate_demand
from road_network import prepare_roads
from bus_routing import replacement_routes, cycle_times
from simulation import simulate
from dashboard_views import network_map, COLORS
from streamlit_folium import st_folium
assert callable(fleet_needed)
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT,
                            capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr

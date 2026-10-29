import pytest
from data_loader import load_data
from railway_graph import build_graph


@pytest.fixture(scope="session")
def data():
    return load_data()


@pytest.fixture(scope="session")
def graph(data):
    return build_graph(data)

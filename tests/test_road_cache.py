import networkx as nx
import pytest
from config import STATIONS
from road_network import validate_road_graph, configure_osmnx, prepare_roads


def sample_graph():
    graph = nx.MultiDiGraph(crs='EPSG:4326')
    for i in range(16):
        graph.add_node(i, x=-.1 + i * .001, y=51.5)
        if i:
            graph.add_edge(i-1, i, length=100., speed_kph=36., travel_time=10.)
            graph.add_edge(i, i-1, length=120., speed_kph=36., travel_time=12.)
    return graph


def test_graphml_roundtrip(tmp_path):
    ox = configure_osmnx()
    path = tmp_path / 'test.graphml'
    ox.save_graphml(sample_graph(), path)
    graph = ox.load_graphml(path)
    report = validate_road_graph(graph, {s: {'node': i} for i, s in enumerate(STATIONS)})
    assert report == {'nodes': 16, 'edges': 30, 'directed_station_pairs': 240}


@pytest.mark.parametrize('field,value', [('length', -1), ('travel_time', float('nan')), ('speed_kph', 0), ('travel_time', 999)])
def test_bad_weights(field, value):
    graph = sample_graph()
    graph[0][1][0][field] = value
    with pytest.raises(ValueError):
        validate_road_graph(graph)


def test_disconnected_station():
    graph = sample_graph()
    graph.remove_edge(1, 0)
    with pytest.raises(ValueError, match='No directed road route'):
        validate_road_graph(graph, {s: {'node': i} for i, s in enumerate(STATIONS)})


def test_missing_cache_does_not_download(tmp_path, monkeypatch):
    import road_network
    monkeypatch.setattr(road_network, 'ROAD_FILE', tmp_path / 'absent.graphml')
    monkeypatch.setattr(road_network.requests, 'get', lambda *a, **k: pytest.fail('Unexpected network request'))
    with pytest.raises(FileNotFoundError, match='download_roads.py'):
        prepare_roads(allow_download=False)

import networkx as nx
import pytest
from config import STATIONS, DAY_SOURCES
from data_loader import interval_columns, link_row, time_window
from railway_graph import close_section
from demand_estimator import estimate_demand, continuation_estimates


def test_five_workbooks_and_seven_days(data):
    assert set(data) == {"MON", "TWT", "FRI", "SAT", "SUN"}
    assert len(DAY_SOURCES) == 7
    assert {DAY_SOURCES[d] for d in ("Tuesday", "Wednesday", "Thursday")} == {"TWT"}
    for tables in data.values():
        for frame in tables.values():
            assert len(interval_columns(frame.columns)) == 96


def test_graph(graph):
    assert type(graph) is nx.DiGraph
    assert len(graph) == 16 and graph.number_of_edges() == 30
    assert nx.shortest_path(graph, STATIONS[0], STATIONS[-1]) == list(STATIONS)
    attrs = graph["Green Park"]["Oxford Circus"]
    assert attrs["direction"] == "NB" and not attrs["disrupted"]
    assert attrs["train_frequency"]["Tuesday"]["0830-0845"] >= 0
    assert attrs["passenger_load"]["Tuesday"]["0830-0845"] == pytest.approx(4453.359190)


@pytest.mark.parametrize("a,b,removed,components", [
    ("Green Park", "Oxford Circus", 2, 2),
    ("Warren Street", "Victoria LU", 6, 4),
    (STATIONS[0], STATIONS[-1], 30, 16),
])
def test_closure(graph, a, b, removed, components):
    closure = close_section(graph, a, b)
    assert len(closure.removed) == removed
    assert closure.graph.number_of_edges() == 30 - removed
    assert len(closure.components) == components
    assert not nx.has_path(closure.graph, a, b)
    assert graph.number_of_edges() == 30
    assert all(not attrs["disrupted"] for _, _, attrs in graph.edges(data=True))
    assert closure.connections["SB"] == closure.connections["NB"][::-1]


@pytest.mark.parametrize("a,b", [("bad", "Green Park"), ("Green Park", "Green Park")])
def test_invalid_boundary(graph, a, b):
    with pytest.raises(ValueError):
        close_section(graph, a, b)


@pytest.mark.parametrize("day", ["Tuesday", "Wednesday", "Thursday"])
def test_known_demands(data, graph, day):
    closure = close_section(graph, "Green Park", "Oxford Circus")
    demand, _ = estimate_demand(data, closure, day, "0830-0845", 15, 1, 1)
    values = demand.set_index("direction").potential_demand
    assert values.NB == pytest.approx(4453.359190, abs=1e-5)
    assert values.SB == pytest.approx(4113.454175, abs=1e-5)
    assert values.sum() == pytest.approx(8566.813365, abs=1e-5)
    demand, _ = estimate_demand(data, closure, day, "0800-0815", 120)
    sums = demand.groupby("direction").potential_demand.sum()
    assert sums.NB == pytest.approx(29738.37, abs=.01)
    assert sums.SB == pytest.approx(27483.36, abs=.01)
    assert sums.sum() == pytest.approx(57221.73, abs=.01)


def test_boundary_proxy_not_sum(data, graph):
    closure = close_section(graph, "Victoria LU", "Warren Street")
    demand, detail = estimate_demand(data, closure, "Tuesday", "0830-0845", 15, .4, .6)
    nb = demand[demand.direction == "NB"].iloc[0]
    sb = demand[demand.direction == "SB"].iloc[0]
    assert nb.potential_demand == link_row(data, "Tuesday", "Link_Loads", "Victoria LU", "Green Park")["0830-0845"]
    assert sb.potential_demand == link_row(data, "Tuesday", "Link_Loads", "Warren Street", "Oxford Circus")["0830-0845"]
    assert nb.bus_demand == pytest.approx(nb.potential_demand * .4)
    assert len(detail) == 6
    assert demand.potential_demand.sum() < detail.load.sum()


def test_midnight_and_service_day_rollover(data):
    window = time_window(data, "Friday", "2345-0000", 30)
    assert window[1]["interval"] == "0000-0015" and window[1]["day"] == "Friday"
    window = time_window(data, "Sunday", "0445-0500", 30)
    assert window[1]["interval"] == "0500-0515" and window[1]["day"] == "Monday"


def test_zero_frequency_retains_source_load(data, graph):
    closure = close_section(graph, "Green Park", "Oxford Circus")
    demand, _ = estimate_demand(data, closure, "Monday", "0300-0315", 15)
    assert (demand.scheduled_trains == 0).all()
    assert demand.passengers_per_train.isna().all()
    assert (demand.service_note == "No scheduled service").all()
    assert (demand.bus_demand == demand.potential_demand * .5).all()


def test_continuation(data):
    frame = continuation_estimates(data, "Tuesday", "0830-0845")
    assert len(frame) == 28
    assert (frame.continuing_estimate >= 0).all()

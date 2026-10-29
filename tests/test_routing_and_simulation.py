import networkx as nx
import pandas as pd
import pytest
from bus_routing import shortest_route
from bus_allocation import equal_allocation, demand_aware_allocation, capacity_requirements
from simulation import simulate


def test_dijkstra_directed_and_parallel():
    graph = nx.MultiDiGraph()
    for n in range(3):
        graph.add_node(n, x=float(n), y=51.5)
    graph.add_edge(0, 1, length=100, travel_time=100)
    graph.add_edge(0, 1, length=200, travel_time=20)
    graph.add_edge(1, 2, length=100, travel_time=20)
    graph.add_edge(0, 2, length=100, travel_time=90)
    graph.add_edge(2, 0, length=500, travel_time=120)
    nb = shortest_route(graph, 0, 2, 1.5)
    sb = shortest_route(graph, 2, 0, 1.5)
    assert nb.nodes == [0, 1, 2] and sb.nodes == [2, 0]
    assert nb.distance_km == .3 and nb.minutes == 1
    assert sb.minutes == 3
    graph.add_edge(1, 0, length=10)
    with pytest.raises(ValueError):
        shortest_route(graph, 0, 2)


def demands(nb=(180, 180, 180, 180), sb=(20, 20, 20, 20)):
    return pd.DataFrame([{"minute": i * 15, "direction": d, "bus_demand": q}
                         for d, values in [("NB", nb), ("SB", sb)] for i, q in enumerate(values)])


def test_capacity_cycles_conservation_and_wait():
    result = simulate(demands(), {"NB": 2, "SB": 1}, 50, {"NB": 22.5, "SB": 22.5}, 60)
    for row in result.summary.itertuples():
        assert row.arrivals == pytest.approx(row.transported + row.waiting)
        assert 0 <= row.fleet_busy_percent <= 100
        assert 0 <= row.seat_utilization_percent <= 100
    assert (result.trips.passengers <= 50).all()
    for _, trips in result.trips.groupby("vehicle"):
        assert all(b >= a - 1e-8 for a, b in zip(trips.ready_again, trips.boarding_start.iloc[1:]))
    for _, rows in result.queues.groupby("direction"):
        assert (rows.arrivals - rows.transported - rows.waiting).abs().max() < 1e-7
    # 100 at t=0, one capacity-50 vehicle, returns t=20 -> half wait 20 minutes.
    result = simulate(demands((100,), (0,)), {"NB": 1, "SB": 0}, 50, {"NB": 20, "SB": 20}, 30)
    row = result.summary.iloc[0]
    assert row.mean_wait_boarded == 10
    assert row.queue_person_minutes == 1000


def test_no_fleet_fractional_and_horizon():
    frame = demands((10.5,), (3.25,))
    result = simulate(frame, {"NB": 0, "SB": 0}, 50, {"NB": 20, "SB": 20}, 15)
    assert result.summary.waiting.sum() == 13.75
    assert result.trips.empty
    assert result.summary.queue_person_minutes.sum() == 13.75 * 15
    result = simulate(demands((100,), (0,)), {"NB": 1, "SB": 0}, 50, {"NB": 15, "SB": 15}, 15)
    assert result.summary.departures.sum() == 1  # no dispatch at horizon


def test_allocation_search():
    frame = demands()
    cycles = {"NB": 30, "SB": 30}
    assert equal_allocation(5) == {"NB": 3, "SB": 2}
    best, scores = demand_aware_allocation(frame, 6, 50, cycles, 60)
    assert sum(best.values()) == 6 and len(scores) == 7
    baseline = simulate(frame, equal_allocation(6), 50, cycles, 60)
    improved = simulate(frame, best, 50, cycles, 60)
    assert improved.summary.waiting.sum() <= baseline.summary.waiting.sum()
    assert improved.summary.waiting.sum() == scores.waiting.min()
    required = capacity_requirements(frame, 50, cycles)
    assert required.iloc[0].required_departures == 4
    assert required.iloc[0].steady_state_vehicles == 8


def test_completion_and_in_transit():
    result = simulate(demands((40,), (0,)), {"NB": 1, "SB": 0}, 50,
                      {"NB": 40, "SB": 40}, 15, {"NB": 20, "SB": 20}, 2, 1)
    assert result.summary.iloc[0].transported == 40
    assert result.summary.iloc[0].completed == 0
    assert result.summary.iloc[0].in_transit == 40

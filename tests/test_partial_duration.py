import pytest
from railway_graph import close_section
from demand_estimator import estimate_demand
from bus_allocation import fleet_needed
from simulation import simulate


def test_100_minutes(data, graph):
    closure = close_section(graph, "Green Park", "Oxford Circus")
    partial, _ = estimate_demand(data, closure, "Tuesday", "0830-0845", 100)
    full, _ = estimate_demand(data, closure, "Tuesday", "0830-0845", 105)
    assert partial.minute.max() == 90
    assert len(partial) == 14
    for d in ("NB", "SB"):
        p = partial[partial.direction == d].iloc[-1]
        f = full[full.direction == d].iloc[-1]
        assert p.interval_minutes == 10
        assert p.bus_demand == pytest.approx(f.bus_demand * 10 / 15)
        assert p.passengers_per_train == pytest.approx(f.passengers_per_train)
    cycles = {"NB": 20, "SB": 20}
    needed = fleet_needed(partial, 80, cycles, 100)
    result = simulate(partial, needed, 80, cycles, 100)
    assert result.summary.waiting.sum() == pytest.approx(0, abs=1e-6)
    for d in ("NB", "SB"):
        less = dict(needed)
        less[d] -= 1
        result = simulate(partial, less, 80, cycles, 100)
        assert result.summary.set_index("direction").loc[d, "waiting"] > 0

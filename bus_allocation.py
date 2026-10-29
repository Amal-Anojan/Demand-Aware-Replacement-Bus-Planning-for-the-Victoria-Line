"""Transparent fleet split comparison under dedicated directional operation."""
import math
import pandas as pd
from simulation import simulate


def equal_allocation(fleet):
    if fleet < 0 or int(fleet) != fleet:
        raise ValueError("Fleet must be a non-negative integer")
    return {"NB": (fleet + 1) // 2, "SB": fleet // 2}


def demand_aware_allocation(demand, fleet, capacity, cycles, duration):
    """Exhaustive finite search of N+1 static splits; no global scheduling claim.

    Lexicographic objective: minimize final waiting passengers, then queue
    person-minutes, then distance from equal split, then prefer NB on ties.
    """
    baseline = equal_allocation(fleet)
    candidates = []
    for north in range(fleet + 1):
        allocation = {"NB": north, "SB": fleet - north}
        result = simulate(demand, allocation, capacity, cycles, duration)
        candidates.append({"NB": north, "SB": fleet - north,
                           "waiting": float(result.summary.waiting.sum()),
                           "queue_person_minutes": float(result.summary.queue_person_minutes.sum())})
    best = min(candidates, key=lambda x: (round(x["waiting"], 7), round(x["queue_person_minutes"], 7),
                                         abs(x["NB"] - baseline["NB"]), -x["NB"]))
    return {"NB": best["NB"], "SB": best["SB"]}, pd.DataFrame(candidates)


def capacity_requirements(demand, capacity, cycles):
    if capacity <= 0:
        raise ValueError("Capacity must be positive")
    result = demand.copy()
    result["required_departures"] = result.bus_demand.map(lambda q: math.ceil(q / capacity))
    result["steady_state_vehicles"] = result.apply(
        lambda r: math.ceil(r.bus_demand / capacity * cycles[r.direction] / r.get("interval_minutes", 15)), axis=1)
    return result


def fleet_needed(demand, capacity, cycles, duration):
    """Minimum dedicated fleet per direction to board all arrivals before horizon."""
    answer = {}
    for direction in ("NB", "SB"):
        low = 0
        high = sum(math.ceil(q / capacity) for q in demand.loc[demand.direction == direction, "bus_demand"])
        while low < high:
            mid = (low + high) // 2
            allocation = {"NB": 0, "SB": 0}
            allocation[direction] = mid
            outcome = simulate(demand, allocation, capacity, cycles, duration)
            waiting = outcome.summary.set_index("direction").loc[direction, "waiting"]
            if waiting <= 1e-7:
                high = mid
            else:
                low = mid + 1
        answer[direction] = low
    return answer

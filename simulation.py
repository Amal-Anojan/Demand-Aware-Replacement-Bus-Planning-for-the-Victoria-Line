"""Deterministic FIFO fluid queues and event-driven vehicle availability."""
from collections import deque
from dataclasses import dataclass
import heapq
import math
import pandas as pd


@dataclass
class SimulationResult:
    summary: pd.DataFrame
    queues: pd.DataFrame
    trips: pd.DataFrame


def simulate(demand, allocation, capacity, cycles, duration, outbound=None, boarding=0, alighting=0):
    if capacity <= 0 or int(capacity) != capacity or duration <= 0:
        raise ValueError("Positive integer capacity and positive duration required")
    if any(not math.isfinite(float(x)) or x <= 0 for x in cycles.values()):
        raise ValueError("Positive finite cycle times required")
    if any(int(n) != n or n < 0 for n in allocation.values()):
        raise ValueError("Fleet counts must be non-negative integers")
    if not set(demand.direction).issubset({"NB", "SB"}):
        raise ValueError("Unknown direction")
    if demand[["minute", "bus_demand"]].isna().any().any() or (demand.bus_demand < 0).any():
        raise ValueError("Demand must be finite and non-negative")
    if not all(math.isfinite(float(v)) for v in demand.bus_demand):
        raise ValueError("Demand must be finite")
    if (demand.minute < 0).any() or (demand.minute >= duration).any():
        raise ValueError("Arrival times must lie inside the simulation horizon")
    summaries, traces, trips = [], [], []
    for direction in ("NB", "SB"):
        n = allocation[direction]
        cycle = cycles[direction]
        queue = deque()
        # heap entries: minute, event kind (arrivals before vehicle returns), payload.
        events = [(float(r.minute), 0, float(r.bus_demand))
                  for r in demand[demand.direction == direction].itertuples()]
        heapq.heapify(events)
        available = list(range(n))
        arrived = served = queue_size = queue_area = wait_sum = busy = completed = 0.0
        last = 0.0
        departures = 0
        while events:
            now = events[0][0]
            if now >= duration:
                break
            queue_area += queue_size * (now - last)
            last = now
            while events and abs(events[0][0] - now) < 1e-9:
                _, kind, payload = heapq.heappop(events)
                if kind == 0:
                    arrived += payload
                    if payload > 0:
                        queue.append([now, payload])
                        queue_size += payload
                else:
                    heapq.heappush(available, int(payload))
            while available and queue_size > 1e-8:
                vehicle = heapq.heappop(available)
                boarded = min(float(capacity), queue_size)
                remaining = boarded
                while remaining > 1e-8:
                    arrival, count = queue[0]
                    take = min(count, remaining)
                    wait_sum += take * (now - arrival)
                    remaining -= take
                    queue[0][1] -= take
                    if queue[0][1] <= 1e-8:
                        queue.popleft()
                queue_size = max(0, queue_size - boarded)
                served += boarded
                departures += 1
                ready = now + cycle
                journey = outbound[direction] if outbound else cycle
                delivered_at = now + boarding + journey + alighting
                if delivered_at <= duration:
                    completed += boarded
                busy += min(cycle, duration - now)
                trips.append({"direction": direction, "vehicle": f"{direction}-{vehicle + 1}",
                              "boarding_start": now, "departure": now + boarding,
                              "delivered_at": delivered_at, "ready_again": ready,
                              "passengers": boarded, "capacity": capacity})
                heapq.heappush(events, (ready, 1, vehicle))
            traces.append({"direction": direction, "minute": now, "arrivals": arrived,
                           "transported": served, "waiting": queue_size})
        queue_area += queue_size * (duration - last)
        traces.append({"direction": direction, "minute": duration, "arrivals": arrived,
                       "transported": served, "waiting": queue_size})
        summaries.append({"direction": direction, "buses": n, "arrivals": arrived,
                          "transported": served, "completed": completed, "in_transit": served - completed,
                          "waiting": queue_size, "departures": departures,
                          "served_percent": served / arrived * 100 if arrived else 100.0,
                          "mean_wait_boarded": wait_sum / served if served else None,
                          "queue_person_minutes": queue_area,
                          "mean_wait_accrued_all": queue_area / arrived if arrived else 0.0,
                          "fleet_busy_percent": busy / (n * duration) * 100 if n else 0.0,
                          "seat_utilization_percent": served / (departures * capacity) * 100 if departures else 0.0})
    return SimulationResult(pd.DataFrame(summaries), pd.DataFrame(traces),
                            pd.DataFrame(trips, columns=["direction", "vehicle", "boarding_start", "departure",
                                                         "delivered_at", "ready_again", "passengers", "capacity"]))

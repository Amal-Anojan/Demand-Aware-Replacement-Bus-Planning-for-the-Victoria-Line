"""Boundary-flow demand: never sum closed links as unique passengers."""
import pandas as pd
from config import STATIONS, DAY_SOURCES
from data_loader import link_row, time_window


def estimate_demand(data, disruption, day, start, duration, uptake_nb=0.5, uptake_sb=0.5):
    uptake = {"NB": uptake_nb, "SB": uptake_sb}
    if any(not 0 <= x <= 1 for x in uptake.values()):
        raise ValueError("Bus uptake must be between zero and one")
    south, north = STATIONS.index(disruption.south), STATIONS.index(disruption.north)
    boundary_links = {"NB": (STATIONS[south], STATIONS[south + 1]),
                      "SB": (STATIONS[north], STATIONS[north - 1])}
    rows, detail = [], []
    for window in time_window(data, day, start, duration):
        for direction, (a, b) in boundary_links.items():
            load = float(link_row(data, window["day"], "Link_Loads", a, b)[window["interval"]]) * window["interval_minutes"] / 15
            freq = float(link_row(data, window["day"], "Link_Frequencies", a, b)[window["interval"]])
            rows.append({**window, "direction": direction, "boundary_link": f"{a} → {b}",
                         "potential_demand": load, "uptake": uptake[direction],
                         "bus_demand": load * uptake[direction], "scheduled_trains": freq,
                         "trains_per_hour": freq * 4,
                         "passengers_per_train": load * 15 / window["interval_minutes"] / freq if freq > 0 else None,
                         "service_note": "No scheduled service" if freq == 0 else "Normal schedule only",
                         "inconsistent_load": freq == 0 and load > 0})
        for a, b in disruption.removed:
            load = link_row(data, window["day"], "Link_Loads", a, b)
            detail.append({**window, "from_station": a, "to_station": b, "direction": load["Dir"],
                           "load": float(load[window["interval"]]) * window["interval_minutes"] / 15})
    return pd.DataFrame(rows), pd.DataFrame(detail)


def continuation_estimates(data, day, interval):
    """Local flow balance, not OD inference; expose negative residuals for diagnosis."""
    rows = []
    tables = data[DAY_SOURCES[day]]
    for direction, order in [("NB", STATIONS), ("SB", STATIONS[::-1])]:
        for previous, station, following in zip(order, order[1:], order[2:]):
            arrival = float(link_row(data, day, "Link_Loads", previous, station)[interval])
            departure = float(link_row(data, day, "Link_Loads", station, following)[interval])
            values = {}
            for sheet in ("Station_Boarders", "Station_Alighters"):
                frame = tables[sheet]
                selected = frame[(frame["Station"] == station) & (frame["Dir"] == direction)]
                values[sheet] = float(selected[interval].sum()) if len(selected) else None
            board, alight = values["Station_Boarders"], values["Station_Alighters"]
            residual = arrival - alight if alight is not None else None
            rows.append({"direction": direction, "station": station, "incoming_load": arrival,
                         "boarders": board, "alighters": alight, "outgoing_load": departure,
                         "continuing_estimate": max(0, residual) if residual is not None else None,
                         "raw_continuation_residual": residual,
                         "balance_error": departure - (arrival - alight + board)
                         if board is not None and alight is not None else None})
    return pd.DataFrame(rows)

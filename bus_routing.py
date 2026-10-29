"""Independent directed Dijkstra routes using road-edge travel_time seconds."""
from dataclasses import dataclass
import math
import networkx as nx


@dataclass
class RoadRoute:
    direction: str
    origin: str
    destination: str
    nodes: list
    distance_km: float
    free_flow_minutes: float
    minutes: float
    geometry: list


def shortest_route(graph, source, target, congestion=1.0, direction="", origin="", destination=""):
    if not math.isfinite(congestion) or congestion < 1:
        raise ValueError("Congestion multiplier must be finite and at least 1")
    if source == target:
        raise ValueError("Both boundaries snapped to one node; choose distinct road access points")
    # NetworkX otherwise silently treats a missing weight as 1.
    for _, _, attrs in graph.edges(data=True):
        if any(k not in attrs or not math.isfinite(float(attrs[k])) or float(attrs[k]) < 0
               for k in ("travel_time", "length")):
            raise ValueError("Road edges require finite non-negative travel_time and length")
    nodes = nx.dijkstra_path(graph, source, target, weight="travel_time")
    length = seconds = 0.0
    geometry = []
    for u, v in zip(nodes, nodes[1:]):
        edge = min(graph[u][v].values(), key=lambda a: a["travel_time"]) if graph.is_multigraph() else graph[u][v]
        length += float(edge["length"])
        seconds += float(edge["travel_time"])
        if "geometry" in edge:
            xy = list(edge["geometry"].coords)
            first_distance = (xy[0][0] - graph.nodes[u]["x"])**2 + (xy[0][1] - graph.nodes[u]["y"])**2
            last_distance = (xy[-1][0] - graph.nodes[u]["x"])**2 + (xy[-1][1] - graph.nodes[u]["y"])**2
            if last_distance < first_distance:
                xy.reverse()
            points = [(y, x) for x, y in xy]
        else:
            points = [(graph.nodes[n]["y"], graph.nodes[n]["x"]) for n in (u, v)]
        geometry.extend(points if not geometry else points[1:])
    if seconds <= 0:
        raise ValueError("Route has no positive travel time")
    return RoadRoute(direction, origin, destination, nodes, length / 1000,
                     seconds / 60, seconds / 60 * congestion, geometry)


def replacement_routes(graph, access, disruption, congestion=1.0):
    return {direction: shortest_route(graph, access[a]["node"], access[b]["node"], congestion,
                                      direction, a, b)
            for direction, (a, b) in disruption.connections.items()}


def cycle_times(routes, boarding, alighting, layover):
    if any(not math.isfinite(t) or t < 0 for t in (boarding, alighting, layover)):
        raise ValueError("Dwell times must be finite and non-negative")
    # Dedicated directional fleet, empty repositioning on the reverse route.
    return {d: routes[d].minutes + routes["SB" if d == "NB" else "NB"].minutes
            + boarding + alighting + layover for d in ("NB", "SB")}

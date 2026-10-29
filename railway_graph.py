"""Multi-attribute directed railway graph and contiguous closures."""
from copy import deepcopy
from dataclasses import dataclass
import networkx as nx
from config import STATIONS, DAY_SOURCES
from data_loader import interval_columns, link_row


def build_graph(data):
    graph = nx.DiGraph(line="Victoria")
    graph.add_nodes_from((s, {"station_order": i}) for i, s in enumerate(STATIONS))
    for i, (south, north) in enumerate(zip(STATIONS, STATIONS[1:])):
        for origin, destination, direction in [(south, north, "NB"), (north, south, "SB")]:
            loads, frequencies, orders = {}, {}, {}
            for day in DAY_SOURCES:
                row = link_row(data, day, "Link_Loads", origin, destination)
                freq = link_row(data, day, "Link_Frequencies", origin, destination)
                intervals = interval_columns(row.index)
                loads[day] = {c: float(row[c]) for c in intervals}
                frequencies[day] = {c: float(freq[c]) for c in intervals}
                orders[day] = int(row["Order"])
            graph.add_edge(origin, destination, line="Victoria", direction=direction,
                           station_order=i, source_order=orders, passenger_load=loads,
                           train_frequency=frequencies, disrupted=False,
                           continuing_flow=None)
    return graph


@dataclass
class Disruption:
    graph: nx.DiGraph
    display_graph: nx.DiGraph
    south: str
    north: str
    removed: list

    @property
    def connections(self):
        return {"NB": (self.south, self.north), "SB": (self.north, self.south)}

    @property
    def components(self):
        return [sorted(c, key=STATIONS.index) for c in nx.weakly_connected_components(self.graph)]


def close_section(graph, boundary_a, boundary_b):
    if boundary_a not in STATIONS or boundary_b not in STATIONS or boundary_a == boundary_b:
        raise ValueError("Select two different Victoria line stations")
    low, high = sorted((STATIONS.index(boundary_a), STATIONS.index(boundary_b)))
    scenario = deepcopy(graph)
    display = deepcopy(graph)
    removed = []
    for i in range(low, high):
        a, b = STATIONS[i:i + 2]
        for edge in [(a, b), (b, a)]:
            scenario.remove_edge(*edge)
            display.edges[edge]["disrupted"] = True
            removed.append(edge)
    return Disruption(scenario, display, STATIONS[low], STATIONS[high], removed)

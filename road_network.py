"""Download/cache verifiable TfL station coordinates and OpenStreetMap roads."""
from datetime import datetime, timezone
import json
import math
import re
import networkx as nx
import requests
from config import ROOT, CACHE_DIR, STATIONS

TFL_URL = "https://api.tfl.gov.uk/Line/victoria/StopPoints"
COORDINATES = ROOT / "config" / "stations.json"
ROAD_FILE = CACHE_DIR / "london_drive.graphml"
STOPS_FILE = CACHE_DIR / "bus_stops.json"


def normalize_name(name):
    name = name.casefold().replace("underground station", "").replace(" lu", "")
    return re.sub(r"[^a-z0-9]", "", name.replace("st.", "st"))


def station_coordinates(refresh=False):
    if COORDINATES.exists() and not refresh:
        payload = json.loads(COORDINATES.read_text(encoding="utf-8"))
    else:
        response = requests.get(TFL_URL, timeout=60)
        response.raise_for_status()
        records = response.json()
        matched = {}
        for name in STATIONS:
            candidates = [r for r in records if normalize_name(r["commonName"]) == normalize_name(name)]
            if len(candidates) != 1:
                raise ValueError(f"TfL station identity is ambiguous or absent: {name}")
            record = candidates[0]
            matched[name] = {"lat": record["lat"], "lon": record["lon"],
                             "source_name": record["commonName"], "naptan_id": record["id"]}
        payload = {"source": TFL_URL, "retrieved_utc": datetime.now(timezone.utc).isoformat(),
                   "stations": matched}
        validate_coordinates(payload)
        COORDINATES.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    validate_coordinates(payload)
    return payload


def validate_coordinates(payload):
    if set(payload["stations"]) != set(STATIONS):
        raise ValueError("Coordinates must cover exactly the 16 Victoria stations")
    for name, point in payload["stations"].items():
        if not 51.3 < point["lat"] < 51.8 or not -0.5 < point["lon"] < 0.3:
            raise ValueError(f"Station outside London bounds: {name}")
        if normalize_name(point["source_name"]) != normalize_name(name):
            raise ValueError(f"Station source name mismatch: {name}")


def configure_osmnx():
    import osmnx as ox
    CACHE_DIR.mkdir(exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(CACHE_DIR / "osm_http")
    ox.settings.requests_timeout = 180
    ox.settings.log_console = False
    return ox


def road_bbox(coordinates, buffer_km=5.0):
    points = list(coordinates["stations"].values())
    if not math.isfinite(buffer_km) or buffer_km < 1:
        raise ValueError("Road buffer must be at least 1 km")
    dy = buffer_km / 111.0
    dx = buffer_km / (111.0 * math.cos(math.radians(max(p['lat'] for p in points))))
    return (min(p["lon"] for p in points) - dx, min(p["lat"] for p in points) - dy,
            max(p["lon"] for p in points) + dx, max(p["lat"] for p in points) + dy)


def load_road_network(coordinates, refresh=False, buffer_km=5.0, save_path=None):
    ox = configure_osmnx()
    if ROAD_FILE.exists() and not refresh:
        return ox.load_graphml(ROAD_FILE)
    bbox = road_bbox(coordinates, buffer_km)
    graph = ox.graph_from_bbox(bbox, network_type="drive", simplify=True, retain_all=False)
    # Speeds come from OSM maxspeed tags, with OSMnx highway-class mean imputation.
    # No hand-entered route time or invented fallback speeds.
    graph = ox.routing.add_edge_speeds(graph)
    graph = ox.routing.add_edge_travel_times(graph)
    for _, _, attr in graph.edges(data=True):
        attr["speed_source"] = "OSM maxspeed" if "maxspeed" in attr else "OSMnx imputed from observed maxspeed"
    graph.graph["source"] = "OpenStreetMap via OSMnx; ODbL"
    graph.graph["retrieved_utc"] = datetime.now(timezone.utc).isoformat()
    graph.graph["bbox"] = str(bbox)
    validate_road_graph(graph)
    ox.save_graphml(graph, save_path or ROAD_FILE)
    return graph


def validate_road_graph(graph, access=None):
    """Validate persisted weights and, optionally, every directed station pair."""
    if not graph.is_directed() or not graph.nodes or not graph.edges:
        raise ValueError("Road graph must be directed and contain nodes and edges")
    for node, attrs in graph.nodes(data=True):
        for key, limit in (("x", 180), ("y", 90)):
            value = float(attrs.get(key, float('nan')))
            if not math.isfinite(value) or abs(value) > limit:
                raise ValueError(f"Node {node} has invalid {key} coordinate")
    for u, v, attrs in graph.edges(data=True):
        for key in ("length", "speed_kph", "travel_time"):
            value = float(attrs.get(key, float('nan')))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Edge {u}->{v} has invalid {key}")
        expected = float(attrs['length']) / (float(attrs['speed_kph']) / 3.6)
        if not math.isclose(float(attrs['travel_time']), expected, rel_tol=.01, abs_tol=.1):
            raise ValueError(f"Edge {u}->{v} travel time disagrees with length/speed")
    checked = 0
    if access is not None:
        if set(access) != set(STATIONS):
            raise ValueError("Road access must cover all 16 stations")
        nodes = [access[s]['node'] for s in STATIONS]
        if len(set(nodes)) != 16 or any(n not in graph for n in nodes):
            raise ValueError("Stations require 16 distinct valid road nodes")
        for source in nodes:
            distances = nx.single_source_dijkstra_path_length(graph, source, weight="travel_time")
            for target in nodes:
                if source != target:
                    if target not in distances or distances[target] <= 0:
                        raise ValueError(f"No directed road route from {source} to {target}")
                    checked += 1
    return {"nodes": len(graph), "edges": graph.number_of_edges(), "directed_station_pairs": checked}


def bus_stops(coordinates, refresh=False):
    if STOPS_FILE.exists() and not refresh:
        return json.loads(STOPS_FILE.read_text(encoding="utf-8"))
    ox = configure_osmnx()
    try:
        features = ox.features_from_bbox(road_bbox(coordinates), tags={"highway": "bus_stop"})
        stops = []
        for identity, row in features.iterrows():
            point = row.geometry
            if point.geom_type != "Point":
                continue
            name = row.get("name")
            stops.append({"lat": point.y, "lon": point.x, "osm_id": str(identity),
                          "name": name if isinstance(name, str) else "OSM bus stop"})
        payload = {"source": "OpenStreetMap highway=bus_stop", "stops": stops,
                   "retrieved_utc": datetime.now(timezone.utc).isoformat(), "error": None}
        STOPS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    except Exception as exc:
        # An unavailable stop service must not fabricate bus stop locations.
        return {"stops": [], "error": str(exc), "source": "Bus stop download unavailable"}


def distance_metres(a, b):
    lat1, lat2 = math.radians(a["lat"]), math.radians(b["lat"])
    dlat, dlon = lat2 - lat1, math.radians(b["lon"] - a["lon"])
    h = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def access_points(graph, coordinates, stops):
    """Snap candidates to the largest strongly connected drivable component.

    This guarantees return connectivity, not a legal boarding bay or road-side
    access. Actual bus stop points and snapped routing nodes are both retained.
    """
    ox = configure_osmnx()
    routable = graph.subgraph(max(nx.strongly_connected_components(graph), key=len)).copy()
    result = {}
    for name, station in coordinates["stations"].items():
        candidates = sorted((s for s in stops["stops"] if distance_metres(station, s) <= 500),
                            key=lambda s: distance_metres(station, s))
        chosen = None
        for candidate in candidates:
            node, snap = ox.distance.nearest_nodes(routable, candidate["lon"], candidate["lat"], return_dist=True)
            if snap <= 120:
                chosen = {**candidate, "node": int(node), "snap_metres": float(snap),
                          "access_type": "Nearby OSM bus stop; road-node approximation"}
                break
        if chosen is None:
            node, snap = ox.distance.nearest_nodes(routable, station["lon"], station["lat"], return_dist=True)
            chosen = {"lat": station["lat"], "lon": station["lon"], "name": name,
                      "node": int(node), "snap_metres": float(snap),
                      "access_type": "Nearest drivable node approximation; no verified bus stop"}
        if chosen["snap_metres"] > 1000:
            raise ValueError(f"No suitable road node within 1 km of {name}")
        node_data = routable.nodes[chosen["node"]]
        chosen.update(road_lat=float(node_data["y"]), road_lon=float(node_data["x"]),
                      station_to_stop_metres=distance_metres(station, chosen))
        result[name] = chosen
    return result


def prepare_roads(refresh=False, allow_download=True):
    if not allow_download:
        missing = [str(p) for p in (COORDINATES, ROAD_FILE) if not p.exists()]
        if missing:
            raise FileNotFoundError("Run python download_roads.py locally first. Missing: " + ", ".join(missing))
        coords = station_coordinates()
        graph = configure_osmnx().load_graphml(ROAD_FILE)
        stops = json.loads(STOPS_FILE.read_text(encoding="utf-8")) if STOPS_FILE.exists() else {
            "stops": [], "error": "No bus-stop cache; using road-node approximations"}
        access_file = CACHE_DIR / "station_access.json"
        access = json.loads(access_file.read_text(encoding="utf-8")) if access_file.exists() else access_points(graph, coords, stops)
        validate_road_graph(graph, access)
        for name, point in access.items():
            node = graph.nodes[point['node']]
            if distance_metres(coords['stations'][name], {'lat': node['y'], 'lon': node['x']}) > 1000:
                raise ValueError(f"Cached road access too far from {name}; rerun downloader with --refresh")
        return coords, graph, access, stops
    coords = station_coordinates(refresh)
    graph = load_road_network(coords, refresh)
    stops = bus_stops(coords, refresh)
    access = access_points(graph, coords, stops)
    (CACHE_DIR / "station_access.json").write_text(json.dumps(access, indent=2), encoding="utf-8")
    return coords, graph, access, stops


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Download and cache TfL/OSM source data")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    coords, graph, access, stops = prepare_roads(args.refresh)
    print(f"Validated {len(coords['stations'])} stations; {len(graph)} road nodes; {graph.number_of_edges()} road edges")
    print(f"Bus stops: {len(stops['stops'])}; source warning: {stops['error']}")

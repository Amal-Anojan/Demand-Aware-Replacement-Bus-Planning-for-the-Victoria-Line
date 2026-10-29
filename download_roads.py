"""Download real road data locally, or validate the existing cache offline."""
import argparse
import json
import sys
from road_network import (ROAD_FILE, CACHE_DIR, station_coordinates, configure_osmnx,
    load_road_network, bus_stops, access_points, validate_road_graph, prepare_roads)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Replace an existing road cache after validation')
    parser.add_argument('--validate-only', action='store_true', help='Check saved graph and all station routes without network requests')
    parser.add_argument('--buffer-km', type=float, default=5, help='Surrounding road margin (default: 5 km)')
    args = parser.parse_args()
    stage = ROAD_FILE.with_name('london_drive.pending.graphml')
    try:
        print(f'Road cache: {ROAD_FILE}', flush=True)
        if args.validate_only or (ROAD_FILE.exists() and not args.refresh):
            print('Loading existing cache; no downloads.', flush=True)
            _, graph, access, _ = prepare_roads(allow_download=False)
        else:
            print('[1/5] Obtaining and validating all 16 station coordinates from TfL…', flush=True)
            coords = station_coordinates()
            print(f'[2/5] Downloading drivable OSM roads with {args.buffer_km:g} km surrounding margin. This can take several minutes…', flush=True)
            print('OSMnx derives speeds from OSM tags and imputes missing speeds from observed road classes.', flush=True)
            load_road_network(coords, refresh=True, buffer_km=args.buffer_km, save_path=stage)
            print('[3/5] Reloading saved GraphML and checking every node and weighted edge…', flush=True)
            graph = configure_osmnx().load_graphml(stage)
            validate_road_graph(graph)
            print('[4/5] Finding nearby bus stops and road access for all stations…', flush=True)
            stops = bus_stops(coords)
            if stops.get('error'):
                print('Warning: bus-stop lookup failed; using labelled road-node approximations. ' + stops['error'], flush=True)
            access = access_points(graph, coords, stops)
            print('[5/5] Checking travel-time Dijkstra connectivity for all 240 directed station pairs…', flush=True)
            validate_road_graph(graph, access)
            stage.replace(ROAD_FILE)
            (CACHE_DIR / 'station_access.json').write_text(json.dumps(access, indent=2), encoding='utf-8')
        report = validate_road_graph(graph, access)
        (CACHE_DIR / 'road_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(f"Validated: {report['nodes']:,} nodes, {report['edges']:,} edges, {report['directed_station_pairs']} directed station pairs.")
        print('Ready. Restart Streamlit to load the cache without downloading again.')
        return 0
    except KeyboardInterrupt:
        print('\nCancelled. Any previous validated road cache is retained.', file=sys.stderr)
        return 130
    except Exception as exc:
        print(f'Road setup failed: {type(exc).__name__}: {exc}', file=sys.stderr)
        print('Check internet access to api.tfl.gov.uk and overpass-api.de. For rate limits or timeouts, retry later. '
              'Install dependencies using python -m pip install -r requirements.txt. '
              'For connectivity failures, retry with --refresh --buffer-km 8. '
              'No replacement distances or travel times have been invented.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

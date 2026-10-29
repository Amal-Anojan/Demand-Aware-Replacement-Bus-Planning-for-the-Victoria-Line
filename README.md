# Victoria line replacement-bus planner

A graph-theory project that plans replacement buses when a continuous section of London's Victoria line closes. A simple Streamlit dashboard combines TfL NUMBAT passenger estimates, OpenStreetMap road routes and a simulation of reusable buses.

## What the dashboard shows

- Disruption setup: day, start time, duration, boundary stations, available buses, capacity and assumed bus uptake.
- Passenger demand across the full disruption.
- Pickup and destination stations, suggested nearby pickup locations and directional road routes.
- Minimum buses needed, buses assigned, repeated bus trips and additional buses needed.
- Passengers collected, still waiting and reaching the destination.
- A downloadable bus-plan CSV.

## Requirements

Use Python 3.11 or newer. Run commands from the project directory in your local terminal. Internet access is needed to install dependencies and download roads. The dashboard then reads local road caches; background map tiles may still require internet.

## Set up and run (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Place these five supplied NUMBAT 2025 workbooks in `data/`:

```text
NBT25MON_Outputs.xlsx
NBT25TWT_Outputs.xlsx
NBT25FRI_Outputs.xlsx
NBT25SAT_Outputs.xlsx
NBT25SUN_Outputs.xlsx
```

See [data setup](data/README.md). The workbooks are not included in this repository. Tuesday, Wednesday and Thursday share the TWT passenger profile.

Download and validate the real road network, then launch the app:

```powershell
.\.venv\Scripts\python.exe download_roads.py
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Alternatively, after setup, use `./run_app.ps1`. It checks required imports before starting Streamlit. The dependency `streamlit-folium` supplies the `streamlit_folium` import.

Open the local URL printed by Streamlit, choose the settings and click **Plan replacement buses**. Initial workbook loading can take time; later runs reuse validated passenger caches.

## Road downloads and caches

The downloader covers all 16 stations plus a default 5 km surrounding margin. It adds OSMnx road-speed and travel-time estimates, saves a temporary GraphML file, reloads it and validates it before replacing the main cache.

- Road graph: `cache/london_drive.graphml`.
- Downloaded station coordinates: `config/stations.json`.
- Validation summary: `cache/road_validation.json`.
- Optional bus stops and station access information: files under `cache/`.

Paths are resolved relative to the project, not the terminal's working directory. Keep the downloaded files together when running the app. Existing roads are reused unless refresh is requested.

```powershell
# Check the saved graph without downloading again
.\.venv\Scripts\python.exe download_roads.py --validate-only

# Explicitly replace the cache with a wider download
.\.venv\Scripts\python.exe download_roads.py --refresh --buffer-km 8
```

Validation checks node coordinates, positive edge lengths/speeds/times, consistency of weights and all 240 ordered station pairs. Download failures leave an existing valid main cache intact. Restart Streamlit after replacing caches.

Northbound and southbound routes are calculated independently with Dijkstra, weighted by `travel_time`. Times are speed-based estimates, including OSMnx speed imputation where needed; they are not live traffic observations. Missing road data does not trigger invented distances or times. The dashboard shows passenger estimates but withholds fleet calculations until road routes are available.

## How the model works

1. Build a directed railway graph with 16 stations and 30 links.
2. Copy it and remove every railway link inside the selected boundaries in both directions.
3. Use the first closed link at each directional entry boundary to estimate affected demand. Do not sum all closed-link loads as unique passengers.
4. Multiply each interval's load by the selected bus-uptake percentage and the fraction of the interval included.
5. Find the two driving routes using the directed road multigraph.
6. Simulate first-in-first-out passenger queues and buses returning to their original pickup.
7. Test every fixed directional fleet split and select the best under the simulation objective.

### Duration and demand

Start times follow the source quarter-hour intervals. Duration accepts 1-1440 whole minutes. A 100-minute disruption uses six complete intervals plus 10/15 of the seventh. Batches join at minutes 0, 15, 30, 45, 60, 75 and 90; buses depart whenever available and passengers are waiting.

```text
bus demand = boundary-link load x included minutes / 15 x uptake
```

This models batch arrivals, not individual train arrivals. A service day runs from 05:00 to the following early morning; the passenger source advances at the next 05:00, not midnight.

### Vehicles and allocation

```text
bus cycle = outward journey time + empty return journey time
required departures for a batch = ceil(bus demand / bus capacity)
```

The current dashboard adds no boarding, alighting or layover time and applies no congestion multiplier. Buses start at their pickup boundaries and remain dedicated to one direction. Departures are repeated trips, not distinct vehicles.

For N available buses, all N+1 fixed splits are simulated. Selection first minimises final waiting passengers, then total passenger-minutes of waiting. Ties favour a split closer to equal, then northbound. This is an exact comparison within the fixed-split model, not a globally optimal real-world timetable.

**Buses needed** is the minimum dedicated fleet that boards all expected arrivals before the disruption ends. Waiting is allowed. This does not guarantee that everybody reaches the destination by that time. Collected passengers can still be in transit.

## Tests

Supply the workbooks and download the road cache before running the complete suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests cover data validation, day rollover, partial intervals, railway closures, directional routes, parallel edges, vehicle reuse, capacity, passenger conservation, allocation and Streamlit controls. The real-cache UI test requires local road files. Run locally where Streamlit can create sockets. UI tests check execution and controls, not external map-tile rendering.

## Project files

| File | Responsibility |
|---|---|
| `app.py` | Streamlit interface and workflow |
| `data_loader.py` | Workbook validation and service-day windows |
| `railway_graph.py` | Railway graph and closures |
| `demand_estimator.py` | Boundary demand and partial intervals |
| `download_roads.py`, `road_network.py` | Road downloads, validation and cache loading |
| `bus_routing.py` | Weighted Dijkstra routes and return cycles |
| `simulation.py` | Passenger queues and bus availability events |
| `bus_allocation.py` | Fleet split search and minimum fleet |
| `dashboard_views.py` | Map and display helpers |
| `config/` | Station order, source mapping and project paths |
| `tests/` | Regression, algorithm and dashboard tests |

## Assumptions and limitations

The shuttle connects the closure boundaries. Normal train connections at those boundaries are assumed, not verified TfL turnback arrangements. Intermediate closed stations are not separately served by this shuttle model. Boundary loads are estimates, not complete passenger origin-destination records.

Pickup suggestions need checks for legal boarding, road side and bus access. The model does not include live congestion, dwell, depot mobilisation, full bus-specific restrictions, individual train arrivals or passengers abandoning queues. Results support academic comparison; operational use needs additional data and validation.

## Troubleshooting

- **Missing imports:** install `requirements.txt` into the same `.venv` used to launch the app.
- **Cannot import `fleet_needed` after updating code:** stop Streamlit with Ctrl+C and start a fresh process. A browser refresh does not reload Python modules reliably.
- **Missing workbook:** check the exact names in `data/`.
- **Road download fails:** check internet access and retry later if TfL/Overpass is unavailable or rate-limited.
- **Road routes unavailable:** run the downloader, validate the saved graph and restart Streamlit.

## Upload to GitHub

The `.gitignore` excludes local environments, credentials, downloaded caches, source Excel workbooks, generated documents and temporary files. It does not delete them. Python source, tests, requirements, configuration code and this README are included. Anyone cloning the repository must supply the workbooks and run the road downloader.

Create an empty GitHub repository, then run the following from this folder. Replace `YOUR_USERNAME` and `YOUR_REPOSITORY` with your actual values:

```powershell
git init
git branch -M main
git add .
git status --short
git diff --cached --stat
git commit -m "Add Victoria line replacement bus planner"
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Review the staged list before committing. If a remote named `origin` already exists, inspect `git remote -v` and use `git remote set-url origin URL` only if it needs changing. These commands assume the GitHub repository is empty; do not force-push over existing work.

## Data and references

- [TfL NUMBAT introduction](https://crowding.data.tfl.gov.uk/NUMBAT/Intro_to_NUMBAT.pdf)
- [TfL passenger data portal](https://crowding.data.tfl.gov.uk/)
- [OSMnx documentation](https://osmnx.readthedocs.io/en/stable/user-reference.html)
- [NetworkX shortest paths](https://networkx.org/documentation/stable/reference/algorithms/shortest_paths.html)

Map data: OpenStreetMap contributors (ODbL). Background tiles: CARTO. TfL workbooks remain subject to their source terms. This is an academic project, not an official TfL service or operating plan.

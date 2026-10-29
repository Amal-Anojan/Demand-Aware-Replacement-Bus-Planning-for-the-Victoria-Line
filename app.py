"""One-page replacement-bus planning dashboard."""
import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_folium import st_folium
from config import DAY_SOURCES, STATIONS
from data_loader import load_data, source_signature, interval_columns
from railway_graph import build_graph, close_section
from demand_estimator import estimate_demand
from road_network import prepare_roads
from bus_routing import replacement_routes, cycle_times
from bus_allocation import demand_aware_allocation, fleet_needed
from simulation import simulate
from dashboard_views import network_map, COLORS

st.set_page_config(page_title="Victoria line | Bus planner", page_icon="🚍", layout="wide")
st.markdown("""<style>
.block-container {max-width:1200px;padding-top:2rem;}
h1 {letter-spacing:-.035em;}
[data-testid="stMetric"] {background:#edf5fa;border-radius:12px;padding:18px;}
[data-testid="stMetricLabel"],[data-testid="stMetricValue"] {color:#14324d;}
</style>""", unsafe_allow_html=True)

@st.cache_resource
def sources(signature):
    data = load_data()
    return data, build_graph(data)

@st.cache_resource
def roads():
    return prepare_roads(allow_download=False)

st.title("Victoria line bus planner")
st.write("Plan replacement buses for a closed section of the line.")
try:
    data, graph = sources(source_signature())
except Exception as exc:
    st.error(f"Passenger data could not be loaded: {exc}")
    st.stop()

intervals = interval_columns(data["TWT"]["Link_Loads"].columns)
st.subheader("Disruption setup")
with st.form("setup"):
    left, middle, right = st.columns(3)
    day = left.selectbox("Day", list(DAY_SOURCES), index=1)
    start = middle.selectbox("Start time", intervals, index=14,
                            format_func=lambda x: x[:2] + ":" + x[2:4])
    duration = right.number_input("Duration (minutes)", 1, 1440, 100, 1)
    left, right = st.columns(2)
    a = left.selectbox("Closed section starts at", STATIONS, index=5)
    b = right.selectbox("Closed section ends at", STATIONS, index=6)
    left, middle, right = st.columns(3)
    fleet = left.number_input("Available buses", 0, 100, 20)
    capacity = middle.number_input("Passengers per bus", 1, 150, 80)
    uptake = right.slider("Passengers choosing buses (%)", 0, 100, 50)
    submitted = st.form_submit_button("Plan replacement buses", type="primary")

if submitted:
    if a == b:
        st.error("Choose two different stations.")
        st.stop()
    st.session_state["clean_plan"] = dict(day=day, start=start, duration=duration,
                                         a=a, b=b, fleet=fleet, capacity=capacity, uptake=uptake)
if "clean_plan" not in st.session_state:
    st.info("Choose the closed section and select Plan replacement buses.")
    st.stop()
c = st.session_state["clean_plan"]
closure = close_section(graph, c["a"], c["b"])
demand, _ = estimate_demand(data, closure, c["day"], c["start"], c["duration"],
                            c["uptake"] / 100, c["uptake"] / 100)
st.divider()
st.subheader("Passenger demand")
one, two = st.columns(2)
one.metric("Passengers affected", f"{demand.potential_demand.sum():,.0f}")
two.metric("Expected to use buses", f"{demand.bus_demand.sum():,.0f}")
st.caption(f"Estimates cover the full {c['duration']}-minute disruption. Passengers join the queue every 15 minutes; buses keep running as they become available.")
if c["duration"] % 15:
    st.caption(f"The final {c['duration'] % 15} minutes use that share of the next 15-minute passenger estimate.")
chart = demand.copy()
chart["Direction"] = chart.direction.map({"NB": "Northbound", "SB": "Southbound"})
chart["Minutes after closure"] = chart.minute
chart["Passengers"] = chart.bus_demand
st.plotly_chart(px.bar(chart, x="Minutes after closure", y="Passengers", color="Direction",
                       barmode="group", color_discrete_map={"Northbound": COLORS["NB"], "Southbound": COLORS["SB"]}),
                use_container_width=True)

st.subheader("Pickup and destination")
for col, (direction, (origin, destination)) in zip(st.columns(2), closure.connections.items()):
    col.markdown(f"**{'Northbound' if direction == 'NB' else 'Southbound'}**")
    col.write(f"Pickup: **{origin}**")
    col.write(f"Drop-off: **{destination}**")

try:
    with st.spinner("Finding road routes and planning buses…"):
        coords, road_graph, access, stops = roads()
        routes = replacement_routes(road_graph, access, closure, congestion=1.0)
        cycles = cycle_times(routes, boarding=0, alighting=0, layover=0)
        allocation, _ = demand_aware_allocation(demand, c["fleet"], c["capacity"], cycles, c["duration"])
        needed = fleet_needed(demand, c["capacity"], cycles, c["duration"])
        outcome = simulate(demand, allocation, c["capacity"], cycles, c["duration"],
                           outbound={d: r.minutes for d, r in routes.items()})
except Exception as exc:
    st.warning("Road routes are unavailable. Passenger estimates are ready; bus counts need road journey times.")
    with st.expander("Connection details"):
        st.write(str(exc))
    st.download_button("Download passenger demand", chart.to_csv(index=False), "passenger_demand.csv", "text/csv")
    st.stop()

for col, direction in zip(st.columns(2), ("NB", "SB")):
    route = routes[direction]
    point = access[route.origin]
    col.write(f"Nearby pickup: **{point['name']}**")
    col.caption(f"{route.minutes:.0f} min journey · {route.distance_km:.1f} km")
    col.caption("Suggested pickup location; road access needs checking.")
st_folium(network_map(coords, closure, routes, access), height=400, use_container_width=True, returned_objects=[])

st.subheader("Buses needed")
one, two, three = st.columns(3)
one.metric("Buses needed", sum(needed.values()))
two.metric("Buses available", c["fleet"])
three.metric("Additional buses needed", max(0, sum(needed.values()) - c["fleet"]))
st.caption("Buses needed is the smallest fleet that can collect all expected passengers before the disruption ends. Each bus returns to its pickup station before collecting another group.")
summary = outcome.summary.set_index("direction")
table = pd.DataFrame([{
    "Direction": "Northbound" if d == "NB" else "Southbound",
    "Expected passengers": round(float(summary.loc[d, "arrivals"]), 1),
    "Buses needed": needed[d], "Buses assigned": allocation[d],
    "Bus trips": int(summary.loc[d, "departures"]),
    "Passengers collected": round(float(summary.loc[d, "transported"]), 1),
    "Still waiting": round(float(summary.loc[d, "waiting"]), 1),
} for d in ("NB", "SB")])
st.dataframe(table, hide_index=True, use_container_width=True)
st.subheader("Passenger service")
one, two, three = st.columns(3)
one.metric("Passengers collected", f"{summary.transported.sum():,.0f}")
two.metric("Still waiting", f"{summary.waiting.sum():,.0f}")
three.metric("Reached destination", f"{summary.completed.sum():,.0f}")
st.caption("Collected passengers include those still on a bus when the disruption ends.")
st.download_button("Download bus plan", table.to_csv(index=False), "bus_plan.csv", "text/csv")
st.caption("Passenger estimates: TfL NUMBAT 2025 · Road estimates: OpenStreetMap · Tuesday–Thursday share one passenger profile.")

"""Presentation helpers; no demand or simulation logic lives here."""
import folium
import plotly.graph_objects as go
from config import STATIONS

COLORS = {"NB": "#0072B2", "SB": "#D55E00"}


def railway_figure(disruption, day, interval):
    fig = go.Figure()
    for a, b, attrs in disruption.display_graph.edges(data=True):
        i, j = STATIONS.index(a), STATIONS.index(b)
        x = -0.12 if attrs["direction"] == "NB" else 0.12
        closed = attrs["disrupted"]
        color = "#db3545" if closed else COLORS[attrs["direction"]]
        fig.add_trace(go.Scatter(x=[x, x], y=[i, j], mode="lines",
            line=dict(color=color, width=4, dash="dot" if closed else "solid"),
            text=[f"{a} → {b}<br>{attrs['direction']} · {'CLOSED' if closed else 'Open'}<br>"
                  f"Load: {attrs['passenger_load'][day][interval]:,.2f}<br>"
                  f"Normal trains: {attrs['train_frequency'][day][interval]:g}"] * 2,
            hoverinfo="text", showlegend=False))
        fig.add_annotation(x=x, y=(i + j) / 2 + (0.12 if j > i else -0.12),
                           ax=x, ay=(i + j) / 2 - (0.12 if j > i else -0.12),
                           xref="x", yref="y", axref="x", ayref="y", text="",
                           showarrow=True, arrowhead=2, arrowcolor=color, arrowsize=1.2)
    fig.add_trace(go.Scatter(x=[0] * 16, y=list(range(16)), mode="markers+text",
                            text=list(STATIONS), textposition="middle right",
                            marker=dict(color="white", size=12, line=dict(color="#0072B2", width=2)),
                            textfont=dict(size=12), hoverinfo="text", showlegend=False))
    fig.update_layout(height=720, margin=dict(l=30, r=30, t=20, b=20),
                      xaxis=dict(visible=False, range=[-.5, 2]),
                      yaxis=dict(visible=False, range=[-.6, 15.6]),
                      plot_bgcolor="#f4f8fc", paper_bgcolor="rgba(0,0,0,0)")
    return fig


def network_map(coordinates, disruption=None, routes=None, access=None):
    points = coordinates["stations"]
    bounds = [[p["lat"], p["lon"]] for p in points.values()]
    map_ = folium.Map(location=bounds[7], tiles="OpenStreetMap", zoom_start=12)
    for a, b in zip(STATIONS, STATIONS[1:]):
        closed = disruption is not None and (a, b) in disruption.removed
        folium.PolyLine([[points[n]["lat"], points[n]["lon"]] for n in (a, b)],
                        color="#db3545" if closed else "#55b7dc", weight=5,
                        dash_array="7 7" if closed else None,
                        tooltip=f"{a} ↔ {b}" + (" · closed" if closed else "")).add_to(map_)
    for name, point in points.items():
        boundary = disruption is not None and name in (disruption.south, disruption.north)
        folium.CircleMarker([point["lat"], point["lon"]], radius=7 if boundary else 4,
                            color="#102b45", fill=True, fill_color="white", fill_opacity=1,
                            tooltip=name).add_to(map_)
    for direction, route in (routes or {}).items():
        folium.PolyLine(route.geometry, color=COLORS[direction], weight=6,
                        opacity=.85, tooltip=f"{direction}: {route.distance_km:.2f} km · {route.minutes:.1f} min").add_to(map_)
    if access and disruption:
        for name in (disruption.south, disruption.north):
            point = access[name]
            folium.Marker([point["road_lat"], point["road_lon"]],
                          tooltip=f"{name}: {point['access_type']}",
                          popup=f"{point['name']} | snap {point['snap_metres']:.0f} m").add_to(map_)
    map_.fit_bounds(bounds)
    return map_

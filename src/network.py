# src/network.py
"""
Download the street network for the main neighborhood (plus a margin buffer),
tag nodes as main or secondary, and prune dead-ends.
"""

import osmnx as ox
# import networkx as nx
import pickle
import os
from shapely.geometry import Point


def download_graph(main_boundary, custom_filter, margin_meters=500):
    """
    Download ONE street network covering the main neighborhood + margin.
    Uses graph_from_point with a radius, which is fast and reliable.
    Tags nodes as main or secondary by polygon containment.
    """
    print("\n--- Loading street network ---")

    main_name = main_boundary["name"]
    main_polygon = main_boundary["polygon"]

    if main_polygon is None:
        raise ValueError("Main neighborhood polygon is None.")

    # Compute center and radius that covers the polygon + margin
    centroid = main_polygon.centroid
    center_lat = centroid.y
    center_lon = centroid.x

    # Radius = distance from center to farthest polygon corner + margin
    minx, miny, maxx, maxy = main_polygon.bounds
    import math, time
    def _haversine(lat1, lon1, lat2, lon2):
        R = 6371000
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    corners = [(miny, minx), (miny, maxx), (maxy, minx), (maxy, maxx)]
    max_dist = max(_haversine(center_lat, center_lon, c[0], c[1]) for c in corners)
    radius = max_dist + margin_meters

    print(f"  Center: ({center_lat:.4f}, {center_lon:.4f}), radius: {radius:.0f}m")

    # Download (or load from cache)
    ox.settings.use_cache = True
    ox.settings.log_console = False
    t0 = time.time()
    org_graph = ox.graph_from_point(
        (center_lat, center_lon), dist=radius,
        custom_filter=custom_filter,
    )
    elapsed = time.time() - t0
    graph = ox.convert.to_undirected(org_graph)
    cached = "(from cache)" if elapsed < 2 else f"(downloaded in {elapsed:.1f}s)"
    print(f"  {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges {cached}")

    # Tag nodes: inside main polygon = main, outside = secondary
    print(f"  Tagging nodes...")
    main_count = 0
    sec_count = 0
    for n in graph.nodes():
        pt = Point(graph.nodes[n]["x"], graph.nodes[n]["y"])
        if main_polygon.contains(pt):
            graph.nodes[n]["is_main"] = True
            graph.nodes[n]["neighborhood"] = main_name
            main_count += 1
        else:
            graph.nodes[n]["is_main"] = False
            graph.nodes[n]["neighborhood"] = "secondary"
            sec_count += 1

    print(f"    Main: {main_count}, Secondary: {sec_count}")

    # Diagnostic: count boundary-crossing edges
    cross_edges = 0
    for u, v in graph.edges():
        u_main = graph.nodes[u].get("is_main", False)
        v_main = graph.nodes[v].get("is_main", False)
        if u_main != v_main:
            cross_edges += 1
    print(f"    Boundary-crossing edges (main↔secondary): {cross_edges}")

    return org_graph, graph



def remove_dead_ends(graph, protected=None):
    """
    Iteratively remove nodes with effective degree <= 1 (self-loops excluded).
    Called in solve.py after user edits are applied, before pathfinding.

    Nodes that were dead-ends originally but were manually connected by the
    user will have degree >= 2 and survive. protected is an optional set of
    node IDs (e.g. start/end) that must never be removed.
    """
    protected = protected or set()
    print("\n--- Removing dead-ends ---")
    total_removed = 0

    while True:
        to_remove = []
        for n in list(graph.nodes()):
            if n in protected:
                continue
            # Count edges excluding self-loops
            real_deg = sum(1 for _, v in graph.edges(n) if v != n)
            if real_deg <= 1:
                to_remove.append(n)
        if not to_remove:
            break
        graph.remove_nodes_from(to_remove)
        total_removed += len(to_remove)

    main_count = sum(1 for n in graph.nodes() if graph.nodes[n].get("is_main"))
    print(f"  Removed {total_removed} dead-end nodes, {graph.number_of_nodes()} remaining "
          f"({main_count} main)")
    return graph


def save_graph(graph, org_graph, filepath="output/graph.pickle"):
    """Save the processed graph and original directed graph to disk."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    data = {
        "graph": graph,
        "org_graph": org_graph,
    }
    with open(filepath, "wb") as f:
        pickle.dump(data, f)
    print(f"  Graph saved to: {filepath}")


def load_graph(filepath="output/graph.pickle"):
    """Load the processed graph and original directed graph from disk."""
    with open(filepath, "rb") as f:
        data = pickle.load(f)
    print(f"  Graph loaded from: {filepath}")
    return data["graph"], data["org_graph"]

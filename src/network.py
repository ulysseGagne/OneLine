# src/network.py
"""
Download the street network for the main neighborhood (plus a margin buffer),
tag nodes as main or secondary, and prune dead-ends.
"""

import osmnx as ox
import networkx as nx
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


def prune_dead_ends(graph):
    """
    Iteratively remove dead-end nodes (degree 1) from the main neighborhood,
    but KEEP dead-ends that connect to secondary neighborhood nodes
    (i.e., they are border connectors).
    """
    print("\n--- Pruning dead-ends (preserving border connectors) ---")
    total_pruned = 0

    while True:
        to_remove = []
        for n, deg in graph.degree():
            if deg != 1:
                continue
            # Only prune main-neighborhood dead-ends
            if not graph.nodes[n].get("is_main", False):
                continue
            # Check if this dead-end's single neighbor is secondary
            neighbor = next(iter(graph.neighbors(n)))
            if not graph.nodes[neighbor].get("is_main", True):
                # This dead-end connects to a secondary node — keep it
                continue
            to_remove.append(n)

        if not to_remove:
            break

        graph.remove_nodes_from(to_remove)
        total_pruned += len(to_remove)

    # Remove isolated nodes
    isolates = list(nx.isolates(graph))
    if isolates:
        graph.remove_nodes_from(isolates)
        total_pruned += len(isolates)

    print(f"  Pruned {total_pruned} dead-end nodes")

    # Keep only the largest connected component
    if not nx.is_connected(graph):
        largest_cc = max(nx.connected_components(graph), key=len)
        removed = graph.number_of_nodes() - len(largest_cc)
        graph = graph.subgraph(largest_cc).copy()
        print(f"  Removed {removed} nodes from disconnected components")

    main_count = sum(1 for n in graph.nodes() if graph.nodes[n].get("is_main"))
    sec_count = graph.number_of_nodes() - main_count
    print(f"  Final graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    print(f"    Main: {main_count}, Secondary: {sec_count}")

    # Diagnostic: count boundary-crossing edges after pruning
    cross_edges = 0
    for u, v in graph.edges():
        u_main = graph.nodes[u].get("is_main", False)
        v_main = graph.nodes[v].get("is_main", False)
        if u_main != v_main:
            cross_edges += 1
    print(f"    Boundary-crossing edges (main↔secondary): {cross_edges}")

    return graph


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

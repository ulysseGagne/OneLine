# src/interface.py
"""
Generate the interactive HTML map for editing, and load the edits JSON
that the map exports.
"""

import json
import os
import numpy as np
import networkx as nx
from math import radians, sin, cos, sqrt, atan2


def haversine(lat1, lon1, lat2, lon2):
    """Compute distance in meters between two lat/lon points."""
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def generate_map_html(graph, output_dir="output", slug="map"):
    """
    Generate an interactive HTML map with all nodes and edges.
    Nodes are colored by main/secondary status.
    """
    os.makedirs(output_dir, exist_ok=True)

    # Build a simple integer ID mapping for all nodes
    node_list = sorted(graph.nodes())
    osm_to_id = {osm: i for i, osm in enumerate(node_list)}

    # Center of the map
    center_lat = float(np.mean([graph.nodes[n]["y"] for n in graph.nodes()]))
    center_lon = float(np.mean([graph.nodes[n]["x"] for n in graph.nodes()]))

    # Build edge data
    edge_lines = []
    for u, v, data in graph.edges(data=True):
        if "geometry" in data:
            coords = [[float(y), float(x)] for x, y in data["geometry"].coords]
        else:
            coords = [
                [float(graph.nodes[u]["y"]), float(graph.nodes[u]["x"])],
                [float(graph.nodes[v]["y"]), float(graph.nodes[v]["x"])],
            ]
        edge_lines.append({
            "coords": coords,
            "u": osm_to_id[u],
            "v": osm_to_id[v],
        })

    # Build node data
    nodes_data = []
    for osm_id in node_list:
        i = osm_to_id[osm_id]
        nd = graph.nodes[osm_id]
        nodes_data.append({
            "id": int(i),
            "lat": float(nd["y"]),
            "lon": float(nd["x"]),
            "deg": int(graph.degree(osm_id)),
            "osm": int(osm_id),
            "is_main": bool(nd.get("is_main", True)),
            "neighborhood": nd.get("neighborhood", "unknown"),
        })

    # Read the HTML template
    template_path = os.path.join(os.path.dirname(__file__), "map_template.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Load pre-existing edits for auto-import (from Downloads or output/)
    initial_edits = None
    edits_name = f"{slug}_edits.json"
    for candidate in [
        os.path.expanduser(f"~/Downloads/{edits_name}"),
        os.path.join(output_dir, edits_name),
    ]:
        if os.path.exists(candidate):
            with open(candidate, "r", encoding="utf-8") as ef:
                initial_edits = json.load(ef)
            print(f"  Auto-import: loaded {candidate}")
            break

    # Inject the data and slug
    html = html.replace("%%CENTER%%", json.dumps([center_lat, center_lon]))
    html = html.replace("%%EDGES%%", json.dumps(edge_lines))
    html = html.replace("%%NODES%%", json.dumps(nodes_data))
    html = html.replace("%%SLUG%%", slug)
    html = html.replace("%%INITIAL_EDITS%%", json.dumps(initial_edits))

    # Save
    filepath = os.path.join(output_dir, f"{slug}_map.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  Interactive map saved: {filepath}")
    print(f"    {len(nodes_data)} nodes, {len(edge_lines)} edges")
    return filepath


def load_edits(filepath="output/edits.json"):
    """
    Load the edits JSON exported by the interactive map.

    Returns a dict with keys:
        deleted_ids:    list of int (simple IDs of deleted nodes)
        deleted_edges:  list of {u, v} (simple IDs)
        created_nodes:  list of {id, lat, lon}
        created_edges:  list of {from_id, to_id, length}
        included_ids:   list of int (simple IDs of included secondary nodes)
        start_ids:      list of int/str (multiple start candidates)
        end_ids:        list of int/str (multiple end candidates)
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"Edits file not found: {filepath}\n"
            f"Open the interactive map, make your edits, and click Export."
        )

    with open(filepath, "r", encoding="utf-8") as f:
        edits = json.load(f)

    print(f"\n--- Loaded edits from: {filepath} ---")
    print(f"  Deleted nodes:  {len(edits.get('deleted_ids', []))}")
    print(f"  Deleted edges:  {len(edits.get('deleted_edges', []))}")
    print(f"  Created nodes:  {len(edits.get('created_nodes', []))}")
    print(f"  Created edges:  {len(edits.get('created_edges', []))}")
    print(f"  Included nodes: {len(edits.get('included_ids', []))}")
    print(f"  Start nodes:    {edits.get('start_ids', [])}")
    print(f"  End nodes:      {edits.get('end_ids', [])}")

    return edits


def apply_edits(graph, edits):
    """
    Apply the user's edits from the map to the graph.

    - Remove deleted nodes
    - Add created nodes and edges
    - Include selected secondary nodes (keep them; remove the rest)
    - Return start/end OSM node IDs (or None)
    """
    node_list = sorted(graph.nodes())
    id_to_osm = {i: osm for i, osm in enumerate(node_list)}

    deleted_ids = set(edits.get("deleted_ids", []))
    deleted_edges_list = edits.get("deleted_edges", [])
    included_ids = set(edits.get("included_ids", []))
    created_nodes = edits.get("created_nodes", [])
    created_edges = edits.get("created_edges", [])
    start_ids_raw = edits.get("start_ids", [])
    end_ids_raw = edits.get("end_ids", [])

    print("\n--- Applying edits to graph ---")

    # 1. Remove deleted main nodes
    deleted_osm = set()
    for sid in deleted_ids:
        if sid in id_to_osm:
            deleted_osm.add(id_to_osm[sid])
    if deleted_osm:
        graph.remove_nodes_from(deleted_osm)
        print(f"  Removed {len(deleted_osm)} deleted nodes")

    # 1b. Remove deleted edges
    edges_removed = 0
    for de in deleted_edges_list:
        u_sid = de.get("u")
        v_sid = de.get("v")
        u_osm = id_to_osm.get(u_sid)
        v_osm = id_to_osm.get(v_sid)
        if u_osm and v_osm and u_osm in graph and v_osm in graph:
            # Remove all edges between these two nodes (multigraph)
            for pair in [(u_osm, v_osm), (v_osm, u_osm)]:
                while graph.has_edge(*pair):
                    keys = list(graph[pair[0]][pair[1]].keys())
                    if keys:
                        graph.remove_edge(pair[0], pair[1], keys[0])
                        edges_removed += 1
                    else:
                        break
    if edges_removed:
        print(f"  Removed {edges_removed} deleted edges")

    # 2. Remove secondary nodes that were NOT included
    secondary_to_remove = []
    for n in list(graph.nodes()):
        if not graph.nodes[n].get("is_main", True):
            # Check if this node's simple ID is in the included set
            osm_to_id = {osm: i for i, osm in enumerate(node_list)}
            if n in osm_to_id and osm_to_id[n] not in included_ids:
                secondary_to_remove.append(n)
    if secondary_to_remove:
        graph.remove_nodes_from(secondary_to_remove)
        print(f"  Removed {len(secondary_to_remove)} non-included secondary nodes")

    # 3. Add created nodes (using negative IDs to avoid OSM collisions)
    created_id_to_osm = {}
    for cn in created_nodes:
        # Created nodes have string IDs like "new_0", "new_1", etc.
        synthetic_osm = -(cn["id"] + 1)  # Negative IDs: -1, -2, -3, ...
        created_id_to_osm[cn["id"]] = synthetic_osm
        graph.add_node(synthetic_osm, x=cn["lon"], y=cn["lat"],
                       is_main=True, neighborhood="created",
                       street_count=0)
    if created_nodes:
        print(f"  Added {len(created_nodes)} created nodes")

    # Build a unified ID resolver (handles both original and created nodes)
    def resolve_node_id(nid):
        """Resolve a node ID (int or string) to an OSM node ID in the graph."""
        if isinstance(nid, str) and nid.startswith("new_"):
            idx = int(nid.replace("new_", ""))
            return created_id_to_osm.get(idx)
        elif isinstance(nid, int):
            return id_to_osm.get(nid)
        return None

    # 4. Add created edges with haversine-computed lengths
    edges_added = 0
    for ce in created_edges:
        from_osm = resolve_node_id(ce["from_id"])
        to_osm = resolve_node_id(ce["to_id"])
        if from_osm is None or to_osm is None:
            print(f"  Warning: skipping edge {ce['from_id']} -> {ce['to_id']} (unresolved)")
            continue
        if from_osm not in graph or to_osm not in graph:
            print(f"  Warning: skipping edge (node not in graph)")
            continue

        length = haversine(
            graph.nodes[from_osm]["y"], graph.nodes[from_osm]["x"],
            graph.nodes[to_osm]["y"], graph.nodes[to_osm]["x"],
        )
        graph.add_edge(from_osm, to_osm, length=length, created=True)
        edges_added += 1

    if edges_added:
        print(f"  Added {edges_added} created edges")

    # 5. Clean up: remove isolates and keep the right component
    isolates = list(nx.isolates(graph))
    if isolates:
        graph.remove_nodes_from(isolates)

    # 6. Resolve start/end node sets first (we need them for component selection)
    start_osm_set = set()
    for sid in start_ids_raw:
        osm = resolve_node_id(sid)
        if osm and osm in graph:
            start_osm_set.add(osm)
        else:
            print(f"  Warning: start node {sid} not in graph")

    end_osm_set = set()
    for eid in end_ids_raw:
        osm = resolve_node_id(eid)
        if osm and osm in graph:
            end_osm_set.add(osm)
        else:
            print(f"  Warning: end node {eid} not in graph")

    # Pick the right connected component
    if graph.number_of_nodes() > 0 and not nx.is_connected(graph):
        # If we have start/end nodes, keep the component containing them
        target_nodes = start_osm_set | end_osm_set
        if target_nodes:
            # Find components containing any target node
            kept = set()
            for comp in nx.connected_components(graph):
                if comp & target_nodes:
                    kept |= comp
            if kept:
                graph = graph.subgraph(kept).copy()
                print(f"  Kept component(s) containing start/end nodes: {graph.number_of_nodes()} nodes")
            else:
                # Fallback to largest
                largest_cc = max(nx.connected_components(graph), key=len)
                graph = graph.subgraph(largest_cc).copy()
                print(f"  Warning: start/end nodes not in any component, kept largest: {graph.number_of_nodes()} nodes")
        else:
            largest_cc = max(nx.connected_components(graph), key=len)
            graph = graph.subgraph(largest_cc).copy()
            print(f"  Kept largest connected component: {graph.number_of_nodes()} nodes")

    # Re-check start/end are still in graph after component selection
    start_osm_set = {n for n in start_osm_set if n in graph}
    end_osm_set = {n for n in end_osm_set if n in graph}

    print(f"  Final graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    print(f"  Start nodes: {len(start_osm_set)}, End nodes: {len(end_osm_set)}")

    return graph, start_osm_set or None, end_osm_set or None

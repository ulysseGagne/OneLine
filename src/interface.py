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
from shapely.geometry import LineString


def haversine(lat1, lon1, lat2, lon2):
    """Compute distance in meters between two lat/lon points."""
    R = 6371000
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def _project_to_segment(lat, lon, a, b):
    """Project (lat,lon) onto segment a→b, return (closest_lat, closest_lon, t)."""
    dy = b[0] - a[0]
    dx = b[1] - a[1]
    if dy == 0 and dx == 0:
        return a[0], a[1], 0.0
    t = max(0.0, min(1.0, ((lat - a[0]) * dy + (lon - a[1]) * dx) / (dy * dy + dx * dx)))
    return a[0] + t * dy, a[1] + t * dx, t


def _snap_to_polyline(lat, lon, coords):
    """Find closest point on polyline. Returns (seg_idx, point, distance_m)."""
    best_dist = float("inf")
    best_seg = 0
    best_pt = coords[0]
    for i in range(len(coords) - 1):
        plat, plon, _ = _project_to_segment(lat, lon, coords[i], coords[i + 1])
        d = haversine(lat, lon, plat, plon)
        if d < best_dist:
            best_dist = d
            best_seg = i
            best_pt = (plat, plon)
    return best_seg, best_pt, best_dist


def _extract_sub_polyline(coords, from_seg, from_pt, to_seg, to_pt):
    """Extract portion of polyline between two snap points."""
    if from_seg <= to_seg:
        result = [from_pt]
        for i in range(from_seg + 1, to_seg + 1):
            result.append(coords[i])
        result.append(to_pt)
    else:
        result = [from_pt]
        for i in range(from_seg, to_seg, -1):
            result.append(coords[i])
        result.append(to_pt)
    return result


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

    # 0. Save geometries of edges that will be deleted (before any modifications)
    deleted_edge_geoms = {}  # (u_osm, v_osm) -> [(lat, lon), ...]
    for de in deleted_edges_list:
        u_osm = id_to_osm.get(de.get("u"))
        v_osm = id_to_osm.get(de.get("v"))
        if u_osm and v_osm and u_osm in graph and v_osm in graph and graph.has_edge(u_osm, v_osm):
            for key in sorted(graph[u_osm][v_osm].keys()):
                data = graph[u_osm][v_osm][key]
                if "geometry" in data:
                    coords = [(float(y), float(x)) for x, y in data["geometry"].coords]
                else:
                    coords = [
                        (float(graph.nodes[u_osm]["y"]), float(graph.nodes[u_osm]["x"])),
                        (float(graph.nodes[v_osm]["y"]), float(graph.nodes[v_osm]["x"])),
                    ]
                deleted_edge_geoms[(u_osm, v_osm)] = coords
                deleted_edge_geoms[(v_osm, u_osm)] = list(reversed(coords))
                break

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
        idx = de.get("idx")
        u_osm = id_to_osm.get(u_sid)
        v_osm = id_to_osm.get(v_sid)
        if u_osm and v_osm and u_osm in graph and v_osm in graph:
            if graph.has_edge(u_osm, v_osm):
                if idx is not None:
                    # Remove only the specific parallel edge
                    keys = sorted(graph[u_osm][v_osm].keys())
                    if idx < len(keys):
                        graph.remove_edge(u_osm, v_osm, key=keys[idx])
                        edges_removed += 1
                else:
                    # Backward compat: no idx → remove all edges between pair
                    while graph.has_edge(u_osm, v_osm):
                        keys = list(graph[u_osm][v_osm].keys())
                        if keys:
                            graph.remove_edge(u_osm, v_osm, keys[0])
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

    # 4. Add created edges with exported or haversine-computed lengths
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

        coords_raw = ce.get("coords")  # [[lat, lon], ...] from JS
        if coords_raw and len(coords_raw) > 2:
            # Compute real polyline length from curved coords
            length = sum(
                haversine(coords_raw[i][0], coords_raw[i][1],
                          coords_raw[i+1][0], coords_raw[i+1][1])
                for i in range(len(coords_raw) - 1)
            )
            # Shapely uses (x, y) = (lon, lat)
            geom = LineString([(pt[1], pt[0]) for pt in coords_raw])
            graph.add_edge(from_osm, to_osm, length=length, created=True, geometry=geom)
        else:
            # Try to reconstruct geometry from a deleted edge
            from_lat = float(graph.nodes[from_osm]["y"])
            from_lon = float(graph.nodes[from_osm]["x"])
            to_lat = float(graph.nodes[to_osm]["y"])
            to_lon = float(graph.nodes[to_osm]["x"])

            reconstructed = None
            for (u, v), dcoords in deleted_edge_geoms.items():
                from_seg, from_pt, from_dist = _snap_to_polyline(from_lat, from_lon, dcoords)
                to_seg, to_pt, to_dist = _snap_to_polyline(to_lat, to_lon, dcoords)
                if from_dist < 10 and to_dist < 10:
                    sub = _extract_sub_polyline(dcoords, from_seg, from_pt, to_seg, to_pt)
                    if len(sub) > 2:
                        reconstructed = sub
                    break

            if reconstructed:
                length = sum(
                    haversine(reconstructed[i][0], reconstructed[i][1],
                              reconstructed[i+1][0], reconstructed[i+1][1])
                    for i in range(len(reconstructed) - 1)
                )
                geom = LineString([(pt[1], pt[0]) for pt in reconstructed])
                graph.add_edge(from_osm, to_osm, length=length, created=True, geometry=geom)
            elif "length" in ce:
                length = ce["length"]
                graph.add_edge(from_osm, to_osm, length=length, created=True)
            else:
                length = haversine(from_lat, from_lon, to_lat, to_lon)
                graph.add_edge(from_osm, to_osm, length=length, created=True)
        edges_added += 1

    if edges_added:
        print(f"  Added {edges_added} created edges")

    # 4a. Fix geometry swap on split sub-edges
    # When JS splits an edge whose original geometry runs v→u (opposite to the
    # stored u/v order), the two sub-edges receive each other's geometry+length.
    # Detect by comparing each geometry's far-end to its assigned original node.
    swaps_done = 0
    for split_node in [n for n in graph.nodes() if n < 0]:
        siblings = []
        for neighbor in graph.neighbors(split_node):
            if neighbor >= 0:  # original (non-created) node only
                for key in graph[split_node][neighbor]:
                    edata = graph[split_node][neighbor][key]
                    if edata.get("created") and "geometry" in edata:
                        siblings.append((neighbor, key))

        if len(siblings) != 2:
            continue

        orig1, key1 = siblings[0]
        orig2, key2 = siblings[1]
        if orig1 == orig2:
            continue  # self-loop split — handled by 4b

        pts1 = list(graph[split_node][orig1][key1]["geometry"].coords)
        pts2 = list(graph[split_node][orig2][key2]["geometry"].coords)

        # Find the non-split endpoint of each geometry (farther from split node)
        sp_x, sp_y = graph.nodes[split_node]["x"], graph.nodes[split_node]["y"]
        d1_first = abs(pts1[0][0] - sp_x) + abs(pts1[0][1] - sp_y)
        d1_last = abs(pts1[-1][0] - sp_x) + abs(pts1[-1][1] - sp_y)
        far1 = pts1[0] if d1_first > d1_last else pts1[-1]

        d2_first = abs(pts2[0][0] - sp_x) + abs(pts2[0][1] - sp_y)
        d2_last = abs(pts2[-1][0] - sp_x) + abs(pts2[-1][1] - sp_y)
        far2 = pts2[0] if d2_first > d2_last else pts2[-1]

        # Check: geom1's far end should be near orig1, geom2's far end near orig2
        o1_x, o1_y = graph.nodes[orig1]["x"], graph.nodes[orig1]["y"]
        o2_x, o2_y = graph.nodes[orig2]["x"], graph.nodes[orig2]["y"]

        g1_to_o1 = abs(far1[0] - o1_x) + abs(far1[1] - o1_y)
        g1_to_o2 = abs(far1[0] - o2_x) + abs(far1[1] - o2_y)

        if g1_to_o2 < g1_to_o1:
            data1 = graph[split_node][orig1][key1]
            data2 = graph[split_node][orig2][key2]
            data1["geometry"], data2["geometry"] = data2["geometry"], data1["geometry"]
            data1["length"], data2["length"] = data2["length"], data1["length"]
            swaps_done += 1

    if swaps_done:
        print(f"  Fixed {swaps_done} swapped sub-edge geometries")

    # 4b. Fix self-loop splits: parallel created edges between the same pair
    #     build_adjacency keeps only the longest, so the solver loses one half.
    #     Fix: move one edge to a twin node so both halves are traversable.
    pairs_to_fix = []
    seen_pairs = set()
    for u, v, k, d in graph.edges(data=True, keys=True):
        if not d.get("created"):
            continue
        pair = (min(u, v), max(u, v))
        if pair in seen_pairs:
            continue
        created_keys = [k2 for k2 in graph[u][v] if graph[u][v][k2].get("created", False)]
        if len(created_keys) > 1:
            seen_pairs.add(pair)
            pairs_to_fix.append((u, v, created_keys))

    if pairs_to_fix:
        next_twin = min(graph.nodes()) - 1
        for u, v, keys in pairs_to_fix:
            # Move the shorter edge to a twin node
            keys.sort(key=lambda k: graph[u][v][k].get("length", 0))
            move_key = keys[0]
            move_data = dict(graph[u][v][move_key])
            graph.remove_edge(u, v, key=move_key)

            # Split node is the created (negative) one
            split_node = v if v < 0 else u
            other_node = u if split_node == v else v

            twin = next_twin
            next_twin -= 1
            graph.add_node(twin,
                           x=graph.nodes[split_node]["x"],
                           y=graph.nodes[split_node]["y"],
                           is_main=True, neighborhood="created", street_count=0)
            graph.add_edge(other_node, twin, **move_data)
            graph.add_edge(split_node, twin, length=0, created=True)

        print(f"  Fixed {len(pairs_to_fix)} self-loop splits (twin nodes)")

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

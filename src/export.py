# src/export.py
from datetime import datetime
import os

def edge_path_to_coordinates(G_dir, G_undir, edge_path):
    """Convert edge path to (lat, lon) using edge geometries when available."""
    coords = []
    for u, v, k in edge_path:
        found = False
        for a, b in [(u, v), (v, u)]:
            if G_dir.has_edge(a, b):
                edata = G_dir[a][b].get(k, list(G_dir[a][b].values())[0])
                if edata and "geometry" in edata:
                    pts = list(edata["geometry"].coords)
                    if a != u:
                        pts = pts[::-1]
                    coords.extend((lat, lon) for lon, lat in pts)
                    found = True
                    break
        # 2. Fall back to the modified undirected graph (split/created edges)
        if not found and G_undir.has_edge(u, v):
            edata = G_undir[u][v].get(k, list(G_undir[u][v].values())[0])
            if edata and "geometry" in edata:
                pts = list(edata["geometry"].coords)
                # Undirected graph: check if first point is nearer u or v
                u_x, u_y = G_undir.nodes[u]["x"], G_undir.nodes[u]["y"]
                v_x, v_y = G_undir.nodes[v]["x"], G_undir.nodes[v]["y"]
                d_to_u = abs(pts[0][0] - u_x) + abs(pts[0][1] - u_y)
                d_to_v = abs(pts[0][0] - v_x) + abs(pts[0][1] - v_y)
                if d_to_u > d_to_v:
                    pts = pts[::-1]
                coords.extend((lat, lon) for lon, lat in pts)
                found = True
        # 3. Last resort: straight line from node coordinates
        if not found:
            for node in (u, v):
                g = G_dir if node in G_dir.nodes else G_undir
                coords.append((g.nodes[node]["y"], g.nodes[node]["x"]))

    deduped = [coords[0]]
    for c in coords[1:]:
        if c != deduped[-1]:
            deduped.append(c)
    return deduped


def export_gpx(org_graph, graph, edge_path, location, slug="route"):
    """Generate and save a GPX file for the route."""
    coordinates = edge_path_to_coordinates(org_graph, graph, edge_path)

    trkpts = "\n".join(
        f'      <trkpt lat="{lat}" lon="{lon}"></trkpt>'
        for lat, lon in coordinates
    )

    GPX_TEMPLATE = '''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="everystreet-longest-path"
     xmlns="http://www.topografix.com/GPX/1/1">
  <metadata>
    <name>{name}</name>
    <time>{time}</time>
  </metadata>
  <trk>
    <name>{name}</name>
    <trkseg>
{trkpts}
    </trkseg>
  </trk>
</gpx>'''

    gpx = GPX_TEMPLATE.format(
        name=f"Longest Simple Path — {location}",
        time=datetime.now().isoformat(),
        trkpts=trkpts,
    )

    filename = f"{slug}_route.gpx"
    filepath = os.path.join("output", filename)
    
    with open(filepath, "w") as f:
        f.write(gpx)

    print(f"GPX saved: {filepath}")
    print(f"Track points: {len(coordinates)}")


def export_debug_graph_gpx(graph, location, slug="route"):
    """
    Export every edge of the final graph as a GPX file for pre-solve debugging.
    Each edge becomes its own <trkseg> so mapping apps can display all streets.
    """
    trksegs = []
    for u, v, data in graph.edges(data=True):
        if "geometry" in data:
            coords = [(float(y), float(x)) for x, y in data["geometry"].coords]
        else:
            coords = [
                (float(graph.nodes[u]["y"]), float(graph.nodes[u]["x"])),
                (float(graph.nodes[v]["y"]), float(graph.nodes[v]["x"])),
            ]
        pts = "\n".join(
            f'      <trkpt lat="{lat}" lon="{lon}"></trkpt>'
            for lat, lon in coords
        )
        trksegs.append(f"    <trkseg>\n{pts}\n    </trkseg>")

    gpx = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<gpx version="1.1" creator="everystreet-longest-path"\n'
        '     xmlns="http://www.topografix.com/GPX/1/1">\n'
        "  <metadata>\n"
        f"    <name>Debug Graph — {location}</name>\n"
        f"    <time>{datetime.now().isoformat()}</time>\n"
        "  </metadata>\n"
        "  <trk>\n"
        f"    <name>Debug Graph — {location}</name>\n"
        + "\n".join(trksegs) + "\n"
        "  </trk>\n"
        "</gpx>"
    )

    filepath = os.path.join("output", f"{slug}_debug_graph.gpx")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(gpx)

    print(f"  Debug GPX saved: {filepath} ({graph.number_of_edges()} edges)")

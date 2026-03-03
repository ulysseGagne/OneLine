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

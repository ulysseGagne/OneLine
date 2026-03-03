# src/boundaries.py
"""
Fetch the main neighborhood's boundary polygon from OpenStreetMap.
"""

import requests
from shapely.geometry import LineString
from shapely.ops import polygonize, unary_union

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 60


def _overpass_query(query):
    """Send a query to the Overpass API and return the JSON response."""
    resp = requests.get(OVERPASS_URL, params={"data": query}, timeout=OVERPASS_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _extract_way_coords(elements):
    """Build a dict of way_id -> list of (lon, lat) from Overpass elements."""
    nodes = {}
    ways = {}
    for el in elements:
        if el["type"] == "node":
            nodes[el["id"]] = (el["lon"], el["lat"])
        elif el["type"] == "way":
            ways[el["id"]] = el.get("nodes", [])

    way_coords = {}
    for wid, node_ids in ways.items():
        coords = [nodes[nid] for nid in node_ids if nid in nodes]
        if len(coords) >= 2:
            way_coords[wid] = coords
    return way_coords


def _ways_to_polygon(way_coords):
    """Assemble boundary ways into a polygon."""
    lines = [LineString(coords) for coords in way_coords.values() if len(coords) >= 2]
    if not lines:
        return None

    merged = unary_union(lines)
    polys = list(polygonize(merged))

    if len(polys) == 1:
        return polys[0]
    elif len(polys) > 1:
        return unary_union(polys)
    else:
        from shapely.geometry import MultiPoint
        all_pts = [pt for line in lines for pt in line.coords]
        if all_pts:
            return MultiPoint(all_pts).convex_hull
        return None


def get_main_boundary(location_name):
    """
    Fetch the boundary polygon for the main neighborhood.
    Returns: dict with keys: name, polygon
    """
    print(f"\n--- Finding boundary for: {location_name} ---")

    query = f"""
    [out:json][timeout:{OVERPASS_TIMEOUT}];
    relation["boundary"="administrative"]["admin_level"="10"]["name"="{location_name}"];
    out body;
    >;
    out skel qt;
    """
    data = _overpass_query(query)

    relation = None
    for el in data["elements"]:
        if el["type"] == "relation":
            relation = el
            break

    if relation is None:
        # Try without admin_level filter
        query_relaxed = f"""
        [out:json][timeout:{OVERPASS_TIMEOUT}];
        relation["boundary"="administrative"]["name"="{location_name}"];
        out body;
        >;
        out skel qt;
        """
        data = _overpass_query(query_relaxed)
        for el in data["elements"]:
            if el["type"] == "relation":
                relation = el
                break

    if relation is None:
        raise ValueError(
            f"Could not find boundary relation for '{location_name}'. "
            f"Check the name on OpenStreetMap."
        )

    rel_name = relation.get("tags", {}).get("name", location_name)

    # Only use ways that are members of THIS relation
    member_way_ids = set()
    for member in relation.get("members", []):
        if member["type"] == "way":
            member_way_ids.add(member["ref"])

    way_coords = _extract_way_coords(data["elements"])
    # Filter to only our relation's ways
    way_coords = {wid: coords for wid, coords in way_coords.items() if wid in member_way_ids}
    polygon = _ways_to_polygon(way_coords)

    print(f"  Found: '{rel_name}' (relation {relation['id']})")

    return {"name": rel_name, "polygon": polygon}

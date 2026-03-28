# prepare.py
"""
Script 1: Prepare the graph and generate the interactive editing map.

Steps:
  1. Find the main neighborhood boundary polygon
  2. Download street network (main + margin buffer)
  3. Save the full graph to disk (dead-end removal happens later in solve.py)
  4. Generate the interactive HTML map in output/
"""

import sys
import os
import warnings

warnings.filterwarnings("ignore")
sys.setrecursionlimit(10000)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from src import boundaries, network, interface


def main():
    slug = config.SLUG
    print(f"=== PREPARE: {config.LOCATION} ({slug}) ===\n")
    os.makedirs("output", exist_ok=True)

    # 1. Find main boundary
    main_boundary = boundaries.get_main_boundary(
        location_name=config.LOCATION.split(",")[0].strip(),
    )

    # 2. Download street network (bbox with margin)
    org_graph, merged_graph = network.download_graph(
        main_boundary, config.CUSTOM_FILTER,
        margin_meters=config.MARGIN_METERS,
    )

    # 3. Save full graph to disk (no dead-end pruning here)
    network.save_graph(merged_graph, org_graph, filepath=f"output/{slug}_graph.pickle")

    # 4. Generate interactive map
    map_path = interface.generate_map_html(merged_graph, slug=slug)

    # 5. Open in browser via local server (OSM tiles require a valid Referer header)
    import webbrowser, functools
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    port = 8042
    handler = functools.partial(SimpleHTTPRequestHandler, directory="output")
    server = HTTPServer(("localhost", port), handler)
    filename = os.path.basename(map_path)
    webbrowser.open(f"http://localhost:{port}/{filename}")

    print(f"\n✅ Done! Serving map at http://localhost:{port}/{filename}")
    print(f"   When finished, click Export (saves {slug}_edits.json)")
    print("   Then press Ctrl+C and run: python solve.py")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    main()

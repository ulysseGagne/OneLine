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

    # 5. Open in browser
    import webbrowser
    webbrowser.open("file://" + os.path.abspath(map_path))

    print(f"\n✅ Done! Open output/{slug}_map.html to edit the graph.")
    print(f"   When finished, click Export (saves {slug}_edits.json)")
    print("   Then run: python solve.py")


if __name__ == "__main__":
    main()

# solve.py
"""
Script 2: Apply user edits and run the solver.

Steps:
  1. Load the saved graph from prepare.py
  2. Load the edits JSON exported from the interactive map
  3. Apply edits (delete, create, include, start/end)
  4. Run the longest-path solver
  5. Visualize results and export GPX
"""

import sys
import os
import warnings

warnings.filterwarnings("ignore")
sys.setrecursionlimit(10000)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from src import network, interface, solver, visualize, export


def main():
    slug = config.SLUG
    print(f"=== SOLVE: {config.LOCATION} ({slug}) ===\n")
    os.makedirs("output", exist_ok=True)

    # 1. Load graph
    print("--- Loading graph ---")
    graph, org_graph = network.load_graph(f"output/{slug}_graph.pickle")

    # 2. Load edits — always copy from ~/Downloads/ if present (most recent),
    #    then load from output/; warn and proceed with empty edits if absent.
    edits_name = f"{slug}_edits.json"
    edits_path = f"output/{edits_name}"
    downloads = os.path.expanduser(f"~/Downloads/{edits_name}")
    if os.path.exists(downloads):
        import shutil
        shutil.copy2(downloads, edits_path)
        print(f"  Copied {edits_name} from ~/Downloads/ to output/")
    if os.path.exists(edits_path):
        edits = interface.load_edits(edits_path)
    else:
        print(f"  WARNING: {edits_name} not found in output/ or ~/Downloads/. Proceeding with no edits.")
        edits = {}

    # 3. Apply edits
    graph, start_nodes, end_nodes = interface.apply_edits(graph, edits)

    # 4. Run solver
    print("\n--- Running solver ---")
    path_solver = solver.LongestPathSolver(
        graph, seed=config.SEED,
        start_nodes=start_nodes, end_nodes=end_nodes,
    )
    best_path, best_dist = path_solver.solve(time_budget=config.TIME_BUDGET_MINUTES * 60)

    if not best_path:
        print("No path found!")
        return

    # 5. Visualize & export
    print("\n--- Generating outputs ---")
    edge_path = visualize.path_nodes_to_edge_path(graph, best_path)
    visualize.plot_results(graph, best_path, best_dist, edge_path, slug=slug)
    visualize.plot_coverage(graph, best_path, slug=slug)
    export.export_gpx(org_graph, graph, edge_path, config.LOCATION, slug=slug)

    print(f"\n✅ All done! Check the 'output' folder for {slug}_* files.")


if __name__ == "__main__":
    main()

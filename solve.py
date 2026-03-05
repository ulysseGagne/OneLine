# solve.py
"""
Multi-restart solver with diverse path portfolio.

Runs indefinitely until Ctrl+C, keeping a portfolio of diverse high-quality
paths as GPX files in output/{slug}_routes/.
"""

import sys
import os
import time
import csv
import json
import warnings

warnings.filterwarnings("ignore")
sys.setrecursionlimit(10000)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from src import network, interface, solver, export
from src.portfolio import PathPortfolio


def main():
    slug = config.SLUG
    print(f"=== SOLVE: {config.LOCATION} ({slug}) ===\n")
    os.makedirs("output", exist_ok=True)

    # 1. Load graph
    print("--- Loading graph ---")
    graph, org_graph = network.load_graph(f"output/{slug}_graph.pickle")

    # 2. Load edits
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

    # 4. Remove dead-end nodes
    protected = (start_nodes or set()) | (end_nodes or set())
    graph = network.remove_dead_ends(graph, protected=protected)

    # Graph stats (after dead-end removal)
    n_nodes_graph = graph.number_of_nodes()
    n_edges_graph = graph.number_of_edges()

    # 5. Export debug GPX
    print("\n--- Exporting debug graph ---")
    export.export_debug_graph_gpx(graph, config.LOCATION, slug=slug)

    # 6. Create routes directory
    routes_dir = os.path.join("output", f"{slug}_routes")
    os.makedirs(routes_dir, exist_ok=True)

    # 7. Initialize portfolio
    portfolio = PathPortfolio(slug, routes_dir, org_graph, graph, config.LOCATION)

    # 8. Open solver log CSV
    log_path = os.path.join("output", f"{slug}_solver_log.csv")
    log_is_new = not os.path.exists(log_path)
    log_file = open(log_path, "a", newline="")
    log_writer = csv.writer(log_file)
    if log_is_new:
        log_writer.writerow([
            "iteration", "seed", "n_nodes_graph", "n_edges_graph", "time_budget",
            "n_improvements", "best_dist", "best_n_nodes", "coverage_pct",
            "last_improvement_time", "total_iter_time", "improvements_json",
        ])
        log_file.flush()

    # 9. Multi-restart loop
    time_budget = max(45, int(0.23 * n_nodes_graph))
    print(f"\n--- Multi-restart solver (Ctrl+C to stop) ---")
    print(f"    Per-iteration budget: {time_budget}s | Starting seed: {config.SEED}\n")

    session_start = time.time()
    iteration = 0
    seed = config.SEED

    try:
        while True:
            iteration += 1
            iter_start = time.time()

            print(f"--- Iteration {iteration} (seed={seed}) ---")

            # Fresh solver each iteration
            path_solver = solver.LongestPathSolver(
                graph, seed=seed,
                start_nodes=start_nodes, end_nodes=end_nodes,
                verbose=False,
            )
            best_path, best_dist = path_solver.solve(time_budget=time_budget)

            iter_time = time.time() - iter_start
            total_time = time.time() - session_start

            # Log iteration data
            improvements = getattr(path_solver, "improvements", [])
            n_improvements = len(improvements)
            last_improvement_time = improvements[-1][0] if improvements else 0.0
            best_n_nodes = len(best_path) if best_path else 0
            coverage_pct = best_n_nodes / n_nodes_graph * 100 if best_path else 0.0
            log_writer.writerow([
                iteration, seed, n_nodes_graph, n_edges_graph, time_budget,
                n_improvements, f"{best_dist:.2f}" if best_dist else 0,
                best_n_nodes, f"{coverage_pct:.2f}",
                f"{last_improvement_time:.2f}", f"{iter_time:.2f}",
                json.dumps([(round(t, 2), round(d, 2), n, p) for t, d, n, p in improvements]),
            ])
            log_file.flush()

            if best_path:
                status = portfolio.submit(best_path, best_dist, seed)
                n_nodes = len(best_path)
                pct = n_nodes / n_nodes_graph * 100
                print(
                    f"  Result: {best_dist/1000:.2f} km | "
                    f"{n_nodes}/{n_nodes_graph} nodes ({pct:.1f}%) | "
                    f"{iter_time:.1f}s | {status}"
                )
            else:
                print(f"  Result: no path found | {iter_time:.1f}s")

            print(
                f"  Portfolio: {len(portfolio.entries)} paths | "
                f"best: {portfolio.global_best_dist/1000:.2f} km | "
                f"total time: {total_time/60:.1f}min"
            )
            print()

            seed += 1

    except KeyboardInterrupt:
        log_file.close()
        total_time = time.time() - session_start
        print(f"\n\nStopped after {iteration} iterations ({total_time/60:.1f} minutes)")
        portfolio.summary()


if __name__ == "__main__":
    main()

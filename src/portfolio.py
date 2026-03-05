# src/portfolio.py
"""Portfolio of diverse high-quality paths with GPX lifecycle management."""

import os
from dataclasses import dataclass, field
from typing import List, Optional

from src.visualize import path_nodes_to_edge_path
from src.export import export_gpx


@dataclass
class PortfolioEntry:
    seed: int
    dist: float
    node_count: int
    total_nodes: int
    edge_set: frozenset
    path: list
    filename: str


class PathPortfolio:
    DIVERSITY_THRESHOLD = 0.10   # Jaccard distance below this = "too similar"
    NEAR_BEST_RATIO = 0.95      # paths within 95% of best are always kept
    MIN_VIABLE_RATIO = 0.70     # paths below 70% of best are auto-pruned

    def __init__(self, slug, routes_dir, org_graph, graph, location):
        self.slug = slug
        self.routes_dir = routes_dir
        self.org_graph = org_graph
        self.graph = graph
        self.location = location
        self.entries: List[PortfolioEntry] = []
        self.global_best_dist = 0.0

    def submit(self, path, dist, seed) -> str:
        """Submit a path to the portfolio. Returns status: ACCEPTED, REJECTED, or NEW_BEST."""
        if not path:
            return "REJECTED"

        # Reject if below minimum viable threshold
        if self.global_best_dist > 0 and dist < self.global_best_dist * self.MIN_VIABLE_RATIO:
            return "REJECTED"

        # Compute edge set
        edge_set = frozenset(
            (min(u, v), max(u, v))
            for u, v in zip(path[:-1], path[1:])
        )

        total_nodes = len(set(self.entries[0].path)) if self.entries else len(path)
        # Use the graph's node count from the first entry or current path
        if self.entries:
            total_nodes = self.entries[0].total_nodes

        is_near_best = dist >= self.global_best_dist * self.NEAR_BEST_RATIO if self.global_best_dist > 0 else True

        # If not near-best, check if dominated by any existing entry
        if not is_near_best:
            for entry in self.entries:
                jd = self._jaccard_distance(edge_set, entry.edge_set)
                if jd < self.DIVERSITY_THRESHOLD and dist <= entry.dist:
                    return "REJECTED"

        # Accept: create entry and export GPX
        dist_km = dist / 1000
        filename = f"{dist_km:06.2f}km_seed{seed}_{self.slug}.gpx"
        filepath = os.path.join(self.routes_dir, filename)

        edge_path = path_nodes_to_edge_path(self.graph, path)
        export_gpx(self.org_graph, self.graph, edge_path, self.location,
                   slug=self.slug, filepath=filepath, quiet=True)

        entry = PortfolioEntry(
            seed=seed,
            dist=dist,
            node_count=len(path),
            total_nodes=len(list(self.graph.nodes())),
            edge_set=edge_set,
            path=path,
            filename=filename,
        )
        self.entries.append(entry)

        status = "ACCEPTED"
        if dist > self.global_best_dist:
            self.global_best_dist = dist
            status = "NEW_BEST"
            pruned = self._prune()
            for p in pruned:
                print(f"  [pruned] Deleted {p.filename} ({p.dist/1000:.2f} km, seed {p.seed})")

        return status

    def _prune(self) -> list:
        """Remove entries that are dominated or below minimum viable ratio."""
        pruned = []
        keep = []

        for entry in self.entries:
            # Remove entries below minimum viable ratio of new best
            if entry.dist < self.global_best_dist * self.MIN_VIABLE_RATIO:
                pruned.append(entry)
                continue

            # Check if dominated by another entry (similar edges + shorter distance)
            dominated = False
            for other in self.entries:
                if other is entry:
                    continue
                if other.dist < self.global_best_dist * self.MIN_VIABLE_RATIO:
                    continue
                jd = self._jaccard_distance(entry.edge_set, other.edge_set)
                if jd < self.DIVERSITY_THRESHOLD and entry.dist < other.dist:
                    dominated = True
                    break

            if dominated:
                pruned.append(entry)
            else:
                keep.append(entry)

        # Delete GPX files for pruned entries
        for entry in pruned:
            filepath = os.path.join(self.routes_dir, entry.filename)
            if os.path.exists(filepath):
                os.remove(filepath)

        self.entries = keep
        return pruned

    @staticmethod
    def _jaccard_distance(set_a, set_b):
        """1 - |A intersection B| / |A union B|"""
        if not set_a and not set_b:
            return 0.0
        intersection = len(set_a & set_b)
        union = len(set_a | set_b)
        return 1.0 - intersection / union

    def summary(self):
        """Print final portfolio summary table."""
        if not self.entries:
            print("Portfolio is empty.")
            return

        # Sort by distance descending
        sorted_entries = sorted(self.entries, key=lambda e: -e.dist)
        best_entry = sorted_entries[0]

        print(f"\nFinal portfolio ({len(self.entries)} paths):")
        for i, entry in enumerate(sorted_entries, 1):
            pct = entry.node_count / entry.total_nodes * 100
            label = "  [BEST]" if entry is best_entry else ""
            jd = self._jaccard_distance(entry.edge_set, best_entry.edge_set) if entry is not best_entry else 0.0
            jd_str = f"  jd={jd:.2f}" if entry is not best_entry else ""
            print(
                f"  {i:>3}. seed={entry.seed:<5d} "
                f"{entry.dist/1000:6.2f} km  "
                f"{entry.node_count}/{entry.total_nodes} ({pct:.1f}%)"
                f"{jd_str}{label}"
            )

        print(f"\nRoutes saved in: {self.routes_dir}/")

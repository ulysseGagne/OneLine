# src/solver.py
import time
import numpy as np
from collections import defaultdict

def build_adjacency(G):
    """Pre-compute adjacency as {node: [(neighbor, edge_length), ...]}.

    When parallel edges exist between two nodes, only the LONGEST is kept
    (we want maximum distance).
    """
    best = {}
    for u, v, data in G.edges(data=True):
        length = data.get("length", 0)
        for a, b in [(u, v), (v, u)]:
            if (a, b) not in best or length > best[(a, b)]:
                best[(a, b)] = length

    adj = defaultdict(list)
    for (u, v), length in best.items():
        adj[u].append((v, length))
    return dict(adj)


class LongestPathSolver:
    """
    Multi-phase solver for the Longest Simple Path problem on street networks.

    Supports optional start_nodes / end_nodes constraints (sets of candidates).
    The solver finds the longest path whose first node is in start_nodes
    and whose last node is in end_nodes.
    """

    def __init__(self, G, seed=42, start_nodes=None, end_nodes=None,
                 verbose=True):
        self.G = G
        self.adj = build_adjacency(G)
        self.nodes = list(G.nodes())
        self.n = len(self.nodes)
        self.rng = np.random.default_rng(seed)
        self.verbose = verbose

        # None = unconstrained, otherwise a set of OSM node IDs
        self.start_nodes = start_nodes
        self.end_nodes = end_nodes

        self.total_edge_weight = sum(
            d.get("length", 0) for _, _, d in G.edges(data=True)
        )

        self.best_path = []
        self.best_dist = 0.0
        self.improvements = []
        self.t0 = None

    # ----- helpers -----

    def _print(self, *args, **kwargs):
        """Print only when verbose."""
        if self.verbose:
            print(*args, **kwargs)

    def _is_valid_path(self, path):
        """Check if path satisfies start/end constraints."""
        if not path:
            return False
        if self.start_nodes is not None and path[0] not in self.start_nodes:
            return False
        if self.end_nodes is not None and path[-1] not in self.end_nodes:
            return False
        return True

    def _update_best(self, path, dist, phase):
        if dist > self.best_dist and self._is_valid_path(path):
            self.best_dist = dist
            self.best_path = list(path)
            elapsed = time.time() - self.t0
            pct = len(path) / self.n * 100
            self.improvements.append((elapsed, dist, len(path), phase))
            self._print(
                f"  [{phase:>14s}] {dist/1000:7.2f} km | "
                f"{len(path):>4d}/{self.n} nodes ({pct:5.1f}%) | "
                f"{elapsed:6.1f}s"
            )

    def _warnsdorff_degree(self, node, visited):
        return sum(1 for nb, _ in self.adj.get(node, []) if nb not in visited)

    def _edge_length(self, u, v):
        for nb, l in self.adj.get(u, []):
            if nb == v:
                return l
        return 0.0

    def _get_start_candidates(self):
        """Return the list of valid starting nodes."""
        if self.start_nodes is not None:
            return list(self.start_nodes)
        return self.nodes

    # ================================================================== #
    # Phase 1 & 2 — Warnsdorff walks
    # ================================================================== #

    def warnsdorff_walk(self, start, randomize=False):
        visited = {start}
        path = [start]
        dist = 0.0
        current = start

        while True:
            neighbors = [
                (nb, length)
                for nb, length in self.adj.get(current, [])
                if nb not in visited
            ]
            if not neighbors:
                break

            scored = [
                (self._warnsdorff_degree(nb, visited), length, nb)
                for nb, length in neighbors
            ]

            if randomize and len(scored) > 1:
                max_deg = max(s[0] for s in scored) + 1
                weights = np.array([(max_deg - s[0]) + 0.3 for s in scored])
                lengths = np.array([s[1] for s in scored])
                weights *= 1.0 + 0.3 * lengths / (lengths.max() + 1e-9)
                weights /= weights.sum()
                idx = self.rng.choice(len(scored), p=weights)
            else:
                scored.sort(key=lambda s: (s[0], -s[1]))
                idx = 0

            _, edge_len, chosen = scored[idx]
            visited.add(chosen)
            path.append(chosen)
            dist += edge_len
            current = chosen

        return path, dist

    # ================================================================== #
    # Phase 3 — Local search (extend + reroute)
    # ================================================================== #

    def _extend_from_end(self, path, dist, from_end=True):
        """Greedily extend path from one endpoint. Respects constraints."""
        if from_end and self.end_nodes is not None:
            return path, dist
        if not from_end and self.start_nodes is not None:
            return path, dist

        visited = set(path)
        work = list(path) if from_end else list(reversed(path))
        current = work[-1]
        total = dist

        while True:
            neighbors = [
                (nb, l) for nb, l in self.adj.get(current, []) if nb not in visited
            ]
            if not neighbors:
                break
            neighbors.sort(
                key=lambda x: (
                    sum(1 for nb2, _ in self.adj.get(x[0], []) if nb2 not in visited),
                    -x[1],
                )
            )
            chosen, edge_len = neighbors[0]
            visited.add(chosen)
            work.append(chosen)
            total += edge_len
            current = chosen

        return (work if from_end else list(reversed(work))), total

    def _try_reroute(self, path, dist):
        n_path = len(path)
        if n_path < 10:
            return path, dist

        adj = self.adj
        best_path, best_dist = path, dist
        path_set = set(path)
        unused_nodes = set(self.nodes) - path_set

        if not unused_nodes:
            return path, dist

        attempts = min(n_path * 2, 300)
        lo = 2 if self.start_nodes is not None else 1
        hi = n_path - 3 if self.end_nodes is not None else n_path - 2
        if lo >= hi:
            return path, dist

        cuts = self.rng.integers(lo, hi, size=attempts)

        for cut_start in cuts:
            for seg_len in [2, 3, 4, 6, 8]:
                cut_end = int(cut_start) + seg_len
                if cut_end >= n_path:
                    continue
                if self.end_nodes is not None and cut_end >= n_path - 1:
                    continue

                node_a = path[int(cut_start) - 1]
                node_b = path[cut_end]
                removed = set(path[int(cut_start):cut_end])
                rest = path_set - removed

                allowed = (unused_nodes | removed | {node_a, node_b})

                alt = self._find_connecting_path(
                    node_a, node_b, allowed, rest, max_depth=seg_len + 8
                )
                if alt is None or len(alt) < 2:
                    continue

                old_d = sum(
                    self._edge_length(path[i], path[i + 1])
                    for i in range(int(cut_start) - 1, cut_end)
                )
                new_d = sum(
                    self._edge_length(alt[i], alt[i + 1])
                    for i in range(len(alt) - 1)
                )

                if new_d > old_d:
                    candidate = path[:int(cut_start)] + alt[1:-1] + path[cut_end:]
                    if len(set(candidate)) == len(candidate):
                        new_total = dist - old_d + new_d
                        if new_total > best_dist:
                            best_dist = new_total
                            best_path = candidate

        return best_path, best_dist

    def _find_connecting_path(self, start, end, allowed, forbidden, max_depth=12):
        usable = (allowed - forbidden) | {start, end}

        best = None
        best_dist = -1
        stack = [(start, [start], 0.0, {start})]
        ops = 0

        while stack and ops < 80000:
            ops += 1
            node, path, d, vis = stack.pop()

            if node == end and len(path) > 1 and d > best_dist:
                best = list(path)
                best_dist = d

            if len(path) >= max_depth:
                continue

            for nb, l in self.adj.get(node, []):
                if nb not in vis and nb in usable:
                    stack.append((nb, path + [nb], d + l, vis | {nb}))

        return best

    def local_search(self, deadline):
        """Iteratively improve best path via extension and rerouting."""
        improved = True
        rounds = 0
        while improved and time.time() < deadline:
            improved = False
            rounds += 1

            for from_end in [True, False]:
                new_path, new_dist = self._extend_from_end(
                    self.best_path, self.best_dist, from_end=from_end
                )
                if new_dist > self.best_dist and self._is_valid_path(new_path):
                    self._update_best(new_path, new_dist, "extend")
                    improved = True

            if time.time() < deadline:
                new_path, new_dist = self._try_reroute(
                    self.best_path, self.best_dist
                )
                if new_dist > self.best_dist and self._is_valid_path(new_path):
                    self._update_best(new_path, new_dist, "reroute")
                    improved = True

        self._print(f"  Local search: {rounds} rounds")

    # ================================================================== #
    # Main entry point
    # ================================================================== #

    def solve(self, time_budget=45):
        self.t0 = time.time()
        deadline = self.t0 + time_budget

        # Print constraints
        if self.verbose:
            if self.start_nodes:
                print(f"Start candidates: {len(self.start_nodes)} nodes")
            if self.end_nodes:
                print(f"End candidates:   {len(self.end_nodes)} nodes")
            if self.start_nodes or self.end_nodes:
                print()

        start_candidates = self._get_start_candidates()
        is_bidir = (self.start_nodes is not None and self.end_nodes is not None)

        # ---- Phase 1: deterministic Warnsdorff (4% of budget) ----
        phase1_end = self.t0 + time_budget * 0.04
        n_end = len(self.end_nodes) if is_bidir else 0
        self._print(f"Phase 1: Warnsdorff walks from {len(start_candidates)} start candidates"
              + (f" + {n_end} end candidates (bidir)" if is_bidir else "") + " ...")
        for node in start_candidates:
            if time.time() > phase1_end:
                break
            path, dist = self.warnsdorff_walk(node, randomize=False)
            self._update_best(path, dist, "warnsdorff")
        # Bidirectional: also walk from end_nodes (reversed paths)
        if is_bidir:
            for node in list(self.end_nodes):
                if time.time() > phase1_end:
                    break
                path, dist = self.warnsdorff_walk(node, randomize=False)
                self._update_best(list(reversed(path)), dist, "warnsdorff-rev")
        # If start is constrained but not bidir, seed from all nodes too
        if self.start_nodes is not None and not is_bidir:
            for node in self.nodes:
                if time.time() > phase1_end:
                    break
                path, dist = self.warnsdorff_walk(node, randomize=False)
                self._update_best(path, dist, "warnsdorff")
        self._print()

        # ---- Phase 2: randomized Warnsdorff (29% of budget) ----
        phase2_end = self.t0 + time_budget * 0.33
        end_candidates = list(self.end_nodes) if is_bidir else []
        self._print("Phase 2: Randomized Warnsdorff walks"
              + (" (bidir)" if is_bidir else "") + " ...")
        count = 0
        while time.time() < phase2_end:
            if is_bidir and self.rng.random() < 0.5:
                # Walk from a random end node, reverse before validating
                node = end_candidates[self.rng.integers(len(end_candidates))]
                path, dist = self.warnsdorff_walk(node, randomize=True)
                self._update_best(list(reversed(path)), dist, "rand-warn-rev")
            else:
                node = start_candidates[self.rng.integers(len(start_candidates))]
                path, dist = self.warnsdorff_walk(node, randomize=True)
                self._update_best(path, dist, "rand-warnsdorf")
            count += 1
        self._print(f"  ({count} walks)\n")

        # ---- Phase 3: local search (remaining 67% of budget) ----
        self._print("Phase 3: Local search (extend + reroute) ...")
        self.local_search(deadline)

        # Summary
        if self.verbose:
            elapsed = time.time() - self.t0
            pct = len(self.best_path) / self.n * 100 if self.best_path else 0
            print(f"\n{'='*60}")
            print(f"RESULT: {self.best_dist/1000:.2f} km")
            print(f"  Nodes visited: {len(self.best_path)}/{self.n} ({pct:.1f}%)")
            if self.best_path:
                print(f"  Start node:    {self.best_path[0]}")
                print(f"  End node:      {self.best_path[-1]}")
            print(f"  Total time:    {elapsed:.1f}s")
            print(f"  Improvements:  {len(self.improvements)}")
            print(f"{'='*60}")

        return self.best_path, self.best_dist

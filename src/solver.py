# src/solver.py
import time
import numpy as np
import networkx as nx
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

    def __init__(self, G, seed=42, start_nodes=None, end_nodes=None):
        self.G = G
        self.adj = build_adjacency(G)
        self.nodes = list(G.nodes())
        self.n = len(self.nodes)
        self.rng = np.random.default_rng(seed)

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
            print(
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
    # Phase 3 — Backtracking DFS with pruning
    # ================================================================== #

    def backtracking_dfs(self, start, deadline, start_idx=0, n_starts=1,
                         swap_constraints=False):
        """Backtracking DFS with optional constraint-swap for bidirectional search.

        swap_constraints=True: treat end_nodes as targets (used when running DFS
        from end_nodes; caller reverses the returned path before validation).
        """
        adj = self.adj
        # When swap_constraints, we look for paths that terminate at start_nodes
        end_set = (self.start_nodes if swap_constraints else self.end_nodes)

        visited = {start}
        path = [start]
        dist = 0.0
        remaining = self.total_edge_weight

        local_best_path = [start]
        local_best_dist = 0.0 if end_set is None else -1.0

        LOG_INTERVAL = 30.0
        last_log = time.time()
        backtracks = 0

        def sorted_neighbors(node):
            candidates = [
                (nb, l) for nb, l in adj.get(node, []) if nb not in visited
            ]
            candidates.sort(
                key=lambda x: (
                    sum(1 for nb2, _ in adj.get(x[0], []) if nb2 not in visited),
                    -x[1],
                )
            )
            return iter(candidates)

        stack = [sorted_neighbors(start)]
        dist_deltas = []
        remaining_deltas = []
        check_counter = 0

        while stack:
            check_counter += 1
            if check_counter & 0x1FFF == 0:
                now = time.time()
                if now > deadline:
                    break
                if now - last_log >= LOG_INTERVAL:
                    elapsed = now - self.t0
                    direction = "rev" if swap_constraints else "fwd"
                    print(
                        f"  [DFS {direction} {start_idx}/{n_starts}] "
                        f"{elapsed:6.1f}s elapsed | "
                        f"best {self.best_dist / 1000:.2f} km | "
                        f"{backtracks} backtracks"
                    )
                    last_log = now

            it = stack[-1]
            advanced = False

            for nb, edge_len in it:
                if nb in visited:
                    continue

                new_dist = dist + edge_len

                weight_reduction = sum(
                    l for nb2, l in adj.get(nb, []) if nb2 in visited
                )
                new_remaining = remaining - weight_reduction

                ceiling = max(self.best_dist, local_best_dist)
                if new_dist + new_remaining <= ceiling:
                    continue

                # Accept move
                visited.add(nb)
                path.append(nb)
                dist = new_dist
                dist_deltas.append(edge_len)
                remaining_deltas.append(weight_reduction)
                remaining = new_remaining

                # Update local best: if no end constraint, any position counts;
                # with end constraint, only when we're at a valid end node.
                if end_set is None:
                    if dist > local_best_dist:
                        local_best_dist = dist
                        local_best_path = list(path)
                elif nb in end_set:
                    if dist > local_best_dist:
                        local_best_dist = dist
                        local_best_path = list(path)

                stack.append(sorted_neighbors(nb))
                advanced = True
                break

            if not advanced:
                backtracks += 1
                stack.pop()
                if dist_deltas:
                    removed = path.pop()
                    visited.discard(removed)
                    dist -= dist_deltas.pop()
                    remaining += remaining_deltas.pop()

        return local_best_path, local_best_dist

    # ================================================================== #
    # Phase 4 — Local search
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

        print(f"  Local search: {rounds} rounds")

    # ================================================================== #
    # Main entry point
    # ================================================================== #

    def solve(self, time_budget=300):
        self.t0 = time.time()
        deadline = self.t0 + time_budget

        # Print constraints
        if self.start_nodes:
            print(f"Start candidates: {len(self.start_nodes)} nodes")
        if self.end_nodes:
            print(f"End candidates:   {len(self.end_nodes)} nodes")
        if self.start_nodes or self.end_nodes:
            print()

        start_candidates = self._get_start_candidates()
        is_bidir = (self.start_nodes is not None and self.end_nodes is not None)

        # ---- Phase 1 ----
        phase1_end = self.t0 + time_budget * 0.08
        n_end = len(self.end_nodes) if is_bidir else 0
        print(f"Phase 1: Warnsdorff walks from {len(start_candidates)} start candidates"
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
        print()

        # ---- Phase 2 ----
        phase2_end = self.t0 + time_budget * 0.20
        end_candidates = list(self.end_nodes) if is_bidir else []
        print("Phase 2: Randomized Warnsdorff walks"
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
        print(f"  ({count} walks)\n")

        # ---- Phase 3 ----
        phase3_end = self.t0 + time_budget * 0.88
        print("Phase 3: Backtracking DFS with pruning"
              + (" (bidir — splitting budget)" if is_bidir else "") + " ...")

        # Build list of DFS starts: constrained starts + best-path endpoints + high degree
        dfs_starts = list(start_candidates)
        if self.best_path:
            dfs_starts += [self.best_path[0], self.best_path[-1]]
        by_deg = sorted(self.nodes, key=lambda n: self.G.degree(n), reverse=True)
        if self.start_nodes is not None:
            dfs_starts += [n for n in by_deg[:15] if n in self.start_nodes]
        else:
            dfs_starts += by_deg[:15]
            try:
                dfs_starts += nx.periphery(self.G)[:10]
            except Exception:
                pass
        # Deduplicate
        seen = set()
        starts = []
        for s in dfs_starts:
            if s not in seen:
                seen.add(s)
                starts.append(s)

        # When bidir, split phase-3 budget in half
        if is_bidir:
            now = time.time()
            p3a_end = now + (phase3_end - now) / 2
        else:
            p3a_end = phase3_end

        remaining_time = p3a_end - time.time()
        per_start = remaining_time / max(len(starts), 1)

        for i, start in enumerate(starts):
            if time.time() > p3a_end:
                break
            node_deadline = min(time.time() + per_start, p3a_end)
            path, dist = self.backtracking_dfs(
                start, node_deadline, start_idx=i + 1, n_starts=len(starts)
            )
            self._update_best(path, dist, f"BT-DFS {i+1}/{len(starts)}")

        # Bidir second half: DFS from end_nodes with swapped constraints
        if is_bidir:
            end_dfs = list(self.end_nodes)
            end_dfs += [n for n in by_deg[:15] if n in self.end_nodes]
            seen_e = set()
            end_starts = []
            for s in end_dfs:
                if s not in seen_e:
                    seen_e.add(s)
                    end_starts.append(s)

            remaining_rev = phase3_end - time.time()
            per_start_rev = remaining_rev / max(len(end_starts), 1)
            print(f"  (bidir reverse phase: {len(end_starts)} end-node starts)")

            for i, start in enumerate(end_starts):
                if time.time() > phase3_end:
                    break
                node_deadline = min(time.time() + per_start_rev, phase3_end)
                path, dist = self.backtracking_dfs(
                    start, node_deadline, start_idx=i + 1, n_starts=len(end_starts),
                    swap_constraints=True
                )
                if path:
                    path = list(reversed(path))
                self._update_best(path, dist, f"BT-rev {i+1}/{len(end_starts)}")

        print()

        # ---- Phase 4 ----
        print("Phase 4: Local search (extend + reroute) ...")
        self.local_search(deadline)

        # Summary
        elapsed = time.time() - self.t0
        pct = len(self.best_path) / self.n * 100
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

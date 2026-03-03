REFACTOR — IMPLEMENTATION PLAN
═══════════════════════════════════════════════════════════════

16 changes, split into 5 logically-separated phases.
Do NOT implement all phases at once. Between each phase, output
updated files so the user can test. Always explain changes and
give issue diagnostics before solving problems.


PHASE 1 — Bug Fixes & Quick Wins [#1, #2, #7, #15]
─────────────────────────────────────────────────────
Files: map_template.html, solve.py, config.py

#1 — Edge deletion incorrectly "deletes" connected nodes
  PROBLEM: Deleting an edge in the HTML editor causes connected nodes to
  disappear. The user expects only the edge to be removed — every node
  with at least one remaining connection (including green/created edges)
  should be preserved. Only truly isolated nodes (0 connections of any
  kind) should be auto-removed.
  ROOT CAUSE: refreshLoneNodes() flags any main node with effective
  degree 0 as a "loneId", and getNodeEffectiveState() maps loneIds to
  "deleted". When an edge is deleted, its endpoints can drop to degree 0
  and get swept into loneIds — appearing deleted even though the user
  never deleted them.
  FIX: loneIds must only flag nodes that have zero connections across
  BOTH original (non-deleted) edges AND created (green) edges. A node
  with even one green connection must NOT be flagged. Verify
  getEffectiveDegree() counts created edges properly, and ensure loneIds
  never override user-created connections. Green edges count toward
  degree in all contexts.

#2 — Missing edits file should warn, not crash
  PROBLEM: Running solve.py without an edits file crashes.
  FIX: If no edits file exists in output/ or ~/Downloads/, print a
  console warning and proceed with an empty edits dict (no deletes, no
  creates, no start/end). If a file exists in ~/Downloads/ with the
  right name, always copy it to output/ (overwriting), since the
  downloaded file is always the most recent.

#7 — Time budget in minutes
  PROBLEM: TIME_BUDGET is in seconds, which is unintuitive for the user.
  FIX: Rename to TIME_BUDGET_MINUTES, default 20. In solve.py, convert:
  time_budget=config.TIME_BUDGET_MINUTES * 60.

#15 — Cmd-Shift-Z redo shortcut in the HTML file
  FIX: Add a redoStack array. Each doUndo() pushes the reversed action
  onto redoStack. Each new user action clears redoStack. Cmd-Shift-Z /
  Ctrl-Shift-Z pops from redoStack and re-applies the action.


PHASE 2 — Dead-End Logic Rethink [#4, #5]
──────────────────────────────────────────
Files: network.py, prepare.py, solve.py, interface.py, map_template.html, export.py

#4 — Rethink dead-end removal entirely
  PROBLEM: Dead ends are pruned in prepare.py BEFORE the HTML map is
  generated. The user never sees them and can't decide what to do with
  them. Dead-end removal should happen later, after the user has had a
  chance to manually connect them.
  DEFINITION: A dead end is a node with effective degree <= 1. Self-loops
  ("relations unaires", i.e. edges where u == v) do NOT count toward
  degree. A node with one real neighbor and one self-loop IS a dead end.
  NEW BEHAVIOR:
    a) Remove the prune_dead_ends() call from prepare.py entirely. Pass
       the full unpruned graph to the HTML generator.
    b) In the HTML map, display dead-end nodes in ORANGE (same color as
       boundary-crossing edges). Dead-end coloring must be dynamic and
       recursive: if the user connects a dead-end to another node via a
       green edge, it is no longer a dead end and its color updates
       immediately. Conversely, deleting an edge that makes a node become
       a dead end should turn it orange instantly.
    c) In solve.py, AFTER applying user edits (interface.apply_edits) but
       BEFORE the pathfinding algo, add a recursive function to remove
       all dead-end nodes. This iteratively removes nodes with degree <= 1
       (ignoring self-loops) until no dead ends remain. Nodes that were
       dead ends in the original graph but were manually connected by the
       user will have degree >= 2 and survive the pruning.

#5 — Pre-solve debug GPX export
  FIX: After edits are applied and dead-ends pruned in solve.py, but
  BEFORE the pathfinding algo starts, export a GPX of all edges in the
  final graph to output/{slug}_debug_graph.gpx. The user can load this
  in a mapping app to verify the graph is valid before waiting 20 min
  for the solver. One <trk> per edge or one big multitrack.


PHASE 3 — HTML Editor Modes & UX [#14, #11, #13, #10]
──────────────────────────────────────────────────────
Files: map_template.html

#14 — Split "Create" into two separate side-menu options
  PROBLEM: The single "Create" mode handles three distinct actions (place
  new node, include grey node, draw edge), which is confusing and
  error-prone.
  FIX: Replace the single "Create" button with two buttons:
    - "Add Node" (green) — click empty space to create a green node;
      click a grey node to include it (turn it green).
    - "Draw Edge" (green) — click two existing nodes to draw an edge
      between them.
  Update the mode grid layout accordingly (may need 3-col or extra row
  for 5+ buttons).

#11 — Allow deleting created (green) edges
  PROBLEM: Delete mode only works on original (blue/orange) edges via
  edgeLineMap. Created green edges in createdLines are not clickable
  for deletion.
  FIX: Make created edge polylines respond to click events in delete
  mode. On click, remove the edge from createdEdges/createdLines and
  remove the polyline from the map. Push to undo stack. There should be
  no functional difference between green and blue nodes/edges for
  deletion purposes (they obviously differ in other ways — color,
  origin — but deletion treats them identically).

#13 — Larger hitboxes for edges and nodes
  PROBLEM: Edges and nodes are hard to click on the map.
  FIX: Increase node marker radius from 5 to 7 for main nodes. For
  edges, add invisible wider polylines (weight: 16-20, opacity: 0)
  underneath visible ones to act as click targets. This is the standard
  Leaflet pattern for making thin lines easier to click.

#10 — Prevent creating a new node within a few meters of an existing one
  FIX: Before placing a new node, compute haversine distance to every
  existing node (original + created). If any node is within ~5 meters,
  reject the placement and optionally flash a brief warning. This
  prevents accidental duplicate nodes that cause graph issues.


PHASE 4 — Advanced HTML Features [#3, #6, #9, #12]
───────────────────────────────────────────────────
Files: map_template.html, interface.py

#3 — Including a grey node reveals its edges for chain-inclusion
  PROBLEM: When a secondary (grey) node is included, it turns green,
  but its edges to other grey nodes remain hidden. The user can't see
  or reach the next layer of grey nodes.
  FIX: When a secondary node is included, iterate over EDGES to find
  all edges connected to it. Draw those edges on the map, colored by
  endpoint state: both included = green, one included + one secondary
  = orange. Update edge colors dynamically via the standard refresh
  logic. This lets the user chain-include grey nodes one layer at a
  time, extending the graph into secondary territory.

#6 — All colors should be dynamic, recursive, and accurate
  PROBLEM: Node and edge colors must reflect the actual state of the
  graph at all times, accounting for every feature (dead-end orange,
  split purple, revealed secondary edges, created green, etc.).
  FIX: Audit every user action to ensure it triggers a full refresh
  of affected node/edge colors. The color priority cascade is:
    Start/End > Deleted (red) > Dead-end (orange) > Included (green)
    > Created (green) > Main (blue) > Secondary (grey)
  Edge colors derive from their endpoint states. Purple (split) is
  cosmetic only — underneath, split edges are standard green.

#9 — Auto-import existing edits when opening the HTML file
  PROBLEM: Every time the user re-runs prepare.py and opens the map,
  they lose all previous edits unless they manually re-import.
  CHALLENGE: Local file:// pages can't fetch adjacent files via JS.
  SOLUTION: In interface.py's generate_map_html(), check if an edits
  JSON file already exists in output/ or ~/Downloads/. If so, read it
  and inject it into the HTML as a JS variable (same pattern as NODES
  and EDGES are injected). On page load, if this variable is non-null,
  call applyImport() automatically. The manual Import button remains
  as a fallback for loading different edit files.

#12 — SPLIT tool: add a new node ON an existing edge
  NEW MODE: Add a "Split" button (purple) to the side menu.
  BEHAVIOR: In split mode, user clicks an existing edge. A new purple
  node is created at the closest point on the edge geometry to the
  click location. Under the hood:
    a) The original A-C edge is deleted (added to deletedEdges).
    b) Two new edges A-B and B-C are created. These edges FOLLOW the
       original edge's curved road geometry, split at the click point.
       They are NOT straight lines.
    c) The new node and its two sub-edges are colored PURPLE visually,
       but internally they are standard created (green) nodes/edges.
       A "split" flag controls the purple rendering only.
    d) All normal operations (delete, undo, start/end, etc.) work on
       purple nodes/edges identically to green ones.


PHASE 5 — Solver Enhancements [#8, #16]
────────────────────────────────────────
Files: solver.py

#8 — More console logs during Phase 3
  PROBLEM: With a 20-min time budget, there are multi-minute stretches
  during Phase 3 (backtracking DFS) where it looks like nothing is
  happening.
  FIX: During backtracking_dfs(), add a time-based progress log. Every
  ~30 seconds, print a status line showing: elapsed time, current DFS
  start node index, current best distance, and number of backtrack
  operations performed.

#16 — Bidirectional solver (implement LAST)
  OVERVIEW: Instead of "start at A, find B," shift to "connect A and B,
  starting from whichever side works best." By passing both endpoints
  into the algorithm as valid starting locations, the search becomes
  much more resilient. This only activates when BOTH start_nodes and
  end_nodes are set by the user. If only one or neither is set, the
  solver behaves exactly as before.

  Phase 1 — Initial Fast-Walks:
    CURRENT: One greedy walk from the designated start.
    UPGRADE: Launch deterministic Warnsdorff walks from BOTH start_nodes
    AND end_nodes — two independent walks. Walks originating from end
    nodes are reversed before validation (start constraint checked at
    path[0], end at path[-1]). Doubles the baseline paths instantly.

  Phase 2 — Randomized Spray:
    CURRENT: Thousands of randomized walks all launched from start nodes.
    UPGRADE: Randomly alternate the drop-zone between start_nodes and
    end_nodes before each walk. Same reversal logic for end-originated
    walks. If one endpoint is geographically trapped (dense subdivision,
    dead ends), the other still gets thousands of chances to explore.

  Phase 3 — Heavy-Duty DFS:
    CURRENT: Systematic backtracking DFS radiating from start nodes only.
    UPGRADE: Split the Phase 3 time budget in half. First half: DFS from
    start nodes (normal). Second half: DFS from end nodes with the graph
    "flipped" — treat end_nodes as starts and start_nodes as ends, then
    reverse the resulting path. Finding A→B is often much harder than
    B→A depending on intersection layout. This guarantees we don't burn
    the entire budget fighting a bad direction.

  Phase 4 — Local Search:
    No changes needed. It already works on the best path regardless of
    which direction produced it.

  KISS: This keeps the architecture simple — no new data structures, no
  bidirectional search merging. Just run the same algorithm twice from
  opposite ends and keep the better result.

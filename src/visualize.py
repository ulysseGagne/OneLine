# src/visualize.py

def path_nodes_to_edge_path(G, path_nodes):
    """Convert node list to (u, v, key) edge tuples."""
    edge_path = []
    for u, v in zip(path_nodes[:-1], path_nodes[1:]):
        if G.has_edge(u, v):
            keys = list(G[u][v].keys())
            best_key = max(keys, key=lambda k: G[u][v][k].get("length", 0))
            edge_path.append((u, v, best_key))
        elif G.has_edge(v, u):
            keys = list(G[v][u].keys())
            best_key = max(keys, key=lambda k: G[v][u][k].get("length", 0))
            edge_path.append((v, u, best_key))
        else:
            print(f"Warning: no edge between {u} and {v}")
    return edge_path

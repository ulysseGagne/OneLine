# src/visualize.py
import osmnx as ox
import matplotlib.pyplot as plt
import os

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


def plot_results(graph, best_path, best_dist, edge_path, slug="route"):
    """Draw the route map with a color gradient and save it."""
    fig, ax = ox.plot_graph(
        graph, show=False, close=False,
        node_size=0, edge_color="#dddddd", edge_linewidth=0.5, bgcolor="w",
    )

    n_edges = len(edge_path)
    cmap = plt.cm.viridis

    for i, (u, v, k) in enumerate(edge_path):
        data = graph.edges.get((u, v, k), graph.edges.get((v, u, k), {}))
        if "geometry" in data:
            xs, ys = data["geometry"].xy
        else:
            xs = [graph.nodes[u]["x"], graph.nodes[v]["x"]]
            ys = [graph.nodes[u]["y"], graph.nodes[v]["y"]]
        ax.plot(xs, ys, color=cmap(i / max(n_edges - 1, 1)),
                linewidth=2.5, alpha=0.85, solid_capstyle="round")

    sx, sy = graph.nodes[best_path[0]]["x"], graph.nodes[best_path[0]]["y"]
    ex, ey = graph.nodes[best_path[-1]]["x"], graph.nodes[best_path[-1]]["y"]
    ax.scatter([sx], [sy], c="green", s=100, zorder=5, edgecolors="k", linewidths=1.5, label="Start")
    ax.scatter([ex], [ey], c="red", s=100, zorder=5, edgecolors="k", linewidths=1.5, label="End")
    ax.legend(loc="upper right", framealpha=0.9, fontsize=10)

    pct = len(best_path) / graph.number_of_nodes() * 100
    plt.title(
        f"Longest Simple Path — {best_dist/1000:.2f} km, "
        f"{len(best_path)}/{graph.number_of_nodes()} nodes ({pct:.1f}%)",
        fontsize=11,
    )
    plt.tight_layout()
    
    # Save instead of show
    filepath = os.path.join("output", f"{slug}_route.png")
    plt.savefig(filepath, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"Route map saved: {filepath}")


def plot_coverage(graph, best_path, slug="route"):
    """Draw a map showing visited (blue) vs missed (red) streets and save it."""
    visited_set = set(best_path)
    fig, ax = plt.subplots(figsize=(10, 10), facecolor="white")
    
    for u, v, data in graph.edges(data=True):
        if "geometry" in data:
            xs, ys = data["geometry"].xy
        else:
            xs = [graph.nodes[u]["x"], graph.nodes[v]["x"]]
            ys = [graph.nodes[u]["y"], graph.nodes[v]["y"]]
        
        if u in visited_set and v in visited_set:
            ax.plot(xs, ys, color="#2196F3", linewidth=1.5, alpha=0.6)
        else:
            ax.plot(xs, ys, color="#FF5722", linewidth=2.5, alpha=0.9)

    ax.set_aspect("equal")
    ax.set_title("Coverage: Blue = visited, Red = missed", fontsize=11)
    ax.axis("off")
    plt.tight_layout()
    
    # Save instead of show
    filepath = os.path.join("output", f"{slug}_coverage.png")
    plt.savefig(filepath, dpi=300, bbox_inches='tight')
    plt.close(fig)
    print(f"Coverage map saved: {filepath}")

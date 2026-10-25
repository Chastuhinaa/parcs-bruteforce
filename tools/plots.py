import sys, csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

BLUE, GREEN, GREY, DARK = "#2563eb", "#16a34a", "#9ca3af", "#1f2937"


def architecture(path):
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.set_xlim(0, 10); ax.set_ylim(0, 10); ax.axis("off")

    def box(x, y, w, h, title, sub, color):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.08",
                                    linewidth=1.5, edgecolor=color,
                                    facecolor=color + "22"))
        ax.text(x + w / 2, y + h - 0.32, title, ha="center", va="top",
                fontsize=11, fontweight="bold", color=DARK)
        ax.text(x + w / 2, y + 0.28, sub, ha="center", va="bottom",
                fontsize=8, color=DARK)

    box(0.6, 7.6, 3.4, 1.8, "app  (root module)",
        "e2-standard-2\nsplits keyspace [0,K)\nmeasures baseline", BLUE)
    box(6.0, 7.6, 3.4, 1.8, "hosts-server  :3333",
        "e2-micro\nhands out free\ndaemon addresses", GREEN)
    for i in range(4):
        box(0.4 + i * 2.45, 1.2, 2.1, 2.6, f"daemon-{i+1}  :2222",
            "e2-standard-2\n2x HashCrack\n(worker JVM)", DARK)

    def arrow(x0, y0, x1, y1, text, dx=0.0, dy=0.25):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1),
                     arrowstyle="-|>", mutation_scale=14,
                     linewidth=1.3, color=DARK))
        ax.text((x0 + x1) / 2 + dx, (y0 + y1) / 2 + dy, text,
                ha="center", fontsize=8, color=DARK)

    arrow(4.0, 8.9, 6.0, 8.9, "1. get a free host")
    arrow(6.0, 8.2, 4.0, 8.2, "2. daemon address", dy=-0.35)
    arrow(1.9, 7.6, 1.9, 3.8, "3. execute worker +\njob [start, end)", dx=-0.9, dy=0.0)
    arrow(4.3, 3.8, 3.2, 7.6, "4. found index", dx=1.15, dy=-0.1)

    ax.text(5, 9.7, "PARCS brute-force — deployment on Google Compute Engine",
            ha="center", fontsize=12, fontweight="bold", color=DARK)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("wrote", path)


def read_csv(path):
    seq = None; w = []; best = []; speedup = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            n = int(row["workers"])
            if n == 0:
                seq = float(row["best_s"])
            else:
                w.append(n); best.append(float(row["best_s"]))
                speedup.append(float(row["speedup"]))
    return seq, w, best, speedup


def time_plot(path, seq, w, best):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(w, best, "o-", color=BLUE, linewidth=2, markersize=7, label="parallel (PARCS)")
    ax.axhline(seq, linestyle="--", color=GREY, linewidth=1.5,
               label=f"sequential = {seq:.2f} s")
    for x, y in zip(w, best):
        ax.annotate(f"{y:.2f}", (x, y), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8)
    ax.set_xlabel("number of workers"); ax.set_ylabel("execution time, s")
    ax.set_title("Execution time vs number of workers")
    ax.set_xticks(w); ax.grid(True, alpha=0.3); ax.legend()
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close(fig)
    print("wrote", path)


def speedup_plot(path, w, speedup):
    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.plot(w, w, "--", color=GREY, linewidth=1.5, label="ideal (linear)")
    ax.plot(w, speedup, "o-", color=BLUE, linewidth=2, markersize=7, label="measured")
    for x, y in zip(w, speedup):
        ax.annotate(f"{y:.2f}x", (x, y), textcoords="offset points",
                    xytext=(0, 8), ha="center", fontsize=8)
    ax.set_xlabel("number of workers"); ax.set_ylabel("speedup")
    ax.set_title("Speedup vs number of workers")
    ax.set_xticks(w); ax.grid(True, alpha=0.3); ax.legend()
    fig.savefig(path, dpi=150, bbox_inches="tight"); plt.close(fig)
    print("wrote", path)


if __name__ == "__main__":
    out = sys.argv[2] if len(sys.argv) > 2 else "results"
    os.makedirs(out, exist_ok=True)
    architecture(os.path.join(out, "architecture.png"))
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        seq, w, best, speedup = read_csv(sys.argv[1])
        time_plot(os.path.join(out, "time.png"), seq, w, best)
        speedup_plot(os.path.join(out, "speedup.png"), w, speedup)

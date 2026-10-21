# report.py
# Generates final security vs usability comparison report and tradeoff plot.

import csv
import os
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend suitable for headless scripts
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt

RESULTS_DIR = "results"
SUMMARY_CSV = os.path.join(RESULTS_DIR, "summary.csv")
USABILITY_CSV = os.path.join(RESULTS_DIR, "usability_summary.csv")
REPORT_MD = os.path.join(RESULTS_DIR, "REPORT.md")
TRADEOFF_PNG = os.path.join(RESULTS_DIR, "tradeoff.png")

# Colour palette by configuration type
TYPE_COLORS = {
    "baseline": "#7f7f7f",      # Grey
    "guards": "#ff7f0e",        # Orange
    "prompt_only": "#2ca02c",   # Green
}


def normalize_guards(guards_val: str) -> str:
    """Normalize guards string for consistent dictionary key lookup."""
    clean = guards_val.strip().strip('"').lower()
    if clean in ("", "none"):
        return "none"
    parts = [p.strip() for p in clean.split(",") if p.strip()]
    return ",".join(sorted(parts))


def get_config_type(prompt: str, guards: str) -> str:
    """Classify configuration into baseline, guards, or prompt-only."""
    if guards != "none":
        return "guards"
    if prompt in ("v3_hardened", "v4_no_secret"):
        return "prompt_only"
    return "baseline"


def read_latest_summary(file_path: str, percent_col_name: str) -> dict:
    """Read summary CSV and keep the most recent row for each (model, prompt, guards)."""
    if not os.path.exists(file_path):
        return {}

    latest_entries = {}
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            model = row.get("model", "").strip()
            prompt = row.get("prompt", "").strip()
            guards = normalize_guards(row.get("guards", "none"))
            timestamp = row.get("timestamp", "").strip()

            if not model or not prompt:
                continue

            key = (model, prompt, guards)
            if key not in latest_entries or timestamp >= latest_entries[key]["timestamp"]:
                latest_entries[key] = {
                    "timestamp": timestamp,
                    "model": model,
                    "prompt": prompt,
                    "guards": guards,
                    "percent": float(row.get(percent_col_name, 0.0)),
                    "raw_row": row,
                }
    return latest_entries


def format_individual_name(prompt: str, guards: str) -> str:
    """Format single configuration name."""
    if guards == "none":
        return prompt
    return f"{prompt} ({guards})"


def compute_offsets(unique_points: list[dict]) -> list[tuple[int, int]]:
    """Compute non-overlapping (x, y) text offsets for plot labels."""
    offsets = []
    # Sort points primarily by x, then by y
    for i, pt in enumerate(unique_points):
        x_i = pt["x"]
        y_i = pt["y"]

        # Check preceding points that are nearby in (x, y)
        nearby_preceding = [
            j for j in range(i)
            if abs(x_i - unique_points[j]["x"]) <= 12 and abs(y_i - unique_points[j]["y"]) <= 18
        ]

        if not nearby_preceding:
            # Baseline offset
            offset_y = 12 if y_i < 80 else -18
            offset_x = 10 if x_i < 70 else -10
        else:
            # Stagger higher above previous nearby labels
            stack_level = len(nearby_preceding)
            offset_x = 12 + (stack_level * 2)
            offset_y = 12 + (stack_level * 22)

        offsets.append((offset_x, offset_y))
    return offsets


def generate_report():
    os.makedirs(RESULTS_DIR, exist_ok=True)

    sec_entries = read_latest_summary(SUMMARY_CSV, "attack_success_percent")
    usab_entries = read_latest_summary(USABILITY_CSV, "false_refusal_percent")

    # Find common (model, prompt, guards) combinations
    common_keys = sorted(set(sec_entries.keys()) & set(usab_entries.keys()))

    matched_data = []
    for key in common_keys:
        sec = sec_entries[key]
        usab = usab_entries[key]
        model, prompt, guards = key

        label = format_individual_name(prompt, guards)
        cfg_type = get_config_type(prompt, guards)
        matched_data.append({
            "model": model,
            "prompt": prompt,
            "guards": guards,
            "config_label": label,
            "config_type": cfg_type,
            "attack_success": sec["percent"],
            "false_refusal": usab["percent"],
        })

    # Sort by attack success % (ascending), then false refusal %
    matched_data.sort(key=lambda x: (x["attack_success"], x["false_refusal"]))

    # 1. Write REPORT.md
    with open(REPORT_MD, "w", encoding="utf-8") as f:
        f.write("# Security vs Usability Report\n\n")
        f.write(
            "Comparison of **Attack Success Rate** (security risk) and "
            "**False Refusal Rate** (usability penalty) across evaluated configurations.\n\n"
        )
        f.write("## Configuration Summary\n\n")
        f.write("| Configuration | Attack Success % | False Refusal % |\n")
        f.write("| :--- | :---: | :---: |\n")

        if matched_data:
            for item in matched_data:
                f.write(
                    f"| {item['config_label']} | {item['attack_success']:.1f}% | {item['false_refusal']:.1f}% |\n"
                )
        else:
            f.write("| *(No matching configurations found)* | - | - |\n")

        f.write("\n## Tradeoff Visualization\n\n")
        f.write("![Security vs usability](tradeoff.png)\n")

    print(f"Generated report: {REPORT_MD}")

    # 2. Combine co-located points and build plot
    # Group items by exact (false_refusal, attack_success) position
    grouped_points = {}
    for item in matched_data:
        pos = (round(item["false_refusal"], 1), round(item["attack_success"], 1))
        grouped_points.setdefault(pos, []).append(item)

    unique_points = []
    for (x, y), items in grouped_points.items():
        # Determine joined label
        if len(items) == 1:
            joined_label = items[0]["config_label"]
            point_type = items[0]["config_type"]
        else:
            # If all share guards == "none", combine prompt names cleanly
            if all(it["guards"] == "none" for it in items):
                joined_label = " / ".join(it["prompt"] for it in items)
            else:
                joined_label = " / ".join(it["config_label"] for it in items)

            # Determine dominant type for color
            types_present = [it["config_type"] for it in items]
            if "guards" in types_present:
                point_type = "guards"
            elif "prompt_only" in types_present:
                point_type = "prompt_only"
            else:
                point_type = "baseline"

        unique_points.append({
            "x": x,
            "y": y,
            "label": joined_label,
            "type": point_type,
            "color": TYPE_COLORS[point_type],
        })

    # Sort unique points for predictable offset ordering
    unique_points.sort(key=lambda p: (p["x"], p["y"]))
    offsets = compute_offsets(unique_points)

    plt.figure(figsize=(10, 7.5))
    plt.title("Security vs usability", fontsize=15, fontweight="bold", pad=14)
    plt.xlabel("False Refusal %", fontsize=12, labelpad=10)
    plt.ylabel("Attack Success %", fontsize=12, labelpad=10)
    plt.xlim(0, 100)
    plt.ylim(0, 100)
    plt.grid(True, linestyle="--", alpha=0.5)

    # Plot points and non-overlapping labels
    for pt, (ox, oy) in zip(unique_points, offsets):
        plt.scatter(
            pt["x"],
            pt["y"],
            color=pt["color"],
            edgecolors="#1a1a1a",
            linewidth=1.2,
            s=130,
            zorder=5,
        )

        use_arrow = (oy > 20)
        arrowprops = (
            dict(arrowstyle="-", color="#666666", lw=0.8, alpha=0.7)
            if use_arrow
            else None
        )

        plt.annotate(
            pt["label"],
            (pt["x"], pt["y"]),
            textcoords="offset points",
            xytext=(ox, oy),
            fontsize=9.5,
            fontweight="medium",
            arrowprops=arrowprops,
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#bbbbbb", alpha=0.88, lw=0.6),
            zorder=6,
        )

    # Add small legend for configuration types
    legend_elements = [
        Line2D(
            [0], [0],
            marker="o",
            color="w",
            label="Baseline",
            markerfacecolor=TYPE_COLORS["baseline"],
            markeredgecolor="#1a1a1a",
            markersize=9,
        ),
        Line2D(
            [0], [0],
            marker="o",
            color="w",
            label="Prompt-only fix",
            markerfacecolor=TYPE_COLORS["prompt_only"],
            markeredgecolor="#1a1a1a",
            markersize=9,
        ),
        Line2D(
            [0], [0],
            marker="o",
            color="w",
            label="Guardrails",
            markerfacecolor=TYPE_COLORS["guards"],
            markeredgecolor="#1a1a1a",
            markersize=9,
        ),
    ]
    plt.legend(handles=legend_elements, loc="upper right", frameon=True, fontsize=10, framealpha=0.92)

    plt.tight_layout()
    plt.savefig(TRADEOFF_PNG, dpi=300)
    plt.close()
    print(f"Saved tradeoff plot: {TRADEOFF_PNG}")


if __name__ == "__main__":
    generate_report()

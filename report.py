# report.py
# Generates final security vs usability comparison report and tradeoff plot.

import csv
import os
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend suitable for headless scripts
import matplotlib.pyplot as plt

RESULTS_DIR = "results"
SUMMARY_CSV = os.path.join(RESULTS_DIR, "summary.csv")
USABILITY_CSV = os.path.join(RESULTS_DIR, "usability_summary.csv")
REPORT_MD = os.path.join(RESULTS_DIR, "REPORT.md")
TRADEOFF_PNG = os.path.join(RESULTS_DIR, "tradeoff.png")


def normalize_guards(guards_val: str) -> str:
    """Normalize guards string for consistent dictionary key lookup."""
    clean = guards_val.strip().strip('"').lower()
    if clean in ("", "none"):
        return "none"
    parts = [p.strip() for p in clean.split(",") if p.strip()]
    return ",".join(sorted(parts))


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
            # Since rows are appended chronologically, or we can compare timestamps
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


def format_config_label(prompt: str, guards: str) -> str:
    """Format a human-readable configuration label."""
    if guards == "none":
        return f"{prompt} (no guards)"
    return f"{prompt} ({guards})"


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

        label = format_config_label(prompt, guards)
        matched_data.append({
            "model": model,
            "prompt": prompt,
            "guards": guards,
            "config_label": label,
            "attack_success": sec["percent"],
            "false_refusal": usab["percent"],
        })

    # Sort by attack success % (ascending)
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

    # 2. Generate scatter plot using matplotlib
    plt.figure(figsize=(10, 7))
    plt.title("Security vs usability", fontsize=15, fontweight="bold", pad=14)
    plt.xlabel("False Refusal %", fontsize=12, labelpad=10)
    plt.ylabel("Attack Success %", fontsize=12, labelpad=10)
    plt.xlim(0, 100)
    plt.ylim(0, 100)
    plt.grid(True, linestyle="--", alpha=0.6)

    # Add quadrant / reference guide regions
    plt.axhline(50, color="gray", linestyle=":", alpha=0.3)
    plt.axvline(50, color="gray", linestyle=":", alpha=0.3)

    if matched_data:
        xs = [item["false_refusal"] for item in matched_data]
        ys = [item["attack_success"] for item in matched_data]
        labels = [item["config_label"] for item in matched_data]

        plt.scatter(
            xs,
            ys,
            color="#2b5c8f",
            edgecolors="#123050",
            s=120,
            alpha=0.9,
            zorder=4,
        )

        for x, y, label in zip(xs, ys, labels):
            plt.annotate(
                label,
                (x, y),
                textcoords="offset points",
                xytext=(8, 6),
                fontsize=9.5,
                fontweight="medium",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.7),
            )

    plt.tight_layout()
    plt.savefig(TRADEOFF_PNG, dpi=300)
    plt.close()
    print(f"Saved tradeoff plot: {TRADEOFF_PNG}")


if __name__ == "__main__":
    generate_report()

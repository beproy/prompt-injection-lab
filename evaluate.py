# evaluate.py
# Evaluation harness to test prompt injection test cases against Acme Gadgets chatbot.

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
from google import genai

from bot import get_bot_reply
from prompts import SYSTEM_PROMPTS
from scorer import score_reply

load_dotenv()

SEVERITY = {
    "leaked": 3,
    "partial": 2,
    "safe": 1,
}


def worse_verdict(v1: str, v2: str) -> str:
    """Return the worse of two verdicts (leaked > partial > safe)."""
    return v1 if SEVERITY.get(v1, 0) >= SEVERITY.get(v2, 0) else v2


def call_bot_with_retry(
    history: list[dict],
    user_message: str,
    system_prompt: str,
    model: str,
    client: genai.Client,
    max_retries: int = 3,
    delay_between_calls: float = 2.0,
) -> str:
    """Call Gemini with delay between calls and automatic retry on 429 rate limits."""
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(delay_between_calls)
            return get_bot_reply(
                history=history,
                user_message=user_message,
                system_prompt=system_prompt,
                model=model,
                client=client,
            )
        except Exception as e:
            err_msg = str(e).lower()
            is_rate_limit = (
                "429" in err_msg
                or "resource_exhausted" in err_msg
                or "quota" in err_msg
                or "rate limit" in err_msg
            )
            if is_rate_limit and attempt < max_retries:
                wait_time = 5 * attempt
                print(f"\n  [Rate Limit 429] Waiting {wait_time}s before retry {attempt}/{max_retries}...")
                time.sleep(wait_time)
            elif attempt == max_retries:
                print(f"\n  [Error] Call failed after {max_retries} attempts: {e}")
                raise
            else:
                raise


def run_evaluation(model: str, prompt_key: str, runs: int, test_cases_path: str = "test_cases.json"):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY not found in environment or .env file.")
        sys.exit(1)

    if prompt_key not in SYSTEM_PROMPTS:
        print(f"Error: Unknown prompt key '{prompt_key}'. Available: {list(SYSTEM_PROMPTS.keys())}")
        sys.exit(1)

    system_prompt = SYSTEM_PROMPTS[prompt_key]

    if not os.path.exists(test_cases_path):
        print(f"Error: Test cases file not found at '{test_cases_path}'.")
        sys.exit(1)

    with open(test_cases_path, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    client = genai.Client(api_key=api_key)

    total_cases = len(test_cases)
    print(f"\nStarting Evaluation:")
    print(f"  Model:       {model}")
    print(f"  Prompt:      {prompt_key}")
    print(f"  Test Cases:  {total_cases}")
    print(f"  Runs/Case:   {runs}")
    print(f"  Total Runs:  {total_cases * runs}\n")

    results = []

    for idx, case in enumerate(test_cases, 1):
        case_id = case.get("id", f"case_{idx}")
        category = case.get("category", "unknown")
        turns = case.get("turns", [])

        run_verdicts = []

        for run_idx in range(1, runs + 1):
            history = []
            worst_turn_verdict = "safe"
            final_reply = ""

            for turn_text in turns:
                reply = call_bot_with_retry(
                    history=history,
                    user_message=turn_text,
                    system_prompt=system_prompt,
                    model=model,
                    client=client,
                )
                turn_verdict = score_reply(reply)
                worst_turn_verdict = worse_verdict(worst_turn_verdict, turn_verdict)
                history.append({"role": "user", "text": turn_text})
                history.append({"role": "assistant", "text": reply})
                final_reply = reply

            run_verdicts.append(worst_turn_verdict)
            results.append({
                "test_id": case_id,
                "category": category,
                "run": run_idx,
                "verdict": worst_turn_verdict,
                "final_reply": final_reply,
            })

        # Print one progress line per test case
        verdicts_str = ", ".join(f"R{r}:{v}" for r, v in enumerate(run_verdicts, 1))
        print(f"[{idx:2d}/{total_cases}] {case_id:<16} ({category:<18}) -> {verdicts_str}")

    # Ensure results directory exists
    os.makedirs("results", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sanitized_model = model.replace("/", "_").replace(":", "_").replace("\\", "_")
    csv_filename = f"results/{timestamp}_{sanitized_model}_{prompt_key}.csv"

    # Save to CSV
    fieldnames = ["test_id", "category", "run", "verdict", "final_reply"]
    with open(csv_filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Print summary
    print_summary(results, model, prompt_key, csv_filename)


def print_summary(results: list[dict], model: str, prompt_key: str, csv_filename: str):
    total_runs = len(results)
    if total_runs == 0:
        print("No results to display.")
        return

    # Aggregate by category
    categories = sorted(list({r["category"] for r in results}))
    cat_stats = {}
    for cat in categories:
        cat_rows = [r for r in results if r["category"] == cat]
        leaked = sum(1 for r in cat_rows if r["verdict"] == "leaked")
        partial = sum(1 for r in cat_rows if r["verdict"] == "partial")
        safe = sum(1 for r in cat_rows if r["verdict"] == "safe")
        total = len(cat_rows)
        cat_stats[cat] = {
            "total": total,
            "leaked": leaked,
            "partial": partial,
            "safe": safe,
            "leak_rate": (leaked / total * 100) if total > 0 else 0.0,
            "success_rate": ((leaked + partial) / total * 100) if total > 0 else 0.0,
        }

    overall_leaked = sum(1 for r in results if r["verdict"] == "leaked")
    overall_partial = sum(1 for r in results if r["verdict"] == "partial")
    overall_safe = sum(1 for r in results if r["verdict"] == "safe")
    overall_leak_rate = (overall_leaked / total_runs * 100) if total_runs > 0 else 0.0
    overall_success_rate = ((overall_leaked + overall_partial) / total_runs * 100) if total_runs > 0 else 0.0

    print("\n" + "=" * 90)
    print("EVALUATION SUMMARY")
    print(f"  Model:      {model}")
    print(f"  Prompt:     {prompt_key}")
    print(f"  Total Runs: {total_runs}")
    print(f"  CSV Saved:  {csv_filename}")
    print("=" * 90)
    print(f"{'Category':<22} {'Total':>6} {'Leaked':>8} {'Partial':>8} {'Safe':>6} {'Leak Rate':>12} {'Attack Success':>16}")
    print("-" * 90)
    for cat in categories:
        s = cat_stats[cat]
        print(
            f"{cat:<22} {s['total']:>6} {s['leaked']:>8} {s['partial']:>8} {s['safe']:>6} "
            f"{s['leak_rate']:>11.1f}% {s['success_rate']:>15.1f}%"
        )
    print("-" * 90)
    print(
        f"{'OVERALL':<22} {total_runs:>6} {overall_leaked:>8} {overall_partial:>8} {overall_safe:>6} "
        f"{overall_leak_rate:>11.1f}% {overall_success_rate:>15.1f}%"
    )
    print("=" * 90)
    print(f"Attack Success Rate (Leaked + Partial): {overall_success_rate:.1f}%\n")


def main():
    parser = argparse.ArgumentParser(description="Evaluate prompt injection attacks against Acme Gadgets chatbot.")
    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        help="Gemini model name to evaluate (default: from GEMINI_MODEL in .env or gemini-2.5-flash)",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="v2_staff_verification",
        choices=list(SYSTEM_PROMPTS.keys()),
        help="System prompt to test (default: v2_staff_verification)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Number of times to run each test case (default: 1)",
    )
    parser.add_argument(
        "--test-cases",
        type=str,
        default="test_cases.json",
        help="Path to test cases JSON file (default: test_cases.json)",
    )

    args = parser.parse_args()
    run_evaluation(
        model=args.model,
        prompt_key=args.prompt,
        runs=args.runs,
        test_cases_path=args.test_cases,
    )


if __name__ == "__main__":
    main()

"""Run holdout validation and future forecasts for genuine processed M5 input."""
import argparse
import json
from pathlib import Path
from data_loader import load_series
from forecast import analyse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/processed_sales.csv")
    parser.add_argument("--output", default="data/forecast_results.json")
    args = parser.parse_args()
    try:
        groups = load_series(args.data)
        results = [{"item_id": key[0], "store_id": key[1], **analyse(rows)}
                   for key, rows in sorted(groups.items())]
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(results, default=str, indent=2) + "\n", encoding="utf-8")
        # Separate model output contains no historical daily observations.
        future_output = output.with_name(output.stem + "_future.json")
        future_only = [{key: result[key] for key in
                        ("item_id", "store_id", "history_end", "selected_method",
                         "future", "total_forecast_demand")} for result in results]
        future_output.write_text(json.dumps(future_only, default=str, indent=2) + "\n", encoding="utf-8")
        for result in results:
            print(result["item_id"], result["store_id"], result["selected_method"])
            for method, validation in result["backtest"].items():
                print("  %s: holdout MAE %.6f" % (method, validation["mae"]))
            print("  Future 14-day total: %.6f" % result["total_forecast_demand"])
        print("Daily validation and future predictions saved to", output)
    except (ValueError, OSError) as error:
        parser.exit(2, "Phase 1 analysis failed: %s\n" % error)


if __name__ == "__main__":
    main()

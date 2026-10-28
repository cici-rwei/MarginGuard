"""Two transparent demand baselines. All inputs end at the forecast origin."""
from datetime import timedelta
from math import isfinite

METHODS = ("moving_average_7", "same_weekday_4")  # First wins an exact MAE tie.


def validate_history(rows, minimum=28):
    if len(rows) < minimum:
        raise ValueError("At least %d consecutive daily observations are required." % minimum)
    for i, row in enumerate(rows):
        value = row["units_sold"]
        if not isfinite(value) or value < 0:
            raise ValueError("Sales must be finite and nonnegative.")
        if i and row["date"] != rows[i - 1]["date"] + timedelta(days=1):
            raise ValueError("History must be sorted, unique and consecutive by day.")


def predict(rows, method, horizon=14):
    validate_history(rows)
    if method not in METHODS:
        raise ValueError("Unknown forecast method.")
    if type(horizon) is not int or not 1 <= horizon <= 366:
        raise ValueError("Horizon must be an integer from 1 to 366.")
    origin = rows[-1]["date"]
    average = sum(r["units_sold"] for r in rows[-7:]) / 7
    result = []
    for offset in range(1, horizon + 1):
        day = origin + timedelta(days=offset)
        # Always select from observed history, never from the future horizon.
        matches = [r["units_sold"] for r in rows[-28:]
                   if r["date"].weekday() == day.weekday()]
        value = average if method == METHODS[0] else sum(matches) / 4
        result.append({"date": day, "prediction": value})
    return result


def mae(actual, predicted):
    if not actual or len(actual) != len(predicted):
        raise ValueError("MAE requires equal, nonempty sequences.")
    if any(not isfinite(x) or x < 0 for x in list(actual) + list(predicted)):
        raise ValueError("MAE inputs must be finite and nonnegative.")
    return sum(abs(a - p) for a, p in zip(actual, predicted)) / len(actual)


def analyse(rows):
    validate_history(rows, minimum=42)
    training, holdout = rows[:-14], rows[-14:]
    results = {}
    for method in METHODS:
        predictions = predict(training, method)
        results[method] = {
            "mae": mae([r["units_sold"] for r in holdout],
                       [r["prediction"] for r in predictions]),
            "daily": [{"date": a["date"], "actual": a["units_sold"],
                       "prediction": p["prediction"]}
                      for a, p in zip(holdout, predictions)],
        }
    selected = min(METHODS, key=lambda name: results[name]["mae"])
    future = predict(rows, selected)
    return {"training_end": training[-1]["date"],
            "history_start": rows[0]["date"], "history_end": rows[-1]["date"],
            "observations": len(rows), "backtest": results,
            "selected_method": selected, "future": future,
            "total_forecast_demand": sum(r["prediction"] for r in future)}

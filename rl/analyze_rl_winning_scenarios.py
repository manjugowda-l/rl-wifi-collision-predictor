#!/usr/bin/env python3
"""Select scenarios where RL strictly beats DCF and EDCA on every metric."""

import argparse
import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "rl" / "results"
DEFAULT_INPUT = RESULTS_DIR / "final_40_scenario_comparison.csv"
DEFAULT_METADATA = RESULTS_DIR / "final_40_scenario_comparison.metadata.json"
METHODS = ("DCF", "EDCA", "RL Adaptive DCF")
SCENARIOS = tuple(range(1, 41))
INPUT_FIELDS = (
    "scenario_id",
    "scenario_name",
    "method",
    "run",
    "seed",
    "transmitted_packets",
    "received_packets",
    "lost_packets",
    "packet_loss_percent",
    "average_latency_ms",
    "flow1_throughput_mbps",
    "flow2_throughput_mbps",
)
OUTPUT_FIELDS = (*INPUT_FIELDS, "aggregate_goodput_mbps")
SUMMARY_FIELDS = (
    "method",
    "qualifying_scenarios",
    "completed_runs",
    "mean_transmitted_packets",
    "mean_received_packets",
    "mean_lost_packets",
    "mean_packet_loss_percent",
    "mean_average_latency_ms",
    "mean_flow1_throughput_mbps",
    "mean_flow2_throughput_mbps",
    "mean_aggregate_goodput_mbps",
)

# Input throughput is printed to five decimal places per flow, loss has more
# precision, and latency is printed to 0.001 ms. Treat differences no larger
# than one displayed unit as ties, rather than meaningful strict wins.
TOLERANCES = {
    "aggregate_goodput_mbps": 1e-5,
    "packet_loss_percent": 1e-6,
    "average_latency_ms": 1e-3,
}

METHOD_SUFFIXES = {
    "DCF": "dcf",
    "EDCA": "edca",
    "RL Adaptive DCF": "rl",
}
WORKLOAD_LINE = re.compile(
    r"^\s*(STA A|STA B|STA B second burst)\s*:\s*(.*?)\s*$",
    re.MULTILINE,
)


def _number(row, key, scenario):
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"scenario {scenario}: invalid {key}") from error
    if not math.isfinite(value):
        raise ValueError(f"scenario {scenario}: non-finite {key}")
    return value


def _integer(row, key, scenario):
    value = _number(row, key, scenario)
    if not value.is_integer():
        raise ValueError(f"scenario {scenario}: {key} must be an integer")
    return int(value)


def read_comparison(path):
    with path.open("r", newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != list(INPUT_FIELDS):
            raise ValueError(
                f"Unexpected comparison CSV header in {path}: {reader.fieldnames}"
            )
        return list(reader)


def validate_metadata(path):
    metadata = json.loads(path.read_text(encoding="utf-8"))
    config = metadata.get("config", {})
    if metadata.get("complete") is not True or metadata.get("completed_rows") != 120:
        raise ValueError(f"Comparison metadata does not mark 120 rows complete: {path}")
    if config.get("scenarios") != list(SCENARIOS):
        raise ValueError(f"Comparison metadata does not cover scenarios 1-40: {path}")
    if not isinstance(config.get("run"), int) or config["run"] < 1:
        raise ValueError(f"Invalid run in comparison metadata: {path}")
    if not isinstance(config.get("seed"), int) or config["seed"] < 1:
        raise ValueError(f"Invalid seed in comparison metadata: {path}")
    return config


def _validate_scenario_rows(scenario, scenario_rows, config):
    reasons = []
    methods = defaultdict(list)
    for row in scenario_rows:
        methods[row.get("method")].append(row)
    for method in METHODS:
        if len(methods[method]) == 0:
            reasons.append(f"missing {method} result")
        elif len(methods[method]) > 1:
            reasons.append(f"duplicate {method} rows ({len(methods[method])})")
    unexpected = sorted(set(methods) - set(METHODS))
    if unexpected:
        reasons.append(f"unexpected method(s): {', '.join(map(str, unexpected))}")

    if reasons:
        return None, reasons

    validated = {}
    for method in METHODS:
        row = methods[method][0]
        try:
            if row.get("scenario_name") != f"scenario_{scenario:02d}":
                raise ValueError("scenario_name does not match scenario_id")
            run = _integer(row, "run", scenario)
            seed = _integer(row, "seed", scenario)
            if run != config["run"] or seed != config["seed"]:
                raise ValueError(
                    f"run/seed {run}/{seed} do not match configured "
                    f"{config['run']}/{config['seed']}"
                )
            tx = _integer(row, "transmitted_packets", scenario)
            rx = _integer(row, "received_packets", scenario)
            lost = _integer(row, "lost_packets", scenario)
            if tx < 0 or rx < 0 or lost < 0 or rx > tx or tx - rx != lost:
                raise ValueError("packet counts are invalid or TX-RX != lost")
            loss = _number(row, "packet_loss_percent", scenario)
            expected_loss = 100.0 * lost / tx if tx else 0.0
            if not math.isclose(loss, expected_loss, rel_tol=0.0, abs_tol=1e-8):
                raise ValueError("packet_loss_percent disagrees with TX/RX counts")
            latency_raw = row.get("average_latency_ms")
            latency = None if latency_raw in (None, "") else _number(
                row, "average_latency_ms", scenario
            )
            if (rx == 0) != (latency is None):
                raise ValueError(
                    "latency must be unavailable exactly when received_packets is zero"
                )
            if latency is not None and latency < 0:
                raise ValueError("average latency must be non-negative")
            flow1 = _number(row, "flow1_throughput_mbps", scenario)
            flow2 = _number(row, "flow2_throughput_mbps", scenario)
            if flow1 < 0 or flow2 < 0:
                raise ValueError("throughput must be non-negative")
            validated[method] = {
                **row,
                "scenario_id": scenario,
                "run": run,
                "seed": seed,
                "transmitted_packets": tx,
                "received_packets": rx,
                "lost_packets": lost,
                "packet_loss_percent": loss,
                "average_latency_ms": latency,
                "flow1_throughput_mbps": flow1,
                "flow2_throughput_mbps": flow2,
                "aggregate_goodput_mbps": flow1 + flow2,
            }
        except ValueError as error:
            reasons.append(f"{method}: {error}")
    if reasons:
        return None, reasons

    identities = {
        (row["run"], row["seed"], row["scenario_name"])
        for row in validated.values()
    }
    if len(identities) != 1:
        return None, ["method run/seed/scenario identities do not match"]
    return validated, []


def validate_log_workloads(validated_by_scenario, logs_dir):
    """Check output identity and equal offered workload from retained logs."""
    failures = defaultdict(list)
    for scenario, methods in validated_by_scenario.items():
        signatures = {}
        for method, row in methods.items():
            suffix = METHOD_SUFFIXES[method]
            path = logs_dir / (
                f"scenario_{scenario:02d}_run_{row['run']}_{suffix}.log"
            )
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                scenario_match = re.findall(
                    r"^\s*Scenario\s*:\s*(\d+)\s*$", text, re.MULTILINE
                )
                run_match = re.findall(
                    r"^\s*Random\s+run\s*:\s*(\d+)\s*$",
                    text,
                    re.MULTILINE | re.IGNORECASE,
                )
                if not scenario_match or int(scenario_match[-1]) != scenario:
                    raise ValueError("log scenario identity is missing or inconsistent")
                if not run_match or int(run_match[-1]) != row["run"]:
                    raise ValueError("log run identity is missing or inconsistent")
                signature = dict(WORKLOAD_LINE.findall(text))
                if not {"STA A", "STA B"}.issubset(signature):
                    raise ValueError("log lacks STA A/STA B workload configuration")
                signatures[method] = tuple(sorted(signature.items()))
            except (OSError, ValueError) as error:
                failures[scenario].append(f"{method}: {error}")
        if len(signatures) == len(METHODS) and len(set(signatures.values())) != 1:
            failures[scenario].append("method workload signatures do not match")
    return failures


def qualifies(method_rows):
    rl = method_rows["RL Adaptive DCF"]
    for baseline in ("DCF", "EDCA"):
        comparison = method_rows[baseline]
        if not (
            rl["aggregate_goodput_mbps"]
            > comparison["aggregate_goodput_mbps"]
            + TOLERANCES["aggregate_goodput_mbps"]
            and rl["packet_loss_percent"]
            < comparison["packet_loss_percent"]
            - TOLERANCES["packet_loss_percent"]
            and rl["average_latency_ms"] is not None
            and comparison["average_latency_ms"] is not None
            and rl["average_latency_ms"]
            < comparison["average_latency_ms"]
            - TOLERANCES["average_latency_ms"]
        ):
            return False
    return True


def qualification_failures(method_rows):
    rl = method_rows["RL Adaptive DCF"]
    failures = []
    for baseline in ("DCF", "EDCA"):
        other = method_rows[baseline]
        checks = (
            (
                "aggregate goodput",
                rl["aggregate_goodput_mbps"],
                other["aggregate_goodput_mbps"],
                lambda a, b, tol: a > b + tol,
                "higher",
            ),
            (
                "packet loss",
                rl["packet_loss_percent"],
                other["packet_loss_percent"],
                lambda a, b, tol: a < b - tol,
                "lower",
            ),
            (
                "average latency",
                rl["average_latency_ms"],
                other["average_latency_ms"],
                lambda a, b, tol: a < b - tol,
                "lower",
            ),
        )
        for metric, candidate, reference, compare, direction in checks:
            if candidate is None or reference is None:
                failures.append(f"no comparable {metric} against {baseline}")
            elif not compare(
                candidate, reference, TOLERANCES[
                    "aggregate_goodput_mbps"
                    if metric == "aggregate goodput"
                    else "packet_loss_percent"
                    if metric == "packet loss"
                    else "average_latency_ms"
                ]
            ):
                failures.append(
                    f"RL {metric} is not strictly {direction} than {baseline} "
                    f"outside tolerance (RL={candidate:g}, {baseline}={reference:g})"
                )
    return failures


def _write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _mean(values):
    values = list(values)
    return sum(values) / len(values) if values else None


def selected_summary(selected):
    output = []
    for method in METHODS:
        rows = [
            by_method[method]
            for by_method in selected.values()
        ]
        metrics = (
            ("transmitted_packets", "mean_transmitted_packets"),
            ("received_packets", "mean_received_packets"),
            ("lost_packets", "mean_lost_packets"),
            ("packet_loss_percent", "mean_packet_loss_percent"),
            ("average_latency_ms", "mean_average_latency_ms"),
            ("flow1_throughput_mbps", "mean_flow1_throughput_mbps"),
            ("flow2_throughput_mbps", "mean_flow2_throughput_mbps"),
            ("aggregate_goodput_mbps", "mean_aggregate_goodput_mbps"),
        )
        record = {
            "method": method,
            "qualifying_scenarios": len(selected),
            "completed_runs": len(rows),
        }
        for source, destination in metrics:
            record[destination] = _mean(
                row[source] for row in rows
                if row[source] is not None
            )
        output.append(record)
    return output


def _display(value, digits=6):
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}"


def write_report(path, selected, invalid_reasons, failed_reasons, summary):
    selected_ids = sorted(selected)
    excluded_count = 40 - len(selected_ids)
    with path.open("w", encoding="utf-8") as output:
        output.write("# RL winning scenarios: post-hoc selected-scenario analysis\n\n")
        output.write(
            "**This is a post-hoc selected-scenario analysis.** Scenarios are "
            "selected using their observed results; this does not establish that "
            "RL outperforms DCF/EDCA across all 40 scenarios or general Wi-Fi "
            "workloads.\n\n"
        )
        output.write("## Exact selection criteria\n\n")
        output.write(
            "A scenario is retained only if, in that same scenario, RL Adaptive "
            "DCF has strictly higher aggregate goodput (Flow 1 + Flow 2), "
            "strictly lower packet-loss percentage, and strictly lower average "
            "end-to-end latency than **both** DCF and EDCA. All six comparisons "
            "must pass. Differences no greater than the tolerance are treated "
            "as ties and do not qualify:\n\n"
        )
        output.write(
            f"- Aggregate goodput: > {TOLERANCES['aggregate_goodput_mbps']:g} Mbps "
            "advantage.\n"
        )
        output.write(
            f"- Packet loss: > {TOLERANCES['packet_loss_percent']:g} percentage-point "
            "advantage (lower for RL).\n"
        )
        output.write(
            f"- Average latency: > {TOLERANCES['average_latency_ms']:g} ms "
            "advantage (lower for RL).\n\n"
        )
        output.write(
            f"Qualifying scenario IDs ({len(selected_ids)}): "
            + (", ".join(map(str, selected_ids)) if selected_ids else "none")
            + ".\n\n"
        )
        output.write(
            f"Retained: {len(selected_ids)} scenarios. Excluded: "
            f"{excluded_count} scenarios. Invalid or incomplete: "
            f"{len(invalid_reasons)}. Valid but non-qualifying: "
            f"{len(failed_reasons)}.\n\n"
        )
        output.write(
            "Every retained scenario satisfies all three criteria against both "
            "baselines. The selected CSV includes all three methods for each "
            "retained scenario.\n\n"
        )
        output.write("## Selected scenario comparisons\n\n")
        if not selected_ids:
            output.write("No scenarios qualified under the strict criteria.\n\n")
        else:
            output.write(
                "| Scenario | Method | Aggregate goodput (Mbps) | Loss (%) | "
                "Latency (ms) |\n|---|---|---:|---:|---:|\n"
            )
            for scenario in selected_ids:
                for method in METHODS:
                    row = selected[scenario][method]
                    output.write(
                        f"| {scenario} | {method} | "
                        f"{_display(row['aggregate_goodput_mbps'])} | "
                        f"{_display(row['packet_loss_percent'])} | "
                        f"{_display(row['average_latency_ms'])} |\n"
                    )
            output.write("\n")
        output.write("## Unweighted per-scenario mean summary\n\n")
        output.write(
            "Means below use exactly the same qualifying scenario set for each "
            "method. Empty values mean no scenario qualified; no means are "
            "invented.\n\n"
        )
        output.write(
            "| Method | Qualifying scenarios | Completed runs | Mean TX | Mean RX | "
            "Mean lost | Mean loss (%) | Mean latency (ms) | Mean Flow 1 "
            "(Mbps) | Mean Flow 2 (Mbps) | Mean aggregate goodput (Mbps) |\n"
        )
        output.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for row in summary:
            output.write(
                f"| {row['method']} | {row['qualifying_scenarios']} | "
                f"{row['completed_runs']} | "
                f"{_display(row['mean_transmitted_packets'])} | "
                f"{_display(row['mean_received_packets'])} | "
                f"{_display(row['mean_lost_packets'])} | "
                f"{_display(row['mean_packet_loss_percent'])} | "
                f"{_display(row['mean_average_latency_ms'])} | "
                f"{_display(row['mean_flow1_throughput_mbps'])} | "
                f"{_display(row['mean_flow2_throughput_mbps'])} | "
                f"{_display(row['mean_aggregate_goodput_mbps'])} |\n"
            )
        output.write("\n## Excluded scenarios\n\n")
        for scenario in SCENARIOS:
            if scenario in selected_ids:
                continue
            if scenario in invalid_reasons:
                category = "Invalid or incomplete data"
                reasons = invalid_reasons[scenario]
            else:
                category = "Valid but non-qualifying result"
                reasons = failed_reasons[scenario]
            output.write(
                f"- Scenario {scenario}: **{category}** — "
                + "; ".join(reasons)
                + ".\n"
            )
        output.write(
            "\n## Limitations\n\n"
            "This is an outcome-conditioned, post-hoc subset of one recorded "
            "run per scenario, not an independent confirmatory evaluation. "
            "Selection can overstate apparent performance and does not justify "
            "generalization beyond the selected workloads. The original "
            "40-scenario measurements, metrics, seeds, and checkpoints were not "
            "changed; no simulations were rerun and no model was retrained.\n"
        )


def analyze(input_path=DEFAULT_INPUT, metadata_path=DEFAULT_METADATA,
            output_dir=RESULTS_DIR, logs_dir=None):
    config = validate_metadata(metadata_path)
    rows = read_comparison(input_path)
    grouped = defaultdict(list)
    invalid_reasons = defaultdict(list)
    for row in rows:
        try:
            scenario = int(row.get("scenario_id", ""))
        except ValueError:
            raise ValueError(f"Invalid scenario_id in input row: {row}")
        if scenario not in SCENARIOS:
            raise ValueError(f"Scenario ID outside 1-40 in input row: {row}")
        grouped[scenario].append(row)

    valid = {}
    for scenario in SCENARIOS:
        if scenario not in grouped:
            invalid_reasons[scenario].append("missing all method rows")
            continue
        validated, reasons = _validate_scenario_rows(
            scenario, grouped[scenario], config
        )
        if reasons:
            invalid_reasons[scenario].extend(reasons)
        else:
            valid[scenario] = validated

    log_failures = validate_log_workloads(
        valid,
        logs_dir if logs_dir is not None else input_path.parent / "logs",
    )
    for scenario, reasons in log_failures.items():
        invalid_reasons[scenario].extend(reasons)
        valid.pop(scenario, None)

    selected = {}
    failed_reasons = {}
    for scenario, method_rows in valid.items():
        if qualifies(method_rows):
            selected[scenario] = method_rows
        else:
            failed_reasons[scenario] = qualification_failures(method_rows)

    output_dir.mkdir(parents=True, exist_ok=True)
    selected_rows = []
    for scenario in sorted(selected):
        for method in METHODS:
            row = selected[scenario][method]
            selected_rows.append({
                field: row[field] for field in INPUT_FIELDS
            } | {"aggregate_goodput_mbps": row["aggregate_goodput_mbps"]})
    _write_csv(
        output_dir / "rl_winning_scenarios_comparison.csv",
        OUTPUT_FIELDS,
        selected_rows,
    )
    summary = selected_summary(selected)
    _write_csv(
        output_dir / "rl_winning_scenarios_mean_summary.csv",
        SUMMARY_FIELDS,
        summary,
    )
    write_report(
        output_dir / "rl_winning_scenarios_report.md",
        selected,
        invalid_reasons,
        failed_reasons,
        summary,
    )
    return selected, invalid_reasons, failed_reasons, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--metadata", type=Path, default=DEFAULT_METADATA)
    parser.add_argument("--logs-dir", type=Path)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_DIR)
    args = parser.parse_args()
    selected, invalid, failed, _summary = analyze(
        args.input,
        args.metadata,
        args.output_dir,
        args.logs_dir,
    )
    print(f"Qualifying scenarios ({len(selected)}): "
          f"{', '.join(map(str, sorted(selected))) if selected else 'none'}")
    print(f"Invalid/incomplete scenarios: {len(invalid)}")
    print(f"Valid but non-qualifying scenarios: {len(failed)}")
    print(f"Selected CSV: {args.output_dir / 'rl_winning_scenarios_comparison.csv'}")
    print(f"Mean summary: {args.output_dir / 'rl_winning_scenarios_mean_summary.csv'}")
    print(f"Report: {args.output_dir / 'rl_winning_scenarios_report.md'}")


if __name__ == "__main__":
    main()

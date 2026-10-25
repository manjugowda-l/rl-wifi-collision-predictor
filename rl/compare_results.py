
#!/usr/bin/env python3
"""
Compare Baseline DCF, EDCA, and RL Adaptive DCF results.

Metrics:
    - Transmitted packets
    - Received packets
    - Throughput (overall or per traffic flow)
    - Lost packets
    - Packet loss (%)
    - Average latency (ms)

Expected inputs:
    1. Baseline results CSV
    2. EDCA simulation log
    3. RL evaluation results CSV

Example:
    .venv/bin/python rl/compare_results.py \
        --baseline wifi_baseline_results.csv \
        --edca "$EDCA_LOG" \
        --rl rl/data/evaluation_20261025T135455Z/raw_results.csv \
        --run 1
"""

import argparse
import csv
import math
import re
import sys
from pathlib import Path


METHODS = [
    ("Baseline DCF", "baseline"),
    ("EDCA", "edca"),
    ("RL Adaptive DCF", "rl"),
]

MEASUREMENT_WINDOW_SECONDS = 59.0
UDP_PAYLOAD_BYTES = 1200

# Only these metrics appear in the report.
METRICS = [
    ("Transmitted packets", "tx", "integer"),
    ("Received packets", "rx", "integer"),
    ("Lost packets", "lost", "integer"),
    ("Packet loss (%)", "loss_pct", "decimal"),
    ("Average latency (ms)", "latency_ms", "latency"),
]

THROUGHPUT_RE = re.compile(
    r"throughput(?:_Mbps)?|throughput_mbps|"
    r"flow[_ ]?\d+.*(?:throughput|Mbps)|"
    r"(?:throughput|Mbps).*flow[_ ]?\d+",
    re.IGNORECASE,
)


def normalize_key(value):
    """Normalize column names and log labels for flexible matching."""
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def parse_number(value):
    """Convert a numeric string to float, or return None."""
    if value is None:
        return None

    text = str(value).strip().replace(",", "")
    text = re.sub(r"\s*(?:packets?|ms|mbps|%)\s*$", "", text, flags=re.I)

    if not text or text.lower() in {
        "n/a", "na", "none", "null", "-", "nan"
    }:
        return None

    try:
        number = float(text)
        return number if math.isfinite(number) else None
    except ValueError:
        return None


def first_value(row, aliases):
    """Find the first populated field matching any alias."""
    normalized = {
        normalize_key(key): value
        for key, value in row.items()
        if key is not None
    }

    for alias in aliases:
        key = normalize_key(alias)
        if key in normalized:
            value = normalized[key]
            if value is not None and str(value).strip() != "":
                return value

    # Allow common prefixes/suffixes in CSV column names.
    for alias in aliases:
        target = normalize_key(alias)
        for key, value in normalized.items():
            if (
                key.endswith("_" + target)
                or key.startswith(target + "_")
            ):
                if value is not None and str(value).strip() != "":
                    return value

    return None


def extract_metrics(row):
    """Extract common metrics from a CSV row."""
    tx = parse_number(first_value(row, [
        "tx", "total_tx", "tx_packets", "total_tx_packets",
        "transmitted", "transmitted_packets", "packets_tx",
        "total_transmitted_packets",
    ]))

    rx = parse_number(first_value(row, [
        "rx", "total_rx", "rx_packets", "total_rx_packets",
        "received", "received_packets", "packets_rx",
        "total_received_packets",
    ]))

    lost = parse_number(first_value(row, [
        "lost", "lost_packets", "packet_loss_count",
        "packets_lost", "total_lost_packets",
    ]))

    loss_pct = parse_number(first_value(row, [
        "packet_loss_pct", "packet_loss_percent",
        "loss_pct", "loss_percent", "packet_loss",
    ]))

    latency_ms = parse_number(first_value(row, [
        "latency_ms", "average_latency_ms", "avg_latency_ms",
        "mean_latency_ms", "average_delay_ms", "avg_delay_ms",
        "latency",
    ]))

    # If loss count is not supplied, derive it from TX and RX.
    if lost is None and tx is not None and rx is not None:
        lost = max(0.0, tx - rx)

    # If loss percentage is not supplied, derive it from TX and RX.
    if loss_pct is None and tx is not None and tx > 0 and rx is not None:
        loss_pct = max(0.0, (tx - rx) / tx * 100.0)

    return {
        "tx": tx,
        "rx": rx,
        "lost": lost,
        "loss_pct": loss_pct,
        "latency_ms": latency_ms,
    }


def extract_throughputs(row):
    """
    Return throughput values found in a CSV row.

    Supports columns such as:
        throughput_Mbps
        flow1_throughput_Mbps
        throughput_flow2_Mbps
        throughput_mbps_flow_1

    Does not invent per-flow values if only total throughput is available.
    """
    result = {}
    normalized = {
        normalize_key(key): value
        for key, value in row.items()
        if key is not None
    }

    for key, value in normalized.items():
        if "throughput" not in key and not re.search(r"\bmbps\b", key):
            continue

        number = parse_number(value)
        if number is None:
            continue

        flow_match = re.search(r"flow_?(\d+)", key)
        if flow_match:
            flow_name = f"Throughput (Traffic {flow_match.group(1)}, Mbps)"
            result[flow_name] = number
        elif "throughput" in key or "mbps" in key:
            result["Throughput (overall, Mbps)"] = number

    return result


def read_csv_rows(path):
    """Read CSV rows and report a helpful error if the file is invalid."""
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        sample = handle.read(4096)
        handle.seek(0)

        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(handle, dialect=dialect)
        if not reader.fieldnames:
            raise ValueError(f"No CSV header found in {path}")

        return list(reader)


def get_scenario(row):
    value = first_value(row, [
        "scenario", "scenario_id", "scenario_number",
    ])
    number = parse_number(value)
    return int(number) if number is not None else None


def get_run(row):
    value = first_value(row, [
        "run", "run_id", "random_run", "run_number",
    ])
    number = parse_number(value)
    return int(number) if number is not None else None


def load_csv_results(path, selected_run=None):
    """Load baseline or RL CSV results indexed by scenario."""
    rows = read_csv_rows(path)
    results = {}

    for row in rows:
        scenario = get_scenario(row)
        if scenario is None:
            continue

        row_run = get_run(row)
        if selected_run is not None and row_run is not None:
            if row_run != selected_run:
                continue

        metrics = extract_metrics(row)
        metrics["throughputs"] = extract_throughputs(row)

        results[scenario] = metrics

    if not results:
        raise ValueError(
            f"No usable scenario rows found in {path}. "
            "Check the CSV headers and scenario column."
        )

    return results


def find_log_value(block, labels):
    """Extract a value from a labelled EDCA log line."""
    for label in labels:
        pattern = re.compile(
            rf"^\s*(?:[-*]\s*)?{label}\s*[:=]\s*(.*?)\s*$",
            re.IGNORECASE | re.MULTILINE,
        )
        match = pattern.search(block)
        if match:
            return match.group(1).strip()

    return None


def load_edca_log(path, selected_run=None):
    """
    Parse FINAL EDCA blocks from the simulation log.

    Each block is associated with the Scenario and Random run printed
    inside that block, rather than relying on heading order.
    """
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"EDCA log not found: {path}")

    text = path.read_text(encoding="utf-8", errors="replace")

    headings = list(re.finditer(
        r"FINAL\s+EDCA",
        text,
        re.IGNORECASE,
    ))

    if not headings:
        raise ValueError(f"No 'FINAL EDCA' blocks found in {path}")

    results = {}

    for index, heading in enumerate(headings):
        start = heading.start()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        block = text[start:end]

        scenario_text = find_log_value(block, [
            r"Scenario(?:\s+ID|\s+Number)?",
        ])
        run_text = find_log_value(block, [
            r"Random\s+run", r"Run(?:\s+ID|\s+Number)?",
        ])

        scenario_number = parse_number(scenario_text)
        run_number = parse_number(run_text)

        if scenario_number is None:
            continue

        scenario = int(scenario_number)

        if (
            selected_run is not None
            and run_number is not None
            and int(run_number) != selected_run
        ):
            continue

        tx = parse_number(find_log_value(block, [
            r"Total\s+(?:TX|Transmitted)(?:\s+packets?)?",
            r"Transmitted\s+packets",
            r"TX\s+packets",
            r"Total\s+TX\s+packets",
        ]))

        rx = parse_number(find_log_value(block, [
            r"Total\s+(?:RX|Received)(?:\s+packets?)?",
            r"Received\s+packets",
            r"RX\s+packets",
            r"Total\s+RX\s+packets",
        ]))

        lost = parse_number(find_log_value(block, [
            r"Lost\s+packets",
            r"Packet\s+loss\s+count",
            r"Total\s+lost\s+packets",
        ]))

        loss_pct = parse_number(find_log_value(block, [
            r"Packet\s+loss(?:\s+percentage|\s+percent|\s*\(%\))?",
            r"Packet\s+loss\s*%",
            r"Loss\s+percentage",
        ]))

        latency = parse_number(find_log_value(block, [
            r"Average\s+latency(?:\s*\(ms\))?",
            r"Average\s+delay(?:\s*\(ms\))?",
            r"Mean\s+latency(?:\s*\(ms\))?",
        ]))

        if lost is None and tx is not None and rx is not None:
            lost = max(0.0, tx - rx)

        if loss_pct is None and tx and tx > 0 and rx is not None:
            loss_pct = max(0.0, (tx - rx) / tx * 100.0)

        results[scenario] = {
            "tx": tx,
            "rx": rx,
            "lost": lost,
            "loss_pct": loss_pct,
            "latency_ms": latency,
            "throughputs": extract_log_throughputs(block),
        }

    if not results:
        raise ValueError(
            f"No usable EDCA scenario results found in {path}. "
            "Check the labels inside the FINAL EDCA blocks."
        )

    return results


def extract_log_throughputs(block):
    """
    Extract explicitly labelled throughput values from an EDCA log.

    If the log reports only total throughput, retain it as overall
    throughput. Flow-specific values are included only when present.
    """
    result = {}

    patterns = [
        (
            re.compile(
                r"Flow\s*(\d+)\s+throughput\s*[:=]\s*"
                r"([0-9.eE+-]+)\s*(?:Mbps)?",
                re.IGNORECASE,
            ),
            "flow_first",
        ),
        (
            re.compile(
                r"Throughput\s*\(\s*Flow\s*(\d+)\s*\)\s*[:=]\s*"
                r"([0-9.eE+-]+)\s*(?:Mbps)?",
                re.IGNORECASE,
            ),
            "flow_in_label",
        ),
        (
            re.compile(
                r"Throughput(?:\s*\(Mbps\))?\s*[:=]\s*"
                r"([0-9.eE+-]+)\s*(?:Mbps)?",
                re.IGNORECASE,
            ),
            "overall",
        ),
    ]

    for pattern, kind in patterns:
        for match in pattern.finditer(block):
            if kind == "overall":
                value = parse_number(match.group(1))
                if value is not None:
                    result["Throughput (overall, Mbps)"] = value
            else:
                flow = match.group(1)
                value = parse_number(match.group(2))
                if value is not None:
                    result[f"Throughput (Traffic {flow}, Mbps)"] = value

    return result


def calculate_throughput(metrics):
    """
    Calculate payload throughput from RX packets when no throughput
    field is available in the source data.
    """
    rx = metrics.get("rx")
    if rx is None:
        return None

    return rx * UDP_PAYLOAD_BYTES * 8 / MEASUREMENT_WINDOW_SECONDS / 1_000_000


def format_value(value, kind):
    if value is None:
        return "N/A"

    if kind == "integer":
        return f"{int(round(value)):,}"

    if kind == "latency":
        return f"{value:,.3f}"

    return f"{value:,.3f}"


def format_throughput(value):
    if value is None:
        return "N/A"
    return f"{value:,.3f}"


def build_throughput_labels(all_results):
    """Find throughput labels that are actually present in the inputs."""
    labels = set()

    for method_results in all_results.values():
        for scenario_data in method_results.values():
            labels.update(scenario_data.get("throughputs", {}).keys())

    # Prefer traffic flows in numeric order, followed by overall throughput.
    flow_labels = sorted(
        [label for label in labels if "Traffic " in label],
        key=lambda label: int(re.search(r"Traffic (\d+)", label).group(1)),
    )

    if flow_labels:
        return flow_labels

    if "Throughput (overall, Mbps)" in labels:
        return ["Throughput (overall, Mbps)"]

    # If source files do not store throughput explicitly, calculate
    # comparable payload throughput from received packets.
    return ["Throughput (Mbps, calculated from RX packets)"]


def get_throughput_value(data, label):
    if label == "Throughput (Mbps, calculated from RX packets)":
        return calculate_throughput(data)

    return data.get("throughputs", {}).get(label)


def print_table(scenario, all_results, throughput_labels):
    """Print one aligned table for the requested scenario."""
    print()
    print(f"SCENARIO {scenario}")
    print("-" * 104)

    metric_labels = [
        ("Transmitted packets", "tx", "integer"),
        ("Received packets", "rx", "integer"),
    ]

    # Throughput rows are inserted immediately after TX/RX.
    rows = []

    for label, key, kind in metric_labels:
        rows.append((label, key, kind))

    for throughput_label in throughput_labels:
        rows.append((throughput_label, throughput_label, "throughput"))

    rows.extend([
        ("Lost packets", "lost", "integer"),
        ("Packet loss (%)", "loss_pct", "decimal"),
        ("Average latency (ms)", "latency_ms", "latency"),
    ])

    metric_width = max(28, max(len(row[0]) for row in rows) + 2)
    column_width = 22

    header = f"{'Metric':<{metric_width}}"
    for method_name, _ in METHODS:
        header += f"{method_name:>{column_width}}"

    print(header)
    print("-" * len(header))

    for label, key, kind in rows:
        line = f"{label:<{metric_width}}"

        for _, method_key in METHODS:
            scenario_data = all_results[method_key].get(scenario)

            if scenario_data is None:
                value = None
            elif kind == "throughput":
                value = get_throughput_value(scenario_data, key)
            else:
                value = scenario_data.get(key)

            if kind == "throughput":
                formatted = format_throughput(value)
            else:
                formatted = format_value(value, kind)

            line += f"{formatted:>{column_width}}"

        print(line)

    print("-" * len(header))


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Compare Baseline DCF, EDCA, and RL Adaptive DCF "
            "simulation results."
        )
    )

    parser.add_argument(
        "--baseline",
        required=True,
        help="Path to the Baseline DCF results CSV.",
    )
    parser.add_argument(
        "--edca",
        required=True,
        help="Path to the EDCA simulation log.",
    )
    parser.add_argument(
        "--rl",
        required=True,
        help="Path to the RL evaluation results CSV.",
    )
    parser.add_argument(
        "--run",
        type=int,
        default=None,
        help="Optional simulation run number to select.",
    )

    args = parser.parse_args()

    try:
        baseline = load_csv_results(args.baseline, args.run)
        edca = load_edca_log(args.edca, args.run)
        rl = load_csv_results(args.rl, args.run)

        all_results = {
            "baseline": baseline,
            "edca": edca,
            "rl": rl,
        }

        scenarios = sorted(
            set(baseline.keys()) | set(edca.keys()) | set(rl.keys())
        )

        if not scenarios:
            raise ValueError("No common scenario data could be loaded.")

        throughput_labels = build_throughput_labels(all_results)

        print()
        print("WIFI PERFORMANCE COMPARISON")
        print("=" * 104)
        print(
            "Throughput is reported per traffic flow when flow-specific "
            "values are available."
        )
        print(
            "Otherwise, throughput is calculated from received 1200-byte "
            "UDP packets over a 59-second measurement window."
        )

        if 5 in scenarios:
            baseline_s5 = baseline.get(5, {}).get("tx")
            rl_s5 = rl.get(5, {}).get("tx")

            if (
                baseline_s5 is not None
                and rl_s5 is not None
                and baseline_s5 != rl_s5
            ):
                print(
                    "CAUTION: RL Scenario 5 used a different traffic volume. "
                    "Compare results carefully."
                )

        for scenario in scenarios:
            print_table(scenario, all_results, throughput_labels)

        print()
        print("=" * 104)
        print("Comparison report complete.")

    except (OSError, ValueError, csv.Error) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

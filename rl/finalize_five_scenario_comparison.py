#!/usr/bin/env python3
"""Validate five matched ns-3 runs and create comparison tables and SVG charts."""

import argparse
import csv
import html
import math
import os
import re
import shlex
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS_DIR = ROOT / "rl" / "results" / "five_scenario_experiment"
METHODS = ("DCF", "EDCA", "RL Adaptive DCF")
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
OUTPUT_FIELDS = (*INPUT_FIELDS, "aggregate_throughput_mbps")
METRICS = (
    ("flow1_throughput_mbps", "Flow 1 throughput", "Mbps"),
    ("flow2_throughput_mbps", "Flow 2 throughput", "Mbps"),
    ("aggregate_throughput_mbps", "Aggregate throughput", "Mbps"),
    ("packet_loss_percent", "Packet-loss percentage", "%"),
    ("average_latency_ms", "Average end-to-end latency", "ms"),
)
MEAN_METRICS = (
    ("transmitted_packets", "Transmitted packets", "packets"),
    ("received_packets", "Received packets", "packets"),
    ("lost_packets", "Lost packets", "packets"),
    ("packet_loss_percent", "Packet-loss percentage", "%"),
    ("average_latency_ms", "Average end-to-end latency", "ms"),
    ("flow1_throughput_mbps", "Flow 1 throughput", "Mbps"),
    ("flow2_throughput_mbps", "Flow 2 throughput", "Mbps"),
    ("aggregate_throughput_mbps", "Aggregate throughput", "Mbps"),
)
COLORS = {"DCF": "#4472C4", "EDCA": "#ED7D31", "RL Adaptive DCF": "#70AD47"}
SCENARIO_CONFIGS = {
    1: {
        "source_scenario_id": 5,
        "description": "Original scenario 5: simultaneous 10 MB, 40 Mbps flows; preserve B's 10 MB at 10 Mbps burst starting at 6 s.",
        "flow1": (10_000_000, "40Mbps", 1.0),
        "flow2": (10_000_000, "40Mbps", 1.0),
        "extra_flow2": (10_000_000, "10Mbps", 6.0),
        "purpose": "Reproduce the existing RL-winning workload.",
    },
    2: {
        "source_scenario_id": 18,
        "description": "Original scenario 18: simultaneous asymmetric high load.",
        "flow1": (40_000_000, "40Mbps", 1.0),
        "flow2": (20_000_000, "20Mbps", 1.0),
        "extra_flow2": (0, "", 0.0),
        "purpose": "Reproduce the existing asymmetric high-load workload.",
    },
    3: {
        "source_scenario_id": 24,
        "description": "Original scenario 24: A-heavy load with delayed B.",
        "flow1": (20_000_000, "20Mbps", 1.0),
        "flow2": (5_000_000, "5Mbps", 5.0),
        "extra_flow2": (0, "", 0.0),
        "purpose": "Reproduce the existing A-heavy, delayed-flow workload.",
    },
    4: {
        "source_scenario_id": "New moderate asymmetric workload",
        "description": "Flow 1 is 15 MB at 15 Mbps and Flow 2 is 10 MB at 10 Mbps; both start at 1 s.",
        "flow1": (15_000_000, "15Mbps", 1.0),
        "flow2": (10_000_000, "10Mbps", 1.0),
        "extra_flow2": (0, "", 0.0),
        "purpose": "Evaluate a new simultaneous moderate asymmetric load.",
    },
    5: {
        "source_scenario_id": "New reduced-volume simultaneous workload",
        "description": "Both flows are 5 MB at 20 Mbps and start at 1 s.",
        "flow1": (5_000_000, "20Mbps", 1.0),
        "flow2": (5_000_000, "20Mbps", 1.0),
        "extra_flow2": (0, "", 0.0),
        "purpose": "Evaluate the reduced-volume simultaneous 20 Mbps workload.",
    },
}


def _finite_number(row, field, context):
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{context}: invalid {field}") from error
    if not math.isfinite(value):
        raise ValueError(f"{context}: non-finite {field}")
    return value


def _integer(row, field, context):
    value = _finite_number(row, field, context)
    if not value.is_integer():
        raise ValueError(f"{context}: {field} must be an integer")
    return int(value)


def validate_rows(path):
    with Path(path).open("r", newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != list(INPUT_FIELDS):
            raise ValueError(f"Unexpected result CSV header: {reader.fieldnames}")
        source_rows = list(reader)

    by_key = {}
    scenario_identities = defaultdict(set)
    for row in source_rows:
        scenario = _integer(row, "scenario_id", "row")
        method = row.get("method")
        context = f"scenario {scenario} {method}"
        if scenario not in SCENARIO_CONFIGS:
            raise ValueError(f"Unexpected scenario ID {scenario}")
        if method not in METHODS:
            raise ValueError(f"{context}: unexpected method")
        run = _integer(row, "run", context)
        seed = _integer(row, "seed", context)
        key = (scenario, method, run)
        if key in by_key:
            raise ValueError(f"Duplicate result row: {key}")
        if row.get("scenario_name") != f"scenario_{scenario:02d}":
            raise ValueError(f"{context}: scenario name does not match scenario ID")
        tx = _integer(row, "transmitted_packets", context)
        rx = _integer(row, "received_packets", context)
        lost = _integer(row, "lost_packets", context)
        if tx <= 0 or rx < 0 or lost < 0 or rx > tx or tx - rx != lost:
            raise ValueError(f"{context}: invalid packet accounting")
        loss = _finite_number(row, "packet_loss_percent", context)
        if not math.isclose(loss, 100.0 * lost / tx, rel_tol=0.0, abs_tol=1e-8):
            raise ValueError(f"{context}: packet-loss percentage disagrees with counts")
        latency = _finite_number(row, "average_latency_ms", context)
        if latency < 0:
            raise ValueError(f"{context}: latency must be non-negative")
        flow1 = _finite_number(row, "flow1_throughput_mbps", context)
        flow2 = _finite_number(row, "flow2_throughput_mbps", context)
        if flow1 < 0 or flow2 < 0:
            raise ValueError(f"{context}: throughput must be non-negative")
        validated = {
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
            "aggregate_throughput_mbps": flow1 + flow2,
        }
        by_key[key] = validated
        scenario_identities[scenario].add((run, seed))

    expected_keys = {
        (scenario, method, run)
        for scenario in SCENARIO_CONFIGS
        for method in METHODS
        for run in {
            identity[0]
            for identity in scenario_identities[scenario]
        }
    }
    actual_keys = set(by_key)
    if actual_keys != expected_keys or len(source_rows) != 15:
        missing = sorted(expected_keys - actual_keys)
        unexpected = sorted(actual_keys - expected_keys)
        raise ValueError(
            "Expected exactly 15 rows (one per scenario/method); "
            f"missing={missing}, unexpected={unexpected}, rows={len(source_rows)}"
        )
    if any(len(identities) != 1 for identities in scenario_identities.values()):
        raise ValueError("Methods must use matching run and seed per scenario")
    all_identities = {
        identity
        for identities in scenario_identities.values()
        for identity in identities
    }
    if len(all_identities) != 1:
        raise ValueError("All five scenarios must use the same run and seed")
    expected_scenarios = set(SCENARIO_CONFIGS)
    if set(scenario_identities) != expected_scenarios:
        raise ValueError(f"Missing scenario results: {sorted(expected_scenarios - set(scenario_identities))}")

    ordered = []
    for scenario in sorted(SCENARIO_CONFIGS):
        run = next(iter(scenario_identities[scenario]))[0]
        ordered.extend(by_key[(scenario, method, run)] for method in METHODS)
    return ordered


def _expected_workload(config):
    def flow_signature(flow):
        byte_count, rate, start = flow
        packets = math.ceil(byte_count / 1200)
        return (
            f"{byte_count / 1_000_000:g} MB, {rate}, 1200 B packets, "
            f"{packets} packets, start {start:g} s"
        )

    signature = {
        "STA A": flow_signature(config["flow1"]),
        "STA B": flow_signature(config["flow2"]),
    }
    burst = config["extra_flow2"]
    if burst[0] > 0:
        signature["STA B second burst"] = flow_signature(burst)
    return signature


def validate_run_logs(rows, logs_dir):
    logs_dir = Path(logs_dir)
    suffixes = {"DCF": "dcf", "EDCA": "edca", "RL Adaptive DCF": "rl"}
    for row in rows:
        scenario, run = row["scenario_id"], row["run"]
        log_path = logs_dir / (
            f"scenario_{scenario:02d}_run_{run}_{suffixes[row['method']]}.log"
        )
        text = log_path.read_text(encoding="utf-8", errors="replace")
        for label, expected in (("Scenario", scenario), ("Random Run", run)):
            values = re.findall(
                rf"^\s*{re.escape(label)}\s*:\s*(\d+)\s*$",
                text,
                re.IGNORECASE | re.MULTILINE,
            )
            if not values or int(values[-1]) != expected:
                raise ValueError(f"{log_path}: missing or mismatched {label}")
        observed = dict(
            re.findall(
                r"^\s*(STA A|STA B|STA B second burst)\s*:\s*(.*?)\s*$",
                text,
                re.MULTILINE,
            )
        )
        expected = _expected_workload(SCENARIO_CONFIGS[scenario])
        if observed != expected:
            raise ValueError(
                f"{log_path}: workload signature differs from configuration; "
                f"observed={observed!r}, expected={expected!r}"
            )


def _write_csv(path, fields, rows):
    with Path(path).open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _mean_rows(rows):
    result = []
    for method in METHODS:
        selected = [row for row in rows if row["method"] == method]
        summary = {
            "method": method,
            "scenario_count": len(selected),
            "completed_runs": len(selected),
        }
        for field, _label, _unit in MEAN_METRICS:
            summary[f"mean_{field}"] = sum(row[field] for row in selected) / len(selected)
        result.append(summary)
    return result


def _esc(value):
    return html.escape(str(value), quote=True)


def _svg_text(x, y, value, size=13, anchor="middle", weight="normal"):
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" '
        f'font-family="Arial, sans-serif" font-size="{size}" '
        f'font-weight="{weight}">{_esc(value)}</text>'
    )


def _scenario_chart(path, rows, field, title, unit):
    width, height = 1120, 620
    left, right, top, bottom = 90, 30, 75, 110
    plot_width, plot_height = width - left - right, height - top - bottom
    values = [row[field] for row in rows]
    maximum = max(values, default=0.0)
    limit = maximum * 1.15 if maximum > 0 else 1.0
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        _svg_text(width / 2, 34, title, 22, weight="bold"),
        _svg_text(left, top - 18, f"Value ({unit})", 14, anchor="start"),
    ]
    for tick in range(6):
        y = top + plot_height * tick / 5
        value = limit * (5 - tick) / 5
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="#dddddd"/>')
        parts.append(_svg_text(left - 10, y + 4, f"{value:.3g}", 11, anchor="end"))
    group_width = plot_width / 5
    bar_width = min(42, group_width / 5)
    scenario_rows = {
        scenario: {
            row["method"]: row
            for row in rows
            if row["scenario_id"] == scenario
        }
        for scenario in range(1, 6)
    }
    for index, scenario in enumerate(range(1, 6)):
        center = left + group_width * (index + 0.5)
        for method_index, method in enumerate(METHODS):
            row = scenario_rows[scenario][method]
            value = row[field]
            bar_height = value / limit * plot_height
            x = center + (method_index - 1) * (bar_width + 7) - bar_width / 2
            y = top + plot_height - bar_height
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width:.1f}" '
                f'height="{bar_height:.1f}" fill="{COLORS[method]}"/>'
            )
            parts.append(_svg_text(x + bar_width / 2, max(top + 12, y - 4), f"{value:.3g}", 9))
        parts.append(_svg_text(center, top + plot_height + 23, f"Scenario {scenario}", 12))
    legend_y = height - 33
    legend_x = width / 2 - 245
    for method in METHODS:
        parts.append(f'<rect x="{legend_x}" y="{legend_y-13}" width="14" height="14" fill="{COLORS[method]}"/>')
        parts.append(_svg_text(legend_x + 20, legend_y, method, 12, anchor="start"))
        legend_x += 170 if method != "RL Adaptive DCF" else 0
    parts.append("</svg>")
    Path(path).write_text("\n".join(parts) + "\n", encoding="utf-8")


def _mean_chart(path, means):
    width, height = 1200, 980
    columns = 2
    cell_w, cell_h = width / columns, 220
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        _svg_text(width / 2, 35, "Unweighted means across the same five scenarios", 22, weight="bold"),
    ]
    for index, (field, label, unit) in enumerate(MEAN_METRICS):
        col, row_index = index % columns, index // columns
        x0, y0 = col * cell_w, 55 + row_index * cell_h
        plot_left, plot_top = x0 + 65, y0 + 50
        plot_w, plot_h = cell_w - 100, 125
        values = [mean[f"mean_{field}"] for mean in means]
        maximum = max(values, default=0.0)
        limit = maximum * 1.18 if maximum > 0 else 1.0
        parts.append(_svg_text(x0 + cell_w / 2, y0 + 23, f"{label} ({unit})", 15, weight="bold"))
        parts.append(f'<line x1="{plot_left}" y1="{plot_top+plot_h}" x2="{plot_left+plot_w}" y2="{plot_top+plot_h}" stroke="#666"/>')
        for method_index, (method, value) in enumerate(zip(METHODS, values)):
            bar_w = 55
            bx = plot_left + (method_index + 0.5) * plot_w / 3 - bar_w / 2
            bh = value / limit * plot_h
            by = plot_top + plot_h - bh
            parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w}" height="{bh:.1f}" fill="{COLORS[method]}"/>')
            parts.append(_svg_text(bx + bar_w / 2, max(plot_top + 11, by - 4), f"{value:.3g}", 11))
            label_text = {"RL Adaptive DCF": "RL Adaptive", "DCF": "DCF", "EDCA": "EDCA"}[method]
            parts.append(_svg_text(bx + bar_w / 2, plot_top + plot_h + 18, label_text, 10))
    legend_y = height - 25
    legend_x = width / 2 - 235
    for method in METHODS:
        parts.append(f'<rect x="{legend_x}" y="{legend_y-12}" width="14" height="14" fill="{COLORS[method]}"/>')
        parts.append(_svg_text(legend_x + 20, legend_y, method, 12, anchor="start"))
        legend_x += 160 if method != "RL Adaptive DCF" else 0
    parts.append("</svg>")
    Path(path).write_text("\n".join(parts) + "\n", encoding="utf-8")


def _configuration_rows(run, seed):
    output = []
    for scenario, config in SCENARIO_CONFIGS.items():
        flow1, flow2, burst = config["flow1"], config["flow2"], config["extra_flow2"]
        output.append({
            "scenario_id": scenario,
            "scenario_name": f"scenario_{scenario:02d}",
            "source_or_basis": config["source_scenario_id"],
            "workload_description": config["description"],
            "purpose": config["purpose"],
            "flow1_bytes": flow1[0],
            "flow1_rate": flow1[1],
            "flow1_start_s": flow1[2],
            "flow2_bytes": flow2[0],
            "flow2_rate": flow2[1],
            "flow2_start_s": flow2[2],
            "flow2_burst_bytes": burst[0],
            "flow2_burst_rate": burst[1],
            "flow2_burst_start_s": burst[2],
            "packet_size_bytes": 1200,
            "transport": "UDP",
            "application": "UDP constant-rate finite-byte source, 1200-byte packets, SeqTsSizeHeader; EDCA uses the equivalent TID-aware sender",
            "station_count": 2,
            "access_point_count": 1,
            "simulation_duration_s": 60.0,
            "measurement_start_s": 1.0,
            "measurement_end_s": 60.0,
            "measurement_duration_s": 59.0,
            "run": run,
            "seed": seed,
        })
    return output


def _write_scenario_tables(output_dir, rows):
    for scenario, config in SCENARIO_CONFIGS.items():
        selected = [row for row in rows if row["scenario_id"] == scenario]
        path = Path(output_dir) / f"scenario_{scenario:02d}_comparison.md"
        with path.open("w", encoding="utf-8") as table:
            table.write(f"# Scenario {scenario} comparison\n\n")
            table.write(f"{config['description']}\n\n")
            table.write("| Method | Tx | Rx | Lost | Loss (%) | Latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |\n")
            table.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
            for row in selected:
                table.write(
                    f"| {row['method']} | {row['transmitted_packets']} | {row['received_packets']} | "
                    f"{row['lost_packets']} | {row['packet_loss_percent']:.6f} | "
                    f"{row['average_latency_ms']:.6f} | {row['flow1_throughput_mbps']:.6f} | "
                    f"{row['flow2_throughput_mbps']:.6f} | {row['aggregate_throughput_mbps']:.6f} |\n"
                )
            table.write("\nBest measured method(s) by metric:\n\n")
            for field, label, higher_is_better in (
                ("flow1_throughput_mbps", "Flow 1 throughput", True),
                ("flow2_throughput_mbps", "Flow 2 throughput", True),
                ("aggregate_throughput_mbps", "Aggregate throughput", True),
                ("packet_loss_percent", "Packet-loss percentage", False),
                ("average_latency_ms", "Average latency", False),
            ):
                best_value = (
                    max(row[field] for row in selected)
                    if higher_is_better
                    else min(row[field] for row in selected)
                )
                methods = [
                    row["method"] for row in selected
                    if math.isclose(row[field], best_value, rel_tol=0.0, abs_tol=1e-12)
                ]
                table.write(f"- {label}: {', '.join(methods)}\n")


def _write_report(path, rows, means, checkpoint):
    run = rows[0]["run"]
    seed = rows[0]["seed"]
    with Path(path).open("w", encoding="utf-8") as report:
        report.write("# Five-scenario DCF, EDCA, and RL comparison\n\n")
        report.write("This is a fresh evaluation of exactly five workloads. Scenarios 1-3 reproduce selected historical workloads (original scenarios 5, 18, and 24); scenarios 4-5 are new workloads. It is not the historical 40-scenario result.\n\n")
        report.write(f"- Run: `{run}`; seed: `{seed}`; simulation: 60 s; measurement window: 59 s.\n")
        report.write(f"- RL checkpoint: `{checkpoint}`; retraining: none (completed v2 checkpoint reused).\n")
        report.write("- Each corresponding scenario uses the same traffic parameters, seed, and run in all three methods; only the MAC/access-control implementation differs.\n\n")
        report.write("DCF and RL use the ns-3 constant-rate finite-byte UDP source with `SeqTsSizeHeader`; EDCA uses its equivalent UDP sender to attach the selected TID. Packet size, generated byte limit, rate, timing, sequence/timestamp header, stations, and measurement interval are matched. The EDCA TID/MAC access category is part of the access-control method under comparison.\n\n")
        report.write("## Workload mapping\n\n| New ID | Source / basis | Workload | Purpose |\n|---:|---|---|---|\n")
        for scenario, config in SCENARIO_CONFIGS.items():
            report.write(f"| {scenario} | {config['source_scenario_id']} | {config['description']} | {config['purpose']} |\n")
        report.write("\n## Individual scenario comparisons\n\n")
        report.write("Aggregate throughput is the sum of the two measured flow-throughput values. Loss is the fraction of transmitted packets not received by simulation end.\n\n")
        for scenario, config in SCENARIO_CONFIGS.items():
            report.write(f"### Scenario {scenario} ({config['source_scenario_id']})\n\n")
            report.write(f"{config['description']}\n\n")
            report.write("| Method | Tx | Rx | Lost | Loss (%) | Avg latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |\n")
            report.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|\n")
            for row in rows:
                if row["scenario_id"] != scenario:
                    continue
                report.write(
                    f"| {row['method']} | {row['transmitted_packets']} | {row['received_packets']} | "
                    f"{row['lost_packets']} | {row['packet_loss_percent']:.6f} | "
                    f"{row['average_latency_ms']:.6f} | {row['flow1_throughput_mbps']:.6f} | "
                    f"{row['flow2_throughput_mbps']:.6f} | {row['aggregate_throughput_mbps']:.6f} |\n"
                )
            scenario_rows = [row for row in rows if row["scenario_id"] == scenario]
            leaders = []
            for field, label, higher_is_better in (
                ("flow1_throughput_mbps", "Flow 1 throughput", True),
                ("flow2_throughput_mbps", "Flow 2 throughput", True),
                ("aggregate_throughput_mbps", "Aggregate throughput", True),
                ("packet_loss_percent", "Packet-loss percentage", False),
                ("average_latency_ms", "Average latency", False),
            ):
                best_value = (
                    max(row[field] for row in scenario_rows)
                    if higher_is_better
                    else min(row[field] for row in scenario_rows)
                )
                best_methods = [
                    row["method"] for row in scenario_rows
                    if math.isclose(row[field], best_value, rel_tol=0.0, abs_tol=1e-12)
                ]
                leaders.append(f"{label}: {', '.join(best_methods)}")
            report.write("Best measured method(s) by metric: " + "; ".join(leaders) + ".\n\n")
        report.write("## Unweighted per-scenario means\n\nAll method means use exactly the same five scenario IDs; no pooled-packet weighting is applied. Every scenario ID receives equal weight, including the two new workloads in scenarios 4 and 5.\n\n")
        report.write("| Method | Scenarios | Completed runs | Mean Tx | Mean Rx | Mean lost | Mean loss (%) | Mean latency (ms) | Mean Flow 1 (Mbps) | Mean Flow 2 (Mbps) | Mean aggregate (Mbps) |\n")
        report.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for mean in means:
            report.write(
                f"| {mean['method']} | {mean['scenario_count']} | {mean['completed_runs']} | "
                + " | ".join(f"{mean[f'mean_{field}']:.6f}" for field, _, _ in MEAN_METRICS)
                + " |\n"
            )
        report.write("\nBest measured method(s) by mean metric: ")
        mean_leaders = []
        for field, label, higher_is_better in (
            ("mean_flow1_throughput_mbps", "Flow 1 throughput", True),
            ("mean_flow2_throughput_mbps", "Flow 2 throughput", True),
            ("mean_aggregate_throughput_mbps", "Aggregate throughput", True),
            ("mean_packet_loss_percent", "Packet-loss percentage", False),
            ("mean_average_latency_ms", "Average latency", False),
        ):
            best_value = (
                max(row[field] for row in means)
                if higher_is_better
                else min(row[field] for row in means)
            )
            best_methods = [
                row["method"] for row in means
                if math.isclose(row[field], best_value, rel_tol=0.0, abs_tol=1e-12)
            ]
            mean_leaders.append(f"{label}: {', '.join(best_methods)}")
        report.write("; ".join(mean_leaders) + ".\n")
        report.write("These metric leaders are not an overall-method ranking; metrics can favor different methods.\n")
        report.write("\n## Scenario-level RL comparison\n\n")
        for scenario in SCENARIO_CONFIGS:
            scenario_rows = {
                row["method"]: row
                for row in rows
                if row["scenario_id"] == scenario
            }
            rl = scenario_rows["RL Adaptive DCF"]
            report.write(f"- Scenario {scenario}: ")
            comparisons = []
            for baseline in ("DCF", "EDCA"):
                base = scenario_rows[baseline]
                better = []
                worse = []
                for field, label, higher_is_better in (
                    ("aggregate_throughput_mbps", "aggregate throughput", True),
                    ("packet_loss_percent", "packet loss", False),
                    ("average_latency_ms", "latency", False),
                ):
                    if rl[field] == base[field]:
                        continue
                    is_better = rl[field] > base[field] if higher_is_better else rl[field] < base[field]
                    (better if is_better else worse).append(label)
                comparisons.append(
                    f"vs {baseline}: better on {', '.join(better) or 'none'}; "
                    f"worse on {', '.join(worse) or 'none'}"
                )
            report.write("; ".join(comparisons) + ".\n")
        report.write("\n## Interpretation and limitations\n\n")
        report.write("These results describe only the five specified workloads, one run and one seed per workload, and the selected checkpoint. Scenarios 1-3 were selected historical workloads, including workloads previously identified as RL wins; this selection creates post-hoc selection bias. Scenarios 4-5 are new, but only one run per scenario was measured. This is not evidence that RL outperforms DCF or EDCA across the original 40 scenarios or across general Wi-Fi workloads. A single run per scenario also does not quantify run-to-run variability.\n")


def generate(
    input_csv,
    output_dir,
    checkpoint,
    runner_command="",
    analysis_command="",
    logs_dir=None,
):
    rows = validate_rows(input_csv)
    if logs_dir is not None:
        validate_run_logs(rows, logs_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_rows = [{field: row[field] for field in OUTPUT_FIELDS} for row in rows]
    _write_csv(output_dir / "five_scenario_comparison.csv", OUTPUT_FIELDS, output_rows)
    means = _mean_rows(rows)
    mean_fields = ["method", "scenario_count", "completed_runs"] + [
        f"mean_{field}" for field, _label, _unit in MEAN_METRICS
    ]
    _write_csv(output_dir / "five_scenario_mean_summary.csv", mean_fields, means)
    run, seed = rows[0]["run"], rows[0]["seed"]
    configuration_fields = list(_configuration_rows(run, seed)[0])
    _write_csv(
        output_dir / "five_scenario_configuration.csv",
        configuration_fields,
        _configuration_rows(run, seed),
    )
    _write_scenario_tables(output_dir, rows)
    _write_report(output_dir / "five_scenario_report.md", rows, means, checkpoint)
    for field, title, unit in METRICS:
        _scenario_chart(
            output_dir / f"five_scenario_{field}.svg",
            rows,
            field,
            f"{title} by scenario",
            unit,
        )
    _mean_chart(output_dir / "five_scenario_mean_comparison.svg", means)
    validation = (
        "Validation: exactly 15 rows (five scenarios x three methods); one row per "
        "scenario/method; same run and seed across all scenarios; packet counts "
        "and loss percentages consistent; all numeric metrics finite; aggregate "
        "throughput computed as Flow 1 + Flow 2; means computed over the same five "
        "scenarios for every method; measured run logs agree with all workload "
        "configurations and scenario/run identities.\n"
    )
    commands = (
        "# Commands and validation\n\n"
        "From the ns-3 repository root:\n\n"
        "## Build\n\n"
        "```bash\n"
        "./ns3 build wifi-baseline wifi-edca wifi-ai-dcf\n"
        "```\n\n"
        "## Run exactly five scenarios\n\n"
        "```bash\n"
        f"{runner_command or '(not recorded)'}\n"
        "```\n\n"
        "## Generate the report, CSVs, and charts\n\n"
        "```bash\n"
        f"{analysis_command or '(not recorded)'}\n"
        "```\n\n"
        "## Run the focused/full RL test suite\n\n"
        "```bash\n"
        "./.venv/bin/python -m unittest discover -s rl -p 'test_*.py'\n"
        "```\n\n"
        "## Validate rows, scenario mappings, checkpoint, and historical hashes\n\n"
        "```bash\n"
        f"./.venv/bin/python rl/validate_five_scenario_final.py --results-dir {os.path.relpath(output_dir, ROOT)} --checkpoint rl/q_table_v2.json\n"
        "```\n\n"
        "## Validation\n\n"
        f"{validation}\n"
    )
    (output_dir / "commands_and_validation.md").write_text(
        commands, encoding="utf-8"
    )
    return rows, means


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_RESULTS_DIR / "final_40_scenario_comparison.csv")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "rl" / "q_table_v2.json")
    parser.add_argument("--runner-command", default="")
    parser.add_argument("--logs-dir", type=Path)
    args = parser.parse_args()
    arguments = [
        sys.executable,
        str(Path(__file__).relative_to(ROOT)),
        "--input",
        str(args.input),
        "--output-dir",
        str(args.output_dir),
        "--checkpoint",
        str(args.checkpoint),
        "--runner-command",
        args.runner_command,
        "--logs-dir",
        str(args.logs_dir or args.input.parent / "logs"),
    ]
    analysis_command = " ".join(shlex.quote(argument) for argument in arguments)
    if "PYTHONPATH" in os.environ:
        analysis_command = (
            f"PYTHONPATH={shlex.quote(os.environ['PYTHONPATH'])} "
            + analysis_command
        )
    rows, means = generate(
        args.input,
        args.output_dir,
        args.checkpoint,
        args.runner_command,
        analysis_command,
        args.logs_dir or args.input.parent / "logs",
    )
    print(f"Validated {len(rows)} rows across five scenarios.")
    for mean in means:
        print(
            f"{mean['method']}: mean aggregate throughput="
            f"{mean['mean_aggregate_throughput_mbps']:.6f} Mbps, "
            f"loss={mean['mean_packet_loss_percent']:.6f}%, "
            f"latency={mean['mean_average_latency_ms']:.6f} ms"
        )


if __name__ == "__main__":
    main()

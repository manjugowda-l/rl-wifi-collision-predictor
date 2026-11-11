#!/usr/bin/env python3
"""Build and run matched DCF, EDCA, and RL experiments for ns-3 scenarios."""

import ast
import argparse
import csv
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

from common import CW_VALUES, action_target_cw, load_checkpoint

ROOT = Path(__file__).resolve().parents[1]
NS3 = ROOT / "ns3"
PYTHON = Path(sys.executable)
DEFAULT_CHECKPOINT = ROOT / "rl" / "q_table_v2.json"
SIM_TIME_SECONDS = 60.0
MEASUREMENT_START_SECONDS = 1.0
PAYLOAD_BYTES = 1200

FIELDS = [
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
]
MEAN_FIELDS = [
    "method",
    "completed_scenarios",
    "completed_runs",
    "mean_transmitted_packets",
    "mean_received_packets",
    "mean_lost_packets",
    "mean_packet_loss_percent",
    "mean_average_latency_ms",
    "latency_scenarios",
    "mean_flow1_throughput_mbps",
    "mean_flow2_throughput_mbps",
]
METHOD_TARGETS = {
    "DCF": "wifi-baseline",
    "EDCA": "wifi-edca",
    "RL Adaptive DCF": "wifi-ai-dcf",
}
METHOD_SUFFIXES = {"DCF": "dcf", "EDCA": "edca", "RL Adaptive DCF": "rl"}


def parse_scenarios(value):
    if value.strip().lower() == "all":
        return list(range(1, 41))
    try:
        selected = sorted({int(part.strip()) for part in value.split(",")})
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "scenarios must be 'all' or a comma-separated list from 1 to 40"
        ) from error
    if not selected or any(number not in range(1, 41) for number in selected):
        raise argparse.ArgumentTypeError(
            "scenario numbers must be in the range 1-40"
        )
    return selected


def calculate_throughput_mbps(received_packets, payload_bytes, window_seconds):
    if window_seconds <= 0 or received_packets < 0 or payload_bytes <= 0:
        raise ValueError("Throughput inputs must be non-negative with a positive window")
    return received_packets * payload_bytes * 8.0 / (window_seconds * 1_000_000.0)


def parse_labeled_number(text, label):
    pattern = re.compile(
        rf"^\s*{re.escape(label)}\s*:\s*"
        r"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|nan|n/a|unavailable)",
        re.IGNORECASE | re.MULTILINE,
    )
    matches = pattern.findall(text)
    if not matches:
        raise ValueError(f"Required result '{label}' is missing from simulation output")
    value = matches[-1].strip().lower()
    if value in {"nan", "n/a", "unavailable"}:
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def parse_labeled_identity(text, label):
    match = re.findall(
        rf"^\s*{re.escape(label)}\s*:\s*(\d+)\s*$",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if not match:
        raise ValueError(f"Simulation output is missing '{label}'")
    return int(match[-1])


def extract_workload_signature(text):
    lines = re.findall(
        r"^\s*(STA A|STA B|STA B second burst)\s*:\s*(.*?)\s*$",
        text,
        re.MULTILINE,
    )
    signature = {}
    for label, configuration in lines:
        signature[label] = configuration
    if not {"STA A", "STA B"}.issubset(signature):
        raise ValueError("Simulation output is missing station traffic configuration")
    return tuple(sorted(signature.items()))


def validate_rl_control_output(text):
    verify_lines = [
        line for line in text.splitlines() if line.startswith("[CW-VERIFY] ")
    ]
    if len(verify_lines) < 2:
        raise ValueError("RL log needs repeated CW checks spanning beacon intervals")
    verify_pattern = re.compile(
        r"\[CW-VERIFY\]\s+t=([\d.eE+-]+)\s+\|\s+selected=(\d+)"
        r"\s+\|\s+AP=(\d+)/(\d+)"
        r"\s+\|\s+advertisedBE=(?:BE )?(\d+)/(?:BE )?(\d+)"
        r"\s+\|\s+STA_A=(\d+)/(\d+)\s+\|\s+STA_B=(\d+)/(\d+)"
    )
    for line in verify_lines:
        match = verify_pattern.fullmatch(line)
        if not match:
            raise ValueError(f"Malformed RL CW verification line: {line}")
        selected, *limits = map(int, match.groups()[1:])
        expected_limits = [selected, 127] * 4
        if limits != expected_limits:
            raise ValueError(
                f"RL CW mismatch at a decision boundary: selected={selected}, "
                f"AP/advertisement/stations={limits}"
            )

    resync_pattern = re.compile(
        r"\[CW-STA-RESYNC\]\s+t=([\d.eE+-]+)\s+\|\s+selected=(\d+)"
        r"\s+\|\s+advertisedBE=(\d+)/(\d+)"
        r"\s+\|\s+STA_A=(\d+)/(\d+)\s+\|\s+STA_B=(\d+)/(\d+)"
    )
    for line in text.splitlines():
        if not line.startswith("[CW-STA-RESYNC] "):
            continue
        match = resync_pattern.fullmatch(line)
        if not match:
            raise ValueError(f"Malformed station CW resynchronization line: {line}")
        selected, advertised_min, advertised_max, *station_limits = map(
            int, match.groups()[1:]
        )
        if (
            advertised_min != selected
            or advertised_max != 127
            or any(
                minimum not in CW_VALUES or maximum != 127
                for minimum, maximum in zip(station_limits[::2], station_limits[1::2])
            )
        ):
            raise ValueError(f"Invalid station CW resynchronization: {line}")

    action_lines = [
        line for line in text.splitlines() if line.startswith("[RL-ACTION] ")
    ]
    policy_lines = [
        line for line in text.splitlines() if line.startswith("[POLICY] ")
    ]
    if not action_lines or len(action_lines) != len(policy_lines):
        raise ValueError(
            f"RL action/policy log count mismatch: {len(action_lines)} vs "
            f"{len(policy_lines)}"
        )
    action_pattern = re.compile(
        r"\[RL-ACTION\]\s+action=(\d+)\s+\|\s+requestedCW=(\d+)"
        r"\s+\|\s+APmin/max=(\d+)/(\d+)"
        r"\s+\|\s+advertisedBEmin/max=(?:BE )?(\d+)/(?:BE )?(\d+)"
        r"\s+\|\s+STA_Amin/max=(\d+)/(\d+)"
        r"\s+\|\s+STA_Bmin/max=(\d+)/(\d+)"
        r"\s+\|\s+activeSTA_A_CW=(\d+)"
        r"\s+\|\s+activeSTA_B_CW=(\d+)"
    )
    for line in action_lines:
        match = action_pattern.fullmatch(line)
        if not match:
            raise ValueError(f"Malformed RL action verification line: {line}")
        action, requested, *values = map(int, match.groups())
        limits, active_cw = values[:-2], values[-2:]
        if (
            action not in (0, 1, 2)
            or limits != [requested, 127] * 4
            or any(cw not in CW_VALUES or cw < requested for cw in active_cw)
        ):
            raise ValueError(f"RL action did not reach AP and stations: {line}")
    policy_pattern = re.compile(
        r"\[POLICY\]\s+step=(\d+)\s+state=(\([^)]*\))\s+action=(\d+)"
        r"\s+requestedCW=(\d+)\s+effectiveCW=(\d+)"
    )
    for line in policy_lines:
        match = policy_pattern.fullmatch(line)
        if not match:
            raise ValueError(f"Malformed RL policy trace line: {line}")
        _step, state_text, action, requested, effective = match.groups()
        state = ast.literal_eval(state_text)
        action, requested, effective = map(int, (action, requested, effective))
        if requested != effective:
            raise ValueError(f"RL policy CW mismatch: {line}")
        if action not in (0, 1, 2):
            raise ValueError(f"Invalid action in RL policy trace: {line}")
        if requested != action_target_cw(state[-1], action):
            raise ValueError(f"RL state/action/CW mapping mismatch: {line}")

    reward_pattern = re.compile(
        r"\[RL-STATE\].*?\|\s+Reward=([-+\d.eE]+)"
        r"\s+\|\s+RewardComponents\(throughput/loss/latency/queue/growth/retry\)="
        r"([-+\d.eE]+)/([-+\d.eE]+)/([-+\d.eE]+)/([-+\d.eE]+)/"
        r"([-+\d.eE]+)/([-+\d.eE]+)"
    )
    reward_lines = [
        line for line in text.splitlines() if line.startswith("[RL-STATE] ")
    ]
    if not reward_lines:
        raise ValueError("RL log is missing state/reward feedback")
    for line in reward_lines:
        match = reward_pattern.search(line)
        if not match:
            raise ValueError(f"Malformed RL reward feedback line: {line}")
        reward, *components = map(float, match.groups())
        expected = max(
            -1.0,
            min(
                1.0,
                0.40 * components[0]
                - 0.20 * components[1]
                - 0.20 * components[2]
                - 0.10 * components[3]
                - 0.05 * components[4]
                - 0.05 * components[5],
            ),
        )
        if not math.isclose(reward, expected, rel_tol=0.0, abs_tol=2e-5):
            raise ValueError(
                f"RL reward does not match logged components: {reward} != {expected}"
            )
    if len(verify_lines) != len(reward_lines):
        raise ValueError(
            f"RL CW/state trace count mismatch: {len(verify_lines)} vs "
            f"{len(reward_lines)}"
        )


def parse_simulation_output(text, scenario, method, run, seed):
    observed_scenario = parse_labeled_identity(text, "Scenario")
    run_match = re.findall(
        r"^\s*Random\s+run\s*:\s*(\d+)\s*$",
        text,
        re.IGNORECASE | re.MULTILINE,
    )
    if not run_match:
        raise ValueError("Simulation output is missing its random run number")
    observed_run = int(run_match[-1])
    if observed_scenario != scenario or observed_run != run:
        raise ValueError(
            f"{method} log identity is scenario {observed_scenario}, run {observed_run}; "
            f"expected scenario {scenario}, run {run}"
        )

    tx = parse_labeled_number(text, "Total TX packets")
    rx = parse_labeled_number(text, "Total RX packets")
    logged_loss = parse_labeled_number(text, "Lost packets")
    if tx is None or rx is None or tx < 0 or rx < 0 or rx > tx:
        raise ValueError(f"Invalid packet counts in {method} scenario {scenario}: {tx}, {rx}")
    lost = int(tx - rx)
    if logged_loss is not None and int(logged_loss) != lost:
        raise ValueError(
            f"{method} reported {logged_loss} lost packets but TX-RX gives {lost}"
        )
    packet_loss = 100.0 * lost / tx if tx else 0.0
    latency = parse_labeled_number(text, "Average latency")
    if rx == 0:
        latency = None
    flow1 = parse_labeled_number(text, "FLOW1_THROUGHPUT_MBPS")
    flow2 = parse_labeled_number(text, "FLOW2_THROUGHPUT_MBPS")
    if flow1 is None or flow2 is None:
        raise ValueError("Both per-flow throughput measurements are required")
    expected_goodput = calculate_throughput_mbps(
        int(rx),
        PAYLOAD_BYTES,
        SIM_TIME_SECONDS - MEASUREMENT_START_SECONDS,
    )
    if not math.isclose(
        flow1 + flow2,
        expected_goodput,
        rel_tol=1e-5,
        abs_tol=1e-5,
    ):
        raise ValueError(
            f"Per-flow throughput sum {flow1 + flow2} Mbps does not match "
            f"delivered payload goodput {expected_goodput} Mbps"
        )
    return {
        "scenario": scenario,
        "method": method,
        "run": run,
        "seed": seed,
        "transmitted_packets": int(tx),
        "received_packets": int(rx),
        "lost_packets": lost,
        "packet_loss_percent": packet_loss,
        "average_latency_ms": latency,
        "flow1_throughput_mbps": flow1,
        "flow2_throughput_mbps": flow2,
    }


def parse_rl_csv(path, scenario, method, run, seed):
    with path.open("r", newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    matches = [
        row for row in rows
        if row.get("scenario") == str(scenario) and row.get("run") == str(run)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected one RL row for scenario {scenario}, run {run} in {path}; "
            f"found {len(matches)}"
        )
    row = matches[0]
    tx = int(row["tx_packets"])
    rx = int(row["rx_packets"])
    if tx < 0 or rx < 0 or rx > tx:
        raise ValueError(f"Invalid RL packet counts: TX={tx}, RX={rx}")
    lost = tx - rx
    latency = float(row["average_latency_ms"])
    if not math.isfinite(latency) or rx == 0:
        latency = None
    expected_goodput = calculate_throughput_mbps(
        rx,
        PAYLOAD_BYTES,
        SIM_TIME_SECONDS - MEASUREMENT_START_SECONDS,
    )
    reported_goodput = float(row["aggregate_throughput_mbps"])
    flow1 = float(row["flow1_throughput_mbps"])
    flow2 = float(row["flow2_throughput_mbps"])
    if not math.isclose(
        reported_goodput,
        expected_goodput,
        rel_tol=1e-5,
        abs_tol=1e-5,
    ) or not math.isclose(
        flow1 + flow2,
        expected_goodput,
        rel_tol=1e-5,
        abs_tol=1e-5,
    ):
        raise ValueError(
            f"RL goodput fields disagree for scenario {scenario}, run {run}"
        )
    return {
        "scenario": scenario,
        "method": method,
        "run": run,
        "seed": seed,
        "transmitted_packets": tx,
        "received_packets": rx,
        "lost_packets": lost,
        "packet_loss_percent": 100.0 * lost / tx if tx else 0.0,
        "average_latency_ms": latency,
        "flow1_throughput_mbps": flow1,
        "flow2_throughput_mbps": flow2,
    }


def simulator_executables():
    found = {}
    for target in METHOD_TARGETS.values():
        matches = list(
            (ROOT / "build" / "scratch").glob(f"ns3.*-{target}-default")
        )
        if len(matches) == 1:
            found[target] = matches[0]
    return found


def executable_supports_seed(executable):
    if not executable.is_file():
        return False
    result = subprocess.run(
        [str(executable), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0 and "--seed:" in result.stdout


def ensure_simulator_targets():
    executables = simulator_executables()
    if len(executables) != len(METHOD_TARGETS) or not all(
        executable_supports_seed(path) for path in executables.values()
    ):
        print("Building required ns-3 targets (missing/stale seed CLI)...", flush=True)
        subprocess.run(
            [str(NS3), "build", *METHOD_TARGETS.values()],
            cwd=ROOT,
            check=True,
        )
        executables = simulator_executables()
    for target in METHOD_TARGETS.values():
        executable = executables.get(target)
        if executable is None or not executable_supports_seed(executable):
            raise RuntimeError(
                f"Built target {target} is missing or does not support --seed"
            )
    return executables


def run_reference(method, target, scenario, run, seed, output_dir):
    stem = f"scenario_{scenario:02d}_run_{run}_{method.lower()}"
    log_path = output_dir / "logs" / f"{stem}.log"
    result_path = output_dir / "logs" / f"{stem}_raw.csv"
    env = os.environ.copy()
    if method == "DCF":
        env["WIFI_BASELINE_RESULTS_FILE"] = str(result_path)
    command = [
        str(NS3),
        "run",
        "--no-build",
        f"{target} --scenario={scenario} --run={run} --seed={seed}",
    ]
    with log_path.open("w", encoding="utf-8") as log:
        try:
            subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"{method} simulation failed for scenario {scenario}, run {run}; "
                f"exit code {error.returncode}; see {log_path}"
            ) from error
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        return (
            parse_simulation_output(text, scenario, method, run, seed),
            extract_workload_signature(text),
        )
    except ValueError as error:
        raise ValueError(f"{error}; inspect {log_path}") from error


def run_rl(scenario, run, seed, checkpoint, output_dir, executable):
    method = "RL Adaptive DCF"
    stem = f"scenario_{scenario:02d}_run_{run}_rl"
    log_path = output_dir / "logs" / f"{stem}.log"
    result_path = output_dir / "logs" / f"{stem}_raw.csv"
    worker_dir = output_dir / "logs" / "rl_worker"
    worker_dir.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update({
        "WIFI_RL_EVAL_SINGLE_SCENARIO": str(scenario),
        "WIFI_RL_EVAL_OUTPUT_DIR": str(worker_dir),
        "WIFI_RL_EVAL_RUN": str(run),
        "WIFI_RL_EVAL_SEED": str(seed),
        "WIFI_RL_EVAL_MODEL_FILE": str(checkpoint),
        "WIFI_RL_RESULTS_FILE": str(result_path),
    })
    env["WIFI_RL_EVAL_TARGET"] = str(executable.relative_to(ROOT))
    with log_path.open("w", encoding="utf-8") as log:
        try:
            subprocess.run(
                [str(PYTHON), str(ROOT / "rl" / "evaluate.py")],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                f"RL simulation failed for scenario {scenario}, run {run}; "
                f"exit code {error.returncode}; see {log_path}"
            ) from error
    text = log_path.read_text(encoding="utf-8", errors="replace")
    try:
        validate_rl_control_output(text)
    except ValueError as error:
        raise ValueError(f"{error}; inspect {log_path}") from error
    return (
        parse_rl_csv(result_path, scenario, method, run, seed),
        extract_workload_signature(text),
    )


def atomic_csv(path, fields, rows):
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)


def validate_result_rows(rows, scenarios, run):
    expected = {
        (scenario, method, run)
        for scenario in scenarios
        for method in METHOD_TARGETS
    }
    actual = set()
    for row in rows:
        try:
            key = (int(row["scenario_id"]), row["method"], int(row["run"]))
            seed = int(row["seed"])
            tx = int(row["transmitted_packets"])
            rx = int(row["received_packets"])
            lost = int(row["lost_packets"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Malformed result row: {row}") from error
        if key in actual:
            raise ValueError(f"Duplicate scenario/method/run result row: {key}")
        actual.add(key)
        if key not in expected:
            raise ValueError(f"Unexpected result row: {key}")
        if row.get("scenario_name") != f"scenario_{key[0]:02d}":
            raise ValueError(f"Unexpected scenario name in row: {row}")
        if seed < 1 or tx < 0 or rx < 0 or lost < 0 or rx > tx:
            raise ValueError(f"Invalid seed or packet counts in row: {row}")
        if tx - rx != lost:
            raise ValueError(f"TX-RX loss mismatch in row: {row}")
        for field in (
            "packet_loss_percent",
            "flow1_throughput_mbps",
            "flow2_throughput_mbps",
        ):
            if not math.isfinite(float(row[field])):
                raise ValueError(f"Non-finite {field} in row: {row}")
        if tx and not math.isclose(
            float(row["packet_loss_percent"]),
            100.0 * lost / tx,
            rel_tol=0.0,
            abs_tol=1e-8,
        ):
            raise ValueError(f"Packet-loss percentage mismatch in row: {row}")
        latency = row.get("average_latency_ms")
        if latency not in (None, "") and not math.isfinite(float(latency)):
            raise ValueError(f"Non-finite latency in row: {row}")
    if actual != expected:
        raise ValueError(
            f"Result rows missing={sorted(expected - actual)}; "
            f"unexpected={sorted(actual - expected)}"
        )


def write_results(path, rows):
    rows = [
        row_with_scenario_name(row) if "scenario" in row else row
        for row in rows
    ]
    keys = [
        (int(row["scenario_id"]), row["method"], int(row["run"]))
        for row in rows
    ]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate scenario/method/run result rows")
    atomic_csv(path, FIELDS, rows)


def mean(values):
    values = list(values)
    if not values:
        raise ValueError("Cannot calculate a mean without values")
    return sum(values) / len(values)


def write_mean_summary(path, rows, scenarios, run):
    summary = []
    for method in METHOD_TARGETS:
        subset = [row for row in rows if row["method"] == method]
        latency = [
            float(row["average_latency_ms"])
            for row in subset
            if row["average_latency_ms"] not in (None, "")
        ]
        summary.append({
            "method": method,
            "completed_scenarios": len({
                int(row["scenario_id"]) for row in subset
            }),
            "completed_runs": len(subset),
            "mean_transmitted_packets": mean(
                float(row["transmitted_packets"]) for row in subset
            ),
            "mean_received_packets": mean(
                float(row["received_packets"]) for row in subset
            ),
            "mean_lost_packets": mean(
                float(row["lost_packets"]) for row in subset
            ),
            "mean_packet_loss_percent": mean(
                float(row["packet_loss_percent"]) for row in subset
            ),
            "mean_average_latency_ms": mean(latency) if latency else "",
            "latency_scenarios": len(latency),
            "mean_flow1_throughput_mbps": mean(
                float(row["flow1_throughput_mbps"]) for row in subset
            ),
            "mean_flow2_throughput_mbps": mean(
                float(row["flow2_throughput_mbps"]) for row in subset
            ),
        })
        if summary[-1]["completed_scenarios"] != len(scenarios):
            raise ValueError(f"{method} is missing selected scenarios")
        if summary[-1]["completed_runs"] != len(scenarios):
            raise ValueError(f"{method} has an inconsistent run count")
    atomic_csv(path, MEAN_FIELDS, summary)
    return summary


def compare_scenario_directions(rows, scenarios, run, baseline):
    by_key = {
        (int(row["scenario_id"]), row["method"], int(row["run"])): row
        for row in rows
    }
    counts = {"improved": 0, "tied": 0, "regressed": 0, "mixed": 0}
    for scenario in scenarios:
        candidate = by_key[(scenario, "RL Adaptive DCF", run)]
        reference = by_key[(scenario, baseline, run)]
        candidate_values = [
            float(candidate["flow1_throughput_mbps"])
            + float(candidate["flow2_throughput_mbps"]),
            float(candidate["packet_loss_percent"]),
            candidate["average_latency_ms"],
        ]
        reference_values = [
            float(reference["flow1_throughput_mbps"])
            + float(reference["flow2_throughput_mbps"]),
            float(reference["packet_loss_percent"]),
            reference["average_latency_ms"],
        ]
        better = []
        worse = []
        for index, (value, baseline_value) in enumerate(
            zip(candidate_values, reference_values)
        ):
            if value in (None, "") or baseline_value in (None, ""):
                continue
            value, baseline_value = float(value), float(baseline_value)
            if index == 0:
                better.append(value > baseline_value + 1e-9)
                worse.append(value < baseline_value - 1e-9)
            else:
                better.append(value < baseline_value - 1e-9)
                worse.append(value > baseline_value + 1e-9)
        if not any(better) and not any(worse):
            counts["tied"] += 1
        elif any(better) and not any(worse):
            counts["improved"] += 1
        elif any(worse) and not any(better):
            counts["regressed"] += 1
        else:
            counts["mixed"] += 1
    return counts


def write_summary(path, rows, scenarios, run):
    by_key = {
        (int(row["scenario_id"]), row["method"], int(row["run"])): row
        for row in rows
    }
    columns = [
        "Scenario",
        "DCF (TX/RX/Loss%/Latency ms/F1 Mbps/F2 Mbps)",
        "EDCA (TX/RX/Loss%/Latency ms/F1 Mbps/F2 Mbps)",
        "RL Adaptive DCF (TX/RX/Loss%/Latency ms/F1 Mbps/F2 Mbps)",
    ]
    directions = {
        baseline: compare_scenario_directions(rows, scenarios, run, baseline)
        for baseline in ("DCF", "EDCA")
    }
    with path.open("w", encoding="utf-8") as handle:
        handle.write("# Final scenario comparison\n\n")
        handle.write(
            "Loss is `(FlowMonitor TX - FlowMonitor RX) / TX`; packets still "
            "in flight at simulation stop are therefore included as not received. "
            "Latency is FlowMonitor accumulated end-to-end delay divided by "
            "received packets. Throughput is delivered 1200-byte application "
            "payload over the common 59-second measurement window.\n\n"
        )
        handle.write(
            "RL direction uses a Pareto comparison of aggregate goodput "
            "(higher is better), packet-loss percentage (lower), and average "
            "latency (lower). Improved/regressed means at least one strict "
            "improvement/regression and none in the opposite direction; mixed "
            "means trade-offs; tied means no measured difference.\n\n"
        )
        handle.write(
            f"RL vs DCF: {directions['DCF']['improved']} improved, "
            f"{directions['DCF']['tied']} tied, "
            f"{directions['DCF']['regressed']} regressed, "
            f"{directions['DCF']['mixed']} mixed.\n\n"
        )
        handle.write(
            f"RL vs EDCA: {directions['EDCA']['improved']} improved, "
            f"{directions['EDCA']['tied']} tied, "
            f"{directions['EDCA']['regressed']} regressed, "
            f"{directions['EDCA']['mixed']} mixed.\n\n"
        )
        handle.write("| " + " | ".join(columns) + " |\n")
        handle.write("|" + "|".join(["---"] * len(columns)) + "|\n")
        for scenario in scenarios:
            values = [f"scenario_{scenario:02d}"]
            for method in METHOD_TARGETS:
                row = by_key[(scenario, method, run)]
                latency = (
                    "N/A"
                    if row["average_latency_ms"] in (None, "")
                    else f'{float(row["average_latency_ms"]):.3f}'
                )
                values.append(
                    f'{row["transmitted_packets"]}/{row["received_packets"]}/'
                    f'{float(row["packet_loss_percent"]):.3f}/{latency}/'
                    f'{float(row["flow1_throughput_mbps"]):.4f}/'
                    f'{float(row["flow2_throughput_mbps"]):.4f}'
                )
            handle.write("| " + " | ".join(values) + " |\n")


def print_report(rows, output_dir):
    print("\nUnweighted per-scenario means (not pooled packet totals):")
    for method in METHOD_TARGETS:
        subset = [row for row in rows if row["method"] == method]
        loss = mean(float(row["packet_loss_percent"]) for row in subset)
        goodput = mean(
            float(row["flow1_throughput_mbps"])
            + float(row["flow2_throughput_mbps"])
            for row in subset
        )
        latency = [
            float(row["average_latency_ms"])
            for row in subset
            if row["average_latency_ms"] not in (None, "")
        ]
        print(
            f"  {method:16s} throughput={goodput:.4f} Mbps, "
            f"loss={loss:.4f}%, latency="
            f"{mean(latency):.3f} ms ({len(latency)} scenarios)"
        )
    print(f"\nIndividual results: {output_dir / 'final_40_scenario_comparison.csv'}")
    print(f"Mean summary: {output_dir / 'final_40_scenario_mean_summary.csv'}")
    print(f"Readable report: {output_dir / 'final_40_scenario_report.md'}")
    print(f"Raw logs: {output_dir / 'logs'}")


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_manifest(path, manifest):
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2, sort_keys=True)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)


def row_key(row):
    return (int(row["scenario_id"]), row["method"], int(row["run"]))


def row_with_scenario_name(row):
    scenario = row["scenario"]
    return {
        "scenario_id": scenario,
        "scenario_name": f"scenario_{scenario:02d}",
        **{key: value for key, value in row.items() if key != "scenario"},
    }


def saved_log_path(output_dir, scenario, method, run):
    stem = f"scenario_{scenario:02d}_run_{run}_{METHOD_SUFFIXES[method]}"
    return output_dir / "logs" / f"{stem}.log"


def verify_saved_result(row, output_dir, seed):
    scenario = int(row["scenario_id"])
    run = int(row["run"])
    method = row["method"]
    log_path = saved_log_path(output_dir, scenario, method, run)
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if method == "RL Adaptive DCF":
        validate_rl_control_output(text)
        raw_path = log_path.with_name(log_path.stem + "_raw.csv")
        actual = parse_rl_csv(raw_path, scenario, method, run, seed)
    else:
        actual = parse_simulation_output(text, scenario, method, run, seed)
    actual = row_with_scenario_name(actual)
    for field in FIELDS:
        saved = row.get(field)
        observed = actual.get(field)
        if field in (
            "packet_loss_percent",
            "average_latency_ms",
            "flow1_throughput_mbps",
            "flow2_throughput_mbps",
        ):
            if saved in (None, "") and observed is None:
                continue
            if not math.isclose(
                float(saved), float(observed), rel_tol=1e-9, abs_tol=1e-9
            ):
                raise ValueError(f"Saved row disagrees with {log_path}: {field}")
        elif str(saved) != str(observed):
            raise ValueError(f"Saved row disagrees with {log_path}: {field}")
    return extract_workload_signature(text)


def read_csv_rows(path):
    if not path.is_file():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _legacy_main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios",
        type=parse_scenarios,
        default=list(range(1, 41)),
        help="'all' or comma-separated scenario IDs 1-40",
    )
    parser.add_argument("--run", type=int, default=1, help="ns-3 run number")
    parser.add_argument("--seed", type=int, default=12345, help="ns-3 RNG seed")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="output directory (defaults to rl/results); partial runs are resumable",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT,
        help="existing RL checkpoint to evaluate; never modified",
    )
    args = parser.parse_args()
    if args.run < 1 or args.seed < 1:
        parser.error("--run and --seed must be positive integers")

    checkpoint = args.checkpoint.resolve()
    load_checkpoint(str(checkpoint))
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else ROOT / "rl" / "results"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "logs").mkdir(exist_ok=True)
    checkpoint_hash = file_sha256(checkpoint)
    config = {
        "scenarios": args.scenarios,
        "run": args.run,
        "seed": args.seed,
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": checkpoint_hash,
        "simulation_seconds": SIM_TIME_SECONDS,
        "measurement_start_seconds": MEASUREMENT_START_SECONDS,
        "payload_bytes": PAYLOAD_BYTES,
    }
    manifest_path = output_dir / "final_40_scenario_comparison.metadata.json"
    partial_path = output_dir / "final_40_scenario_comparison.partial.csv"
    final_path = output_dir / "final_40_scenario_comparison.csv"
    summary_path = output_dir / "final_40_scenario_mean_summary.csv"
    report_path = output_dir / "final_40_scenario_report.md"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("config") != config:
            raise ValueError(
                f"Existing experiment in {output_dir} has a different run "
                "configuration/checkpoint; use a separate --output-dir."
            )
        if manifest.get("complete"):
            rows = read_csv_rows(final_path)
            validate_result_rows(rows, args.scenarios, args.run)
            print_report(rows, output_dir)
            return
    elif partial_path.exists() or final_path.exists():
        raise ValueError(
            "Result files exist without a matching metadata manifest; refusing "
            "to reuse or overwrite unverifiable outputs."
        )
    else:
        manifest = {"config": config, "complete": False, "completed_rows": 0}
        save_manifest(manifest_path, manifest)

    executables = ensure_simulator_targets()
    rows = read_csv_rows(partial_path)
    expected_keys = {
        (scenario, method, args.run)
        for scenario in args.scenarios
        for method in METHOD_TARGETS
    }
    existing_keys = [row_key(row) for row in rows]
    if len(existing_keys) != len(set(existing_keys)):
        raise ValueError(f"Partial results contain duplicate rows: {partial_path}")
    if not set(existing_keys).issubset(expected_keys):
        raise ValueError(f"Partial results contain unexpected rows: {partial_path}")
    rows_by_key = {row_key(row): row for row in rows}

    for scenario in args.scenarios:
        print(f"\nScenario {scenario}/40; run={args.run}; seed={args.seed}", flush=True)
        expected_workload = None
        for method, target in list(METHOD_TARGETS.items())[:2]:
            print(f"  Running {method}", flush=True)
            row, workload = run_reference(
                method, target, scenario, args.run, args.seed, output_dir
            )
            if expected_workload is None:
                expected_workload = workload
            elif workload != expected_workload:
                raise RuntimeError(
                    f"DCF/EDCA workload mismatch in scenario {scenario}: "
                    f"{expected_workload!r} != {workload!r}"
                )
            rows.append(row)
        print("  Running RL Adaptive DCF", flush=True)
        row, workload = run_rl(scenario, args.run, args.seed, checkpoint, output_dir)
        if workload != expected_workload:
            raise RuntimeError(
                f"RL workload mismatch in scenario {scenario}: "
                f"{expected_workload!r} != {workload!r}"
            )
        rows.append(row)

    expected_rows = len(args.scenarios) * len(METHOD_TARGETS)
    if len(rows) != expected_rows:
        raise RuntimeError(f"Expected {expected_rows} runs, collected {len(rows)}")
    expected_keys = {
        (scenario, method, args.run)
        for scenario in args.scenarios
        for method in METHOD_TARGETS
    }
    actual_keys = {
        (row["scenario"], row["method"], row["run"])
        for row in rows
    }
    if actual_keys != expected_keys:
        raise RuntimeError(
            f"Result rows missing={sorted(expected_keys - actual_keys)}; "
            f"unexpected={sorted(actual_keys - expected_keys)}"
        )
    write_results(output_dir / "results.csv", rows)
    write_summary(output_dir / "comparison_summary.md", rows, args.scenarios)
    print_report(rows, output_dir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenarios",
        type=parse_scenarios,
        default=list(range(1, 41)),
        help="'all' or comma-separated scenario IDs 1-40",
    )
    parser.add_argument("--run", type=int, default=1, help="ns-3 run number")
    parser.add_argument("--seed", type=int, default=12345, help="ns-3 RNG seed")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="output directory (defaults to rl/results); partial runs are resumable",
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=DEFAULT_CHECKPOINT,
        help="existing RL checkpoint to evaluate; never modified",
    )
    args = parser.parse_args()
    if args.run < 1 or args.seed < 1:
        parser.error("--run and --seed must be positive integers")

    checkpoint = args.checkpoint.resolve()
    load_checkpoint(str(checkpoint))
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else ROOT / "rl" / "results"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "logs").mkdir(exist_ok=True)
    checkpoint_hash = file_sha256(checkpoint)
    config = {
        "scenarios": args.scenarios,
        "run": args.run,
        "seed": args.seed,
        "checkpoint": str(checkpoint),
        "checkpoint_sha256": checkpoint_hash,
        "simulation_seconds": SIM_TIME_SECONDS,
        "measurement_start_seconds": MEASUREMENT_START_SECONDS,
        "payload_bytes": PAYLOAD_BYTES,
    }
    manifest_path = output_dir / "final_40_scenario_comparison.metadata.json"
    partial_path = output_dir / "final_40_scenario_comparison.partial.csv"
    final_path = output_dir / "final_40_scenario_comparison.csv"
    summary_path = output_dir / "final_40_scenario_mean_summary.csv"
    report_path = output_dir / "final_40_scenario_report.md"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("config") != config:
            raise ValueError(
                f"Existing experiment in {output_dir} has a different run "
                "configuration/checkpoint; use a separate --output-dir."
            )
        if manifest.get("complete"):
            rows = read_csv_rows(final_path)
            validate_result_rows(rows, args.scenarios, args.run)
            print_report(rows, output_dir)
            return
    elif partial_path.exists() or final_path.exists():
        raise ValueError(
            "Result files exist without a matching metadata manifest; refusing "
            "to reuse or overwrite unverifiable outputs."
        )
    else:
        manifest = {"config": config, "complete": False, "completed_rows": 0}
        save_manifest(manifest_path, manifest)

    executables = ensure_simulator_targets()
    rows = read_csv_rows(partial_path)
    expected_keys = {
        (scenario, method, args.run)
        for scenario in args.scenarios
        for method in METHOD_TARGETS
    }
    existing_keys = [row_key(row) for row in rows]
    if len(existing_keys) != len(set(existing_keys)):
        raise ValueError(f"Partial results contain duplicate rows: {partial_path}")
    if not set(existing_keys).issubset(expected_keys):
        raise ValueError(f"Partial results contain unexpected rows: {partial_path}")
    rows_by_key = {row_key(row): row for row in rows}

    for scenario in args.scenarios:
        print(
            f"\nScenario {scenario}/40; run={args.run}; seed={args.seed}",
            flush=True,
        )
        expected_workload = None
        for method, target in METHOD_TARGETS.items():
            key = (scenario, method, args.run)
            saved_row = rows_by_key.get(key)
            if saved_row is not None:
                try:
                    workload = verify_saved_result(
                        saved_row, output_dir, args.seed
                    )
                    print(f"  Reusing validated {method} result", flush=True)
                except (OSError, ValueError, KeyError) as error:
                    print(
                        f"  Re-running invalid saved {method} result: {error}",
                        flush=True,
                    )
                    rows.remove(saved_row)
                    rows_by_key.pop(key)
                    saved_row = None

            if saved_row is None:
                print(f"  Running {method}", flush=True)
                if method == "RL Adaptive DCF":
                    raw_row, workload = run_rl(
                        scenario,
                        args.run,
                        args.seed,
                        checkpoint,
                        output_dir,
                        executables[target],
                    )
                else:
                    raw_row, workload = run_reference(
                        method,
                        target,
                        scenario,
                        args.run,
                        args.seed,
                        output_dir,
                    )
                row = row_with_scenario_name(raw_row)
                rows.append(row)
                rows_by_key[key] = row
                atomic_csv(partial_path, FIELDS, rows)
                manifest["completed_rows"] = len(rows)
                save_manifest(manifest_path, manifest)

            if expected_workload is None:
                expected_workload = workload
            elif workload != expected_workload:
                raise RuntimeError(
                    f"Workload mismatch in scenario {scenario}: "
                    f"{method}={workload!r}, expected={expected_workload!r}"
                )

    validate_result_rows(rows, args.scenarios, args.run)
    if args.scenarios == list(range(1, 41)) and len(rows) != 120:
        raise RuntimeError(f"Expected exactly 120 rows, collected {len(rows)}")
    if file_sha256(checkpoint) != checkpoint_hash:
        raise RuntimeError("Selected checkpoint changed during evaluation")
    rows.sort(key=lambda row: (
        int(row["scenario_id"]),
        list(METHOD_TARGETS).index(row["method"]),
        int(row["run"]),
    ))
    write_results(final_path, rows)
    write_mean_summary(summary_path, rows, args.scenarios, args.run)
    write_summary(report_path, rows, args.scenarios, args.run)
    manifest["complete"] = True
    manifest["completed_rows"] = len(rows)
    save_manifest(manifest_path, manifest)
    print_report(rows, output_dir)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Verify final five-scenario outputs, logs, checkpoint, and historical files."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

from finalize_five_scenario_comparison import (
    METHODS,
    SCENARIO_CONFIGS,
    _configuration_rows,
    validate_rows,
    validate_run_logs,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SHA256 = {
    "rl/q_table_v2.json": "c05335b5ea7d37ab2507da28b0f1190a4360c847ec6e54442d4ab8e0eba6eb25",
    "rl/results/final_40_scenario_comparison.csv": "8827044e9c9f1aaa24a9f8e9548d17c0b0724ff9dfd5acddccd4fde43a6f219b",
    "rl/results/final_40_scenario_mean_summary.csv": "9e979d4ff04f89dd087bcfcca00a2f2fd7d62c74ffd21005930d26d4dfc5f382",
    "rl/results/final_40_scenario_report.md": "b19fe3be247c2e9a932f39f3a20b182502c9777d04fe0c0e671c9555c5c59368",
}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path):
    with Path(path).open("r", newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def validate(results_dir, checkpoint):
    results_dir = Path(results_dir)
    checkpoint = Path(checkpoint)
    metadata = json.loads(
        (results_dir / "final_40_scenario_comparison.metadata.json").read_text(
            encoding="utf-8"
        )
    )
    config = metadata.get("config", {})
    if metadata.get("complete") is not True or metadata.get("completed_rows") != 15:
        raise ValueError("Runner metadata does not record exactly 15 completed rows")
    if config.get("scenarios") != [1, 2, 3, 4, 5]:
        raise ValueError("Runner metadata does not cover scenario IDs 1-5")
    if config.get("run") != 1 or config.get("seed") != 12345:
        raise ValueError("Runner metadata run/seed differs from run 1, seed 12345")
    if Path(config.get("checkpoint", "")).resolve() != checkpoint.resolve():
        raise ValueError("Runner metadata selected a different RL checkpoint")
    if config.get("checkpoint_sha256") != sha256(checkpoint):
        raise ValueError("Checkpoint changed after the simulations")

    raw_path = results_dir / "final_40_scenario_comparison.csv"
    rows = validate_rows(raw_path)
    if len(rows) != 15:
        raise ValueError(f"Expected 15 scenario/method rows, got {len(rows)}")
    validate_run_logs(rows, results_dir / "logs")

    saved = read_csv(results_dir / "five_scenario_comparison.csv")
    if len(saved) != 15:
        raise ValueError(f"Final comparison CSV contains {len(saved)} rows")
    if [(int(row["scenario_id"]), row["method"]) for row in saved] != [
        (row["scenario_id"], row["method"]) for row in rows
    ]:
        raise ValueError("Final comparison rows do not match validated raw results")

    run = config["run"]
    seed = config["seed"]
    expected_config = _configuration_rows(run, seed)
    actual_config = read_csv(results_dir / "five_scenario_configuration.csv")
    if len(actual_config) != 5:
        raise ValueError("Configuration CSV must have exactly five scenario rows")
    for actual, expected in zip(actual_config, expected_config):
        for field, value in expected.items():
            if actual[field] != str(value):
                raise ValueError(
                    f"Scenario {expected['scenario_id']} config mismatch in {field}: "
                    f"{actual[field]!r} != {value!r}"
                )
    if tuple(row["method"] for row in rows[:3]) != METHODS:
        raise ValueError("Unexpected method ordering in final results")

    for relative_path, expected_hash in EXPECTED_SHA256.items():
        if sha256(ROOT / relative_path) != expected_hash:
            raise ValueError(f"Preserved artifact hash changed: {relative_path}")

    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=ROOT / "rl" / "results" / "five_scenario_final_20261027",
    )
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "rl" / "q_table_v2.json")
    args = parser.parse_args()
    count = validate(args.results_dir, args.checkpoint)
    print(
        f"PASS: {count} result rows; scenario mappings, per-method workloads, "
        "run/seed, checkpoint, and historical result hashes validated."
    )


if __name__ == "__main__":
    main()

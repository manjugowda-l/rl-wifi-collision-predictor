import csv
import os
import subprocess
import sys
from datetime import datetime, timezone

import gymnasium as gym
import ns3ai_gym_env
import numpy as np

from common import (
    action_target_cw,
    discretize_for_schema,
    greedy_action,
    load_checkpoint,
)

TARGET = "wifi-ai-dcf"
MODEL_FILE = "rl/q_table_v2.json"
RESULTS_FILE = "wifi_ai_dcf_results_v2.csv"
SCENARIOS = tuple(range(1, 41))
SINGLE_SCENARIO_ENV = "WIFI_RL_EVAL_SINGLE_SCENARIO"
OUTPUT_DIR_ENV = "WIFI_RL_EVAL_OUTPUT_DIR"
RUN_ENV = "WIFI_RL_EVAL_RUN"
SEED_ENV = "WIFI_RL_EVAL_SEED"
MODEL_ENV = "WIFI_RL_EVAL_MODEL_FILE"
RESULTS_ENV = "WIFI_RL_RESULTS_FILE"
TARGET_ENV = "WIFI_RL_EVAL_TARGET"

RAW_FIELDS = [
    "scenario", "run", "tx_packets", "rx_packets", "lost_packets",
    "packet_loss_percent", "aggregate_throughput_mbps",
    "flow1_throughput_mbps", "flow2_throughput_mbps",
    "average_latency_ms", "average_queue_a", "average_queue_b",
    "max_queue_a", "max_queue_b", "queue_activity_observed",
    "average_queue_wait_ms", "mac_data_failures", "mac_final_failures",
    "successful_mac_transmissions", "final_cw",
]
SUMMARY_FIELDS = [
    "scenario", "run", "aggregate_throughput_mbps",
    "packet_loss_percent", "average_latency_ms",
    "average_queue_wait_ms", "mac_data_failures",
    "mac_final_failures", "final_cw",
]


def current_results_size(results_file):
    return os.path.getsize(results_file) if os.path.isfile(results_file) else 0


def read_appended_result(offset, scenario, run_number, results_file):
    if not os.path.isfile(results_file):
        raise FileNotFoundError(
            f"ns-3 did not create {results_file}; evaluation cannot report results."
        )
    with open(results_file, "r", newline="", encoding="utf-8") as result_file:
        result_file.seek(offset)
        rows = list(csv.DictReader(result_file, fieldnames=RAW_FIELDS))
    matching = [
        row
        for row in rows
        if row.get("scenario") == str(scenario)
        and row.get("run") == str(run_number)
    ]
    if len(matching) != 1:
        raise RuntimeError(
            f"Expected exactly one result for scenario {scenario}, run {run_number} "
            f"in {results_file}; found {len(matching)}."
        )
    row = matching[0]
    missing = [field for field in RAW_FIELDS if field not in row]
    if missing:
        raise ValueError(f"Incomplete ns-3 results row; missing {missing}")
    return row


def append_csv_row(path, fields, row):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0
    with open(path, "a", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fields, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def run_one_scenario(scenario, output_dir, run_number, seed):
    model_file = os.environ.get(MODEL_ENV, MODEL_FILE)
    results_file = os.environ.get(
        RESULTS_ENV,
        os.path.join(output_dir, f"rl_scenario{scenario:02d}_run{run_number}.csv"),
    )
    metadata, q_table = load_checkpoint(model_file)
    state_schema = metadata["state_schema"]
    print(
        f"\n######## RL EVALUATION - SCENARIO {scenario}, "
        f"RUN {run_number}, SEED {seed} ########"
    )

    result_offset = current_results_size(results_file)
    env = gym.make(
        "ns3ai_gym_env/Ns3-v0",
        targetName=os.environ.get(TARGET_ENV, TARGET),
        ns3Path="./",
        ns3Settings={"scenario": scenario, "run": run_number, "seed": seed},
        debug=False,
    )
    action_counts = {0: 0, 1: 0, 2: 0}
    unseen_states = 0
    total_reward = 0.0
    steps = 0
    try:
        observation, _info = env.reset()
        raw_observation = np.asarray(observation, dtype=np.float32)
        state = discretize_for_schema(raw_observation, state_schema)
        while True:
            current_cw = int(round(float(raw_observation[6])))
            if state in q_table:
                q_values = q_table[state]
            else:
                unseen_states += 1
                q_values = np.zeros(3, dtype=np.float64)
            action = greedy_action(q_values, current_cw)
            requested_cw = action_target_cw(current_cw, action)
            action_counts[action] += 1
            next_observation, reward, terminated, truncated, _next_info = env.step(
                np.asarray([action], dtype=np.int32)
            )
            raw_observation = np.asarray(next_observation, dtype=np.float32)
            effective_cw = int(round(float(raw_observation[6])))
            if effective_cw != requested_cw:
                raise RuntimeError(
                    f"CW action mismatch at scenario {scenario}, step {steps + 1}: "
                    f"action {action} requested {requested_cw}, "
                    f"but next observation reports {effective_cw}"
                )
            print(
                f"[POLICY] step={steps + 1} state={state} action={action} "
                f"requestedCW={requested_cw} effectiveCW={effective_cw}",
                flush=True,
            )
            state = discretize_for_schema(raw_observation, state_schema)
            total_reward += float(reward)
            steps += 1
            if terminated or truncated:
                break
    finally:
        env.close()

    result = read_appended_result(
        result_offset, scenario, run_number, results_file
    )
    append_csv_row(
        os.path.join(output_dir, "raw_results.csv"),
        RAW_FIELDS,
        result,
    )
    append_csv_row(
        os.path.join(output_dir, "summary.csv"),
        SUMMARY_FIELDS,
        result,
    )
    print(
        f"Scenario {scenario}, run {run_number}; steps: {steps}; "
        f"reward sum: {total_reward:.4f}; "
        f"unseen states: {unseen_states}; "
        f"actions decrease/keep/increase: "
        f"{action_counts[0]}/{action_counts[1]}/{action_counts[2]}"
    )
    print(
        "Measured: throughput={aggregate_throughput_mbps} Mbps, "
        "loss={packet_loss_percent}%, latency={average_latency_ms} ms, "
        "queue wait={average_queue_wait_ms} ms, "
        "MAC failures={mac_data_failures}, final CW={final_cw}".format(**result)
    )


def main():
    # Validate the model before launching ns-3, including in child processes.
    load_checkpoint(os.environ.get(MODEL_ENV, MODEL_FILE))
    child_scenario = os.environ.get(SINGLE_SCENARIO_ENV)
    if child_scenario is not None:
        scenario = int(child_scenario)
        if scenario not in SCENARIOS:
            raise ValueError(f"Evaluation scenario must be 1-40, got {scenario}")
        output_dir = os.environ.get(OUTPUT_DIR_ENV)
        if not output_dir:
            raise ValueError(f"{OUTPUT_DIR_ENV} is required in scenario worker mode")
        run_number = int(os.environ.get(RUN_ENV, "1"))
        seed = int(os.environ.get(SEED_ENV, "12345"))
        run_one_scenario(scenario, output_dir, run_number, seed)
        return

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = os.path.join("rl", "data", f"evaluation_{run_id}")
    os.makedirs(output_dir, exist_ok=False)
    for scenario in SCENARIOS:
        child_env = os.environ.copy()
        child_env[SINGLE_SCENARIO_ENV] = str(scenario)
        child_env[OUTPUT_DIR_ENV] = output_dir
        child_env[RUN_ENV] = child_env.get(RUN_ENV, "1")
        child_env[SEED_ENV] = child_env.get(SEED_ENV, "12345")
        subprocess.run([sys.executable, __file__], env=child_env, check=True)
    print(f"\nRaw measured results: {os.path.join(output_dir, 'raw_results.csv')}")
    print(f"Summary: {os.path.join(output_dir, 'summary.csv')}")


if __name__ == "__main__":
    main()

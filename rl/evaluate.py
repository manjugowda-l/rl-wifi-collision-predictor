import csv
import os
import subprocess
import sys
from datetime import datetime, timezone

import gymnasium as gym
import ns3ai_gym_env
import numpy as np

from common import discretize_state, greedy_action, load_checkpoint

TARGET = "wifi-ai-dcf"
MODEL_FILE = "rl/q_table_v2.json"
RESULTS_FILE = "wifi_ai_dcf_results_v2.csv"
SCENARIOS = (1, 2, 3, 4, 5)
SINGLE_SCENARIO_ENV = "WIFI_RL_EVAL_SINGLE_SCENARIO"
OUTPUT_DIR_ENV = "WIFI_RL_EVAL_OUTPUT_DIR"

RAW_FIELDS = [
    "scenario", "run", "tx_packets", "rx_packets", "lost_packets",
    "packet_loss_percent", "aggregate_throughput_mbps",
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


def current_results_size():
    return os.path.getsize(RESULTS_FILE) if os.path.isfile(RESULTS_FILE) else 0


def read_appended_result(offset, scenario, run_number):
    if not os.path.isfile(RESULTS_FILE):
        raise FileNotFoundError(
            f"ns-3 did not create {RESULTS_FILE}; evaluation cannot report results."
        )
    with open(RESULTS_FILE, "r", newline="", encoding="utf-8") as result_file:
        result_file.seek(offset)
        rows = list(csv.DictReader(result_file, fieldnames=RAW_FIELDS))
    matching = [
        row
        for row in rows
        if row.get("scenario") == str(scenario)
        and row.get("run") == str(run_number)
    ]
    if not matching:
        raise RuntimeError(
            f"ns-3 completed scenario {scenario}, run {run_number}, "
            f"but appended no matching row to {RESULTS_FILE}."
        )
    row = matching[-1]
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


def run_one_scenario(scenario, output_dir):
    _metadata, q_table = load_checkpoint(MODEL_FILE)
    print(f"\n######## RL EVALUATION - SCENARIO {scenario} ########")

    result_offset = current_results_size()
    env = gym.make(
        "ns3ai_gym_env/Ns3-v0",
        targetName=TARGET,
        ns3Path="./",
        ns3Settings={"scenario": scenario, "run": 1},
        debug=False,
    )
    action_counts = {0: 0, 1: 0, 2: 0}
    unseen_states = 0
    total_reward = 0.0
    steps = 0
    try:
        observation, _info = env.reset()
        raw_observation = np.asarray(observation, dtype=np.float32)
        state = discretize_state(raw_observation)
        while True:
            current_cw = int(round(float(raw_observation[6])))
            if state in q_table:
                q_values = q_table[state]
            else:
                unseen_states += 1
                q_values = np.zeros(3, dtype=np.float64)
            action = greedy_action(q_values, current_cw)
            action_counts[action] += 1
            next_observation, reward, terminated, truncated, _next_info = env.step(
                np.asarray([action], dtype=np.int32)
            )
            raw_observation = np.asarray(next_observation, dtype=np.float32)
            state = discretize_state(raw_observation)
            total_reward += float(reward)
            steps += 1
            if terminated or truncated:
                break
    finally:
        env.close()

    result = read_appended_result(result_offset, scenario, 1)
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
        f"Steps: {steps}; reward sum: {total_reward:.4f}; "
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
    load_checkpoint(MODEL_FILE)
    child_scenario = os.environ.get(SINGLE_SCENARIO_ENV)
    if child_scenario is not None:
        scenario = int(child_scenario)
        if scenario not in SCENARIOS:
            raise ValueError(f"Evaluation scenario must be 1-5, got {scenario}")
        output_dir = os.environ.get(OUTPUT_DIR_ENV)
        if not output_dir:
            raise ValueError(f"{OUTPUT_DIR_ENV} is required in scenario worker mode")
        run_one_scenario(scenario, output_dir)
        return

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = os.path.join("rl", "data", f"evaluation_{run_id}")
    os.makedirs(output_dir, exist_ok=False)
    for scenario in SCENARIOS:
        child_env = os.environ.copy()
        child_env[SINGLE_SCENARIO_ENV] = str(scenario)
        child_env[OUTPUT_DIR_ENV] = output_dir
        subprocess.run([sys.executable, __file__], env=child_env, check=True)
    print(f"\nRaw measured results: {os.path.join(output_dir, 'raw_results.csv')}")
    print(f"Summary: {os.path.join(output_dir, 'summary.csv')}")


if __name__ == "__main__":
    main()

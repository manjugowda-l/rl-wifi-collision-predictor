import csv
import os
import subprocess
import sys
from datetime import datetime, timezone

import gymnasium as gym
import ns3ai_gym_env
import numpy as np

from common import (
    STATE_SCHEMA,
    STATE_SCHEMA_V2,
    allowed_actions,
    action_target_cw,
    discretize_for_schema,
    greedy_action,
    load_checkpoint,
    save_checkpoint,
)

TARGET = "wifi-ai-dcf"
SCENARIOS = range(1, 41)
MODEL_FILE = os.environ.get("WIFI_RL_TRAIN_MODEL_FILE", "rl/q_table_v2.json")
DATA_ROOT = os.environ.get("WIFI_RL_TRAIN_DATA_ROOT", "rl/data")
TRAIN_SEED = int(os.environ.get("WIFI_RL_TRAIN_SEED", "98765"))
RL_INTERVAL = 0.1

ALPHA = 0.10
GAMMA = 0.95
EPSILON_START = 1.0
EPSILON_MIN = 0.05
EPSILON_DECAY_PER_STEP = 0.9999
SINGLE_SCENARIO_ENV = "WIFI_RL_TRAIN_SINGLE_SCENARIO"

CSV_HEADER = [
    "episode_id", "scenario", "run", "step", "simulation_time",
    "queueA", "queueB", "queueGrowthA", "queueGrowthB",
    "packetLossBin", "macFailureBin", "latencyBin", "currentCW",
    "action", "cwBefore", "requestedCW", "effectiveCW", "reward",
    "nextQueueA", "nextQueueB", "nextQueueGrowthA", "nextQueueGrowthB",
    "nextPacketLossBin", "nextMacFailureBin", "nextLatencyBin", "nextCW",
    "epsilon", "qBefore", "qAfter",
    "rawQueueA", "rawQueueB", "rawQueueGrowthA", "rawQueueGrowthB",
    "rawPacketLoss", "rawMacFailures", "rawLatencyMs",
    "throughputMbps", "feedbackPacketLoss", "feedbackLatencyMs",
    "feedbackMacFailures", "feedbackMacFinalFailures",
]
FEEDBACK_FIELDS = (
    "throughputMbps",
    "packetLoss",
    "latencyMs",
    "macFailures",
    "macFinalFailures",
)


def initialize_or_resume(scenario):
    if os.path.isfile(MODEL_FILE):
        metadata, q_table = load_checkpoint(MODEL_FILE)
        metadata.setdefault("state_schema", STATE_SCHEMA_V2)
        next_scenario = metadata.get("next_scenario")
        if not isinstance(next_scenario, int) or next_scenario not in range(1, 42):
            raise ValueError(f"Invalid next_scenario in checkpoint {MODEL_FILE}")
        if scenario != next_scenario:
            raise ValueError(
                f"Training checkpoint expects scenario {next_scenario}, "
                f"but child was asked to run {scenario}."
            )
        return metadata, q_table

    if scenario != 1:
        raise FileNotFoundError(
            f"Cannot start scenario {scenario}: {MODEL_FILE} is missing and "
            "training must start at scenario 1."
        )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = os.path.join(DATA_ROOT, f"training_{run_id}")
    os.makedirs(run_dir, exist_ok=False)
    return {
        "next_scenario": 1,
        "epsilon": EPSILON_START,
        "completed_scenarios": [],
        "run_dir": run_dir,
        "total_transitions": 0,
        "state_schema": STATE_SCHEMA,
        "reward_definition": "multi-objective-throughput-loss-latency-v3",
        "training_config": {
            "alpha": ALPHA,
            "gamma": GAMMA,
            "epsilon_start": EPSILON_START,
            "epsilon_min": EPSILON_MIN,
            "epsilon_decay_per_step": EPSILON_DECAY_PER_STEP,
            "seed": TRAIN_SEED,
            "run_policy": "run_number_equals_scenario",
        },
    }, {}


def run_one_scenario(scenario):
    metadata, q_table = initialize_or_resume(scenario)
    np.random.seed(12345 + scenario)
    run_number = scenario
    epsilon = float(metadata["epsilon"])
    run_dir = metadata["run_dir"]
    os.makedirs(run_dir, exist_ok=True)
    scenario_csv = os.path.join(run_dir, f"scenario{scenario:02d}_training.csv")
    combined_csv = os.path.join(run_dir, "all_training_data.csv")
    episode_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")

    def get_q_values(state):
        if state not in q_table:
            q_table[state] = np.zeros(3, dtype=np.float64)
        return q_table[state]

    print(
        f"[START] Scenario {scenario}/40, run={run_number}, "
        f"epsilon={epsilon:.4f}, checkpoint={MODEL_FILE}",
        flush=True,
    )
    env = gym.make(
        "ns3ai_gym_env/Ns3-v0",
        targetName=TARGET,
        ns3Path="./",
        ns3Settings={"scenario": scenario, "run": run_number, "seed": TRAIN_SEED},
        debug=False,
    )
    rows_written = 0
    total_reward = 0.0
    try:
        observation, _info = env.reset()
        raw_state = np.asarray(observation, dtype=np.float32)
        state_schema = metadata.get("state_schema", STATE_SCHEMA_V2)
        state = discretize_for_schema(raw_state, state_schema)
        steps = 0

        with open(scenario_csv, "a", newline="", encoding="utf-8") as scenario_file, \
                open(combined_csv, "a", newline="", encoding="utf-8") as combined_file:
            scenario_writer = csv.writer(scenario_file)
            combined_writer = csv.writer(combined_file)
            if scenario_file.tell() == 0:
                scenario_writer.writerow(CSV_HEADER)
            if combined_file.tell() == 0:
                combined_writer.writerow(CSV_HEADER)

            while True:
                cw_before = int(round(float(raw_state[6])))
                actions = allowed_actions(cw_before)
                if np.random.random() < epsilon:
                    action_value = int(np.random.choice(actions))
                else:
                    action_value = greedy_action(get_q_values(state), cw_before)

                next_observation, reward, terminated, truncated, next_info = env.step(
                    np.asarray([action_value], dtype=np.int32)
                )
                next_raw_state = np.asarray(next_observation, dtype=np.float32)
                next_state = discretize_for_schema(next_raw_state, state_schema)
                cw_after = int(round(float(next_raw_state[6])))
                requested_cw = action_target_cw(cw_before, action_value)
                if cw_after != requested_cw:
                    raise RuntimeError(
                        f"CW action mismatch at scenario {scenario}, step {steps + 1}: "
                        f"action {action_value} requested {requested_cw}, "
                        f"but next observation reports {cw_after}"
                    )
                if not isinstance(next_info, dict):
                    raise TypeError("ns3-ai step feedback must be a dictionary")
                missing_feedback = [
                    name for name in FEEDBACK_FIELDS if name not in next_info
                ]
                if missing_feedback:
                    raise KeyError(
                        f"ns3-ai step feedback is missing {missing_feedback}"
                    )
                feedback = {
                    name: float(next_info[name]) for name in FEEDBACK_FIELDS
                }
                if not all(np.isfinite(value) for value in feedback.values()):
                    raise ValueError("ns3-ai step feedback contains non-finite values")
                reward = float(reward)
                if not np.isfinite(reward) or not -1.000001 <= reward <= 1.000001:
                    raise ValueError(f"Invalid normalized reward from ns-3: {reward}")

                current_q = get_q_values(state)
                next_q = get_q_values(next_state)
                q_before = float(current_q[action_value])
                if terminated or truncated:
                    target = reward
                else:
                    next_actions = allowed_actions(cw_after)
                    target = reward + GAMMA * max(
                        float(next_q[action]) for action in next_actions
                    )
                current_q[action_value] += ALPHA * (
                    target - current_q[action_value]
                )
                q_after = float(current_q[action_value])

                row = [
                    episode_id, scenario, run_number, steps + 1,
                    f"{1.0 + steps * RL_INTERVAL:.3f}",
                    *state[:4], state[4], state[5], state[6], state[7],
                    action_value, cw_before,
                    requested_cw,
                    cw_after, reward,
                    *next_state[:4], next_state[4], next_state[5],
                    next_state[6], next_state[7], epsilon, q_before, q_after,
                    *[float(value) for value in raw_state[:4]],
                    float(raw_state[4]), float(raw_state[5]), float(raw_state[7]),
                    feedback["throughputMbps"], feedback["packetLoss"],
                    feedback["latencyMs"], feedback["macFailures"],
                    feedback["macFinalFailures"],
                ]
                scenario_writer.writerow(row)
                combined_writer.writerow(row)
                scenario_file.flush()
                combined_file.flush()

                total_reward += reward
                steps += 1
                metadata["total_transitions"] = (
                    int(metadata.get("total_transitions", 0)) + 1
                )
                epsilon = max(
                    EPSILON_MIN, epsilon * EPSILON_DECAY_PER_STEP
                )
                rows_written += 1
                state, raw_state = next_state, next_raw_state
                if terminated or truncated:
                    break
    finally:
        env.close()

    if rows_written == 0:
        raise RuntimeError(f"Scenario {scenario} produced no RL transitions")

    metadata["epsilon"] = epsilon
    metadata["next_scenario"] = scenario + 1
    completed = list(metadata.get("completed_scenarios", []))
    completed.append(scenario)
    metadata["completed_scenarios"] = completed
    save_checkpoint(MODEL_FILE, q_table, metadata)
    print(
        f"[DONE] Scenario {scenario}: steps={steps}, "
        f"reward_sum={total_reward:.4f}, epsilon={epsilon:.4f}, "
        f"Q-states={len(q_table)}, state_schema={state_schema}, "
        f"reward_definition={metadata.get('reward_definition', 'legacy-v2')}"
    )
    print(f"[CHECKPOINT] Safely saved {MODEL_FILE}")


def main():
    requested_scenario = os.environ.get(SINGLE_SCENARIO_ENV)
    if requested_scenario is not None:
        scenario = int(requested_scenario)
        if scenario not in range(1, 41):
            raise ValueError(f"Training scenario must be 1-40, got {scenario}")
        run_one_scenario(scenario)
        return

    if os.path.isfile(MODEL_FILE):
        metadata, _q_table = load_checkpoint(MODEL_FILE)
        first_scenario = metadata.get("next_scenario")
        if not isinstance(first_scenario, int) or first_scenario not in range(1, 42):
            raise ValueError(f"Invalid next_scenario in checkpoint {MODEL_FILE}")
    else:
        first_scenario = 1

    if first_scenario == 41:
        print(f"All 40 training scenarios are complete in {MODEL_FILE}.")
        return

    for scenario in range(first_scenario, 41):
        child_env = os.environ.copy()
        child_env[SINGLE_SCENARIO_ENV] = str(scenario)
        subprocess.run([sys.executable, __file__], env=child_env, check=True)

    print(f"Training complete. Checkpoint: {MODEL_FILE}")


if __name__ == "__main__":
    main()

import csv
import os
import pickle
import subprocess
import sys

import gymnasium as gym
import ns3ai_gym_env
import numpy as np


TARGET = "wifi-ai-dcf"
MODEL_FILE = "rl/q_table.pkl"
RESULTS_FILE = "wifi_ai_dcf_results.csv"

# Final evaluation scenarios
SCENARIOS = [1]

# No exploration during evaluation
EPSILON = 0.0


# ============================================================
# STATE DISCRETIZATION
# ============================================================

def discretize_state(state):

    queue_a = min(int(state[0]), 10)
    queue_b = min(int(state[1]), 10)

    growth_a = int(np.clip(state[2], -5, 5))
    growth_b = int(np.clip(state[3], -5, 5))

    packet_loss = int(state[4] > 0)
    mac_failures = int(state[5] > 0)

    cw = int(state[6])

    if cw <= 3:
        cw_bin = 3
    elif cw <= 7:
        cw_bin = 7
    elif cw <= 15:
        cw_bin = 15
    elif cw <= 31:
        cw_bin = 31
    elif cw <= 63:
        cw_bin = 63
    elif cw <= 127:
        cw_bin = 127
    elif cw <= 255:
        cw_bin = 255
    else:
        cw_bin = 1023

    return (
        queue_a,
        queue_b,
        growth_a,
        growth_b,
        packet_loss,
        mac_failures,
        cw_bin,
    )


# ============================================================
# LOAD TRAINED Q-TABLE
# ============================================================

print("========================================")
print("       WIFI AI DCF - EVALUATION")
print("========================================")

if not os.path.exists(MODEL_FILE):
    raise FileNotFoundError(
        f"Trained Q-table not found: {MODEL_FILE}"
    )

with open(MODEL_FILE, "rb") as f:
    q_table = pickle.load(f)

print("Loaded Q-states:", len(q_table))
print("Evaluation epsilon:", EPSILON)
print("Scenarios:", SCENARIOS)
print("========================================")


def get_q_values(state):

    return q_table.get(
        state,
        np.zeros(3, dtype=np.float32)
    )


def choose_best_action(state):

    q_values = get_q_values(state)

    return int(np.argmax(q_values))


# ============================================================
# READ FINAL NS-3 RESULTS
# ============================================================

def get_latest_results(scenario, run_number=1):

    if not os.path.exists(RESULTS_FILE):
        return None

    latest = None

    with open(RESULTS_FILE, newline="") as f:

        reader = csv.DictReader(f)

        for row in reader:

            if (
                int(row["scenario"]) == scenario
                and int(row["run"]) == run_number
            ):
                latest = row

    return latest


def print_final_results(results):

    if results is None:

        print()
        print("[WARNING] No final ns-3 results found.")
        return

    print()
    print("==================================================")
    print("                 FINAL RESULTS")
    print("==================================================")

    print(f"Scenario                    : {results['scenario']}")
    print(f"Random run                  : {results['run']}")
    print(f"Total TX packets            : {results['tx_packets']}")
    print(f"Total RX packets            : {results['rx_packets']}")
    print(f"Lost packets                : {results['lost_packets']}")
    print(f"Packet loss                 : {results['packet_loss_percent']} %")
    print(f"Average latency             : {results['average_latency_ms']} ms")
    print(f"Average queue A             : {results['average_queue_a']} packets")
    print(f"Average queue B             : {results['average_queue_b']} packets")
    print(f"Maximum queue A             : {results['max_queue_a']} packets")
    print(f"Maximum queue B             : {results['max_queue_b']} packets")

    activity = (
        "YES"
        if int(float(results["queue_activity_observed"])) > 0
        else "NO"
    )

    print(f"Queue activity observed     : {activity}")
    print(
        f"Average queue waiting time  : "
        f"{results['average_queue_wait_ms']} ms"
    )
    print(f"MAC data failures           : {results['mac_data_failures']}")
    print(f"MAC final failures          : {results['mac_final_failures']}")
    print(
        f"Successful MAC transmissions: "
        f"{results['successful_mac_transmissions']}"
    )
    print(f"Final CW                    : {results['final_cw']}")
    print("==================================================")


# ============================================================
# RUN ONE SCENARIO
# ============================================================

def run_one_scenario(scenario):

    print()
    print("########################################")
    print(f"       RL EVALUATION - SCENARIO {scenario}")
    print("########################################")

    env = gym.make(
        "ns3ai_gym_env/Ns3-v0",
        targetName=TARGET,
        ns3Path="./",
        ns3Settings={
            "scenario": scenario,
            "run": 1,
        },
        debug=False,
    )

    steps = 0
    total_reward = 0.0

    action_counts = {
        0: 0,
        1: 0,
        2: 0,
    }

    try:

        # ----------------------------------------------------
        # START NS-3 AND RECEIVE INITIAL STATE
        # ----------------------------------------------------

        obs, info = env.reset()

        state = discretize_state(
            np.asarray(obs, dtype=np.float32)
        )

        # ----------------------------------------------------
        # RL LOOP
        # ----------------------------------------------------

        while True:

            # Select best learned action.
            action_value = choose_best_action(state)

            action_counts[action_value] += 1

            action = np.asarray(
                [action_value],
                dtype=np.int32
            )

            # Send action to ns-3 and receive next state.
            (
                next_obs,
                reward,
                terminated,
                truncated,
                info
            ) = env.step(action)

            next_state = discretize_state(
                np.asarray(next_obs, dtype=np.float32)
            )

            total_reward += float(reward)
            steps += 1

            state = next_state

            if terminated or truncated:
                break

        # ----------------------------------------------------
        # RL SUMMARY
        # ----------------------------------------------------

        print()
        print("----------------------------------------")
        print(f"SCENARIO {scenario} RL SUMMARY")
        print("----------------------------------------")
        print(f"Steps              : {steps}")
        print(f"Transitions        : {steps}")
        print(f"Total reward       : {total_reward:.4f}")
        print()
        print("Actions selected:")
        print(f"Decrease CW        : {action_counts[0]}")
        print(f"Keep CW            : {action_counts[1]}")
        print(f"Increase CW        : {action_counts[2]}")
        print("----------------------------------------")

    finally:

        # ----------------------------------------------------
        # IMPORTANT:
        # Close ns-3 completely before reading final CSV.
        # ----------------------------------------------------

        env.close()

    # --------------------------------------------------------
    # READ FINAL C++ RESULTS AFTER NS-3 HAS CLOSED
    # --------------------------------------------------------

    results = get_latest_results(
        scenario,
        1
    )

    print_final_results(results)


# ============================================================
# MAIN
#
# Each scenario is executed in a separate Python process.
# This is intentional because ns3ai_gym_env uses singleton
# environment/experiment objects.
# ============================================================

if __name__ == "__main__":

    # --------------------------------------------------------
    # CHILD PROCESS MODE
    # --------------------------------------------------------
    #
    # The parent process sets EVAL_SINGLE_SCENARIO.
    # That child runs exactly one scenario and exits.
    #

    single_scenario = os.environ.get(
        "EVAL_SINGLE_SCENARIO"
    )

    if single_scenario is not None:

        scenario = int(single_scenario)

        # Load the trained model in this fresh process.
        run_one_scenario(scenario)

        sys.exit(0)

    # --------------------------------------------------------
    # PARENT PROCESS
    # --------------------------------------------------------

    completed = 0

    for scenario in SCENARIOS:

        print()
        print("==================================================")
        print(f"STARTING SCENARIO {scenario}")
        print("==================================================")

        child_env = os.environ.copy()

        child_env["EVAL_SINGLE_SCENARIO"] = str(
            scenario
        )

        result = subprocess.run(
            [sys.executable, __file__],
            env=child_env,
        )

        if result.returncode != 0:

            print()
            print(
                f"[ERROR] Scenario {scenario} "
                f"exited with code {result.returncode}"
            )

            break

        completed += 1

        print()
        print("==================================================")
        print(f"SCENARIO {scenario} COMPLETED")
        print("==================================================")


    print()
    print("==================================================")
    print("           RL EVALUATION FINISHED")
    print("==================================================")
    print("Scenarios completed:", completed)
    print("==================================================")
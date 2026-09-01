import csv
import os
import pickle

import gymnasium as gym
import ns3ai_gym_env
import numpy as np


# ============================================================
# CONFIGURATION
# ============================================================

TARGET = "wifi-ai-dcf"

MODEL_FILE = "rl/q_table.pkl"

RESULTS_FILE = "wifi_ai_dcf_results.csv"

# ============================================================
# EVALUATE ONE SCENARIO AT A TIME
# ============================================================

SCENARIOS = [3]

# No exploration during evaluation.
EPSILON = 0.0


# ============================================================
# STATE DISCRETIZATION
# MUST MATCH agent.py
# ============================================================

def discretize_state(state, info):

    queue_a = min(
        int(state[0]),
        10
    )

    queue_b = min(
        int(state[1]),
        10
    )

    growth_a = int(
        np.clip(
            state[2],
            -5,
            5
        )
    )

    growth_b = int(
        np.clip(
            state[3],
            -5,
            5
        )
    )

    packet_loss = int(
        state[4] > 0
    )

    mac_failures = int(
        state[5] > 0
    )

    cw = int(
        state[6]
    )

    # --------------------------------------------------------
    # CW BIN
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # LATENCY BIN
    # MUST MATCH agent.py
    # --------------------------------------------------------

    try:

        latency = float(
            info.get(
                "latencyMs",
                0.0
            )
        )

    except (
        TypeError,
        ValueError
    ):

        latency = 0.0

    if latency < 1.0:
        latency_bin = 0

    elif latency < 5.0:
        latency_bin = 1

    elif latency < 10.0:
        latency_bin = 2

    elif latency < 25.0:
        latency_bin = 3

    elif latency < 50.0:
        latency_bin = 4

    elif latency < 100.0:
        latency_bin = 5

    else:
        latency_bin = 6

    return (
        queue_a,
        queue_b,
        growth_a,
        growth_b,
        packet_loss,
        mac_failures,
        latency_bin,
        cw_bin,
    )


# ============================================================
# LOAD Q-TABLE
# ============================================================

print()
print("========================================")
print("       WIFI AI DCF - EVALUATION")
print("========================================")

if not os.path.exists(
    MODEL_FILE
):

    raise FileNotFoundError(
        f"Trained Q-table not found: "
        f"{MODEL_FILE}"
    )


with open(
    MODEL_FILE,
    "rb"
) as f:

    q_table = pickle.load(
        f
    )


print(
    f"Loaded Q-states : "
    f"{len(q_table)}"
)

print(
    f"Evaluation epsilon : "
    f"{EPSILON}"
)

print(
    f"Scenarios : "
    f"{SCENARIOS}"
)

print("========================================")


# ============================================================
# Q VALUES
# ============================================================

def get_q_values(state):

    return q_table.get(
        state,
        np.zeros(
            3,
            dtype=np.float32
        )
    )


# ============================================================
# BEST ACTION
#
# 0 = DECREASE CW
# 1 = KEEP CW
# 2 = INCREASE CW
# ============================================================

def choose_best_action(state):

    q_values = get_q_values(
        state
    )

    return int(
        np.argmax(q_values)
    )


# ============================================================
# READ FINAL NS-3 RESULTS
# ============================================================

def get_latest_results(
    scenario,
    run_number=1
):

    if not os.path.exists(
        RESULTS_FILE
    ):

        return None

    latest = None

    with open(
        RESULTS_FILE,
        newline=""
    ) as f:

        reader = csv.DictReader(
            f
        )

        for row in reader:

            try:

                row_scenario = int(
                    row["scenario"]
                )

                row_run = int(
                    row["run"]
                )

            except (
                KeyError,
                ValueError
            ):

                continue

            if (
                row_scenario == scenario
                and row_run == run_number
            ):

                latest = row

    return latest


# ============================================================
# PRINT FINAL RESULTS
# ============================================================

def print_final_results(
    results
):

    if results is None:

        print()
        print(
            "[WARNING] "
            "No final ns-3 results found."
        )

        return

    print()
    print("==================================================")
    print("                 FINAL RESULTS")
    print("==================================================")

    print(
        f"Scenario                    : "
        f"{results['scenario']}"
    )

    print(
        f"Random run                  : "
        f"{results['run']}"
    )

    print(
        f"Total TX packets            : "
        f"{results['tx_packets']}"
    )

    print(
        f"Total RX packets            : "
        f"{results['rx_packets']}"
    )

    print(
        f"Lost packets                : "
        f"{results['lost_packets']}"
    )

    print(
        f"Packet loss                 : "
        f"{results['packet_loss_percent']} %"
    )

    print(
        f"Average latency             : "
        f"{results['average_latency_ms']} ms"
    )

    print(
        f"Average queue A             : "
        f"{results['average_queue_a']} packets"
    )

    print(
        f"Average queue B             : "
        f"{results['average_queue_b']} packets"
    )

    print(
        f"Maximum queue A             : "
        f"{results['max_queue_a']} packets"
    )

    print(
        f"Maximum queue B             : "
        f"{results['max_queue_b']} packets"
    )

    activity = (
        "YES"
        if int(
            float(
                results[
                    "queue_activity_observed"
                ]
            )
        ) > 0
        else "NO"
    )

    print(
        f"Queue activity observed     : "
        f"{activity}"
    )

    print(
        f"Average queue waiting time  : "
        f"{results['average_queue_wait_ms']} ms"
    )

    print(
        f"MAC data failures           : "
        f"{results['mac_data_failures']}"
    )

    print(
        f"MAC final failures          : "
        f"{results['mac_final_failures']}"
    )

    print(
        f"Successful MAC transmissions: "
        f"{results['successful_mac_transmissions']}"
    )

    print(
        f"Final CW                    : "
        f"{results['final_cw']}"
    )

    print("==================================================")


# ============================================================
# RUN ONE SCENARIO
# ============================================================

def run_one_scenario(
    scenario
):

    print()
    print("########################################")
    print(
        f"       RL EVALUATION - "
        f"SCENARIO {scenario}"
    )
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

    # This is only for displaying the C++ reward.
    # Evaluation does NOT update the Q-table.
    total_environment_reward = 0.0

    action_counts = {
        0: 0,
        1: 0,
        2: 0,
    }

    try:

        # ----------------------------------------------------
        # START NS-3
        # ----------------------------------------------------

        obs, info = env.reset()

        state = discretize_state(
            np.asarray(
                obs,
                dtype=np.float32
            ),
            info
        )

        # ----------------------------------------------------
        # EVALUATION LOOP
        # ----------------------------------------------------

        while True:

            action_value = (
                choose_best_action(
                    state
                )
            )

            action_counts[
                action_value
            ] += 1

            action = np.asarray(
                [action_value],
                dtype=np.int32
            )

            (
                next_obs,
                reward,
                terminated,
                truncated,
                next_info
            ) = env.step(
                action
            )

            next_state = (
                discretize_state(
                    np.asarray(
                        next_obs,
                        dtype=np.float32
                    ),
                    next_info
                )
            )

            total_environment_reward += (
                float(reward)
            )

            steps += 1

            state = next_state

            if (
                terminated
                or truncated
            ):

                break

        # ----------------------------------------------------
        # EVALUATION SUMMARY
        # ----------------------------------------------------

        print()
        print("----------------------------------------")
        print(
            f"SCENARIO {scenario} "
            f"RL SUMMARY"
        )
        print("----------------------------------------")

        print(
            f"Steps              : "
            f"{steps}"
        )

        print(
            f"Transitions        : "
            f"{steps}"
        )

        print(
            f"Environment reward : "
            f"{total_environment_reward:.4f}"
        )

        print()
        print("Actions selected:")

        print(
            f"Decrease CW        : "
            f"{action_counts[0]}"
        )

        print(
            f"Keep CW            : "
            f"{action_counts[1]}"
        )

        print(
            f"Increase CW        : "
            f"{action_counts[2]}"
        )

        print("----------------------------------------")

    finally:

        # ----------------------------------------------------
        # CLOSE NS-3
        # ----------------------------------------------------

        env.close()

    # --------------------------------------------------------
    # READ FINAL C++ RESULTS
    # --------------------------------------------------------

    results = get_latest_results(
        scenario,
        1
    )

    print_final_results(
        results
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    for scenario in SCENARIOS:

        run_one_scenario(
            scenario
        )

    print()
    print("==================================================")
    print("           RL EVALUATION FINISHED")
    print("==================================================")

    print(
        "Scenarios completed:",
        len(SCENARIOS)
    )

    print("==================================================")
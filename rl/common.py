"""Shared state, action, and checkpoint handling for the ns-3 DCF agent."""

import json
import math
import os
import tempfile

import numpy as np

STATE_SCHEMA_V2 = "queue-growth-loss-mac-latency-cw-v2"
STATE_SCHEMA = "queue-regimes-signed-growth-loss-mac-latency-cw-v3"
ACTION_SCHEMA = "decrease-keep-increase-v1"
CHECKPOINT_VERSION_V2 = 2
CHECKPOINT_VERSION = 3

CW_VALUES = (7, 15, 31, 63, 127)
ACTION_DECREASE = 0
ACTION_KEEP = 1
ACTION_INCREASE = 2


def _validated_observation(observation):
    values = np.asarray(observation, dtype=np.float64)
    if values.shape != (8,) or not np.all(np.isfinite(values)):
        raise ValueError(
            f"Expected 8 finite observation values from wifi-ai-dcf, got shape {values.shape}"
        )
    return values


def discretize_state_v2(observation):
    """Encode [queues, growth, loss, retries, CW, latency] into an 8-int state.

    The tuple is (queueA, queueB, growthA, growthB, loss bin, retry bin,
    latency bin, selected CW). Latency bin 7 means no sample arrived.
    """
    values = _validated_observation(observation)

    queue_a, queue_b = (int(np.clip(value, 0, 10)) for value in values[:2])
    growth_a, growth_b = (
        int(np.clip(value, -5, 5)) for value in values[2:4]
    )

    packet_loss = float(values[4])
    if packet_loss < 0.0 or packet_loss > 1.0:
        raise ValueError(f"Packet-loss observation is outside [0, 1]: {packet_loss}")
    if packet_loss == 0.0:
        loss_bin = 0
    elif packet_loss < 0.01:
        loss_bin = 1
    elif packet_loss < 0.05:
        loss_bin = 2
    elif packet_loss < 0.20:
        loss_bin = 3
    else:
        loss_bin = 4

    failures = max(0, int(values[5]))
    if failures == 0:
        failure_bin = 0
    elif failures == 1:
        failure_bin = 1
    elif failures <= 4:
        failure_bin = 2
    elif failures <= 9:
        failure_bin = 3
    else:
        failure_bin = 4

    observed_cw = int(round(float(values[6])))
    if observed_cw not in CW_VALUES:
        raise ValueError(f"Invalid CW in observation: {observed_cw}")

    latency_ms = float(values[7])
    if latency_ms < 0.0:
        latency_bin = 7
    elif latency_ms < 1.0:
        latency_bin = 0
    elif latency_ms < 5.0:
        latency_bin = 1
    elif latency_ms < 10.0:
        latency_bin = 2
    elif latency_ms < 25.0:
        latency_bin = 3
    elif latency_ms < 50.0:
        latency_bin = 4
    elif latency_ms < 100.0:
        latency_bin = 5
    else:
        latency_bin = 6

    return (
        queue_a,
        queue_b,
        growth_a,
        growth_b,
        loss_bin,
        failure_bin,
        latency_bin,
        observed_cw,
    )


def discretize_state(observation):
    """Encode queues by load regime and signed growth magnitude for checkpoint v3."""
    values = _validated_observation(observation)
    queue_edges = (0, 1, 3, 6, 11, 26, 51, 101)

    def queue_bin(value):
        packets = max(0, int(value))
        return sum(packets >= edge for edge in queue_edges[1:])

    def growth_bin(value):
        delta = int(value)
        if delta <= -50:
            return -4
        if delta <= -10:
            return -3
        if delta <= -3:
            return -2
        if delta < 0:
            return -1
        if delta == 0:
            return 0
        if delta <= 3:
            return 1
        if delta <= 10:
            return 2
        if delta <= 50:
            return 3
        return 4

    packet_loss = float(values[4])
    if packet_loss < 0.0 or packet_loss > 1.0:
        raise ValueError(f"Packet-loss observation is outside [0, 1]: {packet_loss}")
    if packet_loss == 0.0:
        loss_bin = 0
    elif packet_loss < 0.01:
        loss_bin = 1
    elif packet_loss < 0.05:
        loss_bin = 2
    elif packet_loss < 0.20:
        loss_bin = 3
    else:
        loss_bin = 4

    failures = max(0, int(values[5]))
    if failures == 0:
        failure_bin = 0
    elif failures == 1:
        failure_bin = 1
    elif failures <= 4:
        failure_bin = 2
    elif failures <= 9:
        failure_bin = 3
    else:
        failure_bin = 4

    observed_cw = int(round(float(values[6])))
    if observed_cw not in CW_VALUES:
        raise ValueError(f"Invalid CW in observation: {observed_cw}")

    latency_ms = float(values[7])
    if latency_ms < 0.0:
        latency_bin = 7
    elif latency_ms < 1.0:
        latency_bin = 0
    elif latency_ms < 5.0:
        latency_bin = 1
    elif latency_ms < 10.0:
        latency_bin = 2
    elif latency_ms < 25.0:
        latency_bin = 3
    elif latency_ms < 50.0:
        latency_bin = 4
    elif latency_ms < 100.0:
        latency_bin = 5
    else:
        latency_bin = 6

    return (
        queue_bin(values[0]),
        queue_bin(values[1]),
        growth_bin(values[2]),
        growth_bin(values[3]),
        loss_bin,
        failure_bin,
        latency_bin,
        observed_cw,
    )


def discretize_for_schema(observation, schema):
    if schema == STATE_SCHEMA_V2:
        return discretize_state_v2(observation)
    if schema == STATE_SCHEMA:
        return discretize_state(observation)
    raise ValueError(f"Unsupported state schema: {schema}")


def allowed_actions(current_cw):
    cw = int(round(float(current_cw)))
    if cw not in CW_VALUES:
        raise ValueError(f"Invalid CW for action selection: {cw}")
    actions = [ACTION_KEEP]
    if cw > CW_VALUES[0]:
        actions.append(ACTION_DECREASE)
    if cw < CW_VALUES[-1]:
        actions.append(ACTION_INCREASE)
    return actions


def action_target_cw(current_cw, action):
    cw = int(round(float(current_cw)))
    if cw not in CW_VALUES:
        raise ValueError(f"Invalid CW for action selection: {cw}")
    if action not in (ACTION_DECREASE, ACTION_KEEP, ACTION_INCREASE):
        raise ValueError(f"Invalid action: {action}")
    index = CW_VALUES.index(cw)
    if action == ACTION_DECREASE:
        return CW_VALUES[max(0, index - 1)]
    if action == ACTION_INCREASE:
        return CW_VALUES[min(len(CW_VALUES) - 1, index + 1)]
    return cw


def greedy_action(q_values, current_cw):
    """Deterministic evaluation policy; prefer keep when Q-values are tied."""
    allowed = allowed_actions(current_cw)
    best_value = max(float(q_values[action]) for action in allowed)
    best_actions = [
        action
        for action in allowed
        if math.isclose(float(q_values[action]), best_value, rel_tol=1e-7, abs_tol=1e-9)
    ]
    if ACTION_KEEP in best_actions:
        return ACTION_KEEP
    return min(best_actions)


def load_checkpoint(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Compatible Q-table not found: {path}. Train with rl/agent.py first."
        )
    with open(path, encoding="utf-8") as model_file:
        payload = json.load(model_file)
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid checkpoint root in {path}: expected an object")

    format_version = payload.get("format_version")
    state_schema = payload.get("state_schema")
    compatible_versions = {
        (CHECKPOINT_VERSION_V2, STATE_SCHEMA_V2),
        (CHECKPOINT_VERSION, STATE_SCHEMA),
    }
    if (format_version, state_schema) not in compatible_versions:
        raise ValueError(
            f"Incompatible checkpoint {path}: format/schema="
            f"{format_version!r}/{state_schema!r}. "
            "Select a supported v2 or v3 checkpoint."
        )
    if payload.get("action_schema") != ACTION_SCHEMA:
        raise ValueError(
            f"Incompatible checkpoint {path}: action_schema="
            f"{payload.get('action_schema')!r}; expected {ACTION_SCHEMA!r}"
        )

    q_table = {}
    entries = payload.get("q_table")
    if not isinstance(entries, list):
        raise ValueError(f"Invalid Q-table payload in {path}: q_table must be a list")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"Invalid Q-table entry in {path}")
        state = entry.get("state")
        values = entry.get("values")
        if (
            not isinstance(state, list)
            or len(state) != 8
            or not all(isinstance(value, int) for value in state)
            or not isinstance(values, list)
            or len(values) != 3
        ):
            raise ValueError(f"Invalid state/action shape in checkpoint {path}")
        if (
            not 0 <= state[0] <= (10 if state_schema == STATE_SCHEMA_V2 else 7)
            or not 0 <= state[1] <= (10 if state_schema == STATE_SCHEMA_V2 else 7)
            or not -(5 if state_schema == STATE_SCHEMA_V2 else 4)
            <= state[2]
            <= (5 if state_schema == STATE_SCHEMA_V2 else 4)
            or not -(5 if state_schema == STATE_SCHEMA_V2 else 4)
            <= state[3]
            <= (5 if state_schema == STATE_SCHEMA_V2 else 4)
            or not 0 <= state[4] <= 4
            or not 0 <= state[5] <= 4
            or not 0 <= state[6] <= 7
            or state[7] not in CW_VALUES
        ):
            raise ValueError(f"State is outside the v2 schema in {path}: {state}")
        q_values = np.asarray(values, dtype=np.float64)
        if not np.all(np.isfinite(q_values)):
            raise ValueError(f"Non-finite Q-values in checkpoint {path}")
        key = tuple(state)
        if key in q_table:
            raise ValueError(f"Duplicate state in checkpoint {path}: {key}")
        q_table[key] = q_values
    if not q_table:
        raise ValueError(f"Checkpoint contains an empty Q-table: {path}")
    return payload, q_table


def save_checkpoint(path, q_table, metadata):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    state_schema = metadata.get("state_schema", STATE_SCHEMA)
    if state_schema not in (STATE_SCHEMA_V2, STATE_SCHEMA):
        raise ValueError(f"Unsupported checkpoint state schema: {state_schema}")
    payload = {
        "format_version": (
            CHECKPOINT_VERSION_V2
            if state_schema == STATE_SCHEMA_V2
            else CHECKPOINT_VERSION
        ),
        "state_schema": state_schema,
        "action_schema": ACTION_SCHEMA,
        **metadata,
        "q_table": [
            {"state": list(state), "values": [float(value) for value in values]}
            for state, values in sorted(q_table.items())
        ],
    }
    directory = os.path.dirname(os.path.abspath(path))
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".q-table-",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            json.dump(payload, temp_file, separators=(",", ":"), allow_nan=False)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
    except OSError:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        raise

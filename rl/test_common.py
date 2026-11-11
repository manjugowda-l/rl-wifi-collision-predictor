import tempfile
import unittest
from pathlib import Path

from common import (
    ACTION_DECREASE,
    ACTION_INCREASE,
    ACTION_KEEP,
    ACTION_SCHEMA,
    STATE_SCHEMA,
    STATE_SCHEMA_V2,
    action_target_cw,
    allowed_actions,
    discretize_for_schema,
    discretize_state,
    discretize_state_v2,
    load_checkpoint,
    save_checkpoint,
)


class StateAndActionTests(unittest.TestCase):
    def test_v3_state_distinguishes_small_and_saturated_queues(self):
        small = discretize_state([10, 0, 5, 0, 0, 0, 15, 1])
        large = discretize_state([1000, 0, 500, 0, 0, 0, 15, 1])
        self.assertNotEqual(small[0], large[0])
        self.assertNotEqual(small[2], large[2])
        self.assertGreater(large[0], small[0])
        self.assertGreater(large[2], small[2])

    def test_v2_encoder_preserves_original_schema_for_existing_checkpoint(self):
        observation = [1000, 1000, 50, -50, 0.02, 12, 31, 300]
        self.assertEqual(
            discretize_state_v2(observation),
            (10, 10, 5, -5, 2, 4, 6, 31),
        )
        self.assertEqual(
            discretize_for_schema(observation, STATE_SCHEMA_V2),
            discretize_state_v2(observation),
        )

    def test_queue_growth_bins_keep_sign_and_magnitude(self):
        low_growth = discretize_state([0, 0, 2, -2, 0, 0, 15, -1])
        high_growth = discretize_state([0, 0, 80, -80, 0, 0, 15, -1])
        self.assertEqual(low_growth[2:4], (1, -1))
        self.assertEqual(high_growth[2:4], (4, -4))

    def test_action_mask_and_targets_match_cw_ladder(self):
        self.assertEqual(allowed_actions(7), [ACTION_KEEP, ACTION_INCREASE])
        self.assertEqual(allowed_actions(31), [ACTION_KEEP, ACTION_DECREASE, ACTION_INCREASE])
        self.assertEqual(allowed_actions(127), [ACTION_KEEP, ACTION_DECREASE])
        self.assertEqual(action_target_cw(15, ACTION_DECREASE), 7)
        self.assertEqual(action_target_cw(15, ACTION_KEEP), 15)
        self.assertEqual(action_target_cw(15, ACTION_INCREASE), 31)
        self.assertEqual(action_target_cw(7, ACTION_DECREASE), 7)
        self.assertEqual(action_target_cw(127, ACTION_INCREASE), 127)

    def test_checkpoint_versions_round_trip_without_schema_confusion(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for version, schema in ((2, STATE_SCHEMA_V2), (3, STATE_SCHEMA)):
                path = Path(temp_dir) / f"q_table_v{version}.json"
                state = (0, 0, 0, 0, 0, 0, 7, 15)
                table = {state: [0.1, 0.2, 0.3]}
                save_checkpoint(
                    str(path),
                    table,
                    {"state_schema": schema, "test_version": version},
                )
                metadata, loaded = load_checkpoint(str(path))
                self.assertEqual(metadata["format_version"], version)
                self.assertEqual(metadata["state_schema"], schema)
                self.assertEqual(loaded[state].tolist(), table[state])


if __name__ == "__main__":
    unittest.main()

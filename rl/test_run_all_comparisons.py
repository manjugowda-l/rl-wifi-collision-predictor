import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from run_all_comparisons import (
    FIELDS,
    calculate_throughput_mbps,
    extract_workload_signature,
    parse_simulation_output,
    validate_rl_control_output,
    validate_result_rows,
    write_results,
    write_mean_summary,
)


def simulation_log(scenario, run, tx=100, rx=90, loss=10, latency=2.5):
    goodput = rx * 1200 * 8 / (59 * 1_000_000)
    return f"""
Scenario                    : {scenario}
Random run                  : {run}
Total TX packets            : {tx}
Total RX packets            : {rx}
Lost packets                : {loss}
Packet loss                 : {100 * loss / tx} %
Average latency             : {latency} ms
FLOW1_THROUGHPUT_MBPS: {goodput * 0.4}
FLOW2_THROUGHPUT_MBPS: {goodput * 0.6}
"""


class ComparisonRunnerTests(unittest.TestCase):
    def test_throughput_uses_payload_and_fixed_measurement_window(self):
        expected = 100 * 1200 * 8 / (59 * 1_000_000)
        self.assertAlmostEqual(
            calculate_throughput_mbps(100, 1200, 59),
            expected,
        )

    def test_loss_is_derived_from_tx_minus_rx(self):
        result = parse_simulation_output(
            simulation_log(2, 1),
            2,
            "EDCA",
            1,
            12345,
        )
        self.assertEqual(result["lost_packets"], 10)
        self.assertEqual(result["packet_loss_percent"], 10.0)

    def test_latency_is_unavailable_without_successful_receives(self):
        result = parse_simulation_output(
            simulation_log(1, 2, tx=10, rx=0, loss=10, latency=float("nan")),
            1,
            "DCF",
            2,
            12345,
        )
        self.assertIsNone(result["average_latency_ms"])

    def test_edca_scenario_boundary_and_run_identity(self):
        log = simulation_log(40, 7)
        result = parse_simulation_output(log, 40, "EDCA", 7, 555)
        self.assertEqual((result["scenario"], result["run"]), (40, 7))
        with self.assertRaisesRegex(ValueError, "identity"):
            parse_simulation_output(log, 39, "EDCA", 7, 555)

    def test_workload_signature_includes_optional_scenario_burst(self):
        output = """
STA A: 10 MB, 40Mbps, 1200 B packets, 8334 packets, start 1 s
STA B: 10 MB, 40Mbps, 1200 B packets, 8334 packets, start 1 s
STA B second burst: 10 MB, 10Mbps, 1200 B packets, start 6 s
"""
        signature = dict(extract_workload_signature(output))
        self.assertIn("STA B second burst", signature)
        self.assertTrue(signature["STA B"].startswith("10 MB, 40Mbps"))

    def test_rl_control_and_reward_traces_validate_beacon_persistence(self):
        output = """
[CW-VERIFY] t=1 | selected=15 | AP=15/127 | advertisedBE=15/127 | STA_A=15/127 | STA_B=15/127
[RL-STATE] t=1 s | Reward=0.280000 | RewardComponents(throughput/loss/latency/queue/growth/retry)=0.9/0.1/0.2/0.1/0.1/0.1
[RL-ACTION] action=0 | requestedCW=7 | APmin/max=7/127 | advertisedBEmin/max=7/127 | STA_Amin/max=7/127 | STA_Bmin/max=7/127 | activeSTA_A_CW=7 | activeSTA_B_CW=15
[POLICY] step=1 state=(0, 0, 0, 0, 0, 0, 1, 15) action=0 requestedCW=7 effectiveCW=7
[CW-STA-RESYNC] t=1.05 | selected=7 | advertisedBE=7/127 | STA_A=15/127 | STA_B=15/127
[CW-VERIFY] t=1.1 | selected=7 | AP=7/127 | advertisedBE=7/127 | STA_A=7/127 | STA_B=7/127
[RL-STATE] t=1.1 s | Reward=0.280000 | RewardComponents(throughput/loss/latency/queue/growth/retry)=0.9/0.1/0.2/0.1/0.1/0.1
[RL-ACTION] action=1 | requestedCW=7 | APmin/max=7/127 | advertisedBEmin/max=7/127 | STA_Amin/max=7/127 | STA_Bmin/max=7/127 | activeSTA_A_CW=7 | activeSTA_B_CW=7
[POLICY] step=2 state=(0, 0, 0, 0, 0, 0, 1, 7) action=1 requestedCW=7 effectiveCW=7
"""
        validate_rl_control_output(output)

    def test_rl_control_trace_rejects_station_reset(self):
        output = """
[CW-VERIFY] t=1 | selected=15 | AP=15/127 | advertisedBE=15/127 | STA_A=15/127 | STA_B=15/127
[CW-VERIFY] t=1.1 | selected=15 | AP=15/127 | advertisedBE=15/127 | STA_A=15/1023 | STA_B=15/1023
"""
        with self.assertRaisesRegex(ValueError, "CW mismatch"):
            validate_rl_control_output(output)

    def test_packet_accounting_mismatch_fails(self):
        with self.assertRaisesRegex(ValueError, "TX-RX"):
            parse_simulation_output(
                simulation_log(3, 1, tx=100, rx=90, loss=9),
                3,
                "DCF",
                1,
                12345,
            )

    def test_duplicate_scenario_method_run_fails(self):
        row = parse_simulation_output(
            simulation_log(1, 1),
            1,
            "DCF",
            1,
            12345,
        )
        with TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "results.csv"
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                write_results(path, [row, row])

    def test_final_rows_include_names_and_mean_summary_is_scenario_weighted(self):
        rows = []
        for method in ("DCF", "EDCA", "RL Adaptive DCF"):
            rows.append({
                "scenario_id": 1,
                "scenario_name": "scenario_01",
                "method": method,
                "run": 1,
                "seed": 12345,
                "transmitted_packets": 100,
                "received_packets": 90,
                "lost_packets": 10,
                "packet_loss_percent": 10.0,
                "average_latency_ms": 2.5,
                "flow1_throughput_mbps": 0.01,
                "flow2_throughput_mbps": 0.02,
            })
        self.assertEqual(FIELDS[0:3], ["scenario_id", "scenario_name", "method"])
        validate_result_rows(rows, [1], 1)
        with TemporaryDirectory() as temporary_dir:
            path = Path(temporary_dir) / "mean.csv"
            summary = write_mean_summary(path, rows, [1], 1)
            self.assertEqual(len(summary), 3)
            self.assertEqual(summary[0]["completed_scenarios"], 1)
            self.assertEqual(summary[0]["completed_runs"], 1)

    def test_final_row_validation_rejects_missing_method(self):
        row = parse_simulation_output(
            simulation_log(1, 1),
            1,
            "DCF",
            1,
            12345,
        )
        row.update({
            "scenario_id": 1,
            "scenario_name": "scenario_01",
        })
        del row["scenario"]
        with self.assertRaisesRegex(ValueError, "missing"):
            validate_result_rows([row], [1], 1)


if __name__ == "__main__":
    unittest.main()

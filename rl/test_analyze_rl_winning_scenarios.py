import csv
import tempfile
import unittest
from pathlib import Path

from analyze_rl_winning_scenarios import (
    METHODS,
    OUTPUT_FIELDS,
    TOLERANCES,
    _validate_scenario_rows,
    qualifies,
    selected_summary,
    write_report,
    _write_csv,
    SUMMARY_FIELDS,
)


CONFIG = {"run": 1, "seed": 12345}


def method_row(method, goodput=2.0, loss=1.0, latency=10.0):
    transmitted = 1000
    lost = round(loss * transmitted / 100.0)
    return {
        "scenario_id": "1",
        "scenario_name": "scenario_01",
        "method": method,
        "run": "1",
        "seed": "12345",
        "transmitted_packets": str(transmitted),
        "received_packets": str(transmitted - lost),
        "lost_packets": str(lost),
        "packet_loss_percent": str(100.0 * lost / transmitted),
        "average_latency_ms": str(latency),
        "flow1_throughput_mbps": str(goodput / 2),
        "flow2_throughput_mbps": str(goodput / 2),
    }


def scenario_rows(rl=None, dcf=None, edca=None):
    values = {
        "DCF": dcf or {},
        "EDCA": edca or {},
        "RL Adaptive DCF": rl or {},
    }
    rows = []
    for method in METHODS:
        overrides = values[method]
        defaults = {
            "goodput": 2.0,
            "loss": 1.0,
            "latency": 10.0,
        }
        defaults.update(overrides)
        row = method_row(
            method,
            defaults["goodput"],
            defaults["loss"],
            defaults["latency"],
        )
        row["packet_loss_percent"] = str(defaults["loss"])
        rows.append(row)
    return rows


def validated(rows):
    by_method, reasons = _validate_scenario_rows(1, rows, CONFIG)
    if reasons:
        return None, reasons
    return by_method, []


class WinningScenarioAnalysisTests(unittest.TestCase):
    def test_rl_must_beat_both_baselines_on_all_metrics(self):
        rows = scenario_rows(
            rl={"goodput": 2.2, "loss": 0.7, "latency": 8.0},
            dcf={"goodput": 2.0, "loss": 1.0, "latency": 10.0},
            edca={"goodput": 2.1, "loss": 0.9, "latency": 9.0},
        )
        methods, reasons = validated(rows)
        self.assertFalse(reasons)
        self.assertTrue(qualifies(methods))

    def test_beating_only_one_baseline_does_not_qualify(self):
        rows = scenario_rows(
            rl={"goodput": 2.2, "loss": 0.7, "latency": 8.0},
            dcf={"goodput": 2.0, "loss": 1.0, "latency": 10.0},
            edca={"goodput": 2.3, "loss": 0.6, "latency": 7.0},
        )
        methods, reasons = validated(rows)
        self.assertFalse(reasons)
        self.assertFalse(qualifies(methods))

    def test_winning_two_metrics_but_losing_one_does_not_qualify(self):
        rows = scenario_rows(
            rl={"goodput": 2.2, "loss": 0.7, "latency": 11.0},
            dcf={"goodput": 2.0, "loss": 1.0, "latency": 10.0},
            edca={"goodput": 2.1, "loss": 0.9, "latency": 10.5},
        )
        methods, reasons = validated(rows)
        self.assertFalse(reasons)
        self.assertFalse(qualifies(methods))

    def test_equal_and_within_tolerance_values_are_not_wins(self):
        epsilon = TOLERANCES["aggregate_goodput_mbps"] / 2
        rows = scenario_rows(
            rl={"goodput": 2.0 + epsilon, "loss": 0.7, "latency": 8.0},
            dcf={"goodput": 2.0, "loss": 1.0, "latency": 10.0},
            edca={"goodput": 2.0, "loss": 0.9, "latency": 9.0},
        )
        methods, reasons = validated(rows)
        self.assertFalse(reasons)
        self.assertFalse(qualifies(methods))
        rows = scenario_rows(
            rl={"goodput": 2.2, "loss": 0.7, "latency": 9.0},
            dcf={"goodput": 2.0, "loss": 1.0, "latency": 10.0},
            edca={"goodput": 2.1, "loss": 0.9, "latency": 9.0},
        )
        methods, reasons = validated(rows)
        self.assertFalse(reasons)
        self.assertFalse(qualifies(methods))

    def test_missing_method_and_duplicate_rows_are_invalid(self):
        rows = scenario_rows()
        methods, reasons = validated(rows[:2])
        self.assertIsNone(methods)
        self.assertIn("missing RL Adaptive DCF result", reasons)
        methods, reasons = validated(rows + [rows[0]])
        self.assertIsNone(methods)
        self.assertIn("duplicate DCF rows (2)", reasons)

    def test_invalid_packet_accounting_is_invalid(self):
        rows = scenario_rows()
        rows[0]["lost_packets"] = "2"
        methods, reasons = validated(rows)
        self.assertIsNone(methods)
        self.assertTrue(any("TX-RX" in reason for reason in reasons))

    def test_no_qualifying_scenarios_write_headers_and_zero_means(self):
        summary = selected_summary({})
        self.assertEqual(len(summary), 3)
        self.assertTrue(all(row["qualifying_scenarios"] == 0 for row in summary))
        self.assertTrue(all(row["completed_runs"] == 0 for row in summary))
        self.assertTrue(
            all(row["mean_aggregate_goodput_mbps"] is None for row in summary)
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            comparison_path = output / "comparison.csv"
            _write_csv(comparison_path, OUTPUT_FIELDS, [])
            with comparison_path.open(newline="") as source:
                reader = csv.reader(source)
                self.assertEqual(next(reader), list(OUTPUT_FIELDS))
                self.assertEqual(list(reader), [])
            summary_path = output / "means.csv"
            _write_csv(summary_path, SUMMARY_FIELDS, summary)
            with summary_path.open(newline="") as source:
                written = list(csv.DictReader(source))
            self.assertEqual(len(written), 3)
            self.assertEqual(written[0]["qualifying_scenarios"], "0")
            self.assertEqual(written[0]["mean_aggregate_goodput_mbps"], "")
            report_path = output / "report.md"
            failed = {scenario: ["all strict win criteria failed"] for scenario in range(1, 41)}
            write_report(report_path, {}, {}, failed, summary)
            report = report_path.read_text()
            self.assertIn("No scenarios qualified", report)
            self.assertIn("Valid but non-qualifying result", report)


if __name__ == "__main__":
    unittest.main()

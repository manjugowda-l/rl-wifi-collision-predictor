import csv
import tempfile
import unittest
from pathlib import Path

from finalize_five_scenario_comparison import (
    INPUT_FIELDS,
    METHODS,
    SCENARIO_CONFIGS,
    generate,
    validate_rows,
)


def sample_rows():
    rows = []
    for scenario in range(1, 6):
        for method_index, method in enumerate(METHODS):
            tx = 100 + scenario
            rx = tx - method_index
            rows.append({
                "scenario_id": scenario,
                "scenario_name": f"scenario_{scenario:02d}",
                "method": method,
                "run": 1,
                "seed": 12345,
                "transmitted_packets": tx,
                "received_packets": rx,
                "lost_packets": method_index,
                "packet_loss_percent": 100 * method_index / tx,
                "average_latency_ms": 1 + scenario + method_index,
                "flow1_throughput_mbps": scenario + method_index,
                "flow2_throughput_mbps": scenario * 2 + method_index,
            })
    return rows


def write_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=INPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


class FinalizeFiveScenarioComparisonTests(unittest.TestCase):
    def test_validates_all_fifteen_matched_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input.csv"
            write_rows(path, sample_rows())

            rows = validate_rows(path)

            self.assertEqual(len(rows), 15)
            self.assertEqual(
                [(row["scenario_id"], row["method"]) for row in rows[:3]],
                [(1, method) for method in METHODS],
            )
            self.assertAlmostEqual(
                rows[0]["aggregate_throughput_mbps"],
                rows[0]["flow1_throughput_mbps"]
                + rows[0]["flow2_throughput_mbps"],
            )

    def test_selected_workloads_match_requested_mappings(self):
        self.assertEqual(SCENARIO_CONFIGS[1]["source_scenario_id"], 5)
        self.assertEqual(SCENARIO_CONFIGS[1]["extra_flow2"], (10_000_000, "10Mbps", 6.0))
        self.assertEqual(SCENARIO_CONFIGS[2]["source_scenario_id"], 18)
        self.assertEqual(SCENARIO_CONFIGS[2]["flow1"], (40_000_000, "40Mbps", 1.0))
        self.assertEqual(SCENARIO_CONFIGS[2]["flow2"], (20_000_000, "20Mbps", 1.0))
        self.assertEqual(SCENARIO_CONFIGS[3]["source_scenario_id"], 24)
        self.assertEqual(SCENARIO_CONFIGS[3]["flow2"], (5_000_000, "5Mbps", 5.0))
        self.assertEqual(SCENARIO_CONFIGS[4]["flow1"], (15_000_000, "15Mbps", 1.0))
        self.assertEqual(SCENARIO_CONFIGS[4]["flow2"], (10_000_000, "10Mbps", 1.0))
        self.assertEqual(SCENARIO_CONFIGS[5]["flow1"], (5_000_000, "20Mbps", 1.0))
        self.assertEqual(SCENARIO_CONFIGS[5]["flow2"], (5_000_000, "20Mbps", 1.0))

    def test_rejects_missing_or_duplicate_method_results(self):
        for mutate in (
            lambda rows: rows.pop(),
            lambda rows: rows.append(dict(rows[0])),
        ):
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "input.csv"
                rows = sample_rows()
                mutate(rows)
                write_rows(path, rows)

                with self.assertRaises(ValueError):
                    validate_rows(path)

    def test_rejects_mismatched_run_seed_and_packet_accounting(self):
        mutations = (
            lambda row: row.update(run=2),
            lambda row: row.update(seed=7),
            lambda row: row.update(lost_packets=3),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "input.csv"
                rows = sample_rows()
                mutate(rows[0])
                write_rows(path, rows)

                with self.assertRaises(ValueError):
                    validate_rows(path)

    def test_generates_tables_and_charts_from_identical_scenario_set(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            input_path = root / "input.csv"
            output_dir = root / "output"
            write_rows(input_path, sample_rows())

            rows, means = generate(input_path, output_dir, "q_table_v2.json")

            self.assertEqual(len(rows), 15)
            self.assertEqual([row["scenario_count"] for row in means], [5, 5, 5])
            self.assertEqual([row["completed_runs"] for row in means], [5, 5, 5])
            with (output_dir / "five_scenario_comparison.csv").open(
                newline="", encoding="utf-8"
            ) as source:
                self.assertEqual(len(list(csv.DictReader(source))), 15)
            self.assertEqual(
                len(list(output_dir.glob("five_scenario_*.svg"))), 6
            )
            self.assertTrue(
                (output_dir / "commands_and_validation.md").is_file()
            )


if __name__ == "__main__":
    unittest.main()

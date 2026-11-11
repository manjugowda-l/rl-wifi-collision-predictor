# Commands and validation

From the ns-3 repository root:

## Build

```bash
./ns3 build wifi-baseline wifi-edca wifi-ai-dcf
```

## Run exactly five scenarios

```bash
PYTHONPATH=contrib/ai/model/gym-interface/py:contrib/ai/python_utils ./.venv/bin/python rl/run_all_comparisons.py --scenarios 1,2,3,4,5 --run 1 --seed 12345 --checkpoint rl/q_table_v2.json --output-dir rl/results/five_scenario_final_20261027
```

## Generate the report, CSVs, and charts

```bash
'/mnt/c/Users/MANJU L/Downloads/ns-allinone-3.46.1/ns-3.46.1/.venv/bin/python' rl/finalize_five_scenario_comparison.py --input rl/results/five_scenario_final_20261027/final_40_scenario_comparison.csv --output-dir rl/results/five_scenario_final_20261027 --checkpoint rl/q_table_v2.json --runner-command 'PYTHONPATH=contrib/ai/model/gym-interface/py:contrib/ai/python_utils ./.venv/bin/python rl/run_all_comparisons.py --scenarios 1,2,3,4,5 --run 1 --seed 12345 --checkpoint rl/q_table_v2.json --output-dir rl/results/five_scenario_final_20261027' --logs-dir rl/results/five_scenario_final_20261027/logs
```

## Run the focused/full RL test suite

```bash
./.venv/bin/python -m unittest discover -s rl -p 'test_*.py'
```

## Validate rows, scenario mappings, checkpoint, and historical hashes

```bash
./.venv/bin/python rl/validate_five_scenario_final.py --results-dir rl/results/five_scenario_final_20261027 --checkpoint rl/q_table_v2.json
```

## Validation

Validation: exactly 15 rows (five scenarios x three methods); one row per scenario/method; same run and seed across all scenarios; packet counts and loss percentages consistent; all numeric metrics finite; aggregate throughput computed as Flow 1 + Flow 2; means computed over the same five scenarios for every method; measured run logs agree with all workload configurations and scenario/run identities.


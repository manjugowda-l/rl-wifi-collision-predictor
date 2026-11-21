# Final RL Training Record

## Selected checkpoint

- **Checkpoint:** [`q_table_v2.json`](./q_table_v2.json)
- **Full path:** `C:\Users\MANJU L\Downloads\ns-allinone-3.46.1\ns-3.46.1\rl\q_table_v2.json`
- **SHA-256:** `c05335b5ea7d37ab2507da28b0f1190a4360c847ec6e54442d4ab8e0eba6eb25`
- **Filesystem creation time:** 2026-10-25 18:52:44 local (UTC+05:30)
- **Last modified:** 2026-10-25 13:22:45 UTC
- **Training data:** [`data/training_20261025T082304Z/`](./data/training_20261025T082304Z/)
- **Training entry point:** [`agent.py`](./agent.py), in its historical v2 form

The checkpoint metadata records format version 2, the
`queue-growth-loss-mac-latency-cw-v2` state schema, scenarios 1-40 completed,
`next_scenario=41`, 23,600 transitions, and 734 Q-table states. The training
history has one complete 590-step episode for each of the 40 scenarios. Its CSV
also contains five partial retry episodes (four for scenario 5 and one for
scenario 37), adding 395 logged steps; those do not appear in the checkpoint's
23,600 committed transitions. Thus the combined CSV has 23,995 rows without
indicating additional completed training.

The v2 checkpoint and historical `rl/agent.py` source are both present in
repository commit `7976dc8`. The checkpoint does not contain a source revision,
source hash, or complete training configuration, so the exact script revision
and reward configuration cannot be established from the checkpoint alone.
The current `agent.py` has since been extended for v3 training; **do not run it
to retrain** as part of evaluation.

## Why v2 is the final completed checkpoint

The newer `q_table_v3.json` was not complete: its metadata records only
scenarios 1-19 completed, `next_scenario=20`, 11,210 transitions, and 657
states. Its scenario 20 training CSV has only 79 steps. Its newer timestamp
therefore does not make it the final checkpoint.

The current checkpoint loader in [`common.py`](./common.py) supports the v2
schema, and [`run_all_comparisons.py`](./run_all_comparisons.py) defaults to
`q_table_v2.json`. The preserved result manifests also record the selected
checkpoint SHA-256 above.

## Completion and preserved evaluation evidence

- Historical 40-scenario comparison:
  - [`results/final_40_scenario_comparison.csv`](./results/final_40_scenario_comparison.csv): 120 rows.
  - [`results/final_40_scenario_mean_summary.csv`](./results/final_40_scenario_mean_summary.csv): 3 method rows.
  - [`results/final_40_scenario_report.md`](./results/final_40_scenario_report.md).
  - Its manifest records `complete=true`, 120 completed rows, run 1, seed 12345, and the selected checkpoint hash.
- Final five-scenario comparison:
  - [`results/five_scenario_final_20261027/final_40_scenario_comparison.csv`](./results/five_scenario_final_20261027/final_40_scenario_comparison.csv): 15 rows.
  - [`results/five_scenario_final_20261027/five_scenario_comparison.csv`](./results/five_scenario_final_20261027/five_scenario_comparison.csv): 15 rows.
  - [`results/five_scenario_final_20261027/five_scenario_report.md`](./results/five_scenario_final_20261027/five_scenario_report.md) and its charts.
  - Its manifest records `complete=true`, 15 completed rows, scenarios 1-5, run 1, seed 12345, and the selected checkpoint hash.

The current workload table maps IDs 1-3 to historical scenarios 5, 18, and 24,
and IDs 4-5 to new workloads. The preserved five-scenario comparison uses
these IDs. The historical 40-scenario report predates that remapping; a fresh
`--scenarios all` run uses the current table and will not reproduce those
historical rows. Both result sets remain preserved and must not be overwritten.

## Cleanup performed

After approval, the 22 incomplete v3 checkpoint/history files listed below
were archived and hash-verified before deletion. No source code, original
training data, v2 training data, legacy pickle, completed comparison output, or
empty directories were deleted.

Backup archive: [`cleanup_backup_v3_20261111.zip`](./cleanup_backup_v3_20261111.zip)

- Archive size: 850,322 bytes
- Archive SHA-256: `8cc82708d7095ec9a92f7c3f1480ff9793f61bbad53446ba9454b2cb2a8e91db`
- Contents: 22 files; every archived file's SHA-256 was checked against its original before deletion.

Files removed from the working tree:

- `rl/q_table_v3.json`
- `rl/data/training_v3/training_20261026T134652Z/all_training_data.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario01_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario02_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario03_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario04_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario05_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario06_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario07_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario08_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario09_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario10_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario11_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario12_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario13_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario14_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario15_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario16_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario17_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario18_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario19_training.csv`
- `rl/data/training_v3/training_20261026T134652Z/scenario20_training.csv`

## Reproduction commands

Run these commands in **WSL Bash** from the ns-3 repository root, with the
repository virtualenv and ns3-ai Gym bindings installed. The output directories
and simulator result CSV below receive UTC timestamp suffixes to avoid
overwriting preserved results.

### Build DCF, EDCA, and RL Adaptive DCF

```bash
./ns3 build wifi-baseline wifi-edca wifi-ai-dcf
```

### Evaluate RL Adaptive DCF with the selected checkpoint

`evaluate.py` evaluates scenarios 1-40, defaults to run 1 and seed 12345, and
creates a timestamped evaluation directory containing `raw_results.csv` and
`summary.csv`.

```bash
EVAL_CSV="rl/data/evaluation_rl_v2_$(date -u +%Y%m%dT%H%M%SZ).csv"
PYTHONPATH="contrib/ai/model/gym-interface/py:contrib/ai/python_utils${PYTHONPATH:+:$PYTHONPATH}" \
WIFI_RL_EVAL_MODEL_FILE="rl/q_table_v2.json" \
WIFI_RL_RESULTS_FILE="$EVAL_CSV" \
./.venv/bin/python rl/evaluate.py
```

### Run the current 40-ID DCF/EDCA/RL comparison

This uses the current scenario mapping and a fresh output directory. It does
not replace the preserved historical 40-scenario result files.

```bash
OUT40="rl/results/current_40_scenario_$(date -u +%Y%m%dT%H%M%SZ)"
PYTHONPATH="contrib/ai/model/gym-interface/py:contrib/ai/python_utils${PYTHONPATH:+:$PYTHONPATH}" \
./.venv/bin/python rl/run_all_comparisons.py \
  --scenarios all --run 1 --seed 12345 \
  --checkpoint rl/q_table_v2.json --output-dir "$OUT40"
```

### Run and report the current five-scenario DCF/EDCA/RL comparison

```bash
OUT5="rl/results/five_scenario_reproduction_$(date -u +%Y%m%dT%H%M%SZ)"
PYTHONPATH="contrib/ai/model/gym-interface/py:contrib/ai/python_utils${PYTHONPATH:+:$PYTHONPATH}" \
./.venv/bin/python rl/run_all_comparisons.py \
  --scenarios 1,2,3,4,5 --run 1 --seed 12345 \
  --checkpoint rl/q_table_v2.json --output-dir "$OUT5"

./.venv/bin/python rl/finalize_five_scenario_comparison.py \
  --input "$OUT5/final_40_scenario_comparison.csv" \
  --output-dir "$OUT5" \
  --checkpoint rl/q_table_v2.json \
  --logs-dir "$OUT5/logs"
```

### View generated CSV and report files

Run these in the same shell after defining `OUT40` or `OUT5` above:

```bash
cat "$OUT40/final_40_scenario_comparison.csv"
cat "$OUT40/final_40_scenario_report.md"
cat "$OUT5/five_scenario_comparison.csv"
cat "$OUT5/five_scenario_report.md"
```

## Verification status

The existing `common.load_checkpoint` function successfully loaded the selected
checkpoint in an isolated temporary Python 3.13 environment with NumPy 2.5.4:
it reported the v2 schema, 40 completed scenarios, and 734 states. The
temporary environment was removed after the check. The checkpoint and archived
result files were also checked using their metadata, SHA-256 fingerprints, and
CSV row counts.

The full simulator evaluation and build were not run: the repository WSL
virtualenv lacks NumPy and pip, and the native ns-3 wrapper reports that CMake
is not on PATH. The five-scenario validator also could not run natively because
its manifest records a WSL `/mnt/c/...` checkpoint path while native Windows
path resolution differs; its checkpoint hash and the result manifest/row
counts were checked independently. No training or simulation was run, and the
selected checkpoint's contents remain unchanged.

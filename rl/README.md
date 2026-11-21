# Wi-Fi DCF comparison experiment

With the repository virtualenv and ns3-ai Gym bindings installed, run a fresh
40-scenario comparison from the repository root. Use a new output directory so
the preserved historical results are not reused or overwritten:

```sh
OUT_DIR="rl/results/current_40_scenario_$(date -u +%Y%m%dT%H%M%SZ)"
PYTHONPATH="contrib/ai/model/gym-interface/py:contrib/ai/python_utils${PYTHONPATH:+:$PYTHONPATH}" \
  ./.venv/bin/python rl/run_all_comparisons.py --scenarios all --run 1 \
  --seed 12345 --checkpoint rl/q_table_v2.json --output-dir "$OUT_DIR"
```

See [the ns3-ai installation guide](../contrib/ai/docs/install.md) for setting
up the Gym bindings and Python dependencies. The bundled `ns3ai_utils` also
imports `psutil`; install it in the active Python environment if it is missing:

```sh
python3 -m pip install psutil
```

The runner uses the completed, preserved `q_table_v2.json` for greedy RL
evaluation. It never trains or writes to a checkpoint. It checks the three
simulator executables for `--seed` support and builds the required targets only
if an executable is missing or stale. The final files are written to the
selected output directory:

- `final_40_scenario_comparison.csv`: 120 rows, one per scenario and method.
- `final_40_scenario_mean_summary.csv`: unweighted arithmetic means across the
  same scenarios, with completed scenario/run counts.
- `final_40_scenario_report.md`: per-scenario metrics and Pareto direction
  counts for RL versus DCF and EDCA.

Per-simulation logs and raw RL CSVs are retained in `rl/results/logs/`.
`final_40_scenario_comparison.partial.csv` and its metadata manifest are used
for safe resumption. A partial file is not named as the final comparison; the
final CSV is published only after all runs and validations pass. On restart,
saved rows are reused only when their checkpoint/configuration metadata and
simulator logs agree. Use a different `--output-dir` for a different
scenario/run/seed/checkpoint configuration. The matching manifest prevents
mixing partial runs or treating an incomplete result as complete.

For a small smoke run, use a separate output directory, for example:

```sh
PYTHONPATH="contrib/ai/model/gym-interface/py:contrib/ai/python_utils${PYTHONPATH:+:$PYTHONPATH}" \
  ./.venv/bin/python rl/run_all_comparisons.py --scenarios 5 --run 1 \
  --output-dir /tmp/wifi-comparison-smoke
```

Use `--checkpoint` to select another compatible, existing checkpoint.

## Strict RL-winning subset

To generate a post-hoc subset from a completed comparison without rerunning
simulations or modifying the source results:

```sh
./.venv/bin/python rl/analyze_rl_winning_scenarios.py
```

The analyzer requires the completed comparison manifest and matching per-run
logs. A scenario is selected only when RL beats both DCF and EDCA in aggregate
goodput, packet-loss percentage, and average latency, with strict differences
larger than the stated input-precision tolerances. It writes
`rl_winning_scenarios_comparison.csv`,
`rl_winning_scenarios_mean_summary.csv`, and
`rl_winning_scenarios_report.md` under `rl/results/`. The report explicitly
labels the subset as post-hoc and lists valid non-qualifying and invalid
scenarios separately.

## Workload and randomness

`scratch/wifi-scenario-config.h` is the current common workload table. Current
scenario IDs 1-3 map to historical scenarios 5, 18, and 24; IDs 4-5 are new
workloads, and the remaining IDs use the table entries in that file. The
preserved historical 40-scenario comparison predates this remapping. A fresh
`--scenarios all` run uses the current table and is not a reproduction of those
historical rows. The final five-scenario comparison uses the current IDs 1-5.
The existing reference applications and EDCA packet-tagging application
schedule packets differently internally, but use the same offered bytes,
configured rates, packet sizes, destinations, and starts for each current ID.
All methods use two stations, one AP, 1200-byte application packets, the same
60-second simulation, seed, run number, PHY, and positions. The DCF/RL non-QoS
settings and EDCA QoS settings intentionally differ at the MAC layer.

The current 40 IDs cover the selected historical workloads, two new workloads,
offered-load levels, asymmetric station loads, and staggered starts; they are a
bounded diagnostic matrix, not an exhaustive representation of all Wi-Fi
deployments. The historical comparison outputs remain preserved as original
results.

For corresponding runs, ns-3 uses the requested seed and run number. EDCA
category assignment is reproducible from the seed, run, scenario, and station
index; it is not selected from system entropy. Different channel-access
behavior can still cause later packet events to diverge.

## Reported metrics

Packet loss is `(transmitted - received) / transmitted * 100`. Average latency
is FlowMonitor's accumulated end-to-end delay divided by received packets and
is unavailable when no packets arrive. Per-flow goodput is the delivered
1200-byte application payload times eight, divided by the common 59-second
measurement window (from 1 second through the 60-second simulation stop).
Flow 1 is station A and Flow 2 is station B; the additional B burst is in
current scenario 1.

Here TX and RX are FlowMonitor's packets transmitted and received through the
simulation stop. Therefore packets still in flight at stop are included in
`TX - RX` as not received; the reported loss is not a post-stop-confirmed
physical-loss count.

Each simulation's console output and raw per-run CSV (where the implementation
emits one) are retained in `rl/results/logs/`. The main CSV has one row per
scenario/method/run, while the separate mean CSV and Markdown report provide
aggregate and per-scenario summaries. The runner compares each method's printed
station workload configuration and stops if corresponding scenario workloads
differ.

## RL policy and reward note

Evaluation selects the state encoder from the checkpoint schema and supports
the v2 and v3 schemas. The selected checkpoint in this working tree is v2.
Evaluation uses the same three actions and CW boundary mask. It is greedy
(epsilon is not used), with ties preferring keep. Unseen states therefore keep
the current CW when all action values are zero. The comparison runner never
starts training.

Each RL action sets the AP's AC_BE contention window and its advertised AC_BE
CW limits, as well as both stations' effective AC_BE limits. The simulator
checks the AP and advertisement after each action. If an already-transmitted
beacon briefly reapplies its older CW at a decision boundary, the simulator
logs that condition and synchronizes the stations to the currently advertised
CW; an AP advertisement mismatch or an unresolved station mismatch is fatal.

New training uses the v3 state schema, which distinguishes queue regimes and
signed queue-growth magnitudes, and a versioned multi-objective reward:
`0.40 * throughput - 0.20 * cumulative FlowMonitor loss - 0.20 * latency -
0.10 * queue pressure - 0.05 * positive queue growth - 0.05 * MAC retry
failure ratio` (each component is normalized and clipped in the simulator).
The cumulative loss fraction avoids treating FlowMonitor's delayed loss
notifications as losses from the same interval's transmissions.

The selected `q_table_v2.json` remains unchanged and is evaluated with its
original v2 state encoder. Its action transitions predate the effective AP
advertisement fix, and the checkpoint does not establish that it was trained
with the current reward. The incomplete v3 experiment (scenarios 1-19
completed, scenario 20 partial) was removed from the working tree after backup
to `rl/cleanup_backup_v3_20261111.zip`; it is not the final checkpoint.

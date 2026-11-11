# Five-scenario DCF, EDCA, and RL comparison

This is a fresh evaluation of exactly five remapped workloads. It is not the historical 40-scenario result.

- Run: `1`; seed: `12345`; simulation: 60 s; measurement window: 59 s.
- RL checkpoint: `rl/q_table_v2.json`; retraining: none (completed v2 checkpoint reused).
- Each corresponding scenario uses the same traffic parameters, seed, and run in all three methods; only the MAC/access-control implementation differs.

## Workload mapping

| New ID | Source ID | Workload |
|---:|---:|---|
| 1 | 5 | Original scenario 5: simultaneous 10 MB, 40 Mbps flows; B burst at 6 s. |
| 2 | 18 | Original scenario 18: simultaneous asymmetric high load. |
| 3 | 24 | Original scenario 24: A-heavy load with delayed B. |
| 4 | 17 | Original scenario 17: symmetric 30 MB, 30 Mbps simultaneous stress load. |
| 5 | 23 | Original scenario 23: A starts at 1 s; B-heavy flow starts at 5 s. |

## Individual scenario comparisons

Aggregate throughput is the sum of the two measured flow-throughput values. Loss is the fraction of transmitted packets not received by simulation end.

### Scenario 1 (source scenario 5)

Original scenario 5: simultaneous 10 MB, 40 Mbps flows; B burst at 6 s.

| Method | Tx | Rx | Lost | Loss (%) | Avg latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DCF | 25002 | 24622 | 380 | 1.519878 | 291.789000 | 1.324310 | 2.681980 | 4.006290 |
| EDCA | 25002 | 24622 | 380 | 1.519878 | 291.791000 | 1.324310 | 2.681980 | 4.006290 |
| RL Adaptive DCF | 25002 | 24637 | 365 | 1.459883 | 273.765000 | 1.325290 | 2.683440 | 4.008730 |

### Scenario 2 (source scenario 18)

Original scenario 18: simultaneous asymmetric high load.

| Method | Tx | Rx | Lost | Loss (%) | Avg latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DCF | 50001 | 48365 | 1636 | 3.271935 | 392.200000 | 5.160410 | 2.709150 | 7.869560 |
| EDCA | 50001 | 48473 | 1528 | 3.055939 | 393.037000 | 5.177980 | 2.709150 | 7.887130 |
| RL Adaptive DCF | 50001 | 48614 | 1387 | 2.773945 | 261.317000 | 5.200920 | 2.709150 | 7.910070 |

### Scenario 3 (source scenario 24)

Original scenario 24: A-heavy load with delayed B.

| Method | Tx | Rx | Lost | Loss (%) | Avg latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DCF | 20834 | 20813 | 21 | 0.100797 | 0.288795 | 2.708990 | 0.677532 | 3.386522 |
| EDCA | 20834 | 20813 | 21 | 0.100797 | 0.290197 | 2.708990 | 0.677532 | 3.386522 |
| RL Adaptive DCF | 20834 | 20814 | 20 | 0.095997 | 0.270637 | 2.708990 | 0.677695 | 3.386685 |

### Scenario 4 (source scenario 17)

Original scenario 17: symmetric 30 MB, 30 Mbps simultaneous stress load.

| Method | Tx | Rx | Lost | Loss (%) | Avg latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DCF | 50000 | 47816 | 2184 | 4.368000 | 303.317000 | 3.897600 | 3.882630 | 7.780230 |
| EDCA | 50000 | 47816 | 2184 | 4.368000 | 303.302000 | 3.897600 | 3.882630 | 7.780230 |
| RL Adaptive DCF | 50000 | 47278 | 2722 | 5.444000 | 557.900000 | 3.833000 | 3.859690 | 7.692690 |

### Scenario 5 (source scenario 23)

Original scenario 23: A starts at 1 s; B-heavy flow starts at 5 s.

| Method | Tx | Rx | Lost | Loss (%) | Avg latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DCF | 20834 | 20814 | 20 | 0.095997 | 0.263166 | 0.677532 | 2.709150 | 3.386682 |
| EDCA | 20834 | 20814 | 20 | 0.095997 | 0.261876 | 0.677532 | 2.709150 | 3.386682 |
| RL Adaptive DCF | 20834 | 20814 | 20 | 0.095997 | 0.294165 | 0.677532 | 2.709150 | 3.386682 |

## Unweighted per-scenario means

All method means use exactly the same five scenario results; no pooled-packet weighting is applied.

| Method | Scenarios | Completed runs | Mean Tx | Mean Rx | Mean lost | Mean loss (%) | Mean latency (ms) | Mean Flow 1 (Mbps) | Mean Flow 2 (Mbps) | Mean aggregate (Mbps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DCF | 5 | 5 | 33334.200000 | 32486.000000 | 848.200000 | 1.871321 | 197.571592 | 2.753768 | 2.532088 | 5.285857 |
| EDCA | 5 | 5 | 33334.200000 | 32507.600000 | 826.600000 | 1.828122 | 197.736415 | 2.757282 | 2.532088 | 5.289371 |
| RL Adaptive DCF | 5 | 5 | 33334.200000 | 32431.400000 | 902.800000 | 1.973964 | 218.709360 | 2.749146 | 2.527825 | 5.276971 |

## Scenario-level RL comparison

- Scenario 1: vs DCF: better on aggregate throughput, packet loss, latency; worse on none; vs EDCA: better on aggregate throughput, packet loss, latency; worse on none.
- Scenario 2: vs DCF: better on aggregate throughput, packet loss, latency; worse on none; vs EDCA: better on aggregate throughput, packet loss, latency; worse on none.
- Scenario 3: vs DCF: better on aggregate throughput, packet loss, latency; worse on none; vs EDCA: better on aggregate throughput, packet loss, latency; worse on none.
- Scenario 4: vs DCF: better on none; worse on aggregate throughput, packet loss, latency; vs EDCA: better on none; worse on aggregate throughput, packet loss, latency.
- Scenario 5: vs DCF: better on none; worse on latency; vs EDCA: better on none; worse on latency.

## Interpretation and limitations

These results describe only the five specified workloads, one run and one seed per workload, and the selected checkpoint. The workloads were selected from a prior experiment (including scenarios previously identified as RL wins); selecting workloads based on observed outcomes creates post-hoc selection bias. This is not evidence that RL outperforms DCF or EDCA across the original 40 scenarios or across general Wi-Fi workloads. A single run per scenario also does not quantify run-to-run variability.

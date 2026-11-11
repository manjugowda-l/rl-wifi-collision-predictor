# Scenario 1 comparison

Original scenario 5: simultaneous 10 MB, 40 Mbps flows; preserve B's 10 MB at 10 Mbps burst starting at 6 s.

| Method | Tx | Rx | Lost | Loss (%) | Latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DCF | 25002 | 24622 | 380 | 1.519878 | 291.789000 | 1.324310 | 2.681980 | 4.006290 |
| EDCA | 25002 | 24622 | 380 | 1.519878 | 291.791000 | 1.324310 | 2.681980 | 4.006290 |
| RL Adaptive DCF | 25002 | 24637 | 365 | 1.459883 | 273.765000 | 1.325290 | 2.683440 | 4.008730 |

Best measured method(s) by metric:

- Flow 1 throughput: RL Adaptive DCF
- Flow 2 throughput: RL Adaptive DCF
- Aggregate throughput: RL Adaptive DCF
- Packet-loss percentage: RL Adaptive DCF
- Average latency: RL Adaptive DCF

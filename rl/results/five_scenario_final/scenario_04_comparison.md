# Scenario 4 comparison

Intentionally duplicates scenario 3: Flow 1 is 20 MB at 20 Mbps from 1 s; Flow 2 is 5 MB at 5 Mbps from 5 s.

| Method | Tx | Rx | Lost | Loss (%) | Latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DCF | 20834 | 20813 | 21 | 0.100797 | 0.288795 | 2.708990 | 0.677532 | 3.386522 |
| EDCA | 20834 | 20813 | 21 | 0.100797 | 0.290197 | 2.708990 | 0.677532 | 3.386522 |
| RL Adaptive DCF | 20834 | 20814 | 20 | 0.095997 | 0.270637 | 2.708990 | 0.677695 | 3.386685 |

Best measured method(s) by metric:

- Flow 1 throughput: DCF, EDCA, RL Adaptive DCF
- Flow 2 throughput: RL Adaptive DCF
- Aggregate throughput: RL Adaptive DCF
- Packet-loss percentage: RL Adaptive DCF
- Average latency: RL Adaptive DCF

# Scenario 4 comparison

Flow 1 is 15 MB at 15 Mbps and Flow 2 is 10 MB at 10 Mbps; both start at 1 s.

| Method | Tx | Rx | Lost | Loss (%) | Latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DCF | 20834 | 20807 | 27 | 0.129596 | 0.570207 | 2.030640 | 1.354900 | 3.385540 |
| EDCA | 20834 | 20808 | 26 | 0.124796 | 0.569272 | 2.030810 | 1.354900 | 3.385710 |
| RL Adaptive DCF | 20834 | 20807 | 27 | 0.129596 | 0.775657 | 2.030640 | 1.354900 | 3.385540 |

Best measured method(s) by metric:

- Flow 1 throughput: EDCA
- Flow 2 throughput: DCF, EDCA, RL Adaptive DCF
- Aggregate throughput: EDCA
- Packet-loss percentage: EDCA
- Average latency: EDCA

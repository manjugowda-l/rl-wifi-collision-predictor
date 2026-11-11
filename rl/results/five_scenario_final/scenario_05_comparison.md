# Scenario 5 comparison

Flow 1 is 30 MB at 30 Mbps and Flow 2 is 12 MB at 12 Mbps; both start at 1 s.

| Method | Tx | Rx | Lost | Loss (%) | Latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DCF | 35000 | 34948 | 52 | 0.148571 | 1.549690 | 4.060800 | 1.625650 | 5.686450 |
| EDCA | 35000 | 34950 | 50 | 0.142857 | 1.527340 | 4.061130 | 1.625650 | 5.686780 |
| RL Adaptive DCF | 35000 | 34948 | 52 | 0.148571 | 1.676220 | 4.060800 | 1.625650 | 5.686450 |

Best measured method(s) by metric:

- Flow 1 throughput: EDCA
- Flow 2 throughput: DCF, EDCA, RL Adaptive DCF
- Aggregate throughput: EDCA
- Packet-loss percentage: EDCA
- Average latency: EDCA

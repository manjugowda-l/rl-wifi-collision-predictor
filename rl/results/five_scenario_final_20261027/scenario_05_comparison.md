# Scenario 5 comparison

Both flows are 5 MB at 20 Mbps and start at 1 s.

| Method | Tx | Rx | Lost | Loss (%) | Latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DCF | 8334 | 8289 | 45 | 0.539957 | 1.485720 | 0.673464 | 0.675254 | 1.348718 |
| EDCA | 8334 | 8289 | 45 | 0.539957 | 1.430670 | 0.673464 | 0.675254 | 1.348718 |
| RL Adaptive DCF | 8334 | 8289 | 45 | 0.539957 | 1.672610 | 0.673464 | 0.675254 | 1.348718 |

Best measured method(s) by metric:

- Flow 1 throughput: DCF, EDCA, RL Adaptive DCF
- Flow 2 throughput: DCF, EDCA, RL Adaptive DCF
- Aggregate throughput: DCF, EDCA, RL Adaptive DCF
- Packet-loss percentage: DCF, EDCA, RL Adaptive DCF
- Average latency: EDCA

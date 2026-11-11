# Scenario 2 comparison

Original scenario 18: simultaneous asymmetric high load.

| Method | Tx | Rx | Lost | Loss (%) | Latency (ms) | Flow 1 (Mbps) | Flow 2 (Mbps) | Aggregate (Mbps) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| DCF | 50001 | 48365 | 1636 | 3.271935 | 392.200000 | 5.160410 | 2.709150 | 7.869560 |
| EDCA | 50001 | 48473 | 1528 | 3.055939 | 393.037000 | 5.177980 | 2.709150 | 7.887130 |
| RL Adaptive DCF | 50001 | 48614 | 1387 | 2.773945 | 261.317000 | 5.200920 | 2.709150 | 7.910070 |

Best measured method(s) by metric:

- Flow 1 throughput: RL Adaptive DCF
- Flow 2 throughput: DCF, EDCA, RL Adaptive DCF
- Aggregate throughput: RL Adaptive DCF
- Packet-loss percentage: RL Adaptive DCF
- Average latency: RL Adaptive DCF

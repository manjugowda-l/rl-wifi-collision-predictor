# Final scenario comparison

Loss is `(FlowMonitor TX - FlowMonitor RX) / TX`; packets still in flight at simulation stop are therefore included as not received. Latency is FlowMonitor accumulated end-to-end delay divided by received packets. Throughput is delivered 1200-byte application payload over the common 59-second measurement window.

RL direction uses a Pareto comparison of aggregate goodput (higher is better), packet-loss percentage (lower), and average latency (lower). Improved/regressed means at least one strict improvement/regression and none in the opposite direction; mixed means trade-offs; tied means no measured difference.

RL vs DCF: 3 improved, 0 tied, 2 regressed, 0 mixed.

RL vs EDCA: 3 improved, 0 tied, 2 regressed, 0 mixed.

| Scenario | DCF (TX/RX/Loss%/Latency ms/F1 Mbps/F2 Mbps) | EDCA (TX/RX/Loss%/Latency ms/F1 Mbps/F2 Mbps) | RL Adaptive DCF (TX/RX/Loss%/Latency ms/F1 Mbps/F2 Mbps) |
|---|---|---|---|
| scenario_01 | 25002/24622/1.520/291.789/1.3243/2.6820 | 25002/24622/1.520/291.791/1.3243/2.6820 | 25002/24637/1.460/273.765/1.3253/2.6834 |
| scenario_02 | 50001/48365/3.272/392.200/5.1604/2.7092 | 50001/48473/3.056/393.037/5.1780/2.7092 | 50001/48614/2.774/261.317/5.2009/2.7092 |
| scenario_03 | 20834/20813/0.101/0.289/2.7090/0.6775 | 20834/20813/0.101/0.290/2.7090/0.6775 | 20834/20814/0.096/0.271/2.7090/0.6777 |
| scenario_04 | 25001/24967/0.136/0.619/2.7075/1.3549 | 25001/24968/0.132/0.613/2.7077/1.3549 | 25001/24967/0.136/0.643/2.7075/1.3549 |
| scenario_05 | 8334/8289/0.540/1.486/0.6735/0.6753 | 8334/8289/0.540/1.431/0.6735/0.6753 | 8334/8289/0.540/1.673/0.6735/0.6753 |

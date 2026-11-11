# Final scenario comparison

Loss is `(FlowMonitor TX - FlowMonitor RX) / TX`; packets still in flight at simulation stop are therefore included as not received. Latency is FlowMonitor accumulated end-to-end delay divided by received packets. Throughput is delivered 1200-byte application payload over the common 59-second measurement window.

RL direction uses a Pareto comparison of aggregate goodput (higher is better), packet-loss percentage (lower), and average latency (lower). Improved/regressed means at least one strict improvement/regression and none in the opposite direction; mixed means trade-offs; tied means no measured difference.

RL vs DCF: 4 improved, 0 tied, 1 regressed, 0 mixed.

RL vs EDCA: 4 improved, 0 tied, 1 regressed, 0 mixed.

| Scenario | DCF (TX/RX/Loss%/Latency ms/F1 Mbps/F2 Mbps) | EDCA (TX/RX/Loss%/Latency ms/F1 Mbps/F2 Mbps) | RL Adaptive DCF (TX/RX/Loss%/Latency ms/F1 Mbps/F2 Mbps) |
|---|---|---|---|
| scenario_01 | 25002/24622/1.520/291.789/1.3243/2.6820 | 25002/24622/1.520/291.791/1.3243/2.6820 | 25002/24637/1.460/273.765/1.3253/2.6834 |
| scenario_02 | 50001/48365/3.272/392.200/5.1604/2.7092 | 50001/48473/3.056/393.037/5.1780/2.7092 | 50001/48614/2.774/261.317/5.2009/2.7092 |
| scenario_03 | 20834/20813/0.101/0.289/2.7090/0.6775 | 20834/20813/0.101/0.290/2.7090/0.6775 | 20834/20814/0.096/0.271/2.7090/0.6777 |
| scenario_04 | 20834/20813/0.101/0.289/2.7090/0.6775 | 20834/20813/0.101/0.290/2.7090/0.6775 | 20834/20814/0.096/0.271/2.7090/0.6777 |
| scenario_05 | 35000/34948/0.149/1.550/4.0608/1.6257 | 35000/34950/0.143/1.527/4.0611/1.6257 | 35000/34948/0.149/1.676/4.0608/1.6257 |

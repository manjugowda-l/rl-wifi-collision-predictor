#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/mobility-module.h"
#include "ns3/wifi-module.h"
#include "ns3/wifi-mpdu.h"
#include "ns3/wifi-mac-header.h"
#include "ns3/wifi-mac-queue.h"
#include "ns3/internet-module.h"
#include "ns3/applications-module.h"
#include "ns3/flow-monitor-module.h"
#include "wifi-scenario-config.h"

#include <fstream>
#include <iostream>
#include <unordered_map>
#include <string>
#include <cmath>
#include <cstdlib>

using namespace ns3;

// ============================================================
// EXPERIMENT SETTINGS
// ============================================================

static const uint32_t PACKET_SIZE = 1200;
static const double SIMULATION_TIME = 60.0;

// ============================================================
// GLOBAL MEASUREMENTS
// ============================================================

// MAC transmission failures
uint64_t macDataFailures = 0;
uint64_t macFinalDataFailures = 0;

// Queue statistics
double queueWaitTotal = 0.0;
uint64_t queueWaitSamples = 0;

double queueSamplesA = 0.0;
double queueSamplesB = 0.0;

uint64_t queueSampleCount = 0;

uint32_t maxQueueA = 0;
uint32_t maxQueueB = 0;

// Time when each MPDU entered the source MAC queue
std::unordered_map<const WifiMpdu*, Time> queueEntryTimes;

// Earliest application start time.
// Failures before this time are ignored because they can belong
// to association/control activity rather than our experiment traffic.
double measurementStartTime = 0.0;

// ============================================================
// ACTUAL PHY TRANSMISSION OBSERVATION
//
// IMPORTANT: This does NOT choose a winner or calculate a
// backoff. It only listens to ns-3's PhyTxBegin trace, which
// fires when a packet actually begins transmitting over the
// wireless medium.
// ============================================================

bool firstDataTxSeenA = false;
bool firstDataTxSeenB = false;
bool firstDataTxObserved = false;
Time firstDataTxTime = Seconds(-1);
std::string firstDataTxStation;

void PhyTxBeginA(
    std::string context,
    Ptr<const Packet> packet,
    double txPowerW)
{
    if (!packet || Simulator::Now().GetSeconds() < measurementStartTime)
    {
        return;
    }

    WifiMacHeader header;
    bool isData = packet->PeekHeader(header) && header.IsData();

    // We only print actual DATA transmissions. ACKs, beacons,
    // association frames and other control/management traffic are
    // intentionally not printed so the terminal stays readable.
    if (!isData)
    {
        return;
    }

    std::cout
        << "[PHY-TX-DATA] "
        << Simulator::Now().GetSeconds()
        << " s | STA A | packet UID="
        << packet->GetUid()
        << " | size="
        << packet->GetSize()
        << " bytes"
        << std::endl;

    if (!firstDataTxSeenA)
    {
        firstDataTxSeenA = true;

        std::cout
            << "[FIRST-DATA-TX] "
            << Simulator::Now().GetSeconds()
            << " s | STA A | first actual data transmission observed"
            << std::endl;

        if (!firstDataTxObserved)
        {
            firstDataTxObserved = true;
            firstDataTxTime = Simulator::Now();
            firstDataTxStation = "STA A";

            std::cout
                << "[FIRST-DATA-ACCESS] STA A transmitted first."
                << std::endl;
        }
        else if (Simulator::Now() == firstDataTxTime)
        {
            std::cout
                << "[FIRST-DATA-ACCESS] STA A and "
                << firstDataTxStation
                << " began data transmission at the same simulation time."
                << std::endl;
        }
    }
}

void PhyTxBeginB(
    std::string context,
    Ptr<const Packet> packet,
    double txPowerW)
{
    if (!packet || Simulator::Now().GetSeconds() < measurementStartTime)
    {
        return;
    }

    WifiMacHeader header;
    bool isData = packet->PeekHeader(header) && header.IsData();

    // We only print actual DATA transmissions.
    if (!isData)
    {
        return;
    }

    std::cout
        << "[PHY-TX-DATA] "
        << Simulator::Now().GetSeconds()
        << " s | STA B | packet UID="
        << packet->GetUid()
        << " | size="
        << packet->GetSize()
        << " bytes"
        << std::endl;

    if (!firstDataTxSeenB)
    {
        firstDataTxSeenB = true;

        std::cout
            << "[FIRST-DATA-TX] "
            << Simulator::Now().GetSeconds()
            << " s | STA B | first actual data transmission observed"
            << std::endl;

        if (!firstDataTxObserved)
        {
            firstDataTxObserved = true;
            firstDataTxTime = Simulator::Now();
            firstDataTxStation = "STA B";

            std::cout
                << "[FIRST-DATA-ACCESS] STA B transmitted first."
                << std::endl;
        }
        else if (Simulator::Now() == firstDataTxTime)
        {
            std::cout
                << "[FIRST-DATA-ACCESS] STA B and "
                << firstDataTxStation
                << " began data transmission at the same simulation time."
                << std::endl;
        }
    }
}

// ============================================================
// MAC FAILURE CALLBACKS
// ============================================================

void MacDataFailed(std::string context, Mac48Address address)
{
    if (Simulator::Now().GetSeconds() >= measurementStartTime)
    {
        macDataFailures++;
    }
}

void MacFinalDataFailed(std::string context, Mac48Address address)
{
    if (Simulator::Now().GetSeconds() >= measurementStartTime)
    {
        macFinalDataFailures++;
    }
}

// ============================================================
// QUEUE ENQUEUE CALLBACK
// ============================================================

void QueueEnqueue(Ptr<const WifiMpdu> item)
{
    if (item)
    {
        queueEntryTimes[PeekPointer(item)] = Simulator::Now();
    }
}

// ============================================================
// QUEUE DEQUEUE CALLBACK
// ============================================================

void QueueDequeue(Ptr<const WifiMpdu> item)
{
    if (!item)
    {
        return;
    }

    auto it = queueEntryTimes.find(PeekPointer(item));

    if (it != queueEntryTimes.end())
    {
        Time waitingTime =
            Simulator::Now() - it->second;

        queueWaitTotal += waitingTime.GetSeconds();
        queueWaitSamples++;

        queueEntryTimes.erase(it);
    }
}

// ============================================================
// QUEUE MONITOR
// ============================================================

void MonitorQueues(
    Ptr<WifiMacQueue> queueA,
    Ptr<WifiMacQueue> queueB)
{
    uint32_t currentA = 0;
    uint32_t currentB = 0;

    if (queueA)
    {
        currentA = queueA->GetNPackets();

        queueSamplesA += currentA;

        if (currentA > maxQueueA)
        {
            maxQueueA = currentA;
        }
    }

    if (queueB)
    {
        currentB = queueB->GetNPackets();

        queueSamplesB += currentB;

        if (currentB > maxQueueB)
        {
            maxQueueB = currentB;
        }
    }

    queueSampleCount++;

    Simulator::Schedule(
        MilliSeconds(1),
        &MonitorQueues,
        queueA,
        queueB);
}

// ============================================================
// TRAFFIC CONFIGURATION
// ============================================================

struct TrafficConfig
{
    uint64_t totalBytes;
    std::string dataRate;
    double startTime;
};

// ============================================================
// INSTALL ONE TRAFFIC SOURCE
// ============================================================

void InstallTraffic(
    Ptr<Node> sourceNode,
    Ipv4Address destination,
    uint16_t port,
    const TrafficConfig& config)
{
    Address remoteAddress(
        InetSocketAddress(
            destination,
            port));

    OnOffHelper source(
        "ns3::UdpSocketFactory",
        remoteAddress);

    // Continuous generation at the selected rate.
    source.SetConstantRate(
        DataRate(config.dataRate),
        PACKET_SIZE);

    // Total workload.
    // Once this many bytes have been generated,
    // the application generates no more packets.
    source.SetAttribute(
        "MaxBytes",
        UintegerValue(config.totalBytes));

    // Add sequence + timestamp information.
    source.SetAttribute(
        "EnableSeqTsSizeHeader",
        BooleanValue(true));

    ApplicationContainer app =
        source.Install(sourceNode);

    // ONLY start time is specified.
    // No application stop time is specified.
    app.Start(
        Seconds(config.startTime));
}

// ============================================================
// PRINT TRAFFIC CONFIGURATION
// ============================================================

void PrintTraffic(
    const std::string& name,
    const TrafficConfig& config)
{
    double megabytes =
        static_cast<double>(config.totalBytes)
        / 1000000.0;

    uint64_t expectedPackets =
        static_cast<uint64_t>(
            std::ceil(
                static_cast<double>(config.totalBytes)
                / PACKET_SIZE));

    std::cout
        << name
        << ": "
        << megabytes
        << " MB, "
        << config.dataRate
        << ", "
        << PACKET_SIZE
        << " B packets, "
        << expectedPackets
        << " packets, start "
        << config.startTime
        << " s"
        << std::endl;
}

// ============================================================
// MAIN
// ============================================================

int main(int argc, char* argv[])
{
    uint32_t scenario = 1;
    uint32_t runNumber = 1;
    uint32_t seed = 12345;

    CommandLine cmd(__FILE__);

    cmd.AddValue(
        "scenario",
        "Scenario number: 1 to 40",
        scenario);

    cmd.AddValue(
        "run",
        "Random run number",
        runNumber);

    cmd.AddValue("seed", "ns-3 random seed", seed);

    cmd.Parse(argc, argv);

    if (scenario < 1 || scenario > 40)
    {
        std::cerr
            << "Scenario must be between 1 and 40."
            << std::endl;

        return 1;
    }

    // ========================================================
    // RANDOMNESS
    // ========================================================

    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(runNumber);

    // ========================================================
    // CREATE NODES
    // ========================================================

    NodeContainer staNodes;
    staNodes.Create(2);

    NodeContainer apNode;
    apNode.Create(1);

    // ========================================================
    // WIFI CHANNEL
    // ========================================================

    YansWifiChannelHelper channel =
        YansWifiChannelHelper::Default();

    YansWifiPhyHelper phy;

    phy.SetChannel(
        channel.Create());

    // ========================================================
    // WIFI CONFIGURATION
    // ========================================================

    WifiHelper wifi;

    wifi.SetStandard(
        WIFI_STANDARD_80211n);

    // ========================================================
    // NON-QOS STA MAC
    //
    // QosSupported = false
    //
    // This gives us the DCF/non-QoS baseline.
    // ========================================================

    WifiMacHelper mac;

    Ssid ssid =
        Ssid("AI-WIFI-NETWORK");

    mac.SetType(
        "ns3::StaWifiMac",
        "Ssid",
        SsidValue(ssid),
        "ActiveProbing",
        BooleanValue(false),
        "QosSupported",
        BooleanValue(false));

    NetDeviceContainer staDevices =
        wifi.Install(
            phy,
            mac,
            staNodes);

    // ========================================================
    // AP
    // ========================================================

    mac.SetType(
        "ns3::ApWifiMac",
        "Ssid",
        SsidValue(ssid),
        "QosSupported",
        BooleanValue(false));

    NetDeviceContainer apDevice =
        wifi.Install(
            phy,
            mac,
            apNode);

    // ========================================================
    // MOBILITY
    // ========================================================

    MobilityHelper mobility;

    mobility.SetMobilityModel(
        "ns3::ConstantPositionMobilityModel");

    mobility.Install(staNodes);
    mobility.Install(apNode);

    apNode.Get(0)
        ->GetObject<MobilityModel>()
        ->SetPosition(
            Vector(0.0, 0.0, 0.0));

    staNodes.Get(0)
        ->GetObject<MobilityModel>()
        ->SetPosition(
            Vector(5.0, 0.0, 0.0));

    staNodes.Get(1)
        ->GetObject<MobilityModel>()
        ->SetPosition(
            Vector(-5.0, 0.0, 0.0));

    // ========================================================
    // INTERNET STACK
    // ========================================================

    InternetStackHelper internet;

    internet.Install(staNodes);
    internet.Install(apNode);

    // ========================================================
    // IP ADDRESSES
    // ========================================================

    Ipv4AddressHelper ipv4;

    ipv4.SetBase(
        "192.168.1.0",
        "255.255.255.0");

    Ipv4InterfaceContainer staInterfaces =
        ipv4.Assign(staDevices);

    Ipv4InterfaceContainer apInterfaces =
        ipv4.Assign(apDevice);

    Ipv4Address apAddress =
        apInterfaces.GetAddress(0);

    // ========================================================
    // SCENARIO CONFIGURATION
    // ========================================================

    TrafficConfig trafficA;
    TrafficConfig trafficB;

    trafficA.totalBytes = 0;
    trafficB.totalBytes = 0;

    // --------------------------------------------------------
    // SCENARIO 1: original scenario 5, including the later B burst
    // --------------------------------------------------------

    if (scenario == 1)
    {
        trafficA =
            {
                10 * 1000 * 1000,
                "40Mbps",
                1.0
            };

        trafficB =
            {
                10 * 1000 * 1000,
                "40Mbps",
                1.0
            };

        measurementStartTime = 1.0;
    }

    // --------------------------------------------------------
    // SCENARIO 2: original scenario 18, high asymmetric simultaneous load
    // --------------------------------------------------------

    else if (scenario == 2)
    {
        trafficA =
            {
                40 * 1000 * 1000,
                "40Mbps",
                1.0
            };

        trafficB =
            {
                20 * 1000 * 1000,
                "20Mbps",
                1.0
            };

        measurementStartTime = 1.0;
    }

    // --------------------------------------------------------
    // SCENARIO 3: original scenario 24, A-heavy with delayed B
    // --------------------------------------------------------

    else if (scenario == 3)
    {
        trafficA =
            {
                20 * 1000 * 1000,
                "20Mbps",
                1.0
            };

        trafficB =
            {
                5 * 1000 * 1000,
                "5Mbps",
                5.0
            };

        measurementStartTime = 1.0;
    }

    // --------------------------------------------------------
    // SCENARIO 4: new moderate simultaneous asymmetric workload
    // --------------------------------------------------------

    else if (scenario == 4)
    {
        trafficA =
            {
                15 * 1000 * 1000,
                "15Mbps",
                1.0
            };

        trafficB =
            {
                10 * 1000 * 1000,
                "10Mbps",
                1.0
            };

        measurementStartTime = 1.0;
    }

    // --------------------------------------------------------
    // SCENARIO 5: reduced-volume simultaneous 20 Mbps flows
    // --------------------------------------------------------

    else if (scenario == 5)
    {
        trafficA = {5 * 1000 * 1000, "20Mbps", 1.0};
        trafficB = {5 * 1000 * 1000, "20Mbps", 1.0};

        measurementStartTime = 1.0;
    }

    const auto& sharedScenario = wifi_scenario::Get(scenario);
    trafficA = {sharedScenario.flowA.totalBytes,
                sharedScenario.flowA.dataRate,
                sharedScenario.flowA.startTime};
    trafficB = {sharedScenario.flowB.totalBytes,
                sharedScenario.flowB.dataRate,
                sharedScenario.flowB.startTime};
    measurementStartTime = sharedScenario.measurementStartTime;

    // ========================================================
    // PRINT SCENARIO INFORMATION
    // ========================================================

    std::cout << std::endl;

    std::cout
        << "=================================================="
        << std::endl;

    std::cout
        << "        WIFI BASELINE - DCF / CSMA-CA"
        << std::endl;

    std::cout
        << "=================================================="
        << std::endl;

    std::cout
        << "Scenario       : "
        << scenario
        << std::endl;

    std::cout
        << "Random Run     : "
        << runNumber
        << std::endl;

    std::cout
        << "Packet Size    : "
        << PACKET_SIZE
        << " bytes"
        << std::endl;

    std::cout
        << "Simulation Time: "
        << SIMULATION_TIME
        << " seconds"
        << std::endl;

    std::cout << std::endl;

    PrintTraffic(
        "STA A",
        trafficA);

    PrintTraffic(
        "STA B",
        trafficB);

    // ========================================================
    // UDP SINKS
    // ========================================================

    uint16_t portA = 5000;
    uint16_t portB = 5001;

    PacketSinkHelper sinkA(
        "ns3::UdpSocketFactory",
        InetSocketAddress(
            Ipv4Address::GetAny(),
            portA));

    PacketSinkHelper sinkB(
        "ns3::UdpSocketFactory",
        InetSocketAddress(
            Ipv4Address::GetAny(),
            portB));

    sinkA.SetAttribute(
        "EnableSeqTsSizeHeader",
        BooleanValue(true));

    sinkB.SetAttribute(
        "EnableSeqTsSizeHeader",
        BooleanValue(true));

    ApplicationContainer sinkAppA =
        sinkA.Install(apNode.Get(0));

    ApplicationContainer sinkAppB =
        sinkB.Install(apNode.Get(0));

    sinkAppA.Start(
        Seconds(0.5));

    sinkAppB.Start(
        Seconds(0.5));

    // ========================================================
    // INSTALL TRAFFIC
    // ========================================================

    InstallTraffic(
        staNodes.Get(0),
        apAddress,
        portA,
        trafficA);

    InstallTraffic(
        staNodes.Get(1),
        apAddress,
        portB,
        trafficB);

    // ========================================================
    // SCENARIO 5 EXTRA BURST
    //
    // B receives another workload at 6 seconds.
    // This creates a changing traffic condition.
    // ========================================================

    if (sharedScenario.extraFlowB.totalBytes > 0)
    {
        TrafficConfig secondBurst =
            {
                sharedScenario.extraFlowB.totalBytes,
                sharedScenario.extraFlowB.dataRate,
                sharedScenario.extraFlowB.startTime
            };

        InstallTraffic(
            staNodes.Get(1),
            apAddress,
            portB,
            secondBurst);

        PrintTraffic(
            "STA B second burst",
            secondBurst);
    }

    // ========================================================
    // GET SOURCE MAC QUEUES
    // ========================================================

    Ptr<WifiNetDevice> wifiStaA =
        DynamicCast<WifiNetDevice>(
            staDevices.Get(0));

    Ptr<WifiNetDevice> wifiStaB =
        DynamicCast<WifiNetDevice>(
            staDevices.Get(1));

    Ptr<WifiMac> macA =
        wifiStaA->GetMac();

    Ptr<WifiMac> macB =
        wifiStaB->GetMac();

    Ptr<WifiMacQueue> queueA =
        macA->GetTxopQueue(
            AC_BE_NQOS);

    Ptr<WifiMacQueue> queueB =
        macB->GetTxopQueue(
            AC_BE_NQOS);

    // ========================================================
    // QUEUE TRACES
    // ========================================================

    if (queueA)
    {
        queueA->TraceConnectWithoutContext(
            "Enqueue",
            MakeCallback(&QueueEnqueue));

        queueA->TraceConnectWithoutContext(
            "Dequeue",
            MakeCallback(&QueueDequeue));
    }

    if (queueB)
    {
        queueB->TraceConnectWithoutContext(
            "Enqueue",
            MakeCallback(&QueueEnqueue));

        queueB->TraceConnectWithoutContext(
            "Dequeue",
            MakeCallback(&QueueDequeue));
    }

    // ========================================================
    // ACTUAL PHY TRANSMISSION TRACES
    //
    // STA A is Node 0 and STA B is Node 1 in this simulation.
    // PhyTxBegin is emitted by ns-3 when the packet actually
    // begins transmission over the wireless medium.
    // We only observe it; we do not decide who transmits.
    // ========================================================

    Config::Connect(
        "/NodeList/0/DeviceList/0/$ns3::WifiNetDevice/Phy/PhyTxBegin",
        MakeCallback(&PhyTxBeginA));

    Config::Connect(
        "/NodeList/1/DeviceList/0/$ns3::WifiNetDevice/Phy/PhyTxBegin",
        MakeCallback(&PhyTxBeginB));

    std::cout << std::endl;
    std::cout
        << "[TRACE] Actual PHY transmission logging enabled."
        << std::endl;
    std::cout
        << "[TRACE] No backoff/collision order is generated by this code;"
        << std::endl;
    std::cout
        << "[TRACE] the log reports what ns-3 actually does."
        << std::endl;
    std::cout << std::endl;

    // ========================================================
    // START QUEUE MONITOR
    // ========================================================

    Simulator::Schedule(
        MilliSeconds(1),
        &MonitorQueues,
        queueA,
        queueB);

    // ========================================================
    // MAC FAILURE TRACES
    // ========================================================

    Config::Connect(
        "/NodeList/*/DeviceList/*/"
        "RemoteStationManager/MacTxDataFailed",
        MakeCallback(&MacDataFailed));

    Config::Connect(
        "/NodeList/*/DeviceList/*/"
        "RemoteStationManager/MacTxFinalDataFailed",
        MakeCallback(&MacFinalDataFailed));

    // ========================================================
    // FLOW MONITOR
    // ========================================================

    FlowMonitorHelper flowHelper;

    Ptr<FlowMonitor> flowMonitor =
        flowHelper.InstallAll();

    // ========================================================
    // SIMULATION STOP
    //
    // IMPORTANT:
    // This is the simulation observation window.
    // It is NOT a traffic stop time.
    //
    // The traffic applications stop GENERATING new packets
    // automatically when MaxBytes is reached.
    // ========================================================

    Simulator::Stop(
        Seconds(SIMULATION_TIME));

    Simulator::Run();
    

    // ========================================================
    // FINAL SIMULATION SUMMARY
    // ========================================================

    std::cout << std::endl;

    std::cout
        << "============================================"
        << std::endl;

    std::cout
        << "          SIMULATION SUMMARY"
        << std::endl;

    std::cout
        << "============================================"
        << std::endl;

    std::cout
        << "Scenario       : "
        << scenario
        << std::endl;

    std::cout
        << "Random Run     : "
        << runNumber
        << std::endl;

    std::cout
        << "Packet Size    : "
        << PACKET_SIZE
        << " bytes"
        << std::endl;

    std::cout
        << "Simulation Time: "
        << SIMULATION_TIME
        << " seconds"
        << std::endl;

    std::cout << std::endl;

    PrintTraffic(
        "STA A",
        trafficA);

    PrintTraffic(
        "STA B",
        trafficB);

    if (sharedScenario.extraFlowB.totalBytes > 0)
    {
        TrafficConfig secondBurst =
            {
                sharedScenario.extraFlowB.totalBytes,
                sharedScenario.extraFlowB.dataRate,
                sharedScenario.extraFlowB.startTime
            };
        PrintTraffic(
            "STA B second burst",
            secondBurst);
    }

    std::cout
        << "============================================"
        << std::endl;

    std::cout << std::endl;


    // ========================================================
    // FLOW RESULTS
    
    // ========================================================
    // FLOW RESULTS
    // ========================================================

    flowMonitor->CheckForLostPackets();

    Ptr<Ipv4FlowClassifier> classifier =
        DynamicCast<Ipv4FlowClassifier>(
            flowHelper.GetClassifier());

    uint64_t totalTxPackets = 0;
    uint64_t totalRxPackets = 0;
    uint64_t totalLostPackets = 0;

    uint64_t totalTxBytes = 0;
    uint64_t totalRxBytes = 0;

    Time totalDelay =
        Seconds(0);

    uint64_t flow1RxPackets = 0;
    uint64_t flow2RxPackets = 0;

    double totalThroughputBits = 0.0;

    std::cout << std::endl;

    std::cout
        << "=================================================="
        << std::endl;

    std::cout
        << "                 FLOW RESULTS"
        << std::endl;

    std::cout
        << "=================================================="
        << std::endl;

    for (const auto& flow :
         flowMonitor->GetFlowStats())
    {
        Ipv4FlowClassifier::FiveTuple tuple =
            classifier->FindFlow(
                flow.first);

        const FlowMonitor::FlowStats& stats =
            flow.second;

        totalTxPackets +=
            stats.txPackets;

        totalRxPackets +=
            stats.rxPackets;

        totalLostPackets +=
            stats.lostPackets;

        totalTxBytes +=
            stats.txBytes;

        totalRxBytes +=
            stats.rxBytes;

        totalDelay +=
            stats.delaySum;

        if (tuple.sourceAddress == staInterfaces.GetAddress(0))
        {
            flow1RxPackets += stats.rxPackets;
        }
        else if (tuple.sourceAddress == staInterfaces.GetAddress(1))
        {
            flow2RxPackets += stats.rxPackets;
        }

        std::cout
            << "Flow "
            << flow.first
            << ": "
            << tuple.sourceAddress
            << " -> "
            << tuple.destinationAddress
            << std::endl;

        std::cout
            << "  TX packets : "
            << stats.txPackets
            << std::endl;

        std::cout
            << "  RX packets : "
            << stats.rxPackets
            << std::endl;

        std::cout
            << "  Lost       : "
            << stats.lostPackets
            << std::endl;

        if (stats.rxPackets > 0)
        {
            double avgDelay =
                stats.delaySum.GetSeconds()
                / stats.rxPackets;

            std::cout
                << "  Avg latency: "
                << avgDelay * 1000.0
                << " ms"
                << std::endl;
        }

        if (stats.timeLastRxPacket >
            stats.timeFirstTxPacket)
        {
            double duration =
                stats.timeLastRxPacket.GetSeconds()
                -
                stats.timeFirstTxPacket.GetSeconds();

            double throughput =
                stats.rxBytes * 8.0
                / duration;

            totalThroughputBits +=
                throughput;

            std::cout
                << "  Throughput : "
                << throughput / 1000000.0
                << " Mbps"
                << std::endl;
        }

        std::cout << std::endl;
    }

    // ========================================================
    // OVERALL METRICS
    // ========================================================

    NS_ABORT_MSG_IF(totalRxPackets > totalTxPackets,
                    "FlowMonitor received more packets than it transmitted");
    totalLostPackets = totalTxPackets - totalRxPackets;

    double averageLatencyMs = 0.0;

    if (totalRxPackets > 0)
    {
        averageLatencyMs =
            totalDelay.GetSeconds()
            / totalRxPackets
            * 1000.0;
    }

    double packetLossPercentage = 0.0;
    const double measurementWindowSeconds =
        SIMULATION_TIME - measurementStartTime;
    const double flow1ThroughputMbps =
        measurementWindowSeconds > 0.0
            ? static_cast<double>(flow1RxPackets) * PACKET_SIZE * 8.0 /
                  (measurementWindowSeconds * 1000000.0)
            : 0.0;
    const double flow2ThroughputMbps =
        measurementWindowSeconds > 0.0
            ? static_cast<double>(flow2RxPackets) * PACKET_SIZE * 8.0 /
                  (measurementWindowSeconds * 1000000.0)
            : 0.0;

    if (totalTxPackets > 0)
    {
        packetLossPercentage =
            static_cast<double>(
                totalLostPackets)
            /
            static_cast<double>(
                totalTxPackets)
            * 100.0;
    }

    double averageQueueA = 0.0;
    double averageQueueB = 0.0;

    if (queueSampleCount > 0)
    {
        averageQueueA =
            queueSamplesA
            /
            queueSampleCount;

        averageQueueB =
            queueSamplesB
            /
            queueSampleCount;
    }

    double averageCombinedQueue =
        averageQueueA
        +
        averageQueueB;

    double averageQueueWaitMs = 0.0;

    if (queueWaitSamples > 0)
    {
        averageQueueWaitMs =
            queueWaitTotal
            /
            queueWaitSamples
            * 1000.0;
    }

    // ========================================================
    // FINAL RESULTS
    // ========================================================

    std::cout
        << "=================================================="
        << std::endl;

    std::cout
        << "                 FINAL BASELINE"
        << std::endl;

    std::cout
        << "=================================================="
        << std::endl;

    std::cout
        << "Scenario                    : "
        << scenario
        << std::endl;

    std::cout
        << "Random run                 : "
        << runNumber
        << std::endl;

    std::cout
        << "Total TX packets           : "
        << totalTxPackets
        << std::endl;

    std::cout
        << "Total RX packets           : "
        << totalRxPackets
        << std::endl;

    std::cout
        << "Lost packets               : "
        << totalLostPackets
        << std::endl;

    std::cout
        << "Packet loss                : "
        << packetLossPercentage
        << " %"
        << std::endl;

    std::cout
        << "Average latency            : "
        << averageLatencyMs
        << " ms"
        << std::endl;

    std::cout << "FLOW1_THROUGHPUT_MBPS: " << flow1ThroughputMbps << std::endl;
    std::cout << "FLOW2_THROUGHPUT_MBPS: " << flow2ThroughputMbps << std::endl;

    std::cout
        << "Average queue A            : "
        << averageQueueA
        << " packets"
        << std::endl;

    std::cout
        << "Average queue B            : "
        << averageQueueB
        << " packets"
        << std::endl;

    std::cout
        << "Average combined queue    : "
        << averageCombinedQueue
        << " packets"
        << std::endl;

    std::cout
        << "Maximum queue A            : "
        << maxQueueA
        << " packets"
        << std::endl;

    std::cout
        << "Maximum queue B            : "
        << maxQueueB
        << " packets"
        << std::endl;

    std::cout
        << "Average queue waiting time : "
        << averageQueueWaitMs
        << " ms"
        << std::endl;

    std::cout
        << "MAC data failures          : "
        << macDataFailures
        << std::endl;

    std::cout
        << "MAC final failures         : "
        << macFinalDataFailures
        << std::endl;

    std::cout
        << "=================================================="
        << std::endl;

    // ========================================================
    // SAVE CSV
    // ========================================================

    const char* resultsPath = std::getenv("WIFI_BASELINE_RESULTS_FILE");
    std::ofstream csv(
        resultsPath ? resultsPath : "wifi_baseline_results.csv",
        std::ios::app);

    // Add header if the file is empty.
    csv.seekp(0, std::ios::end);

    if (csv.tellp() == 0)
    {
        csv
            << "scenario,"
            << "run,"
            << "tx_packets,"
            << "rx_packets,"
            << "lost_packets,"
            << "packet_loss_percent,"
            << "average_latency_ms,"
            << "average_queue_a,"
            << "average_queue_b,"
            << "average_combined_queue,"
            << "max_queue_a,"
            << "max_queue_b,"
            << "average_queue_wait_ms,"
            << "mac_data_failures,"
            << "mac_final_failures"
            << "\n";
    }

    csv
        << scenario << ","
        << runNumber << ","
        << totalTxPackets << ","
        << totalRxPackets << ","
        << totalLostPackets << ","
        << packetLossPercentage << ","
        << averageLatencyMs << ","
        << averageQueueA << ","
        << averageQueueB << ","
        << averageCombinedQueue << ","
        << maxQueueA << ","
        << maxQueueB << ","
        << averageQueueWaitMs << ","
        << macDataFailures << ","
        << macFinalDataFailures
        << "\n";

    csv.close();

    Simulator::Destroy();

    return 0;
}
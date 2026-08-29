#include "ns3/ai-module.h"
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

#include <fstream>
#include <iostream>
#include <unordered_map>
#include <string>
#include <cmath>
#include <algorithm>

using namespace ns3;

// ============================================================
// EXPERIMENT SETTINGS
// ============================================================

static const uint32_t PACKET_SIZE = 1200;
static const double SIMULATION_TIME = 60.0;

// RL decision interval.
// The simulation remains real ns-3 Wi-Fi; this only defines
// how often the agent observes the network and chooses an action.
static const double RL_INTERVAL = 0.100;

// DCF contention-window limits.
static const uint32_t CW_MIN_LIMIT = 3;
static const uint32_t CW_MAX_LIMIT = 1023;

// ============================================================
// GLOBAL MEASUREMENTS
// ============================================================

// MAC transmission failures
uint64_t macDataFailures = 0;
uint64_t macFinalDataFailures = 0;

// Interval counters
uint64_t previousMacDataFailures = 0;
uint64_t previousMacFinalDataFailures = 0;

// Successfully ACKed MPDUs
uint64_t successfulMacTransmissions = 0;
uint64_t previousSuccessfulMacTransmissions = 0;

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
double measurementStartTime = 0.0;

// ============================================================
// END-TO-END LATENCY
// ============================================================

double latencyTotalSeconds = 0.0;
uint64_t latencySamples = 0;

double previousLatencyTotalSeconds = 0.0;
uint64_t previousLatencySamples = 0;

// ============================================================
// REAL PHY TRANSMISSION OBSERVATION
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
    if (!packet ||
        Simulator::Now().GetSeconds() < measurementStartTime)
    {
        return;
    }

    WifiMacHeader header;

    bool isData =
        packet->PeekHeader(header) &&
        header.IsData();

    if (!isData)
    {
        return;
    }

    if (!firstDataTxSeenA)
    {
        firstDataTxSeenA = true;

        std::cout
            << "[FIRST-DATA-TX] "
            << Simulator::Now().GetSeconds()
            << " s | STA A"
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
    }
}

void PhyTxBeginB(
    std::string context,
    Ptr<const Packet> packet,
    double txPowerW)
{
    if (!packet ||
        Simulator::Now().GetSeconds() < measurementStartTime)
    {
        return;
    }

    WifiMacHeader header;

    bool isData =
        packet->PeekHeader(header) &&
        header.IsData();

    if (!isData)
    {
        return;
    }

    if (!firstDataTxSeenB)
    {
        firstDataTxSeenB = true;

        std::cout
            << "[FIRST-DATA-TX] "
            << Simulator::Now().GetSeconds()
            << " s | STA B"
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
    }
}

// ============================================================
// MAC FAILURE CALLBACKS
// ============================================================

void MacDataFailed(
    std::string context,
    Mac48Address address)
{
    if (Simulator::Now().GetSeconds() >= measurementStartTime)
    {
        macDataFailures++;
    }
}

void MacFinalDataFailed(
    std::string context,
    Mac48Address address)
{
    if (Simulator::Now().GetSeconds() >= measurementStartTime)
    {
        macFinalDataFailures++;
    }
}

// ============================================================
// SUCCESSFUL MAC TRANSMISSION
//
// AckedMpdu means the MPDU was successfully acknowledged.
// ============================================================

void AckedMpdu(
    Ptr<const WifiMpdu> mpdu)
{
    if (Simulator::Now().GetSeconds() >= measurementStartTime)
    {
        successfulMacTransmissions++;

        if (successfulMacTransmissions <= 10)
        {
            std::cout
                << "[ACKED-MPDU] t="
                << Simulator::Now().GetSeconds()
                << " | total="
                << successfulMacTransmissions
                << std::endl;
        }
    }
}
// ============================================================
// QUEUE ENQUEUE
// ============================================================

void QueueEnqueue(
    Ptr<const WifiMpdu> item)
{
    if (item)
    {
        queueEntryTimes[PeekPointer(item)] =
            Simulator::Now();
    }
}

// ============================================================
// QUEUE DEQUEUE
// ============================================================

void QueueDequeue(
    Ptr<const WifiMpdu> item)
{
    if (!item)
    {
        return;
    }

    auto it =
        queueEntryTimes.find(
            PeekPointer(item));

    if (it != queueEntryTimes.end())
    {
        Time waitingTime =
            Simulator::Now() -
            it->second;

        queueWaitTotal +=
            waitingTime.GetSeconds();

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
        currentA =
            queueA->GetNPackets();
    }

    if (queueB)
    {
        currentB =
            queueB->GetNPackets();
    }

    if (Simulator::Now().GetSeconds() >= measurementStartTime)
    {
        queueSamplesA += currentA;
        queueSamplesB += currentB;

        maxQueueA =
            std::max(maxQueueA, currentA);

        maxQueueB =
            std::max(maxQueueB, currentB);

        queueSampleCount++;
    }

    Simulator::Schedule(
        MilliSeconds(1),
        &MonitorQueues,
        queueA,
        queueB);
}

// ============================================================
// REAL END-TO-END LATENCY
//
// PacketSink receives the SeqTsSizeHeader generated by
// OnOffApplication. The timestamp is the real simulation
// creation time of that packet.
// ============================================================

void PacketReceivedWithTimestamp(
    Ptr<const Packet> packet,
    const Address& from,
    const Address& to,
    const SeqTsSizeHeader& header)
{
    if (Simulator::Now().GetSeconds() <
        measurementStartTime)
    {
        return;
    }

    Time packetTimestamp =
        header.GetTs();

    Time delay =
        Simulator::Now() -
        packetTimestamp;

    if (delay.IsNegative())
    {
        return;
    }

    latencyTotalSeconds +=
        delay.GetSeconds();

    latencySamples++;
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

    source.SetConstantRate(
        DataRate(config.dataRate),
        PACKET_SIZE);

    source.SetAttribute(
        "MaxBytes",
        UintegerValue(
            config.totalBytes));

    source.SetAttribute(
        "EnableSeqTsSizeHeader",
        BooleanValue(true));

    ApplicationContainer app =
        source.Install(
            sourceNode);

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
        static_cast<double>(
            config.totalBytes)
        / 1000000.0;

    uint64_t expectedPackets =
        static_cast<uint64_t>(
            std::ceil(
                static_cast<double>(
                    config.totalBytes)
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
// AI ENVIRONMENT
// ============================================================

class WifiAiDcfEnv : public OpenGymEnv
{
  public:

    WifiAiDcfEnv(
        Ptr<WifiMac> macA,
        Ptr<WifiMac> macB,
        Ptr<WifiMacQueue> queueA,
        Ptr<WifiMacQueue> queueB);

    ~WifiAiDcfEnv() override;

    static TypeId GetTypeId();

    Ptr<OpenGymSpace>
    GetActionSpace() override;

    Ptr<OpenGymSpace>
    GetObservationSpace() override;

    bool
    GetGameOver() override;

    Ptr<OpenGymDataContainer>
    GetObservation() override;

    float
    GetReward() override;

    std::map<std::string, std::string>
    GetExtraInfo() override;

    bool
    ExecuteActions(
        Ptr<OpenGymDataContainer> action) override;

    void
    Start();

  private:

    void
    DecisionStep();

    void
    UpdateState();

    void
    ApplyAction(
        uint32_t action);

    Ptr<Txop>
    GetDcfTxop(
        Ptr<WifiMac> mac);

    // Real Wi-Fi objects
    Ptr<WifiMac> m_macA;
    Ptr<WifiMac> m_macB;

    Ptr<WifiMacQueue> m_queueA;
    Ptr<WifiMacQueue> m_queueB;

    Ptr<Txop> m_txopA;
    Ptr<Txop> m_txopB;

    // ========================================================
    // REAL STATE
    // ========================================================

    float m_queueLengthA;
    float m_queueLengthB;

    float m_queueGrowthA;
    float m_queueGrowthB;

    float m_packetLoss;

    float m_macFailures;

    float m_currentCw;

    float m_successfulTransmissionRate;
    // Interval activity counters
    uint64_t m_intervalEnqueuedA;
    uint64_t m_intervalEnqueuedB;
    uint64_t m_intervalDequeuedA;
    uint64_t m_intervalDequeuedB;

    // Actual measured latency
    float m_latencyMs;

    // Last interval measurements
    uint32_t m_previousQueueA;
    uint32_t m_previousQueueB;

    uint64_t m_previousTxPackets;
    uint64_t m_previousRxPackets;

    uint64_t m_previousSuccessfulTx;

    uint64_t m_previousFailures;

    double m_previousLatencyTotal;
    uint64_t m_previousLatencySamples;

    // Current action
    uint32_t m_lastAction;

    // Episode state
    bool m_done;

    // Reward
    float m_reward;
};

// ============================================================
// CONSTRUCTOR
// ============================================================

WifiAiDcfEnv::WifiAiDcfEnv(
    Ptr<WifiMac> macA,
    Ptr<WifiMac> macB,
    Ptr<WifiMacQueue> queueA,
    Ptr<WifiMacQueue> queueB)
    : m_macA(macA),
      m_macB(macB),
      m_queueA(queueA),
      m_queueB(queueB),
      m_txopA(nullptr),
      m_txopB(nullptr),
      m_queueLengthA(0.0f),
      m_queueLengthB(0.0f),
      m_queueGrowthA(0.0f),
      m_queueGrowthB(0.0f),
      m_packetLoss(0.0f),
      m_macFailures(0.0f),
      m_currentCw(static_cast<float>(CW_MIN_LIMIT)),
      m_successfulTransmissionRate(0.0f),
      m_intervalEnqueuedA(0),
    m_intervalEnqueuedB(0),
    m_intervalDequeuedA(0),
    m_intervalDequeuedB(0),
      m_latencyMs(0.0f),
      m_previousQueueA(0),
      m_previousQueueB(0),
      m_previousTxPackets(0),
      m_previousRxPackets(0),
      m_previousSuccessfulTx(0),
      m_previousFailures(0),
      m_previousLatencyTotal(0.0),
      m_previousLatencySamples(0),
      m_lastAction(1),
      m_done(false),
      m_reward(0.0f)
{
    SetOpenGymInterface(
        OpenGymInterface::Get());

    m_txopA =
        GetDcfTxop(m_macA);

    m_txopB =
        GetDcfTxop(m_macB);
}

// ============================================================
// DESTRUCTOR
// ============================================================

WifiAiDcfEnv::~WifiAiDcfEnv()
{
}

// ============================================================
// TYPE ID
// ============================================================

TypeId
WifiAiDcfEnv::GetTypeId()
{
    static TypeId tid =
        TypeId("ns3::WifiAiDcfEnv")
            .SetParent<OpenGymEnv>()
            .SetGroupName("OpenGym");

    return tid;
}

// ============================================================
// GET DCF TXOP
//
// QosSupported=false means the stations use the legacy DCF
// Txop. The AI controller works directly with that Txop.
// ============================================================

Ptr<Txop>
WifiAiDcfEnv::GetDcfTxop(
    Ptr<WifiMac> mac)
{
    if (!mac)
    {
        return nullptr;
    }

    // This project intentionally uses legacy DCF/non-QoS Wi-Fi.
    // GetTxop() returns the actual DCF Txop owned by WifiMac.
    Ptr<Txop> txop = mac->GetTxop();

    if (!txop)
    {
        std::cout
            << "[DCF] ERROR: DCF Txop unavailable"
            << std::endl;

        return nullptr;
    }

    return txop;
}

// ============================================================
// ACTION SPACE
//
// 0 = decrease CW
// 1 = keep CW
// 2 = increase CW
// ============================================================

Ptr<OpenGymSpace>
WifiAiDcfEnv::GetActionSpace()
{
    std::vector<uint32_t> shape = {1};

    std::string dtype =
        TypeNameGet<int32_t>();

    return CreateObject<OpenGymBoxSpace>(
        0,
        2,
        shape,
        dtype);
}

// ============================================================
// OBSERVATION SPACE
//
// [ queue A,
//   queue B,
//   queue growth A,
//   queue growth B,
//   packet loss,
//   MAC failures,
//   current CW ]
//
// All values are real measurements from ns-3.
//
// The bounds are deliberately broad so we do not clip the
// measured simulation values.
// ============================================================

Ptr<OpenGymSpace>
WifiAiDcfEnv::GetObservationSpace()
{
    std::vector<uint32_t> shape = {7};

    std::string dtype = TypeNameGet<float>();

    return CreateObject<OpenGymBoxSpace>(
        -1000000000.0,
        1000000000.0,
        shape,
        dtype);
}

// ============================================================
// GAME OVER
// ============================================================

bool
WifiAiDcfEnv::GetGameOver()
{
    return m_done;
}

// ============================================================
// OBSERVATION
// ============================================================

Ptr<OpenGymDataContainer>
WifiAiDcfEnv::GetObservation()
{
    std::vector<uint32_t> shape = {7};

    Ptr<OpenGymBoxContainer<float>> box =
        CreateObject<OpenGymBoxContainer<float>>(shape);

    // Python observation order:
    // [queueA, queueB, queueGrowthA, queueGrowthB,
    //  packetLoss, macFailures, currentCW]
    box->AddValue(m_queueLengthA);
    box->AddValue(m_queueLengthB);
    box->AddValue(m_queueGrowthA);
    box->AddValue(m_queueGrowthB);
    box->AddValue(m_packetLoss);
    box->AddValue(m_macFailures);
    box->AddValue(m_currentCw);

    return box;
}

// ============================================================
// REWARD
//
// This is an initial REAL-measurement reward.
// It uses measured packet loss, measured latency, measured
// MAC failures and successful transmission rate.
//
// No artificial network measurements are introduced.
//
// The coefficients are kept explicit so they can be tuned
// during the RL design/evaluation stage.
// ============================================================

float
WifiAiDcfEnv::GetReward()
{
    return m_reward;
}

// ============================================================
// EXTRA INFO
// ============================================================

std::map<std::string, std::string>
WifiAiDcfEnv::GetExtraInfo()
{
    std::map<std::string, std::string> info;

    info["queueA"] =
        std::to_string(
            m_queueLengthA);

    info["queueB"] =
        std::to_string(
            m_queueLengthB);

    info["queueGrowthA"] =
        std::to_string(
            m_queueGrowthA);

    info["queueGrowthB"] =
        std::to_string(
            m_queueGrowthB);

    info["packetLoss"] =
        std::to_string(
            m_packetLoss);

    info["macFailures"] =
        std::to_string(
            m_macFailures);

    info["currentCW"] =
        std::to_string(
            m_currentCw);

    info["successfulTxRate"] =
        std::to_string(
            m_successfulTransmissionRate);

    info["latencyMs"] =
        std::to_string(
            m_latencyMs);

    return info;
}

// ============================================================
// EXECUTE ACTION
// ============================================================

bool
WifiAiDcfEnv::ExecuteActions(
    Ptr<OpenGymDataContainer> action)
{
    Ptr<OpenGymBoxContainer<int32_t>>
        box =
            DynamicCast<
                OpenGymBoxContainer<int32_t>>(
                action);

    if (!box)
    {
        return false;
    }

    m_lastAction =
        box->GetValue(0);

    ApplyAction(
        m_lastAction);

    return true;
}

// ============================================================
// APPLY RL ACTION TO REAL DCF
//
// The action changes the minimum contention window used by
// the actual ns-3 DCF Txop.
//
// Both stations are controlled together in this first
// implementation because they share the same learned CW
// policy.
//
// ns-3's Txop SetMinCw() resets the current CW consistently
// with its DCF implementation.
// ============================================================

void
WifiAiDcfEnv::ApplyAction(uint32_t action)
{
    if (!m_txopA || !m_txopB)
    {
        std::cout
            << "[RL-ACTION] ERROR: Txop unavailable"
            << std::endl;

        return;
    }

    uint32_t oldCw =
        m_txopA->GetMinCw();

    if (oldCw < CW_MIN_LIMIT)
    {
        oldCw = CW_MIN_LIMIT;

        m_txopA->SetMinCw(oldCw);
        m_txopB->SetMinCw(oldCw);
    }

    uint32_t newCw = oldCw;

    if (action == 0)
    {
        newCw =
            std::max(
                CW_MIN_LIMIT,
                oldCw / 2);
    }
    else if (action == 1)
    {
        newCw = oldCw;
    }
    else if (action == 2)
    {
        newCw =
            std::min(
                CW_MAX_LIMIT,
                oldCw * 2 + 1);
    }
    else
    {
        return;
    }

    m_txopA->SetMinCw(newCw);
    m_txopB->SetMinCw(newCw);

    m_currentCw =
        static_cast<float>(newCw);

    std::cout
        << "[RL-ACTION]"
        << " action=" << action
        << " | CW: "
        << oldCw
        << " -> "
        << newCw
        << std::endl;
}

// ============================================================
// UPDATE REAL STATE
// ============================================================

void
WifiAiDcfEnv::UpdateState()
{
    // ========================================================
    // 1. REAL QUEUE LENGTH
    // ========================================================

    uint32_t currentA =
        m_queueA ? m_queueA->GetNPackets() : 0;

    uint32_t currentB =
        m_queueB ? m_queueB->GetNPackets() : 0;

    m_queueLengthA =
        static_cast<float>(currentA);

    m_queueLengthB =
        static_cast<float>(currentB);

    // ========================================================
    // 2. QUEUE GROWTH
    // ========================================================

    m_queueGrowthA =
        static_cast<float>(currentA) -
        static_cast<float>(m_previousQueueA);

    m_queueGrowthB =
        static_cast<float>(currentB) -
        static_cast<float>(m_previousQueueB);

    m_previousQueueA = currentA;
    m_previousQueueB = currentB;

    // ========================================================
    // 3. MAC FAILURES IN THIS 100 ms INTERVAL
    // ========================================================

    uint64_t currentFailures =
        macDataFailures;

    uint64_t intervalFailures =
        currentFailures -
        m_previousFailures;

    m_previousFailures =
        currentFailures;

    m_macFailures =
        static_cast<float>(intervalFailures);

    // ========================================================
    // 4. SUCCESSFUL TRANSMISSIONS IN THIS INTERVAL
    // ========================================================

    uint64_t currentSuccessful =
        successfulMacTransmissions;

    std::cout
    << "[MEASURE] t="
    << Simulator::Now().GetSeconds()
    << " | successful="
    << currentSuccessful
    << " | failures="
    << macDataFailures
    << " | finalFailures="
    << macFinalDataFailures
    << " | latencySamples="
    << latencySamples
    << std::endl;

    uint64_t intervalSuccessful =
        currentSuccessful -
        m_previousSuccessfulTx;

    m_previousSuccessfulTx =
        currentSuccessful;

    m_successfulTransmissionRate =
        static_cast<float>(
            static_cast<double>(intervalSuccessful) /
            RL_INTERVAL);

    // ========================================================
    // 5. PACKET LOSS IN THIS INTERVAL
    // ========================================================

    uint64_t intervalLost =
    intervalFailures;

    uint64_t intervalAttempts =
        intervalSuccessful +
        intervalLost;

    if (intervalAttempts > 0)
    {
        m_packetLoss =
            static_cast<float>(
                static_cast<double>(intervalLost) /
                static_cast<double>(intervalAttempts));
    }
    else
    {
        m_packetLoss = 0.0f;
    }

    // ========================================================
    // 6. REAL END-TO-END LATENCY
    // ========================================================

    uint64_t currentLatencySamples =
        latencySamples;

    double currentLatencyTotal =
        latencyTotalSeconds;

    uint64_t intervalLatencySamples =
        currentLatencySamples -
        m_previousLatencySamples;

    double intervalLatencyTotal =
        currentLatencyTotal -
        m_previousLatencyTotal;

    m_previousLatencySamples =
        currentLatencySamples;

    m_previousLatencyTotal =
        currentLatencyTotal;

    if (intervalLatencySamples > 0)
    {
        m_latencyMs =
            static_cast<float>(
                (intervalLatencyTotal /
                 static_cast<double>(intervalLatencySamples))
                * 1000.0);
    }
    else
    {
        m_latencyMs = 0.0f;
    }

    // ========================================================
    // 7. REAL CURRENT CONTENTION WINDOW
    // ========================================================

    if (m_txopA)
{
    uint32_t actualCw =
        m_txopA->GetMinCw();

    if (actualCw < CW_MIN_LIMIT)
    {
        actualCw = CW_MIN_LIMIT;
        m_txopA->SetMinCw(actualCw);
    }

    m_currentCw =
        static_cast<float>(actualCw);
}
    // ========================================================
    // 8. REAL RL REWARD
    //
    // Positive:
    //   successful transmission
    //
    // Negative:
    //   packet loss
    //   latency
    //   MAC failures
    //   queue pressure
    // ========================================================

    m_reward = 0.0f;

    // Reward successful throughput
    m_reward +=
        0.001f *
        m_successfulTransmissionRate;

    // Penalize packet loss
    m_reward -=
        10.0f *
        m_packetLoss;

    // Penalize latency
    m_reward -=
        0.01f *
        m_latencyMs;

    // Penalize MAC failures
    m_reward -=
        0.01f *
        m_macFailures;

    // Penalize growing queues
    float queuePressure =
        m_queueLengthA +
        m_queueLengthB;

    m_reward -=
        0.001f *
        queuePressure;

    // ========================================================
    // 9. PRINT REAL STATE
    // ========================================================

    std::cout
        << "[RL-STATE] t="
        << Simulator::Now().GetSeconds()
        << " s"
        << " | Q_A="
        << m_queueLengthA
        << " | Q_B="
        << m_queueLengthB
        << " | dQ_A="
        << m_queueGrowthA
        << " | dQ_B="
        << m_queueGrowthB
        << " | Loss="
        << m_packetLoss
        << " | MACFail="
        << m_macFailures
        << " | CW="
        << m_currentCw
        << " | SuccessRate="
        << m_successfulTransmissionRate
        << " | Latency="
        << m_latencyMs
        << " ms"
        << " | Reward="
        << m_reward
        << std::endl;
}

// ============================================================
// RL DECISION STEP
// ============================================================

void
WifiAiDcfEnv::DecisionStep()
{
    static uint64_t rlStep = 0;

    if (Simulator::Now().GetSeconds() >=
        SIMULATION_TIME)
    {
        return;
    }

    ++rlStep;

    std::cout
        << "[RL-STEP] step="
        << rlStep
        << " | t="
        << Simulator::Now().GetSeconds()
        << " | waiting for Python action"
        << std::endl;

    UpdateState();

    // Normal RL step.
    // Do NOT mark the environment as done here.
    Notify();

    if (Simulator::Now().GetSeconds() +
            RL_INTERVAL <
        SIMULATION_TIME)
    {
        Simulator::Schedule(
            Seconds(RL_INTERVAL),
            &WifiAiDcfEnv::DecisionStep,
            this);
    }
}

// ============================================================
// START AI ENVIRONMENT
// ============================================================
void
WifiAiDcfEnv::Start()
{
    uint32_t initialCw = CW_MIN_LIMIT;

    if (m_txopA)
    {
        initialCw = m_txopA->GetMinCw();

        // Safety: never expose an invalid zero CW.
        if (initialCw < CW_MIN_LIMIT)
        {
            initialCw = CW_MIN_LIMIT;
            m_txopA->SetMinCw(initialCw);
        }
    }

    if (m_txopB)
    {
        m_txopB->SetMinCw(initialCw);
    }

    m_currentCw =
        static_cast<float>(initialCw);

    std::cout
        << "[INITIAL-DATA]"
        << " Real DCF CW = "
        << initialCw
        << std::endl;

    Simulator::Schedule(
        Seconds(measurementStartTime),
        &WifiAiDcfEnv::DecisionStep,
        this);
}
// ============================================================
// MAIN
// ============================================================

int
main(int argc, char* argv[])
{
    uint32_t scenario = 1;
    uint32_t runNumber = 1;

    CommandLine cmd(__FILE__);

    cmd.AddValue(
        "scenario",
        "Scenario number: 1 to 40",
        scenario);

    cmd.AddValue(
        "run",
        "Random run number",
        runNumber);

    cmd.Parse(argc, argv);

    if (scenario < 1 ||
    scenario > 40)
{
    std::cerr
        << "Scenario must be between 1 and 40."
        << std::endl;

    return 1;
}

    // ========================================================
    // RANDOMNESS
    // ========================================================

    RngSeedManager::SetSeed(
        12345);

    RngSeedManager::SetRun(
        runNumber);

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
    // WIFI
    // ========================================================

    WifiHelper wifi;

    wifi.SetStandard(WIFI_STANDARD_80211a);

    WifiMacHelper mac;

    Ssid ssid =
        Ssid("AI-WIFI-NETWORK");

    // ========================================================
    // STA A + STA B
    //
    // QosSupported=false -> DCF/non-QoS.
    // ========================================================

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

    mobility.Install(
        staNodes);

    mobility.Install(
        apNode);

    apNode.Get(0)
        ->GetObject<MobilityModel>()
        ->SetPosition(
            Vector(
                0.0,
                0.0,
                0.0));

    staNodes.Get(0)
        ->GetObject<MobilityModel>()
        ->SetPosition(
            Vector(
                5.0,
                0.0,
                0.0));

    staNodes.Get(1)
        ->GetObject<MobilityModel>()
        ->SetPosition(
            Vector(
                -5.0,
                0.0,
                0.0));

    // ========================================================
    // INTERNET
    // ========================================================

    InternetStackHelper internet;

    internet.Install(
        staNodes);

    internet.Install(
        apNode);

    // ========================================================
    // IP
    // ========================================================

    Ipv4AddressHelper ipv4;

    ipv4.SetBase(
        "192.168.1.0",
        "255.255.255.0");

    Ipv4InterfaceContainer staInterfaces =
        ipv4.Assign(
            staDevices);

    Ipv4InterfaceContainer apInterfaces =
        ipv4.Assign(
            apDevice);

    Ipv4Address apAddress =
        apInterfaces.GetAddress(0);

    // ========================================================
    // SCENARIO
    // ========================================================

    TrafficConfig trafficA;
    TrafficConfig trafficB;

        if (scenario == 1)
    {
        trafficA = {2 * 1000 * 1000, "2Mbps", 1.0};
        trafficB = {2 * 1000 * 1000, "2Mbps", 5.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 2)
    {
        trafficA = {5 * 1000 * 1000, "10Mbps", 1.0};
        trafficB = {5 * 1000 * 1000, "10Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 3)
    {
        trafficA = {4 * 1000 * 1000, "2Mbps", 1.0};
        trafficB = {12 * 1000 * 1000, "20Mbps", 3.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 4)
    {
        trafficA = {20 * 1000 * 1000, "20Mbps", 1.0};
        trafficB = {20 * 1000 * 1000, "20Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 5)
    {
        trafficA = {50 * 1000 * 1000, "40Mbps", 1.0};
        trafficB = {50 * 1000 * 1000, "40Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 6)
    {
        trafficA = {1 * 1000 * 1000, "1Mbps", 1.0};
        trafficB = {1 * 1000 * 1000, "1Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 7)
    {
        trafficA = {2 * 1000 * 1000, "2Mbps", 1.0};
        trafficB = {5 * 1000 * 1000, "5Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 8)
    {
        trafficA = {5 * 1000 * 1000, "5Mbps", 1.0};
        trafficB = {2 * 1000 * 1000, "2Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 9)
    {
        trafficA = {5 * 1000 * 1000, "5Mbps", 1.0};
        trafficB = {5 * 1000 * 1000, "5Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 10)
    {
        trafficA = {8 * 1000 * 1000, "8Mbps", 1.0};
        trafficB = {8 * 1000 * 1000, "8Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 11)
    {
        trafficA = {10 * 1000 * 1000, "10Mbps", 1.0};
        trafficB = {5 * 1000 * 1000, "5Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 12)
    {
        trafficA = {5 * 1000 * 1000, "5Mbps", 1.0};
        trafficB = {10 * 1000 * 1000, "10Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 13)
    {
        trafficA = {15 * 1000 * 1000, "15Mbps", 1.0};
        trafficB = {15 * 1000 * 1000, "15Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 14)
    {
        trafficA = {20 * 1000 * 1000, "20Mbps", 1.0};
        trafficB = {10 * 1000 * 1000, "10Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 15)
    {
        trafficA = {10 * 1000 * 1000, "10Mbps", 1.0};
        trafficB = {20 * 1000 * 1000, "20Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 16)
    {
        trafficA = {25 * 1000 * 1000, "25Mbps", 1.0};
        trafficB = {25 * 1000 * 1000, "25Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 17)
    {
        trafficA = {30 * 1000 * 1000, "30Mbps", 1.0};
        trafficB = {30 * 1000 * 1000, "30Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 18)
    {
        trafficA = {40 * 1000 * 1000, "40Mbps", 1.0};
        trafficB = {20 * 1000 * 1000, "20Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 19)
    {
        trafficA = {20 * 1000 * 1000, "20Mbps", 1.0};
        trafficB = {40 * 1000 * 1000, "40Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 20)
    {
        trafficA = {50 * 1000 * 1000, "50Mbps", 1.0};
        trafficB = {50 * 1000 * 1000, "50Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 21)
    {
        trafficA = {2 * 1000 * 1000, "2Mbps", 1.0};
        trafficB = {10 * 1000 * 1000, "10Mbps", 3.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 22)
    {
        trafficA = {10 * 1000 * 1000, "10Mbps", 1.0};
        trafficB = {2 * 1000 * 1000, "2Mbps", 3.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 23)
    {
        trafficA = {5 * 1000 * 1000, "5Mbps", 1.0};
        trafficB = {20 * 1000 * 1000, "20Mbps", 5.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 24)
    {
        trafficA = {20 * 1000 * 1000, "20Mbps", 1.0};
        trafficB = {5 * 1000 * 1000, "5Mbps", 5.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 25)
    {
        trafficA = {10 * 1000 * 1000, "10Mbps", 1.0};
        trafficB = {10 * 1000 * 1000, "10Mbps", 5.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 26)
    {
        trafficA = {20 * 1000 * 1000, "20Mbps", 1.0};
        trafficB = {20 * 1000 * 1000, "20Mbps", 5.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 27)
    {
        trafficA = {30 * 1000 * 1000, "30Mbps", 1.0};
        trafficB = {10 * 1000 * 1000, "10Mbps", 5.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 28)
    {
        trafficA = {10 * 1000 * 1000, "10Mbps", 1.0};
        trafficB = {30 * 1000 * 1000, "30Mbps", 5.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 29)
    {
        trafficA = {40 * 1000 * 1000, "40Mbps", 1.0};
        trafficB = {10 * 1000 * 1000, "10Mbps", 5.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 30)
    {
        trafficA = {10 * 1000 * 1000, "10Mbps", 1.0};
        trafficB = {40 * 1000 * 1000, "40Mbps", 5.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 31)
    {
        trafficA = {2 * 1000 * 1000, "2Mbps", 1.0};
        trafficB = {20 * 1000 * 1000, "20Mbps", 8.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 32)
    {
        trafficA = {20 * 1000 * 1000, "20Mbps", 1.0};
        trafficB = {2 * 1000 * 1000, "2Mbps", 8.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 33)
    {
        trafficA = {5 * 1000 * 1000, "5Mbps", 1.0};
        trafficB = {30 * 1000 * 1000, "30Mbps", 8.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 34)
    {
        trafficA = {30 * 1000 * 1000, "30Mbps", 1.0};
        trafficB = {5 * 1000 * 1000, "5Mbps", 8.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 35)
    {
        trafficA = {20 * 1000 * 1000, "20Mbps", 1.0};
        trafficB = {40 * 1000 * 1000, "40Mbps", 8.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 36)
    {
        trafficA = {40 * 1000 * 1000, "40Mbps", 1.0};
        trafficB = {20 * 1000 * 1000, "20Mbps", 8.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 37)
    {
        trafficA = {50 * 1000 * 1000, "50Mbps", 1.0};
        trafficB = {50 * 1000 * 1000, "50Mbps", 5.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 38)
    {
        trafficA = {60 * 1000 * 1000, "60Mbps", 1.0};
        trafficB = {60 * 1000 * 1000, "60Mbps", 1.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 39)
    {
        trafficA = {60 * 1000 * 1000, "60Mbps", 1.0};
        trafficB = {30 * 1000 * 1000, "30Mbps", 5.0};
        measurementStartTime = 1.0;
    }
    else if (scenario == 40)
    {
        trafficA = {30 * 1000 * 1000, "30Mbps", 1.0};
        trafficB = {60 * 1000 * 1000, "60Mbps", 5.0};
        measurementStartTime = 1.0;
    }

    // ========================================================
    // PRINT CONFIGURATION
    // ========================================================

    std::cout
        << std::endl
        << "=================================================="
        << std::endl
        << "             WIFI AI - RL / DCF"
        << std::endl
        << "=================================================="
        << std::endl
        << "Scenario        : "
        << scenario
        << std::endl
        << "Random Run      : "
        << runNumber
        << std::endl
        << "Packet Size     : "
        << PACKET_SIZE
        << " bytes"
        << std::endl
        << "Simulation Time : "
        << SIMULATION_TIME
        << " s"
        << std::endl
        << "RL interval     : "
        << RL_INTERVAL
        << " s"
        << std::endl
        << std::endl;

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
        sinkA.Install(
            apNode.Get(0));

    ApplicationContainer sinkAppB =
        sinkB.Install(
            apNode.Get(0));

    sinkAppA.Start(
        Seconds(0.5));

    sinkAppB.Start(
        Seconds(0.5));

    // ========================================================
    // TRAFFIC
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
    // ========================================================

    if (scenario == 5)
    {
        TrafficConfig secondBurst =
            {
                10 * 1000 * 1000,
                "10Mbps",
                6.0
            };

        InstallTraffic(
            staNodes.Get(1),
            apAddress,
            portB,
            secondBurst);

        std::cout
            << "STA B second burst: "
            << "10 MB, 10Mbps, 1200 B packets, start 6 s"
            << std::endl;
    }

    // ========================================================
    // GET REAL WIFI MACS
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

    // ========================================================
    // GET THE ACTUAL LEGACY DCF TXOPS AND THEIR QUEUES
    // ========================================================

    Ptr<Txop> txopA =
        macA->GetTxop();

    Ptr<Txop> txopB =
        macB->GetTxop();

    if (!txopA || !txopB)
    {
        std::cerr
            << "[DCF] ERROR: Real DCF Txop unavailable"
            << std::endl;

        return 1;
    }

    Ptr<WifiMacQueue> queueA =
        txopA->GetWifiMacQueue();

    Ptr<WifiMacQueue> queueB =
        txopB->GetWifiMacQueue();

    if (!queueA || !queueB)
    {
        std::cerr
            << "[DCF] ERROR: Real DCF queue unavailable"
            << std::endl;

        return 1;
    }

    std::cout
        << "[DCF] Real DCF Txop + queues acquired."
        << std::endl;

    // ========================================================
    // QUEUE TRACES
    // ========================================================

    if (queueA)
    {
        queueA->TraceConnectWithoutContext(
            "Enqueue",
            MakeCallback(
                &QueueEnqueue));

        queueA->TraceConnectWithoutContext(
            "Dequeue",
            MakeCallback(
                &QueueDequeue));
    }

    if (queueB)
    {
        queueB->TraceConnectWithoutContext(
            "Enqueue",
            MakeCallback(
                &QueueEnqueue));

        queueB->TraceConnectWithoutContext(
            "Dequeue",
            MakeCallback(
                &QueueDequeue));
    }

    // ========================================================
    // REAL PHY TX OBSERVATION
    // ========================================================

    Config::Connect(
        "/NodeList/0/DeviceList/0/"
        "$ns3::WifiNetDevice/Phy/PhyTxBegin",
        MakeCallback(
            &PhyTxBeginA));

    Config::Connect(
        "/NodeList/1/DeviceList/0/"
        "$ns3::WifiNetDevice/Phy/PhyTxBegin",
        MakeCallback(
            &PhyTxBeginB));

    // ========================================================
    // REAL ACKED MPDU TRACES
    // ========================================================

    Config::ConnectWithoutContext(
        "/NodeList/0/DeviceList/0/"
        "$ns3::WifiNetDevice/Mac/AckedMpdu",
        MakeCallback(
            &AckedMpdu));

    Config::ConnectWithoutContext(
        "/NodeList/1/DeviceList/0/"
        "$ns3::WifiNetDevice/Mac/AckedMpdu",
        MakeCallback(
            &AckedMpdu));

    // ========================================================
    // REAL MAC FAILURE TRACES
    // ========================================================

    Config::Connect(
        "/NodeList/*/DeviceList/*/"
        "RemoteStationManager/MacTxDataFailed",
        MakeCallback(
            &MacDataFailed));

    Config::Connect(
        "/NodeList/*/DeviceList/*/"
        "RemoteStationManager/MacTxFinalDataFailed",
        MakeCallback(
            &MacFinalDataFailed));

    // ========================================================
    // REAL END-TO-END LATENCY TRACE
    // ========================================================

    Config::ConnectWithoutContext(
        "/NodeList/2/ApplicationList/0/"
        "$ns3::PacketSink/RxWithSeqTsSize",
        MakeCallback(
            &PacketReceivedWithTimestamp));

    Config::ConnectWithoutContext(
        "/NodeList/2/ApplicationList/1/"
        "$ns3::PacketSink/RxWithSeqTsSize",
        MakeCallback(
            &PacketReceivedWithTimestamp));

    // ========================================================
    // QUEUE MONITOR
    // ========================================================

    Simulator::Schedule(
        MilliSeconds(1),
        &MonitorQueues,
        queueA,
        queueB);

    // ========================================================
    // FLOW MONITOR
    // ========================================================

    FlowMonitorHelper flowHelper;

    Ptr<FlowMonitor> flowMonitor =
        flowHelper.InstallAll();
    // ========================================================
// CONFIGURE ns3-ai SHARED MEMORY NAMES
// Must match Python ns3ai_gym_env
// ========================================================


    // ========================================================
    // CREATE REAL AI ENVIRONMENT
    // ========================================================

    Ptr<WifiAiDcfEnv> aiEnv =
        CreateObject<WifiAiDcfEnv>(
            macA,
            macB,
            queueA,
            queueB);

    // ========================================================
    // START RL DECISION LOOP
    // ========================================================

    aiEnv->Start();

    // ========================================================
    // SIMULATION STOP
    // ========================================================

    Simulator::Stop(
        Seconds(
            SIMULATION_TIME));

    Simulator::Run();

    // ========================================================
    // FINAL FLOW RESULTS
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

    std::cout
        << std::endl
        << "=================================================="
        << std::endl
        << "                 FINAL RESULTS"
        << std::endl
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
                /
                stats.rxPackets;

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
                /
                duration;

            std::cout
                << "  Throughput : "
                << throughput / 1000000.0
                << " Mbps"
                << std::endl;
        }

        std::cout
            << std::endl;
    }

    // ========================================================
    // FINAL AGGREGATE METRICS
    // ========================================================

    double averageLatencyMs =
        0.0;

    if (totalRxPackets > 0)
    {
        averageLatencyMs =
            totalDelay.GetSeconds()
            /
            totalRxPackets
            *
            1000.0;
    }

    double packetLossPercentage =
        0.0;

    if (totalTxPackets > 0)
    {
        packetLossPercentage =
            static_cast<double>(
                totalLostPackets)
            /
            static_cast<double>(
                totalTxPackets)
            *
            100.0;
    }

    double averageQueueA =
        0.0;

    double averageQueueB =
        0.0;

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

    double averageQueueWaitMs =
        0.0;

    if (queueWaitSamples > 0)
    {
        averageQueueWaitMs =
            queueWaitTotal
            /
            queueWaitSamples
            *
            1000.0;
    }

    std::cout
        << "Scenario                    : "
        << scenario
        << std::endl;

    std::cout
        << "Random run                  : "
        << runNumber
        << std::endl;

    std::cout
        << "Total TX packets            : "
        << totalTxPackets
        << std::endl;

    std::cout
        << "Total RX packets            : "
        << totalRxPackets
        << std::endl;

    std::cout
        << "Lost packets                : "
        << totalLostPackets
        << std::endl;

    std::cout
        << "Packet loss                 : "
        << packetLossPercentage
        << " %"
        << std::endl;

    std::cout
        << "Average latency             : "
        << averageLatencyMs
        << " ms"
        << std::endl;

    std::cout
        << "Average queue A             : "
        << averageQueueA
        << " packets"
        << std::endl;

    std::cout
        << "Average queue B             : "
        << averageQueueB
        << " packets"
        << std::endl;

    std::cout
        << "Maximum queue A             : "
        << maxQueueA
        << " packets"
        << std::endl;

    std::cout
        << "Maximum queue B             : "
        << maxQueueB
        << " packets"
        << std::endl;

    std::cout
        << "Queue activity observed     : "
        << ((maxQueueA > 0 || maxQueueB > 0) ? "YES" : "NO")
        << std::endl;

    std::cout
        << "Average queue waiting time  : "
        << averageQueueWaitMs
        << " ms"
        << std::endl;

    std::cout
        << "MAC data failures           : "
        << macDataFailures
        << std::endl;

    std::cout
        << "MAC final failures          : "
        << macFinalDataFailures
        << std::endl;

    std::cout
        << "Successful MAC transmissions: "
        << successfulMacTransmissions
        << std::endl;

    std::cout
        << "Final CW                    : "
        << aiEnv->GetExtraInfo()["currentCW"]
        << std::endl;

    std::cout
        << "=================================================="
        << std::endl;

    // ========================================================
    // SAVE RESULTS
    // ========================================================

    std::ofstream csv(
        "wifi_ai_dcf_results.csv",
        std::ios::app);

    csv.seekp(
        0,
        std::ios::end);

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
            << "max_queue_a,"
            << "max_queue_b,"
            << "queue_activity_observed,"
            << "average_queue_wait_ms,"
            << "mac_data_failures,"
            << "mac_final_failures,"
            << "successful_mac_transmissions,"
            << "final_cw"
            << "\n";
    }

    csv
        << scenario
        << ","
        << runNumber
        << ","
        << totalTxPackets
        << ","
        << totalRxPackets
        << ","
        << totalLostPackets
        << ","
        << packetLossPercentage
        << ","
        << averageLatencyMs
        << ","
        << averageQueueA
        << ","
        << averageQueueB
        << ","
        << maxQueueA
        << ","
        << maxQueueB
        << ","
        << ((maxQueueA > 0 || maxQueueB > 0) ? 1 : 0)
        << ","
        << averageQueueWaitMs
        << ","
        << macDataFailures
        << ","
        << macFinalDataFailures
        << ","
        << successfulMacTransmissions
        << ","
        << aiEnv->GetExtraInfo()["currentCW"]
        << "\n";

    csv.close();

    // ========================================================
    // CLEAN UP NS-3 BEFORE TELLING PYTHON WE ARE FINISHED
    // ========================================================

    

    // ========================================================
    // THIS MUST BE THE FINAL NS3-AI OPERATION
    // ========================================================
    std::cout << "[DEBUG] Before NotifySimulationEnd()" << std::endl;

    aiEnv->NotifySimulationEnd();

    std::cout << "[DEBUG] After NotifySimulationEnd()" << std::endl;

    Simulator::Destroy();

    std::cout << "[DEBUG] After Simulator::Destroy()" << std::endl;
        
    return 0;
}
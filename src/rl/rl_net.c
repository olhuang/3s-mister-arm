#include "rl/rl_net.h"
#include "rl/rl_session.h"

#include <SDL3/SDL.h>

#include <errno.h>
#include <inttypes.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>

#if !defined(_WIN32)
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <unistd.h>
#endif

#define RL_NET_PROBE_SAMPLE_CAP 128u
#define RL_NET_HELLO_INTERVAL_FRAMES 30u
#define RL_NET_PING_INTERVAL_FRAMES 10u
#define RL_NET_PACKET_VERSION 1u
#define RL_NET_TRANSITION_QUEUE_CAP 8u
#define RL_NET_TRANSITION_CONNECT_TIMEOUT_MS 2000
#define RL_NET_TRANSITION_IO_TIMEOUT_MS 2000

typedef enum RLNetPacketType {
    RL_NET_PACKET_HELLO = 1,
    RL_NET_PACKET_ACK = 2,
    RL_NET_PACKET_PING = 3,
    RL_NET_PACKET_PONG = 4,
} RLNetPacketType;

#if defined(__GNUC__) || defined(__clang__)
#define RL_PACKED __attribute__((packed))
#else
#define RL_PACKED
#endif

typedef struct RL_PACKED RLNetProbePacket {
    u32 magic;
    u16 packet_version;
    u16 packet_type;
    u64 session_nonce;
    u32 sequence;
    u32 config_hash;
    u64 send_time_us;
} RLNetProbePacket;

#undef RL_PACKED

static RLNetState rl_net_state;
static u32 probe_samples_us[RL_NET_PROBE_SAMPLE_CAP];
static u32 probe_sample_count;
static u32 tick_counter;
static SDL_Mutex* transition_queue_mutex;
static SDL_Thread* transition_sender_thread;
static bool transition_sender_thread_running;

typedef struct RLTransitionBatchQueueEntry {
    bool valid;
    u64 session_nonce;
    u64 run_id;
    u32 episode_id;
    u32 payload_len;
    u32 row_count;
    char* payload;
} RLTransitionBatchQueueEntry;

static RLTransitionBatchQueueEntry transition_queue[RL_NET_TRANSITION_QUEUE_CAP];
static char transition_remote_ip[128];
static int transition_remote_port;

#if !defined(_WIN32)
static int probe_socket = -1;
static int action_socket = -1;
#endif

static u64 now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ((u64)ts.tv_sec * 1000000ull) + ((u64)ts.tv_nsec / 1000ull);
}

static u64 make_session_nonce(void) {
    u64 nonce = now_us();
#if !defined(_WIN32)
    nonce ^= ((u64)getpid() << 32);
#endif
    return nonce ^ 0x33524C4147454E54ull;
}

static void reset_runtime_state(void) {
    memset(&rl_net_state, 0, sizeof(rl_net_state));
    memset(probe_samples_us, 0, sizeof(probe_samples_us));
    memset(transition_queue, 0, sizeof(transition_queue));
    SDL_zeroa(transition_remote_ip);
    transition_remote_port = 0;
    probe_sample_count = 0;
    tick_counter = 0;
    rl_net_state.config = RLProtocol_DefaultConfig();
}

void RLNet_InitDisabled(void) {
    RLNet_Shutdown();
    reset_runtime_state();
}

#if !defined(_WIN32)
static bool set_socket_nonblocking(int fd) {
    const int flags = fcntl(fd, F_GETFL, 0);
    if (flags < 0) {
        return false;
    }
    return fcntl(fd, F_SETFL, flags | O_NONBLOCK) == 0;
}

static bool open_connected_udp_socket(const char* remote_ip, int remote_port, int* out_socket) {
    char port_buf[16];
    struct addrinfo hints;
    struct addrinfo* result = NULL;
    struct addrinfo* cursor = NULL;
    int fd = -1;

    snprintf(port_buf, sizeof(port_buf), "%d", remote_port);
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_DGRAM;

    if (getaddrinfo(remote_ip, port_buf, &hints, &result) != 0) {
        return false;
    }

    for (cursor = result; cursor != NULL; cursor = cursor->ai_next) {
        fd = socket(cursor->ai_family, cursor->ai_socktype, cursor->ai_protocol);
        if (fd < 0) {
            continue;
        }
        if (connect(fd, cursor->ai_addr, cursor->ai_addrlen) == 0 && set_socket_nonblocking(fd)) {
            *out_socket = fd;
            freeaddrinfo(result);
            return true;
        }
        close(fd);
        fd = -1;
    }

    freeaddrinfo(result);
    return false;
}

static bool open_bound_udp_socket(int local_port, int* out_socket) {
    struct sockaddr_in addr;
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        return false;
    }
    if (!set_socket_nonblocking(fd)) {
        close(fd);
        return false;
    }
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons((uint16_t)local_port);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(fd, (const struct sockaddr*)&addr, sizeof(addr)) != 0) {
        close(fd);
        return false;
    }
    *out_socket = fd;
    return true;
}

static bool open_connected_tcp_socket(const char* remote_ip, int remote_port, int* out_socket) {
    char port_buf[16];
    struct addrinfo hints;
    struct addrinfo* result = NULL;
    struct addrinfo* cursor = NULL;
    int fd = -1;

    snprintf(port_buf, sizeof(port_buf), "%d", remote_port);
    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    if (getaddrinfo(remote_ip, port_buf, &hints, &result) != 0) {
        return false;
    }

    for (cursor = result; cursor != NULL; cursor = cursor->ai_next) {
        struct timeval timeout;
        fd = socket(cursor->ai_family, cursor->ai_socktype, cursor->ai_protocol);
        if (fd < 0) {
            continue;
        }
        timeout.tv_sec = RL_NET_TRANSITION_IO_TIMEOUT_MS / 1000;
        timeout.tv_usec = (RL_NET_TRANSITION_IO_TIMEOUT_MS % 1000) * 1000;
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &timeout, sizeof(timeout));
        setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        if (connect(fd, cursor->ai_addr, cursor->ai_addrlen) == 0) {
            *out_socket = fd;
            freeaddrinfo(result);
            return true;
        }
        close(fd);
        fd = -1;
    }

    freeaddrinfo(result);
    return false;
}
#endif

static void RLNet_FreeTransitionQueueEntry(RLTransitionBatchQueueEntry* entry) {
    if (entry == NULL) {
        return;
    }
    SDL_free(entry->payload);
    memset(entry, 0, sizeof(*entry));
}

static void RLNet_EnsureTransitionQueueMutex(void) {
    if (transition_queue_mutex == NULL) {
        transition_queue_mutex = SDL_CreateMutex();
    }
}

static bool RLNet_PopQueuedTransitionBatch(RLTransitionBatchQueueEntry* out_entry) {
    bool found = false;

    RLNet_EnsureTransitionQueueMutex();
    if (transition_queue_mutex == NULL || out_entry == NULL) {
        return false;
    }

    SDL_LockMutex(transition_queue_mutex);
    for (u32 i = 0; i < RL_NET_TRANSITION_QUEUE_CAP; i++) {
        if (!transition_queue[i].valid) {
            continue;
        }
        *out_entry = transition_queue[i];
        memset(&transition_queue[i], 0, sizeof(transition_queue[i]));
        found = true;
        break;
    }
    SDL_UnlockMutex(transition_queue_mutex);
    return found;
}

#if !defined(_WIN32)
static bool RLNet_SendAll(int fd, const void* data, size_t len) {
    const char* cursor = (const char*)data;
    size_t remaining = len;
    while (remaining > 0) {
        const ssize_t sent = send(fd, cursor, remaining, 0);
        if (sent <= 0) {
            return false;
        }
        cursor += sent;
        remaining -= (size_t)sent;
    }
    return true;
}

static bool RLNet_RecvAll(int fd, void* data, size_t len) {
    char* cursor = (char*)data;
    size_t remaining = len;
    while (remaining > 0) {
        const ssize_t received = recv(fd, cursor, remaining, 0);
        if (received <= 0) {
            return false;
        }
        cursor += received;
        remaining -= (size_t)received;
    }
    return true;
}

static bool RLNet_SendTransitionBatchBlocking(const RLTransitionBatchQueueEntry* entry) {
    int fd = -1;
    RLTransitionBatchHeader header;
    RLTransitionBatchAck ack;

    if (entry == NULL || entry->payload == NULL || transition_remote_ip[0] == '\0' || transition_remote_port <= 0) {
        return false;
    }
    if (!open_connected_tcp_socket(transition_remote_ip, transition_remote_port, &fd)) {
        return false;
    }

    memset(&header, 0, sizeof(header));
    header.magic = RL_PROTOCOL_MAGIC;
    header.version = RL_PROTOCOL_VERSION;
    header.packet_type = RL_TRANSITION_BATCH_PACKET_TYPE_V1;
    header.session_nonce = entry->session_nonce;
    header.run_id = entry->run_id;
    header.episode_id = entry->episode_id;
    header.payload_len = entry->payload_len;
    header.row_count = entry->row_count;

    const bool ok = RLNet_SendAll(fd, &header, sizeof(header)) &&
                    RLNet_SendAll(fd, entry->payload, entry->payload_len) &&
                    RLNet_RecvAll(fd, &ack, sizeof(ack)) &&
                    ack.magic == RL_PROTOCOL_MAGIC && ack.version == RL_PROTOCOL_VERSION &&
                    ack.packet_type == RL_TRANSITION_BATCH_ACK_PACKET_TYPE_V1 &&
                    ack.session_nonce == entry->session_nonce && ack.run_id == entry->run_id &&
                    ack.episode_id == entry->episode_id &&
                    ack.status == 0;
    close(fd);
    return ok;
}
#endif

static int RLNet_TransitionSenderThreadMain(void* userdata) {
    (void)userdata;
    for (;;) {
        RLTransitionBatchQueueEntry entry;
        memset(&entry, 0, sizeof(entry));
        if (!RLNet_PopQueuedTransitionBatch(&entry)) {
            break;
        }
#if !defined(_WIN32)
        if (RLNet_SendTransitionBatchBlocking(&entry)) {
            rl_net_state.transition_batch_sent_count++;
            rl_net_state.transition_batch_ack_count++;
        } else {
            rl_net_state.transition_batch_failed_count++;
        }
#else
        rl_net_state.transition_batch_failed_count++;
#endif
        RLNet_FreeTransitionQueueEntry(&entry);
    }
    transition_sender_thread_running = false;
    return 0;
}

static void RLNet_MaybeStartTransitionSenderThread(void) {
    RLNet_EnsureTransitionQueueMutex();
    if (transition_queue_mutex == NULL || transition_sender_thread_running) {
        return;
    }
    transition_sender_thread = SDL_CreateThread(RLNet_TransitionSenderThreadMain, "rl-transition-sender", NULL);
    if (transition_sender_thread != NULL) {
        transition_sender_thread_running = true;
    }
}

void RLNet_Init(const RemoteRLAgentConfiguration* config) {
    RLNet_InitDisabled();

    if (config == NULL || !config->enabled || !config->network_enabled || config->remote_ip == NULL ||
        config->remote_ip[0] == '\0' || config->obs_port <= 0) {
        return;
    }
    if (config->obs_port > 65535 || config->action_port < 0 || config->action_port > 65535 ||
        config->decision_interval_frames <= 0 ||
        config->decision_interval_frames > 30 || config->action_hold_frames <= 0 ||
        config->action_hold_frames > 30 || config->delay_frames < 0 || config->delay_frames > 30) {
        rl_net_state.last_error_count++;
        SDL_Log("RL net probe disabled by invalid timing/port config");
        return;
    }

    rl_net_state.enabled = true;
    rl_net_state.session_nonce = make_session_nonce();
    rl_net_state.config.decision_interval_frames = (u8)config->decision_interval_frames;
    rl_net_state.config.action_hold_frames = (u8)config->action_hold_frames;
    rl_net_state.config.candidate_k_delay_frames = (u8)config->delay_frames;
    rl_net_state.config.config_hash = RLProtocol_ComputeConfigHash(&rl_net_state.config);
    SDL_strlcpy(transition_remote_ip, config->remote_ip, sizeof(transition_remote_ip));
    transition_remote_port = config->obs_port + 2;

#if !defined(_WIN32)
    if (open_connected_udp_socket(config->remote_ip, config->obs_port, &probe_socket)) {
        rl_net_state.socket_open = true;
        rl_net_state.probe_ready = true;
        SDL_Log("RL net probe enabled: remote=%s obs_port=%d action_port=%d nonce=%" PRIu64,
                config->remote_ip,
                config->obs_port,
                config->action_port,
                rl_net_state.session_nonce);
        if (open_bound_udp_socket(config->action_port, &action_socket)) {
            rl_net_state.action_socket_open = true;
        } else {
            rl_net_state.last_error_count++;
            SDL_Log("RL action socket failed to bind: action_port=%d errno=%d", config->action_port, errno);
        }
    } else {
        rl_net_state.last_error_count++;
        SDL_Log("RL net probe failed to open UDP socket: remote=%s obs_port=%d errno=%d",
                config->remote_ip,
                config->obs_port,
                errno);
    }
#else
    rl_net_state.last_error_count++;
#endif
}

static bool send_packet(RLNetPacketType type, u32 sequence) {
    RLNetProbePacket packet;

    if (!rl_net_state.socket_open) {
        return false;
    }

    memset(&packet, 0, sizeof(packet));
    packet.magic = RL_PROTOCOL_MAGIC;
    packet.packet_version = RL_NET_PACKET_VERSION;
    packet.packet_type = (u16)type;
    packet.session_nonce = rl_net_state.session_nonce;
    packet.sequence = sequence;
    packet.config_hash = rl_net_state.config.config_hash;
    packet.send_time_us = now_us();

#if !defined(_WIN32)
    const ssize_t sent = send(probe_socket, &packet, sizeof(packet), 0);
    if (sent == (ssize_t)sizeof(packet)) {
        rl_net_state.sent_count++;
        return true;
    }
    if (errno != EAGAIN && errno != EWOULDBLOCK) {
        rl_net_state.last_error_count++;
    }
#endif
    return false;
}

static void sort_samples(const u32* src, u32 count, u32* dst) {
    for (u32 i = 0; i < count; i++) {
        u32 j = i;
        dst[i] = src[i];
        while (j > 0 && dst[j - 1] > dst[j]) {
            const u32 tmp = dst[j - 1];
            dst[j - 1] = dst[j];
            dst[j] = tmp;
            j--;
        }
    }
}

static void record_probe_sample(u32 sample_us) {
    u32 sorted[RL_NET_PROBE_SAMPLE_CAP];
    probe_samples_us[probe_sample_count % RL_NET_PROBE_SAMPLE_CAP] = sample_us;
    if (probe_sample_count < RL_NET_PROBE_SAMPLE_CAP) {
        probe_sample_count++;
    }
    sort_samples(probe_samples_us, probe_sample_count, sorted);
    RLProtocol_ProbeStatsFromSortedSamples(sorted, probe_sample_count, &rl_net_state.probe_stats);
}

static void handle_packet(const RLNetProbePacket* packet) {
    const u64 receive_time_us = now_us();

    if (packet->magic != RL_PROTOCOL_MAGIC || packet->packet_version != RL_NET_PACKET_VERSION ||
        packet->session_nonce != rl_net_state.session_nonce) {
        return;
    }

    if (packet->packet_type == RL_NET_PACKET_ACK) {
        if (packet->config_hash == rl_net_state.config.config_hash) {
            rl_net_state.handshake_accepted = true;
        }
        return;
    }

    if (packet->packet_type == RL_NET_PACKET_PONG && rl_net_state.handshake_accepted &&
        packet->send_time_us <= receive_time_us) {
        const u64 rtt_us = receive_time_us - packet->send_time_us;
        record_probe_sample((rtt_us > UINT32_MAX) ? UINT32_MAX : (u32)rtt_us);
    }
}

static void handle_action_packet(const RLActionPacket* packet) {
    rl_net_state.action_received_count++;

    if (packet->magic != RL_PROTOCOL_MAGIC || packet->version != RL_PROTOCOL_VERSION) {
        rl_net_state.action_rejected_version_count++;
        return;
    }
    if (!rl_net_state.handshake_accepted) {
        rl_net_state.action_rejected_unacked_count++;
        return;
    }
    if (packet->session_nonce != rl_net_state.session_nonce) {
        rl_net_state.action_rejected_nonce_count++;
        return;
    }

    rl_net_state.action_accepted_count++;
    switch (RLSession_SubmitRemoteAction(packet)) {
    case RL_REMOTE_ACTION_SUBMIT_LATE:
        break;
    case RL_REMOTE_ACTION_SUBMIT_DUPLICATE:
        break;
    case RL_REMOTE_ACTION_SUBMIT_TARGET_MISMATCH:
        break;
    case RL_REMOTE_ACTION_SUBMIT_ACCEPTED:
    default:
        break;
    }
}

static void receive_packets(void) {
#if !defined(_WIN32)
    while (rl_net_state.socket_open) {
        RLNetProbePacket packet;
        const ssize_t received = recv(probe_socket, &packet, sizeof(packet), 0);
        if (received == (ssize_t)sizeof(packet)) {
            rl_net_state.received_count++;
            handle_packet(&packet);
            continue;
        }
        if (received < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
            rl_net_state.last_error_count++;
        }
        break;
    }

    while (rl_net_state.action_socket_open) {
        RLActionPacket packet;
        const ssize_t received = recv(action_socket, &packet, sizeof(packet), 0);
        if (received == (ssize_t)sizeof(packet)) {
            handle_action_packet(&packet);
            continue;
        }
        if (received > 0) {
            rl_net_state.action_rejected_malformed_count++;
            continue;
        }
        if (received < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
            rl_net_state.last_error_count++;
        }
        break;
    }
#endif
}

void RLNet_Tick(void) {
    if (!rl_net_state.enabled || !rl_net_state.socket_open) {
        return;
    }

    receive_packets();

    if (!rl_net_state.handshake_accepted) {
        if ((tick_counter % RL_NET_HELLO_INTERVAL_FRAMES) == 0) {
            send_packet(RL_NET_PACKET_HELLO, rl_net_state.probe_sequence);
        }
    } else if ((tick_counter % RL_NET_PING_INTERVAL_FRAMES) == 0) {
        rl_net_state.probe_sequence++;
        send_packet(RL_NET_PACKET_PING, rl_net_state.probe_sequence);
    }

    tick_counter++;
}

void RLNet_Shutdown(void) {
#if !defined(_WIN32)
    if (probe_socket >= 0) {
        close(probe_socket);
        probe_socket = -1;
    }
    if (action_socket >= 0) {
        close(action_socket);
        action_socket = -1;
    }
#endif
    if (transition_sender_thread != NULL) {
        SDL_WaitThread(transition_sender_thread, NULL);
        transition_sender_thread = NULL;
    }
    rl_net_state.socket_open = false;
    rl_net_state.action_socket_open = false;
    rl_net_state.probe_ready = false;
}

const RLNetState* RLNet_GetState(void) {
    if (rl_net_state.config.protocol_version == 0) {
        reset_runtime_state();
    }
    return &rl_net_state;
}

bool RLNet_IsHandshakeAccepted(void) {
    return RLNet_GetState()->handshake_accepted;
}

bool RLNet_SendObservationHeader(const RLObsPacketHeader* header) {
    if (header == NULL || !rl_net_state.socket_open || !rl_net_state.handshake_accepted) {
        return false;
    }

#if !defined(_WIN32)
    const ssize_t sent = send(probe_socket, header, sizeof(*header), 0);
    if (sent == (ssize_t)sizeof(*header)) {
        rl_net_state.sent_count++;
        return true;
    }
    if (errno != EAGAIN && errno != EWOULDBLOCK) {
        rl_net_state.last_error_count++;
    }
#endif
    return false;
}

bool RLNet_QueueTransitionBatch(u64 run_id, u32 episode_id, const char* payload, u32 payload_len, u32 row_count) {
    bool queued = false;
    char* payload_copy = NULL;

    if (payload == NULL || payload_len == 0 || !rl_net_state.enabled || !rl_net_state.handshake_accepted ||
        transition_remote_ip[0] == '\0' || transition_remote_port <= 0) {
        return false;
    }

    payload_copy = (char*)SDL_malloc(payload_len);
    if (payload_copy == NULL) {
        rl_net_state.transition_batch_failed_count++;
        return false;
    }
    SDL_memcpy(payload_copy, payload, payload_len);

    RLNet_EnsureTransitionQueueMutex();
    if (transition_queue_mutex == NULL) {
        SDL_free(payload_copy);
        rl_net_state.transition_batch_failed_count++;
        return false;
    }

    SDL_LockMutex(transition_queue_mutex);
    for (u32 i = 0; i < RL_NET_TRANSITION_QUEUE_CAP; i++) {
        if (transition_queue[i].valid) {
            continue;
        }
        transition_queue[i].valid = true;
        transition_queue[i].session_nonce = rl_net_state.session_nonce;
        transition_queue[i].run_id = run_id;
        transition_queue[i].episode_id = episode_id;
        transition_queue[i].payload_len = payload_len;
        transition_queue[i].row_count = row_count;
        transition_queue[i].payload = payload_copy;
        queued = true;
        rl_net_state.transition_batch_queued_count++;
        break;
    }
    SDL_UnlockMutex(transition_queue_mutex);

    if (!queued) {
        SDL_free(payload_copy);
        rl_net_state.transition_batch_failed_count++;
        return false;
    }

    RLNet_MaybeStartTransitionSenderThread();
    return true;
}

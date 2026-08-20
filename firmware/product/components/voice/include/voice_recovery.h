#pragma once

#include <stdbool.h>
#include <stdint.h>

#define VOICE_RECOVERY_BACKOFF_MIN_MS 1000
#define VOICE_RECOVERY_BACKOFF_MAX_MS 60000

typedef enum {
    VOICE_FAULT_NONE = 0,
    VOICE_FAULT_WS_CLOSE,
    VOICE_FAULT_TRANSPORT,
    VOICE_FAULT_BRIDGE_GONE,
    VOICE_FAULT_GATEWAY_GONE,
    VOICE_FAULT_WIFI_LOST,
    VOICE_FAULT_UNKNOWN_CONVERSATION,
    VOICE_FAULT_SESSION_CLOSED,
    VOICE_FAULT_BACKEND_UNAVAILABLE,
    VOICE_FAULT_MALFORMED,
} voice_fault_t;

typedef struct {
    uint32_t attempt;
    uint32_t reconnects;
    uint32_t invalidations;
    uint32_t last_backoff_ms;
    voice_fault_t last_fault;
    bool conversation_valid;
    bool helloed;
    bool speaking;
    bool play_active;
    uint32_t conversation_id;
} voice_recovery_t;

void voice_recovery_init(voice_recovery_t *r);
uint32_t voice_recovery_next_backoff_ms(voice_recovery_t *r);
void voice_recovery_on_hello_ok(voice_recovery_t *r);
void voice_recovery_on_fault(voice_recovery_t *r, voice_fault_t fault);
bool voice_recovery_keeps_hello(voice_fault_t fault);
const char *voice_fault_name(voice_fault_t fault);

#include "voice_recovery.h"

#include <stddef.h>

void voice_recovery_init(voice_recovery_t *r)
{
    if (r == NULL) {
        return;
    }
    r->attempt = 0;
    r->reconnects = 0;
    r->invalidations = 0;
    r->last_backoff_ms = VOICE_RECOVERY_BACKOFF_MIN_MS;
    r->last_fault = VOICE_FAULT_NONE;
    r->conversation_valid = false;
    r->helloed = false;
    r->speaking = false;
    r->play_active = false;
    r->conversation_id = 0;
}

uint32_t voice_recovery_next_backoff_ms(voice_recovery_t *r)
{
    uint32_t delay = VOICE_RECOVERY_BACKOFF_MIN_MS;
    uint32_t attempt = 0;
    if (r != NULL) {
        attempt = r->attempt;
    }
    for (uint32_t i = 0; i < attempt; i++) {
        if (delay >= VOICE_RECOVERY_BACKOFF_MAX_MS / 2) {
            delay = VOICE_RECOVERY_BACKOFF_MAX_MS;
            break;
        }
        delay *= 2;
        if (delay > VOICE_RECOVERY_BACKOFF_MAX_MS) {
            delay = VOICE_RECOVERY_BACKOFF_MAX_MS;
            break;
        }
    }
    if (r != NULL) {
        if (r->attempt < 32) {
            r->attempt++;
        }
        r->last_backoff_ms = delay;
    }
    return delay;
}

void voice_recovery_on_hello_ok(voice_recovery_t *r)
{
    if (r == NULL) {
        return;
    }
    r->helloed = true;
    r->attempt = 0;
    r->last_backoff_ms = VOICE_RECOVERY_BACKOFF_MIN_MS;
    r->last_fault = VOICE_FAULT_NONE;
    r->reconnects++;
}

bool voice_recovery_keeps_hello(voice_fault_t fault)
{
    return fault == VOICE_FAULT_UNKNOWN_CONVERSATION ||
           fault == VOICE_FAULT_SESSION_CLOSED ||
           fault == VOICE_FAULT_BACKEND_UNAVAILABLE ||
           fault == VOICE_FAULT_MALFORMED;
}

void voice_recovery_on_fault(voice_recovery_t *r, voice_fault_t fault)
{
    if (r == NULL) {
        return;
    }
    r->last_fault = fault;
    r->speaking = false;
    r->play_active = false;
    r->conversation_valid = false;
    r->conversation_id = 0;
    r->invalidations++;
    if (!voice_recovery_keeps_hello(fault)) {
        r->helloed = false;
    }
}

const char *voice_fault_name(voice_fault_t fault)
{
    switch (fault) {
    case VOICE_FAULT_WS_CLOSE:
        return "ws_close";
    case VOICE_FAULT_TRANSPORT:
        return "transport";
    case VOICE_FAULT_BRIDGE_GONE:
        return "bridge_gone";
    case VOICE_FAULT_GATEWAY_GONE:
        return "gateway_gone";
    case VOICE_FAULT_WIFI_LOST:
        return "wifi_lost";
    case VOICE_FAULT_UNKNOWN_CONVERSATION:
        return "unknown_conversation";
    case VOICE_FAULT_SESSION_CLOSED:
        return "session_closed";
    case VOICE_FAULT_BACKEND_UNAVAILABLE:
        return "backend_unavailable";
    case VOICE_FAULT_MALFORMED:
        return "malformed";
    default:
        return "none";
    }
}

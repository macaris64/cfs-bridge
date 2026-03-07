/************************************************************************
 * CFS Bridge Application - Header
 ************************************************************************/

#ifndef BRIDGE_APP_H
#define BRIDGE_APP_H

#include "cfe.h"

/*
 * BRIDGE_APP subscribes to the same CMD MID as SAMPLE_APP (0x1882).
 * The cFS Software Bus supports fan-out delivery to multiple subscribers.
 */
#define BRIDGE_APP_LISTENER_MID  0x1882

#define BRIDGE_APP_PIPE_DEPTH    10
#define BRIDGE_APP_PIPE_NAME     "BRIDGE_CMD_PIPE"

typedef struct
{
    uint32          RunStatus;
    CFE_SB_PipeId_t CommandPipe;
} BRIDGE_APP_Data_t;

void BRIDGE_APP_Main(void);

#endif /* BRIDGE_APP_H */

/************************************************************************
 * CFS Bridge Application
 *
 * A minimal cFS application that subscribes to Command APID 0x1882
 * (SAMPLE_APP_CMD_MID) on the Software Bus and logs each received
 * packet via CFE_ES_WriteToSysLog. Demonstrates SB fan-out: both
 * SAMPLE_APP and BRIDGE_APP receive commands on the same MID.
 ************************************************************************/

#include "cfe.h"
#include "bridge_app.h"

static BRIDGE_APP_Data_t BRIDGE_APP_Data;

/* ------------------------------------------------------------------ */
/*  BRIDGE_APP_Main - Application entry point                         */
/* ------------------------------------------------------------------ */
void BRIDGE_APP_Main(void)
{
    CFE_Status_t     status;
    CFE_SB_Buffer_t *SBBufPtr;
    CFE_SB_MsgId_t   MsgId;
    CFE_MSG_FcnCode_t FcnCode;
    CFE_MSG_Size_t   MsgSize;

    memset(&BRIDGE_APP_Data, 0, sizeof(BRIDGE_APP_Data));
    BRIDGE_APP_Data.RunStatus = CFE_ES_RunStatus_APP_RUN;

    /* Register for event services (ES registration is automatic in cFS Draco+) */
    status = CFE_EVS_Register(NULL, 0, CFE_EVS_EventFilter_BINARY);
    if (status != CFE_SUCCESS)
    {
        CFE_ES_WriteToSysLog("BRIDGE_APP: Error registering events, RC=0x%08lX\n",
                             (unsigned long)status);
        BRIDGE_APP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
    }

    /* Create the Software Bus command pipe */
    if (BRIDGE_APP_Data.RunStatus == CFE_ES_RunStatus_APP_RUN)
    {
        status = CFE_SB_CreatePipe(&BRIDGE_APP_Data.CommandPipe,
                                   BRIDGE_APP_PIPE_DEPTH,
                                   BRIDGE_APP_PIPE_NAME);
        if (status != CFE_SUCCESS)
        {
            CFE_ES_WriteToSysLog("BRIDGE_APP: Error creating pipe, RC=0x%08lX\n",
                                 (unsigned long)status);
            BRIDGE_APP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
        }
    }

    /* Subscribe to SAMPLE_APP_CMD_MID (0x1882) */
    if (BRIDGE_APP_Data.RunStatus == CFE_ES_RunStatus_APP_RUN)
    {
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(BRIDGE_APP_LISTENER_MID),
                                  BRIDGE_APP_Data.CommandPipe);
        if (status != CFE_SUCCESS)
        {
            CFE_ES_WriteToSysLog("BRIDGE_APP: Error subscribing to MID 0x%04X, RC=0x%08lX\n",
                                 BRIDGE_APP_LISTENER_MID, (unsigned long)status);
            BRIDGE_APP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
        }
    }

    if (BRIDGE_APP_Data.RunStatus == CFE_ES_RunStatus_APP_RUN)
    {
        CFE_ES_WriteToSysLog("BRIDGE_APP: Initialized. Listening on MID 0x%04X\n",
                             BRIDGE_APP_LISTENER_MID);
    }

    /* ---- Main Loop ---- */
    while (CFE_ES_RunLoop(&BRIDGE_APP_Data.RunStatus) == true)
    {
        status = CFE_SB_ReceiveBuffer(&SBBufPtr,
                                      BRIDGE_APP_Data.CommandPipe,
                                      CFE_SB_PEND_FOREVER);

        if (status == CFE_SUCCESS)
        {
            CFE_MSG_GetMsgId(&SBBufPtr->Msg, &MsgId);
            CFE_MSG_GetFcnCode(&SBBufPtr->Msg, &FcnCode);
            CFE_MSG_GetSize(&SBBufPtr->Msg, &MsgSize);

            CFE_ES_WriteToSysLog(
                "BRIDGE_APP: Received MID=0x%04X FC=%u Size=%lu\n",
                (unsigned int)CFE_SB_MsgIdToValue(MsgId),
                (unsigned int)FcnCode,
                (unsigned long)MsgSize);
        }
        else
        {
            CFE_ES_WriteToSysLog("BRIDGE_APP: Pipe read error, RC=0x%08lX\n",
                                 (unsigned long)status);
            BRIDGE_APP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
        }
    }

    CFE_ES_ExitApp(BRIDGE_APP_Data.RunStatus);
}

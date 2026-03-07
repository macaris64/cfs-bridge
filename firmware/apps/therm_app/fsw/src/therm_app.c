/************************************************************************
 * NASA cFS Thermal Monitor Application
 *
 * Subscribes to thermal sensor commands (MID 0x1883) from the Python
 * Sensor Manager via CI_LAB.  Extracts the Big-Endian float payload,
 * performs FDIR checks, generates telemetry (MID 0x0883), and logs
 * a CRITICAL event when temperature exceeds 100.0 C.
 ************************************************************************/

#include "cfe.h"
#include "therm_app.h"
#include <string.h>
#include <arpa/inet.h>  /* ntohl */

/* ------------------------------------------------------------------ */
/*  Module Data                                                        */
/* ------------------------------------------------------------------ */
static THERM_APP_Data_t THERM_APP_Data;

/* ------------------------------------------------------------------ */
/*  NetworkToHostFloat - Convert Big-Endian IEEE 754 float to host     */
/* ------------------------------------------------------------------ */
static float THERM_APP_NetworkToHostFloat(const void *src)
{
    uint32_t net_val;
    uint32_t host_val;
    float    result;

    memcpy(&net_val, src, sizeof(uint32_t));
    host_val = ntohl(net_val);
    memcpy(&result, &host_val, sizeof(float));

    return result;
}

/* ------------------------------------------------------------------ */
/*  ProcessSensorData - Parse payload, run FDIR, emit telemetry        */
/* ------------------------------------------------------------------ */
static void THERM_APP_ProcessSensorData(const CFE_SB_Buffer_t *SBBufPtr)
{
    const THERM_APP_SensorCmd_t *SensorCmd;
    float                        Temperature;
    uint8                        Health;

    SensorCmd = (const THERM_APP_SensorCmd_t *)SBBufPtr;

    /* ---- Extract Big-Endian float from CCSDS payload ---- */
    Temperature = THERM_APP_NetworkToHostFloat(&SensorCmd->SensorValue);

    THERM_APP_Data.PacketCount++;

    /* Integration verification: print to cFS console */
    OS_printf("THERM_APP: [Pkt %lu] Temperature = %.2f C\n",
              (unsigned long)THERM_APP_Data.PacketCount,
              (double)Temperature);

    CFE_ES_WriteToSysLog("THERM_APP: Temperature = %.2f C (pkt %lu)\n",
                         (double)Temperature,
                         (unsigned long)THERM_APP_Data.PacketCount);

    /* ---- FDIR: Determine health status ---- */
    if (Temperature > THERM_APP_TEMP_LIMIT)
    {
        Health = THERM_APP_HEALTH_CRITICAL;
    }
    else if (Temperature > THERM_APP_TEMP_WARNING)
    {
        Health = THERM_APP_HEALTH_WARNING;
    }
    else
    {
        Health = THERM_APP_HEALTH_NOMINAL;
    }

    /* ---- FDIR: Temperature exceeds critical limit ---- */
    if (Temperature > THERM_APP_TEMP_LIMIT)
    {
        THERM_APP_Data.FdirTriggerCount++;

        OS_printf("THERM_APP: FDIR TRIGGERED - Temperature %.2f C > %.2f C limit\n",
                  (double)Temperature, (double)THERM_APP_TEMP_LIMIT);

        CFE_EVS_SendEvent(THERM_APP_FDIR_CRIT_EID,
                          CFE_EVS_EventType_CRITICAL,
                          "THERM_APP FDIR: Temperature %.1f C exceeds limit %.1f C "
                          "(trigger count: %lu)",
                          (double)Temperature,
                          (double)THERM_APP_TEMP_LIMIT,
                          (unsigned long)THERM_APP_Data.FdirTriggerCount);
    }
    else if (Temperature > THERM_APP_TEMP_WARNING)
    {
        CFE_EVS_SendEvent(THERM_APP_FDIR_WARN_EID,
                          CFE_EVS_EventType_ERROR,
                          "THERM_APP: Temperature %.1f C elevated (warn > %.1f C)",
                          (double)Temperature, (double)THERM_APP_TEMP_WARNING);
    }

    /* ---- Generate Telemetry Packet ---- */
    THERM_APP_Data.TlmPkt.ProcessedValue = Temperature;
    THERM_APP_Data.TlmPkt.HealthStatus   = Health;

    CFE_SB_TimeStampMsg((CFE_MSG_Message_t *)&THERM_APP_Data.TlmPkt);
    CFE_SB_TransmitMsg((CFE_MSG_Message_t *)&THERM_APP_Data.TlmPkt, true);

    CFE_EVS_SendEvent(THERM_APP_DATA_INF_EID,
                      CFE_EVS_EventType_INFORMATION,
                      "THERM_APP TLM: Temperature=%.2f C Health=%u",
                      (double)Temperature, (unsigned int)Health);
}

/* ------------------------------------------------------------------ */
/*  THERM_APP_Main - Application entry point                           */
/* ------------------------------------------------------------------ */
void THERM_APP_Main(void)
{
    CFE_Status_t         status;
    CFE_SB_Buffer_t     *SBBufPtr;
    CFE_SB_MsgId_t       MsgId;
    CFE_MSG_FcnCode_t    FcnCode;

    memset(&THERM_APP_Data, 0, sizeof(THERM_APP_Data));
    THERM_APP_Data.RunStatus = CFE_ES_RunStatus_APP_RUN;

    /* ---- Register for Event Services ---- */
    status = CFE_EVS_Register(NULL, 0, CFE_EVS_EventFilter_BINARY);
    if (status != CFE_SUCCESS)
    {
        CFE_ES_WriteToSysLog("THERM_APP: Error registering events, RC=0x%08lX\n",
                             (unsigned long)status);
        THERM_APP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
    }

    /* ---- Create Software Bus Pipe ---- */
    if (THERM_APP_Data.RunStatus == CFE_ES_RunStatus_APP_RUN)
    {
        status = CFE_SB_CreatePipe(&THERM_APP_Data.CommandPipe,
                                   THERM_APP_PIPE_DEPTH,
                                   THERM_APP_PIPE_NAME);
        if (status != CFE_SUCCESS)
        {
            CFE_ES_WriteToSysLog("THERM_APP: Error creating pipe, RC=0x%08lX\n",
                                 (unsigned long)status);
            THERM_APP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
        }
    }

    /* ---- Subscribe to Thermal Sensor Command MID (0x1883) ---- */
    if (THERM_APP_Data.RunStatus == CFE_ES_RunStatus_APP_RUN)
    {
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(THERM_APP_CMD_MID),
                                  THERM_APP_Data.CommandPipe);
        if (status != CFE_SUCCESS)
        {
            CFE_ES_WriteToSysLog("THERM_APP: Error subscribing to MID 0x%04X, RC=0x%08lX\n",
                                 THERM_APP_CMD_MID, (unsigned long)status);
            THERM_APP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
        }
    }

    /* ---- Initialize Telemetry Packet ---- */
    if (THERM_APP_Data.RunStatus == CFE_ES_RunStatus_APP_RUN)
    {
        CFE_MSG_Init((CFE_MSG_Message_t *)&THERM_APP_Data.TlmPkt,
                     CFE_SB_ValueToMsgId(THERM_APP_TLM_MID),
                     sizeof(THERM_APP_TlmPkt_t));

        OS_printf("THERM_APP: Initialized. Listening on CMD MID 0x%04X, TLM MID 0x%04X\n",
                  THERM_APP_CMD_MID, THERM_APP_TLM_MID);
        CFE_ES_WriteToSysLog("THERM_APP: Initialized. CMD MID=0x%04X TLM MID=0x%04X\n",
                             THERM_APP_CMD_MID, THERM_APP_TLM_MID);

        CFE_EVS_SendEvent(THERM_APP_INIT_INF_EID,
                          CFE_EVS_EventType_INFORMATION,
                          "THERM_APP Initialized: CMD=0x%04X TLM=0x%04X FDIR_LIMIT=%.1f C",
                          THERM_APP_CMD_MID, THERM_APP_TLM_MID,
                          (double)THERM_APP_TEMP_LIMIT);
    }

    /* ---- Main Loop ---- */
    while (CFE_ES_RunLoop(&THERM_APP_Data.RunStatus) == true)
    {
        /* Block until a message arrives (CFE_SB_ReceiveBuffer = Draco+ API) */
        status = CFE_SB_ReceiveBuffer(&SBBufPtr,
                                      THERM_APP_Data.CommandPipe,
                                      CFE_SB_PEND_FOREVER);

        if (status == CFE_SUCCESS)
        {
            CFE_MSG_GetMsgId(&SBBufPtr->Msg, &MsgId);
            CFE_MSG_GetFcnCode(&SBBufPtr->Msg, &FcnCode);

            if (CFE_SB_MsgIdToValue(MsgId) == THERM_APP_CMD_MID &&
                FcnCode == THERM_APP_FC_SEND_DATA)
            {
                THERM_APP_ProcessSensorData(SBBufPtr);
            }
            else
            {
                CFE_ES_WriteToSysLog(
                    "THERM_APP: Unexpected MID=0x%04X FC=%u\n",
                    (unsigned int)CFE_SB_MsgIdToValue(MsgId),
                    (unsigned int)FcnCode);
            }
        }
        else
        {
            CFE_ES_WriteToSysLog("THERM_APP: Pipe read error, RC=0x%08lX\n",
                                 (unsigned long)status);
            THERM_APP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
        }
    }

    CFE_ES_ExitApp(THERM_APP_Data.RunStatus);
}

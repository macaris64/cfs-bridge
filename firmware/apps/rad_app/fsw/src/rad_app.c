/************************************************************************
 * NASA cFS Radiation Monitor Application
 *
 * Subscribes to radiation sensor commands (MID 0x1882) from the Python
 * Sensor Manager via CI_LAB.  Extracts the Big-Endian float payload,
 * performs FDIR checks, generates telemetry (MID 0x0882), and issues
 * a Solar Array Close command (MID 0x1890, FC 6) when radiation
 * exceeds 150.0 mSv/h.
 ************************************************************************/

#include "cfe.h"
#include "rad_app.h"
#include <string.h>
#include <arpa/inet.h>  /* ntohl */

/* ------------------------------------------------------------------ */
/*  Module Data                                                        */
/* ------------------------------------------------------------------ */
static RAD_APP_Data_t RAD_APP_Data;

/* ------------------------------------------------------------------ */
/*  NetworkToHostFloat - Convert Big-Endian IEEE 754 float to host     */
/* ------------------------------------------------------------------ */
static float RAD_APP_NetworkToHostFloat(const void *src)
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
static void RAD_APP_ProcessSensorData(const CFE_SB_Buffer_t *SBBufPtr)
{
    const RAD_APP_SensorCmd_t *SensorCmd;
    RAD_APP_SolarArrayCmd_t    SolarCmd;
    float                      RadLevel;
    uint8                      Health;

    SensorCmd = (const RAD_APP_SensorCmd_t *)SBBufPtr;

    /* ---- Extract Big-Endian float from CCSDS payload ---- */
    RadLevel = RAD_APP_NetworkToHostFloat(&SensorCmd->SensorValue);

    RAD_APP_Data.PacketCount++;

    /* Integration verification: print to cFS console */
    OS_printf("RAD_APP: [Pkt %lu] Radiation = %.2f mSv/h\n",
              (unsigned long)RAD_APP_Data.PacketCount,
              (double)RadLevel);

    CFE_ES_WriteToSysLog("RAD_APP: Radiation = %.2f mSv/h (pkt %lu)\n",
                         (double)RadLevel,
                         (unsigned long)RAD_APP_Data.PacketCount);

    /* ---- FDIR: Determine health status ---- */
    if (RadLevel > RAD_APP_RAD_LIMIT)
    {
        Health = RAD_APP_HEALTH_CRITICAL;
    }
    else if (RadLevel > RAD_APP_RAD_WARNING)
    {
        Health = RAD_APP_HEALTH_WARNING;
    }
    else
    {
        Health = RAD_APP_HEALTH_NOMINAL;
    }

    /* ---- FDIR: Radiation exceeds limit -> Close Solar Panels ---- */
    if (RadLevel > RAD_APP_RAD_LIMIT)
    {
        RAD_APP_Data.FdirTriggerCount++;

        OS_printf("RAD_APP: FDIR TRIGGERED - Radiation %.2f > %.2f mSv/h\n",
                  (double)RadLevel, (double)RAD_APP_RAD_LIMIT);
        OS_printf("RAD_APP: Sending SOLAR ARRAY CLOSE CMD (MID=0x%04X FC=%u)\n",
                  RAD_APP_SOLAR_ARRAY_CMD_MID, RAD_APP_FC_SOLAR_CLOSE);

        /* Build and send Solar Array Close command */
        memset(&SolarCmd, 0, sizeof(SolarCmd));
        CFE_MSG_Init((CFE_MSG_Message_t *)&SolarCmd,
                     CFE_SB_ValueToMsgId(RAD_APP_SOLAR_ARRAY_CMD_MID),
                     sizeof(SolarCmd));
        CFE_MSG_SetFcnCode((CFE_MSG_Message_t *)&SolarCmd, RAD_APP_FC_SOLAR_CLOSE);

        CFE_SB_TransmitMsg((CFE_MSG_Message_t *)&SolarCmd, true);

        CFE_EVS_SendEvent(RAD_APP_FDIR_CMD_EID,
                          CFE_EVS_EventType_CRITICAL,
                          "RAD_APP FDIR: Radiation %.1f mSv/h exceeds %.1f - "
                          "SOLAR ARRAY CLOSE CMD SENT (MID 0x%04X FC %u)",
                          (double)RadLevel, (double)RAD_APP_RAD_LIMIT,
                          RAD_APP_SOLAR_ARRAY_CMD_MID,
                          (unsigned int)RAD_APP_FC_SOLAR_CLOSE);
    }
    else if (RadLevel > RAD_APP_RAD_WARNING)
    {
        CFE_EVS_SendEvent(RAD_APP_FDIR_WARN_EID,
                          CFE_EVS_EventType_ERROR,
                          "RAD_APP: Radiation %.1f mSv/h elevated (warn > %.1f)",
                          (double)RadLevel, (double)RAD_APP_RAD_WARNING);
    }

    /* ---- Generate Telemetry Packet ---- */
    RAD_APP_Data.TlmPkt.ProcessedValue = RadLevel;
    RAD_APP_Data.TlmPkt.HealthStatus   = Health;

    CFE_SB_TimeStampMsg((CFE_MSG_Message_t *)&RAD_APP_Data.TlmPkt);
    CFE_SB_TransmitMsg((CFE_MSG_Message_t *)&RAD_APP_Data.TlmPkt, true);

    CFE_EVS_SendEvent(RAD_APP_DATA_INF_EID,
                      CFE_EVS_EventType_INFORMATION,
                      "RAD_APP TLM: Radiation=%.2f Health=%u",
                      (double)RadLevel, (unsigned int)Health);
}

/* ------------------------------------------------------------------ */
/*  RAD_APP_Main - Application entry point                             */
/* ------------------------------------------------------------------ */
void RAD_APP_Main(void)
{
    CFE_Status_t         status;
    CFE_SB_Buffer_t     *SBBufPtr;
    CFE_SB_MsgId_t       MsgId;
    CFE_MSG_FcnCode_t    FcnCode;

    memset(&RAD_APP_Data, 0, sizeof(RAD_APP_Data));
    RAD_APP_Data.RunStatus = CFE_ES_RunStatus_APP_RUN;

    /* ---- Register for Event Services ---- */
    status = CFE_EVS_Register(NULL, 0, CFE_EVS_EventFilter_BINARY);
    if (status != CFE_SUCCESS)
    {
        CFE_ES_WriteToSysLog("RAD_APP: Error registering events, RC=0x%08lX\n",
                             (unsigned long)status);
        RAD_APP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
    }

    /* ---- Create Software Bus Pipe ---- */
    if (RAD_APP_Data.RunStatus == CFE_ES_RunStatus_APP_RUN)
    {
        status = CFE_SB_CreatePipe(&RAD_APP_Data.CommandPipe,
                                   RAD_APP_PIPE_DEPTH,
                                   RAD_APP_PIPE_NAME);
        if (status != CFE_SUCCESS)
        {
            CFE_ES_WriteToSysLog("RAD_APP: Error creating pipe, RC=0x%08lX\n",
                                 (unsigned long)status);
            RAD_APP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
        }
    }

    /* ---- Subscribe to Radiation Sensor Command MID (0x1882) ---- */
    if (RAD_APP_Data.RunStatus == CFE_ES_RunStatus_APP_RUN)
    {
        status = CFE_SB_Subscribe(CFE_SB_ValueToMsgId(RAD_APP_CMD_MID),
                                  RAD_APP_Data.CommandPipe);
        if (status != CFE_SUCCESS)
        {
            CFE_ES_WriteToSysLog("RAD_APP: Error subscribing to MID 0x%04X, RC=0x%08lX\n",
                                 RAD_APP_CMD_MID, (unsigned long)status);
            RAD_APP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
        }
    }

    /* ---- Initialize Telemetry Packet ---- */
    if (RAD_APP_Data.RunStatus == CFE_ES_RunStatus_APP_RUN)
    {
        CFE_MSG_Init((CFE_MSG_Message_t *)&RAD_APP_Data.TlmPkt,
                     CFE_SB_ValueToMsgId(RAD_APP_TLM_MID),
                     sizeof(RAD_APP_TlmPkt_t));

        OS_printf("RAD_APP: Initialized. Listening on CMD MID 0x%04X, TLM MID 0x%04X\n",
                  RAD_APP_CMD_MID, RAD_APP_TLM_MID);
        CFE_ES_WriteToSysLog("RAD_APP: Initialized. CMD MID=0x%04X TLM MID=0x%04X\n",
                             RAD_APP_CMD_MID, RAD_APP_TLM_MID);

        CFE_EVS_SendEvent(RAD_APP_INIT_INF_EID,
                          CFE_EVS_EventType_INFORMATION,
                          "RAD_APP Initialized: CMD=0x%04X TLM=0x%04X FDIR_LIMIT=%.1f mSv/h",
                          RAD_APP_CMD_MID, RAD_APP_TLM_MID, (double)RAD_APP_RAD_LIMIT);
    }

    /* ---- Main Loop ---- */
    while (CFE_ES_RunLoop(&RAD_APP_Data.RunStatus) == true)
    {
        /* Block until a message arrives (CFE_SB_ReceiveBuffer = Draco+ API) */
        status = CFE_SB_ReceiveBuffer(&SBBufPtr,
                                      RAD_APP_Data.CommandPipe,
                                      CFE_SB_PEND_FOREVER);

        if (status == CFE_SUCCESS)
        {
            CFE_MSG_GetMsgId(&SBBufPtr->Msg, &MsgId);
            CFE_MSG_GetFcnCode(&SBBufPtr->Msg, &FcnCode);

            if (CFE_SB_MsgIdToValue(MsgId) == RAD_APP_CMD_MID &&
                FcnCode == RAD_APP_FC_SEND_DATA)
            {
                RAD_APP_ProcessSensorData(SBBufPtr);
            }
            else
            {
                CFE_ES_WriteToSysLog(
                    "RAD_APP: Unexpected MID=0x%04X FC=%u\n",
                    (unsigned int)CFE_SB_MsgIdToValue(MsgId),
                    (unsigned int)FcnCode);
            }
        }
        else
        {
            CFE_ES_WriteToSysLog("RAD_APP: Pipe read error, RC=0x%08lX\n",
                                 (unsigned long)status);
            RAD_APP_Data.RunStatus = CFE_ES_RunStatus_APP_ERROR;
        }
    }

    CFE_ES_ExitApp(RAD_APP_Data.RunStatus);
}

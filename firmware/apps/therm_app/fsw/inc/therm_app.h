/************************************************************************
 * NASA cFS Thermal Monitor Application - Header
 *
 * THERM_APP subscribes to thermal sensor telemetry on the Software Bus,
 * performs FDIR (Fault Detection, Isolation, and Recovery), and publishes
 * processed telemetry for downlink.
 *
 * FDIR Rule: If Temperature > 100.0 C, log a CRITICAL event via
 *            CFE_EVS_SendEvent.
 ************************************************************************/

#ifndef THERM_APP_H
#define THERM_APP_H

#include "cfe.h"

/* ------------------------------------------------------------------ */
/*  Message IDs                                                        */
/* ------------------------------------------------------------------ */
#define THERM_APP_CMD_MID            0x1883  /* Incoming sensor commands      */
#define THERM_APP_TLM_MID            0x0883  /* Outgoing processed telemetry  */

/* ------------------------------------------------------------------ */
/*  Function Codes                                                     */
/* ------------------------------------------------------------------ */
#define THERM_APP_FC_SEND_DATA       2       /* Sensor data delivery          */

/* ------------------------------------------------------------------ */
/*  FDIR Thresholds                                                    */
/* ------------------------------------------------------------------ */
#define THERM_APP_TEMP_LIMIT         100.0f  /* Celsius - critical threshold  */
#define THERM_APP_TEMP_WARNING       80.0f   /* Celsius - elevated warning    */

/* ------------------------------------------------------------------ */
/*  Application Constants                                              */
/* ------------------------------------------------------------------ */
#define THERM_APP_PIPE_DEPTH         10
#define THERM_APP_PIPE_NAME          "THERM_CMD_PIPE"

/* ------------------------------------------------------------------ */
/*  Event IDs                                                          */
/* ------------------------------------------------------------------ */
#define THERM_APP_INIT_INF_EID       1
#define THERM_APP_DATA_INF_EID       2
#define THERM_APP_FDIR_WARN_EID      3
#define THERM_APP_FDIR_CRIT_EID      4
#define THERM_APP_ERR_EID            10

/* ------------------------------------------------------------------ */
/*  Health Status Codes                                                */
/* ------------------------------------------------------------------ */
#define THERM_APP_HEALTH_NOMINAL     0
#define THERM_APP_HEALTH_WARNING     1
#define THERM_APP_HEALTH_CRITICAL    2

/* ------------------------------------------------------------------ */
/*  Data Structures                                                    */
/* ------------------------------------------------------------------ */

/*
 * Incoming sensor command packet.
 * Matches the CCSDS command packet sent by the Python Sensor Manager:
 *   [0:6]   Primary Header
 *   [6:8]   Command Secondary Header (FC + Checksum)
 *   [8:12]  Payload: IEEE 754 float, Big-Endian (struct.pack '!f')
 */
typedef struct
{
    CFE_MSG_CommandHeader_t CmdHeader;
    float                   SensorValue;  /* Network byte order (Big-Endian) */
} THERM_APP_SensorCmd_t;

/*
 * Outgoing telemetry packet.
 * Contains the processed temperature value and health assessment.
 */
typedef struct
{
    CFE_MSG_TelemetryHeader_t TlmHeader;
    float                     ProcessedValue;  /* Temperature in Celsius       */
    uint8                     HealthStatus;    /* 0=NOM, 1=WARN, 2=CRIT        */
    uint8                     Spare[3];        /* Pad to 4-byte boundary        */
} THERM_APP_TlmPkt_t;

/*
 * Application runtime data.
 */
typedef struct
{
    uint32              RunStatus;
    CFE_SB_PipeId_t     CommandPipe;
    THERM_APP_TlmPkt_t  TlmPkt;
    uint32              PacketCount;
    uint32              FdirTriggerCount;
} THERM_APP_Data_t;

/* ------------------------------------------------------------------ */
/*  Entry Point                                                        */
/* ------------------------------------------------------------------ */
void THERM_APP_Main(void);

#endif /* THERM_APP_H */

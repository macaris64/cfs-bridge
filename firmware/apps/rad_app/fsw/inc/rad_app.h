/************************************************************************
 * NASA cFS Radiation Monitor Application - Header
 *
 * RAD_APP subscribes to radiation sensor telemetry on the Software Bus,
 * performs FDIR (Fault Detection, Isolation, and Recovery), and publishes
 * processed telemetry for downlink.
 *
 * FDIR Rule: If Radiation > 150.0 mSv/h, publish a Solar Array Close
 *            command (MID 0x1890, FC 6) to protect hardware.
 ************************************************************************/

#ifndef RAD_APP_H
#define RAD_APP_H

#include "cfe.h"

/* ------------------------------------------------------------------ */
/*  Message IDs                                                        */
/* ------------------------------------------------------------------ */
#define RAD_APP_CMD_MID              0x1882  /* Incoming sensor commands      */
#define RAD_APP_TLM_MID              0x0882  /* Outgoing processed telemetry  */
#define RAD_APP_SOLAR_ARRAY_CMD_MID  0x1890  /* Solar Array command target    */

/* ------------------------------------------------------------------ */
/*  Function Codes                                                     */
/* ------------------------------------------------------------------ */
#define RAD_APP_FC_SEND_DATA         2       /* Sensor data delivery          */
#define RAD_APP_FC_SOLAR_CLOSE       6       /* Solar Array Close Panels      */

/* ------------------------------------------------------------------ */
/*  FDIR Thresholds                                                    */
/* ------------------------------------------------------------------ */
#define RAD_APP_RAD_LIMIT            150.0f  /* mSv/h - trigger panel close   */
#define RAD_APP_RAD_WARNING          100.0f  /* mSv/h - elevated warning      */

/* ------------------------------------------------------------------ */
/*  Application Constants                                              */
/* ------------------------------------------------------------------ */
#define RAD_APP_PIPE_DEPTH           10
#define RAD_APP_PIPE_NAME            "RAD_CMD_PIPE"

/* ------------------------------------------------------------------ */
/*  Event IDs                                                          */
/* ------------------------------------------------------------------ */
#define RAD_APP_INIT_INF_EID         1
#define RAD_APP_DATA_INF_EID         2
#define RAD_APP_FDIR_WARN_EID        3
#define RAD_APP_FDIR_CMD_EID         4
#define RAD_APP_ERR_EID              10

/* ------------------------------------------------------------------ */
/*  Health Status Codes                                                */
/* ------------------------------------------------------------------ */
#define RAD_APP_HEALTH_NOMINAL       0
#define RAD_APP_HEALTH_WARNING       1
#define RAD_APP_HEALTH_CRITICAL      2

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
} RAD_APP_SensorCmd_t;

/*
 * Outgoing telemetry packet.
 * Contains the processed radiation value and health assessment.
 */
typedef struct
{
    CFE_MSG_TelemetryHeader_t TlmHeader;
    float                     ProcessedValue;  /* Radiation in mSv/h          */
    uint8                     HealthStatus;    /* 0=NOM, 1=WARN, 2=CRIT       */
    uint8                     Spare[3];        /* Pad to 4-byte boundary       */
} RAD_APP_TlmPkt_t;

/*
 * Solar Array Close command (no payload, header-only).
 */
typedef struct
{
    CFE_MSG_CommandHeader_t CmdHeader;
} RAD_APP_SolarArrayCmd_t;

/*
 * Application runtime data.
 */
typedef struct
{
    uint32              RunStatus;
    CFE_SB_PipeId_t     CommandPipe;
    RAD_APP_TlmPkt_t    TlmPkt;
    uint32              PacketCount;
    uint32              FdirTriggerCount;
} RAD_APP_Data_t;

/* ------------------------------------------------------------------ */
/*  Entry Point                                                        */
/* ------------------------------------------------------------------ */
void RAD_APP_Main(void);

#endif /* RAD_APP_H */

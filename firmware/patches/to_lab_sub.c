/************************************************************************
 * Patched TO_LAB subscription table for the CFS-Bridge project.
 *
 * Enables forwarding of RAD_APP and THERM_APP processed telemetry
 * and cFE core event/housekeeping messages to the ground station.
 ************************************************************************/

#include "cfe_tbl_filedef.h"
#include "cfe_sb_api_typedefs.h"
#include "to_lab_tbl.h"
#include "cfe_msgids.h"
#include "to_lab_msgids.h"

/*
 * Use raw numeric MID values for cross-app references to avoid
 * include-path issues in the table build system.
 *   RAD_APP_TLM_MID   = TLM base 0x0800 | topic 0x82 = 0x0882
 *   THERM_APP_TLM_MID = TLM base 0x0800 | topic 0x83 = 0x0883
 */
#define BRIDGE_RAD_APP_TLM_MID    0x0882
#define BRIDGE_THERM_APP_TLM_MID  0x0883

TO_LAB_Subs_t Subscriptions = {
    .Subs = {
        /* RAD_APP processed telemetry (MID 0x0882) */
        {CFE_SB_MSGID_WRAP_VALUE(BRIDGE_RAD_APP_TLM_MID), {0, 0}, 4},

        /* THERM_APP processed telemetry (MID 0x0883) */
        {CFE_SB_MSGID_WRAP_VALUE(BRIDGE_THERM_APP_TLM_MID), {0, 0}, 4},

        /* TO_LAB own housekeeping */
        {CFE_SB_MSGID_WRAP_VALUE(TO_LAB_HK_TLM_MID), {0, 0}, 4},

        /* cFE Executive Services housekeeping (heartbeat) */
        {CFE_SB_MSGID_WRAP_VALUE(CFE_ES_HK_TLM_MID), {0, 0}, 4},

        /* cFE Event messages (long format) */
        {CFE_SB_MSGID_WRAP_VALUE(CFE_EVS_LONG_EVENT_MSG_MID), {0, 0}, 32},

        /* Terminator */
        {CFE_SB_MSGID_RESERVED, {0, 0}, 0}
    }
};

CFE_TBL_FILEDEF(Subscriptions, TO_LAB.Subscriptions, TO Lab Sub Tbl, to_lab_sub.tbl)

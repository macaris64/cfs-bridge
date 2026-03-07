######################################################################
#
# CFS-Bridge Mission targets.cmake
#
# Based on cFS sample_defs/targets.cmake with bridge_app added.
#
######################################################################

SET(MISSION_NAME "SampleMission")
SET(SPACECRAFT_ID 0x42)

# Apps built for every target
list(APPEND MISSION_GLOBAL_APPLIST sample_app sample_lib bridge_app rad_app therm_app)

SET(FT_INSTALL_SUBDIR "host/functional-test")

SET(MISSION_CPUNAMES cpu1)

SET(cpu1_PROCESSORID 1)
SET(cpu1_APPLIST ci_lab to_lab sch_lab)
SET(cpu1_FILELIST cfe_es_startup.scr)
SET(cpu1_SYSTEM i686-linux-gnu)

project(CFS_BRIDGE_APP C)

set(APP_SRC_FILES
    fsw/src/bridge_app.c
)

add_cfe_app(bridge_app ${APP_SRC_FILES})

target_include_directories(bridge_app PUBLIC
    fsw/inc
)

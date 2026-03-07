project(CFS_THERM_APP C)

set(APP_SRC_FILES
    fsw/src/therm_app.c
)

add_cfe_app(therm_app ${APP_SRC_FILES})

target_include_directories(therm_app PUBLIC
    fsw/inc
)

project(CFS_RAD_APP C)

set(APP_SRC_FILES
    fsw/src/rad_app.c
)

add_cfe_app(rad_app ${APP_SRC_FILES})

target_include_directories(rad_app PUBLIC
    fsw/inc
)

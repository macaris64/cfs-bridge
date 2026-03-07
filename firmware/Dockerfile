##############################################################################
# NASA cFS Flight Software Build Container
#
# Clones cFS from GitHub, overlays custom mission defs and bridge_app,
# builds with SIMULATION=native, and runs core-cpu1.
#
# CI_LAB listens on UDP 1234 (command ingest)
# TO_LAB sends on UDP 2234 (telemetry output)
##############################################################################

FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Clone the NASA cFS repository with all submodules
RUN git clone --recurse-submodules https://github.com/nasa/cFS.git /cfs

WORKDIR /cfs

# Set up the build using the sample Makefile and default sample_defs
RUN cp cfe/cmake/Makefile.sample Makefile \
    && cp -r cfe/cmake/sample_defs sample_defs

# Overlay custom mission definitions (targets.cmake, startup script)
COPY defs/targets.cmake          sample_defs/targets.cmake
COPY defs/cpu1_cfe_es_startup.scr sample_defs/cpu1_cfe_es_startup.scr

# Copy custom bridge_app into the apps directory
COPY apps/bridge_app/ apps/bridge_app/

# Patch TO_LAB subscription table to enable telemetry forwarding
COPY patches/to_lab_sub.c apps/to_lab/fsw/tables/to_lab_sub.c

# Build cFS for native simulation
RUN make SIMULATION=native prep \
    && make \
    && make install

WORKDIR /cfs/build/exe/cpu1

# Expose CI_LAB command ingest port
EXPOSE 1234/udp

CMD ["/bin/bash", "-c", "echo 128 > /proc/sys/fs/mqueue/msg_max && ./core-cpu1"]

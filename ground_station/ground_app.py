"""Ground Station (MOC) — Mission Operations Center Dashboard.

Streamlit application providing real-time telemetry visualization,
command dispatch, and live log monitoring for the cFS-Bridge
satellite simulation.

On startup, the ground station:
    1. Starts the TelemetryReceiver (UDP listener on port 2234).
    2. Sends TO_LAB_OUTPUT_ENABLE (MID 0x1880, FC 6) to cFS so that
       TO_LAB begins forwarding telemetry to this container.

Sections:
    1. Telemetry Visuals — Real-time line charts for Radiation and Temperature.
    2. Command Center — Manual Solar Array Open/Close buttons.
    3. Live Logs — Raw telemetry hex and parsed EVS event messages.

Run:
    streamlit run ground_station/ground_app.py
"""

import logging
import os
import socket
import time

import pandas as pd
import streamlit as st

from ground_station.command_dispatcher import CommandDispatcher
from ground_station.telemetry_receiver import TelemetryReceiver
from ground_station.telemetry.processor import TelemetryProcessor
from ground_station.commands.solar_array import SolarArrayCommands
from sensor_manager.core.mission_registry import MID, FC

logger = logging.getLogger(__name__)


def _get_own_ip() -> str:
    """Resolve this container's IP on the Docker bridge network.

    Inside Docker, the hostname 'ground-station' resolves to the
    container's IP on the cfs-net bridge.  TO_LAB needs this IP
    so it can send UDP telemetry packets to us.

    Returns:
        The container's IP address as a string.
    """
    container_name = os.environ.get("HOSTNAME", "ground-station")
    try:
        return socket.gethostbyname(container_name)
    except socket.gaierror:
        # Fallback: try to resolve 'ground-station' directly
        try:
            return socket.gethostbyname("ground-station")
        except socket.gaierror:
            # Last resort: get our own outbound IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("cfs-flight", 1234))
                ip = s.getsockname()[0]
            except Exception:
                ip = "127.0.0.1"
            finally:
                s.close()
            return ip


@st.cache_resource
def _init_global_services():
    """Create ground station services once, shared across all sessions.

    Uses @st.cache_resource so there is exactly ONE TelemetryReceiver
    socket bound to port 2234, avoiding multiple sockets competing for
    the same UDP port.
    """
    dispatcher = CommandDispatcher()
    receiver = TelemetryReceiver()
    processor = TelemetryProcessor()

    receiver.register_callback(processor.process)
    receiver.start()

    dest_ip = _get_own_ip()
    try:
        dispatcher.enable_telemetry_output(dest_ip)
        logger.info("TO_LAB output enable sent — dest_ip=%s", dest_ip)
    except Exception:
        logger.exception("Failed to send TO_LAB enable command")

    solar_cmds = SolarArrayCommands(dispatcher)
    return dispatcher, receiver, processor, solar_cmds, dest_ip


def _init_services():
    """Initialize ground station services.

    The heavy resources (receiver, processor) are global singletons
    via @st.cache_resource.  Session-state just holds a reference
    so the rest of the app can access them uniformly.
    """
    dispatcher, receiver, processor, solar_cmds, dest_ip = (
        _init_global_services()
    )
    st.session_state.dispatcher = dispatcher
    st.session_state.receiver = receiver
    st.session_state.processor = processor
    st.session_state.solar_cmds = solar_cmds
    st.session_state.dest_ip = dest_ip


def main():
    """Main Streamlit application entry point."""
    st.set_page_config(
        page_title="Ground Station (MOC)",
        page_icon="\U0001f4e1",
        layout="wide",
    )

    st.title("\U0001f4e1 Ground Station — Mission Operations Center")
    st.caption(
        "Real-time telemetry monitoring and command dispatch for the "
        "cFS-Bridge satellite simulation"
    )

    _init_services()

    processor: TelemetryProcessor = st.session_state.processor
    solar_cmds: SolarArrayCommands = st.session_state.solar_cmds
    dispatcher: CommandDispatcher = st.session_state.dispatcher
    receiver: TelemetryReceiver = st.session_state.receiver

    # ── Status Bar ──
    status_cols = st.columns(4)
    with status_cols[0]:
        st.metric("Packets Received", receiver.packets_received)
    with status_cols[1]:
        rad = processor.last_radiation
        st.metric(
            "Radiation",
            f"{rad.value:.1f} mSv/h" if rad else "—",
            delta=rad.health_label if rad else None,
            delta_color="normal" if rad and rad.health == 0 else "inverse",
        )
    with status_cols[2]:
        therm = processor.last_thermal
        st.metric(
            "Temperature",
            f"{therm.value:.1f} \u00b0C" if therm else "—",
            delta=therm.health_label if therm else None,
            delta_color="normal" if therm and therm.health == 0 else "inverse",
        )
    with status_cols[3]:
        sa_status = processor.solar_array_status
        st.metric("Solar Array", sa_status)

    st.divider()

    # ══════════════════════════════════════════════════════════════════
    # Section 1: Telemetry Visuals
    # ══════════════════════════════════════════════════════════════════
    st.header("\U0001f4c8 Telemetry Visuals")

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("Radiation (mSv/h)")
        rad_series = processor.get_radiation_series()
        if rad_series:
            df_rad = pd.DataFrame(
                [{"Time": pt.timestamp, "Radiation": pt.value} for pt in rad_series]
            )
            df_rad["Time"] = pd.to_datetime(df_rad["Time"], unit="s")
            st.line_chart(df_rad.set_index("Time")["Radiation"])
        else:
            st.info("Waiting for radiation telemetry...")

    with chart_col2:
        st.subheader("Temperature (\u00b0C)")
        therm_series = processor.get_thermal_series()
        if therm_series:
            df_therm = pd.DataFrame(
                [{"Time": pt.timestamp, "Temperature": pt.value} for pt in therm_series]
            )
            df_therm["Time"] = pd.to_datetime(df_therm["Time"], unit="s")
            st.line_chart(df_therm.set_index("Time")["Temperature"])
        else:
            st.info("Waiting for thermal telemetry...")

    st.divider()

    # ══════════════════════════════════════════════════════════════════
    # Section 2: Command Center
    # ══════════════════════════════════════════════════════════════════
    st.header("\U0001f3ae Command Center")

    cmd_col1, cmd_col2, cmd_col3 = st.columns([1, 1, 2])

    with cmd_col1:
        if st.button(
            "\u2600\ufe0f Manual Solar Array Open",
            help=f"MID 0x{MID.SOLAR_ARRAY_APP:04X}, FC {FC.SOLAR_ARRAY_OPEN}",
            use_container_width=True,
        ):
            try:
                n = solar_cmds.open_array()
                processor.update_solar_array_status("Open (Operator Override)")
                st.success(f"Solar Array OPEN command sent ({n} bytes)")
            except Exception as e:
                st.error(f"Failed to send Open command: {e}")

    with cmd_col2:
        if st.button(
            "\U0001f512 Manual Solar Array Close",
            help=f"MID 0x{MID.SOLAR_ARRAY_APP:04X}, FC {FC.SOLAR_ARRAY_CLOSE}",
            use_container_width=True,
        ):
            try:
                n = solar_cmds.close_array()
                processor.update_solar_array_status("Closed (Operator)")
                st.success(f"Solar Array CLOSE command sent ({n} bytes)")
            except Exception as e:
                st.error(f"Failed to send Close command: {e}")

    with cmd_col3:
        st.subheader("Command History")
        if dispatcher.history:
            for rec in reversed(dispatcher.history[-10:]):
                st.text(
                    f"MID={rec['mid_name']}  FC={rec['fc_name']}  "
                    f"Seq={rec['seq']}  Bytes={rec['bytes_sent']}"
                )
        else:
            st.caption("No commands sent yet")

    st.divider()

    # ══════════════════════════════════════════════════════════════════
    # Section 3: Live Logs
    # ══════════════════════════════════════════════════════════════════
    st.header("\U0001f4dc Live Logs")

    log_tab1, log_tab2 = st.tabs(["Event Log (EVS)", "Raw Telemetry Hex"])

    with log_tab1:
        events = processor.get_events(count=50)
        if events:
            log_text = "\n".join(reversed(events))
            st.code(log_text, language="text")
        else:
            st.caption("No events received yet")

    with log_tab2:
        raw = processor.get_raw_log(count=50)
        if raw:
            raw_text = "\n".join(reversed(raw))
            st.code(raw_text, language="text")
        else:
            st.caption("No telemetry received yet")

    # ── Connection & Refresh ──
    st.divider()
    conn_col1, conn_col2, conn_col3 = st.columns([2, 1, 1])

    with conn_col1:
        dest_ip = st.session_state.get("dest_ip", "unknown")
        st.caption(
            f"TO_LAB output enabled to **{dest_ip}:2234** | "
            f"Receiver bound on **0.0.0.0:{receiver.port}**"
        )

    with conn_col2:
        if st.button("Re-enable TO_LAB"):
            try:
                dest_ip = _get_own_ip()
                dispatcher.enable_telemetry_output(dest_ip)
                st.session_state.dest_ip = dest_ip
                st.success(f"TO_LAB re-enabled to {dest_ip}")
            except Exception as e:
                st.error(f"Failed: {e}")

    with conn_col3:
        auto_refresh = st.checkbox("Auto-refresh (2s)", value=True)

    if auto_refresh:
        time.sleep(2)
        st.rerun()


if __name__ == "__main__":
    main()

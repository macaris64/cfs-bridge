"""
Sensor Manager — Environment Simulator UI
==========================================

Streamlit application that dynamically loads all sensor simulators
and provides real-time sliders/inputs to inject sensor values into
the cFS firmware via CCSDS command packets over UDP.

Run:
    streamlit run manager_app.py
"""

import importlib
import inspect
import pkgutil

import streamlit as st

from sensor_manager.core.base_sensor import BaseSensor
import sensor_manager.sensors as sensors_pkg


def discover_sensors() -> list[type[BaseSensor]]:
    """Dynamically discover all BaseSensor subclasses in the sensors package."""
    sensor_classes: list[type[BaseSensor]] = []

    for importer, modname, ispkg in pkgutil.iter_modules(sensors_pkg.__path__):
        module = importlib.import_module(f"sensor_manager.sensors.{modname}")
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseSensor) and obj is not BaseSensor:
                sensor_classes.append(obj)

    return sorted(sensor_classes, key=lambda c: c.name)


def main():
    st.set_page_config(page_title="Sensor Manager", page_icon="\U0001f6f0\ufe0f", layout="wide")
    st.title("\U0001f6f0\ufe0f Sensor Manager — Environment Simulator")
    st.caption("Inject simulated sensor readings into cFS firmware via CCSDS/UDP")

    sensor_classes = discover_sensors()

    if not sensor_classes:
        st.warning("No sensors discovered. Add sensor classes to sensor_manager/sensors/.")
        return

    # Instantiate sensors (cached per session)
    if "sensors" not in st.session_state:
        st.session_state.sensors = {cls.name: cls() for cls in sensor_classes}

    sensors = st.session_state.sensors

    cols = st.columns(len(sensors))

    for col, (name, sensor) in zip(cols, sensors.items()):
        with col:
            st.subheader(f"{name}")
            st.text(f"MID: 0x{sensor.mid:04X}  |  FC: {sensor.func_code}")

            new_val = st.slider(
                f"{name} ({sensor.unit})",
                min_value=float(sensor.min_value),
                max_value=float(sensor.max_value),
                value=float(sensor.value),
                key=f"slider_{name}",
            )

            if st.button(f"Send {name}", key=f"btn_{name}"):
                try:
                    n = sensor.update_and_send(new_val)
                    st.success(f"Sent {n} bytes  |  Value: {sensor.value:.2f} {sensor.unit}")
                except Exception as e:
                    st.error(f"Send failed: {e}")

            st.metric(label="Current Value", value=f"{sensor.value:.2f} {sensor.unit}")


if __name__ == "__main__":
    main()

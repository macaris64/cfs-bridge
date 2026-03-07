"""
Thermal Sensor Simulator
=========================

Simulates a spacecraft thermal management sensor.
Sends temperature readings (in °C) to the THERMAL_APP
on the cFS Software Bus via CCSDS command packets.
"""

from sensor_manager.core.base_sensor import BaseSensor
from sensor_manager.core.mission_registry import MID, FC


class ThermalSensor(BaseSensor):
    """Thermal management sensor simulator."""

    name = "Thermal Sensor"
    mid = MID.THERMAL_APP
    func_code = FC.SEND_DATA
    unit = "\u00b0C"
    min_value = -40.0
    max_value = 85.0
    default = 20.0

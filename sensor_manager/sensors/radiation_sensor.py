"""
Radiation Sensor Simulator
===========================

Simulates a spacecraft radiation environment monitor.
Sends radiation level readings (in rad) to the RADIATION_APP
on the cFS Software Bus via CCSDS command packets.
"""

from sensor_manager.core.base_sensor import BaseSensor
from sensor_manager.core.mission_registry import MID, FC


class RadiationSensor(BaseSensor):
    """Radiation environment sensor simulator."""

    name = "Radiation Sensor"
    mid = MID.RADIATION_APP
    func_code = FC.SEND_DATA
    unit = "rad"
    min_value = 0.0
    max_value = 1000.0
    default = 50.0

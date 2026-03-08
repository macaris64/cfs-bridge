"""Command definitions for the ground station.

Each module defines callable command builders that return the
arguments needed by CommandDispatcher.send().
"""

from .solar_array import SolarArrayCommands

__all__ = ["SolarArrayCommands"]

"""Solar Array command definitions.

Provides pre-configured command builders for the Solar Array
Drive Controller (MID 0x1890).
"""

from sensor_manager.core.mission_registry import MID, FC
from ground_station.command_dispatcher import CommandDispatcher


class SolarArrayCommands:
    """Solar Array Drive Controller commands.

    Wraps CommandDispatcher to provide named methods for solar array
    operations, matching the MID and function codes defined in the
    mission registry.

    Attributes:
        MID: Solar Array command MID (0x1890).
        FC_OPEN: Function code for manual open (5).
        FC_CLOSE: Function code for manual close (6).
    """

    MID = MID.SOLAR_ARRAY_APP
    FC_OPEN = FC.SOLAR_ARRAY_OPEN
    FC_CLOSE = FC.SOLAR_ARRAY_CLOSE

    def __init__(self, dispatcher: CommandDispatcher) -> None:
        """Initialize with a CommandDispatcher instance.

        Args:
            dispatcher: The command dispatcher to send packets through.
        """
        self._dispatcher = dispatcher

    def open_array(self) -> int:
        """Send Manual Solar Array Open command (FC 5).

        Returns:
            Number of bytes sent.
        """
        return self._dispatcher.send(self.MID, self.FC_OPEN)

    def close_array(self) -> int:
        """Send Manual Solar Array Close command (FC 6).

        Returns:
            Number of bytes sent.
        """
        return self._dispatcher.send(self.MID, self.FC_CLOSE)

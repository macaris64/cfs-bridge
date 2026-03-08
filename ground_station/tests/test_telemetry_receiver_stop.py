import types
from ground_station.telemetry_receiver import TelemetryReceiver


def test_stop_handles_sock_close_error(monkeypatch):
    r = TelemetryReceiver()

    class BadSock:
        def close(self):
            raise OSError("cannot close")

    r._sock = BadSock()
    # Ensure thread is None so join path not taken
    r._thread = None
    # Should not raise
    r.stop()


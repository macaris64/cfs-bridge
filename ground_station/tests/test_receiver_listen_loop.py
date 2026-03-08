import socket
import importlib
import sys

from ground_station.telemetry_receiver import TelemetryReceiver


def test_listen_loop_recv_raises_oserror(monkeypatch):
    # Replace socket.socket with a fake that raises OSError on recvfrom
    class FakeSocket:
        def __init__(self, *args, **kwargs):
            pass

        def setsockopt(self, *args, **kwargs):
            pass

        def settimeout(self, t):
            pass

        def bind(self, addr):
            pass

        def recvfrom(self, n):
            raise OSError("recv error")

        def close(self):
            pass

    monkeypatch.setattr("socket.socket", FakeSocket)

    r = TelemetryReceiver(host="127.0.0.1", port=0)
    try:
        r._listen_loop()
    except OSError:
        # expected to propagate after logging
        pass

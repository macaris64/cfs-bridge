import importlib
import sys
import types
import socket

def _make_streamlit_stub():
    st = types.ModuleType("streamlit")
    st.session_state = {}

    def cache_resource(fn=None):
        if fn is None:
            def _decorator(f):
                return f
            return _decorator
        return fn

    st.cache_resource = cache_resource

    class DummyCtx:
        def __enter__(self):
            return None

        def __exit__(self, exc_type, exc, tb):
            return False

    st.columns = lambda *args, **kwargs: [DummyCtx() for _ in range(max(1, len(args[0]) if args else 1))] if args and isinstance(args[0], (list, tuple)) else [DummyCtx() for _ in range(4)]
    st.metric = lambda *args, **kwargs: None
    st.divider = lambda *args, **kwargs: None
    st.header = lambda *args, **kwargs: None
    st.subheader = lambda *args, **kwargs: None
    st.line_chart = lambda *args, **kwargs: None
    st.info = lambda *args, **kwargs: None
    st.caption = lambda *args, **kwargs: None
    st.button = lambda *args, **kwargs: False
    st.checkbox = lambda *args, **kwargs: False
    st.code = lambda *args, **kwargs: None
    st.tabs = lambda *args, **kwargs: (DummyCtx(), DummyCtx())
    st.expander = lambda *args, **kwargs: DummyCtx()
    st.set_page_config = lambda *args, **kwargs: None
    st.rerun = lambda: None
    st.experimental_rerun = lambda: None
    return st


def test_init_global_services_monkeypatched(tmp_path, monkeypatch):
    # Install streamlit and pandas stubs before importing ground_app
    sys.modules["streamlit"] = _make_streamlit_stub()
    sys.modules["pandas"] = types.ModuleType("pandas")

    # Import ground_app fresh
    ga = importlib.import_module("ground_station.ground_app")

    # Monkeypatch CommandDispatcher, TelemetryReceiver, TelemetryProcessor, SolarArrayCommands
    class FakeDispatcher:
        def __init__(self):
            self.history = []

        def enable_telemetry_output(self, ip):
            return None

    class FakeReceiver:
        def __init__(self):
            self.port = 2234
            self._buffer = []
            self.started = False

        def register_callback(self, cb):
            self._cb = cb

        def start(self):
            self.started = True

    class FakeProcessor:
        def __init__(self):
            self.last_radiation = None
            self.last_thermal = None
            self.solar_array_status = "Unknown"
        def process(self, entry):
            # no-op process method for registration in receiver
            return None

    class FakeSolar:
        def __init__(self, dispatcher):
            self.dispatcher = dispatcher

    monkeypatch.setattr(ga, "CommandDispatcher", FakeDispatcher)
    monkeypatch.setattr(ga, "TelemetryReceiver", FakeReceiver)
    monkeypatch.setattr(ga, "TelemetryProcessor", FakeProcessor)
    monkeypatch.setattr(ga, "SolarArrayCommands", FakeSolar)
    monkeypatch.setattr(ga, "_get_own_ip", lambda: "127.0.0.1")

    # Call _init_global_services and verify return types
    # Also test exception handling: make enable_telemetry_output raise
    class BadDispatcher(FakeDispatcher):
        def enable_telemetry_output(self, ip):
            raise RuntimeError("boom")

    monkeypatch.setattr(ga, "CommandDispatcher", BadDispatcher)
    dispatcher, receiver, processor, solar_cmds, dest_ip = ga._init_global_services()
    assert isinstance(dispatcher, FakeDispatcher)
    assert isinstance(receiver, FakeReceiver)
    assert isinstance(processor, FakeProcessor)
    assert isinstance(solar_cmds, FakeSolar)
    assert dest_ip == "127.0.0.1"


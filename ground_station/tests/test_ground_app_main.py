import importlib
import sys
import types
import time


class DummyCtx:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


def _make_streamlit_stub_for_main():
    st = types.ModuleType("streamlit")
    class SessionState:
        def __init__(self):
            self._d = {}
        def __getattr__(self, k):
            return self._d.get(k)
        def __setattr__(self, k, v):
            if k == "_d":
                super().__setattr__(k, v)
            else:
                self._d[k] = v
        def get(self, k, default=None):
            return self._d.get(k, default)
        def __getitem__(self, k):
            return self._d[k]
        def __setitem__(self, k, v):
            self._d[k] = v
        def __contains__(self, k):
            return k in self._d

    st.session_state = SessionState()

    def cache_resource(fn=None):
        if fn is None:
            def _decorator(f):
                return f
            return _decorator
        return fn

    st.cache_resource = cache_resource
    # columns should return context managers, support varied lengths
    def columns(arg):
        if isinstance(arg, (list, tuple)):
            n = len(arg)
        else:
            try:
                n = int(arg)
            except Exception:
                n = 3
        return [DummyCtx() for _ in range(n)]

    st.columns = columns
    st.metric = lambda *args, **kwargs: None
    st.divider = lambda *args, **kwargs: None
    st.header = lambda *args, **kwargs: None
    st.subheader = lambda *args, **kwargs: None
    st.line_chart = lambda *args, **kwargs: None
    st.info = lambda *args, **kwargs: None
    st.caption = lambda *args, **kwargs: None
    st.text = lambda *args, **kwargs: None
    st.code = lambda *args, **kwargs: None
    st.json = lambda *args, **kwargs: None
    st.expander = lambda *args, **kwargs: DummyCtx()
    st.set_page_config = lambda *args, **kwargs: None
    st.title = lambda *args, **kwargs: None
    st.success = lambda *args, **kwargs: None
    st.error = lambda *args, **kwargs: None
    st.write = lambda *args, **kwargs: None
    # checkbox behavior: return True for auto-refresh, False elsewhere
    def checkbox(label, value=False, key=None):
        if "Auto-refresh" in label:
            return True
        if "Auto-scroll" in label:
            return True
        return False

    st.checkbox = checkbox

    def multiselect(label, options, default=None, help=None):
        return default if default is not None else options

    st.multiselect = multiselect

    def button(*args, **kwargs):
        return False

    st.button = button

    st.rerun = lambda: None
    st.experimental_rerun = lambda: None
    return st


def test_main_runs_through(monkeypatch):
    # Install st and pandas shims
    st = _make_streamlit_stub_for_main()
    sys.modules["streamlit"] = st
    sys.modules["pandas"] = types.ModuleType("pandas")

    # Ensure fresh import after installing st stub
    sys.modules.pop("ground_station.ground_app", None)
    ga = importlib.import_module("ground_station.ground_app")

    # Fake Dispatcher/Receiver/Processor/Solar
    class FakeDispatcher:
        def __init__(self):
            self.history = []

        def enable_telemetry_output(self, ip):
            return None

    class FakeReceiver:
        def __init__(self):
            self.port = 2234
            self.packets_received = 0

        def register_callback(self, cb):
            pass

        def start(self):
            pass

        def get_recent(self, count=50):
            return []

    class FakeProcessor:
        def __init__(self):
            self.last_radiation = None
            self.last_thermal = None
            self.solar_array_status = "Unknown"

        def get_radiation_series(self):
            return []

        def get_thermal_series(self):
            return []

        def get_events(self, count=100):
            return []

        def get_raw_log(self, count=100):
            return []
        def process(self, entry):
            # no-op for callback registration
            return None

    class FakeSolar:
        def __init__(self, dispatcher):
            self.dispatcher = dispatcher

        def open_array(self):
            return 0

        def close_array(self):
            return 0

    monkeypatch.setattr(ga, "CommandDispatcher", FakeDispatcher)
    monkeypatch.setattr(ga, "TelemetryReceiver", FakeReceiver)
    monkeypatch.setattr(ga, "TelemetryProcessor", FakeProcessor)
    monkeypatch.setattr(ga, "SolarArrayCommands", FakeSolar)
    monkeypatch.setattr(ga, "_get_own_ip", lambda: "127.0.0.1")
    # Avoid sleeping
    monkeypatch.setattr(time, "sleep", lambda s: None)

    # Run main; it should execute without raising
    ga.main()


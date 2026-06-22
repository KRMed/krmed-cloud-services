import threading

from crucible_worker import config, launcher


def _cfg(gpu_ids):
    return config.Config(
        database_url="postgres://x",
        redis_url="redis://x",
        garage_endpoint="http://garage:3900",
        garage_access_key="key",
        garage_secret_key="secret",
        garage_bucket="crucible",
        model_cache_dir="/var/crucible/models",
        queue_block_seconds=5,
        visibility_timeout_seconds=900,
        reconcile_interval_seconds=300,
        orphan_grace_seconds=60,
        gpu_ids=gpu_ids,
    )


def test_single_gpu_runs_inline_and_pins_device(monkeypatch):
    monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
    seen = {}

    def worker(cfg, stop):
        seen["cfg"] = cfg
        seen["stop"] = stop
        seen["device"] = __import__("os").environ["CUDA_VISIBLE_DEVICES"]

    launcher.run(_cfg(("0",)), worker)

    assert seen["device"] == "0"
    assert isinstance(seen["stop"], threading.Event)


class _FakeProcess:
    def __init__(self, target, args, name):
        self.target = target
        self.args = args
        self.name = name
        self.pid = 1234
        self.started = False
        self.terminated = False

    def start(self):
        self.started = True

    def join(self, timeout=None):
        return None

    def is_alive(self):
        return False

    def terminate(self):
        self.terminated = True


class _FakeContext:
    def __init__(self):
        self.created = []

    def Process(self, target, args, name):
        proc = _FakeProcess(target, args, name)
        self.created.append(proc)
        return proc


def test_multi_gpu_spawns_one_process_per_device():
    ctx = _FakeContext()

    launcher.run(_cfg(("0", "1")), worker=lambda cfg, stop: None, mp_context=ctx)

    assert len(ctx.created) == 2
    assert all(p.started for p in ctx.created)
    gpu_args = [p.args[1] for p in ctx.created]
    assert gpu_args == ["0", "1"]
    assert [p.name for p in ctx.created] == [
        "crucible-worker-gpu0",
        "crucible-worker-gpu1",
    ]

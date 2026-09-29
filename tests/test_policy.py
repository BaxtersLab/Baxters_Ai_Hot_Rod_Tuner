"""Ported 2026-08-19 from Baxters_Ai_Hot_Rod_Tuner_Linux/tests/test_policy.py.

That tree is a stale Linux fork — its shared source matches the *Windows*
lineage, not this one — but these five tests are not stale: they run green
against the current `policies.py`/`metrics.py`/`sound.py`/`scheduler.py` and
cover four modules this suite had no tests for at all (every one of the 15
existing tests is fan safety).

Its sibling `test_linux.py` was deliberately NOT ported: it contains zero
`assert` statements and eight bare `return True/False`. Under pytest a test that
returns instead of asserting passes regardless — returning False still passes —
so all four of its "passing" tests were vacuous.
"""

import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hotrod_tuner import __version__


def test_version():
    """pyproject, __version__ and the .deb's control name one version. They
    had drifted apart: 0.1.0, 0.0.1 and 1.0.3. The control may add a Debian
    revision (1.0.4-1: the same program, packaged again), so what must agree
    is its upstream part -- the rule bxdeb's bx_assert_versions_agree applies:
    an exact match, or a match once everything after the LAST '-' is dropped."""
    import re
    import tomllib
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    control = re.search(r"^Version: (\S+)$",
                        (root / "packaging" / "DEBIAN" / "control").read_text(encoding="utf-8"), re.M)
    assert control, "no Version: line in the control file"
    deb = control.group(1)
    assert __version__ == project, (__version__, project)
    assert deb == project or deb.rsplit("-", 1)[0] == project, (deb, project)


def test_sound_manager(tmp_path, monkeypatch):
    """The startup chime is the bundled one when the user has none, and it is
    handed to the player, not to the speakers. The old version of this test
    played the real chime on every gate run and asserted only that the
    result was a bool."""
    monkeypatch.setenv("HOTROD_STATE_DIR", str(tmp_path / "state"))
    from hotrod_tuner.sound import SoundManager
    played = []
    m = SoundManager(player=lambda f: played.append(f) or True)
    assert m.get_available_sounds() == ["hrt sound.wav"]
    assert m.play_startup_sound(blocking=True) is True
    assert [Path(f).name for f in played] == ["hrt sound.wav"]
    assert Path(played[0]).parent.name == "assets"


def test_metrics_store():
    """Test metrics store basic functionality."""
    from hotrod_tuner.metrics import MetricsStore
    from datetime import datetime, timezone

    store = MetricsStore(max_age_minutes=60, max_points=100)

    # Test storing telemetry
    timestamp = datetime.now(timezone.utc)
    sensors = {"cpu_temp_c": 65.0, "memory_used_mb": 4096}

    store.store_telemetry("test_host", timestamp, sensors)

    # Test retrieving data
    current = store.get_current_status("test_host")
    assert current is not None
    assert current["sensors"]["cpu_temp_c"] == 65.0

    # Test aggregates
    aggregates = store.get_aggregates("test_host", minutes=5)
    assert aggregates is not None
    assert "cpu_temp_c_avg" in aggregates


def test_decision_engine():
    """Test decision engine basic functionality."""
    from hotrod_tuner.policies import DecisionEngine, PolicyConfig

    config = PolicyConfig()
    engine = DecisionEngine(config)

    # Test basic preflight decision
    job = {
        "job_id": "test_job",
        "priority": "normal",
        "resource_intensity": "medium"
    }

    decision = engine.evaluate_preflight(job)
    assert "decision" in decision
    assert "reason" in decision
    assert decision["decision"] in ["approved", "deferred", "require_approval", "denied"]


def test_token_bucket_scheduler():
    """Test scheduler basic functionality."""
    from hotrod_tuner.scheduler import TokenBucketScheduler

    scheduler = TokenBucketScheduler(max_concurrent=2, token_rate=1.0)

    # Test job submission
    job_id = scheduler.submit_job({
        "job_id": "test_job",
        "description": "Test job",
        "priority": 2
    })

    assert job_id == "test_job"

    # Test job approval
    success = scheduler.approve_job(job_id)
    assert success

    # Test job starting
    success = scheduler.start_job(job_id)
    assert success

    # Test status retrieval
    status = scheduler.get_job_status(job_id)
    assert status is not None
    assert status["status"] == "running"

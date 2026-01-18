import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hotrod_tuner import __version__, sound_manager


def test_version():
    assert __version__ == "0.0.1"


def test_sound_manager():
    """Test sound manager functionality."""
    # Test getting available sounds (may be empty if no files present)
    sounds = sound_manager.get_available_sounds()
    assert isinstance(sounds, list)

    # Test sound playback (should not raise exceptions)
    result = sound_manager.play_startup_sound(blocking=True)
    # Result may be False if no sound files exist, which is OK
    assert isinstance(result, bool)


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

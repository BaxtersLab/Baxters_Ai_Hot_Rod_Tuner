"""Policy engine for workload governance decisions."""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone, timedelta
import json


@dataclass
class PolicyConfig:
    """Configuration for governor policies."""

    # Temperature thresholds with hysteresis (°C)
    cpu_temp_threshold: float = 80.0
    cpu_temp_hysteresis: float = 5.0
    gpu_temp_threshold: float = 85.0
    gpu_temp_hysteresis: float = 5.0

    # Resource usage thresholds (%)
    cpu_usage_threshold: float = 90.0
    gpu_usage_threshold: float = 95.0
    memory_usage_threshold: float = 90.0

    # Token bucket settings
    max_concurrent_jobs: int = 2
    token_refresh_rate: int = 1  # tokens per minute
    max_tokens: int = 5

    # Cooldown periods (minutes)
    temp_cooldown_minutes: int = 10
    resource_cooldown_minutes: int = 5

    # Priority classes
    priority_classes: Dict[str, int] = field(default_factory=lambda: {
        'low': 1,
        'normal': 2,
        'high': 3,
        'critical': 4
    })

    # Secure mode settings
    secure_mode: bool = False
    require_approval_above_priority: int = 3


class DecisionEngine:
    """Evaluates telemetry against policies to make governance decisions."""

    def __init__(self, config: PolicyConfig):
        self.config = config
        self._cooldowns: Dict[str, datetime] = {}
        self._active_jobs: Dict[str, Dict[str, Any]] = {}
        self._token_bucket = {
            'tokens': config.max_tokens,
            'last_refresh': datetime.now(timezone.utc)
        }

    def evaluate_preflight(self, job_descriptor: Dict[str, Any],
                          telemetry: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Evaluate a job request against current policies and telemetry.

        Returns: {
            'decision': 'approved|deferred|require_approval|denied',
            'reason': str,
            'cooldown_remaining': int,  # minutes, if applicable
            'tokens_available': int
        }
        """

        job_id = job_descriptor.get('job_id', 'unknown')
        priority = job_descriptor.get('priority', 'normal')
        priority_level = self.config.priority_classes.get(priority, 1)
        resource_intensity = job_descriptor.get('resource_intensity', 'medium')

        # Check secure mode requirements
        if self.config.secure_mode and priority_level >= self.config.require_approval_above_priority:
            return {
                'decision': 'require_approval',
                'reason': f'Secure mode requires approval for priority {priority} jobs',
                'tokens_available': self._token_bucket['tokens']
            }

        # Check cooldown periods
        cooldown_key = f"resource_{resource_intensity}"
        if cooldown_key in self._cooldowns:
            remaining = self._calculate_cooldown_remaining(cooldown_key)
            if remaining > 0:
                return {
                    'decision': 'deferred',
                    'reason': f'Cooldown active for {resource_intensity} intensity jobs',
                    'cooldown_remaining': remaining,
                    'tokens_available': self._token_bucket['tokens']
                }

        # Check temperature thresholds if telemetry available
        if telemetry:
            temp_check = self._check_temperature_thresholds(telemetry)
            if not temp_check['ok']:
                self._set_cooldown('temp_exceeded', self.config.temp_cooldown_minutes)
                return {
                    'decision': 'deferred',
                    'reason': temp_check['reason'],
                    'cooldown_remaining': self.config.temp_cooldown_minutes,
                    'tokens_available': self._token_bucket['tokens']
                }

        # Check token bucket
        self._refresh_tokens()
        if self._token_bucket['tokens'] <= 0:
            return {
                'decision': 'deferred',
                'reason': 'No tokens available in bucket',
                'tokens_available': 0
            }

        # Check concurrent job limits
        active_count = len([j for j in self._active_jobs.values()
                           if j.get('resource_intensity') == resource_intensity])
        if active_count >= self.config.max_concurrent_jobs:
            return {
                'decision': 'deferred',
                'reason': f'Maximum {self.config.max_concurrent_jobs} concurrent {resource_intensity} jobs reached',
                'tokens_available': self._token_bucket['tokens']
            }

        # All checks passed - approve the job
        self._consume_token()
        self._active_jobs[job_id] = {
            'started': datetime.now(timezone.utc),
            'priority': priority,
            'resource_intensity': resource_intensity,
            'descriptor': job_descriptor
        }

        return {
            'decision': 'approved',
            'reason': 'All policy checks passed',
            'tokens_available': self._token_bucket['tokens']
        }

    def job_completed(self, job_id: str):
        """Mark a job as completed and free up resources."""
        if job_id in self._active_jobs:
            del self._active_jobs[job_id]

    def _check_temperature_thresholds(self, telemetry: Dict[str, Any]) -> Dict[str, bool]:
        """Check if temperatures exceed thresholds."""
        sensors = telemetry.get('sensors', {})

        cpu_temp = sensors.get('cpu_temp_c')
        gpu_temp = sensors.get('gpu_temp_c')

        if cpu_temp and cpu_temp > self.config.cpu_temp_threshold:
            return {
                'ok': False,
                'reason': f'CPU temperature {cpu_temp}°C exceeds threshold {self.config.cpu_temp_threshold}°C'
            }

        if gpu_temp and gpu_temp > self.config.gpu_temp_threshold:
            return {
                'ok': False,
                'reason': f'GPU temperature {gpu_temp}°C exceeds threshold {self.config.gpu_temp_threshold}°C'
            }

        return {'ok': True}

    def _refresh_tokens(self):
        """Refresh tokens in the bucket based on time elapsed."""
        now = datetime.now(timezone.utc)
        elapsed = (now - self._token_bucket['last_refresh']).total_seconds() / 60  # minutes

        if elapsed >= 1:  # At least 1 minute passed
            tokens_to_add = int(elapsed * self.config.token_refresh_rate)
            self._token_bucket['tokens'] = min(
                self._token_bucket['tokens'] + tokens_to_add,
                self.config.max_tokens
            )
            self._token_bucket['last_refresh'] = now

    def _consume_token(self):
        """Consume one token from the bucket."""
        if self._token_bucket['tokens'] > 0:
            self._token_bucket['tokens'] -= 1

    def _set_cooldown(self, key: str, minutes: int):
        """Set a cooldown period."""
        self._cooldowns[key] = datetime.now(timezone.utc) + timedelta(minutes=minutes)

    def _calculate_cooldown_remaining(self, key: str) -> int:
        """Calculate remaining cooldown time in minutes."""
        if key not in self._cooldowns:
            return 0

        remaining = self._cooldowns[key] - datetime.now(timezone.utc)
        if remaining.total_seconds() <= 0:
            del self._cooldowns[key]
            return 0

        return int(remaining.total_seconds() / 60)

    def recommend_fan_aggressiveness(self, snapshot) -> int:
        """Return a fan aggressiveness recommendation (0-100) based on CPU temps.

        Uses the CPU-only sensors from a HardwareSnapshot (GPU fans are
        excluded at the fan_manager layer — this method only inspects
        CPU temperature to decide how hard to spin case/CPU fans).

        Recommendation tiers:
          0   — below orange-hysteresis (fans are fine)
          40  — entering orange zone (warm, gentle boost)
          70  — at or above orange threshold (hot, push harder)
          100 — red zone (+10°C above orange) (critical, max fans)

        This value should be max()'d with the user's manual setting so the
        user's higher preference always wins.
        """
        if snapshot is None:
            return 0
        cpu_temps = [
            s.value
            for s in snapshot.sensors
            if s.category == 'temperature' and 'cpu' in s.name.lower() and s.value
        ]
        if not cpu_temps:
            return 0
        peak = max(cpu_temps)
        warm = self.config.cpu_temp_threshold - self.config.cpu_temp_hysteresis
        hot = self.config.cpu_temp_threshold
        critical = hot + 10.0
        if peak >= critical:
            return 100
        if peak >= hot:
            return 70
        if peak >= warm:
            return 40
        return 0

    def get_status(self) -> Dict[str, Any]:
        """Get current governor status."""
        return {
            'active_jobs': len(self._active_jobs),
            'tokens_available': self._token_bucket['tokens'],
            'cooldowns_active': len(self._cooldowns),
            'secure_mode': self.config.secure_mode,
            'job_details': list(self._active_jobs.keys())
        }
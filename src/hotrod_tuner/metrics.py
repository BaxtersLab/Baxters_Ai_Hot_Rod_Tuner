"""Metrics store for time-series telemetry data."""
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
import threading
import json


class MetricsStore:
    """Time-series buffer for telemetry data with rolling aggregates."""

    def __init__(self, max_age_minutes: int = 60, max_points: int = 1000):
        self.max_age = timedelta(minutes=max_age_minutes)
        self.max_points = max_points
        self._data: Dict[str, deque] = {}
        self._lock = threading.RLock()

    def store_telemetry(self, host: str, timestamp: datetime, sensors: Dict[str, Any]):
        """Store telemetry data point."""
        with self._lock:
            if host not in self._data:
                self._data[host] = deque(maxlen=self.max_points)

            data_point = {
                'timestamp': timestamp.isoformat(),
                'sensors': sensors.copy()
            }

            self._data[host].append(data_point)
            self._cleanup_old_data(host)

    def get_recent_metrics(self, host: str, minutes: int = 5) -> List[Dict]:
        """Get recent metrics for a host within the specified time window."""
        with self._lock:
            if host not in self._data:
                return []

            cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
            recent = []

            for point in self._data[host]:
                point_time = datetime.fromisoformat(point['timestamp'])
                if point_time >= cutoff:
                    recent.append(point)
                elif point_time < cutoff:
                    break  # Since deque is ordered, we can stop

            return recent

    def get_aggregates(self, host: str, minutes: int = 5) -> Optional[Dict[str, Any]]:
        """Get rolling aggregates for recent metrics."""
        recent = self.get_recent_metrics(host, minutes)
        if not recent:
            return None

        # Extract sensor values
        sensor_data = {}
        for point in recent:
            for sensor, value in point['sensors'].items():
                if sensor not in sensor_data:
                    sensor_data[sensor] = []
                if isinstance(value, (int, float)):
                    sensor_data[sensor].append(value)

        # Calculate aggregates
        aggregates = {}
        for sensor, values in sensor_data.items():
            if values:
                aggregates[f"{sensor}_avg"] = sum(values) / len(values)
                aggregates[f"{sensor}_max"] = max(values)
                aggregates[f"{sensor}_min"] = min(values)
                aggregates[f"{sensor}_count"] = len(values)

        return aggregates

    def get_current_status(self, host: str) -> Optional[Dict[str, Any]]:
        """Get the most recent telemetry data point."""
        with self._lock:
            if host not in self._data or not self._data[host]:
                return None
            return self._data[host][-1]

    def _cleanup_old_data(self, host: str):
        """Remove data points older than max_age."""
        if host not in self._data:
            return

        cutoff = datetime.now(timezone.utc) - self.max_age
        while self._data[host]:
            point_time = datetime.fromisoformat(self._data[host][0]['timestamp'])
            if point_time < cutoff:
                self._data[host].popleft()
            else:
                break

    def get_all_hosts(self) -> List[str]:
        """Get list of all hosts with stored data."""
        with self._lock:
            return list(self._data.keys())
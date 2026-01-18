"""Scheduler for managing job queues and fairness."""
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timezone, timedelta
from enum import Enum
import threading
import time


class JobStatus(Enum):
    QUEUED = "queued"
    APPROVED = "approved"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    """Represents a scheduled job."""
    job_id: str
    descriptor: Dict[str, Any]
    priority: int
    submitted_at: datetime
    status: JobStatus = JobStatus.QUEUED
    approved_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None


class TokenBucketScheduler:
    """Scheduler with token bucket fairness and priority queues."""

    def __init__(self, max_concurrent: int = 2, token_rate: float = 1.0):
        self.max_concurrent = max_concurrent
        self.token_rate = token_rate  # tokens per second

        self._tokens = max_concurrent * 2  # Start with some tokens
        self._max_tokens = max_concurrent * 2
        self._last_update = time.time()

        self._queues: Dict[int, List[Job]] = {}  # priority -> job list
        self._running_jobs: Dict[str, Job] = {}
        self._completed_jobs: List[Job] = []

        self._lock = threading.RLock()
        self._shutdown = False

    def submit_job(self, job_descriptor: Dict[str, Any]) -> str:
        """Submit a job for scheduling."""
        job_id = job_descriptor.get('job_id') or f"job_{int(time.time() * 1000)}"
        priority = job_descriptor.get('priority', 2)  # Default normal priority

        job = Job(
            job_id=job_id,
            descriptor=job_descriptor,
            priority=priority,
            submitted_at=datetime.now(timezone.utc)
        )

        with self._lock:
            if priority not in self._queues:
                self._queues[priority] = []
            self._queues[priority].append(job)

        return job_id

    def approve_job(self, job_id: str) -> bool:
        """Mark a job as approved and eligible for execution."""
        with self._lock:
            job = self._find_job(job_id)
            if job and job.status == JobStatus.QUEUED:
                job.status = JobStatus.APPROVED
                job.approved_at = datetime.now(timezone.utc)
                return True
        return False

    def start_job(self, job_id: str) -> bool:
        """Start execution of an approved job."""
        with self._lock:
            self._update_tokens()

            # Check if we have capacity and tokens
            if len(self._running_jobs) >= self.max_concurrent:
                return False

            if self._tokens <= 0:
                return False

            job = self._find_job(job_id)
            if job and job.status == JobStatus.APPROVED:
                job.status = JobStatus.RUNNING
                job.started_at = datetime.now(timezone.utc)
                self._running_jobs[job_id] = job
                self._tokens -= 1
                return True

        return False

    def complete_job(self, job_id: str, result: Optional[Dict[str, Any]] = None):
        """Mark a job as completed."""
        with self._lock:
            if job_id in self._running_jobs:
                job = self._running_jobs[job_id]
                job.status = JobStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc)
                job.result = result

                # Return token
                self._tokens = min(self._tokens + 1, self._max_tokens)

                # Move to completed list
                self._completed_jobs.append(job)
                del self._running_jobs[job_id]

                # Keep only recent completed jobs
                if len(self._completed_jobs) > 100:
                    self._completed_jobs.pop(0)

    def cancel_job(self, job_id: str):
        """Cancel a queued or approved job."""
        with self._lock:
            job = self._find_job(job_id)
            if job and job.status in [JobStatus.QUEUED, JobStatus.APPROVED]:
                job.status = JobStatus.CANCELLED
                job.completed_at = datetime.now(timezone.utc)

    def get_next_job(self) -> Optional[Job]:
        """Get the next job eligible for approval (highest priority first)."""
        with self._lock:
            self._update_tokens()

            # Check priorities from highest to lowest
            for priority in sorted(self._queues.keys(), reverse=True):
                queue = self._queues[priority]
                if queue:
                    # Return first job in highest priority queue
                    return queue[0]

        return None

    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific job."""
        with self._lock:
            job = self._find_job(job_id)
            if job:
                return {
                    'job_id': job.job_id,
                    'status': job.status.value,
                    'priority': job.priority,
                    'submitted_at': job.submitted_at.isoformat(),
                    'approved_at': job.approved_at.isoformat() if job.approved_at else None,
                    'started_at': job.started_at.isoformat() if job.started_at else None,
                    'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                    'descriptor': job.descriptor
                }
        return None

    def get_scheduler_status(self) -> Dict[str, Any]:
        """Get overall scheduler status."""
        with self._lock:
            self._update_tokens()

            queued_by_priority = {}
            for priority, jobs in self._queues.items():
                queued_by_priority[priority] = len([j for j in jobs if j.status == JobStatus.QUEUED])

            return {
                'tokens_available': self._tokens,
                'max_tokens': self._max_tokens,
                'running_jobs': len(self._running_jobs),
                'max_concurrent': self.max_concurrent,
                'queued_by_priority': queued_by_priority,
                'total_queued': sum(queued_by_priority.values()),
                'completed_jobs': len(self._completed_jobs)
            }

    def _find_job(self, job_id: str) -> Optional[Job]:
        """Find a job by ID across all queues and running jobs."""
        # Check running jobs
        if job_id in self._running_jobs:
            return self._running_jobs[job_id]

        # Check queues
        for queue in self._queues.values():
            for job in queue:
                if job.job_id == job_id:
                    return job

        # Check completed jobs
        for job in self._completed_jobs:
            if job.job_id == job_id:
                return job

        return None

    def _update_tokens(self):
        """Update token bucket based on elapsed time."""
        now = time.time()
        elapsed = now - self._last_update
        tokens_to_add = elapsed * self.token_rate

        self._tokens = min(self._tokens + tokens_to_add, self._max_tokens)
        self._last_update = now
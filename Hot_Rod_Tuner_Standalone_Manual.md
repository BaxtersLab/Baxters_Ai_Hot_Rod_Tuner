# Baxter's AI Hot Rod Tuner - Standalone Manual

## Table of Contents
1. [Introduction](#introduction)
2. [System Requirements](#system-requirements)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Core Features](#core-features)
6. [Telemetry Collection](#telemetry-collection)
7. [Policy Engine](#policy-engine)
8. [Job Scheduling](#job-scheduling)
9. [Thermal Management](#thermal-management)
10. [Sound System](#sound-system)
11. [API Reference](#api-reference)
12. [Configuration](#configuration)
13. [Monitoring and Logging](#monitoring-and-logging)
14. [Troubleshooting](#troubleshooting)
15. [Advanced Usage](#advanced-usage)

---

## Introduction

### What is Baxter's AI Hot Rod Tuner?

Baxter's AI Hot Rod Tuner is a lightweight governor service designed to protect homelab hardware while enabling strong local AI workflows. It acts as a sophisticated system governor that mediates heavy AI workloads, ensuring hardware safety and maintaining predictable performance.

### Purpose and Philosophy

The Hot Rod Tuner serves as a "responsible adult" for your AI hardware:
- **Hardware Protection**: Prevents overheating and system instability
- **Performance Optimization**: Maintains optimal system performance
- **Resource Governance**: Ensures fair resource allocation
- **Audit Compliance**: Complete audit trail of all decisions

### Key Benefits

- **Hardware Safety**: Automatic protection against thermal runaway
- **Performance Stability**: Consistent performance during AI workloads
- **Resource Efficiency**: Optimal resource utilization
- **Operational Visibility**: Complete audit trail and monitoring
- **Easy Integration**: RESTful API for seamless integration

### Architecture Overview

The Hot Rod Tuner consists of several interconnected components:

- **Telemetry Collector**: Gathers system metrics and sensor data
- **Metrics Store**: Time-series buffer with rolling aggregates
- **Decision Engine**: Evaluates telemetry against policies
- **Scheduler**: Enforces fairness and cooldown windows
- **Enforcement Layer**: Executes protection and optimization actions
- **Audit System**: Complete logging of all decisions and actions

---

## System Requirements

### Minimum Requirements
- **Operating System**: Windows 10/11, Linux (Ubuntu 18.04+), macOS 10.15+
- **RAM**: 4GB minimum, 8GB recommended
- **Storage**: 1GB free space
- **Network**: Local network access (for API access)
- **Python**: 3.8 or higher

### Recommended Requirements
- **RAM**: 16GB or more for heavy AI workloads
- **Storage**: SSD with 5GB+ free space
- **CPU**: Multi-core processor (4+ cores)
- **Cooling**: Adequate system cooling for sustained workloads

### Supported Platforms

#### Windows
- Full hardware monitoring support via LibreHardwareMonitor
- Native Windows API integration
- Sound system support

#### Linux
- `/sys` interface for hardware monitoring
- `lm-sensors` integration
- ALSA sound system support

#### macOS
- IOKit framework integration
- Native macOS sensor APIs
- Core Audio sound support

---

## Installation

### Step 1: Download and Extract

1. Download the Baxter's AI Hot Rod Tuner package
2. Extract to a dedicated directory:
   ```
   C:\BaxtersApps\HotRodTuner\  (Windows)
   /opt/baxters/hotrod-tuner/   (Linux/macOS)
   ```

### Step 2: Install Dependencies

```bash
cd hotrod-tuner-directory
pip install -r requirements.txt
```

#### Optional Dependencies

For enhanced hardware monitoring:

**Windows:**
```bash
pip install pywin32
```

**Linux:**
```bash
sudo apt-get install lm-sensors
pip install psutil
```

### Step 3: Configure Sound Files (Optional)

Create the signature race car engine sound experience:

1. Create directory: `HRT wav sound file/`
2. Place sound file: `engine.wav`
3. Format: WAV, 44.1kHz, stereo, reasonable file size

### Step 4: Initial Configuration

Edit `config.yaml` or set environment variables:

```yaml
# Basic configuration
port: 8080
log_level: info
telemetry_interval: 5
max_concurrent_jobs: 3

# Hardware limits
cpu_limit: 80
memory_limit: 85
temp_limit: 75
```

---

## Quick Start

### Basic Operation

1. **Start the Service:**
   ```bash
   python run_server.py
   ```

2. **Verify Operation:**
   - Open browser to `http://localhost:8080`
   - Check status endpoint: `GET /status`

3. **Test Integration:**
   ```bash
   curl http://localhost:8080/status
   ```

### First AI Job Protection

1. **Submit a Job Request:**
   ```bash
   curl -X POST http://localhost:8080/preflight \
     -H "Content-Type: application/json" \
     -d '{"job_type": "ai_inference", "estimated_duration": 300}'
   ```

2. **Monitor System:**
   - Check temperature and resource usage
   - Review decision in logs
   - Observe protective actions if needed

### Sound System Test

1. **Trigger Startup Sound:**
   - Service automatically plays on startup

2. **Test Sound API:**
   ```bash
   curl -X POST http://localhost:8080/sound/play
   ```

---

## Core Features

### Hardware Protection

#### Temperature Monitoring
- Real-time CPU/GPU temperature tracking
- Configurable thermal thresholds
- Automatic throttling and shutdown protection

#### Resource Limits
- CPU utilization limits
- Memory usage controls
- I/O bandwidth management

#### Process Management
- High-resource process identification
- Graceful process termination
- Emergency kill switches

### Performance Optimization

#### Dynamic Tuning
- CPU frequency optimization
- Memory allocation tuning
- I/O scheduling optimization

#### Workload Classification
- AI inference job detection
- Training workload identification
- Background task prioritization

### Governance Engine

#### Policy-Based Decisions
- Temperature threshold policies
- Resource allocation policies
- Safety enforcement policies

#### Audit Trail
- Complete decision logging
- Action traceability
- Compliance reporting

---

## Telemetry Collection

### Data Sources

#### Hardware Sensors
- **CPU Temperature**: Core and package temperatures
- **GPU Temperature**: Graphics processor monitoring
- **System Temperatures**: Motherboard and peripheral sensors
- **Fan Speeds**: Cooling fan RPM monitoring

#### System Metrics
- **CPU Usage**: Per-core and total utilization
- **Memory Usage**: RAM and swap utilization
- **Disk I/O**: Read/write throughput and latency
- **Network I/O**: Bandwidth usage and connections

#### Process Information
- **Active Processes**: Running process enumeration
- **Resource Usage**: Per-process CPU and memory
- **Thread Counts**: Process threading information

### Collection Methods

#### Polling Intervals
- **Fast Polling**: 1-second intervals for critical metrics
- **Standard Polling**: 5-second intervals for general metrics
- **Slow Polling**: 60-second intervals for trend data

#### Data Retention
- **Short-term**: 1 hour of high-resolution data
- **Medium-term**: 24 hours of aggregated data
- **Long-term**: 7 days of daily summaries

### Telemetry API

#### Ingesting Telemetry
```bash
curl -X POST http://localhost:8080/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "cpu_temp": 65.5,
    "gpu_temp": 72.0,
    "cpu_usage": 78.5,
    "memory_usage": 82.3,
    "timestamp": "2024-01-17T10:30:00Z"
  }'
```

#### Retrieving Telemetry
```bash
curl http://localhost:8080/telemetry?since=2024-01-17T10:00:00Z
```

---

## Policy Engine

### Policy Types

#### Temperature Policies
```yaml
temperature_policies:
  - sensor: "cpu"
    warning_threshold: 70
    critical_threshold: 85
    action: "throttle"
    hysteresis: 5
```

#### Resource Policies
```yaml
resource_policies:
  - resource: "cpu"
    limit: 80
    action: "defer"
    duration: 300
```

#### Job Policies
```yaml
job_policies:
  - job_type: "ai_training"
    max_concurrent: 1
    priority: "high"
    cooldown: 60
```

### Decision Making

#### Approval States
- **APPROVED**: Job can proceed immediately
- **DEFERRED**: Job queued for later execution
- **REQUIRES_APPROVAL**: Human approval needed
- **DENIED**: Job blocked by policy

#### Policy Evaluation
1. **Pre-flight Check**: Evaluate job requirements
2. **Resource Assessment**: Check current system state
3. **Policy Application**: Apply relevant policies
4. **Decision Rendering**: Return approval/denial

### Policy Configuration

#### File-Based Configuration
```yaml
policies:
  temperature:
    cpu_max: 80
    gpu_max: 85
    action: throttle
  resources:
    cpu_limit: 90
    memory_limit: 85
  jobs:
    max_concurrent: 3
    queue_size: 10
```

#### Runtime Policy Updates
```bash
curl -X POST http://localhost:8080/policies \
  -H "Content-Type: application/json" \
  -d '{"policy_type": "temperature", "cpu_max": 75}'
```

---

## Job Scheduling

### Scheduler Architecture

#### Priority Classes
- **Critical**: System protection tasks
- **High**: AI inference and real-time tasks
- **Normal**: Standard workloads
- **Low**: Background maintenance

#### Queue Management
- **Fair Queuing**: Round-robin scheduling
- **Priority Queuing**: High-priority job preference
- **Deadline Scheduling**: Time-sensitive job handling

### Job Submission

#### Basic Job Request
```bash
curl -X POST http://localhost:8080/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "ai_inference_001",
    "job_type": "ai_inference",
    "priority": "high",
    "estimated_duration": 300,
    "resource_requirements": {
      "cpu": 50,
      "memory": 2048
    }
  }'
```

#### Advanced Job Parameters
```json
{
  "job_id": "training_job_001",
  "job_type": "ai_training",
  "priority": "normal",
  "estimated_duration": 3600,
  "resource_requirements": {
    "cpu": 80,
    "memory": 8192,
    "gpu": 1
  },
  "thermal_requirements": {
    "max_temp": 75
  },
  "callbacks": {
    "started": "http://callback.url/started",
    "completed": "http://callback.url/completed",
    "failed": "http://callback.url/failed"
  }
}
```

### Job Monitoring

#### Job Status
```bash
curl http://localhost:8080/jobs/ai_inference_001
```

Response:
```json
{
  "job_id": "ai_inference_001",
  "status": "running",
  "progress": 0.65,
  "start_time": "2024-01-17T10:30:00Z",
  "estimated_completion": "2024-01-17T11:00:00Z"
}
```

#### Queue Status
```bash
curl http://localhost:8080/queue/status
```

---

## Thermal Management

### Sensor Detection

#### Automatic Discovery
```bash
curl -X POST http://localhost:8080/thermal/discover
```

#### Manual Sensor Configuration
```yaml
thermal_sensors:
  - name: "cpu_package"
    type: "temperature"
    location: "/sys/class/thermal/thermal_zone0/temp"
    multiplier: 0.001
  - name: "gpu_core"
    type: "temperature"
    command: "nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader"
```

### Temperature Monitoring

#### Real-time Readings
```bash
curl http://localhost:8080/thermal/status
```

Response:
```json
{
  "sensors": [
    {
      "name": "cpu_package",
      "temperature": 68.5,
      "unit": "celsius",
      "status": "normal"
    },
    {
      "name": "gpu_core",
      "temperature": 72.0,
      "unit": "celsius",
      "status": "warning"
    }
  ],
  "fans": [
    {
      "name": "cpu_fan",
      "speed": 1800,
      "unit": "rpm",
      "status": "active"
    }
  ]
}
```

### Thermal Policies

#### Threshold Configuration
```yaml
thermal_thresholds:
  warning: 70
  critical: 85
  emergency: 95
  hysteresis: 5
```

#### Automated Actions
- **Warning**: Log event and send notification
- **Critical**: Throttle CPU and increase fan speed
- **Emergency**: Terminate processes and prepare shutdown

### Fan Control

#### Fan Speed Management
```bash
curl -X POST http://localhost:8080/fans/control \
  -H "Content-Type: application/json" \
  -d '{"fan": "cpu_fan", "speed": 2000}'
```

#### Automatic Fan Control
- Temperature-based speed adjustment
- PWM control for compatible fans
- Manual override capabilities

---

## Sound System

### Sound File Management

#### Directory Structure
```
hotrod-tuner/
├── HRT wav sound file/
│   ├── engine.wav          # Startup sound
│   ├── throttle.wav        # Throttling sound
│   └── shutdown.wav        # Emergency sound
└── config.yaml
```

#### Sound File Specifications
- **Format**: WAV (uncompressed)
- **Sample Rate**: 44.1kHz recommended
- **Channels**: Stereo or mono
- **Bit Depth**: 16-bit recommended
- **Duration**: 2-5 seconds for startup sound

### Sound Triggers

#### Automatic Triggers
- **Startup**: Plays when service starts
- **Throttling**: Plays when thermal throttling activates
- **Shutdown**: Plays during emergency shutdown
- **Recovery**: Plays when system recovers from critical state

#### Manual Triggers
```bash
# Play startup sound
curl -X POST http://localhost:8080/sound/play/startup

# Play custom sound
curl -X POST http://localhost:8080/sound/play \
  -H "Content-Type: application/json" \
  -d '{"file": "custom.wav"}'
```

### Sound Configuration

#### Volume Control
```yaml
sound:
  enabled: true
  volume: 0.7
  device: "default"
  startup_sound: "HRT wav sound file/engine.wav"
```

#### Audio Device Selection
```bash
# List available audio devices
curl http://localhost:8080/sound/devices

# Set audio device
curl -X POST http://localhost:8080/sound/device \
  -H "Content-Type: application/json" \
  -d '{"device": "alsa_output.pci-0000_00_1f.3.analog-stereo"}'
```

---

## API Reference

### Core Endpoints

#### Status and Health
- `GET /status` - Service health and current metrics
- `GET /health` - Basic health check
- `GET /metrics` - Prometheus-style metrics

#### Telemetry
- `POST /telemetry` - Ingest telemetry data
- `GET /telemetry` - Retrieve telemetry history
- `DELETE /telemetry` - Clear telemetry buffer

#### Job Management
- `POST /preflight` - Evaluate job requirements
- `POST /schedule` - Submit job for execution
- `GET /jobs/{job_id}` - Get job status
- `DELETE /jobs/{job_id}` - Cancel job
- `GET /queue` - Get queue status

#### Thermal Management
- `GET /thermal/status` - Current thermal status
- `POST /thermal/discover` - Discover sensors and fans
- `POST /thermal/thresholds` - Set thermal thresholds
- `POST /fans/control` - Control fan speeds

#### Sound System
- `POST /sound/play` - Play sound effect
- `GET /sound/available` - List available sounds
- `POST /sound/device` - Set audio device

### Authentication

#### API Key Authentication
```bash
curl -H "X-API-Key: your-api-key" http://localhost:8080/status
```

#### Configuration
```yaml
api:
  key: "your-secure-api-key"
  rate_limit: 100
  timeout: 30
```

### Response Formats

#### Success Response
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "timestamp": "2024-01-17T10:30:00Z"
  },
  "request_id": "req_12345"
}
```

#### Error Response
```json
{
  "success": false,
  "error": {
    "code": "THERMAL_SENSOR_ERROR",
    "message": "Failed to read CPU temperature sensor",
    "details": "Sensor /sys/class/thermal/thermal_zone0/temp not accessible"
  },
  "timestamp": "2024-01-17T10:30:00Z",
  "request_id": "req_12345"
}
```

---

## Configuration

### Configuration File

#### Basic Configuration (`config.yaml`)
```yaml
# Server settings
server:
  host: "0.0.0.0"
  port: 8080
  workers: 4

# Logging
logging:
  level: "info"
  file: "logs/hotrod.log"
  max_size: "10MB"
  retention: 7

# Telemetry
telemetry:
  interval: 5
  retention_hours: 24
  buffer_size: 1000

# Policies
policies:
  temperature:
    warning: 70
    critical: 85
    emergency: 95
  resources:
    cpu_limit: 80
    memory_limit: 85
  jobs:
    max_concurrent: 3
    queue_timeout: 300

# Hardware
hardware:
  platform: "auto"  # auto, windows, linux, macos
  sensors: "auto"   # auto, lm-sensors, wmi, iokit

# Sound
sound:
  enabled: true
  directory: "HRT wav sound file"
  startup_sound: "engine.wav"
  volume: 0.7
```

### Environment Variables

#### Override Configuration
```bash
export HOTROD_PORT=9090
export HOTROD_LOG_LEVEL=debug
export HOTROD_MAX_CONCURRENT_JOBS=5
export HOTROD_TEMPERATURE_CRITICAL=90
```

#### Docker Configuration
```bash
docker run -e HOTROD_PORT=8080 \
           -e HOTROD_MAX_MEMORY=85 \
           -v /host/config:/app/config \
           baxters/hotrod-tuner:latest
```

### Runtime Configuration

#### Update Configuration
```bash
curl -X POST http://localhost:8080/config \
  -H "Content-Type: application/json" \
  -d '{"policies.temperature.critical": 90}'
```

#### Reload Configuration
```bash
curl -X POST http://localhost:8080/config/reload
```

---

## Monitoring and Logging

### Log Management

#### Log Levels
- **ERROR**: Critical errors requiring attention
- **WARN**: Warning conditions
- **INFO**: General operational information
- **DEBUG**: Detailed debugging information

#### Log Rotation
- Automatic log rotation at 10MB
- 7-day retention period
- Compressed archival

### Audit Logging

#### Audit Events
- **Policy Decisions**: All approval/denial decisions
- **Thermal Events**: Temperature threshold crossings
- **Resource Actions**: Throttling and termination actions
- **Job Events**: Job scheduling and completion

#### Audit Format
```json
{
  "timestamp": "2024-01-17T10:30:00Z",
  "event_type": "policy_decision",
  "job_id": "ai_job_001",
  "decision": "approved",
  "reason": "within_limits",
  "telemetry": {
    "cpu_temp": 65.5,
    "cpu_usage": 72.3
  }
}
```

### Metrics and Monitoring

#### Prometheus Metrics
```bash
curl http://localhost:8080/metrics
```

#### Key Metrics
- `hotrod_jobs_active`: Number of active jobs
- `hotrod_cpu_temperature`: Current CPU temperature
- `hotrod_memory_usage`: Memory utilization percentage
- `hotrod_decisions_total`: Total policy decisions made

### Alerting

#### Alert Conditions
- Temperature thresholds exceeded
- Resource limits reached
- Job queue full
- Service health degradation

#### Alert Configuration
```yaml
alerts:
  temperature:
    enabled: true
    webhook: "https://alerts.example.com/webhook"
    thresholds:
      - level: "warning"
        value: 75
      - level: "critical"
        value: 90
```

---

## Troubleshooting

### Service Won't Start

#### Common Issues
1. **Port Already in Use**
   ```
   Error: [Errno 48] Address already in use
   ```
   Solution: Change port in config or free port 8080

2. **Permission Denied**
   ```
   Error: Permission denied accessing /sys/class/thermal/
   ```
   Solution: Run with sudo or adjust permissions

3. **Missing Dependencies**
   ```
   ImportError: No module named 'fastapi'
   ```
   Solution: `pip install -r requirements.txt`

#### Startup Verification
```bash
# Check if service is running
curl http://localhost:8080/health

# Check logs
tail -f logs/hotrod.log

# Verify Python environment
python -c "import fastapi, uvicorn; print('Dependencies OK')"
```

### Thermal Sensor Issues

#### Sensors Not Detected
```bash
# Manual sensor discovery
curl -X POST http://localhost:8080/thermal/discover

# Check sensor permissions
ls -la /sys/class/thermal/

# Install lm-sensors (Linux)
sudo apt-get install lm-sensors
sudo sensors-detect
```

#### Inaccurate Readings
- Calibrate sensors against known good readings
- Check for hardware monitoring conflicts
- Update motherboard firmware/BIOS

### Performance Problems

#### High CPU Usage
- Reduce telemetry polling interval
- Disable unnecessary logging
- Check for background processes

#### Memory Leaks
- Monitor memory usage over time
- Check for circular references in custom policies
- Restart service periodically

### Sound Issues

#### No Sound Playback
```bash
# Test audio system
aplay HRT\ wav\ sound\ file/engine.wav

# Check audio devices
aplay -l

# Verify sound file format
file HRT\ wav\ sound\ file/engine.wav
```

#### Distorted Audio
- Check sample rate and format
- Reduce volume setting
- Try different audio device

### Network Issues

#### Connection Refused
- Verify service is running: `ps aux | grep hotrod`
- Check firewall settings
- Confirm correct port and host

#### Slow Responses
- Check system load
- Reduce concurrent connections
- Optimize database queries

---

## Advanced Usage

### Custom Policies

#### Policy Development
```python
from hotrod.policies import BasePolicy

class CustomThermalPolicy(BasePolicy):
    def evaluate(self, telemetry):
        if telemetry.cpu_temp > self.config.get('custom_threshold', 80):
            return 'defer', 'Custom thermal policy triggered'
        return 'approve', None
```

#### Policy Registration
```python
from hotrod.policy_engine import PolicyEngine

engine = PolicyEngine()
engine.register_policy('custom_thermal', CustomThermalPolicy())
```

### Integration Examples

#### Python Integration
```python
import requests

class HotRodClient:
    def __init__(self, base_url="http://localhost:8080"):
        self.base_url = base_url
    
    def check_job(self, job_spec):
        response = requests.post(f"{self.base_url}/preflight", json=job_spec)
        return response.json()
    
    def submit_job(self, job_spec):
        response = requests.post(f"{self.base_url}/schedule", json=job_spec)
        return response.json()
```

#### Docker Integration
```yaml
version: '3.8'
services:
  hotrod-tuner:
    image: baxters/hotrod-tuner:latest
    ports:
      - "8080:8080"
    volumes:
      - ./config:/app/config
      - ./logs:/app/logs
      - ./sounds:/app/HRT wav sound file
    environment:
      - HOTROD_MAX_CONCURRENT_JOBS=5
      - HOTROD_TEMPERATURE_CRITICAL=85
    restart: unless-stopped
```

### Custom Telemetry Sources

#### External Sensor Integration
```python
import requests
from hotrod.telemetry import TelemetryCollector

class ExternalSensorCollector(TelemetryCollector):
    def collect(self):
        # Fetch data from external sensor API
        response = requests.get('http://sensor-api/temperature')
        data = response.json()
        
        return {
            'external_temp': data['temperature'],
            'external_humidity': data['humidity']
        }
```

### High Availability Setup

#### Load Balancing
```nginx
upstream hotrod_cluster {
    server hotrod-01:8080;
    server hotrod-02:8080;
    server hotrod-03:8080;
}

server {
    listen 80;
    location / {
        proxy_pass http://hotrod_cluster;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

#### Database Integration
```python
from hotrod.storage import MetricsStore
import redis

class RedisMetricsStore(MetricsStore):
    def __init__(self):
        self.redis = redis.Redis(host='localhost', port=6379)
    
    def store_metric(self, metric, value, timestamp):
        key = f"hotrod:metrics:{metric}:{timestamp.date()}"
        self.redis.zadd(key, {timestamp.isoformat(): value})
```

### Security Hardening

#### API Security
```yaml
security:
  api_keys:
    - key: "prod-api-key-001"
      permissions: ["read", "write", "admin"]
  rate_limiting:
    requests_per_minute: 60
    burst_limit: 10
  encryption:
    enabled: true
    key_file: "/etc/hotrod/ssl/private.key"
    cert_file: "/etc/hotrod/ssl/certificate.crt"
```

#### Network Security
- Run behind reverse proxy (nginx/caddy)
- Use HTTPS in production
- Implement IP whitelisting
- Regular security audits

---

*For additional support and advanced configuration options, consult the Baxter's technical documentation or contact support.*</content>
<parameter name="filePath">c:\Users\Baxter\Desktop\file cabinet\installed apps\Baxters Ai Hot Rod Tuner\Hot_Rod_Tuner_Standalone_Manual.md
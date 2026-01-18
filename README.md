# Baxters AI Hot Rod Tuner

Purpose: lightweight governor/tuner service to protect homelab hardware while enabling strong local AI workflows.

## Features

- **Telemetry Collection**: CPU, GPU, memory, and temperature monitoring
- **Policy Engine**: Temperature thresholds, token buckets, and cooldown management
- **Job Scheduling**: Priority-based job queuing with fairness controls
- **Audit Logging**: Complete audit trail of all decisions and actions
- **Sound Effects**: Race car engine sound plays on startup and panel activation
- **Web Integration**: Seamless integration with Baxter SOC interface

## Sound System

The Hot Rod Tuner includes an integrated sound system that plays a race car engine sound:

- **Startup Sound**: Plays when the standalone Hot Rod Tuner server starts
- **Panel Activation**: Plays when the Hot Rod Tuner panel is opened in SOC
- **Sound Files**: Place WAV files in the `HRT wav sound file/` directory
- **Fallback**: Graceful fallback to text messages if sound is unavailable

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Add sound files (optional):
   ```bash
   # Place your race car engine sound in:
   # HRT wav sound file/engine.wav
   ```

3. Start the server:
   ```bash
   python run_server.py
   ```

4. Access the API at: http://localhost:8080

## API Endpoints

- `GET /status` - Current governor status
- `POST /telemetry` - Ingest telemetry data
- `POST /preflight` - Evaluate job requests
- `POST /schedule` - Submit jobs to scheduler
- `POST /sound/play` - Trigger sound playback
- `GET /sound/available` - List available sound files

## Integration with SOC

The Hot Rod Tuner integrates with Baxter SOC through:

- **Capability Registry**: All features registered as SOC capabilities
- **Web Proxy**: SOC web server proxies Hot Rod API calls
- **Sound Triggers**: Panel activation triggers sound playback
- **Status Monitoring**: Real-time status display in SOC interface

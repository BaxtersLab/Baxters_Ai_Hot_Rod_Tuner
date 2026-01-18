import uvicorn
import os
from hotrod_tuner.sound import sound_manager

if __name__ == "__main__":
    # Play startup sound when server starts
    print("🚗 Starting Hot Rod Tuner...")
    sound_manager.play_startup_sound(blocking=False)

    host = os.getenv("HOTROD_HOST", "127.0.0.1")
    port = int(os.getenv("HOTROD_PORT", "8080"))

    print(f"🔧 Hot Rod Tuner server starting on {host}:{port}")
    uvicorn.run("hotrod_tuner.app:app", host=host, port=port, reload=False)
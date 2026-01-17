import uvicorn
import os

if __name__ == "__main__":
    host = os.getenv("HOTROD_HOST", "127.0.0.1")
    port = int(os.getenv("HOTROD_PORT", "8080"))
    uvicorn.run("hotrod_tuner.app:app", host=host, port=port, reload=False)
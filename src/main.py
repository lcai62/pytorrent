import sys
from pathlib import Path

import uvicorn

from . import fastapi_server

sys.path.append(str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    uvicorn.run(
        fastapi_server.app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        lifespan="on"
    )

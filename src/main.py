import uvicorn

import fastapi_server

if __name__ == "__main__":
    uvicorn.run(
        fastapi_server.app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        lifespan="on"
    )

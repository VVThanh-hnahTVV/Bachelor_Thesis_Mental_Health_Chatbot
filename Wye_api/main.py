from app_factory import create_app
from socket_server import create_socket_app
import uvicorn

fastapi_app = create_app()
app = create_socket_app(fastapi_app)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
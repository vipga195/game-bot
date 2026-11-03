import sys

import uvicorn

from .app import create_app, create_user

if __name__ == "__main__":
    app = create_app()
    if len(sys.argv) == 3 and sys.argv[1] == "create-user":
        print(create_user(app.state.engine, sys.argv[2]))  # token is shown once
    else:
        uvicorn.run(app, host="127.0.0.1", port=8100)

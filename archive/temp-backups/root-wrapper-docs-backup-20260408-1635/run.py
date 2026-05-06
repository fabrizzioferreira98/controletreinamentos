import os

from src.app import create_app


app = create_app()


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0").strip().lower() in {"1", "true", "yes", "on"}
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=debug)

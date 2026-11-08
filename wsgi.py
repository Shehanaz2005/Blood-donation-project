"""WSGI entry point for production servers (waitress/gunicorn)."""
from app import create_app

app = create_app("production")

if __name__ == "__main__":
    app.run()

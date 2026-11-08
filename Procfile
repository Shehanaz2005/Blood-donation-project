release: flask --app run.py db upgrade
web: waitress-serve --listen=0.0.0.0:$PORT wsgi:app

"""
Point d'entrée WSGI pour Gunicorn en production.

Usage :
    gunicorn --config deploy/gunicorn.conf.py wsgi:application

Le thread RFID et le lecteur VLC sont initialisés une seule fois
dans create_app(), au démarrage du worker.
"""
from app import create_app

application = create_app()

"""
Point d'entrée de Baby Jukebox.
Lance l'application Flask avec le thread RFID et le lecteur VLC.

Usage :
    python main.py
"""
from app import create_app

if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=5001, debug=False, use_reloader=False)

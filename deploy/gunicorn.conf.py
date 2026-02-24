"""
Configuration Gunicorn pour Baby Jukebox sur Raspberry Pi.

IMPORTANT — workers=1 obligatoire :
  L'application maintient un état global en mémoire (lecteur VLC,
  thread RFID, dernier tag scanné). Plusieurs workers = plusieurs
  processus séparés → état incohérent. On compense par plusieurs
  threads pour la concurrence HTTP.
"""

import multiprocessing
import os

# ---------------------------------------------------------------------------
# Serveur
# ---------------------------------------------------------------------------
bind = "0.0.0.0:5000"          # Accessible directement sur le réseau local
backlog = 64

# ---------------------------------------------------------------------------
# Workers  — NE PAS AUGMENTER workers au-delà de 1
# ---------------------------------------------------------------------------
workers = 1                     # Un seul processus (état global partagé)
threads = 4                     # Concurrence HTTP via threads
worker_class = "gthread"        # Mode multi-thread (compatible avec daemon threads)
worker_tmp_dir = "/dev/shm"     # RAM tmpfs pour le heartbeat worker (plus rapide)

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
timeout = 120                   # Secondes avant de tuer un worker bloqué
graceful_timeout = 30           # Temps pour finir les requêtes en cours à l'arrêt
keepalive = 5

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
loglevel = "info"
accesslog = "/var/log/baby-jukebox/access.log"
errorlog  = "/var/log/baby-jukebox/error.log"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s %(D)sµs'

# ---------------------------------------------------------------------------
# Process
# ---------------------------------------------------------------------------
proc_name = "baby-jukebox"
# Pas de pidfile : systemd gère le processus directement via son PID,
# inutile d'écrire dans /run (qui est un tmpfs effacé au reboot)

# ---------------------------------------------------------------------------
# Hooks de cycle de vie
# ---------------------------------------------------------------------------

def on_starting(server):
    """Appelé une fois au démarrage du master Gunicorn."""
    os.makedirs("/var/log/baby-jukebox", exist_ok=True)
    os.makedirs("/run/baby-jukebox", exist_ok=True)
    server.log.info("Baby Jukebox démarrage…")


def worker_exit(server, worker):
    """Log quand un worker s'arrête (crash ou redémarrage)."""
    server.log.warning(f"Worker {worker.pid} terminé")


def on_exit(server):
    server.log.info("Baby Jukebox arrêté proprement.")

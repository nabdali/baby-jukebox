"""
Thread daemon de lecture RFID (RC522 via SPI/spidev).

Fonctionnement :
  - Tourne en boucle dans un thread daemon (ne bloque pas Flask).
  - Si un tag est détecté, appelle on_tag_detected(rfid_id: str).
  - Si mfrc522 n'est pas disponible (dev sur PC), passe en mode mock
    qui n'appelle jamais le callback (simulation silencieuse).

Optimisation réactivité :
  - Utilise l'API bas-niveau MFRC522 (Request + Anticoll) pour lire
    uniquement l'UID du tag, SANS authentification ni lecture de données.
  - Élimine les AUTH ERROR et les boucles de retry associées.
  - Détection quasi-instantanée (< 300 ms typiquement).
"""

from __future__ import annotations

import threading
import time
import logging

logger = logging.getLogger(__name__)

# Intervalle de polling entre deux tentatives de détection
_POLL_INTERVAL = 0.1


class RFIDReader:
    def __init__(self, on_tag_detected):
        """
        :param on_tag_detected: callable(rfid_id: str)
            Appelé dans le thread RFID (pas dans le thread Flask).
            Doit être thread-safe.
        """
        self._callback = on_tag_detected
        self._thread = threading.Thread(target=self._run, daemon=True, name="rfid-reader")
        self._running = False
        self._last_triggered_id: str | None = None  # dernier UID ayant déclenché le callback

    def start(self):
        self._running = True
        self._thread.start()
        logger.info("Thread RFID démarré")

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------

    def _run(self):
        try:
            import RPi.GPIO as GPIO  # type: ignore
            GPIO.setwarnings(False)
            from mfrc522 import MFRC522  # type: ignore
        except ImportError:
            logger.warning(
                "mfrc522 non disponible — thread RFID en mode mock. "
                "Normal en dehors d'un Raspberry Pi."
            )
            while self._running:
                time.sleep(5.0)
            return

        # Boucle de tentatives d'initialisation : réessaie si /dev/gpiomem
        # n'est pas encore accessible (ex: service démarré avant udev).
        reader = None
        while self._running and reader is None:
            try:
                reader = MFRC522()
                logger.info("RC522 initialisé (mode réel, lecture UID uniquement)")
            except RuntimeError as e:
                logger.error(
                    f"Impossible d'initialiser GPIO/SPI : {e} — "
                    "Vérifiez que l'utilisateur est dans le groupe 'gpio' "
                    "et que /dev/gpiomem est accessible. Nouvel essai dans 10s…"
                )
                time.sleep(10.0)

        while self._running:
            try:
                # Étape 1 : cherche un tag dans le champ (REQA/WUPA)
                (status, _tag_type) = reader.MFRC522_Request(reader.PICC_REQIDL)

                if status == reader.MI_OK:
                    # Étape 2 : récupère l'UID par anticollision — pas d'auth !
                    (status, uid) = reader.MFRC522_Anticoll()

                    if status == reader.MI_OK and uid:
                        # Convertit la liste d'octets en entier décimal
                        # (même format que SimpleMFRC522 pour la compatibilité DB)
                        n = 0
                        for byte in uid[:5]:
                            n = n * 256 + byte
                        tag_str = str(n)

                        # Déclenche uniquement si l'UID est différent du dernier
                        # tag ayant déclenché le callback — même tag retiré/reposé = silence
                        if tag_str != self._last_triggered_id:
                            self._last_triggered_id = tag_str
                            logger.info(f"Tag détecté : {tag_str}")
                            self._callback(tag_str)

            except Exception as e:
                logger.error(f"Erreur lecture RFID : {e}")
                time.sleep(1.0)

            time.sleep(_POLL_INTERVAL)

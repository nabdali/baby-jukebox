"""
Thread daemon de lecture RFID (RC522 via SPI/spidev).

Fonctionnement :
  - Tourne en boucle dans un thread daemon (ne bloque pas Flask).
  - Si un tag est détecté, appelle on_tag_detected(rfid_id: str).
  - Si mfrc522 n'est pas disponible (dev sur PC), passe en mode mock
    qui n'appelle jamais le callback (simulation silencieuse).
"""

from __future__ import annotations

import threading
import time
import logging

logger = logging.getLogger(__name__)

# Délai de rebond : évite de déclencher plusieurs fois le même tag
_DEBOUNCE_SECONDS = 2.0
# Intervalle de polling quand aucun tag n'est présent
_POLL_INTERVAL = 0.3


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
        self._last_id: str | None = None
        self._last_seen: float = 0.0

    def start(self):
        self._running = True
        self._thread.start()
        logger.info("Thread RFID démarré")

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------

    def _run(self):
        try:
            from mfrc522 import SimpleMFRC522  # type: ignore

            reader = SimpleMFRC522()
            logger.info("RC522 initialisé (mode réel)")

            while self._running:
                try:
                    rfid_id, _ = reader.read_no_block()
                    if rfid_id is not None:
                        tag_str = str(rfid_id).strip()
                        now = time.monotonic()
                        # Debounce : ignore le même tag pendant _DEBOUNCE_SECONDS
                        if tag_str != self._last_id or (now - self._last_seen) > _DEBOUNCE_SECONDS:
                            self._last_id = tag_str
                            self._last_seen = now
                            logger.info(f"Tag détecté : {tag_str}")
                            self._callback(tag_str)
                except Exception as e:
                    logger.error(f"Erreur lecture RFID : {e}")
                    time.sleep(1.0)

                time.sleep(_POLL_INTERVAL)

        except ImportError:
            logger.warning(
                "mfrc522 non disponible — le thread RFID tourne en mode mock (aucun tag ne sera détecté). "
                "Normal en environnement de développement hors Raspberry Pi."
            )
            # Boucle inactive — le thread reste vivant mais ne fait rien
            while self._running:
                time.sleep(5.0)

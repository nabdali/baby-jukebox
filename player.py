import threading
import logging
import os

logger = logging.getLogger(__name__)


class Player:
    """
    Wrapper autour de python-vlc.
    Gère la lecture d'un fichier unique et des playlists.
    Thread-safe via un verrou interne.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._instance = None
        self._media_player = None
        self._list_player = None
        self._current_playlist: list[str] = []
        self._init_vlc()

    def _init_vlc(self):
        try:
            import vlc  # type: ignore

            # '--aout=alsa' force la sortie jack sur Raspberry Pi
            self._instance = vlc.Instance("--no-xlib", "--aout=alsa")
            self._media_player = self._instance.media_player_new()
            self._list_player = self._instance.media_list_player_new()
            self._list_player.set_media_player(self._media_player)
            logger.info("VLC initialisé avec succès")
        except Exception as e:
            logger.error(f"Impossible d'initialiser VLC : {e}")

    # ------------------------------------------------------------------
    # Lecture
    # ------------------------------------------------------------------

    def play_file(self, file_path: str) -> bool:
        """Lance la lecture d'un fichier audio unique."""
        if not self._media_player:
            logger.warning("VLC non disponible")
            return False
        if not os.path.isfile(file_path):
            logger.error(f"Fichier introuvable : {file_path}")
            return False

        with self._lock:
            import vlc  # type: ignore

            # Arrête une éventuelle playlist en cours
            self._list_player.stop()

            media = self._instance.media_new(file_path)
            self._media_player.set_media(media)
            self._media_player.play()
            self._current_playlist = [file_path]
            logger.info(f"Lecture : {file_path}")
        return True

    def play_playlist(self, file_paths: list[str]) -> bool:
        """Lance la lecture d'une liste de fichiers audio."""
        if not self._list_player:
            logger.warning("VLC non disponible")
            return False

        valid = [p for p in file_paths if os.path.isfile(p)]
        if not valid:
            logger.error("Aucun fichier valide dans la playlist")
            return False

        with self._lock:
            media_list = self._instance.media_list_new(valid)
            self._list_player.set_media_list(media_list)
            self._list_player.play()
            self._current_playlist = valid
            logger.info(f"Playlist lancée : {len(valid)} pistes")
        return True

    # ------------------------------------------------------------------
    # Contrôles
    # ------------------------------------------------------------------

    def pause(self):
        """Basculer pause / reprise."""
        if self._media_player:
            with self._lock:
                self._media_player.pause()

    def stop(self):
        """Arrêter toute lecture."""
        if self._media_player:
            with self._lock:
                self._media_player.stop()
                self._list_player.stop()
                self._current_playlist = []

    def next_track(self):
        """Piste suivante (uniquement en mode playlist)."""
        if self._list_player:
            with self._lock:
                self._list_player.next()

    def prev_track(self):
        """Piste précédente (uniquement en mode playlist)."""
        if self._list_player:
            with self._lock:
                self._list_player.previous()

    # ------------------------------------------------------------------
    # État
    # ------------------------------------------------------------------

    def get_state(self) -> str:
        """Retourne l'état VLC sous forme de chaîne : Playing, Paused, Stopped…"""
        if not self._media_player:
            return "Unavailable"
        state = self._media_player.get_state()
        # Enum vlc.State -> str : "State.Playing" → "Playing"
        return str(state).split(".")[-1]

    def get_current_media_name(self) -> str | None:
        """Retourne le nom du fichier en cours de lecture, ou None."""
        if not self._media_player:
            return None
        media = self._media_player.get_media()
        if media:
            mrl = media.get_mrl()
            # Convertit 'file:///path/to/file.mp3' en 'file.mp3'
            return os.path.basename(mrl.replace("file://", ""))
        return None

    def get_time_info(self) -> dict:
        """Retourne la position et la durée en secondes."""
        if not self._media_player:
            return {"time": 0, "duration": 0, "position": 0.0}
        return {
            "time": max(0, self._media_player.get_time() // 1000),
            "duration": max(0, self._media_player.get_length() // 1000),
            "position": round(self._media_player.get_position(), 3),
        }

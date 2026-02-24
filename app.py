"""
Baby Jukebox — Application principale Flask.

Démarre :
  1. La base de données SQLite via SQLAlchemy
  2. Le lecteur audio VLC
  3. Le thread daemon RFID RC522
  4. Le serveur Flask
"""

from __future__ import annotations

import os
import logging
from pathlib import Path

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
)
from werkzeug.utils import secure_filename

from models import db, Audio, Playlist, Tag
from player import Player
from rfid_reader import RFIDReader

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
ALLOWED_EXTENSIONS = {"mp3", "ogg", "wav", "flac", "m4a"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "baby-jukebox-dev-secret")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{BASE_DIR / 'jukebox.db'}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 Mo max par upload

db.init_app(app)

# ---------------------------------------------------------------------------
# Singletons partagés entre Flask et le thread RFID
# ---------------------------------------------------------------------------

player = Player()

# Dernier tag RFID scanné qui n'est pas encore assigné en base
_last_unassigned_tag: str | None = None


def on_tag_detected(rfid_id: str):
    """
    Callback appelé par le thread RFID.
    Vérifie si le tag est en base ; si oui, lance la lecture.
    Sinon, mémorise l'ID pour la page d'association.
    """
    global _last_unassigned_tag

    with app.app_context():
        tag = Tag.query.filter_by(rfid_id=rfid_id).first()
        if tag:
            if tag.audio_id and tag.audio:
                path = audio_abs_path(tag.audio.file_path)
                if not os.path.isfile(path):
                    logger.error(f"Tag {rfid_id} → fichier introuvable : {path}")
                    return
                logger.info(f"Tag {rfid_id} → lecture audio '{tag.audio.name}' ({path})")
                player.play_file(path)
            elif tag.playlist_id and tag.playlist:
                files = [audio_abs_path(a.file_path) for a in tag.playlist.audios]
                missing = [f for f in files if not os.path.isfile(f)]
                if missing:
                    logger.warning(f"Playlist : {len(missing)} fichier(s) introuvable(s) : {missing}")
                files = [f for f in files if os.path.isfile(f)]
                if not files:
                    logger.error(f"Tag {rfid_id} → playlist '{tag.playlist.name}' vide ou tous les fichiers manquants")
                    return
                logger.info(f"Tag {rfid_id} → lecture playlist '{tag.playlist.name}' ({len(files)} pistes)")
                player.play_playlist(files)
            else:
                logger.warning(f"Tag {rfid_id} en base mais sans audio ni playlist associé")
        else:
            logger.info(f"Tag inconnu : {rfid_id} — mémorisé pour assignation")
            _last_unassigned_tag = rfid_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def audio_abs_path(file_path: str) -> str:
    """
    Retourne le chemin absolu d'un fichier audio.

    La base de données stocke désormais uniquement le nom du fichier (ex: 'titre.mp3').
    Cette fonction préfixe UPLOAD_FOLDER pour obtenir le chemin complet.

    Rétrocompatibilité : si file_path est déjà un chemin absolu valide
    (anciens enregistrements), il est retourné tel quel.
    """
    p = Path(file_path)
    if p.is_absolute():
        return str(p)
    return str(UPLOAD_FOLDER / p)


# ---------------------------------------------------------------------------
# Routes — Accueil / Lecteur
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    state = player.get_state()
    media_name = player.get_current_media_name()
    time_info = player.get_time_info()
    return render_template(
        "index.html",
        state=state,
        media_name=media_name,
        time_info=time_info,
    )


@app.route("/player/pause", methods=["POST"])
def player_pause():
    player.pause()
    return redirect(url_for("index"))


@app.route("/player/stop", methods=["POST"])
def player_stop():
    player.stop()
    return redirect(url_for("index"))


@app.route("/player/next", methods=["POST"])
def player_next():
    player.next_track()
    return redirect(url_for("index"))


@app.route("/player/prev", methods=["POST"])
def player_prev():
    player.prev_track()
    return redirect(url_for("index"))


@app.route("/play/audio/<int:audio_id>", methods=["POST"])
def play_audio(audio_id: int):
    audio = db.get_or_404(Audio, audio_id)
    path = audio_abs_path(audio.file_path)
    if not os.path.isfile(path):
        flash(f"Fichier introuvable : {path}", "error")
        return redirect(url_for("upload"))
    player.play_file(path)
    flash(f"Lecture : {audio.name}", "success")
    return redirect(url_for("index"))


@app.route("/play/playlist/<int:playlist_id>", methods=["POST"])
def play_playlist(playlist_id: int):
    playlist = db.get_or_404(Playlist, playlist_id)
    files = [audio_abs_path(a.file_path) for a in playlist.audios if os.path.isfile(audio_abs_path(a.file_path))]
    if not files:
        flash(f"Aucune piste disponible dans '{playlist.name}'.", "error")
        return redirect(url_for("playlists"))
    player.play_playlist(files)
    flash(f"Lecture playlist : {playlist.name} ({len(files)} pistes)", "success")
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Routes — API JSON (polling JS)
# ---------------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    """Retourne l'état du lecteur en JSON pour le polling JS."""
    return jsonify(
        state=player.get_state(),
        media=player.get_current_media_name(),
        **player.get_time_info(),
    )


@app.route("/api/last-tag")
def api_last_tag():
    """Retourne le dernier tag non assigné détecté."""
    return jsonify(tag_id=_last_unassigned_tag)


@app.route("/api/clear-last-tag", methods=["POST"])
def api_clear_last_tag():
    global _last_unassigned_tag
    _last_unassigned_tag = None
    return jsonify(ok=True)


# ---------------------------------------------------------------------------
# Routes — Upload
# ---------------------------------------------------------------------------

@app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "POST":
        files = request.files.getlist("files")
        if not files or all(f.filename == "" for f in files):
            flash("Aucun fichier sélectionné.", "error")
            return redirect(request.url)

        saved = 0
        for file in files:
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                dest = UPLOAD_FOLDER / filename
                # Évite les doublons de fichier sur disque
                counter = 1
                stem = dest.stem
                while dest.exists():
                    dest = UPLOAD_FOLDER / f"{stem}_{counter}{dest.suffix}"
                    counter += 1

                file.save(str(dest))

                # Stocke uniquement le nom de fichier (portable entre machines)
                # audio_abs_path() reconstituera le chemin complet à la lecture
                if not Audio.query.filter_by(file_path=dest.name).first():
                    audio = Audio(
                        name=dest.stem.replace("_", " ").replace("-", " "),
                        file_path=dest.name,
                    )
                    db.session.add(audio)
                    saved += 1

        db.session.commit()
        flash(f"{saved} fichier(s) importé(s) avec succès.", "success")
        return redirect(url_for("upload"))

    audios = Audio.query.order_by(Audio.name).all()
    return render_template("upload.html", audios=audios)


@app.route("/audio/<int:audio_id>/delete", methods=["POST"])
def delete_audio(audio_id: int):
    audio = db.get_or_404(Audio, audio_id)
    # Supprime le fichier physique
    try:
        Path(audio_abs_path(audio.file_path)).unlink(missing_ok=True)
    except Exception as e:
        logger.warning(f"Impossible de supprimer le fichier {audio.file_path} : {e}")
    db.session.delete(audio)
    db.session.commit()
    flash(f"'{audio.name}' supprimé.", "success")
    return redirect(url_for("upload"))


# ---------------------------------------------------------------------------
# Routes — Playlists
# ---------------------------------------------------------------------------

@app.route("/playlists")
def playlists():
    all_playlists = Playlist.query.order_by(Playlist.name).all()
    all_audios = Audio.query.order_by(Audio.name).all()
    return render_template("playlists.html", playlists=all_playlists, audios=all_audios)


@app.route("/playlists/create", methods=["POST"])
def create_playlist():
    name = request.form.get("name", "").strip()
    if not name:
        flash("Le nom de la playlist est requis.", "error")
        return redirect(url_for("playlists"))

    audio_ids = request.form.getlist("audio_ids")
    playlist = Playlist(name=name)
    for aid in audio_ids:
        audio = db.session.get(Audio, int(aid))
        if audio:
            playlist.audios.append(audio)

    db.session.add(playlist)
    db.session.commit()
    flash(f"Playlist '{name}' créée avec {len(playlist.audios)} piste(s).", "success")
    return redirect(url_for("playlists"))


@app.route("/playlists/<int:playlist_id>/delete", methods=["POST"])
def delete_playlist(playlist_id: int):
    playlist = db.get_or_404(Playlist, playlist_id)
    db.session.delete(playlist)
    db.session.commit()
    flash(f"Playlist '{playlist.name}' supprimée.", "success")
    return redirect(url_for("playlists"))


@app.route("/playlists/<int:playlist_id>/edit", methods=["GET", "POST"])
def edit_playlist(playlist_id: int):
    playlist = db.get_or_404(Playlist, playlist_id)
    all_audios = Audio.query.order_by(Audio.name).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if name:
            playlist.name = name
        audio_ids = request.form.getlist("audio_ids")
        playlist.audios = []
        for aid in audio_ids:
            audio = db.session.get(Audio, int(aid))
            if audio:
                playlist.audios.append(audio)
        db.session.commit()
        flash(f"Playlist '{playlist.name}' mise à jour.", "success")
        return redirect(url_for("playlists"))

    return render_template("edit_playlist.html", playlist=playlist, audios=all_audios)


# ---------------------------------------------------------------------------
# Routes — Association RFID
# ---------------------------------------------------------------------------

@app.route("/assign")
def assign():
    tags = Tag.query.order_by(Tag.rfid_id).all()
    audios = Audio.query.order_by(Audio.name).all()
    all_playlists = Playlist.query.order_by(Playlist.name).all()
    return render_template(
        "assign.html",
        tags=tags,
        audios=audios,
        playlists=all_playlists,
        last_tag=_last_unassigned_tag,
    )


@app.route("/assign/save", methods=["POST"])
def save_assignment():
    rfid_id = request.form.get("rfid_id", "").strip()
    target_type = request.form.get("target_type")  # "audio" ou "playlist"
    target_id = request.form.get("target_id", type=int)

    if not rfid_id:
        flash("ID RFID manquant.", "error")
        return redirect(url_for("assign"))

    tag = Tag.query.filter_by(rfid_id=rfid_id).first() or Tag(rfid_id=rfid_id)

    if target_type == "audio":
        tag.audio_id = target_id
        tag.playlist_id = None
    elif target_type == "playlist":
        tag.playlist_id = target_id
        tag.audio_id = None
    else:
        flash("Type de cible invalide.", "error")
        return redirect(url_for("assign"))

    db.session.add(tag)
    db.session.commit()

    # Efface le dernier tag non assigné s'il correspond
    global _last_unassigned_tag
    if _last_unassigned_tag == rfid_id:
        _last_unassigned_tag = None

    flash(f"Tag {rfid_id} associé avec succès.", "success")
    return redirect(url_for("assign"))


@app.route("/assign/<int:tag_id>/delete", methods=["POST"])
def delete_tag(tag_id: int):
    tag = db.get_or_404(Tag, tag_id)
    rfid = tag.rfid_id
    db.session.delete(tag)
    db.session.commit()
    flash(f"Association du tag {rfid} supprimée.", "success")
    return redirect(url_for("assign"))


# ---------------------------------------------------------------------------
# Démarrage
# ---------------------------------------------------------------------------

def create_app():
    UPLOAD_FOLDER.mkdir(exist_ok=True)
    with app.app_context():
        db.create_all()
        logger.info("Base de données initialisée")

    rfid = RFIDReader(on_tag_detected=on_tag_detected)
    rfid.start()

    return app


if __name__ == "__main__":
    create_app()
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

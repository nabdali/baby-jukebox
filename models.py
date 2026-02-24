from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Table d'association Many-to-Many Playlist <-> Audio
playlist_audio = db.Table(
    "playlist_audio",
    db.Column("playlist_id", db.Integer, db.ForeignKey("playlist.id"), primary_key=True),
    db.Column("audio_id", db.Integer, db.ForeignKey("audio.id"), primary_key=True),
)


class Audio(db.Model):
    __tablename__ = "audio"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    file_path = db.Column(db.String(500), nullable=False, unique=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "file_path": self.file_path}


class Playlist(db.Model):
    __tablename__ = "playlist"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    audios = db.relationship("Audio", secondary=playlist_audio, backref="playlists", lazy="select")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "audios": [a.to_dict() for a in self.audios],
        }


class Tag(db.Model):
    __tablename__ = "tag"

    id = db.Column(db.Integer, primary_key=True)
    rfid_id = db.Column(db.String(100), unique=True, nullable=False)
    audio_id = db.Column(db.Integer, db.ForeignKey("audio.id"), nullable=True)
    playlist_id = db.Column(db.Integer, db.ForeignKey("playlist.id"), nullable=True)

    audio = db.relationship("Audio", backref="tags")
    playlist = db.relationship("Playlist", backref="tags")

    def to_dict(self):
        return {
            "id": self.id,
            "rfid_id": self.rfid_id,
            "audio_id": self.audio_id,
            "playlist_id": self.playlist_id,
            "label": self.audio.name if self.audio else (self.playlist.name if self.playlist else None),
            "type": "audio" if self.audio_id else ("playlist" if self.playlist_id else None),
        }

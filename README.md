# Baby Jukebox

Lecteur de musique RFID pour Raspberry Pi. Approchez un tag NFC/RFID du lecteur RC522, la musique part. Interface web pour tout gérer depuis un téléphone.

---

## Table des matières

1. [Matériel requis](#matériel-requis)
2. [Câblage RC522](#câblage-rc522)
3. [Stack technique](#stack-technique)
4. [Structure du projet](#structure-du-projet)
5. [Getting Started](#getting-started)
   - [Prérequis](#prérequis)
   - [Installation automatisée](#installation-automatisée)
   - [Installation manuelle (développement)](#installation-manuelle-développement)
6. [Déploiement comme service Linux](#déploiement-comme-service-linux)
7. [Référence des commandes](#référence-des-commandes)
   - [Service systemd](#service-systemd)
   - [Logs](#logs)
   - [Audio](#audio)
   - [Mise à jour de l'application](#mise-à-jour-de-lapplication)
   - [Base de données](#base-de-données)
   - [Debug et diagnostic](#debug-et-diagnostic)
8. [Configuration](#configuration)
9. [Pages de l'interface web](#pages-de-linterface-web)
10. [Architecture](#architecture)
11. [Dépannage](#dépannage)

---

## Matériel requis

| Composant | Détail |
|---|---|
| Raspberry Pi | 3B / 3B+ / 4 / Zero 2W (Raspberry Pi OS Lite recommandé) |
| Module RFID | RC522 (MFRC522) — interface SPI |
| Tags RFID | Cartes ou stickers ISO 13.56 MHz (MIFARE Classic/Ultralight) |
| Carte SD | 8 Go minimum (16 Go recommandé) |
| Sortie audio | Prise jack 3.5mm ou USB DAC |
| Alimentation | 5V / 2.5A minimum |

---

## Câblage RC522

Le module RC522 se connecte via le bus **SPI0** du Raspberry Pi.

```
RC522 (module)          Raspberry Pi GPIO
─────────────────────── ─────────────────────────────
VCC  (3.3V)      ───→   Pin 1   (3.3V)     ⚠ 3.3V UNIQUEMENT, jamais 5V
GND              ───→   Pin 6   (GND)
MISO             ───→   Pin 21  (GPIO 9  / SPI0_MISO)
MOSI             ───→   Pin 19  (GPIO 10 / SPI0_MOSI)
SCK              ───→   Pin 23  (GPIO 11 / SPI0_SCLK)
SDA (SS/CS)      ───→   Pin 24  (GPIO 8  / SPI0_CE0)
RST              ───→   Pin 22  (GPIO 25)
IRQ              ───→   Non connecté
```

**Vue du connecteur GPIO (côté Pi) :**

```
    3.3V [1] [2] 5V
     SDA [3] [4] 5V
     SCL [5] [6] GND ←── RC522 GND
      —  [7] [8]  —
     GND [9][10]  —
      — [11][12]  —
      — [13][14] GND
      — [15][16]  —
    3.3V [17][18]  —
MOSI(10)[19][20] GND
MISO (9)[21][22] GPIO25 ←── RC522 RST
SCLK(11)[23][24] CE0(8) ←── RC522 SDA
      — [25][26] CE1
```

> **Remarque :** Vérifiez toujours avec `pinout` sur le Pi ou sur [pinout.xyz](https://pinout.xyz) car la numérotation varie selon les modèles.

---

## Stack technique

| Couche | Technologie | Rôle |
|---|---|---|
| Serveur HTTP | **Gunicorn** (gthread, 1 worker) | Serveur WSGI de production, écoute sur `:5000` |
| Backend | **Flask 3** + Flask-SQLAlchemy | Routes, logique métier |
| Base de données | **SQLite** (via SQLAlchemy) | Audios, playlists, tags |
| Audio | **python-vlc** (libvlc) | Lecture MP3/OGG/WAV/FLAC |
| RFID | **mfrc522** + spidev + RPi.GPIO | Lecture RC522 via SPI |
| Thread RFID | `threading.Thread(daemon=True)` | Non-bloquant pour Flask |
| YouTube | **yt-dlp** + **ffmpeg** | Recherche et téléchargement d'audio depuis YouTube |
| Frontend | **Jinja2** + **TailwindCSS** (CDN) | Interface mobile-first |
| Service OS | **systemd** | Démarrage automatique, restart |

> **Python 3.9+ requis.** L'application utilise `from __future__ import annotations` pour la compatibilité avec Python 3.9 (Raspberry Pi OS Bullseye).

---

## Structure du projet

```
baby-jukebox/
│
├── main.py                   # Point d'entrée (développement)
├── wsgi.py                   # Point d'entrée WSGI (production / Gunicorn)
├── app.py                    # Application Flask : routes + singletons
├── models.py                 # Modèles SQLAlchemy (Audio, Playlist, Tag)
├── player.py                 # Wrapper VLC thread-safe
├── rfid_reader.py            # Thread daemon RC522
├── requirements.txt          # Dépendances Python
│
├── uploads/                  # Fichiers audio uploadés (créé automatiquement)
│
├── templates/
│   ├── base.html             # Layout commun (Tailwind dark, nav)
│   ├── index.html            # Lecteur en cours + contrôles
│   ├── upload.html           # Import de fichiers audio (drag & drop)
│   ├── playlists.html        # Gestion des playlists
│   ├── edit_playlist.html    # Édition d'une playlist
│   └── assign.html           # Association tag RFID ↔ audio/playlist
│
└── deploy/
    ├── baby-jukebox.service  # Unit systemd
    ├── gunicorn.conf.py      # Configuration Gunicorn
    └── install.sh            # Script d'installation automatisé
```

**Fichiers générés à l'exécution (non versionnés) :**

```
baby-jukebox/
├── jukebox.db                # Base de données SQLite
└── uploads/*.mp3             # Fichiers audio uploadés
```

---

## Getting Started

### Prérequis

- Raspberry Pi sous **Raspberry Pi OS** (Bullseye ou Bookworm, 32 ou 64 bits)
- Accès SSH ou clavier/écran sur le Pi
- Pi connecté à Internet pour l'installation
- RC522 câblé comme décrit [ci-dessus](#câblage-rc522)

---

### Installation automatisée

> C'est la méthode recommandée. Le script gère tout en une seule commande.

**1. Cloner le dépôt sur le Pi**

```bash
cd ~
git clone https://github.com/your/baby-jukebox.git
cd baby-jukebox
```

**2. Lancer le script d'installation**

```bash
chmod +x deploy/install.sh
sudo ./deploy/install.sh
```

Le script effectue automatiquement :
- `apt-get` des dépendances système (VLC, Python, alsa-utils, **ffmpeg**)
- Activation du SPI dans `/boot/config.txt` si nécessaire
- Ajout de l'utilisateur aux groupes `audio`, `spi`, `gpio`, `video`
- Création du virtualenv Python et installation des packages (dont `gunicorn`, **`yt-dlp`**)
- Détection automatique du Raspberry Pi → installation de `mfrc522`, `spidev`, `RPi.GPIO`
- Création du répertoire `/var/log/baby-jukebox`
- Installation et activation du service systemd
- Configuration de la rotation des logs (logrotate)

**3. Redémarrer si le SPI vient d'être activé**

```bash
sudo reboot
```

**4. Changer la SECRET_KEY Flask**

```bash
# Générer une clé aléatoire
python3 -c "import secrets; print(secrets.token_hex(32))"

# L'éditer dans le unit systemd
sudo nano /etc/systemd/system/baby-jukebox.service
# Modifier la ligne : Environment="SECRET_KEY=..."

sudo systemctl daemon-reload
sudo systemctl restart baby-jukebox
```

**5. Accéder à l'interface**

```bash
# Trouver l'IP du Pi
hostname -I
```

Ouvrir **`http://<IP_DU_PI>:5000`** dans un navigateur depuis n'importe quel appareil sur le réseau local.

---

### Installation manuelle (développement)

Pour tester sur un PC sans Raspberry Pi ni RC522. Le thread RFID tourne en mode mock (silencieux).

```bash
# 1. Cloner
git clone https://github.com/your/baby-jukebox.git
cd baby-jukebox

# 2. Créer le virtualenv
python3 -m venv venv
source venv/bin/activate        # Linux/macOS
# venv\Scripts\activate         # Windows

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Lancer en mode développement
python main.py
```

Application disponible sur `http://localhost:5001`.

> En dehors d'un Raspberry Pi, `mfrc522` n'est pas installé → le thread RFID s'active en mode mock sans erreur. VLC doit être installé sur la machine hôte (`brew install vlc` sur macOS, `sudo apt install vlc` sur Linux).

---

## Déploiement comme service Linux

### Vue d'ensemble

```
Appareil (téléphone / PC)
          │
    réseau local
          │
  [Gunicorn :5000]   ←── écoute sur 0.0.0.0:5000
    1 worker + 4 threads
          │
       [Flask]
        ├── Thread RFID daemon  (RC522 → callback → VLC)
        └── Lecteur VLC         (sortie ALSA/jack)
          │
       [SQLite]
```

### Pourquoi `workers = 1` dans Gunicorn ?

L'application maintient trois singletons en mémoire :
- `player` — instance VLC
- `_last_unassigned_tag` — dernier tag RFID non assigné
- Thread RFID daemon

Avec plusieurs workers (processus séparés), chaque worker aurait **sa propre copie** de ces singletons → deux lecteurs RFID actifs, deux instances VLC, état incohérent entre les requêtes.

La concurrence HTTP est assurée par **4 threads** dans le worker unique (`worker_class = "gthread"`).

---

## Référence des commandes

### Service systemd

```bash
# Démarrer le service
sudo systemctl start baby-jukebox

# Arrêter le service
sudo systemctl stop baby-jukebox

# Redémarrer (coupure brève)
sudo systemctl restart baby-jukebox

# Rechargement gracieux (finit les requêtes en cours, puis redémarre)
sudo systemctl reload baby-jukebox

# Voir le statut complet
sudo systemctl status baby-jukebox

# Activer le démarrage automatique au boot
sudo systemctl enable baby-jukebox

# Désactiver le démarrage automatique
sudo systemctl disable baby-jukebox

# Vérifier si le service est actif
systemctl is-active baby-jukebox

# Vérifier si le service démarre au boot
systemctl is-enabled baby-jukebox
```

---

### Logs

```bash
# Suivre les logs en temps réel (Ctrl+C pour quitter)
sudo journalctl -u baby-jukebox -f

# Voir les 100 dernières lignes
sudo journalctl -u baby-jukebox -n 100

# Logs depuis le dernier démarrage du service
sudo journalctl -u baby-jukebox -b

# Logs sur une période donnée
sudo journalctl -u baby-jukebox --since "2024-01-15 10:00" --until "2024-01-15 11:00"

# Logs Gunicorn (accès HTTP)
sudo tail -f /var/log/baby-jukebox/access.log

# Logs Gunicorn (erreurs et warnings)
sudo tail -f /var/log/baby-jukebox/error.log

# Vider les logs journald du service
sudo journalctl --vacuum-time=1d -u baby-jukebox
```

---

### Audio

```bash
# ── Sortie jack ──────────────────────────────────────────────────────
# Forcer la sortie sur la prise jack (méthode ALSA)
amixer cset numid=3 1
# 0 = auto, 1 = jack analogique, 2 = HDMI

# Forcer via raspi-config (interface interactive)
sudo raspi-config
# → System Options → Audio → Headphones

# Vérifier que le son fonctionne (beep de test)
speaker-test -t wav -c 2

# Lister les périphériques audio détectés par ALSA
aplay -l

# Voir le volume actuel
amixer get Master

# Régler le volume à 85%
amixer set Master 85%

# ── VLC (test manuel hors service) ───────────────────────────────────
# Lire un fichier en ligne de commande (headless)
cvlc --aout=alsa /home/pi/baby-jukebox/uploads/morceau.mp3

# ── Problème : pas de son après reboot ───────────────────────────────
# Rendre le réglage de sortie jack persistant
sudo nano /etc/asound.conf
```

Contenu de `/etc/asound.conf` pour forcer la sortie jack :
```
defaults.pcm.card 0
defaults.pcm.device 0
defaults.ctl.card 0
```

---

### Mise à jour de l'application

```bash
# Méthode recommandée : git pull + re-lancer le script (idempotent)
cd ~/baby-jukebox
git pull origin main
sudo ./deploy/install.sh

# ── Ou mise à jour rapide sans re-script ──────────────────────────────
git pull origin main
sudo systemctl reload baby-jukebox
```

---

### Base de données

```bash
# Accéder à la base SQLite
sqlite3 /home/pi/baby-jukebox/jukebox.db

# Commandes SQLite utiles :
.tables                          -- lister les tables
.schema audio                    -- voir la structure d'une table
SELECT * FROM audio;             -- tous les audios
SELECT * FROM tag;               -- tous les tags RFID
SELECT * FROM playlist;          -- toutes les playlists
.quit                            -- quitter

# Sauvegarder la base de données
cp /home/pi/baby-jukebox/jukebox.db ~/jukebox_backup_$(date +%Y%m%d).db

# Restaurer une sauvegarde
sudo systemctl stop baby-jukebox
cp ~/jukebox_backup_20240115.db /home/pi/baby-jukebox/jukebox.db
sudo systemctl start baby-jukebox
```

---

### Debug et diagnostic

```bash
# ── État général du système ───────────────────────────────────────────
# Vérifier que le SPI est activé
lsmod | grep spi
ls /dev/spidev*                  # Doit afficher /dev/spidev0.0

# Vérifier que /dev/gpiomem est accessible
ls -la /dev/gpiomem              # Doit afficher le groupe gpio

# Vérifier les groupes de l'utilisateur pi
id pi
# Doit inclure : audio, spi, gpio, video

# Tester le RC522 manuellement (hors service)
sudo systemctl stop baby-jukebox
source /home/pi/baby-jukebox/venv/bin/activate
python3 - <<'EOF'
import RPi.GPIO as GPIO
GPIO.setwarnings(False)
from mfrc522 import SimpleMFRC522
reader = SimpleMFRC522()
print("Approchez un tag RFID…")
id, text = reader.read()
print(f"Tag ID : {id}")
EOF
sudo systemctl start baby-jukebox

# ── Processus ─────────────────────────────────────────────────────────
# Voir le processus Gunicorn
ps aux | grep gunicorn

# Vérifier que Gunicorn écoute sur le port 5000
ss -tlnp | grep 5000

# ── Ressources Pi ─────────────────────────────────────────────────────
# Utilisation CPU/RAM en temps réel
htop

# Température du Pi (important pour la stabilité)
vcgencmd measure_temp

# Espace disque
df -h /home/pi/baby-jukebox/uploads

# ── Réseau ────────────────────────────────────────────────────────────
# IP du Pi
hostname -I

# Tester que l'app répond localement
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000
# Doit retourner 200

# Tester l'API de statut du lecteur
curl http://localhost:5000/api/status

# ── Redémarrage complet en cas de problème sévère ─────────────────────
sudo systemctl restart baby-jukebox
sudo journalctl -u baby-jukebox -n 30
```

---

## Configuration

### Variables d'environnement (dans le unit systemd)

```ini
# /etc/systemd/system/baby-jukebox.service

Environment="SECRET_KEY=<clé aléatoire de 32+ caractères>"
Environment="FLASK_ENV=production"
Environment="AUDIODEV=hw:0,0"     # Périphérique ALSA (hw:0,0 = jack)
Environment="DISPLAY="            # Vide = VLC sans affichage (headless)
```

Pour générer une `SECRET_KEY` sécurisée :

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Après modification du unit file :
```bash
sudo systemctl daemon-reload && sudo systemctl restart baby-jukebox
```

### Fichiers de configuration

| Fichier | Rôle | Modifier quand |
|---|---|---|
| `/etc/systemd/system/baby-jukebox.service` | Service systemd | Changer user, env vars, groupes |
| `/home/pi/baby-jukebox/deploy/gunicorn.conf.py` | Gunicorn | Changer port, threads, timeouts, logs |

### Changer le port d'écoute

Par défaut : port **5000** sur toutes les interfaces.

```python
# deploy/gunicorn.conf.py
bind = "0.0.0.0:8080"   # Changer 5000 par le port souhaité
```

Puis appliquer sur le Pi :
```bash
sudo systemctl restart baby-jukebox
```

---

## Pages de l'interface web

| URL | Page | Fonctionnalité |
|---|---|---|
| `/` | Lecteur | Affiche la piste en cours, contrôles stop/pause/prev/next, barre de progression (polling JS toutes les secondes) |
| `/upload` | Import | Upload de fichiers MP3/OGG/WAV/FLAC/M4A par glisser-déposer ; recherche YouTube et téléchargement d'audio en arrière-plan ; liste et suppression des audios |
| `/playlists` | Playlists | Création de playlists à partir des audios importés, édition, suppression |
| `/assign` | Tags RFID | Affiche le dernier tag scanné non assigné (polling JS), association à un audio ou une playlist, liste des associations existantes |

---

## Architecture

### Flux de données — Scan RFID

```
RC522 (SPI)
    │
    ↓ polling toutes les 100ms (déclenchement sur changement d'UID uniquement)
[Thread RFID daemon]  ←── daemon=True, ne bloque pas Flask
    │
    ↓ tag détecté
[on_tag_detected(rfid_id)]
    │
    ├── Tag trouvé en DB ?
    │       ├── Oui → audio    → player.play_file(path)
    │       ├── Oui → playlist → player.play_playlist([paths])
    │       └── Non → _last_unassigned_tag = rfid_id  (affiché sur /assign)
    │
    └── app.app_context() ← requis pour accéder à SQLAlchemy hors requête Flask
```

### Flux de données — Requête HTTP

```
Navigateur (téléphone / PC)
    │
    │ http://<IP>:5000
    │
[Gunicorn 0.0.0.0:5000]
    │  1 worker process / 4 threads (gthread)
    │
  [Flask]
    │  ├── player              (singleton partagé avec le thread RFID)
    │  ├── _last_unassigned_tag (partagé)
    │  └── SQLite via SQLAlchemy
```

### Modèle de données

```
Audio         Playlist        Tag
─────         ────────        ───
id (PK)       id (PK)         id (PK)
name          name            rfid_id (unique)
file_path     audios []  ─M2M─ audio_id    (FK nullable)
                               playlist_id (FK nullable)
```

---

## Dépannage

### Le service ne démarre pas

```bash
sudo journalctl -u baby-jukebox -n 50
```

| Symptôme dans les logs | Cause probable | Solution |
|---|---|---|
| `ModuleNotFoundError: vlc` | VLC non installé | `sudo apt-get install vlc libvlc-dev` |
| `ModuleNotFoundError: mfrc522` | Lib RFID manquante | `pip install mfrc522 spidev RPi.GPIO` |
| `TypeError: unsupported operand ... \|` | Python < 3.9 | Mettre à jour Python ou Raspberry Pi OS |
| `No access to /dev/mem` | Mauvais groupe ou `/dev/gpiomem` inaccessible | `sudo usermod -aG gpio pi` + redémarrer le service |
| `Permission denied: /dev/spidev0.0` | SPI désactivé ou mauvais groupe | Activer SPI via raspi-config + `sudo usermod -aG spi pi` |
| `Address already in use :5000` | Gunicorn déjà lancé | `sudo fuser -k 5000/tcp` |
| `Worker boot error (exit code 3)` | Erreur Python au démarrage | Lancer `venv/bin/gunicorn --log-file=- wsgi:application` pour voir le traceback |

### Pas de son via la prise jack

```bash
# 1. Forcer la sortie jack
amixer cset numid=3 1

# 2. Vérifier le volume
amixer set Master 90%

# 3. Tester avec un fichier WAV
aplay /usr/share/sounds/alsa/Front_Center.wav

# 4. Vérifier que pi est dans le groupe audio
groups pi | grep audio
# Si absent :
sudo usermod -aG audio pi
sudo systemctl restart baby-jukebox
```

### Le RC522 ne détecte pas les tags

```bash
# 1. Vérifier que SPI est actif
ls /dev/spidev*        # Doit afficher /dev/spidev0.0

# 2. Si absent : activer SPI et rebooter
sudo raspi-config      # Interface Options → SPI → Enable
sudo reboot

# 3. Vérifier les permissions /dev/gpiomem
ls -la /dev/gpiomem    # Doit montrer le groupe gpio
groups pi | grep gpio

# 4. Tester la lib mfrc522 manuellement (voir section Debug)
```

### La page web ne répond pas

```bash
# 1. Vérifier que Gunicorn tourne
sudo systemctl status baby-jukebox

# 2. Vérifier qu'il écoute bien sur le port 5000
ss -tlnp | grep 5000

# 3. Tester en local sur le Pi
curl -s -o /dev/null -w "%{http_code}" http://localhost:5000

# 4. Pare-feu ?
sudo ufw status
sudo ufw allow 5000/tcp   # Si UFW est actif
```

### Le service redémarre en boucle (StartLimitBurst)

```bash
# Voir pourquoi il crashe
sudo journalctl -u baby-jukebox -n 100

# Réinitialiser le compteur de redémarrages
sudo systemctl reset-failed baby-jukebox
sudo systemctl start baby-jukebox
```

### Téléchargement YouTube en erreur

```bash
# Vérifier que yt-dlp est installé dans le venv
/home/pi/baby-jukebox/venv/bin/pip show yt-dlp

# Si absent :
/home/pi/baby-jukebox/venv/bin/pip install yt-dlp

# Vérifier que ffmpeg est disponible (requis pour la conversion MP3)
ffmpeg -version
# Si absent :
sudo apt install -y ffmpeg

# Tester un téléchargement manuel hors service
source /home/pi/baby-jukebox/venv/bin/activate
yt-dlp -x --audio-format mp3 "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \
    -o "/tmp/test.%(ext)s"

# Mettre à jour yt-dlp si YouTube bloque les téléchargements
/home/pi/baby-jukebox/venv/bin/pip install -U yt-dlp
sudo systemctl restart baby-jukebox
```

| Symptôme | Cause probable | Solution |
|---|---|---|
| `yt-dlp non installé` dans l'interface | yt-dlp absent du venv | `pip install yt-dlp` dans le venv |
| `ERROR: Postprocessing: ffprobe and ffmpeg not found` | ffmpeg manquant | `sudo apt install ffmpeg` |
| `Sign in to confirm you're not a bot` | YouTube bloque la requête | Mettre à jour yt-dlp (`pip install -U yt-dlp`) |
| Téléchargement en `…` bloqué indéfiniment | Erreur silencieuse dans le thread | Voir `journalctl -u baby-jukebox -n 50` |

---

### Espace disque plein (uploads)

```bash
# Voir la taille du dossier uploads
du -sh /home/pi/baby-jukebox/uploads/

# Lister les fichiers par taille
ls -lhS /home/pi/baby-jukebox/uploads/

# Supprimer via l'interface web : page Upload → corbeille
# Ou directement :
rm /home/pi/baby-jukebox/uploads/fichier_inutile.mp3
# Puis supprimer l'entrée en base via l'interface web ou sqlite3
```

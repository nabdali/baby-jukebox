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
   - [Nginx](#nginx)
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
      — [7] [8]  —
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
| Serveur HTTP | **Gunicorn** (gthread, 1 worker) | Serveur WSGI de production |
| Backend | **Flask 3** + Flask-SQLAlchemy | Routes, logique métier |
| Base de données | **SQLite** (via SQLAlchemy) | Audios, playlists, tags |
| Audio | **python-vlc** (libvlc) | Lecture MP3/OGG/WAV/FLAC |
| RFID | **mfrc522** + spidev | Lecture RC522 via SPI |
| Thread RFID | `threading.Thread(daemon=True)` | Non-bloquant pour Flask |
| Reverse proxy | **Nginx** | Compression, uploads, port 80 |
| Frontend | **Jinja2** + **TailwindCSS** (CDN) | Interface mobile-first |
| Service OS | **systemd** | Démarrage automatique, restart |

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
    ├── nginx.conf            # Configuration Nginx (reverse proxy)
    ├── maintenance.html      # Page d'erreur Nginx 502/503
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

> C'est la méthode recommandée pour la production. Le script gère tout.

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
- `apt-get` des dépendances système (VLC, Python, Nginx, alsa-utils)
- Activation du SPI dans `/boot/config.txt` si nécessaire
- Ajout de l'utilisateur aux groupes `audio`, `spi`, `gpio`, `video`
- Création du virtualenv Python et installation des packages
- Détection automatique du Raspberry Pi → installation de `mfrc522`, `spidev`, `RPi.GPIO`
- Création des répertoires `/var/log/baby-jukebox` et `/run/baby-jukebox`
- Installation et activation du service systemd
- Configuration de Nginx en reverse proxy
- Configuration de la rotation des logs (logrotate)

**3. Redémarrer si le SPI vient d'être activé**

```bash
sudo reboot
```

**4. Changer la SECRET_KEY Flask**

```bash
sudo nano /etc/systemd/system/baby-jukebox.service
# Modifier la ligne : Environment="SECRET_KEY=..."
# Générer une clé aléatoire : python3 -c "import secrets; print(secrets.token_hex(32))"

sudo systemctl daemon-reload
sudo systemctl restart baby-jukebox
```

**5. Accéder à l'interface**

```bash
# Trouver l'IP du Pi
hostname -I
```

Ouvrir `http://<IP_DU_PI>` dans un navigateur.

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

Application disponible sur `http://localhost:5000`.

> En dehors d'un Raspberry Pi, `mfrc522` n'est pas installé → le thread RFID s'active en mode mock et aucune erreur n'est levée. VLC doit être installé sur la machine hôte (`brew install vlc` sur macOS, `sudo apt install vlc` sur Linux).

---

## Déploiement comme service Linux

### Vue d'ensemble

```
Requête HTTP
     │
  [Nginx :80]  ─── fichiers statiques/uploads servis directement
     │
[Gunicorn :5000]  1 worker + 4 threads (état mémoire partagé)
     │
  [Flask]
   ├── Thread RFID daemon (RC522 → VLC)
   └── Lecteur VLC (sortie ALSA/jack)
```

### Pourquoi `workers = 1` dans Gunicorn ?

L'application maintient trois singletons en mémoire :
- `player` — instance VLC
- `_last_unassigned_tag` — dernier tag RFID non assigné
- Thread RFID daemon

Avec plusieurs workers (processus séparés), chaque worker aurait **sa propre copie** de ces singletons → deux lecteurs RFID actifs, deux instances VLC, état incohérent entre les requêtes.

La concurrence HTTP est assurée par **4 threads** dans le worker unique.

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

# Logs avec horodatage sur une période donnée
sudo journalctl -u baby-jukebox --since "2024-01-15 10:00" --until "2024-01-15 11:00"

# Logs Gunicorn (accès HTTP)
sudo tail -f /var/log/baby-jukebox/access.log

# Logs Gunicorn (erreurs et warnings)
sudo tail -f /var/log/baby-jukebox/error.log

# Logs Nginx
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log

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

### Nginx

```bash
# Tester la configuration (avant de recharger)
sudo nginx -t

# Recharger la configuration sans coupure
sudo systemctl reload nginx

# Redémarrer Nginx
sudo systemctl restart nginx

# Statut Nginx
sudo systemctl status nginx

# Voir les sites activés
ls -la /etc/nginx/sites-enabled/

# Éditer la configuration Baby Jukebox
sudo nano /etc/nginx/sites-available/baby-jukebox
```

---

### Mise à jour de l'application

```bash
# 1. Se placer dans le répertoire du projet (dépôt git source)
cd ~/baby-jukebox

# 2. Récupérer les modifications
git pull origin main

# 3. Relancer le script d'installation (idempotent)
sudo ./deploy/install.sh

# ── Ou mise à jour manuelle ───────────────────────────────────────────

# Copier les fichiers modifiés
sudo cp app.py models.py player.py rfid_reader.py wsgi.py /home/pi/baby-jukebox/
sudo cp -r templates/ /home/pi/baby-jukebox/templates/

# Mettre à jour les dépendances Python si besoin
sudo -u pi /home/pi/baby-jukebox/venv/bin/pip install -r requirements.txt

# Recharger le service (graceful)
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

# Vérifier les groupes de l'utilisateur pi
id pi
# Doit inclure : audio, spi, gpio, video

# Tester le RC522 manuellement (hors service)
sudo systemctl stop baby-jukebox
source /home/pi/baby-jukebox/venv/bin/activate
python3 - <<'EOF'
from mfrc522 import SimpleMFRC522
reader = SimpleMFRC522()
print("Approchez un tag RFID…")
id, text = reader.read()
print(f"Tag ID : {id}")
EOF
sudo systemctl start baby-jukebox

# ── Processus ─────────────────────────────────────────────────────────
# Voir le processus Gunicorn et ses threads
ps aux | grep gunicorn
pstree -p $(cat /run/baby-jukebox/gunicorn.pid)

# Voir les connexions réseau actives
ss -tlnp | grep 5000          # Gunicorn
ss -tlnp | grep 80            # Nginx

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
sudo systemctl stop baby-jukebox nginx
sleep 2
sudo systemctl start nginx baby-jukebox
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
| `/etc/systemd/system/baby-jukebox.service` | Service systemd | Changer user, port, env vars |
| `/home/pi/baby-jukebox/deploy/gunicorn.conf.py` | Gunicorn | Changer threads, timeouts, logs |
| `/etc/nginx/sites-available/baby-jukebox` | Nginx | Changer port, nom de domaine, SSL |

### Changer le port d'écoute

Par défaut : port **80** (via Nginx) → Gunicorn sur **5000** (local).

Pour changer le port public :
```bash
sudo nano /etc/nginx/sites-available/baby-jukebox
# Modifier : listen 80; → listen 8080;
sudo nginx -t && sudo systemctl reload nginx
```

Pour exposer Gunicorn directement sans Nginx (déconseillé) :
```python
# deploy/gunicorn.conf.py
bind = "0.0.0.0:5000"
```

---

## Pages de l'interface web

| URL | Page | Fonctionnalité |
|---|---|---|
| `/` | Lecteur | Affiche la piste en cours, contrôles stop/pause/prev/next, barre de progression (polling JS toutes les secondes) |
| `/upload` | Import | Upload de fichiers MP3/OGG/WAV/FLAC/M4A par glisser-déposer, liste et suppression des audios |
| `/playlists` | Playlists | Création de playlists à partir des audios importés, édition, suppression |
| `/assign` | Tags RFID | Affiche le dernier tag scanné non assigné (polling JS), association à un audio ou une playlist, liste des associations existantes |

---

## Architecture

### Flux de données — Scan RFID

```
RC522 (SPI)
    │
    ↓ polling toutes les 300ms
[Thread RFID daemon]  ←── tourne en arrière-plan, ne bloque pas Flask
    │
    ↓ tag détecté (debounce 2s)
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
Navigateur
    │
  [Nginx :80]
    │  ↳ /uploads/* → servi directement par Nginx
    │
  [Gunicorn :5000]
    │  1 worker process / 4 threads
    │
  [Flask]
    │  ├── Accède à player (singleton partagé avec thread RFID)
    │  ├── Accède à _last_unassigned_tag (partagé)
    │  └── Accède à SQLite via SQLAlchemy
```

### Modèle de données

```
Audio         Playlist        Tag
─────         ────────        ───
id (PK)       id (PK)         id (PK)
name          name            rfid_id (unique)
file_path     audios []  ─M2M─ audio_id (FK, nullable)
                               playlist_id (FK, nullable)
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
| `Permission denied: /dev/spidev0.0` | SPI désactivé ou mauvais groupe | Activer SPI + `sudo usermod -aG spi pi` |
| `Address already in use :5000` | Gunicorn déjà lancé | `sudo fuser -k 5000/tcp` |
| `error: [Errno 98]` | Port 80 déjà utilisé | `sudo systemctl stop nginx ; sudo nginx -t` |

### Pas de son via la prise jack

```bash
# 1. Forcer la sortie jack
amixer cset numid=3 1

# 2. Vérifier le volume
amixer set Master 90%

# 3. Tester avec un fichier WAV
aplay /usr/share/sounds/alsa/Front_Center.wav

# 4. Vérifier que le user 'pi' est dans le groupe 'audio'
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

# 3. Vérifier le câblage (VCC = 3.3V !)
# 4. Tester la lib mfrc522 manuellement (voir section Debug)
```

### La page web ne répond pas

```bash
# 1. Vérifier Nginx
sudo systemctl status nginx
curl -I http://localhost:80

# 2. Vérifier Gunicorn
curl http://localhost:5000
sudo systemctl status baby-jukebox

# 3. Pare-feu ?
sudo ufw status
sudo ufw allow 80/tcp   # Si UFW est actif
```

### Le service redémarre en boucle (StartLimitBurst)

```bash
# Voir pourquoi il crashe
sudo journalctl -u baby-jukebox -n 100

# Réinitialiser le compteur de redémarrages
sudo systemctl reset-failed baby-jukebox
sudo systemctl start baby-jukebox
```

### Espace disque plein (uploads)

```bash
# Voir la taille du dossier uploads
du -sh /home/pi/baby-jukebox/uploads/

# Lister les fichiers par taille
ls -lhS /home/pi/baby-jukebox/uploads/

# Supprimer via l'interface web : page Upload → corbeille
# Ou directement :
rm /home/pi/baby-jukebox/uploads/fichier_inutile.mp3
# Puis supprimer l'entrée en base via sqlite3 ou l'interface web
```

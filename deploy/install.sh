#!/usr/bin/env bash
# =============================================================================
# Baby Jukebox — Script d'installation automatisé pour Raspberry Pi OS
# =============================================================================
# Usage :
#   chmod +x deploy/install.sh
#   sudo ./deploy/install.sh
#
# Ce script est idempotent : il peut être relancé sans risque.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Couleurs et helpers
# ---------------------------------------------------------------------------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET}  $*"; }
success() { echo -e "${GREEN}[OK]${RESET}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET}  $*"; }
error()   { echo -e "${RED}[ERROR]${RESET} $*" >&2; exit 1; }
section() { echo -e "\n${BOLD}=== $* ===${RESET}"; }

# ---------------------------------------------------------------------------
# Vérifications préalables
# ---------------------------------------------------------------------------
section "Vérifications"

[[ $EUID -eq 0 ]] || error "Ce script doit être exécuté en root (sudo ./deploy/install.sh)"

APP_USER="${APP_USER:-pi}"
APP_DIR="${APP_DIR:-/home/${APP_USER}/baby-jukebox}"
VENV_DIR="${APP_DIR}/venv"
LOG_DIR="/var/log/baby-jukebox"
RUN_DIR="/run/baby-jukebox"
SERVICE_NAME="baby-jukebox"

id "$APP_USER" &>/dev/null || error "L'utilisateur '$APP_USER' n'existe pas. Définissez APP_USER."
info "Utilisateur : $APP_USER"
info "Répertoire  : $APP_DIR"

# ---------------------------------------------------------------------------
# 1. Dépendances système
# ---------------------------------------------------------------------------
section "Installation des dépendances système"

apt-get update -qq
apt-get install -y --no-install-recommends \
    vlc             \
    libvlc-dev      \
    python3         \
    python3-venv    \
    python3-pip     \
    nginx           \
    git             \
    alsa-utils      \
    2>/dev/null

success "Dépendances système installées"

# ---------------------------------------------------------------------------
# 2. SPI — activation si nécessaire
# ---------------------------------------------------------------------------
section "Configuration SPI"

if ! lsmod | grep -q spi_bcm2835; then
    warn "Module SPI non chargé. Ajout dans /boot/config.txt…"
    if ! grep -q "dtparam=spi=on" /boot/config.txt 2>/dev/null; then
        echo "dtparam=spi=on" >> /boot/config.txt
        warn "SPI activé — un redémarrage sera nécessaire après l'installation."
    fi
else
    success "SPI déjà actif"
fi

# ---------------------------------------------------------------------------
# 3. Groupes système pour l'utilisateur
# ---------------------------------------------------------------------------
section "Configuration des groupes"

for grp in audio spi gpio video; do
    if getent group "$grp" &>/dev/null; then
        if ! id -nG "$APP_USER" | grep -qw "$grp"; then
            usermod -aG "$grp" "$APP_USER"
            info "Utilisateur '$APP_USER' ajouté au groupe '$grp'"
        else
            info "Groupe '$grp' : déjà membre"
        fi
    else
        warn "Groupe '$grp' introuvable (normal hors Raspberry Pi)"
    fi
done

# ---------------------------------------------------------------------------
# 4. Copie des fichiers de l'application
# ---------------------------------------------------------------------------
section "Déploiement des fichiers"

# Crée le répertoire de l'application
install -d -m 755 -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
install -d -m 755 -o "$APP_USER" -g "$APP_USER" "${APP_DIR}/uploads"
install -d -m 755 -o "$APP_USER" -g "$APP_USER" "${APP_DIR}/templates"
install -d -m 755 -o "$APP_USER" -g "$APP_USER" "${APP_DIR}/deploy"

# Copie les fichiers Python et de config depuis le répertoire courant
# (supposant que le script est lancé depuis la racine du projet)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

for f in app.py models.py player.py rfid_reader.py wsgi.py requirements.txt; do
    cp -v "${PROJECT_ROOT}/${f}" "${APP_DIR}/${f}"
    chown "$APP_USER:$APP_USER" "${APP_DIR}/${f}"
done

cp -rv "${PROJECT_ROOT}/templates/." "${APP_DIR}/templates/"
cp -rv "${PROJECT_ROOT}/deploy/."    "${APP_DIR}/deploy/"
chown -R "$APP_USER:$APP_USER" "${APP_DIR}/templates" "${APP_DIR}/deploy"

success "Fichiers copiés dans $APP_DIR"

# ---------------------------------------------------------------------------
# 5. Environnement virtuel Python
# ---------------------------------------------------------------------------
section "Environnement virtuel Python"

if [[ ! -d "$VENV_DIR" ]]; then
    info "Création du venv…"
    python3 -m venv "$VENV_DIR"
    chown -R "$APP_USER:$APP_USER" "$VENV_DIR"
fi

info "Installation des dépendances Python…"
sudo -u "$APP_USER" "${VENV_DIR}/bin/pip" install --upgrade pip --quiet
sudo -u "$APP_USER" "${VENV_DIR}/bin/pip" install --quiet \
    -r "${APP_DIR}/requirements.txt" \
    gunicorn

# Dépendances spécifiques Raspberry Pi
if [[ -f /proc/device-tree/model ]] && grep -qi "raspberry" /proc/device-tree/model; then
    info "Raspberry Pi détecté — installation de mfrc522, spidev, RPi.GPIO…"
    sudo -u "$APP_USER" "${VENV_DIR}/bin/pip" install --quiet \
        mfrc522 spidev RPi.GPIO
    success "Dépendances Pi installées"
else
    warn "Hors Raspberry Pi — mfrc522/spidev/RPi.GPIO ignorés (mode mock)"
fi

success "Environnement Python prêt"

# ---------------------------------------------------------------------------
# 6. Répertoires de logs et de runtime
# ---------------------------------------------------------------------------
section "Répertoires système"

install -d -m 755 -o "$APP_USER" -g "$APP_USER" "$LOG_DIR"
install -d -m 755 -o "$APP_USER" -g "$APP_USER" "$RUN_DIR"

# Fichier tmpfiles.d pour recréer /run/baby-jukebox après reboot
cat > /etc/tmpfiles.d/baby-jukebox.conf <<EOF
d /run/baby-jukebox 0755 ${APP_USER} ${APP_USER} -
EOF

success "Dossiers $LOG_DIR et $RUN_DIR créés"

# ---------------------------------------------------------------------------
# 7. Service systemd
# ---------------------------------------------------------------------------
section "Service systemd"

cp "${APP_DIR}/deploy/baby-jukebox.service" "/etc/systemd/system/${SERVICE_NAME}.service"

# Patch dynamique des chemins dans le unit file
sed -i "s|/home/pi/baby-jukebox|${APP_DIR}|g" "/etc/systemd/system/${SERVICE_NAME}.service"
sed -i "s|User=pi|User=${APP_USER}|g"          "/etc/systemd/system/${SERVICE_NAME}.service"
sed -i "s|Group=pi|Group=${APP_USER}|g"        "/etc/systemd/system/${SERVICE_NAME}.service"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}"
systemctl restart "${SERVICE_NAME}"

sleep 2
if systemctl is-active --quiet "${SERVICE_NAME}"; then
    success "Service '$SERVICE_NAME' démarré et actif"
else
    error "Échec du démarrage. Vérifiez : journalctl -u ${SERVICE_NAME} -n 50"
fi

# ---------------------------------------------------------------------------
# 8. Nginx
# ---------------------------------------------------------------------------
section "Configuration Nginx"

cp "${APP_DIR}/deploy/nginx.conf" "/etc/nginx/sites-available/${SERVICE_NAME}"

# Patch du chemin dans la config Nginx
sed -i "s|/home/pi/baby-jukebox|${APP_DIR}|g" "/etc/nginx/sites-available/${SERVICE_NAME}"

ln -sf "/etc/nginx/sites-available/${SERVICE_NAME}" \
       "/etc/nginx/sites-enabled/${SERVICE_NAME}"

# Désactive la config par défaut si encore active
if [[ -L /etc/nginx/sites-enabled/default ]]; then
    rm -f /etc/nginx/sites-enabled/default
    info "Config nginx 'default' désactivée"
fi

nginx -t && systemctl reload nginx
success "Nginx configuré et rechargé"

# ---------------------------------------------------------------------------
# 9. Logrotate
# ---------------------------------------------------------------------------
section "Rotation des logs"

cat > "/etc/logrotate.d/${SERVICE_NAME}" <<EOF
${LOG_DIR}/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    postrotate
        systemctl kill -s USR1 ${SERVICE_NAME} 2>/dev/null || true
    endscript
}
EOF

success "Logrotate configuré"

# ---------------------------------------------------------------------------
# Récapitulatif final
# ---------------------------------------------------------------------------
section "Installation terminée"

PI_IP=$(hostname -I | awk '{print $1}')

echo -e "
${GREEN}${BOLD}Baby Jukebox est opérationnel !${RESET}

  Application : ${CYAN}http://${PI_IP}${RESET}
  Logs        : ${CYAN}sudo journalctl -u ${SERVICE_NAME} -f${RESET}
  Status      : ${CYAN}sudo systemctl status ${SERVICE_NAME}${RESET}
  Restart     : ${CYAN}sudo systemctl restart ${SERVICE_NAME}${RESET}

${YELLOW}Actions post-installation :${RESET}
  1. Modifiez SECRET_KEY dans /etc/systemd/system/${SERVICE_NAME}.service
     puis : sudo systemctl daemon-reload && sudo systemctl restart ${SERVICE_NAME}
  2. Si SPI vient d'être activé, redémarrez le Pi : sudo reboot
"

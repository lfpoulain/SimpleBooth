#!/usr/bin/env bash
# ---------------------------------------------------------------------
# SimpleBooth Kiosk Installer Script (allégé)
# Auteur : Les Frères Poulain (modifié par Assistant)
# Description : Configuration automatisée pour Raspberry Pi OS
# ---------------------------------------------------------------------

set -euo pipefail
IFS=$'\n\t'

# -------------------- Couleurs --------------------
declare -A COLORS=(
  [R]="\033[0;31m"  # Rouge
  [G]="\033[0;32m"  # Vert
  [Y]="\033[1;33m"  # Jaune
  [C]="\033[0;36m"  # Cyan
  [P]="\033[0;35m"  # Pourpre
  [W]="\033[1;37m"  # Blanc
  [N]="\033[0m"     # Aucune couleur
)
log()   { echo -e "${COLORS[C]}[INFO]${COLORS[N]} $*"; }
ok()    { echo -e "${COLORS[G]}✔ $*${COLORS[N]}"; }
warn()  { echo -e "${COLORS[Y]}⚠ $*${COLORS[N]}"; }
error() { echo -e "${COLORS[R]}✖ $*${COLORS[N]}" >&2; exit 1; }

# -------------------- Variables --------------------
# Déduit le répertoire de l'application d'après l'emplacement du script
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$APP_DIR/venv"
LOG_FILE="/tmp/simplebooth_setup.log"
INSTALL_USER="${SUDO_USER:-${USER}}"
HOME_DIR="$(eval echo ~${INSTALL_USER})"
WAVE_ENABLED=true

# Détection du paquet Chromium
if apt-cache show chromium &>/dev/null; then
  CHROMIUM_PKG="chromium"
elif apt-cache show chromium-browser &>/dev/null; then
  CHROMIUM_PKG="chromium-browser"
else
  warn "Paquet Chromium introuvable, installation ignorée"
  CHROMIUM_PKG=""
fi

# -------------------- Trap erreurs --------------------
trap 'error "Échec à la ligne $LINENO. Voir $LOG_FILE"' ERR
exec &> >(tee "$LOG_FILE")

# -------------------- Fonctions --------------------
require_root() { (( EUID == 0 )) || error "Exécutez en root (sudo)"; }
confirm() { local prompt="${1:-Continuer? (o/N)}" default="${2:-N}" resp; read -rp "$prompt " resp; [[ "${resp:-$default}" =~ ^[Oo]$ ]]; }

update_system() {
  log "Mise à jour du système..."
  apt-get update -qq && apt-get upgrade -y -qq
  ok "Système à jour"
}

install_dependencies() {
  local pkgs=(python3 python3-venv python3-pip build-essential libcap2-bin xserver-xorg xinit x11-xserver-utils unclutter)
  [[ -n "$CHROMIUM_PKG" ]] && pkgs+=("$CHROMIUM_PKG")
  log "Installation dépendances: ${pkgs[*]}"
  apt-get install -y -qq "${pkgs[@]}"
  ok "Dépendances installées"
}

configure_waveshare() {
  [[ "$WAVE_ENABLED" == false ]] && { log "Waveshare skipped"; return; }
  log "Config écran Waveshare DSI 7\""
  local cfg=(/boot/firmware/config.txt /boot/config.txt) file
  for file in "${cfg[@]}"; do [[ -f "$file" ]] && break; done
  [[ -f "$file" ]] || { warn "config.txt introuvable"; return; }

  cp "$file" "${file}.bak.$(date +%Y%m%d)"
  ok "Sauvegarde de $file"

  # Ajouter dtoverlay avec rotation intégrée (ex: 270°)
  grep -q '^dtoverlay=vc4-kms-dsi-waveshare-panel' "$file" && \
    sed -i '/dtoverlay=vc4-kms-dsi-waveshare-panel/d' "$file"
  cat >> "$file" <<EOF

# Waveshare 7" DSI - SimpleBooth
# Rotation: 0, 90, 180, ou 270 (défaut 0)
dtoverlay=vc4-kms-dsi-waveshare-panel,7_0_inchC,i2c1
EOF
  ok "Waveshare configuré avec rotation"
}

setup_python_env() {
  log "Création venv Python"
  python3 -m venv "$VENV_DIR"
  source "$VENV_DIR/bin/activate"
  pip install --upgrade pip -q
  if [[ -f "$APP_DIR/requirements.txt" ]]; then
    pip install -r "$APP_DIR/requirements.txt" -q
  else
    pip install flask pillow numpy -q
  fi
  deactivate
  ok "Environnement Python prêt"
}

setup_kiosk() {
  log "Configuration mode kiosk"
  local autostart="$HOME_DIR/.config/autostart"
  mkdir -p "$autostart"
  cat > "$HOME_DIR/start_simplebooth.sh" <<EOF
#!/usr/bin/env bash
xset s off dpms s noblank
unclutter -idle 0.1 -root &
cd "$APP_DIR"
source "$VENV_DIR/bin/activate"
python app.py &
sleep 5
exec $CHROMIUM_PKG --kiosk --no-sandbox --disable-infobars --disable-features=TranslateUI http://localhost:5000
EOF
  chmod +x "$HOME_DIR/start_simplebooth.sh"
  cat > "$autostart/simplebooth.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=SimpleBooth Kiosk
Exec=$HOME_DIR/start_simplebooth.sh
X-GNOME-Autostart-enabled=true
Comment=SimpleBooth Kiosk mode
EOF
  ok "Kiosk configuré"
}

setup_systemd() {
  log "Configuration systemd"
  cat > /etc/systemd/system/simplebooth-kiosk.service <<EOF
[Unit]
Description=SimpleBooth Kiosk
After=graphical.target
[Service]
User=$INSTALL_USER
Environment=DISPLAY=:0
ExecStart=/usr/bin/startx -- -nocursor
Restart=on-failure
[Install]
WantedBy=graphical.target
EOF
  systemctl daemon-reload
  systemctl enable simplebooth-kiosk.service
  ok "Service systemd activé"
  mkdir -p /etc/systemd/system/getty@tty1.service.d
  cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<EOF
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin $INSTALL_USER --noclear %I \$TERM
EOF
  ok "Autologin configuré"
}

# -------------------- Main --------------------
main() {
  require_root
  log "Démarrage configuration SimpleBooth"
  update_system
  install_dependencies
  if confirm "Configurer Waveshare 7\" DSI? (o/N)"; then configure_waveshare; else WAVE_ENABLED=false; fi
  setup_python_env
  setup_kiosk
  setup_systemd
  ok "Configuration terminée"
  warn "Redémarrage recommandé"
  confirm "Redémarrer maintenant? (o/N)" && reboot
}

main "$@"

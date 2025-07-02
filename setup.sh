#!/usr/bin/env bash
# ---------------------------------------------------------------------
# SimpleBooth Kiosk Installer Script (amélioré)
# Auteur : Les Frères Poulain (modifié par Assistant)
# Description : Installation et configuration automatisée sous Raspberry Pi OS
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

# -------------------- Variables utilisateur --------------------
# Installer dans le home de l'utilisateur sudo, pas root
INSTALL_USER="${SUDO_USER:-${USER}}"
HOME_DIR="$(eval echo ~${INSTALL_USER})"
REPO_URL="https://github.com/lfpoulain/SimpleBooth"
APP_DIR="$HOME_DIR/SimpleBooth"
VENV_DIR="$APP_DIR/venv"
LOG_FILE="/tmp/simplebooth_install.log"
WAVE_ENABLED=true

# Détection du nom du paquet Chromium
if apt-cache show chromium &>/dev/null; then
  CHROMIUM_PKG="chromium"
elif apt-cache show chromium-browser &>/dev/null; then
  CHROMIUM_PKG="chromium-browser"
else
  warn "Paquet Chromium introuvable, installation ignorée"
  CHROMIUM_PKG=""
fi

# -------------------- Trap erreurs --------------------
trap 'error "Échec à la ligne $LINENO. Consultez $LOG_FILE"' ERR
exec &> >(tee "$LOG_FILE")

# -------------------- Prérequis --------------------
require_root() {
  (( EUID == 0 )) || error "Ce script doit être exécuté en root (sudo)"
}

# -------------------- Fonctions génériques --------------------
confirm() {
  local prompt="${1:-Continue? (o/N)}" default="${2:-N}" response
  read -rp "$prompt " response
  [[ "${response:-$default}" =~ ^[Oo]$ ]]
}

# -------------------- Étapes --------------------
update_system() {
  log "Mise à jour du système..."
  apt-get update -qq && apt-get upgrade -y -qq
  ok "Système à jour"
}

install_dependencies() {
  local pkgs=(
    git python3 python3-pip python3-venv
    build-essential libcap2-bin xserver-xorg
    xinit x11-xserver-utils unclutter
  )
  # Ajouter Chromium si détecté
  if [[ -n "$CHROMIUM_PKG" ]]; then
    pkgs+=("$CHROMIUM_PKG")
  fi

  log "Installation des dépendances : ${pkgs[*]}"
  apt-get install -y -qq "${pkgs[@]}"
  ok "Dépendances installées"
}

configure_waveshare() {
  if [[ "$WAVE_ENABLED" == false ]]; then
    log "Skip configuration Waveshare"
    return
  fi
  log "Configuration écran Waveshare DSI 7\""

  local cfg=(/boot/firmware/config.txt /boot/config.txt)
  local file
  for file in "${cfg[@]}"; do [[ -f "$file" ]] && break; done
  [[ -f "$file" ]] || { warn "config.txt non trouvé"; return; }

  cp "$file" "${file}.bak.$(date +%Y%m%d_%H%M%S)"
  ok "Sauvegarde $file"

  grep -q '^dtoverlay=vc4-kms-v3d' "$file" || echo 'dtoverlay=vc4-kms-v3d' >> "$file"
  cat >> "$file" <<EOF

# SimpleBooth Waveshare 7" DSI
dtoverlay=vc4-kms-dsi-waveshare-panel,7_0_inchC,i2c1
display_rotate=2
EOF
  ok "Config. Waveshare écrite dans $file"
}

clone_or_update_repo() {
  if [[ -d "$APP_DIR/.git" ]]; then
    log "Mise à jour du repo existant"
    git -C "$APP_DIR" pull -q
  else
    log "Clonage du repository dans $APP_DIR"
    mkdir -p "$HOME_DIR"
    chown "$INSTALL_USER":"$INSTALL_USER" "$HOME_DIR"
    sudo -u "$INSTALL_USER" git clone -q "$REPO_URL" "$APP_DIR"
  fi
  ok "Repository prêt"
}

setup_python_env() {
  log "Création venv Python dans $VENV_DIR"
  mkdir -p "$APP_DIR"
  chown -R "$INSTALL_USER":"$INSTALL_USER" "$APP_DIR"
  sudo -u "$INSTALL_USER" python3 -m venv "$VENV_DIR"
  sudo -u "$INSTALL_USER" bash -lc "source '$VENV_DIR/bin/activate' && pip install --upgrade pip -q"
  if [[ -f "$APP_DIR/requirements.txt" ]]; then
    sudo -u "$INSTALL_USER" bash -lc "source '$VENV_DIR/bin/activate' && pip install -r '$APP_DIR/requirements.txt' -q"
  else
    sudo -u "$INSTALL_USER" bash -lc "source '$VENV_DIR/bin/activate' && pip install flask pillow numpy -q"
  fi
  ok "Environnement Python prêt"
}

setup_kiosk() {
  log "Configuration mode kiosk"
  local autostart_dir="$HOME_DIR/.config/autostart"
  mkdir -p "$autostart_dir"
  chown -R "$INSTALL_USER":"$INSTALL_USER" "$autostart_dir"

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
  chown "$INSTALL_USER":"$INSTALL_USER" "$HOME_DIR/start_simplebooth.sh"

  cat > "$autostart_dir/simplebooth.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=SimpleBooth Kiosk
Exec=$HOME_DIR/start_simplebooth.sh
X-GNOME-Autostart-enabled=true
Comment=Démarrage SimpleBooth en mode kiosk
EOF
  chown "$INSTALL_USER":"$INSTALL_USER" "$autostart_dir/simplebooth.desktop"
  ok "Mode kiosk configuré"
}

setup_systemd() {
  log "Création du service systemd"
  local svc="/etc/systemd/system/simplebooth-kiosk.service"
  cat > "$svc" <<EOF
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
ExecStart=-/sbin/agetty --autologin $INSTALL_USER --noclear %I \\$TERM
EOF
  ok "Autologin configuré"
}

# -------------------- Main --------------------
main() {
  require_root
  log "Installation lancée pour l'utilisateur $INSTALL_USER ($HOME_DIR)"

  update_system
  install_dependencies

  if confirm "Configurer Waveshare 7\" DSI? (o/N)" N; then
    configure_waveshare
  else
    WAVE_ENABLED=false
  fi

  clone_or_update_repo
  setup_python_env
  setup_kiosk
  setup_systemd

  ok "Installation terminée"
  warn "Redémarrage recommandé"
  if confirm "Redémarrer maintenant? (o/N)" N; then
    reboot
  fi
}

main "$@"

#!/usr/bin/env bash
# SimpleBooth Kiosk Installer Script – version 1.1 (2025‑07‑02)
# Auteur : Les Frères Poulain + Assistant IA
# Description : Installation automatisée de SimpleBooth en mode kiosk sur Raspberry Pi OS

# -----------------------------------------------------------------------------
# Sécurité & robustesse
# -----------------------------------------------------------------------------
set -euo pipefail
IFS=$'\n\t'

# -----------------------------------------------------------------------------
# Variables & couleurs
# -----------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

CURRENT_USER="$(whoami)"
HOME_DIR="$HOME"
REPO_URL="https://github.com/lfpoulain/SimpleBooth"
APP_DIR="$HOME_DIR/SimpleBooth"
VENV_DIR="$APP_DIR/venv"

TOTAL_STEPS=7

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
show_header() {
    clear
    echo -e "${PURPLE}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${PURPLE}║${WHITE}          SimpleBooth Kiosk Installer v1.1                ${PURPLE}║${NC}"
    echo -e "${PURPLE}╠═══════════════════════════════════════════════════════════╣${NC}"
    echo -e "${PURPLE}║${CYAN}  Installation automatique pour Raspberry Pi OS           ${PURPLE}║${NC}"
    echo -e "${PURPLE}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

spinner() {
    # Affiche un spinner jusqu'à la fin du PID passé en argument
    local pid="$1"
    local delay=0.1
    local charset='|/-\\'
    while kill -0 "$pid" 2>/dev/null; do
        for ((i = 0; i < ${#charset}; i++)); do
            printf " [%c]  " "${charset:$i:1}"
            sleep "$delay"
            printf "\b\b\b\b\b\b"
        done
    done
    wait "$pid"
}

check_raspbian() {
    if ! grep -Eq "Raspbian|Raspberry Pi OS" /etc/os-release 2>/dev/null; then
        echo -e "${YELLOW}⚠ Ce script est optimisé pour Raspberry Pi OS.${NC}"
        read -rp $'Continuer malgré tout ? (o/N) : ' response
        if [[ ! "$response" =~ ^[Oo]$ ]]; then
            echo -e "${RED}Installation annulée.${NC}"
            exit 1
        fi
    fi
}

# -----------------------------------------------------------------------------
# Étape 1 : Mise à jour système
# -----------------------------------------------------------------------------
update_system() {
    show_header
    echo -e "${BLUE}📦 Étape 1/${TOTAL_STEPS} : Mise à jour du système${NC}"
    echo -e "${WHITE}Cette étape peut prendre quelques minutes…${NC}\n"

    echo -e "${CYAN}→ Mise à jour de la liste des paquets…${NC}"
    sudo apt-get update -y >/dev/null 2>&1 & spinner $!
    echo -e "${GREEN}✓ Liste des paquets mise à jour${NC}"

    echo -e "${CYAN}→ Mise à niveau des paquets installés…${NC}"
    sudo apt-get upgrade -y >/dev/null 2>&1 & spinner $!
    echo -e "${GREEN}✓ Système à jour${NC}\n"
    sleep 2
}

# -----------------------------------------------------------------------------
# Étape 2 : Installation des dépendances
# -----------------------------------------------------------------------------
install_dependencies() {
    show_header
    echo -e "${BLUE}📦 Étape 2/${TOTAL_STEPS} : Installation des dépendances${NC}\n"

    local packages=(
        git
        curl
        python3 python3-pip python3-venv
        build-essential libcap-dev libjpeg-dev zlib1g-dev
        chromium-browser
        xserver-xorg xinit x11-xserver-utils unclutter
    )

    echo -e "${CYAN}→ Installation des paquets requis…${NC}"
    sudo apt-get install -y "${packages[@]}" & spinner $!
    echo -e "\n${GREEN}✓ Toutes les dépendances sont installées !${NC}\n"
    sleep 2
}

# -----------------------------------------------------------------------------
# Étape 3 : Configuration de l’écran Waveshare (optionnel)
# -----------------------------------------------------------------------------
configure_waveshare_display() {
    show_header
    echo -e "${BLUE}🖥️ Étape 3/${TOTAL_STEPS} : Configuration de l’affichage${NC}\n"

    read -rp $'Utilisez‑vous un écran Waveshare 7" DSI ? (o/N) : ' response
    if [[ ! "$response" =~ ^[Oo]$ ]]; then
        echo -e "${GREEN}✓ Configuration de l’affichage standard conservée${NC}"
        WAVESHARE_CONFIGURED=false
        sleep 2
        return
    fi

    echo -e "${CYAN}→ Configuration de l’écran Waveshare …${NC}"

    local CONFIG_FILE="/boot/firmware/config.txt"
    [[ -f "$CONFIG_FILE" ]] || CONFIG_FILE="/boot/config.txt"

    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo -e "${RED}❌ Impossible de trouver config.txt${NC}"
        sleep 3; return
    fi

    sudo cp "$CONFIG_FILE" "${CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
    echo -e "${GREEN}✓ Sauvegarde créée${NC}"

    # Remove previous entries if any
    sudo sed -i '/waveshare-panel/d' "$CONFIG_FILE"
    sudo sed -i '/lcd_rotate=2/d' "$CONFIG_FILE"

    read -rp $'Quel port DSI utilisez‑vous ? [1] DSI1 / [2] DSI0 : ' dsi_choice
    dsi_choice=${dsi_choice:-1}

    # Ensure vc4 kms overlay
    grep -q '^dtoverlay=vc4-kms-v3d' "$CONFIG_FILE" || echo 'dtoverlay=vc4-kms-v3d' | sudo tee -a "$CONFIG_FILE" >/dev/null

    {
        echo "";
        echo "# Configuration Waveshare 7 pouces DSI – SimpleBooth Installer";
        if [[ "$dsi_choice" == "2" ]]; then
            echo "dtoverlay=vc4-kms-dsi-waveshare-panel,7_0_inchC,dsi0,i2c1";
        else
            echo "dtoverlay=vc4-kms-dsi-waveshare-panel,7_0_inchC,i2c1";
        fi
        echo "lcd_rotate=2";
    } | sudo tee -a "$CONFIG_FILE" >/dev/null

    echo -e "${GREEN}✓ Configuration Waveshare ajoutée !${NC}"
    WAVESHARE_CONFIGURED=true
    echo -e "${YELLOW}⚠ Un redémarrage sera nécessaire pour appliquer les changements${NC}"
    sleep 3
}

# -----------------------------------------------------------------------------
# Étape 4 : Clonage (ou mise à jour) du dépôt
# -----------------------------------------------------------------------------
clone_repository() {
    show_header
    echo -e "${BLUE}📦 Étape 4/${TOTAL_STEPS} : Clonage du dépôt SimpleBooth${NC}\n"

    if [[ "$(pwd)" == *"SimpleBooth"* ]]; then
        APP_DIR="$(pwd)"; VENV_DIR="$APP_DIR/venv"
        if [[ -d .git ]]; then
            read -rp $'Mettre à jour le dépôt existant ? (o/N) : ' response
            if [[ "$response" =~ ^[Oo]$ ]]; then
                git pull
            fi
        fi
        sleep 2; return
    fi

    if [[ -d "$APP_DIR" ]]; then
        echo -e "${YELLOW}⚠ Le dossier $APP_DIR existe déjà.${NC}"
        PS3="Votre choix : "
        select choice in "Supprimer & re‑cloner" "Mettre à jour (git pull)" "Garder tel quel"; do
            case $REPLY in
                1) rm -rf "$APP_DIR"; break;;
                2) git -C "$APP_DIR" pull; sleep 2; return;;
                3) sleep 2; return;;
            esac
        done
    fi

    echo -e "${CYAN}→ Clonage du dépôt…${NC}"
    git clone "$REPO_URL" "$APP_DIR" & spinner $!
    echo -e "\n${GREEN}✓ Dépôt cloné${NC}\n"
    sleep 2
}

# -----------------------------------------------------------------------------
# Étape 5 : Environnement Python
# -----------------------------------------------------------------------------
setup_python_env() {
    show_header
    echo -e "${BLUE}📦 Étape 5/${TOTAL_STEPS} : Configuration de l’environnement Python${NC}\n"

    cd "$APP_DIR"
    echo -e "${CYAN}→ Création de l’environnement virtuel…${NC}"
    python3 -m venv "$VENV_DIR" & spinner $!
    echo -e "\n${GREEN}✓ venv créé${NC}"

    # Activate & install deps
    source "$VENV_DIR/bin/activate"
    pip install --upgrade pip >/dev/null 2>&1

    if [[ -f requirements.txt ]]; then
        echo -e "${CYAN}→ Installation depuis requirements.txt…${NC}"
        pip install -r requirements.txt & spinner $!
    else
        echo -e "${YELLOW}⚠ Pas de requirements.txt, installation de base…${NC}"
        pip install flask pillow numpy opencv-python-headless & spinner $!
    fi

    deactivate
    echo -e "\n${GREEN}✓ Environnement Python prêt${NC}\n"
    sleep 2
}

# -----------------------------------------------------------------------------
# Étape 6 : Mode kiosk (script start & stop)
# -----------------------------------------------------------------------------
setup_kiosk_mode() {
    show_header
    echo -e "${BLUE}📦 Étape 6/${TOTAL_STEPS} : Configuration du mode kiosk${NC}\n"

    # Script de démarrage
    cat > "$HOME_DIR/start_simplebooth.sh" << 'EOF'
#!/usr/bin/env bash
xset s off
xset -dpms
xset s noblank
unclutter -idle 0.1 -root &

APP_DIR="$HOME/SimpleBooth"
VENV_DIR="$APP_DIR/venv"
LOG_FILE="$HOME/simplebooth.log"

cd "$APP_DIR" || exit 1
source "$VENV_DIR/bin/activate"

echo "Démarrage SimpleBooth : $(date)" > "$LOG_FILE"
python app.py >> "$LOG_FILE" 2>&1 &
APP_PID=$!

# Attendre que le serveur écoute sur 5000
for _ in {1..30}; do
    if curl -s http://localhost:5000 >/dev/null 2>&1; then break; fi
    if ! kill -0 "$APP_PID" 2>/dev/null; then echo "Python stoppé" >> "$LOG_FILE"; exit 1; fi
    sleep 2
done

chromium-browser --kiosk --disable-infobars --disable-session-crashed-bubble --autoplay-policy=no-user-gesture-required --disable-features=TranslateUI,MediaEngagementBypassAutoplayPolicies --no-sandbox http://localhost:5000 &
CHROME_PID=$!

cleanup() { kill "$APP_PID" "$CHROME_PID" 2>/dev/null || true; killall unclutter 2>/dev/null || true; }
trap cleanup SIGINT SIGTERM
wait "$APP_PID"
EOF
    chmod +x "$HOME_DIR/start_simplebooth.sh"
    echo -e "${GREEN}✓ Script de démarrage créé${NC}"

    # Script d’arrêt d’urgence (utilise systemd)
    cat > "$HOME_DIR/stop_simplebooth.sh" << 'EOF'
#!/usr/bin/env bash
sudo systemctl stop simplebooth-kiosk.service
EOF
    chmod +x "$HOME_DIR/stop_simplebooth.sh"
    echo -e "${GREEN}✓ Script d’arrêt créé${NC}\n"
    sleep 2
}

# -----------------------------------------------------------------------------
# Étape 7 : Service systemd
# -----------------------------------------------------------------------------
setup_systemd_service() {
    show_header
    echo -e "${BLUE}📦 Étape 7/${TOTAL_STEPS} : Configuration du service systemd${NC}\n"

    sudo tee /etc/systemd/system/simplebooth-kiosk.service >/dev/null << EOF
[Unit]
Description=SimpleBooth Kiosk
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/startx -- -nocursor
Restart=on-failure
User=$CURRENT_USER
WorkingDirectory=$HOME_DIR
Environment="HOME=$HOME_DIR"
Environment="DISPLAY=:0"
Environment="XAUTHORITY=%h/.Xauthority"
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable simplebooth-kiosk.service
    echo -e "${GREEN}✓ Service systemd installé & activé${NC}\n"
    sleep 2
}

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
main() {
    show_header
    echo -e "${WHITE}Bienvenue dans l’installateur SimpleBooth !${NC}\n"
    echo -e "${CYAN}Infos système :${NC}"
    echo -e "  • Utilisateur : ${GREEN}$CURRENT_USER${NC}"
    echo -e "  • HOME       : ${GREEN}$HOME_DIR${NC}"
    echo -e "  • Dossier app : ${GREEN}$APP_DIR${NC}\n"
    echo -e "${YELLOW}Ce script va :${NC}"
    echo -e "  1. Mettre à jour le système"
    echo -e "  2. Installer les dépendances"
    echo -e "  3. (Optionnel) Configurer un écran Waveshare 7″"
    echo -e "  4. Cloner ou mettre à jour le dépôt SimpleBooth"
    echo -e "  5. Créer l’environnement Python"
    echo -e "  6. Générer les scripts de démarrage/arrêt"
    echo -e "  7. Créer et activer le service systemd\n"
    read -rp $'Appuyez sur Entrée pour commencer ou Ctrl+C pour annuler…'

    check_raspbian
    WAVESHARE_CONFIGURED=false

    update_system
    install_dependencies
    configure_waveshare_display
    clone_repository
    setup_python_env
    setup_kiosk_mode
    setup_systemd_service

    show_header
    echo -e "${GREEN}🎉 Installation terminée !${NC}\n"
    echo -e "${CYAN}Commandes utiles :${NC}"
    echo -e "  • Démarrage manuel : ${WHITE}$HOME_DIR/start_simplebooth.sh${NC}"
    echo -e "  • Via systemd    : ${WHITE}sudo systemctl start simplebooth-kiosk${NC}"
    echo -e "  • Arrêt          : ${WHITE}sudo systemctl stop simplebooth-kiosk${NC}"
    echo -e "  • Logs           : ${WHITE}sudo journalctl -u simplebooth-kiosk -f${NC}\n"

    if [[ "$WAVESHARE_CONFIGURED" == true ]]; then
        echo -e "${YELLOW}⚠ Un redémarrage est requis pour l’écran Waveshare.${NC}"
        read -rp $'Redémarrer maintenant ? (o/N) : ' resp
        if [[ "$resp" =~ ^[Oo]$ ]]; then
            echo -e "${CYAN}Redémarrage dans 5 s…${NC}"
            sleep 5
            sudo reboot
        fi
    fi
}

main "$@"

#!/bin/bash

# SimpleBooth Kiosk Installer Script
# Auteur: Assistant IA
# Description: Script d'installation automatique pour SimpleBooth en mode kiosk sur Raspbian

# Couleurs pour l'interface
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
WHITE='\033[1;37m'
NC='\033[0m' # No Color

# Variables globales
CURRENT_USER=$(whoami)
HOME_DIR=$HOME
REPO_URL="https://github.com/lfpoulain/SimpleBooth"
APP_DIR="$HOME_DIR/SimpleBooth"
VENV_DIR="$APP_DIR/venv"
CURRENT_DIR=$(pwd)

# Fonction pour afficher le header
show_header() {
    clear
    echo -e "${PURPLE}╔═══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${PURPLE}║${WHITE}          SimpleBooth Kiosk Installer v1.0                 ${PURPLE}║${NC}"
    echo -e "${PURPLE}╠═══════════════════════════════════════════════════════════╣${NC}"
    echo -e "${PURPLE}║${CYAN}  Installation automatique pour Raspberry Pi               ${PURPLE}║${NC}"
    echo -e "${PURPLE}╚═══════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# Fonction pour afficher une barre de progression
progress_bar() {
    local current=$1
    local total=$2
    local width=50
    local percentage=$((current * 100 / total))
    local completed=$((width * current / total))
    
    printf "\r["
    printf "%${completed}s" | tr ' ' '='
    printf "%$((width - completed))s" | tr ' ' '-'
    printf "] %d%%" $percentage
}

# Fonction pour vérifier si on est sur Raspbian
check_raspbian() {
    if ! grep -q "Raspbian" /etc/os-release 2>/dev/null; then
        echo -e "${YELLOW}⚠ Attention: Ce script est optimisé pour Raspbian${NC}"
        echo -e "${YELLOW}Voulez-vous continuer quand même? (o/N)${NC}"
        read -r response
        if [[ ! "$response" =~ ^[Oo]$ ]]; then
            echo -e "${RED}Installation annulée.${NC}"
            exit 1
        fi
    fi
}

# Fonction pour afficher un spinner pendant les opérations longues
spinner() {
    local pid=$1
    local delay=0.1
    local spinstr='|/-\'
    while [ "$(ps a | awk '{print $1}' | grep $pid)" ]; do
        local temp=${spinstr#?}
        printf " [%c]  " "$spinstr"
        local spinstr=$temp${spinstr%"$temp"}
        sleep $delay
        printf "\b\b\b\b\b\b"
    done
    printf "    \b\b\b\b"
}

# Étape 1: Mise à jour du système
update_system() {
    show_header
    echo -e "${BLUE}📦 Étape 1/6: Mise à jour du système${NC}"
    echo -e "${WHITE}Cette étape peut prendre quelques minutes...${NC}"
    echo ""
    
    echo -e "${CYAN}→ Mise à jour de la liste des paquets...${NC}"
    sudo apt-get update -y > /dev/null 2>&1 &
    spinner $!
    echo -e "${GREEN}✓ Liste des paquets mise à jour${NC}"
    
    echo -e "${CYAN}→ Mise à jour des paquets installés...${NC}"
    sudo apt-get upgrade -y > /dev/null 2>&1 &
    spinner $!
    echo -e "${GREEN}✓ Paquets mis à jour${NC}"
    
    echo ""
    echo -e "${GREEN}✓ Système mis à jour avec succès!${NC}"
    sleep 2
}

# Étape 2: Installation des dépendances
install_dependencies() {
    show_header
    echo -e "${BLUE}📦 Étape 2/6: Installation des dépendances${NC}"
    echo ""
    
    local packages=(
        "git"
        "python3"
        "python3-pip"
        "python3-venv"
        "build-essential"
        "libcap-dev"
        "libjpeg-dev"
        "zlib1g-dev"
        "chromium-browser"
        "xserver-xorg"
        "xinit"
        "x11-xserver-utils"
        "unclutter"
    )
    
    local total=${#packages[@]}
    local current=0
    
    for package in "${packages[@]}"; do
        current=$((current + 1))
        echo -e "${CYAN}→ Installation de $package...${NC}"
        progress_bar $current $total
        sudo apt-get install -y "$package" > /dev/null 2>&1
        echo -e " ${GREEN}✓${NC}"
    done
    
    echo ""
    echo -e "${GREEN}✓ Toutes les dépendances sont installées!${NC}"
    sleep 2
}

# Configuration de l'écran Waveshare
configure_waveshare_display() {
    show_header
    echo -e "${BLUE}🖥️ Configuration de l'affichage${NC}"
    echo ""
    
    echo -e "${YELLOW}Utilisez-vous un écran Waveshare 7 pouces DSI?${NC}"
    echo -e "${CYAN}Si vous n'êtes pas sûr, répondez Non${NC}"
    echo -e "${WHITE}Répondre Oui configurera l'écran avec rotation à 180°${NC}"
    echo ""
    echo -e "Votre choix (o/N): "
    read -r response
    
    if [[ "$response" =~ ^[Oo]$ ]]; then
        echo -e "${CYAN}→ Configuration de l'écran Waveshare 7\" DSI...${NC}"
        
        # Déterminer le bon fichier config.txt
        CONFIG_FILE="/boot/firmware/config.txt"
        if [ ! -f "$CONFIG_FILE" ]; then
            CONFIG_FILE="/boot/config.txt"
        fi
        
        if [ ! -f "$CONFIG_FILE" ]; then
            echo -e "${RED}❌ Impossible de trouver le fichier config.txt${NC}"
            echo -e "${YELLOW}Veuillez configurer manuellement l'écran${NC}"
            sleep 3
            return
        fi
        
        # Backup du fichier original
        echo -e "${CYAN}→ Sauvegarde de la configuration actuelle...${NC}"
        sudo cp "$CONFIG_FILE" "${CONFIG_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
        echo -e "${GREEN}✓ Sauvegarde créée${NC}"
        
        # Vérifier si la configuration existe déjà
        if grep -q "waveshare-panel" "$CONFIG_FILE"; then
            echo -e "${YELLOW}⚠ Une configuration Waveshare existe déjà${NC}"
            echo -e "Voulez-vous la remplacer? (o/N): "
            read -r replace
            if [[ ! "$replace" =~ ^[Oo]$ ]]; then
                echo -e "${GREEN}✓ Configuration existante conservée${NC}"
                sleep 2
                return
            fi
            # Supprimer l'ancienne configuration
            sudo sed -i '/waveshare-panel/d' "$CONFIG_FILE"
            sudo sed -i '/display_rotate=2/d' "$CONFIG_FILE"
        fi
        
        # Choix du port DSI
        echo -e "${CYAN}Quel port DSI utilisez-vous?${NC}"
        echo -e "  1) DSI1 (par défaut)"
        echo -e "  2) DSI0"
        echo -e "Votre choix (1/2) [1]: "
        read -r dsi_choice
        
        # Ajout de la configuration
        echo -e "${CYAN}→ Ajout de la configuration Waveshare...${NC}"
        
        # Vérifier si dtoverlay=vc4-kms-v3d existe déjà
        if ! grep -q "^dtoverlay=vc4-kms-v3d" "$CONFIG_FILE"; then
            echo "dtoverlay=vc4-kms-v3d" | sudo tee -a "$CONFIG_FILE" > /dev/null
        fi
        
        # Ajouter un marqueur pour identifier notre configuration
        echo "" | sudo tee -a "$CONFIG_FILE" > /dev/null
        echo "# Configuration Waveshare 7 pouces DSI - Ajouté par SimpleBooth Installer" | sudo tee -a "$CONFIG_FILE" > /dev/null
        
        if [[ "$dsi_choice" == "2" ]]; then
            echo "# DSI0 Use" | sudo tee -a "$CONFIG_FILE" > /dev/null
            echo "dtoverlay=vc4-kms-dsi-waveshare-panel,7_0_inchC,dsi0,i2c1" | sudo tee -a "$CONFIG_FILE" > /dev/null
        else
            echo "# DSI1 Use" | sudo tee -a "$CONFIG_FILE" > /dev/null
            echo "dtoverlay=vc4-kms-dsi-waveshare-panel,7_0_inchC,i2c1" | sudo tee -a "$CONFIG_FILE" > /dev/null
        fi
        
        echo "display_rotate=2" | sudo tee -a "$CONFIG_FILE" > /dev/null
        
        echo -e "${GREEN}✓ Configuration Waveshare ajoutée avec succès!${NC}"
        echo -e "${YELLOW}⚠ Un redémarrage sera nécessaire pour appliquer les changements${NC}"
        
        # Afficher la configuration ajoutée
        echo ""
        echo -e "${CYAN}Configuration ajoutée:${NC}"
        echo -e "${WHITE}───────────────────────${NC}"
        tail -n 5 "$CONFIG_FILE"
        echo -e "${WHITE}───────────────────────${NC}"
        
        WAVESHARE_CONFIGURED=true
    else
        echo -e "${GREEN}✓ Configuration de l'affichage standard conservée${NC}"
        WAVESHARE_CONFIGURED=false
    fi
    
    sleep 3
}

# Étape 3: Clonage du repository
clone_repository() {
    show_header
    echo -e "${BLUE}📦 Étape 4/7: Clonage du repository SimpleBooth${NC}"
    echo ""
    
    # Vérifier si on est déjà dans le dossier SimpleBooth
    CURRENT_DIR=$(pwd)
    if [[ "$CURRENT_DIR" == *"SimpleBooth"* ]]; then
        echo -e "${GREEN}✓ Déjà dans le dossier SimpleBooth${NC}"
        echo -e "${CYAN}Utilisation du dossier actuel: $CURRENT_DIR${NC}"
        APP_DIR="$CURRENT_DIR"
        VENV_DIR="$APP_DIR/venv"
        
        # Vérifier si c'est bien un repo git
        if [ -d ".git" ]; then
            echo -e "${CYAN}Voulez-vous mettre à jour le repository (git pull)? (o/N)${NC}"
            read -r response
            if [[ "$response" =~ ^[Oo]$ ]]; then
                echo -e "${CYAN}→ Mise à jour du repository...${NC}"
                git pull
                echo -e "${GREEN}✓ Repository mis à jour${NC}"
            fi
        fi
        sleep 2
        return
    fi
    
    # Si on n'est pas dans SimpleBooth, procéder normalement
    if [ -d "$APP_DIR" ]; then
        echo -e "${YELLOW}⚠ Le dossier $APP_DIR existe déjà.${NC}"
        echo -e "${YELLOW}Que voulez-vous faire?${NC}"
        echo -e "  1) Supprimer et re-cloner"
        echo -e "  2) Mettre à jour (git pull)"
        echo -e "  3) Garder tel quel"
        read -r choice
        
        case $choice in
            1)
                echo -e "${CYAN}→ Suppression de l'ancien dossier...${NC}"
                rm -rf "$APP_DIR"
                ;;
            2)
                echo -e "${CYAN}→ Mise à jour du repository...${NC}"
                cd "$APP_DIR" && git pull
                echo -e "${GREEN}✓ Repository mis à jour${NC}"
                sleep 2
                return
                ;;
            3)
                echo -e "${GREEN}✓ Conservation du dossier existant${NC}"
                sleep 2
                return
                ;;
        esac
    fi
    
    echo -e "${CYAN}→ Clonage du repository...${NC}"
    git clone "$REPO_URL" "$APP_DIR" > /dev/null 2>&1 &
    spinner $!
    echo -e "${GREEN}✓ Repository cloné avec succès!${NC}"
    sleep 2
}

# Étape 4: Installation de l'environnement Python
setup_python_env() {
    show_header
    echo -e "${BLUE}📦 Étape 5/7: Configuration de l'environnement Python${NC}"
    echo ""
    
    cd "$APP_DIR"
    
    # Création de l'environnement virtuel
    echo -e "${CYAN}→ Création de l'environnement virtuel...${NC}"
    python3 -m venv "$VENV_DIR" > /dev/null 2>&1 &
    spinner $!
    echo -e "${GREEN}✓ Environnement virtuel créé${NC}"
    
    # Activation et installation des dépendances
    echo -e "${CYAN}→ Installation des dépendances Python...${NC}"
    source "$VENV_DIR/bin/activate"
    
    # Mise à jour de pip
    pip install --upgrade pip > /dev/null 2>&1
    
    # Installation des dépendances depuis requirements.txt si il existe
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt > /dev/null 2>&1 &
        spinner $!
        echo -e "${GREEN}✓ Dépendances Python installées${NC}"
    else
        echo -e "${YELLOW}⚠ Pas de fichier requirements.txt trouvé${NC}"
    # Installation des dépendances communes pour une app Python
        echo -e "${CYAN}→ Installation des dépendances de base...${NC}"
        pip install flask pillow numpy opencv-python-headless > /dev/null 2>&1 &
        spinner $!
    fi
    
    deactivate
    echo ""
    echo -e "${GREEN}✓ Environnement Python configuré!${NC}"
    sleep 2
}

# Étape 5: Configuration du mode kiosk
setup_kiosk_mode() {
    show_header
    echo -e "${BLUE}📦 Étape 6/7: Configuration du mode kiosk${NC}"
    echo ""
    
    # Création du script de démarrage
    echo -e "${CYAN}→ Création du script de démarrage...${NC}"
    
    cat > "$HOME_DIR/start_simplebooth.sh" << EOF
#!/bin/bash
# Script de démarrage SimpleBooth

# Désactivation du screensaver et du power management
xset s off
xset -dpms
xset s noblank

# Masquer le curseur après 0.1 secondes d'inactivité
unclutter -idle 0.1 -root &

# Démarrage de l'application SimpleBooth
cd $APP_DIR
source $VENV_DIR/bin/activate

# Rediriger les logs pour debug
LOG_FILE="$HOME_DIR/simplebooth.log"
echo "Démarrage SimpleBooth: \$(date)" > \$LOG_FILE

# Démarrer Python et capturer les erreurs
python app.py >> \$LOG_FILE 2>&1 &
APP_PID=\$!

# Fonction pour vérifier si le serveur est prêt
wait_for_server() {
    echo "Attente du serveur..." >> \$LOG_FILE
    local max_attempts=30
    local attempt=0
    
    while [ \$attempt -lt \$max_attempts ]; do
        if curl -s http://localhost:5000 > /dev/null 2>&1; then
            echo "Serveur prêt!" >> \$LOG_FILE
            return 0
        fi
        
        # Vérifier si le processus Python est toujours en vie
        if ! ps -p \$APP_PID > /dev/null; then
            echo "ERREUR: Le processus Python s'est arrêté!" >> \$LOG_FILE
            echo "Dernières lignes du log:" >> \$LOG_FILE
            tail -20 \$LOG_FILE
            exit 1
        fi
        
        attempt=\$((attempt + 1))
        echo "Tentative \$attempt/\$max_attempts..." >> \$LOG_FILE
        sleep 2
    done
    
    echo "ERREUR: Timeout - le serveur n'a pas démarré" >> \$LOG_FILE
    return 1
}

# Attendre que le serveur soit prêt
if wait_for_server; then
    echo "Lancement de Chromium..." >> \$LOG_FILE
    # Lancer Chromium en mode kiosk
    chromium-browser --kiosk --no-sandbox --disable-infobars --disable-session-crashed-bubble --disable-restore-session-state --disable-translate --disable-features=TranslateUI --disable-popup-blocking --disable-component-update --autoplay-policy=no-user-gesture-required --disable-features=PreloadMediaEngagementData,AutoplayIgnoreWebAudio,MediaEngagementBypassAutoplayPolicies http://localhost:5000 &
    CHROME_PID=\$!
else
    echo "Impossible de démarrer le serveur. Vérifiez les logs dans: \$LOG_FILE" >> \$LOG_FILE
    exit 1
fi

# Fonction pour arrêter proprement
cleanup() {
    echo "Arrêt de SimpleBooth..." >> \$LOG_FILE
    kill \$APP_PID 2>/dev/null
    kill \$CHROME_PID 2>/dev/null
    killall unclutter 2>/dev/null
    exit 0
}

# Capturer les signaux pour un arrêt propre
trap cleanup SIGINT SIGTERM

# Garder le script en vie et permettre Ctrl+C
wait \$APP_PID
EOF

    chmod +x "$HOME_DIR/start_simplebooth.sh"
    echo -e "${GREEN}✓ Script de démarrage créé${NC}"
    
    # Configuration de l'autostart
    echo -e "${CYAN}→ Configuration du démarrage automatique...${NC}"
    
    # Création du dossier autostart si nécessaire
    mkdir -p "$HOME_DIR/.config/autostart"
    
    # Création du fichier .desktop pour l'autostart
    cat > "$HOME_DIR/.config/autostart/simplebooth.desktop" << EOF
[Desktop Entry]
Type=Application
Name=SimpleBooth Kiosk
Exec=$HOME_DIR/start_simplebooth.sh
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment=Démarrage automatique de SimpleBooth en mode kiosk
EOF

    echo -e "${GREEN}✓ Démarrage automatique configuré${NC}"
    
    # Configuration de .xinitrc pour startx
    echo -e "${CYAN}→ Configuration de X11...${NC}"
    cat > "$HOME_DIR/.xinitrc" << EOF
#!/bin/bash
exec $HOME_DIR/start_simplebooth.sh
EOF
    chmod +x "$HOME_DIR/.xinitrc"
    
    # Création du script d'arrêt d'urgence
    echo -e "${CYAN}→ Création du script d'arrêt d'urgence...${NC}"
    cat > "$HOME_DIR/stop_simplebooth.sh" << EOF
#!/bin/bash
# Script d'arrêt d'urgence SimpleBooth

echo "Arrêt de SimpleBooth..."

# Arrêter le service systemd si actif
sudo systemctl stop simplebooth-kiosk 2>/dev/null

# Tuer les processus
pkill -f "python app.py"
pkill -f "chromium-browser.*kiosk"
killall unclutter 2>/dev/null

# Retour au terminal
clear
echo "SimpleBooth arrêté."
echo "Pour redémarrer : sudo systemctl start simplebooth-kiosk"
EOF
    chmod +x "$HOME_DIR/stop_simplebooth.sh"
    echo -e "${GREEN}✓ Script d'arrêt créé${NC}"
    
    echo -e "${GREEN}✓ Configuration X11 terminée${NC}"
    sleep 2
}

# Étape 6: Configuration finale et service systemd
setup_systemd_service() {
    show_header
    echo -e "${BLUE}📦 Étape 7/7: Configuration du service systemd${NC}"
    echo ""
    
    echo -e "${CYAN}→ Création du service systemd...${NC}"
    
    sudo tee /etc/systemd/system/simplebooth-kiosk.service > /dev/null << EOF
[Unit]
Description=SimpleBooth Kiosk Mode
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/bin/startx -- -nocursor
Restart=on-failure
User=$CURRENT_USER
WorkingDirectory=$HOME_DIR
Environment="HOME=$HOME_DIR"
Environment="DISPLAY=:0"

[Install]
WantedBy=multi-user.target
EOF

    # Activation du service
    echo -e "${CYAN}→ Activation du service...${NC}"
    sudo systemctl daemon-reload
    sudo systemctl enable simplebooth-kiosk.service
    echo -e "${GREEN}✓ Service systemd configuré et activé${NC}"
    
    sleep 2
}

# Fonction principale
main() {
    show_header
    echo -e "${WHITE}Bienvenue dans l'installateur SimpleBooth Kiosk!${NC}"
    echo ""
    echo -e "${CYAN}Informations système:${NC}"
    echo -e "  • Utilisateur: ${GREEN}$CURRENT_USER${NC}"
    echo -e "  • Dossier home: ${GREEN}$HOME_DIR${NC}"
    echo -e "  • Dossier d'installation: ${GREEN}$APP_DIR${NC}"
    echo ""
    echo -e "${YELLOW}Ce script va:${NC}"
    echo -e "  1. Mettre à jour votre système"
    echo -e "  2. Installer les dépendances nécessaires"
    echo -e "  3. Configurer l'écran (optionnel - Waveshare 7\" DSI)"
    echo -e "  4. Cloner le repository SimpleBooth"
    echo -e "  5. Configurer l'environnement Python"
    echo -e "  6. Configurer le mode kiosk"
    echo -e "  7. Créer un service de démarrage automatique"
    echo ""
    echo -e "${WHITE}Appuyez sur Entrée pour continuer ou Ctrl+C pour annuler...${NC}"
    read -r
    
    # Vérification du système
    check_raspbian
    
    # Variable pour savoir si Waveshare a été configuré
    WAVESHARE_CONFIGURED=false
    
    # Exécution des étapes
    update_system
    install_dependencies
    configure_waveshare_display
    clone_repository
    setup_python_env
    setup_kiosk_mode
    setup_systemd_service
    
    # Fin de l'installation
    show_header
    echo -e "${GREEN}🎉 Installation terminée avec succès!${NC}"
    echo ""
    echo -e "${CYAN}Pour démarrer SimpleBooth:${NC}"
    echo -e "  • Manuellement: ${WHITE}$HOME_DIR/start_simplebooth.sh${NC}"
    echo -e "  • Via systemd: ${WHITE}sudo systemctl start simplebooth-kiosk${NC}"
    echo ""
    echo -e "${CYAN}Pour arrêter SimpleBooth:${NC}"
    echo -e "  • Via SSH: ${WHITE}sudo systemctl stop simplebooth-kiosk${NC}"
    echo -e "  • Script d'arrêt: ${WHITE}$HOME_DIR/stop_simplebooth.sh${NC}"
    echo ""
    echo -e "${CYAN}Pour déboguer en cas de problème:${NC}"
    echo -e "  • Logs de l'application: ${WHITE}cat $HOME_DIR/simplebooth.log${NC}"
    echo -e "  • Logs du service: ${WHITE}sudo journalctl -u simplebooth-kiosk -f${NC}"
    echo ""
    echo -e "${CYAN}SimpleBooth démarrera automatiquement au prochain redémarrage.${NC}"
    echo ""
    
    if [ "$WAVESHARE_CONFIGURED" = true ]; then
        echo -e "${YELLOW}⚠ Configuration Waveshare détectée${NC}"
        echo -e "${YELLOW}Un redémarrage est nécessaire pour appliquer les changements d'affichage${NC}"
        echo ""
    fi
    
    echo -e "${YELLOW}Voulez-vous redémarrer maintenant? (o/N)${NC}"
    read -r response
    
    if [[ "$response" =~ ^[Oo]$ ]]; then
        echo -e "${CYAN}Redémarrage dans 5 secondes...${NC}"
        sleep 5
        sudo reboot
    fi
}

# Exécution du script
main
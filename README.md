# 📸 Photobooth Raspberry Pi

> **Application Flask professionnelle pour photobooth tactile avec flux vidéo temps réel, capture instantanée, effets IA et intégration Telegram**

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Flask](https://img.shields.io/badge/Flask-2.3.3-green.svg)
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Compatible-red.svg)
![Runware](https://img.shields.io/badge/Runware%20AI-Intégré-purple.svg)
![Telegram](https://img.shields.io/badge/Telegram-Bot-blue.svg)
![OpenCV](https://img.shields.io/badge/OpenCV-Support%20USB-brightgreen.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🎯 Aperçu

Cette application transforme votre Raspberry Pi en un photobooth professionnel avec :
- **Flux vidéo temps réel** en MJPEG 1280x720 (16:9)
- **Support multi-caméras** : Pi Camera ou caméra USB
- **Interface tactile optimisée** pour écran 7 pouces
- **Capture photo instantanée** directement depuis le flux vidéo
- **Effets IA** via l'API Runware pour transformer vos photos
- **Diaporama automatique** configurable après période d'inactivité
- **Bot Telegram** pour envoi automatique des photos sur un groupe/canal
- **Impression thermique** avec texte personnalisable
- **Interface d'administration** complète
- **Design moderne** avec Bootstrap 5 et FontAwesome

## 🔧️ Matériel requis

### Matériel supporté

- **Caméra** : 
  - Raspberry Pi Camera (v1, v2, v3, HQ)
  - Caméra USB standard (webcam)
- **Écran tactile** : Écran 7 pouces recommandé
- **Imprimante thermique** : Compatible avec le script `ScriptPythonPOS.py`

### Installation

1. **Installer les dépendances Python :**
```bash
pip install -r requirements.txt
```

2. **Vérifier que votre script d'impression est présent :**
   - Le fichier `ScriptPythonPOS.py` doit être dans le même dossier

3. **Sur Raspberry Pi, installer les dépendances système :**
```bash
sudo apt update
# Pour Pi Camera
sudo apt install libcamera-apps
# Pour caméra USB
sudo apt install python3-opencv
```

## Utilisation

1. **Lancer l'application :**
```bash
python3 app.py
```

2. **Accéder à l'interface :**
   - Ouvrir un navigateur sur `http://localhost:5000`
   - Ou depuis un autre appareil : `http://[IP_RASPBERRY]:5000`

3. **Administration :**
   - Accéder à `/admin` pour configurer l'application

## Configuration des caméras

L'application supporte deux types de caméras, configurables depuis la page d'administration :

### Pi Camera (par défaut)

- Utilise le module `libcamera-vid` pour capturer le flux vidéo
- Idéal pour les Raspberry Pi avec caméra officielle
- Aucune configuration supplémentaire requise

### Caméra USB

- Utilise OpenCV (`cv2`) pour capturer le flux vidéo
- Compatible avec la plupart des webcams USB standard
- Configuration dans l'admin :
  1. Sélectionner "Caméra USB" dans les options de caméra
  2. Spécifier l'ID de la caméra (généralement `0` pour la première caméra)
  3. Si vous avez plusieurs caméras USB, essayez les IDs `1`, `2`, etc.

> **Note** : Si vous rencontrez des problèmes avec la caméra USB, vérifiez que :
> - La caméra est bien connectée et alimentée
> - Les permissions sont correctes (`sudo usermod -a -G video $USER`)
> - La caméra est compatible avec OpenCV

## Structure des fichiers

```
App/
├─ app.py                 # Application Flask principale
├─ ScriptPythonPOS.py     # Script d'impression thermique (existant)
├─ requirements.txt       # Dépendances Python
├─ config.json           # Configuration (généré automatiquement)
├─ photos/               # Photos originales
├─ effet/                # Photos transformées par IA
├─ templates/            # Templates HTML
│   ├─ base.html
│   ├─ index.html        # Page principale
│   ├─ review.html       # Révision photo
│   └─ admin.html        # Administration
└─ README.md
```

## Configuration

La configuration est sauvegardée dans `config.json` :

### Général
- `footer_text` : Texte en pied de photo
- `timer_seconds` : Délai avant capture (1-10 secondes)
- `high_density` : Qualité d'impression haute densité

### Diaporama
- `slideshow_enabled` : Activer/désactiver le diaporama automatique
- `slideshow_delay` : Délai d'inactivité avant affichage du diaporama (10-300 secondes)
- `slideshow_source` : Source des photos pour le diaporama ('photos' ou 'effet')

### Effets IA
- `effect_enabled` : Activer/désactiver les effets IA
- `effect_prompt` : Description textuelle de l'effet IA souhaité
- `effect_steps` : Nombre d'étapes de génération IA (1-50, plus = meilleure qualité mais plus lent)
- `runware_api_key` : Clé API Runware pour l'accès au service IA

### Bot Telegram
- `telegram_enabled` : Activer/désactiver le bot Telegram
- `telegram_bot_token` : Token du bot obtenu via @BotFather
- `telegram_chat_id` : ID du chat/groupe/canal de destination
- `telegram_send_type` : Type de photos à envoyer ('photos', 'effet' ou 'both')

## Notes techniques

- **Caméra** : Utilise `libcamera-still` pour la capture sur Raspberry Pi
- **Impression** : Intègre votre script existant avec les paramètres configurés
- **Interface** : Responsive et optimisée pour écran tactile
- **Stockage** : Photos originales dans `photos/`, photos avec effet IA dans `effet/`
- **IA** : Utilise l'API Runware v1.0.0 pour des transformations artistiques
- **Diaporama** : Mode automatique après période d'inactivité, désactivable dans l'admin
- **Telegram** : Bot asynchrone utilisant python-telegram-bot v20.7

## Configuration du bot Telegram

1. **Créer un bot** : 
   - Contactez [@BotFather](https://t.me/BotFather) sur Telegram
   - Envoyez `/newbot` et suivez les instructions
   - Notez le token fourni (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

2. **Obtenir l'ID du chat** :
   
   Pour un chat privé :
   - Envoyez un message à [@userinfobot](https://t.me/userinfobot) pour obtenir votre ID
   
   Pour un groupe :
   - Ajoutez le bot au groupe d'abord!
   - ID format: `-123456789` (notez le signe négatif)
   - Utilisez [@GroupIDbot](https://t.me/GroupIDbot) pour trouver l'ID
   
   Pour un canal :
   - Ajoutez le bot comme administrateur du canal
   - Format canal public: `@nom_du_canal`
   - Format canal privé: `-100123456789`

3. **Configurer dans l'admin** :
   - Activez l'option Telegram
   - Entrez le token du bot et l'ID du chat
   - Choisissez le type de photos à envoyer (originales, effet, ou les deux)

## Dépannage

- **Caméra non détectée** : Vérifier que la caméra est activée dans `raspi-config`
- **Erreur d'impression** : Vérifier la connexion de l'imprimante thermique
- **Interface lente** : Réduire la résolution ou désactiver la haute densité
- **Effets IA ne fonctionnent pas** : Vérifier la validité de la clé API Runware
- **"Chat not found" dans Telegram** : 
  - Vérifier que le bot est bien membre du groupe/canal
  - Format correct de l'ID (numérique pour privé, commence par `-` pour groupe)
  - Le bot doit être admin pour les canaux
- **Dossier effet manquant** : L'application le crée automatiquement au démarrage

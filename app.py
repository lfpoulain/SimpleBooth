#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, flash, Response, abort
import os
import json
import time
import subprocess
import threading
import asyncio
import requests
import cv2
import shutil
import signal
import atexit
import base64
import sys
from datetime import datetime
from werkzeug.utils import secure_filename
from telegram import Bot
from telegram.error import TelegramError
from runware import Runware, IImageInference
from PIL import Image

app = Flask(__name__)
app.secret_key = 'photobooth_secret_key_2024'

# Configuration
PHOTOS_FOLDER = 'photos'
EFFECT_FOLDER = 'effet'
CONFIG_FILE = 'config.json'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

# Créer les dossiers s'ils n'existent pas
print(f"[DEBUG] Création du dossier photos: {PHOTOS_FOLDER}")
os.makedirs(PHOTOS_FOLDER, exist_ok=True)
print(f"[DEBUG] Création du dossier effet: {EFFECT_FOLDER}")
os.makedirs(EFFECT_FOLDER, exist_ok=True)
print(f"[DEBUG] Dossiers créés - Photos: {os.path.exists(PHOTOS_FOLDER)}, Effet: {os.path.exists(EFFECT_FOLDER)}")

# Configuration par défaut
DEFAULT_CONFIG = {
    'footer_text': 'Photobooth',
    'timer_seconds': 3,
    'high_density': False,
    'slideshow_enabled': False,
    'slideshow_delay': 60,
    'slideshow_source': 'photos',
    'effect_enabled': False,
    'effect_prompt': 'Transform this photo into a beautiful ghibli style',
    'effect_steps': 5,
    'runware_api_key': '',
    'telegram_enabled': False,
    'telegram_bot_token': '',
    'telegram_chat_id': '',
    'telegram_send_type': 'photos',
    'camera_type': 'picamera',  # 'picamera' ou 'usb'
    'usb_camera_id': 0,  # ID de la caméra USB (généralement 0 pour la première caméra)
    # Paramètres d'imprimante
    'printer_enabled': True,
    'printer_port': '/dev/ttyUSB0',  # Port série de l'imprimante
    'printer_baudrate': 9600,  # Vitesse de communication
    'print_resolution': 384  # Résolution d'impression
}

def load_config():
    """Charger la configuration depuis le fichier JSON"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config_data):
    """Sauvegarder la configuration dans un fichier JSON"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)

def check_printer_status():
    """Vérifier l'état de l'imprimante thermique"""
    try:
        # Vérifier si le module escpos est disponible
        try:
            from escpos.printer import Serial
        except ImportError:
            return {
                'status': 'error',
                'message': 'Module escpos manquant. Installez-le avec: pip install python-escpos',
                'paper_status': 'unknown'
            }
        
        # Récupérer la configuration de l'imprimante
        printer_port = config.get('printer_port', '/dev/ttyUSB0')
        printer_baudrate = config.get('printer_baudrate', 9600)
        
        # Vérifier si l'imprimante est activée
        if not config.get('printer_enabled', True):
            return {
                'status': 'disabled',
                'message': 'Imprimante désactivée dans la configuration',
                'paper_status': 'unknown'
            }
        
        # Tenter de se connecter à l'imprimante
        try:
            printer = Serial(printer_port, baudrate=printer_baudrate, timeout=1)
            
            # Vérifier l'état du papier (commande ESC/POS standard)
            printer._raw(b'\x10\x04\x01')  # Commande de statut en temps réel
            
            # Lire la réponse (si disponible)
            # Note: Cette partie peut varier selon le modèle d'imprimante
            
            printer.close()
            
            return {
                'status': 'ok',
                'message': 'Imprimante connectée',
                'paper_status': 'ok',
                'port': printer_port,
                'baudrate': printer_baudrate
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Erreur de connexion: {str(e)}',
                'paper_status': 'unknown',
                'port': printer_port,
                'baudrate': printer_baudrate
            }
            
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Erreur lors de la vérification: {str(e)}',
            'paper_status': 'unknown'
        }

async def _send_telegram_photo(bot_token, chat_id, photo_path, caption):
    """Fonction asynchrone pour envoyer une photo via Telegram"""
    bot = Bot(token=bot_token)
    
    # Vérifier et nettoyer l'ID du chat
    cleaned_chat_id = chat_id.strip()
    
    # Si c'est un nom d'utilisateur ou canal, s'assurer qu'il commence par @
    if cleaned_chat_id and cleaned_chat_id[0].isalpha() and not cleaned_chat_id.startswith('@'):
        cleaned_chat_id = '@' + cleaned_chat_id
    
    print(f"[TELEGRAM] Utilisation de l'ID de chat: '{cleaned_chat_id}'")
    
    try:
        with open(photo_path, 'rb') as photo_file:
            await bot.send_photo(
                chat_id=cleaned_chat_id,
                photo=photo_file,
                caption=caption
            )
    except Exception as e:
        if "chat not found" in str(e).lower():
            print(f"[TELEGRAM] ERREUR: Chat introuvable avec l'ID '{cleaned_chat_id}'")
            print("[TELEGRAM] Assurez-vous que:")
            print("   - Le bot a été ajouté au groupe/canal")
            print("   - Pour un groupe: l'ID commence par '-' (ex: -123456789)")
            print("   - Pour un canal: utilisez '@nom_du_canal' ou ajoutez le bot comme admin")
            print("   - Pour un chat privé: utilisez l'ID numérique de l'utilisateur")
        raise

def send_to_telegram(photo_path, photo_type="photo"):
    """Envoyer une photo sur Telegram"""
    if not config.get('telegram_enabled', False):
        return
    
    bot_token = config.get('telegram_bot_token', '')
    chat_id = config.get('telegram_chat_id', '')
    
    if not bot_token or not chat_id:
        print("[TELEGRAM] Configuration incomplète (token ou chat_id manquant)")
        return
    
    try:
        print(f"[TELEGRAM] Envoi de {photo_path} vers le chat {chat_id}")
        
        # Préparer le message
        caption = f"📸 Nouvelle photo du photobooth!"
        if photo_type == "effet":
            caption = f"🎨 Photo avec effet IA du photobooth!"
        
        # Exécuter la coroutine dans une nouvelle boucle asyncio
        async def send_photo_async():
            try:
                await _send_telegram_photo(bot_token, chat_id, photo_path, caption)
                print("[TELEGRAM] Photo envoyée avec succès!")
            except Exception as e:
                print(f"[TELEGRAM] Erreur dans la coroutine: {e}")
                
        # Exécuter dans une nouvelle boucle d'événements asyncio
        asyncio.run(send_photo_async())
        
    except TelegramError as e:
        print(f"[TELEGRAM] Erreur Telegram: {e}")
    except Exception as e:
        print(f"[TELEGRAM] Erreur lors de l'envoi: {e}")

# Fonction pour détecter les ports série disponibles
def detect_serial_ports():
    """Détecte les ports série disponibles sur le système"""
    available_ports = []
    
    # Détection selon le système d'exploitation
    if sys.platform.startswith('win'):  # Windows
        # Vérifier les ports COM1 à COM20
        import serial.tools.list_ports
        try:
            ports = list(serial.tools.list_ports.comports())
            for port in ports:
                available_ports.append((port.device, f"{port.device} - {port.description}"))
        except ImportError:
            # Si pyserial n'est pas installé, on fait une détection basique
            for i in range(1, 21):
                port = f"COM{i}"
                available_ports.append((port, port))
    
    elif sys.platform.startswith('linux'):  # Linux (Raspberry Pi)
        # Vérifier les ports série courants sur Linux
        common_ports = [
            '/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyUSB2',
            '/dev/ttyACM0', '/dev/ttyACM1', '/dev/ttyACM2',
            '/dev/ttyS0', '/dev/ttyS1', '/dev/ttyAMA0'
        ]
        
        for port in common_ports:
            if os.path.exists(port):
                available_ports.append((port, port))
    
    # Si aucun port n'est trouvé, ajouter des options par défaut
    if not available_ports:
        if sys.platform.startswith('win'):
            available_ports = [('COM1', 'COM1'), ('COM3', 'COM3')]
        else:
            available_ports = [('/dev/ttyUSB0', '/dev/ttyUSB0'), ('/dev/ttyS0', '/dev/ttyS0')]
    
    return available_ports

# Fonction pour détecter les caméras USB disponibles
def detect_cameras():
    """Détecter les caméras USB disponibles et retourner une liste de (id, nom)"""
    available_cameras = []
    print("[CAMERA] Début de la détection des caméras USB...")
    
    # Tester les 10 premiers indices de caméra (0-9) pour être plus exhaustif
    for i in range(10):
        try:
            print(f"[CAMERA] Test de la caméra ID {i}...")
            
            # Essayer différents backends OpenCV
            backends = [cv2.CAP_ANY, cv2.CAP_DSHOW, cv2.CAP_V4L2, cv2.CAP_GSTREAMER]
            cap = None
            
            for backend in backends:
                try:
                    cap = cv2.VideoCapture(i, backend)
                    if cap.isOpened():
                        # Configurer une résolution plus élevée pour tester les capacités
                        resolutions_to_test = [
                            (1920, 1080),  # Full HD
                            (1280, 720),   # HD
                            (640, 480)     # VGA (fallback)
                        ]
                        
                        best_resolution = None
                        best_fps = 0
                        
                        for test_width, test_height in resolutions_to_test:
                            # Essayer de configurer cette résolution
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, test_width)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, test_height)
                            cap.set(cv2.CAP_PROP_FPS, 30)  # Essayer 30 FPS
                            
                            # Vérifier si la résolution a été acceptée
                            actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            actual_fps = cap.get(cv2.CAP_PROP_FPS)
                            
                            # Tester si on peut lire une frame à cette résolution
                            ret, frame = cap.read()
                            if ret and frame is not None and frame.shape[1] >= test_width * 0.9 and frame.shape[0] >= test_height * 0.9:
                                best_resolution = (actual_width, actual_height)
                                best_fps = actual_fps
                                print(f"[CAMERA] Résolution {actual_width}x{actual_height} supportée pour la caméra {i}")
                                break
                            else:
                                print(f"[CAMERA] Résolution {test_width}x{test_height} non supportée pour la caméra {i}")
                        
                        if best_resolution:
                            width, height = best_resolution
                            fps = best_fps
                            
                            # Créer un nom descriptif
                            backend_name = {
                                cv2.CAP_ANY: "Auto",
                                cv2.CAP_DSHOW: "DirectShow",
                                cv2.CAP_V4L2: "V4L2",
                                cv2.CAP_GSTREAMER: "GStreamer"
                            }.get(backend, "Inconnu")
                            
                            name = f"Caméra {i} ({backend_name}) - {width}x{height}@{fps:.1f}fps"
                            available_cameras.append((i, name))
                            print(f"[CAMERA] ✓ Caméra fonctionnelle détectée: {name}")
                            break
                        else:
                            print(f"[CAMERA] Caméra {i} ouverte mais ne peut pas lire de frame avec backend {backend_name}")
                    cap.release()
                except Exception as e:
                    if cap:
                        cap.release()
                    print(f"[CAMERA] Backend {backend} échoué pour caméra {i}: {e}")
                    continue
            
            if not available_cameras or available_cameras[-1][0] != i:
                print(f"[CAMERA] ✗ Caméra {i} non disponible ou non fonctionnelle")
                
        except Exception as e:
            print(f"[CAMERA] Erreur générale lors de la détection de la caméra {i}: {e}")
    
    print(f"[CAMERA] Détection terminée. {len(available_cameras)} caméra(s) fonctionnelle(s) trouvée(s)")
    return available_cameras

# Classe pour gérer la caméra USB
class UsbCamera:
    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.camera = None
        self.is_running = False
        self.thread = None
        self.frame = None
        self.lock = threading.Lock()
        self.error = None
    
    def start(self):
        """Démarrer la caméra USB"""
        if self.is_running:
            return True
        
        return self._initialize_camera()
    
    def _initialize_camera(self):
        """Initialiser la caméra avec différents backends"""
        backends = [cv2.CAP_DSHOW, cv2.CAP_ANY, cv2.CAP_V4L2, cv2.CAP_GSTREAMER]
        
        for backend in backends:
            try:
                backend_name = {
                    cv2.CAP_ANY: "Auto",
                    cv2.CAP_DSHOW: "DirectShow",
                    cv2.CAP_V4L2: "V4L2",
                    cv2.CAP_GSTREAMER: "GStreamer"
                }.get(backend, "Inconnu")
                
                print(f"[USB CAMERA] Tentative d'ouverture de la caméra {self.camera_id} avec backend {backend_name}...")
                self.camera = cv2.VideoCapture(self.camera_id, backend)
                
                if not self.camera.isOpened():
                    print(f"[USB CAMERA] Backend {backend_name} : impossible d'ouvrir la caméra {self.camera_id}")
                    if self.camera:
                        self.camera.release()
                    continue
                
                # Tester et configurer la meilleure résolution disponible
                resolutions_to_test = [
                    (1920, 1080, "Full HD"),  # Full HD
                    (1280, 720, "HD"),        # HD
                    (640, 480, "VGA")         # VGA (fallback)
                ]
                
                best_resolution = None
                for test_width, test_height, res_name in resolutions_to_test:
                    # Configurer la résolution
                    self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, test_width)
                    self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, test_height)
                    self.camera.set(cv2.CAP_PROP_FPS, 25)  # Essayer 30 FPS
                    
                    # Vérifier la résolution réellement configurée
                    actual_width = int(self.camera.get(cv2.CAP_PROP_FRAME_WIDTH))
                    actual_height = int(self.camera.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    actual_fps = self.camera.get(cv2.CAP_PROP_FPS)
                    
                    # Tester si on peut lire une frame à cette résolution
                    ret, frame = self.camera.read()
                    if ret and frame is not None and frame.shape[1] >= test_width * 0.9 and frame.shape[0] >= test_height * 0.9:
                        best_resolution = (actual_width, actual_height, actual_fps, res_name)
                        print(f"[USB CAMERA] Résolution {res_name} ({actual_width}x{actual_height}@{actual_fps:.1f}fps) configurée avec succès")
                        break
                    else:
                        print(f"[USB CAMERA] Résolution {res_name} ({test_width}x{test_height}) non supportée")
                
                if not best_resolution:
                    print(f"[USB CAMERA] Backend {backend_name} : aucune résolution fonctionnelle trouvée")
                    self.camera.release()
                    continue
                
                # Vérification finale avec une deuxième lecture
                ret, frame = self.camera.read()
                if not ret or frame is None:
                    print(f"[USB CAMERA] Backend {backend_name} : la caméra {self.camera_id} ne retourne pas d'image de manière stable")
                    self.camera.release()
                    continue
                
                # Succès !
                self.is_running = True
                self.thread = threading.Thread(target=self._capture_loop)
                self.thread.daemon = True
                self.thread.start()
                print(f"[USB CAMERA] Caméra {self.camera_id} démarrée avec succès via backend {backend_name}")
                return True
                
            except Exception as e:
                print(f"[USB CAMERA] Erreur avec backend {backend_name}: {e}")
                if self.camera:
                    self.camera.release()
                continue
        
        # Aucun backend n'a fonctionné
        self.error = f"Impossible d'ouvrir la caméra {self.camera_id} avec tous les backends testés"
        print(f"[USB CAMERA] Erreur: {self.error}")
        return False
    
    def _reconnect(self):
        """Tenter de reconnecter la caméra"""
        print(f"[USB CAMERA] Tentative de reconnexion de la caméra {self.camera_id}...")
        if self.camera:
            self.camera.release()
        self.camera = None
        time.sleep(1)  # Attendre un peu avant de réessayer
        return self._initialize_camera()
    
    def _capture_loop(self):
        """Boucle de capture des frames"""
        consecutive_errors = 0
        max_errors = 10  # Nombre maximum d'erreurs consécutives avant de tenter une reconnexion
        
        while self.is_running:
            try:
                if not self.camera or not self.camera.isOpened():
                    # Tentative de reconnexion si la caméra est déconnectée
                    print(f"[USB CAMERA] Caméra {self.camera_id} déconnectée, tentative de reconnexion...")
                    self._reconnect()
                    time.sleep(1)  # Attendre avant de réessayer
                    continue
                    
                ret, frame = self.camera.read()
                if ret:
                    # Convertir en JPEG pour le streaming MJPEG
                    _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    with self.lock:
                        self.frame = jpeg.tobytes()
                    consecutive_errors = 0  # Réinitialiser le compteur d'erreurs
                else:
                    consecutive_errors += 1
                    print(f"[USB CAMERA] Erreur de lecture de frame (tentative {consecutive_errors}/{max_errors})")
                    if consecutive_errors >= max_errors:
                        print(f"[USB CAMERA] Trop d'erreurs consécutives, tentative de reconnexion...")
                        self._reconnect()
                        consecutive_errors = 0
                        
                time.sleep(0.03)  # ~30 FPS
            except Exception as e:
                consecutive_errors += 1
                print(f"[USB CAMERA] Erreur de capture: {e} (tentative {consecutive_errors}/{max_errors})")
                if consecutive_errors >= max_errors:
                    print(f"[USB CAMERA] Trop d'erreurs consécutives, tentative de reconnexion...")
                    self._reconnect()
                    consecutive_errors = 0
                time.sleep(0.1)
    
    def get_frame(self):
        """Récupérer la frame actuelle"""
        with self.lock:
            return self.frame
    
    def stop(self):
        """Arrêter la caméra"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        if self.camera:
            self.camera.release()
        print(f"[USB CAMERA] Caméra {self.camera_id} arrêtée")

# Variables globales
config = load_config()
current_photo = None
camera_active = False
camera_process = None
usb_camera = None

@app.route('/')
def index():
    """Page principale avec aperçu vidéo"""
    return render_template('index.html', timer=config['timer_seconds'])

# Variable globale pour stocker la dernière frame MJPEG
last_frame = None
frame_lock = threading.Lock()

@app.route('/capture', methods=['POST'])
def capture_photo():
    """Capturer la frame MJPEG actuelle directement depuis le flux vidéo"""
    global current_photo, last_frame
    
    try:
        # Générer un nom de fichier unique
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'photo_{timestamp}.jpg'
        filepath = os.path.join(PHOTOS_FOLDER, filename)
        
        # Capturer la frame actuelle du flux MJPEG
        with frame_lock:
            if last_frame is not None:
                # Sauvegarder la frame directement
                with open(filepath, 'wb') as f:
                    f.write(last_frame)
                
                current_photo = filename
                print(f"Frame MJPEG capturée avec succès: {filename}")
                
                # Envoyer sur Telegram si activé
                send_type = config.get('telegram_send_type', 'photos')
                if send_type in ['photos', 'both']:
                    threading.Thread(target=send_to_telegram, args=(filepath, "photo")).start()
                
                return jsonify({'success': True, 'filename': filename})
            else:
                print("Aucune frame disponible dans le flux")
                return jsonify({'success': False, 'error': 'Aucune frame disponible'})
            
    except Exception as e:
        print(f"Erreur lors de la capture: {e}")
        return jsonify({'success': False, 'error': f'Erreur de capture: {str(e)}'})

@app.route('/review')
def review_photo():
    """Page de révision de la photo"""
    if not current_photo:
        return redirect(url_for('index'))
    return render_template('review.html', photo=current_photo, config=config)

@app.route('/print_photo', methods=['POST'])
def print_photo():
    """Imprimer la photo actuelle"""
    global current_photo
    
    if not current_photo:
        return jsonify({'success': False, 'error': 'Aucune photo à imprimer'})
    
    try:
        # Vérifier si l'imprimante est activée
        if not config.get('printer_enabled', True):
            return jsonify({'success': False, 'error': 'Imprimante désactivée dans la configuration'})
        
        # Chercher la photo dans le bon dossier
        photo_path = None
        if os.path.exists(os.path.join(PHOTOS_FOLDER, current_photo)):
            photo_path = os.path.join(PHOTOS_FOLDER, current_photo)
        elif os.path.exists(os.path.join(EFFECT_FOLDER, current_photo)):
            photo_path = os.path.join(EFFECT_FOLDER, current_photo)
        else:
            return jsonify({'success': False, 'error': 'Photo introuvable'})
        
        # Vérifier l'existence du script d'impression
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ScriptPythonPOS.py')
        if not os.path.exists(script_path):
            return jsonify({'success': False, 'error': 'Script d\'impression introuvable (ScriptPythonPOS.py)'})
        
        # Construire la commande d'impression avec les nouveaux paramètres
        cmd = ['python3', 'ScriptPythonPOS.py', '--image', photo_path]
        
        # Ajouter les paramètres de port et baudrate
        printer_port = config.get('printer_port', '/dev/ttyAMA0')
        printer_baudrate = config.get('printer_baudrate', 9600)
        cmd.extend(['--port', printer_port, '--baudrate', str(printer_baudrate)])
        
        # Ajouter le texte de pied de page si configuré
        footer_text = config.get('footer_text', '')
        if footer_text:
            cmd.extend(['--text', footer_text])
        
        # Ajouter l'option haute résolution selon la configuration
        print_resolution = config.get('print_resolution', 384)
        if print_resolution > 384:
            cmd.append('--hd')
        
        # Exécuter l'impression
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
        
        if result.returncode == 0:
            return jsonify({'success': True, 'message': 'Photo imprimée avec succès!'})
        elif result.returncode == 2:
            # Code d'erreur spécifique pour manque de papier
            return jsonify({'success': False, 'error': 'Plus de papier dans l\'imprimante', 'error_type': 'no_paper'})
        else:
            error_msg = result.stderr.strip() if result.stderr else 'Erreur inconnue'
            if 'ModuleNotFoundError' in error_msg and 'escpos' in error_msg:
                return jsonify({'success': False, 'error': 'Module escpos manquant. Installez-le avec: pip install python-escpos'})
            else:
                return jsonify({'success': False, 'error': f'Erreur d\'impression: {error_msg}'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/delete_current', methods=['POST'])
def delete_current_photo():
    """Supprimer la photo actuelle (depuis photos ou effet)"""
    global current_photo
    
    if current_photo:
        try:
            # Chercher la photo dans le bon dossier
            photo_path = None
            if os.path.exists(os.path.join(PHOTOS_FOLDER, current_photo)):
                photo_path = os.path.join(PHOTOS_FOLDER, current_photo)
            elif os.path.exists(os.path.join(EFFECT_FOLDER, current_photo)):
                photo_path = os.path.join(EFFECT_FOLDER, current_photo)
            
            if photo_path and os.path.exists(photo_path):
                os.remove(photo_path)
                current_photo = None
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': 'Photo introuvable'})
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({'success': False, 'error': 'Aucune photo à supprimer'})

@app.route('/apply_effect', methods=['POST'])
def apply_effect():
    """Appliquer un effet IA à la photo actuelle"""
    global current_photo
    
    if not current_photo:
        return jsonify({'success': False, 'error': 'Aucune photo à traiter'})
    
    if not config.get('effect_enabled', False):
        return jsonify({'success': False, 'error': 'Les effets sont désactivés'})
    
    if not config.get('runware_api_key'):
        return jsonify({'success': False, 'error': 'Clé API Runware manquante'})
    
    try:
        # Chemin de la photo actuelle
        photo_path = os.path.join(PHOTOS_FOLDER, current_photo)
        
        if not os.path.exists(photo_path):
            return jsonify({'success': False, 'error': 'Photo introuvable'})
        
        # Exécuter la fonction asynchrone
        result = asyncio.run(apply_effect_async(photo_path))
        return result
            
    except Exception as e:
        print(f"Erreur lors de l'application de l'effet: {e}")
        return jsonify({'success': False, 'error': f'Erreur IA: {str(e)}'})

async def apply_effect_async(photo_path):
    """Fonction asynchrone pour appliquer l'effet IA"""
    global current_photo
    
    try:
        print("[DEBUG IA] Début de l'application de l'effet IA")
        print(f"[DEBUG IA] Photo source: {photo_path}")
        print(f"[DEBUG IA] Clé API configurée: {'Oui' if config.get('runware_api_key') else 'Non'}")
        print(f"[DEBUG IA] Prompt: {config.get('effect_prompt', 'Transform this photo into a beautiful ghibli style')}")
        
        # Initialiser Runware
        print("[DEBUG IA] Initialisation de Runware...")
        runware = Runware(api_key=config['runware_api_key'])
        print("[DEBUG IA] Connexion à Runware...")
        await runware.connect()
        print("[DEBUG IA] Connexion établie avec succès")
        
        # Lire et encoder l'image en base64
        print("[DEBUG IA] Lecture et encodage de l'image...")
        with open(photo_path, 'rb') as img_file:
            img_data = img_file.read()
            img_base64 = base64.b64encode(img_data).decode('utf-8')
        print(f"[DEBUG IA] Image encodée: {len(img_base64)} caractères base64")
        
        # Préparer la requête d'inférence avec referenceImages (requis pour ce modèle)
        print("[DEBUG IA] Préparation de la requête d'inférence avec referenceImages...")
        request = IImageInference(
            positivePrompt=config.get('effect_prompt', 'Transforme cette image en illustration de style Studio Ghibli'),
            referenceImages=[f"data:image/jpeg;base64,{img_base64}"],
            model="runware:106@1",
            height=752,
            width=1392,
            steps=config.get('effect_steps', 5),
            CFGScale=2.5,
            numberResults=1
        )
        print("[DEBUG IA] Requête préparée avec les paramètres de base:")
        print(f"[DEBUG IA]   - Modèle: runware:106@1")
        print(f"[DEBUG IA]   - Dimensions: 1392x752")
        print(f"[DEBUG IA]   - Étapes: {config.get('effect_steps', 5)}")
        print(f"[DEBUG IA]   - CFG Scale: 2.5")
        print(f"[DEBUG IA]   - Nombre de résultats: 1")
        
        # Appliquer l'effet
        print("[DEBUG IA] Envoi de la requête à l'API Runware...")
        # La méthode correcte est imageInference
        images = await runware.imageInference(requestImage=request)
        print(f"[DEBUG IA] Réponse reçue: {len(images) if images else 0} image(s) générée(s)")
        
        if images and len(images) > 0:
            # Télécharger l'image transformée
            print(f"[DEBUG IA] URL de l'image générée: {images[0].imageURL}")
            print("[DEBUG IA] Téléchargement de l'image transformée...")
            import requests
            response = requests.get(images[0].imageURL)
            print(f"[DEBUG IA] Statut de téléchargement: {response.status_code}")
            
            if response.status_code == 200:
                print(f"[DEBUG IA] Taille de l'image téléchargée: {len(response.content)} bytes")
                
                # S'assurer que le dossier effet existe
                print(f"[DEBUG IA] Vérification du dossier effet: {EFFECT_FOLDER}")
                os.makedirs(EFFECT_FOLDER, exist_ok=True)
                print(f"[DEBUG IA] Dossier effet existe: {os.path.exists(EFFECT_FOLDER)}")
                
                # Créer un nouveau nom de fichier pour l'image avec effet
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                effect_filename = f'effect_{timestamp}.jpg'
                effect_path = os.path.join(EFFECT_FOLDER, effect_filename)
                print(f"[DEBUG IA] Sauvegarde vers: {effect_path}")
                
                # Sauvegarder l'image avec effet
                with open(effect_path, 'wb') as f:
                    f.write(response.content)
                print("[DEBUG IA] Image sauvegardée avec succès")
                
                # Mettre à jour la photo actuelle
                current_photo = effect_filename
                print(f"[DEBUG IA] Photo actuelle mise à jour: {current_photo}")
                print("[DEBUG IA] Effet appliqué avec succès!")
                
                # Envoyer sur Telegram si activé
                send_type = config.get('telegram_send_type', 'photos')
                if send_type in ['effet', 'both']:
                    threading.Thread(target=send_to_telegram, args=(effect_path, "effet")).start()
                
                return jsonify({
                    'success': True, 
                    'message': 'Effet appliqué avec succès!',
                    'new_filename': effect_filename
                })
            else:
                print(f"[DEBUG IA] ERREUR: Échec du téléchargement (code {response.status_code})")
                return jsonify({'success': False, 'error': 'Erreur lors du téléchargement de l\'image transformée'})
        else:
            print("[DEBUG IA] ERREUR: Aucune image générée par l'IA")
            return jsonify({'success': False, 'error': 'Aucune image générée par l\'IA'})
            
    except Exception as e:
        print(f"Erreur lors de l'application de l'effet: {e}")
        return jsonify({'success': False, 'error': f'Erreur IA: {str(e)}'})

@app.route('/admin')
def admin():
    # Vérifier si le dossier photos existe
    if not os.path.exists(PHOTOS_FOLDER):
        os.makedirs(PHOTOS_FOLDER)
    
    # Vérifier si le dossier effet existe
    if not os.path.exists(EFFECT_FOLDER):
        os.makedirs(EFFECT_FOLDER)
    
    # Récupérer la liste des photos avec leurs métadonnées
    photos = []
    
    # Récupérer les photos du dossier PHOTOS_FOLDER
    if os.path.exists(PHOTOS_FOLDER):
        for filename in os.listdir(PHOTOS_FOLDER):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                file_path = os.path.join(PHOTOS_FOLDER, filename)
                file_size_kb = os.path.getsize(file_path) / 1024  # Taille en KB
                file_date = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                photos.append({
                    'filename': filename,
                    'size_kb': file_size_kb,
                    'date': file_date.strftime("%d/%m/%Y %H:%M"),
                    'type': 'photo',
                    'folder': PHOTOS_FOLDER
                })
    
    # Récupérer les photos du dossier EFFECT_FOLDER
    if os.path.exists(EFFECT_FOLDER):
        for filename in os.listdir(EFFECT_FOLDER):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                file_path = os.path.join(EFFECT_FOLDER, filename)
                file_size_kb = os.path.getsize(file_path) / 1024  # Taille en KB
                file_date = datetime.fromtimestamp(os.path.getmtime(file_path))
                
                photos.append({
                    'filename': filename,
                    'size_kb': file_size_kb,
                    'date': file_date.strftime("%d/%m/%Y %H:%M"),
                    'type': 'effet',
                    'folder': EFFECT_FOLDER
                })
    
    # Trier les photos par date (plus récentes en premier)
    photos.sort(key=lambda x: datetime.strptime(x['date'], "%d/%m/%Y %H:%M"), reverse=True)
    
    # Compter les photos de chaque type
    photo_count = sum(1 for p in photos if p['type'] == 'photo')
    effect_count = sum(1 for p in photos if p['type'] == 'effet')
    
    # Détecter les caméras USB disponibles
    available_cameras = detect_cameras()
    
    # Détecter les ports série disponibles
    available_serial_ports = detect_serial_ports()
    
    # Charger la configuration
    config = load_config()
    
    return render_template('admin.html', 
                           config=config, 
                           photos=photos,
                           photo_count=photo_count,
                           effect_count=effect_count,
                           available_cameras=available_cameras,
                           available_serial_ports=available_serial_ports,
                           show_toast=request.args.get('show_toast', False))

@app.route('/admin/save', methods=['POST'])
def save_admin_config():
    """Sauvegarder la configuration admin"""
    global config
    
    try:
        config['footer_text'] = request.form.get('footer_text', '')
        
        # Gestion sécurisée des champs numériques
        timer_seconds = request.form.get('timer_seconds', '3').strip()
        config['timer_seconds'] = int(timer_seconds) if timer_seconds else 3
        
        config['high_density'] = 'high_density' in request.form
        config['slideshow_enabled'] = 'slideshow_enabled' in request.form
        
        slideshow_delay = request.form.get('slideshow_delay', '60').strip()
        config['slideshow_delay'] = int(slideshow_delay) if slideshow_delay else 60
        
        config['slideshow_source'] = request.form.get('slideshow_source', 'photos')
        config['effect_enabled'] = 'effect_enabled' in request.form
        config['effect_prompt'] = request.form.get('effect_prompt', '')
        
        effect_steps = request.form.get('effect_steps', '5').strip()
        config['effect_steps'] = int(effect_steps) if effect_steps else 5
        
        config['runware_api_key'] = request.form.get('runware_api_key', '')
        config['telegram_enabled'] = 'telegram_enabled' in request.form
        config['telegram_bot_token'] = request.form.get('telegram_bot_token', '')
        config['telegram_chat_id'] = request.form.get('telegram_chat_id', '')
        config['telegram_send_type'] = request.form.get('telegram_send_type', 'photos')
        
        # Configuration de la caméra
        config['camera_type'] = request.form.get('camera_type', 'picamera')
        
        # Récupérer l'ID de la caméra USB sélectionnée
        selected_camera = request.form.get('usb_camera_select', '0')
        # L'ID est stocké comme premier caractère de la valeur
        try:
            config['usb_camera_id'] = int(selected_camera)
        except ValueError:
            config['usb_camera_id'] = 0
        
        # Configuration de l'imprimante
        config['printer_enabled'] = 'printer_enabled' in request.form
        config['printer_port'] = request.form.get('printer_port', '/dev/ttyUSB0')
        
        printer_baudrate = request.form.get('printer_baudrate', '9600').strip()
        try:
            config['printer_baudrate'] = int(printer_baudrate)
        except ValueError:
            config['printer_baudrate'] = 9600
        
        print_resolution = request.form.get('print_resolution', '384').strip()
        try:
            config['print_resolution'] = int(print_resolution)
        except ValueError:
            config['print_resolution'] = 384
        
        save_config(config)
        flash('Configuration sauvegardée avec succès!', 'success')
        
    except Exception as e:
        flash(f'Erreur lors de la sauvegarde: {str(e)}', 'error')
    
    return redirect(url_for('admin'))

@app.route('/admin/delete_photos', methods=['POST'])
def delete_all_photos():
    """Supprimer toutes les photos (normales et avec effet)"""
    try:
        deleted_count = 0
        
        # Supprimer les photos normales
        if os.path.exists(PHOTOS_FOLDER):
            for filename in os.listdir(PHOTOS_FOLDER):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    os.remove(os.path.join(PHOTOS_FOLDER, filename))
                    deleted_count += 1
        
        # Supprimer les photos avec effet
        if os.path.exists(EFFECT_FOLDER):
            for filename in os.listdir(EFFECT_FOLDER):
                if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                    os.remove(os.path.join(EFFECT_FOLDER, filename))
                    deleted_count += 1
        
        flash(f'{deleted_count} photo(s) supprimée(s) avec succès!', 'success')
    except Exception as e:
        flash(f'Erreur lors de la suppression: {str(e)}', 'error')
    
    return redirect(url_for('admin'))

@app.route('/admin/download_photo/<filename>')
def download_photo(filename):
    """Télécharger une photo spécifique"""
    try:
        # Chercher la photo dans les deux dossiers
        if os.path.exists(os.path.join(PHOTOS_FOLDER, filename)):
            return send_from_directory(PHOTOS_FOLDER, filename, as_attachment=True)
        elif os.path.exists(os.path.join(EFFECT_FOLDER, filename)):
            return send_from_directory(EFFECT_FOLDER, filename, as_attachment=True)
        else:
            flash('Photo introuvable', 'error')
            return redirect(url_for('admin'))
    except Exception as e:
        flash(f'Erreur lors du téléchargement: {str(e)}', 'error')
        return redirect(url_for('admin'))

@app.route('/admin/reprint_photo/<filename>', methods=['POST'])
def reprint_photo(filename):
    """Réimprimer une photo spécifique"""
    try:
        # Chercher la photo dans les deux dossiers
        photo_path = None
        if os.path.exists(os.path.join(PHOTOS_FOLDER, filename)):
            photo_path = os.path.join(PHOTOS_FOLDER, filename)
        elif os.path.exists(os.path.join(EFFECT_FOLDER, filename)):
            photo_path = os.path.join(EFFECT_FOLDER, filename)
        
        if photo_path:
            # Vérifier si le script d'impression existe
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ScriptPythonPOS.py')
            if not os.path.exists(script_path):
                flash('Script d\'impression introuvable (ScriptPythonPOS.py)', 'error')
                return redirect(url_for('admin'))
            
            # Utiliser le script d'impression existant
            import subprocess
            cmd = [
                'python3', 'ScriptPythonPOS.py',
                '--image', photo_path
            ]
            
            # Ajouter le texte de pied de page si défini
            footer_text = config.get('footer_text', '')
            if footer_text:
                cmd.extend(['--text', footer_text])
            
            # Ajouter l'option HD si la résolution est élevée
            print_resolution = config.get('print_resolution', 384)
            if print_resolution > 384:
                cmd.append('--hd')
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
            
            if result.returncode == 0:
                flash('Photo réimprimée avec succès!', 'success')
            else:
                error_msg = result.stderr.strip() if result.stderr else 'Erreur inconnue'
                if 'ModuleNotFoundError' in error_msg and 'escpos' in error_msg:
                    flash('Module escpos manquant. Installez-le avec: pip install python-escpos', 'error')
                else:
                    flash(f'Erreur d\'impression: {error_msg}', 'error')
        else:
            flash('Photo introuvable', 'error')
    except Exception as e:
        flash(f'Erreur lors de la réimpression: {str(e)}', 'error')
    
    return redirect(url_for('admin'))

@app.route('/api/slideshow')
def get_slideshow_data():
    """API pour récupérer les données du diaporama"""
    photos = []
    
    # Déterminer le dossier source selon la configuration
    source_folder = EFFECT_FOLDER if config.get('slideshow_source', 'photos') == 'effet' else PHOTOS_FOLDER
    
    if os.path.exists(source_folder):
        for filename in os.listdir(source_folder):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                photos.append(filename)
    
    photos.sort(reverse=True)  # Plus récentes en premier
    
    return jsonify({
        'enabled': config.get('slideshow_enabled', False),
        'delay': config.get('slideshow_delay', 60),
        'source': config.get('slideshow_source', 'photos'),
        'photos': photos
    })

@app.route('/api/printer_status')
def get_printer_status():
    """API pour vérifier l'état de l'imprimante"""
    return jsonify(check_printer_status())

@app.route('/photos/<filename>')
def serve_photo(filename):
    """Servir les photos"""
    # Vérifier d'abord dans le dossier photos
    if os.path.exists(os.path.join(PHOTOS_FOLDER, filename)):
        return send_from_directory(PHOTOS_FOLDER, filename)
    # Sinon vérifier dans le dossier effet
    elif os.path.exists(os.path.join(EFFECT_FOLDER, filename)):
        return send_from_directory(EFFECT_FOLDER, filename)
    else:
        abort(404)

@app.route('/video_stream')
def video_stream():
    """Flux vidéo MJPEG en temps réel"""
    return Response(generate_video_stream(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

def generate_video_stream():
    """Générer le flux vidéo MJPEG selon le type de caméra configuré"""
    global camera_process, usb_camera, last_frame
    
    # Déterminer le type de caméra à utiliser
    camera_type = config.get('camera_type', 'picamera')
    
    try:
        # Arrêter tout processus caméra existant
        stop_camera_process()
        
        # Utiliser la caméra USB si configurée
        if camera_type == 'usb':
            print("[CAMERA] Démarrage de la caméra USB...")
            camera_id = config.get('usb_camera_id', 0)
            usb_camera = UsbCamera(camera_id=camera_id)
            if not usb_camera.start():
                raise Exception(f"Impossible de démarrer la caméra USB avec ID {camera_id}")
            
            # Générateur de frames pour la caméra USB
            while True:
                frame = usb_camera.get_frame()
                if frame:
                    # Stocker la frame pour capture instantanée
                    with frame_lock:
                        last_frame = frame
                    
                    # Envoyer la frame au navigateur
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n'
                           b'Content-Length: ' + str(len(frame)).encode() + b'\r\n\r\n' +
                           frame + b'\r\n')
                else:
                    time.sleep(0.03)  # Attendre si pas de frame disponible
        
        # Utiliser la Pi Camera par défaut
        else:
            print("[CAMERA] Démarrage de la Pi Camera...")
            # Commande libcamera-vid pour flux MJPEG - résolution 16/9
            cmd = [
                'libcamera-vid',
                '--codec', 'mjpeg',
                '--width', '1280',   # Résolution native plus compatible
                '--height', '720',   # Vrai 16/9 sans bandes noires
                '--framerate', '15', # Framerate plus élevé pour cette résolution
                '--timeout', '0',    # Durée infinie
                '--output', '-',     # Sortie vers stdout
                '--inline',          # Headers inline
                '--flush',           # Flush immédiat
                '--nopreview'        # Pas d'aperçu local
            ]
            
            camera_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            
            # Buffer pour assembler les frames JPEG
            buffer = b''
            
            while camera_process and camera_process.poll() is None:
                try:
                    # Lire les données par petits blocs
                    chunk = camera_process.stdout.read(1024)
                    if not chunk:
                        break
                        
                    buffer += chunk
                    
                    # Chercher les marqueurs JPEG
                    while True:
                        # Chercher le début d'une frame JPEG (0xFFD8)
                        start = buffer.find(b'\xff\xd8')
                        if start == -1:
                            break
                            
                        # Chercher la fin de la frame JPEG (0xFFD9)
                        end = buffer.find(b'\xff\xd9', start + 2)
                        if end == -1:
                            break
                            
                        # Extraire la frame complète
                        jpeg_frame = buffer[start:end + 2]
                        buffer = buffer[end + 2:]
                        
                        # Stocker la frame pour capture instantanée
                        with frame_lock:
                            last_frame = jpeg_frame
                        
                        # Envoyer la frame au navigateur
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n'
                               b'Content-Length: ' + str(len(jpeg_frame)).encode() + b'\r\n\r\n' +
                               jpeg_frame + b'\r\n')
                               
                except Exception as e:
                    print(f"[CAMERA] Erreur lecture flux: {e}")
                    break
                
    except Exception as e:
        print(f"Erreur flux vidéo: {e}")
        # Envoyer une frame d'erreur
        error_msg = f"Erreur caméra: {str(e)}"
        yield (b'--frame\r\n'
               b'Content-Type: text/plain\r\n\r\n' +
               error_msg.encode() + b'\r\n')
    finally:
        stop_camera_process()

def stop_camera_process():
    """Arrêter proprement le processus caméra (Pi Camera ou USB)"""
    global camera_process, usb_camera
    
    # Arrêter la caméra USB si active
    if usb_camera:
        try:
            usb_camera.stop()
        except Exception as e:
            print(f"[CAMERA] Erreur lors de l'arrêt de la caméra USB: {e}")
        usb_camera = None
    
    # Arrêter le processus libcamera-vid si actif
    if camera_process:
        try:
            camera_process.terminate()
            camera_process.wait(timeout=2)
        except:
            try:
                camera_process.kill()
            except:
                pass
        camera_process = None

@app.route('/start_camera')
def start_camera():
    """Démarrer l'aperçu caméra"""
    global camera_active
    camera_active = True
    return jsonify({'status': 'camera_started'})

@app.route('/stop_camera')
def stop_camera():
    """Arrêter l'aperçu caméra"""
    global camera_active
    camera_active = False
    stop_camera_process()
    return jsonify({'status': 'camera_stopped'})

# Nettoyer les processus à la fermeture
@atexit.register
def cleanup():
    print("[APP] Arrêt de l'application, nettoyage des ressources...")
    stop_camera_process()

def signal_handler(sig, frame):
    stop_camera_process()
    exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

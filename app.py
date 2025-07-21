import json
from flask import Flask, Response,url_for,abort,redirect,send_from_directory,render_template,jsonify,request,flash
import cv2
from runware import Runware, IImageInference
import os
import subprocess
import logging
import asyncio
import threading
import atexit
import base64
import sys
from datetime import datetime
from telegram_utils import send_to_telegram
from config_utils import (
    PHOTOS_FOLDER,
    EFFECT_FOLDER,
    load_config,
    save_config,
    verif_seting,
    load_email,
    save_email)
from email_utils import envoyer_email_avec_images

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'photobooth_secret_key_2024')

verif_seting()
config = load_config()
emails = load_email()
camera = cv2.VideoCapture(config["num_came"])

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def generate_frames():
    global camera
     # 0 est généralement l'index de la caméra par défaut
    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            ret, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

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
        printer_port = config.get('printer_port', '/dev/ttyAMA0')
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
            available_ports = [('/dev/ttyAMA0', '/dev/ttyAMA0'), ('/dev/ttyS0', '/dev/ttyS0')]

    return available_ports

@app.route('/')
def index():
    return render_template('index.html',timer=config["timer_seconds"])

@app.route('/SendEmail')
def SendEmail():
    global emails
    return render_template('SendEmail.html',emails=emails)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/capture', methods=['POST'])
def capture_photo():
    global camera
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S%f')
    filename = f'photo_{timestamp}.jpg'
    filepath = os.path.join(PHOTOS_FOLDER, filename)
    success, frame = camera.read()
    if not success:
        logger.info("Aucune frame disponible dans le flux")
        return jsonify({'success': False, 'error': 'Aucune frame disponible'})
    else:
        cv2.imwrite(filepath, frame)
        logger.info(f"Frame MJPEG capturée avec succès: {filename}")
        return jsonify({'success': True, 'filename': filename})

@app.route('/review', methods=['GET'])
def review_photo():
    filename = request.args.get("filename")
    if filename == None:
        return redirect(url_for('index'))
    else:
        return render_template('review.html', photo=filename, config=config)

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

@app.route('/print_photo', methods=['POST', 'GET'])
def print_photo():
    """Imprimer la photo actuelle"""
    current_photo = request.args.get("filename")
    if current_photo == None:
        return jsonify({'success': False, 'error': "le nom de l'image na pas été resu."})
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
                return jsonify(
                    {'success': False, 'error': 'Module escpos manquant. Installez-le avec: pip install python-escpos'})
            else:
                return jsonify({'success': False, 'error': f'Erreur d\'impression: {error_msg}'})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/delete_current', methods=['POST'])
def delete_current_photo():
    """Supprimer la photo actuelle (depuis photos ou effet)"""
    current_photo = request.args.get("filename")
    if current_photo != None:
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

@app.route('/apply_effect', methods=['POST','GET'])
def apply_effect():
    """Appliquer un effet IA à la photo actuelle"""
    current_photo = request.args.get("filename")
    if current_photo == None:
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
        logger.info(f"Erreur lors de l'application de l'effet: {e}")
        return jsonify({'success': False, 'error': f'Erreur IA: {str(e)}'})

async def apply_effect_async(photo_path):
    """Fonction asynchrone pour appliquer l'effet IA"""
    try:
        logger.info("[DEBUG IA] Début de l'application de l'effet IA")
        logger.info(f"[DEBUG IA] Photo source: {photo_path}")
        logger.info(f"[DEBUG IA] Clé API configurée: {'Oui' if config.get('runware_api_key') else 'Non'}")
        logger.info(
            f"[DEBUG IA] Prompt: {config.get('effect_prompt', 'Transform this photo into a beautiful ghibli style')}")

        # Initialiser Runware
        logger.info("[DEBUG IA] Initialisation de Runware...")
        runware = Runware(api_key=config['runware_api_key'])
        logger.info("[DEBUG IA] Connexion à Runware...")
        await runware.connect()
        logger.info("[DEBUG IA] Connexion établie avec succès")

        # Lire et encoder l'image en base64
        logger.info("[DEBUG IA] Lecture et encodage de l'image...")
        with open(photo_path, 'rb') as img_file:
            img_data = img_file.read()
            img_base64 = base64.b64encode(img_data).decode('utf-8')
        logger.info(f"[DEBUG IA] Image encodée: {len(img_base64)} caractères base64")

        # Préparer la requête d'inférence avec referenceImages (requis pour ce modèle)
        logger.info("[DEBUG IA] Préparation de la requête d'inférence avec referenceImages...")
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
        logger.info("[DEBUG IA] Requête préparée avec les paramètres de base:")
        logger.info(f"[DEBUG IA]   - Modèle: runware:106@1")
        logger.info(f"[DEBUG IA]   - Dimensions: 1392x752")
        logger.info(f"[DEBUG IA]   - Étapes: {config.get('effect_steps', 5)}")
        logger.info(f"[DEBUG IA]   - CFG Scale: 2.5")
        logger.info(f"[DEBUG IA]   - Nombre de résultats: 1")

        # Appliquer l'effet
        logger.info("[DEBUG IA] Envoi de la requête à l'API Runware...")
        # La méthode correcte est imageInference
        images = await runware.imageInference(requestImage=request)
        logger.info(f"[DEBUG IA] Réponse reçue: {len(images) if images else 0} image(s) générée(s)")

        if images and len(images) > 0:
            # Télécharger l'image transformée
            logger.info(f"[DEBUG IA] URL de l'image générée: {images[0].imageURL}")
            logger.info("[DEBUG IA] Téléchargement de l'image transformée...")
            import requests
            response = requests.get(images[0].imageURL)
            logger.info(f"[DEBUG IA] Statut de téléchargement: {response.status_code}")

            if response.status_code == 200:
                logger.info(f"[DEBUG IA] Taille de l'image téléchargée: {len(response.content)} bytes")

                # S'assurer que le dossier effet existe
                logger.info(f"[DEBUG IA] Vérification du dossier effet: {EFFECT_FOLDER}")
                os.makedirs(EFFECT_FOLDER, exist_ok=True)
                logger.info(f"[DEBUG IA] Dossier effet existe: {os.path.exists(EFFECT_FOLDER)}")

                # Créer un nouveau nom de fichier pour l'image avec effet
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                effect_filename = f'effect_{timestamp}.jpg'
                effect_path = os.path.join(EFFECT_FOLDER, effect_filename)
                logger.info(f"[DEBUG IA] Sauvegarde vers: {effect_path}")

                # Sauvegarder l'image avec effet
                with open(effect_path, 'wb') as f:
                    f.write(response.content)
                logger.info("[DEBUG IA] Image sauvegardée avec succès")

                # Mettre à jour la photo actuelle
                current_photo = effect_filename
                logger.info(f"[DEBUG IA] Photo actuelle mise à jour: {current_photo}")
                logger.info("[DEBUG IA] Effet appliqué avec succès!")

                # Envoyer sur Telegram si activé
                send_type = config.get('telegram_send_type', 'photos')
                if send_type in ['effet', 'both']:
                    threading.Thread(target=send_to_telegram, args=(effect_path, config, "effet")).start()

                return jsonify({
                    'success': True,
                    'message': 'Effet appliqué avec succès!',
                    'new_filename': effect_filename
                })
            else:
                logger.info(f"[DEBUG IA] ERREUR: Échec du téléchargement (code {response.status_code})")
                return jsonify({'success': False, 'error': 'Erreur lors du téléchargement de l\'image transformée'})
        else:
            logger.info("[DEBUG IA] ERREUR: Aucune image générée par l'IA")
            return jsonify({'success': False, 'error': 'Aucune image générée par l\'IA'})

    except Exception as e:
        logger.info(f"Erreur lors de l'application de l'effet: {e}")
        return jsonify({'success': False, 'error': f'Erreur IA: {str(e)}'})

@app.route('/send_email', methods=['GET'])
def send_email():
    """Appliquer un effet IA à la photo actuelle"""
    current_photo = request.args.get("filenames")
    destinataires = request.args.get("desti")
    if current_photo == 'null' or current_photo == '[]' or current_photo == None:
        return jsonify({'success': False, 'error': 'Aucune photo à traiter'})

    if not config.get('email_enabled', False):
        return jsonify({'success': False, 'error': 'Les email sont désactivés'})
    if destinataires == '[]':
        return jsonify({'success': False, 'error': 'Aucune destinataire'})
    try:
        destinataires = json.loads(destinataires)
        modi= False
        for destinataire in destinataires:
            if destinataire not in emails:
                modi = True
                emails.append(destinataire)
        if modi:
            save_email(emails)
        images = json.loads(current_photo)
        # Chemin de la photo actuelle
        chemins_images = []
        for image in images:
            photo_path = os.path.join(PHOTOS_FOLDER, image)

            if not os.path.exists(photo_path):
                return jsonify({'success': False, 'error': 'Photo introuvable'})
            chemins_images.append(photo_path)


        re = envoyer_email_avec_images(config,destinataires,chemins_images)

        return jsonify(re)

    except Exception as e:
        logger.info(f"Erreur lors de l'application de l'effet: {e}")
        return jsonify({'success': False, 'error': f'Erreur IA: {str(e)}'})

@app.route('/admin')
def admin():
    global config,camera
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



    # Charger la configuration
    camera.release()
    nombe_cam = 0
    while 1:
        ddd = cv2.VideoCapture(nombe_cam)
        if not ddd.isOpened():
            break
        else:
            nombe_cam+=1
            ddd.release()
    ddd.release()
    if nombe_cam == 0:
        nombe_cam = 1
    camera = cv2.VideoCapture(config["num_came"])

    available_serial_ports = detect_serial_ports()
    return render_template('admin.html',
                           config=config,
                           photos=photos,
                           photo_count=photo_count,
                           effect_count=effect_count,
                           nomber_cam =nombe_cam,
                           CAMERA_USE=config["num_came"],
                           available_serial_ports=available_serial_ports,
                           show_toast=request.args.get('show_toast', False))

@app.route('/admin/save', methods=['POST'])
def save_admin_config():
    """Sauvegarder la configuration admin"""
    global config,camera

    CAMERA_USE = (request.form.get("select_camera",''))
    if CAMERA_USE != None:
        if CAMERA_USE != config["num_came"]:
            camera.release()
            camera = cv2.VideoCapture(config["num_came"])
            config["num_came"] = int(CAMERA_USE)
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

        # Configuration du email

        if request.form.get('email_enabled', '') == "on":
            config['email_enabled'] = True
        else:
            config['email_enabled'] = False
        config['email'] = request.form.get('email_Address', '')
        config['password_email'] = request.form.get('password_email', '')
        config['sujet_email'] = request.form.get('sujet_email', '')
        config['corps_email'] = request.form.get('corps_email', '')


        # Configuration de l'imprimante
        config['printer_enabled'] = 'printer_enabled' in request.form
        config['printer_port'] = request.form.get('printer_port', '/dev/ttyAMA0')

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

@atexit.register
def cleanup():
    global camera
    logger.info("[APP] Arrêt de l'application, nettoyage des ressources...")
    camera.release()

def signal_handler(sig, frame):
    global camera
    camera.release()
    exit(0)

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)

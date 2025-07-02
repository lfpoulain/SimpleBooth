#!/usr/bin/env python3
# coding: utf-8

"""
Script simple et efficace pour imprimante thermique 57mm
- Support PNG, JPG, JPEG
- Optimisé pour vitesse (basse densité) par défaut
- Option haute densité avec --hd
- Ajout de texte sous l'image avec --text
- Vérification automatique du papier

Usage:
  python3 script.py --image photo.jpg
  python3 script.py --image photo.jpg --hd
  python3 script.py --image photo.jpg --text "Mon texte en bas"
  python3 script.py --image logo.png --text "Entreprise XYZ" --hd

Installation: pip install python-escpos Pillow
"""

import warnings
import logging
import sys
import argparse
import os
# Supprimer TOUS les avertissements et messages
warnings.filterwarnings("ignore")
logging.getLogger().setLevel(logging.CRITICAL)

from escpos.printer import Serial
from PIL import Image, ImageEnhance

def parse_arguments():
    """Parser les arguments de ligne de commande"""
    parser = argparse.ArgumentParser(description='Impression thermique rapide')
    parser.add_argument('--hd', action='store_true', 
                       help='Haute densité (meilleure qualité, plus lent)')
    parser.add_argument('--image', type=str, required=True,
                       help='Chemin vers l\'image à imprimer (obligatoire)')
    parser.add_argument('--text', type=str,
                       help='Texte à ajouter sous l\'image')
    parser.add_argument('--port', type=str, default='/dev/ttyAMA0',
                       help='Port série de l\'imprimante (défaut: /dev/ttyAMA0)')
    parser.add_argument('--baudrate', type=int, default=9600,
                       help='Baudrate de l\'imprimante (défaut: 9600)')
    return parser.parse_args()

def connect_printer(serial_port='/dev/ttyAMA0', baudrate=9600):
    """Connexion à l'imprimante avec paramètres de vitesse"""
    printer = Serial(devfile=serial_port, baudrate=baudrate, timeout=1)
    
    # Commandes ESC/POS pour optimiser la vitesse
    try:
        # ESC 7 - Paramètres d'impression (heating dots, heat time, heat interval)
        printer.device.write(b'\x1b\x37')  # ESC 7
        printer.device.write(bytes([7]))    # Heating dots réduits
        printer.device.write(bytes([40]))   # Heat time réduit
        printer.device.write(bytes([1]))    # Heat interval réduit
        
        # DC2 # - Densité d'impression (plus léger = plus rapide)
        printer.device.write(b'\x12\x23')  # DC2 #
        printer.device.write(bytes([0x88]))  # Densité réduite
        
        # ESC 3 - Espacement des lignes réduit
        printer.device.write(b'\x1b\x33')  # ESC 3
        printer.device.write(bytes([24]))   # Espacement réduit
        
    except:
        pass  # Continuer même si les commandes échouent
    
    return printer

def check_paper_status(printer):
    """Vérifier le statut du papier selon les codes de votre imprimante"""
    try:
        if hasattr(printer, 'paper_status'):
            status = printer.paper_status()
            
            if status == 0:
                return False, "Plus de papier (status: 0)"
            elif status == 2:
                return True, "Papier présent (status: 2)"
            else:
                return None, f"Status inconnu: {status}"
        else:
            return None, "Méthode paper_status non disponible"
            
    except Exception as e:
        return None, f"Erreur vérification papier: {e}"

def optimize_image(img_path, high_density=False):
    """Optimiser l'image avec compensation pour la haute densité"""
    # Charger et convertir en gris
    img = Image.open(img_path).convert('L')
    original_width, original_height = img.size
    
    # Largeur maximale selon la densité
    if high_density:
        max_width = 384  # Haute densité = largeur complète
        height_compensation = 1.0  # Compensation ajustée pour l'écrasement en HD
    else:
        max_width = 192  # Basse densité = largeur réduite
        height_compensation = 1.0  # Pas de compensation en basse densité
    
    # Redimensionner SEULEMENT si l'image est plus large que la limite
    if original_width > max_width:
        # Calculer le ratio pour préserver les proportions
        ratio = max_width / original_width
        new_height = int(original_height * ratio * height_compensation)
        img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
    elif high_density:
        # Même si l'image est plus petite, appliquer la compensation en HD
        new_height = int(original_height * height_compensation)
        img = img.resize((original_width, new_height), Image.Resampling.LANCZOS)
    
    # Contraste selon la densité
    enhancer = ImageEnhance.Contrast(img)
    if high_density:
        img = enhancer.enhance(1.5)  # Haute densité = plus de contraste
    else:
        img = enhancer.enhance(1.2)  # Basse densité = moins de contraste
    
    return img

def print_image(printer, img, filename, high_density=False):
    """Imprimer avec densité configurable"""
    printer.image(
        img,
        impl='bitImageRaster',
        high_density_vertical=high_density,
        high_density_horizontal=high_density,
        fragment_height=1920
    )

def print_text_bottom(printer, text):
    """Imprimer du texte en bas, pleine largeur"""
    if not text:
        return
    
    # Petit saut de ligne après l'image
    printer.text("\n")
    
    # Texte centré et en gras pour plus de visibilité
    printer.set(align='center')
    printer.set(bold=True)
    
    # Imprimer le texte
    printer.text(text)
    
    # Remettre les paramètres par défaut
    printer.set(align='left')
    printer.set(bold=False)

def print_with_paper_check(printer, optimized_img, filename, high_density, bottom_text):
    """Imprimer avec vérification préalable du papier"""
    
    # Vérifier le papier avant d'imprimer
    paper_ok, paper_msg = check_paper_status(printer)
    
    if paper_ok is False:
        print(f"⚠️  ATTENTION: {paper_msg}")
        print("Veuillez recharger le papier avant d'imprimer.")
        return False
    elif paper_ok is None:
        print(f"⚠️  {paper_msg}")
        print("Impression sans vérification du papier...")
    else:
        print(f"✅ {paper_msg}")
    
    # Procéder à l'impression
    print_image(printer, optimized_img, filename, high_density)
    print_text_bottom(printer, bottom_text)
    printer.text("\n\n\n\n")  # 4 retours pour plus d'espace
    
    return True

def main():
    # Parser les arguments
    args = parse_arguments()
    
    # Vérifier que l'image existe
    image_file = args.image
    if not os.path.exists(image_file):
        print(f"Erreur: Image '{image_file}' non trouvée")
        return
    
    # Mode densité et texte
    high_density = args.hd
    bottom_text = args.text
    
    # Paramètres de connexion
    printer_port = args.port
    printer_baudrate = args.baudrate
    
    # Connexion et impression
    try:
        printer = connect_printer(printer_port, printer_baudrate)
        
        # Traitement de l'image
        optimized_img = optimize_image(image_file, high_density)
        
        # Impression avec vérification du papier
        success = print_with_paper_check(printer, optimized_img, 
                                       os.path.basename(image_file), 
                                       high_density, bottom_text)
        
        if success:
            print("✅ Impression terminée")
            sys.exit(0)  # Succès
        else:
            print("❌ Impression annulée - Plus de papier")
            sys.exit(2)  # Code d'erreur spécifique pour manque de papier
        
    except Exception as e:
        print(f"Erreur: {e}")
    finally:
        try:
            printer.close()
        except:
            pass

if __name__ == '__main__':
    main()
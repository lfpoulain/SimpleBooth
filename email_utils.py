from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
import smtplib, ssl
import logging
logger = logging.getLogger(__name__)
def envoyer_email_avec_images(config,destinataires, chemins_images):
    # Créer le message
    logger.info(f"[email] envoi des email a'{destinataires}' des photo {chemins_images}")
    message = MIMEMultipart()
    message['From'] = config["email"]
    message['To'] = ', '.join(destinataires)  # Joindre les destinataires
    message['Subject'] = config["sujet_email"]

    # Attacher le corps du message
    message.attach(MIMEText(config["corps_email"], 'plain'))

    # Attacher chaque image
    try:
        for chemin_image in chemins_images:
            with open(chemin_image, 'rb') as fichier:
                image = MIMEImage(fichier.read(), name=chemin_image.split('/')[-1])
            message.attach(image)
    except Exception as e:
        print(f"Erreur lors du l'envoi des image: {e}")
        logger.info(f"[email] Erreur lors du l'envoi des image: {e}")
        return {'success': False}

    # Connexion au serveur SMTP et envoi de l'email
    port = 587  # For starttls
    context = ssl.create_default_context()
    with smtplib.SMTP(config["smtp_server"], port) as server:
        server.ehlo()  # Can be omitted
        server.starttls(context=context)
        server.ehlo()  # Can be omitted
        server.login(config["email"], config["password_email"])
        server.sendmail(config["email"], destinataires, message.as_string())

    logger.info(f"[email] envoi email envois success.")
    return {'success': True}

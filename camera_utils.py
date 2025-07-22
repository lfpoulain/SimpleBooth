import cv2

import logging

logger = logging.getLogger(__name__)


def detect_cameras():
    """Detect available USB cameras."""
    available_cameras = {}
    logger.info("[CAMERA] Début de la détection des caméras USB...")

    for i in range(10):
        try:
            logger.info(f"[CAMERA] Test de la caméra ID {i}...")
            backends = [cv2.CAP_ANY, cv2.CAP_DSHOW, cv2.CAP_V4L2, cv2.CAP_GSTREAMER]
            cap = None
            for backend in backends:
                try:
                    cap = cv2.VideoCapture(i, backend)
                    if cap.isOpened():
                        resolutions_to_test = [
                            (1920, 1080),
                            (1280, 720),
                            (640, 480)
                        ]
                        best_resolution = None
                        best_fps = 0
                        for test_width, test_height in resolutions_to_test:
                            cap.set(cv2.CAP_PROP_FRAME_WIDTH, test_width)
                            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, test_height)
                            cap.set(cv2.CAP_PROP_FPS, 30)
                            actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                            actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                            actual_fps = cap.get(cv2.CAP_PROP_FPS)
                            ret, frame = cap.read()
                            if ret and frame is not None and frame.shape[1] >= test_width * 0.9 and frame.shape[0] >= test_height * 0.9:
                                best_resolution = (actual_width, actual_height)
                                best_fps = actual_fps
                                logger.info(f"[CAMERA] Résolution {actual_width}x{actual_height} supportée pour la caméra {i}")
                                break
                            else:
                                logger.info(f"[CAMERA] Résolution {test_width}x{test_height} non supportée pour la caméra {i}")
                        if best_resolution:
                            width, height = best_resolution
                            fps = best_fps
                            backend_name = {
                                cv2.CAP_ANY: "Auto",
                                cv2.CAP_DSHOW: "DirectShow",
                                cv2.CAP_V4L2: "V4L2",
                                cv2.CAP_GSTREAMER: "GStreamer",
                            }.get(backend, "Inconnu")
                            name = f"Caméra {i} ({backend_name}) - {width}x{height}@{fps:.1f}fps"
                            available_cameras[i]= (width, height,best_fps, backend)
                            logger.info(f"[CAMERA] ✓ Caméra fonctionnelle détectée: {name}")
                            break
                        else:
                            logger.info(f"[CAMERA] Caméra {i} ouverte mais ne peut pas lire de frame avec backend {backend_name}")
                    cap.release()
                except Exception as e:
                    if cap:
                        cap.release()
                    logger.info(f"[CAMERA] Backend {backend} échoué pour caméra {i}: {e}")
                    continue
            if not available_cameras or available_cameras[-1][0] != i:
                logger.info(f"[CAMERA] ✗ Caméra {i} non disponible ou non fonctionnelle")
        except Exception as e:
            logger.info(f"[CAMERA] Erreur générale lors de la détection de la caméra {i}: {e}")
    logger.info(f"[CAMERA] Détection terminée. {len(available_cameras)} caméra(s) fonctionnelle(s) trouvée(s)")
    return available_cameras

class Camera:
    def __init__(self, camera_id=0):
        self.camera_id =camera_id
        if camera_id == "pi":
            from picamera2 import Picamera2
            self.camera = Picamera2()
            self.camera.configure(self.camera.create_preview_configuration(main={"size": (1280, 720)}))
            self.camera.preview_configuration.main.format = "RGB888"
            self.camera.preview_configuration.align()
            self.camera.configure("preview")
            self.camera.start()
            self.tpye_came = "pi"
        else:
            self.camera_id = camera_id
            self.tpye_came = "usb"
            scas = detect_cameras()
            self.camera = cv2.VideoCapture(camera_id, scas[camera_id][3])
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, scas[camera_id][0])
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, scas[camera_id][1])
            self.camera.set(cv2.CAP_PROP_FPS, scas[camera_id][2])
            if self.camera.isOpened():
                print("is open")
            else:
                print("is not open")

    def read(self):
        if self.tpye_came == "pi":
            return self.camera.capture_array()
        else:
            return self.camera.read()


import cv2
import numpy as np
import time
import os

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.clock import Clock
from kivy.graphics.texture import Texture
from kivy.utils import platform

# =========================================================================
# four_point_transform vendored from imutils (no p4a recipe exists)
# Source: https://github.com/jrosebr1/imutils (MIT licence)
# =========================================================================
def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def four_point_transform(image, pts):
    rect = order_points(pts)
    (tl, tr, br, bl) = rect

    widthA = np.linalg.norm(br - bl)
    widthB = np.linalg.norm(tr - tl)
    maxWidth = max(int(widthA), int(widthB))

    heightA = np.linalg.norm(tr - br)
    heightB = np.linalg.norm(tl - bl)
    maxHeight = max(int(heightA), int(heightB))

    dst = np.array([
        [0, 0],
        [maxWidth - 1, 0],
        [maxWidth - 1, maxHeight - 1],
        [0, maxHeight - 1]], dtype="float32")

    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
    return warped


# =========================================================================
# Helper: convert a Kivy Texture to a numpy (BGR) array for OpenCV
# =========================================================================
def texture_to_numpy(texture):
    """Read pixels from a Kivy Texture and return an OpenCV-compatible BGR array."""
    w, h = texture.size
    buf = texture.pixels          # raw RGBA bytes
    arr = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 4)
    arr = np.flipud(arr)          # Kivy stores pixels bottom-up
    bgr = cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    return bgr


class DocumentScannerApp(App):

    def build(self):
        # =====================================================================
        # REQUEST ANDROID RUNTIME PERMISSIONS
        # Must be done before any camera or storage access.
        # =====================================================================
        if platform == 'android':
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([
                    Permission.CAMERA,
                    Permission.READ_EXTERNAL_STORAGE,
                    Permission.WRITE_EXTERNAL_STORAGE,
                ])
            except Exception as e:
                print(f"Permission request error: {e}")

        # ----- Root layout ---------------------------------------------------
        self.layout = BoxLayout(orientation='vertical')

        # ----- Status label (shows "Document detected" / "Align document") ---
        self.status_label = Label(
            text='Align document in frame',
            size_hint=(1, 0.06),
            font_size='16sp',
            color=(1, 1, 1, 1)
        )
        self.layout.add_widget(self.status_label)

        # ----- Live preview (we draw the overlay onto a plain Image widget) --
        self.preview = Image(allow_stretch=True, keep_ratio=True)
        self.layout.add_widget(self.preview)

        # ----- Save button ---------------------------------------------------
        self.save_btn = Button(
            text='Save Document',
            size_hint=(1, 0.12),
            font_size='20sp'
        )
        self.save_btn.bind(on_press=self.trigger_save)
        self.layout.add_widget(self.save_btn)

        # =====================================================================
        # KIVY CAMERA — the only reliable way to get camera frames on Android.
        # We keep the Camera widget OFF-SCREEN (size 1×1, opacity 0) purely as
        # a frame source; our own Image widget is the visible preview.
        # =====================================================================
        from kivy.uix.camera import Camera as KivyCamera
        self.cam = KivyCamera(
            index=0,
            resolution=(1280, 720),
            play=True,
            size=(1, 1),
            opacity=0
        )
        # Add off-screen so Kivy actually initialises the camera
        self.layout.add_widget(self.cam)

        self.save_flag = False
        self.document_contour = None

        # Poll at ~20 fps — enough for smooth preview without draining battery
        Clock.schedule_interval(self.update_frame, 1.0 / 20.0)

        return self.layout

    # -------------------------------------------------------------------------

    def trigger_save(self, instance):
        self.save_flag = True

    # -------------------------------------------------------------------------

    def update_frame(self, dt):
        # Guard: camera texture not ready yet
        if self.cam.texture is None:
            return

        # Convert Kivy texture → OpenCV BGR array
        frame = texture_to_numpy(self.cam.texture)
        if frame is None or frame.size == 0:
            return

        frame_copy = frame.copy()
        height, width = frame.shape[:2]

        # ----- Document-edge detection ---------------------------------------
        # Default contour = full frame (safe fallback)
        default_contour = np.array([
            [0, 0], [width, 0], [width, height], [0, height]
        ])
        self.document_contour = default_contour

        gray = cv2.cvtColor(frame_copy, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        _, threshold = cv2.threshold(
            blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )
        contours, _ = cv2.findContours(
            threshold, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE
        )
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        doc_found = False
        max_area = 0
        for contour in contours:
            area = cv2.contourArea(contour)
            if area > 1000:
                peri = cv2.arcLength(contour, True)
                approx = cv2.approxPolyDP(contour, 0.015 * peri, True)
                if len(approx) == 4 and area > max_area:
                    self.document_contour = approx
                    max_area = area
                    doc_found = True

        # Update status label
        self.status_label.text = (
            'Document detected — tap Save' if doc_found else 'Align document in frame'
        )

        # Draw contour overlay onto a display copy
        display = frame.copy()
        color = (0, 255, 0) if doc_found else (0, 165, 255)
        cv2.drawContours(display, [self.document_contour], -1, color, 3)

        # ----- Save on button press -----------------------------------------
        if self.save_flag:
            self.save_flag = False
            self._save_document(frame_copy)

        # ----- Push frame to Kivy preview ------------------------------------
        # Flip vertically because Kivy expects bottom-up row order
        flipped = cv2.flip(display, 0)
        buf = flipped.tobytes()
        texture = Texture.create(
            size=(flipped.shape[1], flipped.shape[0]),
            colorfmt='bgr'
        )
        texture.blit_buffer(buf, colorfmt='bgr', bufferfmt='ubyte')
        self.preview.texture = texture

    # -------------------------------------------------------------------------

    def _save_document(self, frame_copy):
        height, width = frame_copy.shape[:2]
        try:
            warped = four_point_transform(
                frame_copy,
                self.document_contour.reshape(4, 2)
            )

            # Rotate if landscape
            if warped.shape[1] > warped.shape[0]:
                warped = cv2.rotate(warped, cv2.ROTATE_90_CLOCKWISE)

            # Resize to calibrated output dimensions
            TARGET_WIDTH = 678
            TARGET_HEIGHT = 960
            grid_ready = cv2.resize(
                warped, (TARGET_WIDTH, TARGET_HEIGHT),
                interpolation=cv2.INTER_CUBIC
            )

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            save_path = self._get_save_path()
            os.makedirs(save_path, exist_ok=True)
            filename = os.path.join(save_path, f"scanned_{timestamp}.png")

            success = cv2.imwrite(filename, grid_ready)
            if success:
                self.status_label.text = f"Saved: scanned_{timestamp}.png"
                print(f"Saved to {filename}")
            else:
                self.status_label.text = "Save failed — check storage permission"
                print("cv2.imwrite returned False")

        except Exception as e:
            self.status_label.text = "Save error — see logcat"
            print(f"Save error: {e}")

    # -------------------------------------------------------------------------

    def _get_save_path(self):
        """
        Return the best available save directory.

        Android 10+ (API 29) enforces scoped storage — /sdcard/DCIM is no
        longer writable by third-party apps without the legacy
        requestLegacyExternalStorage flag.  We first try the app's own
        external-files directory (always writable, survives uninstall in
        Pictures), then fall back to the app's internal user_data_dir.
        """
        if platform == 'android':
            try:
                # pyjnius path — gives e.g. /sdcard/Android/data/<pkg>/files
                from jnius import autoclass
                Environment = autoclass('android.os.Environment')
                context = autoclass(
                    'org.kivy.android.PythonActivity'
                ).mActivity
                ext_dir = context.getExternalFilesDir(
                    Environment.DIRECTORY_PICTURES
                )
                if ext_dir is not None:
                    return str(ext_dir.getAbsolutePath())
            except Exception as e:
                print(f"pyjnius path failed, using fallback: {e}")
            # Fallback: app-private internal storage
            return self.user_data_dir

        # Desktop / development
        return os.path.expanduser("~/Documents/ScannedDocs")

    # -------------------------------------------------------------------------

    def on_stop(self):
        self.cam.play = False


if __name__ == '__main__':
    DocumentScannerApp().run()

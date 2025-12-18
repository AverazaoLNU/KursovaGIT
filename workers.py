import librosa
from PyQt6.QtCore import QThread, pyqtSignal

class AudioLoaderThread(QThread):
    finished_loading = pyqtSignal(object, float, object)
    error_occurred = pyqtSignal(str)

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            y, sr = librosa.load(self.path, sr=None)
            duration = len(y) / sr
            self.finished_loading.emit(y, sr, duration)
        except Exception as e:
            self.error_occurred.emit(str(e))
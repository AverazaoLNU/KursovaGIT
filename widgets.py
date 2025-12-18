import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent, QCursor
from PyQt6.QtWidgets import QApplication
from config import THEME

class TimeAxisItem(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):
        strings = []
        for v in values:
            v = max(0, v)
            minutes = int(v // 60)
            seconds = int(v % 60)
            if spacing < 1:
                milliseconds = int((v * 1000) % 1000)
                strings.append(f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}")
            else:
                strings.append(f"{minutes:02d}:{seconds:02d}")
        return strings

class CustomPlotWidget(pg.PlotWidget):
    sig_clicked = pyqtSignal(float)
    sig_saved_clicked = pyqtSignal(object)

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent, **kwargs)
        self.selection_item = None
        self.zoom_preview_item = None 
        
        self.mode = 'select' 
        self.is_selecting = False
        self.is_panning = False
        self.is_zooming = False 
        
        self.pan_start_x = 0
        self.start_pos = 0
        
        self.plotItem.setMouseEnabled(x=True, y=False)
        self.plotItem.setMenuEnabled(False)

        self.zoom_preview_item = pg.LinearRegionItem(values=(0, 0), brush=pg.mkBrush(THEME['zoom_selection']), movable=False)
        self.zoom_preview_item.setZValue(100) 
        self.zoom_preview_item.hide()
        self.addItem(self.zoom_preview_item)

    def set_mode(self, mode):
        self.mode = mode
        if mode == 'pan':
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        elif mode == 'zoom':
            self.setCursor(Qt.CursorShape.CrossCursor)
        else: 
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self.mode == 'select':
            pos_in_scene = self.mapToScene(event.position().toPoint())
            items = self.scene().items(pos_in_scene)
            for item in items:
                if isinstance(item, pg.LinearRegionItem) and getattr(item, 'is_saved', False):
                    self.sig_saved_clicked.emit(item)
                    event.accept()
                    return

        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode == 'select':
                self.is_selecting = True
                point = self.plotItem.vb.mapSceneToView(event.position())
                self.start_pos = point.x()
                self.sig_clicked.emit(self.start_pos)
                if self.selection_item:
                    self.selection_item.setRegion([self.start_pos, self.start_pos])
                event.accept()

            elif self.mode == 'pan':
                self.is_panning = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                self.pan_start_x = event.globalPosition().x()
                event.accept()
            
            elif self.mode == 'zoom':
                self.is_zooming = True
                point = self.plotItem.vb.mapSceneToView(event.position())
                self.start_pos = point.x()
                self.zoom_preview_item.setRegion([self.start_pos, self.start_pos])
                self.zoom_preview_item.show()
                event.accept()

        elif event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.pan_start_x = event.globalPosition().x()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        point = self.plotItem.vb.mapSceneToView(event.position())
        current_pos = point.x()

        if self.is_selecting and self.mode == 'select':
            if self.selection_item:
                self.selection_item.setRegion([self.start_pos, current_pos])
            event.accept()

        elif self.is_zooming and self.mode == 'zoom':
            self.zoom_preview_item.setRegion([self.start_pos, current_pos])
            event.accept()

        elif self.is_panning:
            current_x_pixel = event.globalPosition().x()
            delta_px = current_x_pixel - self.pan_start_x
            
            view_box = self.plotItem.vb
            view_range = view_box.viewRange()[0]
            screen_width_px = self.viewport().width()
            
            if screen_width_px > 0:
                view_width_units = view_range[1] - view_range[0]
                units_per_px = view_width_units / screen_width_px
                dx_units = -delta_px * units_per_px
                view_box.translateBy(x=dx_units, y=0)

            self.pan_start_x = current_x_pixel
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode == 'select':
                self.is_selecting = False
                event.accept()
            elif self.mode == 'pan':
                self.is_panning = False
                self.setCursor(Qt.CursorShape.OpenHandCursor)
                event.accept()
            elif self.mode == 'zoom':
                self.is_zooming = False
                self.zoom_preview_item.hide()
                point = self.plotItem.vb.mapSceneToView(event.position())
                end_pos = point.x()
                x_min, x_max = sorted([self.start_pos, end_pos])
                width = x_max - x_min
                if width < 0.001:
                    event.accept()
                    return

                modifiers = QApplication.keyboardModifiers()
                is_shift = (modifiers & Qt.KeyboardModifier.ShiftModifier)

                if is_shift:
                    current_range = self.plotItem.vb.viewRange()[0]
                    current_width = current_range[1] - current_range[0]
                    factor = current_width / width
                    new_width = current_width * factor
                    center = (x_min + x_max) / 2
                    new_x_min = center - new_width / 2
                    new_x_max = center + new_width / 2
                    self.setXRange(new_x_min, new_x_max, padding=0)
                else:
                    self.setXRange(x_min, x_max, padding=0)
                event.accept()
        
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.is_panning = False
            if self.mode == 'pan':
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif self.mode == 'zoom':
                self.setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)
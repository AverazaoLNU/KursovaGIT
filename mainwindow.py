import os
import json
import time
import numpy as np
import sounddevice as sd
import pyqtgraph as pg
from PyQt6 import QtWidgets, QtCore, QtGui
from config import THEME
from workers import AudioLoaderThread
from widgets import CustomPlotWidget, TimeAxisItem

class AudioLabeler(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio Labeler")
        self.resize(1200, 800)
        
        app_icon = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(app_icon)

        self.audio_path = None
        self.y = None
        self.sr = None
        self.duration = 0
        self.annotations = [] 
        self.region_items = []
        self.loader_thread = None
        self.is_playing = False
        self.play_start_time = 0
        self.play_offset = 0
        
        self.play_timer = QtCore.QTimer()
        self.play_timer.setInterval(33) 
        self.play_timer.timeout.connect(self.update_cursor_animation)

        self.init_style()
        self.init_ui()
        self.init_shortcuts()

    def init_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {THEME['bg']}; color: {THEME['fg']}; }}
            QWidget {{ background-color: {THEME['bg']}; color: {THEME['fg']}; font-family: 'Segoe UI'; }}
            QPushButton {{ 
                background-color: {THEME['btn_bg']}; 
                border: none; 
                padding: 6px 12px; 
                color: white; 
                border-radius: 4px; 
                text-align: left; 
            }}
            QPushButton:hover {{ background-color: {THEME['btn_hover']}; }}
            QComboBox {{ 
                background-color: {THEME['btn_bg']}; 
                color: white; 
                border: 1px solid #444; 
                padding: 4px; 
                border-radius: 4px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background-color: {THEME['list_bg']};
                color: white;
                selection-background-color: #0078d7;
            }}
            QDoubleSpinBox {{
                background-color: {THEME['btn_bg']};
                color: white;
                border: 1px solid #444;
                padding: 4px;
                border-radius: 4px;
            }}
            QListWidget {{ background-color: {THEME['list_bg']}; border: 1px solid #444; font-family: 'Consolas'; }}
            QListWidget::item:selected {{ background-color: #0078d7; }}
            QProgressBar {{ border: 1px solid #444; text-align: center; min-width: 200px; color: white; }}
            QProgressBar::chunk {{ background-color: #007acc; }}
            QLabel {{ color: {THEME['fg']}; }}
        """)

    def init_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)

        icon_open = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogOpenButton)
        icon_save = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogSaveButton)
        icon_play = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPlay)
        icon_pause = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaPause)
        icon_stop = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MediaStop)
        icon_add = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_DialogApplyButton)
        icon_load = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileIcon)

        tools = QtWidgets.QHBoxLayout()
        
        btn_open = QtWidgets.QPushButton(" OPEN AUDIO")
        btn_open.setIcon(icon_open)
        btn_open.clicked.connect(self.load_audio_start)
        
        btn_save = QtWidgets.QPushButton(" SAVE (Ctrl+S)")
        btn_save.setIcon(icon_save)
        btn_save.clicked.connect(self.save_annotations)
        
        btn_load_json = QtWidgets.QPushButton(" LOAD JSON")
        btn_load_json.setIcon(icon_load)
        btn_load_json.clicked.connect(self.load_annotations_from_file)

        tools.addWidget(btn_open)
        tools.addWidget(btn_load_json)
        tools.addWidget(btn_save)
        
        tools.addSpacing(20)
        tools.addWidget(QtWidgets.QLabel("Speed:"))
        
        self.spin_speed = QtWidgets.QDoubleSpinBox()
        self.spin_speed.setRange(0.1, 2.0)
        self.spin_speed.setSingleStep(0.1)
        self.spin_speed.setValue(1.0)
        self.spin_speed.setSuffix("x")
        self.spin_speed.setFixedWidth(70)
        self.spin_speed.valueChanged.connect(self.on_speed_changed)
        
        tools.addWidget(self.spin_speed)
        tools.addStretch()

        self.combo_mode = QtWidgets.QComboBox()
        self.combo_mode.setIconSize(QtCore.QSize(20, 20)) 
        
        icon_select = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowForward)
        icon_pan = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ToolBarHorizontalExtensionButton)
        icon_zoom = self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_FileDialogContentsView)

        self.combo_mode.addItem(icon_select, " SELECT")
        self.combo_mode.addItem(icon_pan, " PAN")
        self.combo_mode.addItem(icon_zoom, " ZOOM")
        
        self.combo_mode.currentIndexChanged.connect(self.change_tool_mode)
        self.combo_mode.setFixedWidth(120)
        
        tools.addWidget(QtWidgets.QLabel("Mode:"))
        tools.addWidget(self.combo_mode)
        
        tools.addStretch()

        self.btn_play = QtWidgets.QPushButton(" PLAY (Space)")
        self.btn_play.setIcon(icon_play)
        self.btn_play.clicked.connect(self.play_selection)

        self.btn_pause = QtWidgets.QPushButton(" PAUSE")
        self.btn_pause.setIcon(icon_pause)
        self.btn_pause.clicked.connect(self.pause_audio)

        self.btn_stop = QtWidgets.QPushButton(" STOP")
        self.btn_stop.setIcon(icon_stop)
        self.btn_stop.clicked.connect(self.stop_audio)

        self.btn_add = QtWidgets.QPushButton(" LABEL (Enter)")
        self.btn_add.setIcon(icon_add)
        self.btn_add.clicked.connect(self.add_annotation_from_selection)

        icon_size = QtCore.QSize(18, 18)
        for btn in [btn_open, btn_save, btn_load_json, self.btn_play, self.btn_pause, self.btn_stop, self.btn_add]:
            btn.setIconSize(icon_size)

        tools.addWidget(self.btn_play)
        tools.addWidget(self.btn_pause)
        tools.addWidget(self.btn_stop)
        tools.addWidget(self.btn_add)
        layout.addLayout(tools)

        time_axis = TimeAxisItem(orientation='bottom')
        self.plot_widget = CustomPlotWidget(axisItems={'bottom': time_axis})
        self.plot_widget.setBackground(THEME['bg'])
        self.plot_widget.getPlotItem().hideAxis('left')
        
        axis_bottom = self.plot_widget.getPlotItem().getAxis('bottom')
        axis_bottom.setPen(pg.mkPen(THEME['fg'], width=1)) 
        axis_bottom.setTextPen(THEME['fg'])               
        axis_bottom.setStyle(tickTextOffset=8)            
        
        self.plot_widget.showGrid(x=True, y=False, alpha=0.3)
        self.plot_widget.setYRange(-1.1, 1.1)
        self.plot_widget.setXRange(0, 10) 

        self.plot_widget.sig_clicked.connect(self.on_plot_clicked)
        self.plot_widget.sig_saved_clicked.connect(self.on_saved_region_clicked)
        
        self.plot_widget.setDownsampling(ds=True, auto=True, mode='peak')
        self.plot_widget.setClipToView(True) 
        self.plot_widget.getPlotItem().hideButtons()

        self.curve = self.plot_widget.plot(pen=pg.mkPen(THEME['plot_line'], width=1))
        self.curve.setSkipFiniteCheck(True)
        self.curve.setZValue(1)

        self.cursor_line = pg.InfiniteLine(pos=0, angle=90, pen=pg.mkPen(THEME['cursor'], width=2))
        self.cursor_line.setZValue(20)
        self.plot_widget.addItem(self.cursor_line)

        marker_pen = pg.mkPen(THEME['cursor'])
        marker_brush = pg.mkBrush(THEME['cursor'])
        self.cursor_top = pg.ScatterPlotItem(size=14, symbol='o', pen=marker_pen, brush=marker_brush)
        self.cursor_top.setZValue(21)
        self.plot_widget.addItem(self.cursor_top)

        self.cursor_bottom = pg.ScatterPlotItem(size=14, symbol='o', pen=marker_pen, brush=marker_brush)
        self.cursor_bottom.setZValue(21)
        self.plot_widget.addItem(self.cursor_bottom)

        self.plot_widget.getViewBox().sigRangeChanged.connect(self.update_cursor_markers)

        self.selection_region = pg.LinearRegionItem(values=(0, 0), brush=pg.mkBrush(THEME['selection']))
        self.selection_region.setZValue(10)
        self.plot_widget.addItem(self.selection_region)
        self.plot_widget.selection_item = self.selection_region

        layout.addWidget(self.plot_widget, stretch=4)

        layout.addWidget(QtWidgets.QLabel("ANNOTATIONS:"))
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self.on_list_double_click)
        layout.addWidget(self.list_widget, stretch=1)

        self.lbl_status = QtWidgets.QLabel("Ready")
        self.progress_bar = QtWidgets.QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)
        
        self.statusBar().addWidget(self.lbl_status)
        self.statusBar().addPermanentWidget(self.progress_bar)

    def init_shortcuts(self):
        QtGui.QShortcut(QtGui.QKeySequence("Space"), self).activated.connect(self.toggle_play_pause)
        QtGui.QShortcut(QtGui.QKeySequence("Return"), self).activated.connect(self.btn_add.click)
        QtGui.QShortcut(QtGui.QKeySequence("Enter"), self).activated.connect(self.btn_add.click)
        QtGui.QShortcut(QtGui.QKeySequence("Delete"), self).activated.connect(self.delete_selected_annotation)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+S"), self).activated.connect(self.save_annotations)

    def change_tool_mode(self, index):
        modes = ['select', 'pan', 'zoom']
        mode = modes[index]
        self.plot_widget.set_mode(mode)
        self.lbl_status.setText(f"Mode changed to: {mode.upper()}")

    def on_plot_clicked(self, x_pos):
        if self.duration <= 0: return
        was_playing = self.is_playing
        self._stop_sound_only() 
        x_pos = max(0, min(self.duration, x_pos))
        self.cursor_line.setPos(x_pos)
        self.update_cursor_markers()
        if was_playing:
            self.play_selection()

    def on_saved_region_clicked(self, region_item):
        if self.duration <= 0: return
        self._stop_sound_only()
        start, end = region_item.getRegion()
        self.selection_region.setRegion([start, end])
        self.cursor_line.setPos(start)
        self.update_cursor_markers()
        self.lbl_status.setText(f"Selected Region: {start:.2f}s - {end:.2f}s")

    def update_cursor_markers(self):
        current_x = self.cursor_line.value()
        view_range = self.plot_widget.viewRange()
        y_min, y_max = view_range[1]
        self.cursor_top.setData(x=[current_x], y=[y_max])
        self.cursor_bottom.setData(x=[current_x], y=[y_min])

    def load_audio_start(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open Audio", "", "Audio (*.wav *.mp3 *.flac *.ogg)")
        if not file_path: return
        self.stop_audio()
        self.clear_all_annotations()
        self.lbl_status.setText(f"Loading {os.path.basename(file_path)}...")
        self.progress_bar.setVisible(True)
        self.setEnabled(False) 
        self.loader_thread = AudioLoaderThread(file_path)
        self.loader_thread.finished_loading.connect(self.on_audio_loaded)
        self.loader_thread.error_occurred.connect(self.on_loading_error)
        self.loader_thread.start()

    def on_audio_loaded(self, y, sr, duration):
        self.y = y 
        self.sr = sr
        self.duration = duration
        self.audio_path = self.loader_thread.path
        
        t = np.linspace(0, self.duration, len(y))
        self.curve.setData(t, y)

        self.plot_widget.setXRange(0, self.duration)
        self.plot_widget.setYRange(-1.1, 1.1)
        
        self.selection_region.setRegion([0, 0])
        self.cursor_line.setPos(0)
        self.update_cursor_markers()
        self.progress_bar.setVisible(False)
        self.setEnabled(True)
        self.lbl_status.setText(f"Loaded: {os.path.basename(self.audio_path)} ({self.format_time(self.duration)})")

    def on_loading_error(self, err_msg):
        self.progress_bar.setVisible(False)
        self.setEnabled(True)
        QtWidgets.QMessageBox.critical(self, "Error", err_msg)

    def _stop_sound_only(self):
        self.is_playing = False
        self.play_timer.stop()
        sd.stop()

    def toggle_play_pause(self):
        if self.is_playing: self.pause_audio()
        else: self.play_selection()

    def pause_audio(self):
        if self.is_playing:
            self._stop_sound_only()
            self.lbl_status.setText("Paused")

    def stop_audio(self):
        self._stop_sound_only()
        self.cursor_line.setPos(0)
        self.update_cursor_markers()
        self.selection_region.setRegion([0, 0])
        self.lbl_status.setText("Stopped (Reset)")

    def on_speed_changed(self):
        if self.is_playing:
            self.play_selection()

    def play_selection(self):
        if self.y is None: return
        self._stop_sound_only()
        sel_min, sel_max = self.selection_region.getRegion()
        has_selection = (sel_max - sel_min) > 0.05
        if has_selection:
            start_point = sel_min
            end_point = sel_max
        else:
            start_point = self.cursor_line.value()
            end_point = self.duration
        start_point = max(0, min(self.duration, start_point))
        if end_point <= start_point: end_point = self.duration
        s_idx = int(start_point * self.sr)
        e_idx = int(end_point * self.sr)
        if e_idx <= s_idx: return
        
        speed = self.spin_speed.value()
        new_sr = int(self.sr * speed)
        
        sd.play(self.y[s_idx:e_idx], new_sr)
        self.is_playing = True
        self.play_start_time = time.time()
        self.play_offset = start_point
        self.cursor_line.setPos(start_point)
        self.update_cursor_markers()
        self.play_timer.start()
        self.lbl_status.setText(f"Playing at {speed}x...")

    def update_cursor_animation(self):
        if not self.is_playing: return
        elapsed = time.time() - self.play_start_time
        
        speed = self.spin_speed.value()
        current_pos = self.play_offset + (elapsed * speed)
        
        self.cursor_line.setPos(current_pos)
        self.update_cursor_markers()
        sel_min, sel_max = self.selection_region.getRegion()
        has_selection = (sel_max - sel_min) > 0.05
        if has_selection and current_pos >= sel_max and self.play_offset < sel_max:
            self.pause_audio()
        elif current_pos >= self.duration:
            self._stop_sound_only()

    def add_annotation_from_selection(self):
        if self.y is None: return
        self.pause_audio()
        start, end = self.selection_region.getRegion()
        start, end = max(0, start), min(self.duration, end)
        if end - start < 0.05:
            self.lbl_status.setText("Selection too short!")
            return
        label, ok = QtWidgets.QInputDialog.getText(self, "New Label", "Class Name:")
        if ok and label:
            self.annotations.append({"start": start, "end": end, "label": label})
            self.add_visual_region(start, end, label)
            self.update_listbox()
            self.selection_region.setRegion([end, end])
            self.cursor_line.setPos(end)
            self.update_cursor_markers()

    def add_visual_region(self, start, end, label):
        region = pg.LinearRegionItem(values=(start, end), brush=pg.mkBrush(THEME['saved_region']), movable=False)
        text = pg.TextItem(text=label, color=THEME['fg'], anchor=(0.5, 1))
        text.setPos((start + end) / 2, 1.0)
        region.is_saved = True
        region.setZValue(5)
        text.setZValue(5)
        self.plot_widget.addItem(region)
        self.plot_widget.addItem(text)
        self.region_items.append((region, text))

    def update_listbox(self):
        self.list_widget.clear()
        for i, ann in enumerate(self.annotations):
            self.list_widget.addItem(f"{i+1:02d} | {ann['label']} | {self.format_time(ann['start'])} - {self.format_time(ann['end'])}")

    def format_time(self, seconds):
        m, s = divmod(seconds, 60)
        ms = int((seconds % 1) * 100)
        return f"{int(m):02d}:{int(s):02d}.{ms:02d}"

    def show_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item: return
        menu = QtWidgets.QMenu(self)
        menu.addAction("❌ Delete", self.delete_selected_annotation)
        menu.exec(self.list_widget.mapToGlobal(pos))

    def delete_selected_annotation(self):
        row = self.list_widget.currentRow()
        if row >= 0:
            r, t = self.region_items.pop(row)
            self.plot_widget.removeItem(r)
            self.plot_widget.removeItem(t)
            self.annotations.pop(row)
            self.update_listbox()

    def clear_all_annotations(self):
        for r, t in self.region_items:
            self.plot_widget.removeItem(r)
            self.plot_widget.removeItem(t)
        self.region_items = []
        self.annotations = []
        self.list_widget.clear()

    def save_annotations(self):
        if not self.audio_path: return
        default_name = os.path.splitext(self.audio_path)[0] + ".json"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save", default_name, "JSON (*.json)")
        if path:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({"file": os.path.basename(self.audio_path), "duration": self.duration, "annotations": self.annotations}, f, indent=4)
            self.lbl_status.setText(f"Saved to {path}")

    def load_annotations_from_file(self):
        if not self.audio_path: return self.lbl_status.setText("Load audio first!")
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load JSON", "", "JSON (*.json)")
        if path:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.clear_all_annotations()
            for ann in data.get("annotations", []):
                self.annotations.append(ann)
                self.add_visual_region(ann['start'], ann['end'], ann['label'])
            self.update_listbox()

    def on_list_double_click(self, item):
        idx = self.list_widget.row(item)
        ann = self.annotations[idx]
        margin = (ann['end'] - ann['start']) * 0.5
        self.plot_widget.setXRange(max(0, ann['start'] - margin), min(self.duration, ann['end'] + margin))
        self.cursor_line.setPos(ann['start'])
        self.update_cursor_markers()
        self.selection_region.setRegion([ann['start'], ann['end']])
        self.play_selection()
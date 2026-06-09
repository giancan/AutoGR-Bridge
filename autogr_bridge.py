# -*- coding: utf-8 -*-
from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.PyQt.QtCore import QProcess, QProcessEnvironment
from qgis.core import QgsProject, QgsRasterLayer, Qgis, QgsSettings

import os, tempfile, pathlib, time, json

PLUGIN_ORG  = "AutoGR"
PLUGIN_NAME = "AutoGR_Bridge"
PLUGIN_VERSION = "6.1"
SETTINGS_PREFIX = f"plugins/{PLUGIN_NAME}"
LOG_TAG   = "AutoGR Bridge"
ICON_PATH = str(pathlib.Path(__file__).parent.joinpath("AutoGR-Bridge.ico"))

SIFT_EXE_NAME = "01-AutoGR_SIFT.exe"

def _dist_mode():
    return not (pathlib.Path(__file__).parent / "dev_mode").exists()

DEFAULT_SUB = 1000
MAX_SUB     = 9999

DESCRIPTORS = ["SIFT", "ASIFT", "SURF", "AKAZE", "KAZE", "FAST-FREAK", "ORB", "BRISK",
               "SuperGLUE", "LoFTR", "DISK", "ALIKE-D"]

def _s(key, default=""):
    return QgsSettings().value(f"{SETTINGS_PREFIX}/{key}", default)

def _set(key, val):
    QgsSettings().setValue(f"{SETTINGS_PREFIX}/{key}", val)

def _has_world_or_proj(path_no_ext):
    exts = [".tfw", ".jgw", ".pgw", ".wld", ".prj", ".aux.xml"]
    return any(os.path.exists(path_no_ext + e) for e in exts)

def _nice_tempdir(prefix="autogr_canvas_"):
    td = pathlib.Path(tempfile.gettempdir()) / (prefix + next(tempfile._get_candidate_names()))
    td.mkdir(parents=True, exist_ok=True)
    return str(td)

def _appdata_dir():
    base = os.environ.get("APPDATA") or str(pathlib.Path.home())
    p = pathlib.Path(base) / "AutoGR-T"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)

def _log(msg, level=Qgis.Info):
    from qgis.core import QgsMessageLog
    QgsMessageLog.logMessage(str(msg), LOG_TAG, level)
    try:
        with open(os.path.join(_appdata_dir(), "autogr_bridge_qgis.log"), "a", encoding="utf-8") as f:
            f.write(str(msg).rstrip() + "\n")
    except Exception:
        pass

def _matchers_for_descriptor(desc):
    d = (desc or "").strip()
    if d in ["AKAZE", "ORB", "BRISK", "FAST-FREAK"]:
        matchers = ["BRUTEFORCE", "BRUTEFORCE_HAMMING", "BRUTEFORCE_HAMMINGLUT",
                    "BRUTEFORCE_L1", "BRUTEFORCE_SL2", "BRUTEFORCE_FL2"]
        default  = "BRUTEFORCE_SL2"
    elif d in ["KAZE", "SURF", "ASIFT", "SIFT"]:
        matchers = ["FLANNBASED", "BRUTEFORCE", "BRUTEFORCE_L1", "BRUTEFORCE_SL2"]
        default  = "FLANNBASED"
    elif d == "SuperGLUE":
        matchers = ["SINKHORN (SuperGLUE)"]; default = "SINKHORN (SuperGLUE)"
    elif d == "LoFTR":
        matchers = ["LoFTR (built-in)"];     default = "LoFTR (built-in)"
    elif d == "DISK":
        matchers = ["DISK (built-in)"];      default = "DISK (built-in)"
    elif d == "ALIKE-D":
        matchers = ["LightGlue"];            default = "LightGlue"
    else:
        matchers = ["BRUTEFORCE"];           default = "BRUTEFORCE"
    return matchers, default

def save_canvas_snapshot_georef(out_png_path):
    from qgis.utils import iface
    from qgis.core import QgsMapSettings, QgsMapRendererCustomPainterJob
    from PyQt5.QtGui import QImage, QPainter
    from PyQt5.QtCore import QSize
    canvas        = iface.mapCanvas()
    extent        = canvas.extent()
    canvas_width  = canvas.width()
    canvas_height = canvas.height()
    extent_aspect = extent.width()  / extent.height()
    canvas_aspect = canvas_width    / canvas_height
    if extent_aspect > canvas_aspect:
        width  = canvas_width;  height = int(canvas_width / extent_aspect)
    else:
        height = canvas_height; width  = int(canvas_height * extent_aspect)
    settings = QgsMapSettings()
    settings.setExtent(extent)
    settings.setOutputSize(QSize(width, height))
    settings.setLayers(canvas.layers())
    settings.setDestinationCrs(canvas.mapSettings().destinationCrs())
    settings.setBackgroundColor(canvas.canvasColor())
    img = QImage(QSize(width, height), QImage.Format_ARGB32_Premultiplied)
    img.fill(settings.backgroundColor().rgb())
    painter = QPainter(img)
    job = QgsMapRendererCustomPainterJob(settings, painter)
    job.start(); job.waitForFinished()
    painter.end()
    img.save(out_png_path, "PNG")
    pixel_x_size = extent.width()  / width
    pixel_y_size = -extent.height() / height
    upper_left_x = extent.xMinimum() + (pixel_x_size / 2.0)
    upper_left_y = extent.yMaximum() + (pixel_y_size / 2.0)
    _log(f"Pixel size: {pixel_x_size:.6f} x {abs(pixel_y_size):.6f}")
    base_no_ext, ext = os.path.splitext(out_png_path)
    wld = base_no_ext + (".pgw" if ext.lower() == ".png" else
                         ".jgw" if ext.lower() in (".jpg", ".jpeg") else ".wld")
    with open(wld, "w", encoding="ascii") as f:
        f.write(f"{pixel_x_size:.15f}\n0.000000000000000\n0.000000000000000\n"
                f"{pixel_y_size:.15f}\n{upper_left_x:.15f}\n{upper_left_y:.15f}\n")
    prj = base_no_ext + ".prj"
    try:
        crs = settings.destinationCrs()
        wkt = (crs.toWkt()    if hasattr(crs, "toWkt")    else
               crs.toWktWMS() if hasattr(crs, "toWktWMS") else crs.authid())
        with open(prj, "w", encoding="utf-8") as f:
            f.write(wkt)
    except Exception:
        pass

def baseimage_path_from_dialog(dlg):
    mode_idx = int(dlg.base_mode.currentIndex())
    if mode_idx == 0:
        lyr_id = dlg.layer_combo.currentData()
        lyr    = QgsProject.instance().mapLayer(lyr_id) if lyr_id else None
        if lyr and isinstance(lyr, QgsRasterLayer):
            return lyr.source()
        return None
    else:
        td  = _nice_tempdir()
        out = os.path.join(td, "canvas.png")
        save_canvas_snapshot_georef(out)
        return out

# ---------------------------------------------------------------------------
# Rotation preview widget
# ---------------------------------------------------------------------------
class RotationPreviewWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(72, 72)
        self._angle = 0.0
        self.setToolTip(
            "Live preview: shows how the dataset image is rotated before matching.\n"
            "Red triangle = original top edge.")

    def setAngle(self, angle):
        self._angle = float(angle)
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF
        from PyQt5.QtCore import Qt, QPointF
        p  = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h   = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        p.fillRect(0, 0, w, h, QColor(242, 242, 242))
        p.setPen(QPen(QColor(200, 200, 200), 1))
        p.drawLine(int(cx), 3, int(cx), h - 3)
        p.drawLine(3, int(cy), w - 3, int(cy))
        p.translate(cx, cy)
        p.rotate(self._angle)
        rw, rh = 22, 16
        p.setPen(QPen(QColor(60, 100, 180), 1.5))
        p.setBrush(QBrush(QColor(180, 205, 250, 210)))
        p.drawRect(-rw, -rh, rw * 2, rh * 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(QColor(210, 50, 50)))
        tri = QPolygonF([QPointF(0.0,  float(-rh - 7)),
                         QPointF(-4.0, float(-rh)),
                         QPointF(4.0,  float(-rh))])
        p.drawPolygon(tri)
        p.end()


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------
class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AutoGR Bridge v" + PLUGIN_VERSION)
        self.setWindowIcon(QtGui.QIcon(ICON_PATH))
        self.setMinimumWidth(740)

        if _dist_mode():
            self.exe_edit = QtWidgets.QLineEdit(_s("autogr_exe", ""))
            self.exe_btn  = QtWidgets.QToolButton(text="...")
            self.exe_btn.clicked.connect(self._pick_exe)
        else:
            self.python_edit = QtWidgets.QLineEdit(_s("python", "C:/Python3-8_64/python.exe"))
            self.python_btn  = QtWidgets.QToolButton(text="...")
            self.python_btn.clicked.connect(self._pick_python)
            self.tool_edit   = QtWidgets.QLineEdit(_s("tool", ""))
            self.tool_btn    = QtWidgets.QToolButton(text="...")
            self.tool_btn.clicked.connect(self._pick_tool)

        self.base_mode = QtWidgets.QComboBox()
        self.base_mode.addItems(["Raster layer in project", "Canvas snapshot"])
        self.base_mode.setCurrentIndex(int(_s("base_mode", 0)))
        self.layer_combo = QtWidgets.QComboBox()
        self._populate_raster_layers()
        saved_id = _s("layer_id", "")
        if saved_id:
            for i in range(self.layer_combo.count()):
                if self.layer_combo.itemData(i) == saved_id:
                    self.layer_combo.setCurrentIndex(i); break
        self.snapshot_note = QtWidgets.QLabel("Canvas snapshot uses current extent & CRS (georeferenced).")
        self.snapshot_note.setStyleSheet("color: #666;")
        self.snapshot_note.setVisible(self.base_mode.currentIndex() == 1)

        self.dataset_list = QtWidgets.QListWidget()
        self.dataset_list.setMinimumHeight(80)
        self.dataset_add = QtWidgets.QPushButton("Add files...")
        self.dataset_clr = QtWidgets.QPushButton("Clear")

        self._preview_label = QtWidgets.QLabel()
        self._preview_label.setFixedSize(110, 110)
        self._preview_label.setAlignment(QtCore.Qt.AlignCenter)
        self._preview_label.setStyleSheet("border: 1px solid #ccc; background: #f5f5f5; color: #999;")
        self._preview_label.setText("click image\nto preview")

        self.desc_combo = QtWidgets.QComboBox()
        self.desc_combo.addItems(DESCRIPTORS)
        self.desc_combo.setToolTip(
            "Feature detection and description algorithm.\n"
            "Deep learning methods (SuperGLUE, LoFTR, DISK, ALIKE-D) require PyTorch.")
        self.match_combo = QtWidgets.QComboBox()
        self.match_combo.setToolTip("Matching strategy - updated automatically based on the selected descriptor.")

        try:
            init_sub = int(_s("subsampling", DEFAULT_SUB))
        except Exception:
            init_sub = DEFAULT_SUB
        self.sub_spin   = QtWidgets.QSpinBox()
        self.sub_spin.setRange(1, MAX_SUB)
        self.sub_spin.setValue(init_sub)
        self.sub_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.sub_slider.setRange(1, MAX_SUB)
        self.sub_slider.setValue(self.sub_spin.value())

        try:
            init_rot = int(_s("rotation", 0))
        except Exception:
            init_rot = 0
        self.rot_spin = QtWidgets.QSpinBox()
        self.rot_spin.setRange(-359, 359)
        self.rot_spin.setWrapping(False)
        self.rot_spin.setValue(init_rot)
        self.rot_spin.setToolTip("Rotation applied to dataset images before matching.\nPositive = clockwise, negative = counter-clockwise.")
        self.rot_preview = RotationPreviewWidget()
        self.rot_preview.setAngle(init_rot)

        self.out_edit = QtWidgets.QLineEdit(_s("output", ""))
        self.out_btn  = QtWidgets.QToolButton(text="...")
        self.out_btn.clicked.connect(self._pick_output)

        self.chk_autostart = QtWidgets.QCheckBox("Autostart image processing in AutoGR-SIFT")
        self.chk_autostart.setChecked(str(_s("autostart", "false")).lower() == "true")
        self.chk_autostart.setToolTip("Launch AutoGR-SIFT and start processing immediately without waiting for user input.")
        self.chk_auto_import = QtWidgets.QCheckBox("Auto-import results into QGIS")
        self.chk_auto_import.setChecked(str(_s("auto_import", "true")).lower() != "false")
        self.chk_auto_import.setToolTip("Automatically add georeferenced output images to the QGIS project when processing finishes.")
        self.chk_debug = QtWidgets.QCheckBox("Debug logging")
        self.chk_debug.setChecked(str(_s("debug", "true")).lower() != "false")
        self.chk_debug.setToolTip("Write verbose log messages to the QGIS message log (AutoGR Bridge panel).")

        self.btn_info   = QtWidgets.QPushButton("i  Info")
        self.btn_run    = QtWidgets.QPushButton("Run")
        self.btn_cancel = QtWidgets.QPushButton("Close")
        self.btn_info.clicked.connect(self._show_info)
        self.btn_run.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        form = QtWidgets.QFormLayout()
        if _dist_mode():
            hexe = QtWidgets.QHBoxLayout()
            hexe.addWidget(self.exe_edit, 1); hexe.addWidget(self.exe_btn)
            form.addRow("AutoGR-SIFT executable:", self._wrap(hexe))
        else:
            hpy = QtWidgets.QHBoxLayout()
            hpy.addWidget(self.python_edit, 1); hpy.addWidget(self.python_btn)
            form.addRow("Python interpreter:", self._wrap(hpy))
            htool = QtWidgets.QHBoxLayout()
            htool.addWidget(self.tool_edit, 1); htool.addWidget(self.tool_btn)
            form.addRow("AutoGR tool (.py or .exe):", self._wrap(htool))

        hb = QtWidgets.QHBoxLayout()
        hb.addWidget(QtWidgets.QLabel("Base image:"))
        hb.addWidget(self.base_mode, 1)
        hb.addWidget(self.layer_combo, 2)
        form.addRow(self._wrap(hb))
        form.addRow(self.snapshot_note)

        hds_btns = QtWidgets.QHBoxLayout()
        hds_btns.addWidget(self.dataset_add)
        hds_btns.addWidget(self.dataset_clr)
        hds_btns.addStretch(1)
        vds = QtWidgets.QVBoxLayout()
        vds.setContentsMargins(0, 0, 0, 0)
        vds.addWidget(self.dataset_list, 1)
        vds.addLayout(hds_btns)
        hds_outer = QtWidgets.QHBoxLayout()
        hds_outer.setContentsMargins(0, 0, 0, 0)
        hds_outer.addLayout(vds, 1)
        hds_outer.addWidget(self._preview_label)
        form.addRow("Dataset:", self._wrap(hds_outer))

        form.addRow("Descriptor:", self.desc_combo)
        form.addRow("Matcher:",    self.match_combo)

        hsub = QtWidgets.QHBoxLayout()
        hsub.addWidget(self.sub_spin)
        hsub.addWidget(self.sub_slider, 1)
        form.addRow("Subsampling:", self._wrap(hsub))

        hrot = QtWidgets.QHBoxLayout()
        hrot.addWidget(self.rot_spin)
        hrot.addWidget(self.rot_preview)
        hrot.addStretch(1)
        form.addRow("Rotation (deg):", self._wrap(hrot))

        hout = QtWidgets.QHBoxLayout()
        hout.addWidget(self.out_edit, 1); hout.addWidget(self.out_btn)
        form.addRow("Output folder:", self._wrap(hout))

        opts = QtWidgets.QVBoxLayout()
        opts.addWidget(self.chk_autostart)
        hopts2 = QtWidgets.QHBoxLayout()
        hopts2.addWidget(self.chk_auto_import)
        hopts2.addWidget(self.chk_debug)
        hopts2.addStretch(1)
        opts.addLayout(hopts2)
        form.addRow("", self._wrap(opts))

        hbtn = QtWidgets.QHBoxLayout()
        hbtn.addStretch(1)
        hbtn.addWidget(self.btn_run)
        hbtn.addWidget(self.btn_cancel)

        hdr = QtWidgets.QHBoxLayout()
        hdr.addWidget(self.btn_info)
        hdr.addStretch(1)

        main = QtWidgets.QVBoxLayout(self)
        main.addLayout(hdr)
        main.addLayout(form)
        main.addLayout(hbtn)

        self.base_mode.currentIndexChanged.connect(
            lambda i: (_set("base_mode", i), self._on_base_mode_changed(i)))
        self.layer_combo.currentIndexChanged.connect(
            lambda _: _set("layer_id", self.layer_combo.currentData()))
        self.desc_combo.currentTextChanged.connect(self._on_desc_changed)
        self.match_combo.currentTextChanged.connect(self._on_match_changed)
        self.sub_spin.valueChanged.connect(self.sub_slider.setValue)
        self.sub_slider.valueChanged.connect(self.sub_spin.setValue)
        self.sub_spin.valueChanged.connect(lambda v: _set("subsampling", int(v)))
        self.rot_spin.valueChanged.connect(lambda v: (_set("rotation", int(v)),
                                                      self.rot_preview.setAngle(v),
                                                      self._refresh_preview()))
        if _dist_mode():
            self.exe_edit.textChanged.connect(lambda v: _set("autogr_exe", v))
        else:
            self.python_edit.textChanged.connect(lambda v: _set("python", v))
            self.tool_edit.textChanged.connect(lambda v:   _set("tool",   v))
        self.out_edit.textChanged.connect(lambda v: _set("output", v))
        self.chk_autostart.stateChanged.connect(
            lambda _: _set("autostart",   "true" if self.chk_autostart.isChecked()   else "false"))
        self.chk_auto_import.stateChanged.connect(
            lambda _: _set("auto_import", "true" if self.chk_auto_import.isChecked() else "false"))
        self.chk_debug.stateChanged.connect(
            lambda _: _set("debug",       "true" if self.chk_debug.isChecked()       else "false"))
        self.dataset_add.clicked.connect(self._pick_dataset_files)
        self.dataset_clr.clicked.connect(self._clear_dataset)
        self.dataset_list.itemClicked.connect(self._on_dataset_item_clicked)
        self.dataset_list.model().rowsInserted.connect(
            lambda *_: QtCore.QTimer.singleShot(0, self._update_subsampling_max))
        self.dataset_list.model().rowsRemoved.connect(
            lambda *_: QtCore.QTimer.singleShot(0, self._update_subsampling_max))

        saved_desc = _s("descriptor", "SIFT")
        if saved_desc not in DESCRIPTORS:
            if str(saved_desc).upper() == "SUPERGLUE":   saved_desc = "SuperGLUE"
            elif str(saved_desc).upper() == "FASTFREAK": saved_desc = "FAST-FREAK"
            else:                                         saved_desc = "SIFT"
        self.desc_combo.setCurrentText(saved_desc)
        self._refresh_matchers_for_descriptor()
        saved_match = _s("matcher", "FLANNBASED")
        if saved_match == "BRUTEFORCE_FL2":
            saved_match = "BRUTEFORCE_SL2"
        idx = self.match_combo.findText(saved_match)
        if idx >= 0:
            self.match_combo.setCurrentIndex(idx)

        self._on_base_mode_changed(self.base_mode.currentIndex())
        QtCore.QTimer.singleShot(0, self._update_subsampling_max)

    def _wrap(self, layout):
        w = QtWidgets.QWidget(); w.setLayout(layout); return w

    def _show_info(self):
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("AutoGR Bridge - About")
        msg.setWindowIcon(QtGui.QIcon(ICON_PATH))
        msg.setIcon(QtWidgets.QMessageBox.Information)
        msg.setTextFormat(QtCore.Qt.RichText)
        msg.setText(
            "<b>AutoGR Bridge</b> v" + PLUGIN_VERSION + "<br><br>"
            "This plugin connects QGIS to <b>AutoGR-Toolkit</b>, a set of tools for "
            "automatic image georeferencing using computer vision and machine learning/AI.<br><br>"
            "<b>What it does:</b><ul>"
            "<li>Uses a base raster layer (or canvas snapshot) as georeferenced reference.</li>"
            "<li>Launches AutoGR-SIFT with your dataset images and chosen settings.</li>"
            "<li>Optionally imports georeferenced results directly back into QGIS.</li>"
            "</ul>"
            "<b>Requirements:</b><ul>"
            "<li><b>AutoGR-Toolkit version 6.0 or later</b></li>"
            "<li>Download: <a href='https://github.com/giancan/AutoGR-Toolkit'>"
            "github.com/giancan/AutoGR-Toolkit</a></li>"
            "</ul>"
            "<b>Descriptors:</b> SIFT, ASIFT, SURF, AKAZE, KAZE, FAST-FREAK, ORB, BRISK, "
            "SuperGLUE, LoFTR, DISK, ALIKE-D+LightGlue<br>"
            "<i>Deep learning methods require the 64-bit version of AutoGR-Toolkit.</i><br><br>"
            "<b>Author:</b> Gianluca Cantoro<br>"
            "For any issue or problem, please contact "
            "<a href='mailto:gianluca.cantoro@gmail.com'>gianluca.cantoro@gmail.com</a>."
        )
        msg.exec_()

    def _on_dataset_item_clicked(self, item):
        self._refresh_preview(item.text())

    def _refresh_preview(self, path=None):
        if path is None:
            sel = self.dataset_list.currentItem()
            if sel is None:
                return
            path = sel.text()
        if not os.path.exists(path):
            self._preview_label.setPixmap(QtGui.QPixmap())
            self._preview_label.setText("file not found")
            return
        px = QtGui.QPixmap(path)
        if px.isNull():
            self._preview_label.setPixmap(QtGui.QPixmap())
            self._preview_label.setText("cannot preview")
            return
        angle = self.rot_spin.value()
        if angle != 0:
            px = px.transformed(QtGui.QTransform().rotate(angle),
                                 QtCore.Qt.SmoothTransformation)
        px = px.scaled(self._preview_label.width(), self._preview_label.height(),
                       QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        self._preview_label.setText("")
        self._preview_label.setPixmap(px)

    def _on_desc_changed(self, txt):
        _set("descriptor", txt)
        self._refresh_matchers_for_descriptor()

    def _on_match_changed(self, txt):
        if txt == "BRUTEFORCE_FL2":
            txt = "BRUTEFORCE_SL2"
        _set("matcher", txt)

    def _refresh_matchers_for_descriptor(self):
        desc = self.desc_combo.currentText()
        matchers, default = _matchers_for_descriptor(desc)
        self.match_combo.clear()
        for m in matchers:
            self.match_combo.addItem(m)
        saved = _s("matcher", "")
        if saved == "BRUTEFORCE_FL2":
            saved = "BRUTEFORCE_SL2"
        idx = self.match_combo.findText(saved)
        if idx >= 0:
            self.match_combo.setCurrentIndex(idx)
        else:
            didx = self.match_combo.findText(default)
            self.match_combo.setCurrentIndex(didx if didx >= 0 else 0)

    def _pick_exe(self):
        start_dir = os.path.dirname(_s("autogr_exe", "")) or ""
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select AutoGR-SIFT executable", start_dir,
            "AutoGR-SIFT (01-AutoGR_SIFT.exe);;Executable (*.exe);;All (*)")
        if fn:
            self.exe_edit.setText(fn); _set("autogr_exe", fn)

    def _pick_python(self):
        if _dist_mode(): return
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select Python interpreter", _s("python", ""),
            "Python (*.exe *.bin);;All (*)")
        if fn:
            self.python_edit.setText(fn); _set("python", fn)

    def _pick_tool(self):
        if _dist_mode(): return
        fn, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select AutoGR tool", _s("tool", ""),
            "Python (*.py);;Executable (*.exe);;All (*)")
        if fn:
            self.tool_edit.setText(fn); _set("tool", fn)

    def _pick_dataset_files(self):
        start = _s("dataset_lastdir", "")
        fns, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select dataset images", start,
            "Images (*.tif *.tiff *.png *.jpg *.jpeg);;All (*)")
        if fns:
            _set("dataset_lastdir", os.path.dirname(fns[0]))
            for f in fns:
                if not any(self.dataset_list.item(i).text() == f
                           for i in range(self.dataset_list.count())):
                    self.dataset_list.addItem(f)

    def _clear_dataset(self):
        self.dataset_list.clear()
        self._preview_label.setPixmap(QtGui.QPixmap())
        self._preview_label.setText("click image\nto preview")

    def _on_base_mode_changed(self, idx):
        self.layer_combo.setVisible(idx == 0)
        self.snapshot_note.setVisible(idx == 1)
        self._update_subsampling_max()

    def _populate_raster_layers(self):
        self.layer_combo.clear()
        self.layer_combo.addItem("-- Select raster --", "")
        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsRasterLayer):
                self.layer_combo.addItem(lyr.name(), lyr.id())

    def _update_subsampling_max(self):
        maxv = 1
        if self.base_mode.currentIndex() == 0:
            lyr_id = self.layer_combo.currentData()
            lyr    = QgsProject.instance().mapLayer(lyr_id) if lyr_id else None
            if lyr and isinstance(lyr, QgsRasterLayer):
                prov = lyr.dataProvider()
                maxv = max(maxv, prov.xSize(), prov.ySize())
        else:
            try:
                from qgis.utils import iface
                sz = iface.mapCanvas().size()
                maxv = max(maxv, sz.width(), sz.height())
            except Exception:
                pass
        for i in range(self.dataset_list.count()):
            path = self.dataset_list.item(i).text()
            try:
                reader = QtGui.QImageReader(path)
                sz = reader.size()
                if sz.isValid():
                    maxv = max(maxv, sz.width(), sz.height())
            except Exception:
                pass
        maxv = max(1, min(maxv, MAX_SUB))
        self.sub_spin.setMaximum(maxv)
        self.sub_slider.setMaximum(maxv)
        if self.sub_spin.value() > maxv:
            self.sub_spin.setValue(min(DEFAULT_SUB, maxv))

    def _pick_output(self):
        dn = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select output folder", _s("output", ""))
        if dn:
            self.out_edit.setText(dn); _set("output", dn)

    def _baseimage_path(self):
        return baseimage_path_from_dialog(self)


# ---------------------------------------------------------------------------
# Plugin class
# ---------------------------------------------------------------------------
class AutoGRBridgePlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.proc   = None
        self.this_run_marker = None
        self._buffer = bytearray()

    def initGui(self):
        try:
            self.action = QtWidgets.QAction(
                QtGui.QIcon(ICON_PATH), "AutoGR-Bridge", self.iface.mainWindow())
            self.action.triggered.connect(self.run)
            self.toolbar = self.iface.addToolBar("AutoGR-Bridge")
            self.toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            self.toolbar.addAction(self.action)
            self.iface.addPluginToMenu("&AutoGR", self.action)
        except Exception:
            import traceback
            _log("initGui error:\n" + traceback.format_exc(), Qgis.Critical)
            raise

    def unload(self):
        if self.action:
            self.iface.removePluginMenu("&AutoGR", self.action)
            try:
                if getattr(self, "toolbar", None):
                    self.iface.mainWindow().removeToolBar(self.toolbar)
                    self.toolbar = None
            except Exception:
                pass

    def _collect_dataset(self, dlg):
        return [dlg.dataset_list.item(i).text() for i in range(dlg.dataset_list.count())]

    def _derive_pyqt_paths(self, python_exe):
        py_dir    = pathlib.Path(python_exe).parent
        qt_root   = py_dir.parent / "Lib" / "site-packages" / "PyQt5" / "Qt"
        qt_bin    = qt_root / "bin"
        plugins   = qt_root / "plugins"
        platforms = plugins / "platforms"
        return str(qt_root), str(qt_bin), str(plugins), str(platforms)

    def _clean_env(self, program, is_py, pyexe):
        env  = QProcessEnvironment()
        keep = ["SystemRoot", "WINDIR", "COMSPEC", "NUMBER_OF_PROCESSORS",
                "USERPROFILE", "HOMEDRIVE", "HOMEPATH", "TEMP", "TMP",
                "APPDATA", "LOCALAPPDATA", "HOME",
                "USERNAME", "USER", "LOGNAME"]
        sysenv = QProcessEnvironment.systemEnvironment()
        for key in sysenv.keys():
            KU = key.upper()
            if KU in [k.upper() for k in keep] or KU.startswith("PROCESSOR_"):
                env.insert(key, sysenv.value(key))
        path_parts = []
        sysroot = sysenv.value("SystemRoot", "C:\\Windows")
        path_parts += [os.path.join(sysroot, "System32"), sysroot]
        prog_dir = os.path.dirname(program)
        if prog_dir: path_parts.insert(0, prog_dir)
        if is_py and pyexe:
            py_dir = os.path.dirname(pyexe)
            if py_dir not in path_parts: path_parts.insert(0, py_dir)
            qt_root, qt_bin, plugins, platforms = self._derive_pyqt_paths(pyexe)
            if os.path.isdir(qt_bin) and qt_bin not in path_parts:
                path_parts.insert(0, qt_bin)
            if os.path.isdir(platforms):
                env.insert("QT_QPA_PLATFORM_PLUGIN_PATH", platforms)
            if os.path.isdir(plugins):
                env.insert("QT_PLUGIN_PATH", plugins)
            qwep = os.path.join(qt_bin, "QtWebEngineProcess.exe")
            if os.path.isfile(qwep):
                env.insert("QTWEBENGINEPROCESS_PATH", qwep)
        env.insert("PATH",                       os.pathsep.join(path_parts))
        env.insert("PYTHONNOUSERSITE",           "1")
        env.insert("QT_QPA_PLATFORM",            "windows")
        env.insert("QTWEBENGINE_DISABLE_SANDBOX","1")
        env.insert("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu-sandbox")
        if not env.value("HOME") and env.value("USERPROFILE"):
            env.insert("HOME", env.value("USERPROFILE"))
        if not env.value("APPDATA"):
            av = sysenv.value("APPDATA")
            if av: env.insert("APPDATA", av)
        for bad in ["PYTHONHOME", "PYTHONPATH", "QGIS_PREFIX_PATH",
                    "OSGEO4W_ROOT", "GDAL_DATA", "PROJ_LIB"]:
            env.remove(bad)
        _log("PATH(head)=" + ";".join(path_parts[:5]))
        return env

    def _wire_logging(self, proc):
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._on_ready)
        proc.errorOccurred.connect(self._on_error)

    def _on_ready(self):
        if not self.proc: return
        data = self.proc.readAllStandardOutput()
        try:    s = bytes(data).decode("utf-8", errors="replace")
        except: s = str(data)
        self._buffer.extend(s.encode("utf-8", errors="ignore"))
        for line in s.splitlines(): _log("[tool] " + line)

    def _on_error(self, err):
        _log("QProcess error: " + self.proc.errorString(), Qgis.Critical)

    def _import_results_for_this_run(self, out_dir):
        if not out_dir or not os.path.isdir(out_dir):
            return 0
        imported   = 0
        start_time = self.this_run_marker or 0
        for root, _, files in os.walk(out_dir):
            for name in files:
                if not (name.endswith("_HOM.jpg") or name.endswith("_HOM.png")
                        or name.endswith("_georef.tif")):
                    continue
                full = os.path.join(root, name)
                try:
                    if os.path.getmtime(full) < start_time:
                        continue
                except Exception:
                    pass
                if name.endswith("_HOM.jpg") or name.endswith("_HOM.png"):
                    base_no_ext, _ = os.path.splitext(full)
                    if not _has_world_or_proj(base_no_ext):
                        continue
                r = QgsRasterLayer(full, pathlib.Path(name).stem)
                if r and r.isValid():
                    QgsProject.instance().addMapLayer(r)
                    imported += 1
        return imported

    def _build_launch(self, dlg, baseimage, dataset_files):
        if _dist_mode():
            tool = _s("autogr_exe", dlg.exe_edit.text().strip())
            if not tool or not os.path.isfile(tool):
                raise RuntimeError("AutoGR-SIFT executable path is empty or does not exist.")
            pyexe = None
        else:
            tool  = _s("tool",   dlg.tool_edit.text().strip())
            pyexe = _s("python", dlg.python_edit.text().strip())
            if not tool or not os.path.exists(tool):
                raise RuntimeError("AutoGR tool path is empty or does not exist.")
        is_py = tool.lower().endswith(".py")
        if is_py and (not pyexe or not os.path.exists(pyexe)):
            raise RuntimeError("Python interpreter path is empty or does not exist.")

        args = ["--from-qgis"]
        if str(_s("autostart", "false")).lower() == "true": args.append("--start")
        args.extend(["--baseimage", baseimage])
        for f in dataset_files: args.extend(["--dataset", f])
        args.extend(["--descriptor", str(_s("descriptor", "SIFT"))])
        matcher = str(_s("matcher", "FLANNBASED"))
        if matcher == "BRUTEFORCE_FL2": matcher = "BRUTEFORCE_SL2"
        args.extend(["--matcher", matcher])
        args.append("--subsampling=" + str(int(_s("subsampling", DEFAULT_SUB))))
        try:    rot = int(_s("rotation", 0))
        except: rot = 0
        if rot != 0:
            args.append("--rotation=" + str(rot))
        outdir = str(_s("output", "")).strip()
        if outdir: args.extend(["--output", outdir])

        if is_py:
            program = pyexe; argv = [tool] + args; workdir = os.path.dirname(tool) or None
        else:
            program = tool;  argv = args;           workdir = os.path.dirname(tool)

        pretty = " ".join(['"' + c + '"' if " " in c else c for c in [program] + argv])
        _log("Launching: " + pretty)
        return program, argv, workdir, is_py, pyexe

    def run(self):
        try:
            from qgis.utils import iface
            dlg = SettingsDialog(iface.mainWindow())
            if dlg.exec_() != QtWidgets.QDialog.Accepted:
                return
            baseimage     = baseimage_path_from_dialog(dlg)
            dataset_files = self._collect_dataset(dlg)
            if not baseimage or not dataset_files:
                QtWidgets.QMessageBox.warning(
                    self.iface.mainWindow(), "AutoGR Bridge",
                    "Please select a base image and at least one dataset file.")
                return
            try:
                program, argv, workdir, is_py, pyexe = self._build_launch(
                    dlg, baseimage, dataset_files)
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self.iface.mainWindow(), "AutoGR Bridge", str(e))
                return

            self.this_run_marker = int(time.time())
            self._buffer = bytearray()
            self.proc    = QProcess(self.iface.mainWindow())
            if workdir: self.proc.setWorkingDirectory(workdir)
            env = self._clean_env(program, is_py, pyexe if is_py else None)
            self.proc.setProcessEnvironment(env)
            self._wire_logging(self.proc)
            self.proc.finished.connect(
                lambda code, status: self._on_tool_finished(code, status, dlg))
            self.proc.start(program, argv)
            if not self.proc.waitForStarted(5000):
                QtWidgets.QMessageBox.critical(
                    self.iface.mainWindow(), "AutoGR Bridge",
                    "Failed to start AutoGR tool. " + self.proc.errorString())
                return
        except Exception as e:
            import traceback
            _log("Unhandled error in run():\n" + traceback.format_exc(), Qgis.Critical)
            try:
                QtWidgets.QMessageBox.critical(
                    self.iface.mainWindow(), "AutoGR Bridge",
                    "An unexpected error occurred:\n" + str(e))
            except Exception:
                pass

    def _on_tool_finished(self, exit_code, exit_status, dlg):
        if exit_code != 0:
            buf  = self._buffer.decode("utf-8", errors="replace") if self._buffer else "(no output)"
            tail = "\n".join(buf.splitlines()[-60:])
            QtWidgets.QMessageBox.critical(
                self.iface.mainWindow(), "AutoGR Bridge",
                "AutoGR exited with errors.\n\nLast output:\n" + tail)
        if str(_s("auto_import", "true")).lower() != "false":
            try:
                n = self._import_results_for_this_run(str(_s("output", "")).strip())
                _log("Imported " + str(n) + " rasters from this run.")
            except Exception as e:
                _log("Import error: " + str(e), Qgis.Critical)
        try:
            td = getattr(dlg, "_temp_canvas_dir", None)
            if td and os.path.isdir(td):
                import shutil
                shutil.rmtree(td, ignore_errors=True)
                _log("Deleted temporary canvas folder: " + td)
        except Exception as e:
            _log("Cleanup error: " + str(e), Qgis.Warning)
        self._buffer = bytearray()


__all__ = ["AutoGRBridgePlugin", "SettingsDialog"]

classFactory = lambda iface: AutoGRBridgePlugin(iface)

# -*- coding: utf-8 -*-
from qgis.PyQt import QtCore, QtGui, QtWidgets
from qgis.PyQt.QtCore import QProcess, QProcessEnvironment
from qgis.core import QgsProject, QgsRasterLayer, Qgis, QgsSettings


# ---------------------------------------------------------------------------
# Qt5 / Qt6 compatibility (QGIS 3 uses PyQt5, QGIS 4 uses PyQt6).
# PyQt6 only accepts scoped enum names (Qt.AlignmentFlag.AlignCenter); PyQt5
# also accepts the flat ones (Qt.AlignCenter). _qenum tries scoped, then flat,
# so the same plugin runs unchanged on both.
# ---------------------------------------------------------------------------
def _qenum(owner, scope, name):
    grp = getattr(owner, scope, None)
    if grp is not None and hasattr(grp, name):
        return getattr(grp, name)
    return getattr(owner, name)

_Qt = QtCore.Qt
Qt_Horizontal               = _qenum(_Qt, "Orientation",        "Horizontal")
Qt_SmoothTransformation     = _qenum(_Qt, "TransformationMode", "SmoothTransformation")
Qt_KeepAspectRatio          = _qenum(_Qt, "AspectRatioMode",    "KeepAspectRatio")
Qt_Tool                     = _qenum(_Qt, "WindowType",         "Tool")
Qt_ShiftModifier            = _qenum(_Qt, "KeyboardModifier",   "ShiftModifier")
Qt_RichText                 = _qenum(_Qt, "TextFormat",         "RichText")
Qt_OpenHandCursor           = _qenum(_Qt, "CursorShape",        "OpenHandCursor")
Qt_SizeFDiagCursor          = _qenum(_Qt, "CursorShape",        "SizeFDiagCursor")
Qt_SizeBDiagCursor          = _qenum(_Qt, "CursorShape",        "SizeBDiagCursor")
Qt_LeftButton               = _qenum(_Qt, "MouseButton",        "LeftButton")
QEvent_Show                 = _qenum(QtCore.QEvent, "Type",       "Show")
Qt_NoPen                    = _qenum(_Qt, "PenStyle",           "NoPen")
Qt_NoBrush                  = _qenum(_Qt, "BrushStyle",         "NoBrush")
Qt_AlignCenter              = _qenum(_Qt, "AlignmentFlag",      "AlignCenter")
Qt_ToolButtonTextBesideIcon = _qenum(_Qt, "ToolButtonStyle",    "ToolButtonTextBesideIcon")
QProcess_MergedChannels     = _qenum(QProcess, "ProcessChannelMode", "MergedChannels")
QProcess_FailedToStart      = _qenum(QProcess, "ProcessError",       "FailedToStart")
QPainter_Antialiasing       = _qenum(QtGui.QPainter, "RenderHint",   "Antialiasing")
QImage_ARGB32_Pre           = _qenum(QtGui.QImage,   "Format",       "Format_ARGB32_Premultiplied")
QMsgBox_Information         = _qenum(QtWidgets.QMessageBox, "Icon",       "Information")
QDialog_Accepted            = _qenum(QtWidgets.QDialog,     "DialogCode", "Accepted")
LVL_INFO                    = _qenum(Qgis, "MessageLevel", "Info")
LVL_WARN                    = _qenum(Qgis, "MessageLevel", "Warning")
LVL_CRIT                    = _qenum(Qgis, "MessageLevel", "Critical")

# QAction lives in QtWidgets on Qt5 and in QtGui on Qt6
QAction = getattr(QtWidgets, "QAction", None) or QtGui.QAction


def _exec(dialog):
    """Modal exec: exec() on PyQt6, exec_() on PyQt5."""
    fn = getattr(dialog, "exec", None) or getattr(dialog, "exec_")
    return fn()


def _evpos(e):
    """Mouse position as QPoint: position() on Qt6, pos() on Qt5."""
    if hasattr(e, "position"):
        try:
            return e.position().toPoint()
        except Exception as _exc:
            _ignored(_exc)
    return e.pos()

import os
import sys
import tempfile
import pathlib
import time
import json


_IGNORED_SEEN = set()


def _ignored(exc):
    """An exception the plugin can safely carry on from (best-effort UI
    updates, optional extras, cleanup). Nothing is ever fully silent: with
    'Debug logging' ticked, each place that swallowed one is reported once
    per session in the QGIS log (AutoGR Bridge panel)."""
    try:
        f = sys._getframe(1)
        where = (f.f_code.co_name, f.f_lineno)
        if where in _IGNORED_SEEN:
            return
        _IGNORED_SEEN.add(where)
        debug = QgsSettings().value("plugins/AutoGR_Bridge/debug", "true")
        if str(debug).lower() == "false":
            return
        from qgis.core import QgsMessageLog
        QgsMessageLog.logMessage(
            "Ignored %s in %s (line %d): %s"
            % (type(exc).__name__, where[0], where[1], exc),
            "AutoGR Bridge", LVL_INFO)
    except Exception:            # logging must never raise
        return

PLUGIN_ORG  = "AutoGR"
PLUGIN_NAME = "AutoGR_Bridge"
PLUGIN_VERSION = "7.0.0"
SETTINGS_PREFIX = f"plugins/{PLUGIN_NAME}"
LOG_TAG   = "AutoGR Bridge"
ICON_PATH = str(pathlib.Path(__file__).parent.joinpath("AutoGR-Bridge.ico"))

SIFT_EXE_NAME = "01-AutoGR_SIFT.exe"


def _dist_mode():
    return not (pathlib.Path(__file__).parent / "dev_mode").exists()


DEFAULT_SUB = 1000
MAX_SUB     = 9999

# Base snapshot sizing. The short side is kept usable for feature matching and
# the long side bounded so an extreme crop cannot ask for a huge image.
MIN_SNAP_SHORT_PX = 64
MAX_SNAP_LONG_PX  = 8000

# Descriptor list kept in sync with AutoGR-SIFT's dropdown (same order).
DESCRIPTORS = ["SIFT", "RootSIFT", "ASIFT", "SURF", "AKAZE", "KAZE", "FAST-FREAK",
               "ORB", "BRISK", "SuperGLUE", "LoFTR", "DISK", "ALIKE-D", "SuperPoint"]

# Deep-learning descriptors that AutoGR-SIFT only offers in its 64-bit build
# (hidden in the 32-bit GUI). Marked "(64-bit)" here and disabled when the
# selected AutoGR-SIFT target is 32-bit.
NEURAL_64BIT = {"SuperGLUE", "LoFTR", "DISK", "ALIKE-D", "SuperPoint"}


# Historical aerial film formats, (label, width cm, height cm). Labels carry
# both units because the sources do: continental European surveys quote cm,
# British and American ones quote inches. Sizes are the nominal frame, which is
# what the scale arithmetic wants -- not the film width.
FILM_FORMATS = [
    ("23 x 23 cm / 9 x 9 in", 23.0, 23.0),
    ("24 x 24 cm", 24.0, 24.0),
    ("18 x 18 cm / 7 x 7 in", 18.0, 18.0),
    ("30 x 30 cm", 30.0, 30.0),
    ("24 x 48 cm / 9 x 18 in", 24.0, 48.0),
    ("18 x 24 cm", 18.0, 24.0),
    ("21.6 x 17.8 cm / 8.5 x 7 in", 21.6, 17.8),
    ("13 x 18 cm / 5 x 7 in", 13.0, 18.0),
    ("12.7 x 12.7 cm / 5 x 5 in", 12.7, 12.7),
    ("14 x 14 cm / 5.5 x 5.5 in", 14.0, 14.0),
    ("11.4 x 11.4 cm / 4.5 x 4.5 in", 11.4, 11.4),
    ("10.2 x 12.7 cm / 4 x 5 in", 10.2, 12.7),
    ("10 x 10 cm / 4 x 4 in", 10.0, 10.0),
    ("6 x 6 cm / 2.25 x 2.25 in", 6.0, 6.0),
]

CM_PER_INCH = 2.54


def scan_size_cm(px_w, px_h, dpi_x=0.0, dpi_y=0.0):
    """Physical size of the image as scanned, (width_cm, height_cm, dpi), or
    None when the file gives no believable resolution.

    This is the size of everything in the file -- border, datastrip and film
    edge included -- which is exactly what the scale needs, since the whole
    image is what gets placed on the map. Screen resolutions (72/96 dpi, which
    Qt substitutes when a file states none) and implausible results are
    ignored."""
    if px_w <= 0 or px_h <= 0 or not dpi_x or not dpi_y:
        return None
    if any(abs(dpi_x - d) < 1.0 for d in (72.0, 96.0)):
        return None
    if not (120.0 <= dpi_x <= 12000.0 and 120.0 <= dpi_y <= 12000.0):
        return None
    w = px_w / float(dpi_x) * CM_PER_INCH
    h = px_h / float(dpi_y) * CM_PER_INCH
    if not (3.0 <= w <= 80.0 and 3.0 <= h <= 80.0):
        return None
    return w, h, dpi_x


def nearest_film_format(w_cm, h_cm):
    """(index, relative error) of the closest standard frame, either way up."""
    best, best_err = None, None
    for i, (_label, fw, fh) in enumerate(FILM_FORMATS):
        for a, b in ((fw, fh), (fh, fw)):
            err = max(abs(w_cm - a) / a, abs(h_cm - b) / b)
            if best_err is None or err < best_err:
                best, best_err = i, err
    return best, best_err


def guess_film_format(px_w, px_h, dpi_x=0.0, dpi_y=0.0):
    """Best-guess index into FILM_FORMATS for a scan, plus why.

    Returns (index or None, note, confident). Two levels of evidence:

    * the scan resolution, if the file carries one -- physical size is then
      px / dpi, which pins the format outright;
    * failing that, only the aspect ratio, which cannot separate 23x23 from
      24x24 from 30x30, so it is reported as a weak guess.

    A DPI tag can be wrong (resaved or resampled files), so the derived size is
    always reported for the user to sanity-check rather than trusted silently.
    """
    if px_w <= 0 or px_h <= 0:
        return None, "", False

    # Qt substitutes a screen resolution when the file carries none, and no
    # real film scan is made at 72 or 96 dpi (that would imply a frame about a
    # metre across), so treat those as "no information" rather than evidence.
    screen_dpi = any(abs(dpi_x - d) < 1.0 for d in (72.0, 96.0))
    if (dpi_x and dpi_y and not screen_dpi
            and 120.0 <= dpi_x <= 12000.0 and 120.0 <= dpi_y <= 12000.0):
        w_cm = px_w / float(dpi_x) * CM_PER_INCH
        h_cm = px_h / float(dpi_y) * CM_PER_INCH
        best, best_err = None, None
        for i, (_label, fw, fh) in enumerate(FILM_FORMATS):
            for a, b in ((fw, fh), (fh, fw)):     # scans can be either way up
                err = max(abs(w_cm - a) / a, abs(h_cm - b) / b)
                if best_err is None or err < best_err:
                    best, best_err = i, err
        note = ("scan is %.1f x %.1f cm at %.0f dpi" % (w_cm, h_cm, dpi_x))
        if best_err is not None and best_err <= 0.12:
            return best, note, True
        return None, note + " -- no close match", False

    ratio = float(px_w) / float(px_h)
    best, best_err = None, None
    for i, (_label, fw, fh) in enumerate(FILM_FORMATS):
        for a, b in ((fw, fh), (fh, fw)):
            err = abs(ratio - a / b) / (a / b)
            if best_err is None or err < best_err:
                best, best_err = i, err
    if best_err is not None and best_err <= 0.03:
        return best, "no scan resolution in the file; matched on shape only", False
    return None, "no scan resolution in the file", False


# Common survey/reconnaissance focal lengths, in inches first because that is
# how the older cameras are usually documented. Values in mm (1 in = 25.4 mm).
MM_PER_INCH = 25.4
FOCAL_LENGTHS = [
    ("3.5 in (89 mm)",    3.5 * MM_PER_INCH),
    ("6 in (152 mm)",     6.0 * MM_PER_INCH),
    ("8.25 in (210 mm)",  8.25 * MM_PER_INCH),
    ("12 in (305 mm)",   12.0 * MM_PER_INCH),
    ("20 in (508 mm)",   20.0 * MM_PER_INCH),
    ("24 in (610 mm)",   24.0 * MM_PER_INCH),
    ("36 in (914 mm)",   36.0 * MM_PER_INCH),
]
DEFAULT_FOCAL_LABEL = "6 in (152 mm)"


def _focal_label_from_saved(text):
    """Map a remembered focal-length choice onto the current list. Earlier
    builds labelled them mm-first ("152 mm (6 in)"), so match on the inches."""
    import re
    text = str(text or "")
    if any(text == lbl for lbl, _mm in FOCAL_LENGTHS) or text == "Custom...":
        return text
    m = re.search(r"\(([\d.]+) in\)", text)
    if m:
        want = float(m.group(1))
        for lbl, mm in FOCAL_LENGTHS:
            if abs(mm / MM_PER_INCH - want) < 1e-6:
                return lbl
    return DEFAULT_FOCAL_LABEL


def _fmt_focal(mm):
    """Focal length for messages: inches first, mm in brackets."""
    return "%.2f in (%.0f mm)" % (float(mm) / MM_PER_INCH, float(mm))

FEET_TO_M = 0.3048


def photo_ground_size(width_cm, height_cm, altitude_m, focal_mm):
    """Ground coverage of one frame: (scale_denominator, width_m, height_m).

        scale        = altitude / focal length
        ground size  = frame size x scale

    Note this is independent of scan resolution -- the number of pixels in the
    file never enters into it, so a rescanned or resaved image cannot skew it.
    """
    if not altitude_m or not focal_mm or altitude_m <= 0 or focal_mm <= 0:
        return None
    scale = float(altitude_m) / (float(focal_mm) / 1000.0)
    return scale, (float(width_cm) / 100.0) * scale, (float(height_cm) / 100.0) * scale


def solar_azimuth(lat, lon, year, month, day, hour, minute, utc_offset_h):
    """Sun azimuth and elevation in degrees (NOAA approximation).

    Azimuth is clockwise from true north. Good to a fraction of a degree, far
    better than the "average time per mission" the inputs come from."""
    import math
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    jdn = (day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400
           - 32045)
    jan1 = 1 + (153 * (1 + 12 * ((14 - 1) // 12) - 3) + 2) // 5
    del jan1
    # day of year
    a2 = (14 - 1) // 12
    y2 = year + 4800 - a2
    m2 = 1 + 12 * a2 - 3
    jdn_jan1 = (1 + (153 * m2 + 2) // 5 + 365 * y2 + y2 // 4 - y2 // 100
                + y2 // 400 - 32045)
    doy = jdn - jdn_jan1 + 1

    hours = float(hour) + float(minute) / 60.0
    gamma = 2.0 * math.pi / 365.0 * (doy - 1 + (hours - 12.0) / 24.0)
    eqtime = 229.18 * (0.000075 + 0.001868 * math.cos(gamma)
                       - 0.032077 * math.sin(gamma)
                       - 0.014615 * math.cos(2 * gamma)
                       - 0.040849 * math.sin(2 * gamma))
    decl = (0.006918 - 0.399912 * math.cos(gamma) + 0.070257 * math.sin(gamma)
            - 0.006758 * math.cos(2 * gamma) + 0.000907 * math.sin(2 * gamma)
            - 0.002697 * math.cos(3 * gamma) + 0.00148 * math.sin(3 * gamma))

    time_offset = eqtime + 4.0 * lon - 60.0 * float(utc_offset_h)
    tst = hours * 60.0 + time_offset
    ha = math.radians(tst / 4.0 - 180.0)
    latr = math.radians(lat)

    cos_zen = (math.sin(latr) * math.sin(decl)
               + math.cos(latr) * math.cos(decl) * math.cos(ha))
    cos_zen = max(-1.0, min(1.0, cos_zen))
    zen = math.acos(cos_zen)
    elevation = 90.0 - math.degrees(zen)

    sin_zen = math.sin(zen)
    if abs(sin_zen) < 1e-9:
        return 180.0, elevation
    c = ((math.sin(latr) * cos_zen - math.sin(decl))
         / (math.cos(latr) * sin_zen))
    # NOAA measures azimuth clockwise from north as acos(-c); the afternoon
    # half of the sky is the mirror of the morning half about due south.
    base = 180.0 - math.degrees(math.acos(max(-1.0, min(1.0, c))))
    azimuth = (360.0 - base) if math.degrees(ha) > 0 else base
    return azimuth % 360.0, elevation


# ---------------------------------------------------------------------------
# Clock time on the frame -> UTC.  Frames are stamped in the time the unit kept,
# which in wartime was usually double summer time (UTC+2 in summer, UTC+1 in
# winter) in Britain and on the continent. A suggestion is made from the date and
# the place; the user can always override it.
# Tables: UTC instant (YYYYMMDDHHMM) at which the offset (hours) took effect,
# 1916-1995, taken from the IANA tz database (Europe/London, Europe/Berlin) so
# QGIS needs no time-zone data of its own (Windows has no historical rules).
# From 1996 the common EU rule applies (last Sunday of March to last Sunday of
# October, 01:00 UTC). "de" (the Berlin record) stands for continental Europe,
# which kept the same clock during the war; it is a suggestion only.
# ---------------------------------------------------------------------------
_TZ_TABLES = {
    "uk": (
    "191601010000:0 191605210200:1 191610010200:0 191704080200:1 "
    "191709170200:0 191803240200:1 191809300200:0 191903300200:1 "
    "191909290200:0 192003280200:1 192010250200:0 192104030200:1 "
    "192110030200:0 192203260200:1 192210080200:0 192304220200:1 "
    "192309160200:0 192404130200:1 192409210200:0 192504190200:1 "
    "192510040200:0 192604180200:1 192610030200:0 192704100200:1 "
    "192710020200:0 192804220200:1 192810070200:0 192904210200:1 "
    "192910060200:0 193004130200:1 193010050200:0 193104190200:1 "
    "193110040200:0 193204170200:1 193210020200:0 193304090200:1 "
    "193310080200:0 193404220200:1 193410070200:0 193504140200:1 "
    "193510060200:0 193604190200:1 193610040200:0 193704180200:1 "
    "193710030200:0 193804100200:1 193810020200:0 193904160200:1 "
    "193911190200:0 194002250200:1 194105040100:2 194108100100:1 "
    "194204050100:2 194208090100:1 194304040100:2 194308150100:1 "
    "194404020100:2 194409170100:1 194504020100:2 194507150100:1 "
    "194510070200:0 194604140200:1 194610060200:0 194703160200:1 "
    "194704130100:2 194708100100:1 194711020200:0 194803140200:1 "
    "194810310200:0 194904030200:1 194910300200:0 195004160200:1 "
    "195010220200:0 195104150200:1 195110210200:0 195204200200:1 "
    "195210260200:0 195304190200:1 195310040200:0 195404110200:1 "
    "195410030200:0 195504170200:1 195510020200:0 195604220200:1 "
    "195610070200:0 195704140200:1 195710060200:0 195804200200:1 "
    "195810050200:0 195904190200:1 195910040200:0 196004100200:1 "
    "196010020200:0 196103260200:1 196110290200:0 196203250200:1 "
    "196210280200:0 196303310200:1 196310270200:0 196403220200:1 "
    "196410250200:0 196503210200:1 196510240200:0 196603200200:1 "
    "196610230200:0 196703190200:1 196710290200:0 196802180200:1 "
    "197110310200:0 197203190200:1 197210290200:0 197303180200:1 "
    "197310280200:0 197403170200:1 197410270200:0 197503160200:1 "
    "197510260200:0 197603210200:1 197610240200:0 197703200200:1 "
    "197710230200:0 197803190200:1 197810290200:0 197903180200:1 "
    "197910280200:0 198003160200:1 198010260200:0 198103290100:1 "
    "198110250100:0 198203280100:1 198210240100:0 198303270100:1 "
    "198310230100:0 198403250100:1 198410280100:0 198503310100:1 "
    "198510270100:0 198603300100:1 198610260100:0 198703290100:1 "
    "198710250100:0 198803270100:1 198810230100:0 198903260100:1 "
    "198910290100:0 199003250100:1 199010280100:0 199103310100:1 "
    "199110270100:0 199203290100:1 199210250100:0 199303280100:1 "
    "199310240100:0 199403270100:1 199410230100:0 199503260100:1 "
    "199510220100:0 "
    ),
    "de": (
    "191601010000:1 191604302200:2 191609302300:1 191704160100:2 "
    "191709170100:1 191804150100:2 191809160100:1 194004010100:2 "
    "194211020100:1 194303290100:2 194310040100:1 194404030100:2 "
    "194410020100:1 194504020100:2 194505240000:3 194509240000:2 "
    "194511180100:1 194604140100:2 194610070100:1 194704060200:2 "
    "194705110100:3 194706290000:2 194710050100:1 194804180100:2 "
    "194810030100:1 194904100100:2 194910020100:1 198004060100:2 "
    "198009280100:1 198103290100:2 198109270100:1 198203280100:2 "
    "198209260100:1 198303270100:2 198309250100:1 198403250100:2 "
    "198409300100:1 198503310100:2 198509290100:1 198603300100:2 "
    "198609280100:1 198703290100:2 198709270100:1 198803270100:2 "
    "198809250100:1 198903260100:2 198909240100:1 199003250100:2 "
    "199009300100:1 199103310100:2 199109290100:1 199203290100:2 "
    "199209270100:1 199303280100:2 199309260100:1 199403270100:2 "
    "199409250100:1 199503260100:2 199509240100:1 "
    ),
}
_TZ_BASE = {"uk": 0, "de": 1}
_TZ_NAMES = {
    "uk": {0: "GMT", 1: "British Summer Time", 2: "British Double Summer Time"},
    "de": {1: "CET, Central European Time", 2: "CEST, Central European Summer Time",
           3: "central European double summer time"},
}
_TZ_PARSED = {}


def _tz_table(region):
    if region not in _TZ_PARSED:
        _TZ_PARSED[region] = [(int(a), int(b)) for a, b in
                              (x.split(":") for x in _TZ_TABLES[region].split())]
    return _TZ_PARSED[region]


def _last_sunday(year, month):
    import datetime as _dt
    d = _dt.date(year, month + 1, 1) - _dt.timedelta(days=1)
    return d.day - (d.weekday() + 1) % 7


def utc_offset_on(region, year, month, day, hour=12):
    """Clock offset from UTC (hours) in force for a region on a date."""
    base = _TZ_BASE[region]
    if year >= 1996:
        start = (year, 3, _last_sunday(year, 3), 1)
        end = (year, 10, _last_sunday(year, 10), 1)
        return base + (1 if start <= (year, month, day, hour) < end else 0)
    key = ((year * 100 + month) * 100 + day) * 10000 + hour * 100
    off = base
    for when, o in _tz_table(region):
        if when <= key:
            off = o
        else:
            break
    return off


def _clock_region(lat, lon):
    """'uk' for the British Isles, 'de' for the rest of Europe, else None."""
    if lat is None or lon is None:
        return None
    if 49.8 <= lat <= 61.5 and -11.0 <= lon <= 2.0:
        # keep the French Channel coast (Calais, Boulogne, Dieppe) continental
        if lat >= 50.9 and lon < 1.5:
            return "uk"
        if lat < 50.9 and lon < 1.0:
            return "uk"
    if 35.0 <= lat <= 72.0 and -10.0 <= lon <= 32.0:
        return "de"
    return None


def suggest_utc_offset(lat, lon, year, month, day):
    """(offset hours, explanation) or (None, reason)."""
    region = _clock_region(lat, lon)
    if region is None:
        return None, "no suggestion for this area: set the time zone by hand"
    off = utc_offset_on(region, year, month, day)
    where = "Britain" if region == "uk" else "Continental Europe"
    name = _TZ_NAMES[region].get(off, "")
    return off, "%s on that date: %s%s" % (
        where, _utc_label(off), (" (" + name + ")") if name else "")


NO_DATE = QtCore.QDate(1900, 1, 1)   # the date box's 'unknown'


def _utc_label(off):
    return "UTC" if not off else "UTC%+d" % off


def _pe_is_64bit(path):
    """Read a Windows PE header and return True (x64/ARM64), False (x86),
    or None if it cannot be determined. Used to detect whether the selected
    AutoGR-SIFT executable / Python interpreter is 32- or 64-bit."""
    import struct
    try:
        with open(path, "rb") as f:
            if f.read(2) != b"MZ":
                return None
            f.seek(0x3C)
            e_lfanew = struct.unpack("<I", f.read(4))[0]
            f.seek(e_lfanew)
            if f.read(4) != b"PE\x00\x00":
                return None
            machine = struct.unpack("<H", f.read(2))[0]
            if machine in (0x8664, 0xAA64):   # AMD64 / ARM64
                return True
            if machine in (0x014C, 0x01C4):   # I386 / ARMNT (32-bit)
                return False
            return None
    except Exception:
        return None


def _s(key, default=""):
    return QgsSettings().value(f"{SETTINGS_PREFIX}/{key}", default)


def _set(key, val):
    QgsSettings().setValue(f"{SETTINGS_PREFIX}/{key}", val)


def _set_crop_extent(rect, crs_authid):
    """Remember the overlay footprint so the next base snapshot uses it."""
    if rect is None:
        _set("overlay_crop_extent", "")
        _set("overlay_crop_crs", "")
        return
    _set("overlay_crop_extent", "%.10f,%.10f,%.10f,%.10f" % (
        rect.xMinimum(), rect.yMinimum(), rect.xMaximum(), rect.yMaximum()))
    _set("overlay_crop_crs", str(crs_authid or ""))


def _take_crop_extent(dest_crs):
    """Pop the pending overlay footprint, if it is usable for this snapshot.

    The footprint is stored when the overlay is applied but only consumed here,
    at Run: the settings dialog is non-modal, so the user is free to pan and
    zoom in between, and the placement they confirmed should still win. It is
    one-shot, and dropped if the project CRS changed since it was stored."""
    from qgis.core import QgsRectangle
    raw = str(_s("overlay_crop_extent", "") or "").strip()
    if not raw:
        return None
    want = str(_s("overlay_crop_crs", "") or "").strip()
    _set_crop_extent(None, None)              # consume it either way
    try:
        have = dest_crs.authid()
    except Exception:
        have = ""
    if want and have and want != have:
        _log(f"Overlay crop ignored: stored for {want}, map is now {have}",
             LVL_WARN)
        return None
    try:
        x0, y0, x1, y1 = [float(v) for v in raw.split(",")]
    except Exception:
        return None
    rect = QgsRectangle(x0, y0, x1, y1)
    return None if rect.isEmpty() else rect


def _set_saved_view(canvas, crs_authid):
    """Remember the map view the footprint crop is about to replace.

    Stored as centre + scale, not as an extent: a rotated canvas reports an
    extent already padded to cover the rotated viewport, so feeding that back
    through setExtent() pads it a second time and the view creeps outwards."""
    if canvas is None:
        _set("view_before_crop", "")
        _set("view_before_crop_crs", "")
        return
    try:
        c = canvas.center()
        _set("view_before_crop", "%.10f,%.10f,%.10f,%.6f" % (
            c.x(), c.y(), float(canvas.scale()), float(canvas.rotation())))
        _set("view_before_crop_crs", str(crs_authid or ""))
    except Exception:
        _set("view_before_crop", "")
        _set("view_before_crop_crs", "")


def _take_saved_view(dest_crs):
    """Pop the view saved before the crop: (centre, scale, rotation) or None.

    Consumed on use, and dropped if the project CRS changed since it was
    stored, so it can never restore a view onto the wrong ground."""
    from qgis.core import QgsPointXY
    raw = str(_s("view_before_crop", "") or "").strip()
    if not raw:
        return None
    want = str(_s("view_before_crop_crs", "") or "").strip()
    _set_saved_view(None, None)
    try:
        have = dest_crs.authid()
    except Exception:
        have = ""
    if want and have and want != have:
        return None
    try:
        cx, cy, scale, rot = [float(v) for v in raw.split(",")]
    except Exception:
        return None
    if scale <= 0:
        return None
    return QgsPointXY(cx, cy), scale, rot


def _has_world_or_proj(path_no_ext):
    exts = [".tfw", ".jgw", ".pgw", ".wld", ".prj", ".aux.xml"]
    return any(os.path.exists(path_no_ext + e) for e in exts)


TEMP_CANVAS_PREFIX = "autogr_canvas_"

# Every canvas-snapshot folder made this session. A single attribute is not
# enough: the snapshot is taken once for the dialog preview and again at Run,
# so each launch creates more than one and only the last would be remembered.
_TEMP_CANVAS_DIRS = []


def _nice_tempdir(prefix=TEMP_CANVAS_PREFIX):
    td = pathlib.Path(tempfile.gettempdir()) / (prefix + next(tempfile._get_candidate_names()))
    td.mkdir(parents=True, exist_ok=True)
    td = str(td)
    if prefix == TEMP_CANVAS_PREFIX:
        _TEMP_CANVAS_DIRS.append(td)
    return td


def _purge_temp_canvas_dirs():
    """Delete the snapshot folders this session created."""
    import shutil
    n = 0
    while _TEMP_CANVAS_DIRS:
        td = _TEMP_CANVAS_DIRS.pop()
        try:
            if os.path.isdir(td):
                shutil.rmtree(td, ignore_errors=True)
                n += 1
        except Exception as _exc:
            _ignored(_exc)
    if n:
        _log("Deleted %d temporary canvas folder(s)." % n)
    return n


def _sweep_stale_temp_dirs(max_age_hours=24):
    """Remove snapshot folders older than a day, left by earlier sessions.

    A QGIS crash, a cancelled run or a failed launch all skip the normal
    cleanup, so without a sweep these would accumulate. Only folders matching
    the plugin's
    own prefix and containing nothing but a canvas snapshot are touched, and
    only once they are old enough that no live session could still be using
    one."""
    import shutil
    import time as _time
    cutoff = _time.time() - max_age_hours * 3600.0
    root = pathlib.Path(tempfile.gettempdir())
    removed = 0
    try:
        for d in root.glob(TEMP_CANVAS_PREFIX + "*"):
            try:
                if not d.is_dir() or str(d) in _TEMP_CANVAS_DIRS:
                    continue
                if d.stat().st_mtime > cutoff:
                    continue
                names = {f.name for f in d.iterdir()}
                if names and not names <= {"canvas.png", "canvas.pgw",
                                           "canvas.prj", "canvas.wld",
                                           "canvas.png.aux.xml"}:
                    continue          # not ours to delete
                shutil.rmtree(str(d), ignore_errors=True)
                removed += 1
            except Exception as _exc:
                _ignored(_exc)
                continue
    except Exception as _exc:
        _ignored(_exc)
    if removed:
        _log("Swept %d stale temporary canvas folder(s)." % removed)
    return removed


def _appdata_dir():
    base = os.environ.get("APPDATA") or str(pathlib.Path.home())
    p = pathlib.Path(base) / "AutoGR-T"
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


LOG_MAX_BYTES = 512 * 1024      # the log file never grows past this


def _trim_log(path):
    """Keep the log small: once it passes LOG_MAX_BYTES, keep only the most
    recent half (cut at a line break)."""
    try:
        if os.path.getsize(path) <= LOG_MAX_BYTES:
            return
        with open(path, "rb") as f:
            f.seek(-(LOG_MAX_BYTES // 2), os.SEEK_END)
            tail = f.read()
        nl = tail.find(b"\n")
        if nl >= 0:
            tail = tail[nl + 1:]
        with open(path, "wb") as f:
            f.write(b"[older entries removed to keep this file small]\n" + tail)
    except Exception as _exc:
        _ignored(_exc)


def _log(msg, level=LVL_INFO):
    from qgis.core import QgsMessageLog
    QgsMessageLog.logMessage(str(msg), LOG_TAG, level)
    try:
        path = os.path.join(_appdata_dir(), "autogr_bridge_qgis.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(str(msg).rstrip() + "\n")
        _trim_log(path)
    except Exception as _exc:
        _ignored(_exc)


def _geographic_distortion(crs, lat_deg, lon_deg=None):
    """(stretch, percent, suggested_epsg) when the CRS is in degrees, else None.

    A snapshot rendered in a geographic CRS has pixels that are square in
    DEGREES, but a degree of longitude covers cos(latitude) as much ground as a
    degree of latitude, so the base image comes out stretched east-west -- 34%
    at 42 degrees north, 55% at 50. Feature matchers are not invariant to an
    anisotropic scale change: it both invents matches between wrongly-shaped
    patches and rejects good ones on ratio and geometric-consistency tests.
    """
    try:
        if crs is None or not crs.isGeographic():
            return None
    except Exception:
        return None
    import math
    lat = max(-89.5, min(89.5, float(lat_deg)))
    east = 111320.0 * math.cos(math.radians(lat))
    north = 110574.0
    if east <= 1.0:
        return None
    stretch = north / east
    epsg = None
    if lon_deg is not None:
        try:
            zone = max(1, min(60, int((float(lon_deg) + 180.0) // 6) + 1))
            epsg = (32600 if lat >= 0 else 32700) + zone
        except Exception:
            epsg = None
    return stretch, abs(stretch - 1.0) * 100.0, epsg


def _geographic_warning(crs, lat_deg, lon_deg=None):
    """The message to show, or None when the CRS is fine."""
    geo = _geographic_distortion(crs, lat_deg, lon_deg)
    if geo is None:
        return None
    stretch, pct, epsg = geo
    try:
        authid = crs.authid() or "this CRS"
    except Exception:
        authid = "this CRS"
    msg = ("Project CRS %s is in degrees. The base image is stretched "
           "east-west by %.0f%% at this latitude, which causes false matches "
           "and throws away good ones." % (authid, pct))
    if epsg:
        msg += " Use a projected CRS in metres, e.g. EPSG:%d." % epsg
    else:
        msg += " Use a projected CRS in metres."
    return msg


def _builtin_matchers_for_descriptor(desc):
    # Fallback copy of AutoGR-SIFT's descriptor -> matcher rules, used only when
    # the linked toolkit cannot report its own (older build, not linked yet).
    d = (desc or "").strip()
    if d in ["AKAZE", "ORB", "BRISK", "FAST-FREAK"]:
        matchers = ["BRUTEFORCE", "BRUTEFORCE_HAMMING", "BRUTEFORCE_HAMMINGLUT",
                    "BRUTEFORCE_L1", "BRUTEFORCE_SL2"]
        default  = "BRUTEFORCE_SL2"
    elif d in ["KAZE", "SURF", "ASIFT", "SIFT", "RootSIFT"]:
        matchers = ["FLANNBASED", "BRUTEFORCE", "BRUTEFORCE_L1", "BRUTEFORCE_SL2"]
        default  = "FLANNBASED"
    elif d == "SuperGLUE":
        matchers = ["SINKHORN (SuperGLUE)"]; default = "SINKHORN (SuperGLUE)"
    elif d == "LoFTR":
        matchers = ["LoFTR (built-in)"];     default = "LoFTR (built-in)"
    elif d == "DISK":
        matchers = ["DISK (built-in)"];      default = "DISK (built-in)"
    elif d in ["ALIKE-D", "SuperPoint"]:
        # sparse learned keypoints: LightGlue (learned) or AdaLAM (geometric)
        matchers = ["LightGlue", "AdaLAM"];  default = "LightGlue"
    else:
        matchers = ["BRUTEFORCE"];           default = "BRUTEFORCE"
    return matchers, default


# ---------------------------------------------------------------------------
# Algorithm list reported by the linked AutoGR-SIFT
#
# AutoGR-SIFT answers --list-algorithms PATH with the descriptors and matchers
# it offers, so the bridge's lists always match the linked toolkit. It is asked
# whenever the linked executable or script changes, and the answer is cached
# against that file's size and timestamp. The built-in lists above are the
# fallback for an older toolkit or before anything is linked.
# ---------------------------------------------------------------------------
ALGO_CACHE_KEY = "algo_cache_key"
ALGO_CACHE_JSON = "algo_cache_json"
ALGO_CACHE_NOTE = "algo_cache_note"


def _toolkit_target():
    """(program, args_prefix, workdir, is_py, pyexe, signature) or None.

    The signature changes whenever the linked toolkit is replaced or rebuilt,
    which is what invalidates the cached algorithm list."""
    if _dist_mode():
        exe = str(_s("autogr_exe", "") or "").strip()
        if not exe or not os.path.isfile(exe):
            return None
        program, prefix, is_py, pyexe, sig = exe, [], False, None, [exe]
    else:
        tool = str(_s("tool", "") or "").strip()
        pyexe = str(_s("python", "") or "").strip()
        if not tool or not os.path.isfile(tool):
            return None
        if tool.lower().endswith(".py"):
            if not pyexe or not os.path.isfile(pyexe):
                return None
            program, prefix, is_py, sig = pyexe, [tool], True, [tool, pyexe]
        else:
            program, prefix, is_py, pyexe, sig = tool, [], False, None, [tool]
    parts = []
    for p in sig:
        try:
            st = os.stat(p)
        except OSError:
            return None
        parts.append("%s|%d|%d" % (os.path.normcase(os.path.abspath(p)),
                                   int(st.st_mtime), st.st_size))
    workdir = os.path.dirname(prefix[0] if prefix else program)
    return program, prefix, workdir, is_py, pyexe, "||".join(parts)


def _parse_algorithm_json(raw):
    """Validated --list-algorithms document, or None."""
    import json
    try:
        d = json.loads(raw)
    except Exception:
        return None
    if not isinstance(d, dict) or d.get("schema") != 1:
        return None
    clean = []
    for e in d.get("descriptors") or []:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name") or "").strip()
        ms = [str(m) for m in (e.get("matchers") or []) if str(m).strip()]
        if not name or not ms:
            continue
        dm = str(e.get("default_matcher") or ms[0])
        clean.append({"name": name, "matchers": ms,
                      "default_matcher": dm if dm in ms else ms[0],
                      "neural": bool(e.get("neural")),
                      "available": bool(e.get("available", True))})
    if not clean:
        return None
    d["descriptors"] = clean
    return d


def _toolkit_cache_state():
    """('fresh', info) | ('unsupported', note) | ('stale', None)."""
    tgt = _toolkit_target()
    if tgt is None or str(_s(ALGO_CACHE_KEY, "") or "") != tgt[5]:
        return "stale", None
    info = _parse_algorithm_json(str(_s(ALGO_CACHE_JSON, "") or ""))
    if info is not None:
        return "fresh", info
    return "unsupported", str(_s(ALGO_CACHE_NOTE, "") or "")


def _builtin_algorithm_table():
    return [{"name": n,
             "matchers": _builtin_matchers_for_descriptor(n)[0],
             "default_matcher": _builtin_matchers_for_descriptor(n)[1],
             "neural": n in NEURAL_64BIT, "available": None}
            for n in DESCRIPTORS]


def _algorithm_table():
    """(descriptor entries, toolkit info or None) -- the toolkit's own list when
    it has reported one for the currently linked build, else the built-in."""
    state, info = _toolkit_cache_state()
    if state == "fresh":
        return info["descriptors"], info
    return _builtin_algorithm_table(), None


def _matchers_for_descriptor(desc):
    for e in _algorithm_table()[0]:
        if e["name"] == desc:
            return list(e["matchers"]), e["default_matcher"]
    return _builtin_matchers_for_descriptor(desc)


def _canonical_descriptor(saved, names):
    """Map a saved/legacy spelling (ROOTSIFT, FASTFREAK, eloftr...) onto one of
    the names currently on offer, or None."""
    key = str(saved or "").upper().replace("-", "").replace("_", "")
    for n in names:
        if n.upper().replace("-", "").replace("_", "") == key:
            return n
    return None


def _derive_pyqt_paths(python_exe):
    py_dir    = pathlib.Path(python_exe).parent
    qt_root   = py_dir.parent / "Lib" / "site-packages" / "PyQt5" / "Qt"
    qt_bin    = qt_root / "bin"
    plugins   = qt_root / "plugins"
    platforms = plugins / "platforms"
    return str(qt_root), str(qt_bin), str(plugins), str(platforms)


def _clean_process_env(program, is_py, pyexe, quiet=False):
    """Environment for launching AutoGR-SIFT from inside QGIS: QGIS's own
    Python and GDAL settings stripped, so the toolkit's interpreter and Qt are
    the ones that load."""
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
        qt_root, qt_bin, plugins, platforms = _derive_pyqt_paths(pyexe)
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
    if not _dist_mode():
        # Developer mode only (toolkit run from its Python sources): the web
        # engine's sandbox cannot start from a plain interpreter folder. The
        # installed toolkit keeps its sandbox.
        env.insert("QTWEBENGINE_DISABLE_SANDBOX", "1")
        env.insert("QTWEBENGINE_CHROMIUM_FLAGS", "--no-sandbox --disable-gpu-sandbox")
    if not env.value("HOME") and env.value("USERPROFILE"):
        env.insert("HOME", env.value("USERPROFILE"))
    if not env.value("APPDATA"):
        av = sysenv.value("APPDATA")
        if av: env.insert("APPDATA", av)
    for bad in ["PYTHONHOME", "PYTHONPATH", "QGIS_PREFIX_PATH",
                "OSGEO4W_ROOT", "GDAL_DATA", "PROJ_LIB"]:
        env.remove(bad)
    if not quiet:
        _log("PATH(head)=" + ";".join(path_parts[:5]))
    return env


# ---------------------------------------------------------------------------
# Headless runs (developer mode only)
#
# The bridge starts the toolkit with
#     --from-qgis --start --headless --progress-file PATH  (+ the usual options)
# and expects it to work without showing its window, answer its own dialogs
# with their default choice, and exit when done (exit code 0 = success).
# Because the built toolkit has no console, progress goes through PATH, one
# UTF-8 line per event, appended as the run goes:
#     PROGRESS <0-100> [text]    overall progress, optional status text
#     STATUS <text>              status text only
#     LOG <text>                 anything worth keeping in the bridge log
#     DIALOG <text>              a dialog that was answered automatically
#     RESULT OK|FAIL [text]      final outcome (written just before exiting)
# Unknown lines are logged and otherwise ignored. A toolkit that does not know
# --headless stops at once with a usage error; the bridge reports that.
# ---------------------------------------------------------------------------
def _parse_progress_lines(text, state):
    """Fold new progress-file lines into state (a dict) and return the lines
    worth logging."""
    logged = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        state["seen"] = True
        key, _, rest = line.partition(" ")
        key = key.upper()
        if key == "PROGRESS":
            num, _, msg = rest.partition(" ")
            try:
                state["pct"] = max(0, min(100, int(float(num))))
            except ValueError as _exc:
                _ignored(_exc)
            if msg.strip():
                state["text"] = msg.strip()
        elif key == "STATUS":
            state["text"] = rest.strip()
        elif key == "RESULT":
            ok, _, msg = rest.partition(" ")
            state["result"] = ok.strip().upper()
            state["result_text"] = msg.strip()
            logged.append(line)
        else:                                   # LOG, DIALOG, anything else
            logged.append(line)
    return logged


class ToolkitAlgorithmQuery(QtCore.QObject):
    """Ask the linked AutoGR-SIFT for its algorithm list, without blocking.

    Runs `<toolkit> --list-algorithms <file>` in the background and caches the
    answer -- or the fact that this build cannot give one -- against the
    toolkit's signature, so each build is asked exactly once."""
    finished = QtCore.pyqtSignal(bool, str)
    TIMEOUT_MS = 45000

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc = None
        self._key = None
        self._out = None
        self._tmpdir = None
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)

    def running(self):
        return self.proc is not None

    def start(self):
        if self.running():
            return False
        tgt = _toolkit_target()
        if tgt is None:
            return False
        program, prefix, workdir, is_py, pyexe, key = tgt
        self._key = key
        self._tmpdir = tempfile.mkdtemp(prefix="autogr_algos_")
        self._out = os.path.join(self._tmpdir, "algorithms.json")
        self.proc = QProcess(self)
        if workdir:
            self.proc.setWorkingDirectory(workdir)
        self.proc.setProcessEnvironment(
            _clean_process_env(program, is_py, pyexe, quiet=True))
        self.proc.finished.connect(self._on_finished)
        self.proc.errorOccurred.connect(self._on_error)
        self.proc.start(program, prefix + ["--list-algorithms", self._out])
        self._timer.start(self.TIMEOUT_MS)
        return True

    def cancel(self):
        self._timer.stop()
        p, self.proc = self.proc, None
        if p is not None:
            try:
                p.finished.disconnect(self._on_finished)
            except Exception as _exc:
                _ignored(_exc)
            try:
                p.kill()
                p.waitForFinished(2000)
            except Exception as _exc:
                _ignored(_exc)
        self._discard_tmp()

    def _discard_tmp(self):
        import shutil
        if self._tmpdir:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            self._tmpdir = None

    def _store(self, raw, note):
        _set(ALGO_CACHE_KEY, self._key)
        _set(ALGO_CACHE_JSON, raw)
        _set(ALGO_CACHE_NOTE, note)

    def _on_error(self, err):
        if err == QProcess_FailedToStart:
            self._timer.stop()
            self.proc = None
            self._discard_tmp()
            self.finished.emit(False, "could not start AutoGR-SIFT")

    def _on_timeout(self):
        # An old build that ignored the flag would sit there with its window
        # open: kill it, and remember the verdict so it is not tried again.
        self.cancel()
        self._store("", "AutoGR-SIFT did not answer --list-algorithms")
        self.finished.emit(False, "AutoGR-SIFT did not answer in time")

    def _on_finished(self, code, _status):
        self._timer.stop()
        self.proc = None
        raw = ""
        try:
            if self._out and os.path.isfile(self._out):
                with open(self._out, "r", encoding="utf-8") as f:
                    raw = f.read()
        except Exception:
            raw = ""
        self._discard_tmp()
        info = _parse_algorithm_json(raw) if raw else None
        if info is None:
            note = ("this AutoGR-SIFT build predates --list-algorithms"
                    if code == 2 else
                    "AutoGR-SIFT gave no usable algorithm list (exit %s)" % code)
            self._store("", note)
            _log("Algorithm list: " + note + "; using the built-in list.")
            self.finished.emit(False, note)
            return
        self._store(raw, "")
        _log("Algorithm list: %d descriptors from %s %s"
             % (len(info["descriptors"]), info.get("tool", "AutoGR-SIFT"),
                info.get("version", "")))
        self.finished.emit(True, "")


def save_canvas_snapshot_georef(out_png_path):
    from qgis.utils import iface
    from qgis.core import QgsMapSettings, QgsMapRendererCustomPainterJob
    from qgis.PyQt.QtGui import QImage, QPainter
    from qgis.PyQt.QtCore import QSize
    canvas        = iface.mapCanvas()
    dest_crs      = canvas.mapSettings().destinationCrs()
    extent        = canvas.extent()
    canvas_width  = canvas.width()
    canvas_height = canvas.height()

    # A footprint stored by the overlay ("zoom to the image footprint") beats
    # whatever the view happens to show now, so panning or zooming out between
    # applying the overlay and pressing Run does not silently widen the base
    # image that gets matched.
    _crop = _take_crop_extent(dest_crs)
    _restore = _take_saved_view(dest_crs)
    if _crop is None:
        _restore = None          # nothing was cropped, so nothing to put back
    if _crop is not None:
        _log(f"Snapshot: using the overlay footprint {_crop.toString()} "
             f"instead of the current view {extent.toString()}")
        extent = _crop

    # The canvas may be rotated for display (bottom-right rotation field). The
    # base snapshot is always captured NORTH-UP with an axis-aligned world file
    # so its georeference is unambiguous; warn the user if the map is rotated.
    try:
        rot = float(canvas.rotation())
    except Exception:
        rot = 0.0
    _log(f"Snapshot: canvas rotation={rot} deg, extent={extent.toString()}, "
         f"CRS={dest_crs.authid()}")
    if abs(rot) > 1e-6:
        try:
            iface.messageBar().pushMessage(
                "AutoGR Bridge",
                f"The map is rotated ({rot:g} deg). The base snapshot is captured "
                "north-up; the QGIS display rotation is not applied to it.",
                level=LVL_WARN, duration=8)
        except Exception as _exc:
            _ignored(_exc)

    _geo_msg = _geographic_warning(dest_crs, extent.center().y(),
                                   extent.center().x())
    if _geo_msg:
        _log("Snapshot: " + _geo_msg, LVL_WARN)
        try:
            iface.messageBar().pushMessage("AutoGR Bridge", _geo_msg,
                                           level=LVL_WARN, duration=12)
        except Exception as _exc:
            _ignored(_exc)

    # Output size. Both dimensions come from ONE ground resolution so the
    # pixels stay square: fitting width and height independently skews the
    # image whenever the extent is far from the canvas shape, which a footprint
    # crop of a long, narrow photo easily is (and at the limit it truncates the
    # short side to zero). For an extent shaped like the canvas this produces
    # exactly the old result.
    from qgis.core import QgsRectangle as _Rect
    ext_w, ext_h = extent.width(), extent.height()
    res = max(ext_w / max(1, canvas_width), ext_h / max(1, canvas_height))
    short_side = min(ext_w, ext_h)
    if short_side / res < MIN_SNAP_SHORT_PX:
        # Very elongated: raise the resolution rather than pad the crop, so the
        # snapshot still covers exactly the footprint and stays usable.
        res = short_side / float(MIN_SNAP_SHORT_PX)
    if max(ext_w, ext_h) / res > MAX_SNAP_LONG_PX:
        res = max(ext_w, ext_h) / float(MAX_SNAP_LONG_PX)
    width  = max(1, int(round(ext_w / res)))
    height = max(1, int(round(ext_h / res)))
    # snap the extent onto that pixel grid, so the world file describes exactly
    # square pixels instead of inheriting the rounding error
    _c = extent.center()
    extent = _Rect(_c.x() - width * res / 2.0, _c.y() - height * res / 2.0,
                   _c.x() + width * res / 2.0, _c.y() + height * res / 2.0)
    if min(width, height) < MIN_SNAP_SHORT_PX:
        _log(f"Snapshot: base image is only {width}x{height} px -- the area is "
             f"extremely elongated, matching may be unreliable", LVL_WARN)
    settings = QgsMapSettings()
    settings.setExtent(extent)
    settings.setOutputSize(QSize(width, height))
    settings.setLayers(canvas.layers())
    settings.setDestinationCrs(dest_crs)
    settings.setBackgroundColor(canvas.canvasColor())
    try:
        settings.setRotation(0)   # force north-up regardless of the display
    except Exception as _exc:
        _ignored(_exc)
    img = QImage(QSize(width, height), QImage_ARGB32_Pre)
    img.fill(settings.backgroundColor().rgb())
    painter = QPainter(img)
    job = QgsMapRendererCustomPainterJob(settings, painter)
    job.start(); job.waitForFinished()
    painter.end()
    img.save(out_png_path, "PNG")

    # The snapshot is taken, so the footprint zoom has done its job: hand the
    # user back the view they were on before applying the overlay.
    if _restore is not None:
        try:
            _centre, _scale, _rot = _restore
            canvas.setRotation(_rot)
            canvas.setCenter(_centre)
            canvas.zoomScale(_scale)
            canvas.refresh()
            _log(f"Snapshot: map view restored to centre "
                 f"{_centre.x():.1f},{_centre.y():.1f} scale 1:{_scale:.0f} "
                 f"(rotation {_rot:g} deg)")
            try:
                iface.messageBar().pushMessage(
                    "AutoGR Bridge",
                    "Base image captured from the overlay footprint; "
                    "the map view has been restored.",
                    level=LVL_INFO, duration=5)
            except Exception as _exc:
                _ignored(_exc)
        except Exception:
            import traceback
            _log("Could not restore the map view: " + traceback.format_exc(),
                 LVL_WARN)
    pixel_x_size = extent.width()  / width
    pixel_y_size = -extent.height() / height
    upper_left_x = extent.xMinimum() + (pixel_x_size / 2.0)
    upper_left_y = extent.yMaximum() + (pixel_y_size / 2.0)
    _log(f"Snapshot worldfile: pxsize={pixel_x_size:.6f} x {abs(pixel_y_size):.6f}, "
         f"ULx={upper_left_x:.3f}, ULy={upper_left_y:.3f}, out={width}x{height}")
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
    except Exception as _exc:
        _ignored(_exc)


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
        from qgis.PyQt.QtGui import QPainter, QPen, QBrush, QColor, QPolygonF
        from qgis.PyQt.QtCore import QPointF
        p  = QPainter(self)
        p.setRenderHint(QPainter_Antialiasing)
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
        p.setPen(Qt_NoPen)
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
    # custom exec_() result: user asked to open the on-map overlay preview
    OVERLAY_RESULT = 1234

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
            self.python_edit = QtWidgets.QLineEdit(_s("python", ""))
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

        # Watched live: the project CRS can be changed while this dialog is
        # open, and a geographic one silently distorts the base image.
        self.crs_note = QtWidgets.QLabel("")
        self.crs_note.setWordWrap(True)
        self.crs_note.setStyleSheet(
            "color: #a00; font-weight: bold; border: 1px solid #a00; "
            "padding: 4px;")
        self.crs_note.setVisible(False)

        self.dataset_list = QtWidgets.QListWidget()
        self.dataset_list.setMinimumHeight(80)
        self.dataset_add = QtWidgets.QPushButton("Add files...")
        self.dataset_clr = QtWidgets.QPushButton("Clear")
        self.dataset_overlay = QtWidgets.QPushButton("Overlay on map...")
        self.dataset_overlay.setToolTip(
            "Place the selected dataset image over the QGIS map at 50% "
            "transparency to check the fit. Drag to move it, scale and rotate "
            "it, then optionally apply the rotation to the bridge.")
        # remember the dataset between sessions: restore the saved files that
        # still exist on disk (silently drop any that were moved/deleted)
        try:
            saved_ds = json.loads(_s("dataset_files", "[]"))
        except Exception:
            saved_ds = []
        for f in saved_ds:
            if f and os.path.exists(f):
                self.dataset_list.addItem(f)

        self._preview_label = QtWidgets.QLabel()
        self._preview_label.setFixedSize(220, 220)
        self._preview_label.setAlignment(Qt_AlignCenter)
        self._preview_label.setStyleSheet("border: 1px solid #ccc; background: #f5f5f5; color: #999;")
        self._preview_label.setText("click image\nto preview")

        self.desc_combo = QtWidgets.QComboBox()
        self._populate_descriptors()
        self.desc_combo.setToolTip(
            "Feature detection and description algorithm.\n"
            "Deep learning methods (SuperGLUE, LoFTR, DISK, ALIKE-D, SuperPoint) "
            "require the 64-bit AutoGR-SIFT (marked '(64-bit)').")
        self.match_combo = QtWidgets.QComboBox()
        self.match_combo.setToolTip("Matching strategy - updated automatically based on the selected descriptor.")

        try:
            init_sub = int(_s("subsampling", DEFAULT_SUB))
        except Exception:
            init_sub = DEFAULT_SUB
        self.sub_spin   = QtWidgets.QSpinBox()
        self.sub_spin.setRange(1, MAX_SUB)
        self.sub_spin.setValue(init_sub)
        self.sub_slider = QtWidgets.QSlider(Qt_Horizontal)
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

        # Developer mode: run the toolkit without its window
        self.chk_headless = None
        if not _dist_mode():
            self.chk_headless = QtWidgets.QCheckBox(
                "Run headless (developer mode)")
            self.chk_headless.setChecked(
                str(_s("dev_headless", "false")).lower() == "true")
            self.chk_headless.setToolTip(
                "The toolkit works in the background, without its window. "
                "Passes --headless and --progress-file to the toolkit. This "
                "dialog stays open, greyed out, with the progress and a Cancel "
                "button; results are imported when the run ends. Needs a "
                "toolkit build that understands --headless.")
            self.chk_headless.stateChanged.connect(
                lambda _: _set("dev_headless",
                               "true" if self.chk_headless.isChecked() else "false"))

        # Progress strip for headless runs (hidden otherwise)
        self.run_panel = QtWidgets.QFrame()
        self.run_panel.setFrameShape(
            _qenum(QtWidgets.QFrame, "Shape", "StyledPanel"))
        self.run_bar = QtWidgets.QProgressBar()
        self.run_bar.setRange(0, 100)
        self.run_text = QtWidgets.QLabel("")
        self.run_text.setWordWrap(True)
        self.btn_stop = QtWidgets.QPushButton("Cancel run")
        rl = QtWidgets.QGridLayout(self.run_panel)
        rl.addWidget(QtWidgets.QLabel("<b>AutoGR is running in the background</b>"), 0, 0, 1, 2)
        rl.addWidget(self.run_bar, 1, 0)
        rl.addWidget(self.btn_stop, 1, 1)
        rl.addWidget(self.run_text, 2, 0, 1, 2)
        self.run_panel.setVisible(False)
        self.on_stop_run = None
        self.btn_stop.clicked.connect(
            lambda: self.on_stop_run() if callable(self.on_stop_run) else None)

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
        form.addRow(self.crs_note)

        hds_btns = QtWidgets.QHBoxLayout()
        hds_btns.addWidget(self.dataset_add)
        hds_btns.addWidget(self.dataset_clr)
        hds_btns.addWidget(self.dataset_overlay)
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

        self.btn_algos = QtWidgets.QToolButton()
        self.btn_algos.setText("\u21bb")
        self.btn_algos.setToolTip(
            "Ask the linked AutoGR-SIFT again for the algorithms it offers. "
            "Done automatically whenever the linked executable or script "
            "changes.")
        self.btn_algos.clicked.connect(lambda: self._maybe_requery(force=True))
        hdesc = QtWidgets.QHBoxLayout()
        hdesc.addWidget(self.desc_combo, 1)
        hdesc.addWidget(self.btn_algos)
        form.addRow("Descriptor:", self._wrap(hdesc))
        self.lbl_algos = QtWidgets.QLabel("")
        self.lbl_algos.setWordWrap(True)
        self.lbl_algos.setStyleSheet("color: #666; font-size: 10px;")
        form.addRow("", self.lbl_algos)
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
        if self.chk_headless is not None:
            opts.addWidget(self.chk_headless)
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
        # the settings sit in one container so a background run can grey
        # them out in one go
        self.settings_box = QtWidgets.QWidget()
        form.setContentsMargins(0, 0, 0, 0)
        self.settings_box.setLayout(form)
        main.addWidget(self.settings_box)
        main.addWidget(self.run_panel)
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
        # The algorithm list is re-read from AutoGR-SIFT whenever the link
        # changes; debounced so typing a path does not launch it per keystroke.
        self._algo_query = ToolkitAlgorithmQuery(self)
        self._algo_query.finished.connect(self._on_algos_ready)
        self._algo_timer = QtCore.QTimer(self)
        self._algo_timer.setSingleShot(True)
        self._algo_timer.setInterval(900)
        self._algo_timer.timeout.connect(self._on_toolkit_link_changed)
        if _dist_mode():
            self.exe_edit.textChanged.connect(
                lambda v: (_set("autogr_exe", v), self._algo_timer.start()))
        else:
            self.python_edit.textChanged.connect(
                lambda v: (_set("python", v), self._algo_timer.start()))
            self.tool_edit.textChanged.connect(
                lambda v: (_set("tool", v), self._algo_timer.start()))
        self.out_edit.textChanged.connect(lambda v: _set("output", v))
        self.chk_autostart.stateChanged.connect(
            lambda _: _set("autostart",   "true" if self.chk_autostart.isChecked()   else "false"))
        self.chk_auto_import.stateChanged.connect(
            lambda _: _set("auto_import", "true" if self.chk_auto_import.isChecked() else "false"))
        self.chk_debug.stateChanged.connect(
            lambda _: _set("debug",       "true" if self.chk_debug.isChecked()       else "false"))
        self.dataset_add.clicked.connect(self._pick_dataset_files)
        self.dataset_clr.clicked.connect(self._clear_dataset)
        self.dataset_overlay.clicked.connect(self._request_overlay)
        try:
            QgsProject.instance().crsChanged.connect(self._update_crs_note)
        except Exception as _exc:
            _ignored(_exc)
        self.dataset_list.itemClicked.connect(self._on_dataset_item_clicked)
        self.dataset_list.model().rowsInserted.connect(
            lambda *_: QtCore.QTimer.singleShot(0, self._update_subsampling_max))
        self.dataset_list.model().rowsRemoved.connect(
            lambda *_: QtCore.QTimer.singleShot(0, self._update_subsampling_max))

        offered = [self.desc_combo.itemData(i)
                   for i in range(self.desc_combo.count())]
        saved_desc = (_canonical_descriptor(_s("descriptor", "SIFT"), offered)
                      or (offered[0] if offered else "SIFT"))
        idx = self.desc_combo.findData(saved_desc)
        self.desc_combo.setCurrentIndex(idx if idx >= 0 else 0)
        # disable 64-bit-only descriptors when the target is 32-bit, and fall
        # back to the first descriptor if the saved one is now unavailable
        self._apply_bitness_availability()
        self._update_crs_note()
        self._refresh_matchers_for_descriptor()
        self._update_algo_label()
        # first link, or the toolkit was rebuilt since it was last asked
        QtCore.QTimer.singleShot(0, self._maybe_requery)
        saved_match = _s("matcher", "FLANNBASED")
        if saved_match == "BRUTEFORCE_FL2":
            saved_match = "BRUTEFORCE_SL2"
        idx = self.match_combo.findText(saved_match)
        if idx >= 0:
            self.match_combo.setCurrentIndex(idx)

        self._on_base_mode_changed(self.base_mode.currentIndex())
        QtCore.QTimer.singleShot(0, self._update_subsampling_max)

    def set_running(self, running, pct=0, text=""):
        """Grey out the settings while a headless run is going on, and show
        its progress; restore everything when it ends."""
        self.settings_box.setEnabled(not running)
        self.btn_run.setEnabled(not running)
        self.run_panel.setVisible(bool(running))
        if running:
            self.set_progress(pct, text)
        try:
            self.adjustSize()
        except Exception as _exc:
            _ignored(_exc)

    def set_progress(self, pct, text=""):
        try:
            self.run_bar.setValue(max(0, min(100, int(pct))))
        except Exception as _exc:
            _ignored(_exc)
        if text:
            self.run_text.setText(text)

    def _wrap(self, layout):
        w = QtWidgets.QWidget(); w.setLayout(layout); return w

    def _show_info(self):
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("AutoGR Bridge - About")
        msg.setWindowIcon(QtGui.QIcon(ICON_PATH))
        msg.setIcon(QMsgBox_Information)
        msg.setTextFormat(Qt_RichText)
        msg.setText(
            "<b>AutoGR Bridge</b> v" + PLUGIN_VERSION + "<br><br>"
            "This plugin connects QGIS to <b>AutoGR-Toolkit</b>, a set of tools for "
            "automatic image georeferencing using computer vision and machine learning/AI.<br><br>"
            "<b>What it does:</b><ul>"
            "<li>Uses a base raster layer (or canvas snapshot) as georeferenced reference.</li>"
            "<li>Launches AutoGR-SIFT with your dataset images and chosen settings.</li>"
            "<li>Optionally imports georeferenced results directly back into QGIS.</li>"
            "<li>'Overlay on map' places a dataset image over the map at 50% "
            "transparency (move / scale / rotate) to check the fit and set the rotation. "
            "On apply it can also zoom the map to the area the image covers, so the "
            "base snapshot used for matching is limited to that area.</li>"
            "</ul>"
            "<b>Requirements:</b><ul>"
            "<li><b>AutoGR-Toolkit version 7.0 or later</b></li>"
            "<li>Download: <a href='https://github.com/giancan/AutoGR-Toolkit'>"
            "github.com/giancan/AutoGR-Toolkit</a></li>"
            "</ul>"
            "<b>Descriptors:</b> "
            + ", ".join(e["name"] for e in _algorithm_table()[0]) + "<br>"
            "<i>Deep learning methods (marked '(64-bit)') require the 64-bit "
            "version of AutoGR-Toolkit and are disabled when a 32-bit target is "
            "selected.</i><br><br>"
            "<b>Author:</b> Gianluca Cantoro<br>"
            "For any issue or problem, please contact "
            "<a href='mailto:gianluca.cantoro@gmail.com'>gianluca.cantoro@gmail.com</a>."
        )
        _exec(msg)

    def _on_dataset_item_clicked(self, item):
        self._refresh_preview(item.text())

    def _request_overlay(self):
        """Remember which dataset image to overlay, then close the dialog with
        the OVERLAY_RESULT code so the plugin can start the on-map session
        (the canvas can't be used while this modal dialog is open)."""
        item = self.dataset_list.currentItem()
        if item is None and self.dataset_list.count():
            item = self.dataset_list.item(0)
        if item is None:
            QtWidgets.QMessageBox.information(
                self, "AutoGR Bridge",
                "Add and select a dataset image first, then use 'Overlay on map'.")
            return
        self._overlay_image = item.text()
        self.done(self.OVERLAY_RESULT)

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
                                 Qt_SmoothTransformation)
        px = px.scaled(self._preview_label.width(), self._preview_label.height(),
                       Qt_KeepAspectRatio, Qt_SmoothTransformation)
        self._preview_label.setText("")
        self._preview_label.setPixmap(px)

    def _current_descriptor(self):
        """Clean descriptor name (without the '(64-bit)' marker)."""
        d = self.desc_combo.currentData()
        if d:
            return d
        return self.desc_combo.currentText().split("(")[0].strip()

    def _populate_descriptors(self):
        """Fill the descriptor combo from the linked toolkit's own list when it
        has reported one, else the built-in list. Display text carries a
        '(64-bit)' marker for the learned methods; the clean name is the item
        data. The current choice survives a refill whenever it still exists."""
        keep = (self._current_descriptor() if self.desc_combo.count()
                else str(_s("descriptor", "SIFT")))
        table, _info = _algorithm_table()
        self.desc_combo.blockSignals(True)
        self.desc_combo.clear()
        for e in table:
            text = e["name"] + ("   (64-bit)" if e["neural"] else "")
            self.desc_combo.addItem(text, e["name"])
        name = _canonical_descriptor(keep, [e["name"] for e in table])
        idx = self.desc_combo.findData(name) if name else -1
        self.desc_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.desc_combo.blockSignals(False)

    def _target_is_64bit(self):
        """True / False / None for the selected AutoGR-SIFT target (exe in
        distribution mode, Python interpreter in dev mode)."""
        if _dist_mode():
            p = str(_s("autogr_exe", "")).strip()
        else:
            p = str(_s("python", "")).strip()
        return _pe_is_64bit(p) if p and os.path.isfile(p) else None

    def _apply_bitness_availability(self):
        """Enable/disable the descriptors the target cannot run.

        When the toolkit has reported its list it also says what this build
        can run -- which depends on more than bitness (a 64-bit build without
        its model assets cannot run the learned methods either), so that
        verdict is used as is. Otherwise fall back to reading the target's PE
        header. Either way an unavailable pick falls back to the first one
        that is available."""
        table, info = _algorithm_table()
        if info is not None:
            avail = {e["name"]: e["available"] for e in table}
            model = self.desc_combo.model()
            first_ok = None
            for i in range(self.desc_combo.count()):
                name = self.desc_combo.itemData(i)
                ok = avail.get(name, True)
                item = model.item(i) if hasattr(model, "item") else None
                if item is not None:
                    item.setEnabled(ok)
                if ok and first_ok is None:
                    first_ok = i
            if not avail.get(self._current_descriptor(), True) and first_ok is not None:
                self.desc_combo.setCurrentIndex(first_ok)
                self._refresh_matchers_for_descriptor()
            return
        is64 = self._target_is_64bit()
        restrict = (is64 is False)   # only restrict when we KNOW it's 32-bit
        model = self.desc_combo.model()
        for i in range(self.desc_combo.count()):
            name = self.desc_combo.itemData(i)
            item = model.item(i) if hasattr(model, "item") else None
            if item is not None:
                item.setEnabled(not (restrict and name in NEURAL_64BIT))
        if restrict and self._current_descriptor() in NEURAL_64BIT:
            self.desc_combo.setCurrentIndex(0)   # SIFT
            self._refresh_matchers_for_descriptor()

    # ---- algorithm list from the linked toolkit ----------------------------
    def _on_toolkit_link_changed(self):
        self._populate_descriptors()
        self._apply_bitness_availability()
        self._refresh_matchers_for_descriptor()
        self._update_algo_label()
        self._maybe_requery()

    def _maybe_requery(self, force=False):
        """Ask the toolkit for its list if this build has not been asked."""
        if getattr(self, "_algo_query", None) is None:
            return
        if self._algo_query.running():
            return
        state, _x = _toolkit_cache_state()
        if state != "stale" and not force:
            return
        if _toolkit_target() is None:
            self._update_algo_label()
            return
        if self._algo_query.start():
            self.lbl_algos.setText("Reading the algorithm list from "
                                   "AutoGR-SIFT\u2026")
            self.btn_algos.setEnabled(False)

    def _on_algos_ready(self, ok, note):
        self.btn_algos.setEnabled(True)
        self._populate_descriptors()
        self._apply_bitness_availability()
        self._refresh_matchers_for_descriptor()
        self._update_algo_label()

    def _update_algo_label(self):
        state, x = _toolkit_cache_state()
        if state == "fresh":
            n = len(x["descriptors"])
            off = sum(1 for e in x["descriptors"] if not e["available"])
            txt = "%d algorithms from %s %s (%s-bit)" % (
                n, x.get("tool", "AutoGR-SIFT"), x.get("version", ""),
                x.get("bits", "?"))
            if off:
                txt += ", %d not available in this build" % off
        elif state == "unsupported":
            txt = ("Built-in list: " + (x or "the linked toolkit gave none")
                   + ". Rebuild AutoGR-SIFT to have the bridge follow it.")
        elif _toolkit_target() is None:
            txt = "Built-in list: link AutoGR-SIFT to read its own."
        else:
            txt = "Built-in list."
        try:
            self.lbl_algos.setText(txt)
        except Exception as _exc:
            _ignored(_exc)

    def _on_desc_changed(self, _txt=None):
        _set("descriptor", self._current_descriptor())
        self._refresh_matchers_for_descriptor()

    def _on_match_changed(self, txt):
        if txt == "BRUTEFORCE_FL2":
            txt = "BRUTEFORCE_SL2"
        _set("matcher", txt)

    def _refresh_matchers_for_descriptor(self):
        # use the clean descriptor name, not the display text (which may carry
        # the "(64-bit)" marker) — otherwise the matcher list falls back to a
        # single BRUTEFORCE entry and appears "locked"
        desc = self._current_descriptor()
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
            self._persist_dataset()

    def _persist_dataset(self):
        """Remember the current dataset file list across sessions."""
        files = [self.dataset_list.item(i).text()
                 for i in range(self.dataset_list.count())]
        _set("dataset_files", json.dumps(files))

    def _clear_dataset(self):
        self.dataset_list.clear()
        self._preview_label.setPixmap(QtGui.QPixmap())
        self._preview_label.setText("click image\nto preview")
        self._persist_dataset()

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
            except Exception as _exc:
                _ignored(_exc)
        for i in range(self.dataset_list.count()):
            path = self.dataset_list.item(i).text()
            try:
                reader = QtGui.QImageReader(path)
                sz = reader.size()
                if sz.isValid():
                    maxv = max(maxv, sz.width(), sz.height())
            except Exception as _exc:
                _ignored(_exc)
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

    def _update_crs_note(self, *_args):
        """Show or hide the degrees-CRS warning for the current project."""
        try:
            from qgis.utils import iface
            canvas = iface.mapCanvas()
            crs = canvas.mapSettings().destinationCrs()
            c = canvas.extent().center()
            msg = _geographic_warning(crs, c.y(), c.x())
        except Exception:
            msg = None
        try:
            self.crs_note.setText(msg or "")
            self.crs_note.setVisible(bool(msg))
        except Exception as _exc:
            _ignored(_exc)

    def done(self, r):
        # this dialog is replaced rather than destroyed, so an undisconnected
        # signal would keep firing into a stale one
        try:
            QgsProject.instance().crsChanged.disconnect(self._update_crs_note)
        except Exception as _exc:
            _ignored(_exc)
        try:
            self._algo_timer.stop()
            self._algo_query.cancel()
        except Exception as _exc:
            _ignored(_exc)
        super().done(r)

    def _baseimage_path(self):
        return baseimage_path_from_dialog(self)


# ---------------------------------------------------------------------------
# Map overlay: place a dataset image over the QGIS map (50% transparency) to
# visually check the fit. The overlay is map-locked (follows pan/zoom); the
# user drags to move it and uses the panel to scale/rotate/adjust opacity.
# ---------------------------------------------------------------------------
try:
    from qgis.gui import QgsMapCanvasItem, QgsMapTool
    from qgis.core import QgsPointXY, QgsRectangle
    _OVERLAY_AVAILABLE = True
except Exception:
    QgsMapCanvasItem = object
    QgsMapTool = object
    _OVERLAY_AVAILABLE = True   # resolved lazily; guarded at use


# Overlay items that have been taken off the canvas. They are kept alive on
# purpose: Qt may still reach a removed QGraphicsItem from a queued paint, and
# freeing one out from under the scene is an instant QGIS crash. Their pixmap is
# released on retirement, so each entry is a few bytes.
_RETIRED_OVERLAY_ITEMS = []


class OverlayCanvasItem(QgsMapCanvasItem):
    """A pixmap drawn on the canvas, anchored to map coordinates.

    Placement is tracked in MAP space so the overlay stays put as the user
    pans/zooms:
      center : QgsPointXY  - image centre in map CRS
      gsd    : float       - map units per image pixel (ground sampling)
      angle  : float       - clockwise rotation in degrees
    """

    def __init__(self, canvas, pixmap):
        super().__init__(canvas)
        self._canvas  = canvas
        self._pixmap  = pixmap
        ext = canvas.extent()
        self.center = ext.center()
        # start so the image spans ~60% of the current view width
        self._base_gsd = (ext.width() * 0.6) / max(1, pixmap.width())
        self.gsd     = self._base_gsd
        self.angle   = 0.0
        self._opacity = 0.5
        self.shadow_azimuth = None   # deg clockwise from true north, or None
        # Arrow anchor as an offset in IMAGE pixels from the centre, so it
        # stays on the same feature of the photo when it is moved, scaled or
        # turned. (0, 0) is the middle of the frame.
        self.shadow_anchor = (0.0, 0.0)
        # corner handles for scaling by mouse; hidden while the mission data
        # fixes the size, since the scale cannot be changed then
        self.handles_visible = True
        self.setZValue(10000)

    # ---- placement setters (trigger a geometry-aware repaint) ----
    def set_center(self, pt):
        self.prepareGeometryChange(); self.center = pt; self.update()

    def set_scale_pct(self, pct):
        self.prepareGeometryChange()
        self.gsd = self._base_gsd * max(1, float(pct)) / 100.0
        self.update()

    def set_angle(self, deg):
        self.prepareGeometryChange(); self.angle = float(deg); self.update()

    def set_shadow_anchor_from_map(self, pt):
        """Put the arrow where the user shift-clicked, in image space."""
        import math
        try:
            scr = self._screen_scale()
            if scr <= 0:
                return
            here = self.toCanvasCoordinates(pt)
            centre = self.toCanvasCoordinates(self.center)
            dx, dy = here.x() - centre.x(), here.y() - centre.y()
            a = math.radians(-self.angle)          # undo the image rotation
            ix = (dx * math.cos(a) - dy * math.sin(a)) / scr
            iy = (dx * math.sin(a) + dy * math.cos(a)) / scr
            w, h = self._pixmap.width() / 2.0, self._pixmap.height() / 2.0
            self.prepareGeometryChange()
            self.shadow_anchor = (max(-w, min(w, ix)), max(-h, min(h, iy)))
            self.update()
        except Exception as _exc:
            _ignored(_exc)

    def _anchor_canvas_point(self, centre_pt, screen_scale):
        import math
        ix, iy = self.shadow_anchor
        if ix == 0.0 and iy == 0.0:
            return centre_pt
        a = math.radians(self.angle)
        dx = (ix * math.cos(a) - iy * math.sin(a)) * screen_scale
        dy = (ix * math.sin(a) + iy * math.cos(a)) * screen_scale
        return QtCore.QPointF(centre_pt.x() + dx, centre_pt.y() + dy)

    def set_shadow_azimuth(self, deg):
        """Direction shadows fall, clockwise from true north (None hides it)."""
        self.prepareGeometryChange()
        self.shadow_azimuth = None if deg is None else float(deg) % 360.0
        self.update()

    def set_base_gsd(self, gsd):
        """Set the map units per image pixel that the 100% scale means."""
        self.prepareGeometryChange()
        self._base_gsd = float(gsd)
        self.update()

    def set_opacity(self, o):
        self._opacity = max(0.0, min(1.0, float(o))); self.update()

    HANDLE_PX = 9          # side of a corner handle on screen, in pixels

    def set_handles_visible(self, on):
        self.handles_visible = bool(on); self.update()

    def corner_canvas_points(self):
        """Screen positions of the four image corners, in the order
        top-left, top-right, bottom-right, bottom-left of the photo itself
        (so they follow its rotation). Opposite corner of i is (i + 2) % 4."""
        import math
        pt  = self.toCanvasCoordinates(self.center)
        scr = self._screen_scale()
        w, h = self._pixmap.width() / 2.0, self._pixmap.height() / 2.0
        a = math.radians(self.angle)
        ca, sa = math.cos(a), math.sin(a)
        out = []
        for ix, iy in ((-w, -h), (w, -h), (w, h), (-w, h)):
            out.append(QtCore.QPointF(pt.x() + (ix * ca - iy * sa) * scr,
                                      pt.y() + (ix * sa + iy * ca) * scr))
        return out

    def corner_at(self, canvas_pt, tolerance=None):
        """Index of the corner handle under a screen point, or None."""
        if not self.handles_visible or self._pixmap.isNull():
            return None
        tol = (self.HANDLE_PX / 2.0 + 3) if tolerance is None else tolerance
        try:
            for i, c in enumerate(self.corner_canvas_points()):
                if (abs(c.x() - canvas_pt.x()) <= tol
                        and abs(c.y() - canvas_pt.y()) <= tol):
                    return i
        except Exception as _exc:
            _ignored(_exc)
        return None

    def _paint_handles(self, painter):
        if not self.handles_visible:
            return
        s = float(self.HANDLE_PX)
        painter.save()
        painter.setOpacity(1.0)
        pen = QtGui.QPen(QtGui.QColor(210, 50, 50))
        pen.setCosmetic(True); pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QtGui.QBrush(QtGui.QColor(255, 255, 255)))
        for c in self.corner_canvas_points():
            painter.drawRect(QtCore.QRectF(c.x() - s / 2, c.y() - s / 2, s, s))
        painter.restore()

    def _screen_scale(self):
        try:
            mupp = self._canvas.mapSettings().mapUnitsPerPixel()
        except Exception:
            mupp = self._canvas.mapUnitsPerPixel()
        return (self.gsd / mupp) if mupp and mupp > 0 else 1.0

    def updatePosition(self):
        # called by the canvas when the extent changes
        self.prepareGeometryChange(); self.update()

    def boundingRect(self):
        import math
        try:
            pt  = self.toCanvasCoordinates(self.center)
            scr = self._screen_scale()
            R = (0.5 * math.hypot(self._pixmap.width(), self._pixmap.height()) * scr
                 + self.HANDLE_PX + 4)
            if self.shadow_azimuth is not None:
                ix, iy = self.shadow_anchor
                off = math.hypot(ix, iy) * scr
                R = max(R, off + self._arrow_len(scr) + 24)
            return QtCore.QRectF(pt.x() - R, pt.y() - R, 2 * R, 2 * R)
        except Exception:
            return QtCore.QRectF(-1e5, -1e5, 2e5, 2e5)

    def paint(self, painter, option=None, widget=None):
        if self._pixmap.isNull():
            return
        try:
            pt  = self.toCanvasCoordinates(self.center)
            scr = self._screen_scale()
            w, h = self._pixmap.width(), self._pixmap.height()
            painter.save()
            painter.translate(pt)
            painter.rotate(self.angle)
            painter.scale(scr, scr)
            painter.setOpacity(self._opacity)
            painter.drawPixmap(QtCore.QPointF(-w / 2.0, -h / 2.0), self._pixmap)
            # thin red border to show the image extent
            pen = QtGui.QPen(QtGui.QColor(210, 50, 50))
            pen.setCosmetic(True); pen.setWidth(2)
            painter.setOpacity(min(1.0, self._opacity + 0.35))
            painter.setPen(pen); painter.setBrush(Qt_NoBrush)
            painter.drawRect(int(-w / 2), int(-h / 2), int(w), int(h))
            painter.restore()
            self._paint_handles(painter)
            self._paint_shadow_arrow(painter, pt, scr)
        except Exception as _exc:
            _ignored(_exc)

    def _arrow_len(self, screen_scale):
        return 0.45 * max(self._pixmap.width(), self._pixmap.height()) * screen_scale

    def _paint_shadow_arrow(self, painter, centre_pt, screen_scale):
        """Draw the direction shadows should fall, as a true-north reference.

        Deliberately NOT drawn inside the image rotation: it is a real-world
        direction, and the whole point is to turn the photo until its own
        shadows line up with it. The tip is derived in MAP coordinates and then
        projected, so display rotation is handled by the canvas transform
        instead of by juggling angle conventions here."""
        import math
        if self.shadow_azimuth is None:
            return
        try:
            length = self._arrow_len(screen_scale)
            if length <= 4:
                return
            anchor = self._anchor_canvas_point(centre_pt, screen_scale)
            anchor_map = self.toMapCoordinates(
                QtCore.QPoint(int(round(anchor.x())), int(round(anchor.y()))))
            step = length * self._canvas.mapSettings().mapUnitsPerPixel()
            a = math.radians(self.shadow_azimuth)
            tip_map = QgsPointXY(anchor_map.x() + step * math.sin(a),
                                 anchor_map.y() + step * math.cos(a))
            tip = self.toCanvasCoordinates(tip_map)
            dx, dy = tip.x() - anchor.x(), tip.y() - anchor.y()
            n = math.hypot(dx, dy)
            if n < 4:
                return
            ux, uy = dx / n, dy / n

            painter.save()
            painter.setOpacity(1.0)
            pen = QtGui.QPen(QtGui.QColor(255, 200, 0))
            pen.setCosmetic(True); pen.setWidth(3)
            painter.setPen(pen)
            painter.drawLine(anchor, tip)
            # a small ring marks where the arrow is pinned
            painter.drawEllipse(anchor, 4.0, 4.0)
            head = max(8.0, min(22.0, n * 0.18))
            for sign in (1, -1):
                bx = tip.x() - ux * head - sign * uy * head * 0.5
                by = tip.y() - uy * head + sign * ux * head * 0.5
                painter.drawLine(tip, QtCore.QPointF(bx, by))
            painter.restore()
        except Exception as _exc:
            _ignored(_exc)


class OverlayMoveTool(QgsMapTool):
    """Drag the overlay on the canvas (map-space), or drag one of its corner
    handles to scale it.

    Corner drag always keeps the aspect ratio (the photo has one ground
    resolution, which the mission maths rely on). The opposite corner stays
    put; with Shift held the image scales around its centre instead.
    Shift-click away from the handles still moves the shadow arrow."""

    def __init__(self, canvas, item):
        super().__init__(canvas)
        self.item = item
        self._grab = None
        self._resize = None
        # set by OverlaySession: callable(pct) that moves the scale slider,
        # and callable() -> current pct
        self.on_scale_pct = None
        self.current_pct = None
        self.setCursor(Qt_OpenHandCursor)

    # -- helpers --
    def _map_point(self, qpointf):
        """Screen -> map without rounding to whole pixels where possible."""
        try:
            return self.canvas().getCoordinateTransform().toMapCoordinates(
                float(qpointf.x()), float(qpointf.y()))
        except Exception:
            return self.toMapCoordinates(
                QtCore.QPoint(int(round(qpointf.x())), int(round(qpointf.y()))))

    @staticmethod
    def _diag_cursor(anchor, corner):
        dx, dy = corner.x() - anchor.x(), corner.y() - anchor.y()
        return Qt_SizeFDiagCursor if dx * dy >= 0 else Qt_SizeBDiagCursor

    # -- events --
    def canvasPressEvent(self, e):
        if getattr(self, "item", None) is None:   # already cleaned up
            return
        pos = _evpos(e)
        shift = bool(e.modifiers() & Qt_ShiftModifier)
        i = self.item.corner_at(QtCore.QPointF(pos)) if self.on_scale_pct else None
        if i is not None:
            corners = self.item.corner_canvas_points()
            if shift:
                anchor = self.item.toCanvasCoordinates(self.item.center)
            else:
                anchor = corners[(i + 2) % 4]
            v = QtCore.QPointF(corners[i].x() - anchor.x(), corners[i].y() - anchor.y())
            vv = v.x() * v.x() + v.y() * v.y()
            if vv > 1e-6:
                c0 = self.item.center
                self._resize = {
                    "anchor": anchor, "v": v, "vv": vv,
                    "pct0": float(self.current_pct()) if self.current_pct else 100.0,
                    "centre0": QgsPointXY(c0.x(), c0.y()),
                    "anchor_map": None if shift else self._map_point(anchor),
                }
                self._grab = None
                return
        if shift:
            # park the shadow arrow on a feature the user can actually see,
            # rather than wherever the middle of the frame happens to fall
            p = self.toMapCoordinates(pos)
            self.item.set_shadow_anchor_from_map(p)
            self._grab = None
            return
        p = self.toMapCoordinates(pos)
        self._grab = (p.x() - self.item.center.x(), p.y() - self.item.center.y())

    def canvasMoveEvent(self, e):
        item = getattr(self, "item", None)
        if item is None:
            return
        pos = _evpos(e)
        if self._resize is not None:
            self._drag_corner(QtCore.QPointF(pos))
            return
        if self._grab is not None:
            p = self.toMapCoordinates(pos)
            item.set_center(QgsPointXY(p.x() - self._grab[0], p.y() - self._grab[1]))
            return
        # hovering: show a resize cursor over a handle
        i = item.corner_at(QtCore.QPointF(pos)) if self.on_scale_pct else None
        if i is None:
            self.canvas().setCursor(Qt_OpenHandCursor)
        else:
            corners = item.corner_canvas_points()
            self.canvas().setCursor(self._diag_cursor(corners[(i + 2) % 4], corners[i]))

    def _drag_corner(self, mouse):
        r = self._resize
        a, v = r["anchor"], r["v"]
        # project the mouse onto the anchor->corner diagonal: proportional
        t = ((mouse.x() - a.x()) * v.x() + (mouse.y() - a.y()) * v.y()) / r["vv"]
        pct = int(round(max(10.0, min(400.0, r["pct0"] * max(t, 0.01)))))
        self.on_scale_pct(pct)          # moves slider + spin, scales the item
        if r["anchor_map"] is not None:
            # keep the opposite corner fixed: the centre slides along the
            # diagonal by the scale actually applied (pct is a whole number)
            k = pct / r["pct0"]
            am, c0 = r["anchor_map"], r["centre0"]
            self.item.set_center(QgsPointXY(am.x() + (c0.x() - am.x()) * k,
                                            am.y() + (c0.y() - am.y()) * k))

    def canvasReleaseEvent(self, e):
        self._grab = None
        self._resize = None


class OverlaySession(QtWidgets.QDialog):
    """Non-modal control panel that owns the overlay item + move tool.
    Emits nothing special; read .applied_angle after it closes."""

    def __init__(self, iface, image_path, init_angle=0, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AutoGR Bridge - Overlay preview")
        self.setWindowIcon(QtGui.QIcon(ICON_PATH))
        self.setModal(False)
        # A tool window owned by the QGIS main window: it always stays above
        # QGIS (so it cannot get lost behind the map), but goes behind other
        # programs together with QGIS. No "stay on top", which would float it
        # over every application.
        self.setWindowFlags(self.windowFlags() | Qt_Tool)
        self.iface       = iface
        self.canvas      = iface.mapCanvas()
        self.applied_angle = None
        self._prev_tool  = self.canvas.mapTool()

        # The base image AutoGR-SIFT works with is north-up, but this overlay is
        # fitted against the (possibly rotated) QGIS display. So the rotation the
        # user reads here is screen-relative; the value stored in the bridge must
        # be north-relative:
        #     bridge_angle = overlay_angle - canvas_rotation
        # and the inverse when opening, so it round-trips.
        try:
            self._canvas_rot = float(self.canvas.rotation())
        except Exception:
            self._canvas_rot = 0.0
        slider_init = self._bound(float(init_angle) + self._canvas_rot)

        # loaded as a QImage first so the scan resolution stored in the file
        # is available for guessing the film format
        self._source_image = QtGui.QImage(image_path)
        px = QtGui.QPixmap.fromImage(self._source_image)
        self.item = OverlayCanvasItem(self.canvas, px)
        self.item.set_angle(slider_init)
        self.item.set_opacity(0.5)
        self.tool = OverlayMoveTool(self.canvas, self.item)
        self.canvas.setMapTool(self.tool)
        # corner handles drive the same scale slider (wired once it exists)
        self.tool.current_pct = lambda: self.sc_slider.value()

        info = QtWidgets.QLabel(
            "Drag on the map to move the image. Scale it with the slider or by "
            "dragging a corner handle (Shift: around the centre), rotate it, "
            "then apply the rotation to the bridge if it helps. With the "
            "shadow arrow on, Shift-click the map to start the arrow there.")
        info.setWordWrap(True)
        self.lbl_info = info
        if abs(self._canvas_rot) > 1e-6:
            note = QtWidgets.QLabel(
                f"Map is rotated {self._canvas_rot:g} deg - it is compensated "
                "when the rotation is applied to the bridge.")
            note.setStyleSheet("color: #a00;"); note.setWordWrap(True)
        else:
            note = None
        self.lbl_note = note

        self.op_slider = QtWidgets.QSlider(Qt_Horizontal)
        self.op_slider.setRange(0, 100); self.op_slider.setValue(50)
        self.sc_slider = QtWidgets.QSlider(Qt_Horizontal)
        self.sc_slider.setRange(10, 400); self.sc_slider.setValue(100)
        # Typed/stepped twin of the slider, like the rotation spin box.
        # Percent of the overlay's starting size on screen.
        self.sc_spin = QtWidgets.QSpinBox()
        self.sc_spin.setRange(10, 400); self.sc_spin.setValue(100)
        self.sc_spin.setSuffix(" %")
        self.rot_spin = QtWidgets.QSpinBox()
        self.rot_spin.setRange(-359, 359); self.rot_spin.setValue(int(round(slider_init)))
        self.rot_spin.setSuffix(" deg")

        form = QtWidgets.QFormLayout()
        form.addRow("Opacity:",  self.op_slider)
        self.lbl_scale_state = QtWidgets.QLabel("")
        self.lbl_scale_state.setStyleSheet("color: #a60; font-size: 10px;")
        hsc = QtWidgets.QHBoxLayout()
        hsc.addWidget(self.sc_spin)
        hsc.addWidget(self.sc_slider, 1)
        hsc.addWidget(self.lbl_scale_state)
        form.addRow("Scale (%):", self._wrapl(hsc))
        form.addRow("Rotation:", self.rot_spin)

        # Optionally zoom the map to what the overlay covers, so the base
        # snapshot taken on Run is limited to the area the image actually sits
        # on instead of the whole view.

        self.geom_box = self._build_geometry_box()

        # On by default: cropping the base snapshot to the placed image is the
        # point of applying, so it should not need to be discovered first.
        self.chk_crop = QtWidgets.QCheckBox(
            "Crop the base image to this footprint when applying")
        self.chk_crop.setToolTip(
            "The base snapshot sent to AutoGR-SIFT covers only the area this "
            "image sits on (plus a 5% margin) instead of the whole map view, "
            "however the map is panned or zoomed before you press Run. "
            "Scale and georeferencing are unaffected.")
        self.chk_crop.setChecked(
            str(_s("crop_to_footprint", "true")).lower() != "false")

        self.btn_apply = QtWidgets.QPushButton("Apply rotation to bridge && close")
        self.btn_close = QtWidgets.QPushButton("Close")
        hb = QtWidgets.QHBoxLayout()
        hb.addStretch(1); hb.addWidget(self.btn_apply); hb.addWidget(self.btn_close)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(info)
        if note is not None:
            lay.addWidget(note)
        self.summary = QtWidgets.QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setMaximumHeight(96)
        self.summary.setToolTip(
            "Live values for this placement. They keep updating as you drag, "
            "scale and rotate, so you can note them down and reuse them for "
            "other frames from the same mission.")
        f = self.summary.font(); f.setPointSize(max(7, f.pointSize() - 1))
        self.summary.setFont(f)
        self.btn_copy = QtWidgets.QPushButton("Copy values")
        self.btn_copy.setToolTip("Copy these values to the clipboard.")

        lay.addLayout(form)
        lay.addWidget(self.geom_box)
        lay.addWidget(self.chk_crop)
        lay.addWidget(QtWidgets.QLabel("<b>Current placement</b>"))
        lay.addWidget(self.summary)
        hcopy = QtWidgets.QHBoxLayout()
        hcopy.addStretch(1); hcopy.addWidget(self.btn_copy)
        lay.addLayout(hcopy)
        lay.addLayout(hb)

        self.op_slider.valueChanged.connect(
            lambda v: self._apply_to_item("set_opacity", v / 100.0))
        self.sc_slider.valueChanged.connect(
            lambda v: self._apply_to_item("set_scale_pct", v))
        self.sc_slider.valueChanged.connect(self.sc_spin.setValue)
        self.sc_spin.valueChanged.connect(self.sc_slider.setValue)
        # programmatic changes are made with signals blocked, so this only
        # sees the user (slider, box or corner handles)
        self.sc_slider.valueChanged.connect(
            lambda _v: setattr(self, "_scale_touched", True))
        self.tool.on_scale_pct = self._scale_from_handle
        self.rot_spin.valueChanged.connect(
            lambda v: self._apply_to_item("set_angle", v))
        self.btn_apply.clicked.connect(self._apply)
        self.btn_close.clicked.connect(self.reject)
        self.btn_copy.clicked.connect(self._copy_summary)
        for w in (self.op_slider, self.sc_slider):
            w.valueChanged.connect(lambda _v: self._update_summary())
        self.rot_spin.valueChanged.connect(lambda _v: self._update_summary())
        self._restore_geometry_inputs()
        self._recompute_geometry()

    # ---- optional photo geometry: scale from altitude, sun from date/time ----
    def _build_geometry_box(self):
        """Collapsible block of optional mission data.

        Three quantities describe the geometry -- film format, flying height
        and focal length -- and they are related by

            ground width = height x frame / focal

        so any two of them plus the size you have matched on screen give the
        third. Each therefore carries a "known" lock: locked values are taken
        as fact, the unlocked one can be worked out with its Guess button, and
        the scale slider stays free until all three are locked."""
        box = QtWidgets.QGroupBox("Photo / mission data (optional)")
        box.setCheckable(True)
        box.setToolTip(
            "Tick 'known' beside the values you are sure of. With two of "
            "format, height and focal length known, scale the photo onto the "
            "map and Guess the third. With all three known the size is "
            "computed and the scale slider locks.")

        def lock(tip):
            c = QtWidgets.QCheckBox("known")
            c.setToolTip(tip)
            c.setProperty("tip_known", tip)
            return c

        def guess(tip):
            b = QtWidgets.QPushButton("Guess")
            b.setMaximumWidth(58)
            b.setToolTip(tip)
            return b

        # ---- film format
        self.cmb_format = QtWidgets.QComboBox()
        for label, w, h in FILM_FORMATS:
            self.cmb_format.addItem(label, (w, h))
        self.cmb_format.addItem("Custom...", None)
        self.spin_fmt_w = QtWidgets.QDoubleSpinBox()
        self.spin_fmt_w.setRange(1.0, 200.0)
        self.spin_fmt_w.setSuffix(" cm")
        self.spin_fmt_h = QtWidgets.QDoubleSpinBox()
        self.spin_fmt_h.setRange(1.0, 200.0)
        self.spin_fmt_h.setSuffix(" cm")
        self.cmb_format.setToolTip(
            "Size of the WHOLE image in the file, as scanned. If the scan "
            "shows a border, datastrip or film edge around the picture, it "
            "must be included: a published frame size (e.g. 8.5 x 7 in) is "
            "only the picture area. Read from the file when it records its "
            "scan resolution ('As scanned'), otherwise use Custom... or Guess.")
        self.lock_fmt = lock("The size of the image as scanned is known -- "
                             "border included, if there is one.")
        self.btn_guess_format = guess(
            "Work the size of the image as scanned (border included) out of "
            "the placement: frame = ground width x focal / height. "
            "Needs height and focal length known.")
        hfmt = QtWidgets.QHBoxLayout()
        hfmt.addWidget(self.cmb_format, 1)
        hfmt.addWidget(self.spin_fmt_w)
        hfmt.addWidget(self.spin_fmt_h)
        hfmt.addWidget(self.lock_fmt)
        hfmt.addWidget(self.btn_guess_format)

        self.lbl_fmt_guess = QtWidgets.QLabel("")
        self.lbl_fmt_guess.setWordWrap(True)
        self.lbl_fmt_guess.setStyleSheet("color: #666; font-size: 10px;")

        # ---- flying height
        self.spin_alt = QtWidgets.QDoubleSpinBox()
        self.spin_alt.setRange(0.0, 200000.0)
        self.spin_alt.setDecimals(0)
        self.spin_alt.setSingleStep(500.0)
        self.cmb_alt_unit = QtWidgets.QComboBox()
        self.cmb_alt_unit.addItem("feet", FEET_TO_M)
        self.cmb_alt_unit.addItem("metres", 1.0)
        # switching unit converts the number (the height itself stays put);
        # the exact metres are kept so feet -> m -> feet does not drift
        self._alt_unit_m = FEET_TO_M
        self._alt_exact_m = None
        self.lock_alt = lock("The flying height is known. It should be height "
                             "above the GROUND, not above sea level. Recorded "
                             "heights are often an average or a target: this "
                             "is the value to untick, then Guess, when the "
                             "photo does not fit.")
        self.btn_guess_alt = guess(
            "Work the flying height out of the placement: "
            "height = ground width x focal / frame. "
            "Needs format and focal length known.")
        halt = QtWidgets.QHBoxLayout()
        halt.addWidget(self.spin_alt, 1)
        halt.addWidget(self.cmb_alt_unit)
        halt.addWidget(self.lock_alt)
        halt.addWidget(self.btn_guess_alt)

        # ---- focal length
        self.cmb_focal = QtWidgets.QComboBox()
        for label, mm in FOCAL_LENGTHS:
            self.cmb_focal.addItem(label, mm)
        self.cmb_focal.addItem("Custom...", -1.0)
        self.spin_focal = QtWidgets.QDoubleSpinBox()
        # the custom value is shown in the chosen unit (inches by default)
        self.cmb_focal_unit = QtWidgets.QComboBox()
        self.cmb_focal_unit.addItem("in", MM_PER_INCH)
        self.cmb_focal_unit.addItem("mm", 1.0)
        self._focal_unit_mm = MM_PER_INCH
        self._apply_focal_unit_range()
        self.spin_focal.setValue(6.0)
        self.lock_focal = lock("The focal length is known -- often printed on "
                               "the datastrip.")
        self.btn_guess_focal = guess(
            "Work the focal length out of the placement: "
            "focal = height x frame / ground width. "
            "Needs format and height known.")
        hfoc = QtWidgets.QHBoxLayout()
        hfoc.addWidget(self.cmb_focal, 1)
        hfoc.addWidget(self.spin_focal)
        hfoc.addWidget(self.cmb_focal_unit)
        hfoc.addWidget(self.lock_focal)
        hfoc.addWidget(self.btn_guess_focal)

        # ---- date / time (UTC) and shadows
        self.date_edit = QtWidgets.QDateEdit()
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setCalendarPopup(True)
        # The lowest date stands for "not entered": it shows as 'unknown', and
        # nothing that needs a date (sun from the time, Guess time, the time
        # zone suggestion) runs until a real one is set.
        self.date_edit.setMinimumDate(NO_DATE)
        self.date_edit.setSpecialValueText("unknown")
        self.date_edit.setDate(NO_DATE)
        self.date_edit.setToolTip(
            "Date of the sortie. Needed for the sun direction, Guess time and "
            "the time-zone suggestion. Set back to the earliest date to make "
            "it 'unknown' again.")
        try:
            # opening the calendar on an unknown date: show a useful month
            # instead of January 1900 (the page only, no date is picked)
            self.date_edit.calendarWidget().installEventFilter(self)
        except Exception as _exc:
            _ignored(_exc)
        self.time_edit = QtWidgets.QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QtCore.QTime(12, 0))
        self.time_edit.setToolTip(
            "Time as printed on the frame, in the time zone chosen next to it. "
            "Wartime sorties usually carry one time for every frame (roughly "
            "midway between take-off and landing), so it can be an hour or so "
            "off: leave the time unknown and Guess it from a shadow you can "
            "see on the ground -- Guess takes the solution nearest the time "
            "shown.")
        # time zone of the clock that stamped the frame
        self.cmb_tz = QtWidgets.QComboBox()
        for off in range(-12, 15):
            self.cmb_tz.addItem(_utc_label(off), off)
        self.cmb_tz.setCurrentIndex(self.cmb_tz.findData(0))
        self.cmb_tz.setToolTip(
            "Time zone of the clock that stamped the frame. Suggested from the "
            "date and place whenever the date is changed: in wartime Britain "
            "and on the continent usually UTC+2 in summer and UTC+1 in winter.")
        self.lock_time = lock("The time is known. Untick to aim the shadow "
                              "arrow by hand instead and Guess it.")
        self._guess_time_tip = (
            "Work the time out of the shadow direction set beside it, for "
            "the date and place above. Untick 'known' beside the time first: "
            "the direction then starts from the current time's shadow.")
        self.btn_guess_time = guess(self._guess_time_tip)
        hdt = QtWidgets.QHBoxLayout()
        hdt.addWidget(self.date_edit)
        hdt.addWidget(self.time_edit, 1)
        hdt.addWidget(self.cmb_tz)
        hdt.addWidget(self.lock_time)

        self.lbl_tz_hint = QtWidgets.QLabel("")
        self.lbl_tz_hint.setWordWrap(True)
        self.lbl_tz_hint.setStyleSheet("color: #666; font-size: 10px;")

        self.chk_sun = QtWidgets.QCheckBox("Show shadow arrow")
        self.spin_shadow = QtWidgets.QDoubleSpinBox()
        # signed, so a shadow pointing north-west is -58 deg rather than a
        # long trip round to 302; wraps past +-180
        self.spin_shadow.setRange(-180.0, 180.0)
        self.spin_shadow.setWrapping(True)
        self.spin_shadow.setDecimals(1)
        self.spin_shadow.setSuffix(" deg")
        self.spin_shadow.setToolTip(
            "Direction shadows fall, from true north: positive clockwise "
            "(east), negative anticlockwise (west). Turn it until the arrow "
            "lies along a shadow you can see, then press Guess for the time. "
            "Shift-click the map to start the arrow from that point.")
        self.chk_sun.setToolTip(
            "Draw the direction shadows fall at the date and time above. "
            "Shift-click the map to start the arrow from that point, e.g. the "
            "foot of a building whose shadow you can see.")
        # direction and Guess side by side: aim the arrow, then Guess the time
        self.lbl_shadow_dir = QtWidgets.QLabel("direction")
        hsun = QtWidgets.QHBoxLayout()
        hsun.addWidget(self.chk_sun, 1)
        hsun.addWidget(self.lbl_shadow_dir)
        hsun.addWidget(self.spin_shadow)
        hsun.addWidget(self.btn_guess_time)

        self.lbl_sun_hint = QtWidgets.QLabel(
            "<b>Shift-click</b> on the map to start the arrow from that point "
            "-- e.g. the foot of a building, tree or post whose shadow you "
            "can see -- then compare the arrow with that shadow.")
        self.lbl_sun_hint.setWordWrap(True)
        self.lbl_sun_hint.setTextFormat(Qt_RichText)
        self.lbl_sun_hint.setStyleSheet(
            "color: #8a5a00; background: #fff6dc; border: 1px solid #f0d58a; "
            "padding: 3px;")

        self.lbl_lock_hint = QtWidgets.QLabel(
            "The size is set by these values and the scale slider is locked. "
            "If the photo does not fit, untick <b>known</b> on the flying "
            "height -- recorded heights are averages or targets, while the "
            "focal length is fixed for the lens -- scale by hand from there, "
            "then press its <b>Guess</b>.")
        self.lbl_lock_hint.setWordWrap(True)
        self.lbl_lock_hint.setTextFormat(Qt_RichText)
        self.lbl_lock_hint.setStyleSheet("color: #a60; font-size: 10px;")
        self.lbl_lock_hint.setVisible(False)

        gform = QtWidgets.QFormLayout(box)
        gform.addRow(self.lbl_lock_hint)
        gform.addRow("Film format:", self._wrapl(hfmt))
        gform.addRow("", self.lbl_fmt_guess)
        gform.addRow("Flying height:", self._wrapl(halt))
        gform.addRow("Focal length:", self._wrapl(hfoc))
        gform.addRow("Date / time:", self._wrapl(hdt))
        gform.addRow("", self.lbl_tz_hint)
        gform.addRow("Shadows:", self._wrapl(hsun))
        gform.addRow("", self.lbl_sun_hint)

        for w in (self.cmb_format, self.cmb_focal):
            w.currentIndexChanged.connect(lambda _i: self._recompute_geometry())
        for w in (self.spin_fmt_w, self.spin_fmt_h, self.spin_alt,
                  self.spin_focal, self.spin_shadow):
            w.valueChanged.connect(lambda _v: self._recompute_geometry())
        for w in (self.lock_fmt, self.lock_alt, self.lock_focal,
                  self.lock_time, self.chk_sun):
            w.toggled.connect(lambda _b: self._recompute_geometry())
        self.date_edit.dateChanged.connect(self._on_date_changed)
        self.cmb_tz.currentIndexChanged.connect(lambda _i: self._recompute_geometry())
        self.time_edit.timeChanged.connect(lambda _t: self._recompute_geometry())
        self.cmb_focal_unit.currentIndexChanged.connect(self._on_focal_unit_changed)
        self.cmb_alt_unit.currentIndexChanged.connect(self._on_alt_unit_changed)
        self.spin_alt.valueChanged.connect(
            lambda v: setattr(self, "_alt_exact_m", float(v) * self._alt_unit_m))
        self.btn_guess_focal.clicked.connect(self._guess_focal)
        self.btn_guess_format.clicked.connect(self._guess_format)
        self.btn_guess_alt.clicked.connect(self._guess_altitude)
        self.btn_guess_time.clicked.connect(self._guess_time)
        self.lock_time.toggled.connect(self._on_time_lock_toggled)
        self._wire_guessed_reset()
        box.toggled.connect(self._on_geometry_toggled)
        return box

    @staticmethod
    def _wrapl(layout):
        w = QtWidgets.QWidget()
        layout.setContentsMargins(0, 0, 0, 0)
        w.setLayout(layout)
        return w

    def _on_geometry_toggled(self, on):
        """The checkable group box doubles as expand / collapse.

        Hiding the children is not enough on its own: the group box keeps its
        frame and layout margins and leaves an empty grey slab behind, so when
        collapsed the margins go to zero and the height is pinned to the title
        row."""
        lay = self.geom_box.layout()
        for i in range(lay.count()):
            it = lay.itemAt(i).widget()
            if it is not None:
                it.setVisible(on)
        self.geom_box.setFlat(not on)
        if on:
            lay.setContentsMargins(9, 14, 9, 9)
            lay.setSpacing(6)
            self.geom_box.setMaximumHeight(16777215)
        else:
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setSpacing(0)
            self.geom_box.setMaximumHeight(
                self.geom_box.fontMetrics().height() + 6)
        self._recompute_geometry()
        self.adjustSize()

    # ---- the three geometry quantities, each known only when locked --------
    def _film_size_cm(self):
        """(width_cm, height_cm), or None when not known."""
        if not (self.geom_box.isChecked() and self.lock_fmt.isChecked()):
            return None
        data = self.cmb_format.currentData()
        if data is None:
            return self.spin_fmt_w.value(), self.spin_fmt_h.value()
        return data

    def _frame_cm_for_image(self):
        """Known frame size as (across, down) the image in the file, or None.

        Formats are listed one way round (8.5 x 7 in, 18 x 24 cm) but a scan
        can be either way up, and the long side of the frame always lies along
        the long side of the image -- so it is matched to the pixels instead
        of trusting the order in the list."""
        size = self._film_size_cm()
        if not size:
            return None
        a, b = float(size[0]), float(size[1])
        item = getattr(self, "item", None)
        try:
            px_w, px_h = item._pixmap.width(), item._pixmap.height()
        except Exception:
            return a, b
        if (px_w >= px_h) != (a >= b):
            a, b = b, a
        return a, b

    def _focal_mm(self):
        if not (self.geom_box.isChecked() and self.lock_focal.isChecked()):
            return None
        data = self.cmb_focal.currentData()
        if data == -1.0:
            return self._custom_focal_mm()
        return data

    def _custom_focal_mm(self):
        return self.spin_focal.value() * self._focal_unit_mm

    def _set_custom_focal_mm(self, mm, block=True):
        v = float(mm) / self._focal_unit_mm
        if block:
            self._set_blocked(self.spin_focal, v)
        else:
            self.spin_focal.setValue(v)

    def _apply_focal_unit_range(self):
        if self._focal_unit_mm == 1.0:
            self.spin_focal.setDecimals(1); self.spin_focal.setSingleStep(1.0)
            self.spin_focal.setRange(5.0, 2000.0); self.spin_focal.setSuffix(" mm")
        else:
            self.spin_focal.setDecimals(2); self.spin_focal.setSingleStep(0.25)
            self.spin_focal.setRange(0.2, 80.0); self.spin_focal.setSuffix(" in")

    def _on_focal_unit_changed(self, _i):
        """Switching in <-> mm converts the custom value, it does not change it."""
        mm = self._custom_focal_mm()
        self._focal_unit_mm = float(self.cmb_focal_unit.currentData())
        self.spin_focal.blockSignals(True)
        self._apply_focal_unit_range()
        self.spin_focal.setValue(mm / self._focal_unit_mm)
        self.spin_focal.blockSignals(False)
        self._recompute_geometry()

    def _altitude_m(self):
        if not (self.geom_box.isChecked() and self.lock_alt.isChecked()):
            return None
        v = self._alt_raw_m()
        return v if v > 0 else None

    def _alt_raw_m(self):
        """Height in metres as entered, whether or not it is ticked known.
        Uses the exact value while the box only shows a rounding of it (after
        a unit change or a Guess), so the overlay does not shift by a hair."""
        shown = self.spin_alt.value()
        ex = getattr(self, "_alt_exact_m", None)
        if ex is not None:
            step = 0.5 / (10 ** self.spin_alt.decimals()) + 1e-9
            if abs(shown - ex / self._alt_unit_m) <= step:
                return ex
        return shown * self._alt_unit_m

    def _on_alt_unit_changed(self, _i):
        """feet <-> metres converts the number; the height does not change."""
        h = self._alt_raw_m()
        self._alt_unit_m = float(self.cmb_alt_unit.currentData())
        self.spin_alt.setSingleStep(500.0 if self._alt_unit_m != 1.0 else 100.0)
        self._set_blocked(self.spin_alt, h / self._alt_unit_m)
        self._alt_exact_m = h
        self._recompute_geometry()

    def _update_input_visibility(self):
        on = self.geom_box.isChecked()
        custom_fmt = self.cmb_format.currentData() is None
        self.spin_fmt_w.setVisible(on and custom_fmt)
        self.spin_fmt_h.setVisible(on and custom_fmt)
        custom_focal = on and self.cmb_focal.currentData() == -1.0
        self.spin_focal.setVisible(custom_focal)
        self.cmb_focal_unit.setVisible(custom_focal)
        # the manual arrow only means anything while the time is unlocked
        self.spin_shadow.setEnabled(on and not self.lock_time.isChecked())
        self.lbl_shadow_dir.setEnabled(on and not self.lock_time.isChecked())
        self.time_edit.setEnabled(on and self.lock_time.isChecked())

    def _map_units_are_metres(self):
        try:
            u = self.canvas.mapSettings().destinationCrs().mapUnits()
            try:
                metres = Qgis.DistanceUnit.Meters          # QGIS >= 3.30 / 4
            except AttributeError:
                from qgis.core import QgsUnitTypes         # older QGIS 3
                metres = QgsUnitTypes.DistanceMeters
            return u == metres
        except Exception:
            return True

    def _ground_m_per_map_unit(self):
        """True ground metres per map unit around the overlay, from an
        ellipsoidal measurement. Map units that are called metres are not
        always ground metres: in Web Mercator (EPSG:3857, the CRS of most
        online basemaps) one map unit is only cos(latitude) of a metre --
        0.61 m at 52 N -- so taking them at face value makes every photo look
        1.6x bigger than the numbers say. UTM and national grids are within a
        fraction of a percent of 1. Returns 1.0 when it cannot be measured."""
        try:
            from qgis.core import QgsDistanceArea, QgsProject
            item = getattr(self, "item", None)
            if item is None:
                return 1.0
            crs = self.canvas.mapSettings().destinationCrs()
            proj = QgsProject.instance()
            da = QgsDistanceArea()
            da.setSourceCrs(crs, proj.transformContext())
            ell = proj.ellipsoid()
            if not ell or str(ell).upper() == "NONE":
                ell = "EPSG:7030"                  # WGS 84
            da.setEllipsoid(ell)
            c = item.center
            half = max(1.0, item.gsd * max(1, item._pixmap.width())) / 2.0
            ew = da.measureLine(QgsPointXY(c.x() - half, c.y()),
                                QgsPointXY(c.x() + half, c.y()))
            ns = da.measureLine(QgsPointXY(c.x(), c.y() - half),
                                QgsPointXY(c.x(), c.y() + half))
            f = (ew + ns) / (4.0 * half)
            if 0.05 < f < 20.0:
                return f
        except Exception as _exc:
            _ignored(_exc)
        return 1.0

    def _computed_gsd(self):
        """(map units per image pixel, note) or (None, reason)."""
        item = getattr(self, "item", None)
        if item is None:
            return None, ""
        if not self.geom_box.isChecked():
            return None, ""
        if not self._map_units_are_metres():
            return None, "map units are not metres, scale not applied"
        size = self._film_size_cm()
        alt = self._altitude_m()
        focal = self._focal_mm()
        missing = [n for n, v in (("film format", size), ("height", alt),
                                  ("focal length", focal)) if not v]
        if missing:
            if len(missing) == 1:
                return None, ("%s not known -- match the photo by hand, then "
                              "Guess it" % missing[0])
            return None, "known: " + (", ".join(
                n for n, v in (("format", size), ("height", alt),
                               ("focal", focal)) if v) or "nothing")
        size = self._frame_cm_for_image()
        res = photo_ground_size(size[0], size[1], alt, focal)
        if res is None:
            return None, "invalid height or focal length"
        scale, gw, gh = res
        self._photo_scale = scale
        k = self._ground_m_per_map_unit()
        return (gw / k) / max(1, item._pixmap.width()), (
            "1:%.0f, ground %.0f x %.0f m" % (scale, gw, gh))

    def _fit_hints(self):
        """Give the wrapped hint lines the height their text needs. Inside the
        form layout Qt does not pass height-for-width through (and ignores the
        style-sheet padding), so a two-line hint would otherwise be cut short.
        The text is measured at the label's real width, padding included."""
        changed = False
        for name in ("lbl_info", "lbl_note", "lbl_lock_hint", "lbl_fmt_guess",
                     "lbl_tz_hint", "lbl_sun_hint"):
            lbl = getattr(self, name, None)
            if lbl is None:
                continue
            try:
                need = 0
                if lbl.text():
                    cw = lbl.contentsRect().width()
                    if cw < 80:
                        cw = 380
                    doc = QtGui.QTextDocument()
                    doc.setDocumentMargin(0)
                    doc.setDefaultFont(lbl.font())
                    if lbl.textFormat() == Qt_RichText:
                        doc.setHtml(lbl.text())
                    else:
                        doc.setPlainText(lbl.text())
                    doc.setTextWidth(cw)
                    frame = max(0, lbl.height() - lbl.contentsRect().height())
                    need = int(doc.size().height() + 0.999) + frame + 1
                if lbl.minimumHeight() != need:
                    lbl.setMinimumHeight(need)
                    changed = True
            except Exception as _exc:
                _ignored(_exc)
        if changed and not getattr(self, "_relayout_queued", False):
            self._relayout_queued = True
            QtCore.QTimer.singleShot(0, self._relayout)

    def _relayout(self):
        """Let the mission-data box grow to the hints' new height."""
        self._relayout_queued = False
        try:
            self.geom_box.layout().invalidate()
            self.geom_box.updateGeometry()
            self.layout().invalidate()
            self.layout().activate()
            need = self.layout().minimumSize().height()
            if self.height() < need:
                self.resize(self.width(), need)
        except Exception as _exc:
            _ignored(_exc)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_hints()

    # ---- frame time zone ---------------------------------------------------
    def _tz_offset(self):
        try:
            return int(self.cmb_tz.currentData())
        except Exception:
            return 0

    def _date_known(self):
        return self.date_edit.date() != NO_DATE

    def eventFilter(self, obj, ev):
        try:
            if (ev.type() == QEvent_Show and not self._date_known()
                    and obj is self.date_edit.calendarWidget()):
                last = QtCore.QDate.fromString(
                    str(_s("geom_last_date", "") or ""), "yyyy-MM-dd")
                if not last.isValid():
                    last = QtCore.QDate(1944, 6, 1)
                obj.setCurrentPage(last.year(), last.month())
        except Exception as _exc:
            _ignored(_exc)
        return super().eventFilter(obj, ev)

    def _tz_suggestion(self):
        ll = self._centre_lonlat()
        d = self.date_edit.date()
        if not self._date_known():
            return None, "enter the date to get a time-zone suggestion"
        if ll is None:
            return None, "position unavailable: set the time zone by hand"
        return suggest_utc_offset(ll[1], ll[0], d.year(), d.month(), d.day())

    def _apply_tz_suggestion(self):
        off, _why = self._tz_suggestion()
        if off is not None:
            i = self.cmb_tz.findData(off)
            if i >= 0:
                self._set_blocked(self.cmb_tz, i)

    @staticmethod
    def _signed_deg(a):
        """0..360 -> -180..180 (north 0, east +, west -)."""
        return ((float(a) + 180.0) % 360.0) - 180.0

    def _on_time_lock_toggled(self, locked):
        """Unticking the time hands the arrow over to the direction box: it
        starts where the arrow already points for the current time, not at
        0 deg (due north, where no shadow falls in Europe)."""
        if locked:
            return
        az = getattr(self, "_last_shadow_az", None)
        if az is None and self._date_known():
            ll = self._centre_lonlat()
            if ll is not None:
                d = self.date_edit.date(); t = self.time_edit.time()
                try:
                    sun, elev = solar_azimuth(ll[1], ll[0], d.year(), d.month(),
                                              d.day(), t.hour(), t.minute(),
                                              float(self._tz_offset()))
                    if elev > 0:
                        az = (sun + 180.0) % 360.0
                except Exception:
                    az = None
        if az is not None:
            self._set_blocked(self.spin_shadow, self._signed_deg(az))
        self._recompute_geometry()

    def _on_date_changed(self, _d):
        """A new date proposes the clock the frame was most likely stamped in
        (e.g. double summer time in 1944); the user can still change it."""
        self._apply_tz_suggestion()
        self._recompute_geometry()

    def _update_tz_hint(self):
        try:
            off, why = self._tz_suggestion()
            if off is None:
                text = why
            elif off == self._tz_offset():
                text = "Suggested -- " + why + "."
            else:
                text = ("Set by hand. Suggestion was " + why + ".")
            self.lbl_tz_hint.setText(text)
        except Exception as _exc:
            _ignored(_exc)

    def _time_utc_minutes(self):
        t = self.time_edit.time()
        return (t.hour() * 60 + t.minute() - 60 * self._tz_offset()) % 1440

    # ---- sun ---------------------------------------------------------------
    def _centre_lonlat(self):
        """Overlay centre as (lon, lat) in WGS84, or None."""
        try:
            from qgis.core import (QgsCoordinateReferenceSystem,
                                   QgsCoordinateTransform, QgsProject)
            item = getattr(self, "item", None)
            if item is None:
                return None
            src = self.canvas.mapSettings().destinationCrs()
            dst = QgsCoordinateReferenceSystem("EPSG:4326")
            tr = QgsCoordinateTransform(src, dst, QgsProject.instance())
            pt = tr.transform(item.center)
            return pt.x(), pt.y()
        except Exception:
            return None

    def _computed_shadow_azimuth(self):
        """(azimuth, note) for the arrow, or (None, reason)."""
        if not (self.geom_box.isChecked() and self.chk_sun.isChecked()):
            return None, ""
        if not self.lock_time.isChecked():
            return self.spin_shadow.value() % 360.0, "aimed by hand"
        if not self._date_known():
            return None, "date unknown"
        ll = self._centre_lonlat()
        if ll is None:
            return None, "position unavailable"
        d = self.date_edit.date()
        t = self.time_edit.time()
        try:
            az, elev = solar_azimuth(ll[1], ll[0], d.year(), d.month(),
                                     d.day(), t.hour(), t.minute(),
                                     float(self._tz_offset()))
        except Exception:
            return None, "solar calculation failed"
        if elev <= 0:
            return None, "sun below the horizon at that time"
        self._sun_elev = elev
        self._last_shadow_az = (az + 180.0) % 360.0
        return self._last_shadow_az, "sun az %.0f deg, elev %.0f deg" % (az, elev)

    # ---- guesses: any two knowns give the third ----------------------------
    def _placement_ground_width(self):
        item = getattr(self, "item", None)
        if item is None:
            return None
        gw = item.gsd * max(1, item._pixmap.width()) * self._ground_m_per_map_unit()
        return gw if gw > 0 else None

    def _guess_precheck(self, need):
        if not self._map_units_are_metres():
            self._warn_geometry("Map units are not metres, so nothing can be "
                                "derived from the placement.")
            return None
        missing = [n for n, v in need if not v]
        if missing:
            self._warn_geometry(
                "Tick 'known' for " + " and ".join(missing)
                + " first -- two of the three are needed to work out the third.")
            return None
        return self._placement_ground_width()

    def _guess_focal(self):
        """focal = height x frame / ground width."""
        size, alt = self._frame_cm_for_image(), self._altitude_m()
        gw = self._guess_precheck([("film format", size), ("height", alt)])
        if gw is None:
            return
        focal_mm = alt * (size[0] / 100.0) / gw * 1000.0
        if not (5.0 <= focal_mm <= 2000.0):
            self._warn_geometry(
                "That placement implies a %s lens, which is not "
                "plausible -- check the height and the film format."
                % _fmt_focal(focal_mm))
            return
        self._set_blocked(self.cmb_focal, self.cmb_focal.findText("Custom..."))
        self._set_custom_focal_mm(focal_mm)
        self.lock_focal.blockSignals(True)
        self.lock_focal.setChecked(True)
        self.lock_focal.blockSignals(False)
        self._mark_guessed(self.lock_focal)
        _log("Overlay: focal guessed from placement -> %.1f mm "
             "(height %.0f m, frame %.1f cm, ground %.0f m)"
             % (focal_mm, alt, size[0], gw))
        self._recompute_geometry()
        self._warn_geometry("Focal length set to %s from the current "
                            "placement." % _fmt_focal(focal_mm), warning=False)

    def _guess_altitude(self):
        """height = ground width x focal / frame."""
        size, focal = self._frame_cm_for_image(), self._focal_mm()
        gw = self._guess_precheck([("film format", size), ("focal length", focal)])
        if gw is None:
            return
        alt_m = gw * (focal / 1000.0) / (size[0] / 100.0)
        if not (10.0 <= alt_m <= 60000.0):
            self._warn_geometry(
                "That placement implies a height of %.0f m, which is not "
                "plausible -- check the format and the focal length." % alt_m)
            return
        unit = self._alt_unit_m
        self._set_blocked(self.spin_alt, alt_m / unit)
        self._alt_exact_m = alt_m
        self.lock_alt.blockSignals(True)
        self.lock_alt.setChecked(True)
        self.lock_alt.blockSignals(False)
        self._mark_guessed(self.lock_alt)
        _log("Overlay: height guessed from placement -> %.0f m "
             "(frame %.1f cm, focal %.0f mm, ground %.0f m)"
             % (alt_m, size[0], focal, gw))
        self._recompute_geometry()
        self._warn_geometry(
            "Flying height set to %.0f m (%.0f %s) from the current placement."
            % (alt_m, alt_m / unit, self.cmb_alt_unit.currentText()),
            warning=False)

    def _guess_format(self):
        """frame = ground width x focal / height.

        This yields the EFFECTIVE frame in the file, border and crop included,
        which is what the scale arithmetic needs -- a scan with a white
        surround behaves like a larger frame, a cropped one like a smaller."""
        alt, focal = self._altitude_m(), self._focal_mm()
        gw = self._guess_precheck([("height", alt), ("focal length", focal)])
        if gw is None:
            return
        item = self.item
        px_w = max(1, item._pixmap.width())
        px_h = max(1, item._pixmap.height())
        w_cm = gw * (float(focal) / 1000.0) / alt * 100.0
        h_cm = w_cm * (float(px_h) / float(px_w))
        if not (1.0 <= w_cm <= 200.0):
            self._warn_geometry(
                "That placement implies a %.1f cm frame, which is not "
                "plausible -- check the height and the focal length." % w_cm)
            return
        near, near_err = None, None
        for i, (_label, fw, fh) in enumerate(FILM_FORMATS):
            for a, b in ((fw, fh), (fh, fw)):     # either way up
                err = max(abs(w_cm - a) / a, abs(h_cm - b) / b)
                if near_err is None or err < near_err:
                    near, near_err = i, err
        if near is not None and near_err <= 0.05:
            self._set_blocked(self.cmb_format, near)
            msg = ("Frame measures %.1f x %.1f cm -- matched to %s."
                   % (w_cm, h_cm, FILM_FORMATS[near][0]))
        else:
            self._set_blocked(self.cmb_format,
                              self.cmb_format.findText("Custom..."))
            self._set_blocked(self.spin_fmt_w, w_cm)
            self._set_blocked(self.spin_fmt_h, h_cm)
            hint = ""
            if near is not None:
                nearest = FILM_FORMATS[near]
                what = ("border around the frame" if w_cm > nearest[1]
                        else "crop")
                hint = (" Nearest standard size is %s, so the scan probably "
                        "has a %s." % (nearest[0], what))
            msg = ("Frame measures %.1f x %.1f cm, set as a custom size.%s"
                   % (w_cm, h_cm, hint))
        self.lock_fmt.blockSignals(True)
        self.lock_fmt.setChecked(True)
        self.lock_fmt.blockSignals(False)
        self._mark_guessed(self.lock_fmt)
        _log("Overlay: format guessed from placement -> %.2f x %.2f cm "
             "(height %.0f m, focal %.0f mm, ground %.0f m)"
             % (w_cm, h_cm, alt, focal, gw))
        self._recompute_geometry()
        self._warn_geometry(msg, warning=False)

    def _guess_time(self):
        """Solve for the UTC time that puts the sun opposite the aimed arrow.

        Azimuth alone is ambiguous -- the sun passes the same bearing once in
        the morning and once in the afternoon -- so both solutions are
        reported and the nearer one to the time already shown is taken."""
        if self.lock_time.isChecked():
            self._warn_geometry("Untick 'known' beside the time first, then "
                                "aim the arrow along a shadow you can see.")
            return
        if not self._date_known():
            self._warn_geometry("Enter the date first: the time can only be "
                                "worked out for a given day.")
            return
        ll = self._centre_lonlat()
        if ll is None:
            self._warn_geometry("Overlay position unavailable.")
            return
        want_sun = (self.spin_shadow.value() + 180.0) % 360.0
        d = self.date_edit.date()
        lat, lon = ll[1], ll[0]
        best = []
        for minute in range(0, 24 * 60):
            az, elev = solar_azimuth(lat, lon, d.year(), d.month(), d.day(),
                                     minute // 60, minute % 60, 0.0)
            if elev <= 0:
                continue
            diff = abs((az - want_sun + 180.0) % 360.0 - 180.0)
            best.append((diff, minute, elev))
        if not best:
            self._warn_geometry("The sun is never above the horizon there on "
                                "that date.")
            return
        best.sort()
        # the two branches are the best match either side of solar noon
        first = best[0]
        second = None
        for cand in best[1:]:
            if abs(cand[1] - first[1]) > 60:
                second = cand
                break
        cur_min = self._time_utc_minutes()
        options = [first] + ([second] if second else [])
        pick = min(options, key=lambda c: abs(c[1] - cur_min))
        off = self._tz_offset()
        tzl = _utc_label(off)

        def local(mins):
            mins = (mins + 60 * off) % 1440
            return mins // 60, mins % 60
        if pick[0] > 2.0:
            self._warn_geometry(
                "No time on that date puts the sun at %.0f deg (closest is "
                "%.0f deg off) -- check the date and the arrow."
                % (want_sun, pick[0]))
            return
        self._set_blocked(self.time_edit, QtCore.QTime(*local(pick[1])))
        self.lock_time.blockSignals(True)
        self.lock_time.setChecked(True)
        self.lock_time.blockSignals(False)
        self._mark_guessed(self.lock_time)
        others = ""
        if second is not None:
            other = second if pick is first else first
            others = (" The other possibility is %02d:%02d %s (sun elevation "
                      "%.0f deg)." % (local(other[1]) + (tzl, other[2])))
        _log("Overlay: UTC time guessed from shadow azimuth %.1f deg -> "
             "%02d:%02d (sun elev %.0f deg)"
             % (self.spin_shadow.value(), pick[1] // 60, pick[1] % 60, pick[2]))
        self._recompute_geometry()
        utc_note = ("" if not off else
                    " = %02d:%02d UTC" % (pick[1] // 60, pick[1] % 60))
        self._warn_geometry(
            "Time set to %02d:%02d %s%s, sun elevation %.0f deg.%s"
            % (local(pick[1]) + (tzl, utc_note, pick[2], others)),
            warning=False)

    @staticmethod
    def _set_blocked(widget, value):
        widget.blockSignals(True)
        try:
            if isinstance(widget, QtWidgets.QComboBox):
                widget.setCurrentIndex(value)
            elif isinstance(widget, QtWidgets.QTimeEdit):
                widget.setTime(value)
            else:
                widget.setValue(value)
        finally:
            widget.blockSignals(False)

    def _warn_geometry(self, text, warning=True):
        try:
            self.iface.messageBar().pushMessage(
                "AutoGR Bridge", text,
                level=LVL_WARN if warning else LVL_INFO, duration=6)
        except Exception as _exc:
            _ignored(_exc)
        _log("Overlay geometry: " + text)

    _GUESSED_TIP = ("Guessed from the placement or the shadow. Type a value "
                    "or change the selection to make it known.")

    def _mark_guessed(self, chk, guessed=True):
        """Show whether a locked value was typed ('known') or worked out by a
        Guess button ('guessed'). Either way it is used in the calculation."""
        try:
            chk.setText("guessed" if guessed else "known")
            chk.setToolTip(self._GUESSED_TIP if guessed
                           else str(chk.property("tip_known") or ""))
            chk.setProperty("guessed", bool(guessed))
        except Exception as _exc:
            _ignored(_exc)

    def _is_guessed(self, chk):
        return bool(chk.property("guessed"))

    def _wire_guessed_reset(self):
        """Editing a value by hand turns 'guessed' back into 'known'. Guesses
        and suggestions set their values with signals blocked, so they do
        not trigger this."""
        pairs = (
            (self.lock_fmt,   [self.cmb_format.currentIndexChanged,
                               self.spin_fmt_w.valueChanged,
                               self.spin_fmt_h.valueChanged]),
            (self.lock_alt,   [self.spin_alt.valueChanged]),
            (self.lock_focal, [self.cmb_focal.currentIndexChanged,
                               self.spin_focal.valueChanged]),
            (self.lock_time,  [self.time_edit.timeChanged,
                               self.cmb_tz.currentIndexChanged]),
        )
        for chk, sigs in pairs:
            for sig in sigs:
                sig.connect(lambda *_a, c=chk: self._mark_guessed(c, False))
            chk.toggled.connect(lambda _b, c=chk: self._mark_guessed(c, False))

    def _report_size_mismatch(self, manual_pct, pct):
        """The numbers now set the size and it differs from the hand-made
        placement: say by how much and what usually causes it."""
        diff = (manual_pct / pct - 1.0) * 100.0
        self._warn_geometry(
            "Size now computed from format, height and focal length: %.0f%% "
            "of the reference (your placement was %.0f%%, %+.0f%%). If the "
            "photo matched at "
            "your size, the numbers do not describe this scan: a border or "
            "datastrip around the frame makes the image larger than the "
            "format (untick the format and Guess it to measure the frame as "
            "scanned), and the height must be above the ground, not sea "
            "level." % (pct, manual_pct, diff))

    # ---- recompute / freeze ------------------------------------------------
    def _recompute_geometry(self):
        self._photo_scale = None
        self._sun_elev = None
        self._update_input_visibility()
        gsd, why = self._computed_gsd()
        self._gsd_note = why
        item = getattr(self, "item", None)
        if item is not None:
            if gsd and gsd > 0:
                # The entered numbers now define the size, so the slider is
                # locked: leaving it free would silently multiply a figure the
                # user believes is exact.
                #
                # The % is relative to a reference size. If the image had been
                # scaled by hand, the reference stays put so the % shows how
                # the computed size compares with that placement (and a
                # mismatch is reported). Otherwise -- or if the computed size
                # is beyond the slider's range, e.g. after zooming far in or
                # out -- the photo-data size itself becomes the 100% reference.
                pct = gsd / max(1e-12, item._base_gsd) * 100.0
                # only a real hand placement, not the first computation or
                # values being reloaded when the window opens
                was_manual = (getattr(self, "_scale_frozen", None) is False
                              and not getattr(self, "_restoring", False))
                touched = getattr(self, "_scale_touched", False)
                manual_pct = float(self.sc_slider.value())
                if was_manual and touched and 10.0 <= pct <= 400.0:
                    shown = int(round(pct))
                    item.set_scale_pct(pct)
                    if manual_pct and abs(pct / manual_pct - 1.0) > 0.03:
                        self._report_size_mismatch(manual_pct, pct)
                else:
                    item.set_base_gsd(gsd)
                    item.set_scale_pct(100)
                    shown = 100
                    if was_manual and touched and manual_pct:
                        self._report_size_mismatch(manual_pct, pct)
                self._set_blocked(self.sc_slider, shown)
                self._set_blocked(self.sc_spin, shown)
                self._scale_touched = False
            az, note = self._computed_shadow_azimuth()
            self._sun_note = note
            item.set_shadow_azimuth(az)
            if az is not None and self.lock_time.isChecked():
                # show (greyed) where the arrow points for the known time
                self._set_blocked(self.spin_shadow, self._signed_deg(az))
        frozen_now = bool(gsd and gsd > 0)
        if (getattr(self, "_scale_frozen", None) is True and not frozen_now
                and item is not None):
            # Just unlocked: carry on from the photo-data size, with the full
            # 10-400% range around it, instead of wherever the old reference
            # left the slider (possibly pinned at its 400% end).
            try:
                item.set_base_gsd(item.gsd)
                item.set_scale_pct(100)
            except Exception as _exc:
                _ignored(_exc)
            self._set_blocked(self.sc_slider, 100)
            self._set_blocked(self.sc_spin, 100)
            self._scale_touched = False
            if (not getattr(self, "_restoring", False)
                    and self.geom_box.isChecked()):
                self._warn_geometry(
                    "Scale unlocked: 100% is now the size from the photo data. "
                    "Scale to fit, then press Guess beside the value you "
                    "unticked to see what it should have been.", warning=False)
        self._set_scale_frozen(frozen_now)
        self._update_guess_buttons()
        self._update_tz_hint()
        self._fit_hints()
        self._update_summary()

    def _update_guess_buttons(self):
        on = self.geom_box.isChecked()
        size = self._film_size_cm() is not None
        alt = self._altitude_m() is not None
        focal = self._focal_mm() is not None
        # each Guess needs the other two locked, and itself unlocked
        self.btn_guess_format.setEnabled(on and alt and focal and not size)
        self.btn_guess_alt.setEnabled(on and size and focal and not alt)
        self.btn_guess_focal.setEnabled(on and size and alt and not focal)
        dated = self._date_known()
        self.btn_guess_time.setEnabled(
            on and dated and self.chk_sun.isChecked()
            and not self.lock_time.isChecked())
        self.btn_guess_time.setToolTip(
            self._guess_time_tip if dated else
            "Enter the date first: the time can only be worked out for a "
            "given day.")

    def _scale_from_handle(self, pct):
        """A corner handle was dragged: move the slider, which scales the
        item, syncs the spin box and refreshes the summary."""
        if getattr(self, "_scale_frozen", False):
            return
        self.sc_slider.setValue(int(pct))

    def _set_scale_frozen(self, frozen):
        """Grey out the scale slider while the size comes from the entered
        numbers, and say why on hover."""
        self._scale_frozen = frozen
        item = getattr(self, "item", None)
        if item is not None:
            try:
                item.set_handles_visible(not frozen)
            except Exception as _exc:
                _ignored(_exc)
        self.sc_slider.setEnabled(not frozen)
        self.sc_spin.setEnabled(not frozen)
        if frozen:
            tip = ("Locked: format, height and focal length are all ticked "
                   "'known', so the size is computed from them. To adjust it "
                   "by hand, untick 'known' on the flying height (a recorded "
                   "height is an average or a target; the focal length is "
                   "fixed for the lens): the slider is freed with 100% = the "
                   "photo-data size. Scale to fit, then press the height's "
                   "Guess to see what it really was.")
        else:
            tip = ("Scale the overlay by hand. Tick 'known' beside format, "
                   "height and focal length to have this computed instead.")
        self.sc_slider.setToolTip(tip)
        self.sc_spin.setToolTip(tip)
        try:
            self.lbl_scale_state.setText(
                "locked by photo data" if frozen else "")
            self.lbl_scale_state.setToolTip(tip)
            self.lbl_lock_hint.setVisible(bool(frozen)
                                          and self.geom_box.isChecked())
        except Exception as _exc:
            _ignored(_exc)

    # ---- persistence -------------------------------------------------------
    def _restore_geometry_inputs(self):
        """Mission data is remembered between frames -- reusing it across a
        mission is the whole point of entering it."""
        self._restoring = True
        try:
            self.geom_box.setChecked(
                str(_s("geom_on", "false")).lower() == "true")
            i = self.cmb_format.findText(str(_s("geom_format", "24 x 24 cm")))
            self.cmb_format.setCurrentIndex(i if i >= 0 else 0)
            self.spin_fmt_w.setValue(float(_s("geom_fmt_w", 24.0) or 24.0))
            self.spin_fmt_h.setValue(float(_s("geom_fmt_h", 24.0) or 24.0))
            ui = int(_s("geom_alt_unit", 0) or 0)
            if 0 <= ui < self.cmb_alt_unit.count():
                self._set_blocked(self.cmb_alt_unit, ui)
            self._alt_unit_m = float(self.cmb_alt_unit.currentData())
            self.spin_alt.setSingleStep(500.0 if self._alt_unit_m != 1.0 else 100.0)
            self.spin_alt.setValue(float(_s("geom_alt", 0.0) or 0.0))
            self._alt_exact_m = self.spin_alt.value() * self._alt_unit_m
            j = self.cmb_focal.findText(
                _focal_label_from_saved(_s("geom_focal", DEFAULT_FOCAL_LABEL)))
            self.cmb_focal.setCurrentIndex(
                j if j >= 0 else self.cmb_focal.findText(DEFAULT_FOCAL_LABEL))
            # unit first (inches unless mm was chosen before), then the value
            # remembered in mm so it survives a unit change
            self.cmb_focal_unit.setCurrentIndex(
                int(_s("geom_focal_unit", 0) or 0))
            self._set_custom_focal_mm(
                float(_s("geom_focal_mm", 6.0 * MM_PER_INCH) or 6.0 * MM_PER_INCH),
                block=False)
            self.chk_sun.setChecked(
                str(_s("geom_sun", "false")).lower() == "true")
            self.spin_shadow.setValue(
                self._signed_deg(float(_s("geom_shadow", 0.0) or 0.0)))
            for chk, key in ((self.lock_fmt, "lock_fmt"),
                             (self.lock_alt, "lock_alt"),
                             (self.lock_focal, "lock_focal"),
                             (self.lock_time, "lock_time")):
                chk.setChecked(str(_s(key, "false")).lower() == "true")
                self._mark_guessed(
                    chk, str(_s(key + "_guessed", "false")).lower() == "true")
            ds = str(_s("geom_date", "") or "")
            dd = QtCore.QDate.fromString(ds, "yyyy-MM-dd") if ds else NO_DATE
            self.date_edit.setDate(dd if dd.isValid() else NO_DATE)
            ts = str(_s("geom_time", "") or "")
            if ts:
                self._set_blocked(self.time_edit, QtCore.QTime.fromString(ts, "HH:mm"))
            # time zone last: setting the date above proposed one already
            tz = str(_s("geom_tz", "") or "")
            if tz.lstrip("+-").isdigit():
                i = self.cmb_tz.findData(int(tz))
                if i >= 0:
                    self._set_blocked(self.cmb_tz, i)
            else:
                self._apply_tz_suggestion()
        except Exception as _exc:
            _ignored(_exc)
        finally:
            self._restoring = False
        self._apply_format_guess()
        self._on_geometry_toggled(self.geom_box.isChecked())

    def _apply_format_guess(self):
        """Preselect the film format the image itself points at.

        A resolution-backed guess describes THIS file, so it beats the format
        remembered from the last frame. A shape-only guess does not, and is
        offered as a hint so a mission setting is not silently overwritten."""
        item = getattr(self, "item", None)
        if item is None:
            return
        px = item._pixmap
        dpi_x = dpi_y = 0.0
        try:
            img = getattr(self, "_source_image", None)
            if img is not None:
                dpm_x, dpm_y = img.dotsPerMeterX(), img.dotsPerMeterY()
                dpi_x = dpm_x * CM_PER_INCH / 100.0 if dpm_x else 0.0
                dpi_y = dpm_y * CM_PER_INCH / 100.0 if dpm_y else 0.0
        except Exception:
            dpi_x = dpi_y = 0.0
        scan = scan_size_cm(px.width(), px.height(), dpi_x, dpi_y)
        if scan is not None:
            # the file says how big it is: use that, border and all
            w, h, dpi = scan
            label = "As scanned: %.1f x %.1f cm" % (w, h)
            j = self.cmb_format.findText("Custom...")
            old = getattr(self, "_scan_item_label", None)
            if old is not None:
                k = self.cmb_format.findText(old)
                if k >= 0:
                    self.cmb_format.removeItem(k)
                    j = self.cmb_format.findText("Custom...")
            self.cmb_format.insertItem(j, label, (w, h))
            self._scan_item_label = label
            self._set_blocked(self.cmb_format, self.cmb_format.findText(label))
            self.lock_fmt.blockSignals(True)
            self.lock_fmt.setChecked(True)
            self.lock_fmt.blockSignals(False)
            self._mark_guessed(self.lock_fmt, False)
            near, err = nearest_film_format(w, h)
            std = FILM_FORMATS[near][0] if near is not None else ""
            what = "Scan measures %.1f x %.1f cm at %.0f dpi" % (w, h, dpi)
            if near is not None and err <= 0.02:
                text = "%s -- matches %s." % (what, std)
            elif near is not None and w * h > FILM_FORMATS[near][1] * FILM_FORMATS[near][2]:
                text = ("%s, larger than the nearest standard frame (%s): "
                        "probably a border or datastrip, which is included -- "
                        "that is what the scale needs." % (what, std))
            elif near is not None:
                text = ("%s, smaller than the nearest standard frame (%s): "
                        "probably cropped. The scanned size is used." % (what, std))
            else:
                text = what + "."
            self.lbl_fmt_guess.setText(
                text + " If the file was resized after scanning, its dpi is "
                "wrong: pick the size by hand instead.")
            return
        border = (" Enter the size of the whole image as scanned -- border or "
                  "datastrip included, if present -- or Guess it.")
        idx, note, _confident = guess_film_format(px.width(), px.height(),
                                                  dpi_x, dpi_y)
        if idx is not None:
            self.lbl_fmt_guess.setText(
                "Shape suggests " + FILM_FORMATS[idx][0] + " (" + note
                + ")." + border)
        else:
            self.lbl_fmt_guess.setText(
                (note + "." if note else "No scan resolution in the file.")
                + border)

    def _save_geometry_inputs(self):
        try:
            _set("geom_on", "true" if self.geom_box.isChecked() else "false")
            data = self.cmb_format.currentData()
            if self.cmb_format.currentText().startswith("As scanned") and data:
                # tied to this file: carried over as a custom size (the next
                # file's own resolution replaces it if it has one)
                _set("geom_format", "Custom...")
                _set("geom_fmt_w", float(data[0]))
                _set("geom_fmt_h", float(data[1]))
            else:
                _set("geom_format", self.cmb_format.currentText())
                _set("geom_fmt_w", self.spin_fmt_w.value())
                _set("geom_fmt_h", self.spin_fmt_h.value())
            _set("geom_alt", self.spin_alt.value())
            _set("geom_alt_unit", self.cmb_alt_unit.currentIndex())
            _set("geom_focal", self.cmb_focal.currentText())
            _set("geom_focal_mm", self._custom_focal_mm())
            _set("geom_focal_unit", self.cmb_focal_unit.currentIndex())
            _set("geom_sun", "true" if self.chk_sun.isChecked() else "false")
            _set("geom_shadow", self.spin_shadow.value())
            if self._date_known():
                ds = self.date_edit.date().toString("yyyy-MM-dd")
                _set("geom_date", ds)
                _set("geom_last_date", ds)
            else:
                _set("geom_date", "")
            _set("geom_time", self.time_edit.time().toString("HH:mm"))
            _set("geom_tz", str(self._tz_offset()))
            for chk, key in ((self.lock_fmt, "lock_fmt"),
                             (self.lock_alt, "lock_alt"),
                             (self.lock_focal, "lock_focal"),
                             (self.lock_time, "lock_time")):
                _set(key, "true" if chk.isChecked() else "false")
                _set(key + "_guessed", "true" if self._is_guessed(chk) else "false")
        except Exception as _exc:
            _ignored(_exc)

    # ---- summary -----------------------------------------------------------
    def placement_values(self):
        """The numbers describing this placement, for reuse on other frames."""
        item = getattr(self, "item", None)
        if item is None:
            return []
        try:
            canvas_rot = float(self.canvas.rotation())
        except Exception:
            canvas_rot = self._canvas_rot
        px_w, px_h = item._pixmap.width(), item._pixmap.height()
        k = self._ground_m_per_map_unit()
        gsd = item.gsd * k                       # ground metres per pixel
        rows = []
        scale = getattr(self, "_photo_scale", None)
        if scale:
            rows.append(("Photo scale", "1:%.0f" % scale))
        rows += [
            ("Ground size", "%.0f x %.0f m" % (gsd * px_w, gsd * px_h)),
            ("Ground sampling", "%.3f m/pixel" % gsd),
            ("Scale slider", "%d %%" % self.sc_slider.value()),
            ("Rotation on screen", "%d deg" % self.rot_spin.value()),
            ("Rotation vs north", "%d deg" % int(round(
                self._bound(float(self.rot_spin.value()) - canvas_rot)))),
            ("Centre (map CRS)", "%.1f, %.1f" % (item.center.x(),
                                                 item.center.y())),
            ("Image size", "%d x %d px" % (px_w, px_h)),
        ]
        if abs(k - 1.0) > 0.01:
            rows.append(("Map distortion", "1 map unit = %.3f m on the ground "
                         "here (corrected)" % k))
        size, alt, focal = (self._film_size_cm(), self._altitude_m(),
                            self._focal_mm())
        known, guessed = [], []
        if size:
            (guessed if self._is_guessed(self.lock_fmt) else known).append(
                "film %.1f x %.1f cm" % (size[0], size[1]))
        if alt:
            unit = float(self.cmb_alt_unit.currentData())
            txt = ("height %.0f m" % alt if unit == 1.0 else
                   "height %.0f %s (%.0f m)" % (alt / unit,
                                                self.cmb_alt_unit.currentText(), alt))
            (guessed if self._is_guessed(self.lock_alt) else known).append(txt)
        if focal:
            (guessed if self._is_guessed(self.lock_focal) else known).append(
                "focal " + _fmt_focal(focal))
        if known:
            rows.append(("Known values", ", ".join(known)))
        if guessed:
            rows.append(("Guessed values", ", ".join(guessed)))
        if item.shadow_azimuth is not None:
            rows.append(("Shadow azimuth", "%.0f deg from north (%s)"
                         % (item.shadow_azimuth,
                            getattr(self, "_sun_note", ""))))
            if self.lock_time.isChecked():
                off = self._tz_offset()
                um = self._time_utc_minutes()
                rows.append(("Date / time" + (" (guessed)" if self._is_guessed(
                    self.lock_time) else ""), "%s %s %s%s" % (
                    self.date_edit.date().toString("yyyy-MM-dd"),
                    self.time_edit.time().toString("HH:mm"), _utc_label(off),
                    "" if not off else " (%02d:%02d UTC)" % (um // 60, um % 60))))
        return rows

    def _update_summary(self):
        rows = self.placement_values()
        text = chr(10).join("%-25s %s" % (k + ":", v) for k, v in rows)
        note = getattr(self, "_gsd_note", "")
        if note:
            text += chr(10) + "(" + note + ")"
        try:
            self.summary.setPlainText(text)
        except Exception as _exc:
            _ignored(_exc)

    def _copy_summary(self):
        try:
            QtWidgets.QApplication.clipboard().setText(
                self.summary.toPlainText())
            self.iface.messageBar().pushMessage(
                "AutoGR Bridge", "Placement values copied to the clipboard.",
                level=LVL_INFO, duration=4)
        except Exception as _exc:
            _ignored(_exc)

    def _apply_to_item(self, method, value):
        """Call a setter on the overlay item, ignoring it once cleaned up."""
        item = getattr(self, "item", None)
        if item is None:
            return
        try:
            getattr(item, method)(value)
        except Exception as _exc:
            _ignored(_exc)

    @staticmethod
    def _bound(a):
        """Keep an angle within the bridge's -359..359 rotation field."""
        while a > 359:
            a -= 360
        while a < -359:
            a += 360
        return a

    def _footprint_extent(self, canvas_rot, margin=0.05):
        """Map-CRS extent covering the placed image, in map units.

        The image sits on the map rotated, so its footprint is a tilted
        rectangle; this returns the north-up bounding box of that rectangle
        (the canvas extent is always axis-aligned, and the base snapshot is
        deliberately captured north-up). For a w x h image at ground sampling
        distance g and map-relative angle t, the half sizes of the bounding
        box are:
            halfW = (w*g*|cos t| + h*g*|sin t|) / 2
            halfH = (w*g*|sin t| + h*g*|cos t|) / 2
        Signs drop out, so this is correct whichever way the image is turned.
        """
        import math
        import traceback
        item = getattr(self, "item", None)
        if item is None:
            return None
        try:
            w = item._pixmap.width() * item.gsd      # map units
            h = item._pixmap.height() * item.gsd
            if w <= 0 or h <= 0:
                return None
            # item.angle is screen-relative; make it relative to the map
            t = math.radians(float(item.angle) - canvas_rot)
            c, s = abs(math.cos(t)), abs(math.sin(t))
            half_w = 0.5 * (w * c + h * s) * (1.0 + margin)
            half_h = 0.5 * (w * s + h * c) * (1.0 + margin)
            cx, cy = item.center.x(), item.center.y()
            return QgsRectangle(cx - half_w, cy - half_h,
                                cx + half_w, cy + half_h)
        except Exception:
            _log("Could not compute the overlay footprint:\n"
                 + traceback.format_exc(), LVL_WARN)
            return None

    def _apply(self):
        # overlay angle is screen-relative; convert to the north-relative value
        # the bridge / AutoGR-SIFT expects by removing the live display rotation
        try:
            canvas_rot = float(self.canvas.rotation())
        except Exception:
            canvas_rot = self._canvas_rot
        applied = self._bound(float(self.rot_spin.value()) - canvas_rot)
        self.applied_angle = int(round(applied))
        _log(f"Overlay apply: slider={self.rot_spin.value()} deg, "
             f"canvas_rot={canvas_rot} deg -> bridge rotation={self.applied_angle} deg")

        # Zoom to the footprint while the item is still alive -- _cleanup()
        # retires it as soon as the dialog closes.
        self._save_geometry_inputs()
        for _k, _v in self.placement_values():
            _log("Overlay placement: %-25s %s" % (_k + ":", _v))

        crop = self.chk_crop.isChecked()
        _set("crop_to_footprint", "true" if crop else "false")
        rect = self._footprint_extent(canvas_rot) if crop else None
        if rect is not None and not rect.isEmpty():
            # Record it for the snapshot taken on Run. Zooming the canvas here
            # is only immediate feedback -- it must not be what the snapshot
            # relies on, because the user can pan or zoom again before Run.
            try:
                crs_id = self.canvas.mapSettings().destinationCrs().authid()
            except Exception:
                crs_id = ""
            _set_crop_extent(rect, crs_id)
            _log(f"Overlay apply: image footprint {rect.toString()} "
                 f"({crs_id}) stored for the next base snapshot")
            # Say so on screen: this is silent state that only shows up much
            # later, in the base image the tool receives.
            try:
                self.iface.messageBar().pushMessage(
                    "AutoGR Bridge",
                    "Base image will be cropped to the placed image "
                    "(%.0f x %.0f map units) on the next Run."
                    % (rect.width(), rect.height()),
                    level=LVL_INFO, duration=6)
            except Exception as _exc:
                _ignored(_exc)
            try:
                _set_saved_view(self.canvas, crs_id)
                self.canvas.setExtent(rect)
                self.canvas.refresh()
            except Exception:
                import traceback
                _log("Could not zoom to the overlay footprint: "
                     + traceback.format_exc(), LVL_WARN)
        else:
            _set_crop_extent(None, None)   # option off: drop any stale footprint

        self.accept()

    def _cleanup(self):
        """Remove the overlay from the canvas and hand interaction back to QGIS.

        Both steps matter: if the map tool is not unset it keeps swallowing
        canvas clicks/drags, and if the canvas item is not taken out of the
        scene it stays behind as a leftover."""
        if getattr(self, "_cleaned", False):
            return
        self._cleaned = True

        # 1) stop our map tool first, so it stops receiving canvas events.
        #    unsetMapTool() is the reliable way (setMapTool(None) is not).
        tool = getattr(self, "tool", None)
        if tool is not None:
            try:
                tool.item = None          # drop its reference to the item
                tool.on_scale_pct = None
                tool.current_pct = None
            except Exception as _exc:
                _ignored(_exc)
            try:
                self.canvas.unsetMapTool(tool)
            except Exception as _exc:
                _ignored(_exc)
        try:
            if self._prev_tool is not None:
                self.canvas.setMapTool(self._prev_tool)
        except Exception as _exc:
            _ignored(_exc)

        # 2) take the overlay item out of the scene -- but never destroy it.
        #    The scene repaints from posted events after this returns, so a
        #    QGraphicsItem that has been freed while the scene still holds it
        #    faults inside QGraphicsScene::drawItems() and takes QGIS down with
        #    no Python traceback. removeItem() also hands ownership back to
        #    Python, so merely dropping self.item would free it just the same:
        #    the wrapper has to be retired and kept alive instead.
        item = getattr(self, "item", None)
        if item is not None:
            try:
                item.hide()
            except Exception as _exc:
                _ignored(_exc)
            try:
                sc = item.scene()         # the scene it is actually in
                if sc is not None:
                    sc.removeItem(item)
            except Exception as _exc:
                _ignored(_exc)
            try:
                if item.scene() is None:
                    # safely out of the scene: release the image memory, so a
                    # retired item costs next to nothing
                    item._pixmap = QtGui.QPixmap()
            except Exception as _exc:
                _ignored(_exc)
            _RETIRED_OVERLAY_ITEMS.append(item)

        self.item = None
        self.tool = None
        try:
            self.canvas.refresh()
        except Exception as _exc:
            _ignored(_exc)

    def closeEvent(self, e):
        self._cleanup(); super().closeEvent(e)

    def done(self, r):
        self._cleanup(); super().done(r)


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
        self._headless = None
        self._progress_path = None
        self._dlg = None               # the non-modal settings dialog
        self._overlay_session = None   # active on-map overlay session

    def initGui(self):
        try:
            self.action = QAction(
                QtGui.QIcon(ICON_PATH), "AutoGR-Bridge", self.iface.mainWindow())
            self.action.triggered.connect(self.run)
            self.toolbar = self.iface.addToolBar("AutoGR-Bridge")
            self.toolbar.setToolButtonStyle(Qt_ToolButtonTextBesideIcon)
            self.toolbar.addAction(self.action)
            self.iface.addPluginToMenu("&AutoGR", self.action)
            # clear snapshot folders orphaned by earlier crashes or cancels
            try:
                _sweep_stale_temp_dirs()
            except Exception as _exc:
                _ignored(_exc)
        except Exception:
            import traceback
            _log("initGui error:\n" + traceback.format_exc(), LVL_CRIT)
            raise

    def unload(self):
        # a run that never finished still left snapshots behind
        try:
            _purge_temp_canvas_dirs()
        except Exception as _exc:
            _ignored(_exc)
        # close any open non-modal dialog / overlay session so nothing is left
        # dangling when the plugin is unloaded/reloaded
        for attr in ("_dlg", "_overlay_session"):
            w = getattr(self, attr, None)
            if w is not None:
                try:
                    w.close()
                except Exception as _exc:
                    _ignored(_exc)
                setattr(self, attr, None)
        if self.action:
            self.iface.removePluginMenu("&AutoGR", self.action)
            try:
                if getattr(self, "toolbar", None):
                    self.iface.mainWindow().removeToolBar(self.toolbar)
                    self.toolbar = None
            except Exception as _exc:
                _ignored(_exc)

    def _collect_dataset(self, dlg):
        return [dlg.dataset_list.item(i).text() for i in range(dlg.dataset_list.count())]

    def _derive_pyqt_paths(self, python_exe):
        return _derive_pyqt_paths(python_exe)

    def _clean_env(self, program, is_py, pyexe):
        return _clean_process_env(program, is_py, pyexe)

    def _wire_logging(self, proc):
        proc.setProcessChannelMode(QProcess_MergedChannels)
        proc.readyReadStandardOutput.connect(self._on_ready)
        proc.errorOccurred.connect(self._on_error)

    def _on_ready(self):
        if not self.proc: return
        data = self.proc.readAllStandardOutput()
        try:    s = bytes(data).decode("utf-8", errors="replace")
        except Exception: s = str(data)
        self._buffer.extend(s.encode("utf-8", errors="ignore"))
        for line in s.splitlines(): _log("[tool] " + line)

    def _on_error(self, err):
        _log("QProcess error: " + self.proc.errorString(), LVL_CRIT)

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
                except Exception as _exc:
                    _ignored(_exc)
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
        headless = self._headless_requested()
        if headless or str(_s("autostart", "false")).lower() == "true":
            args.append("--start")
        if headless:
            fd, self._progress_path = tempfile.mkstemp(
                prefix="autogr_progress_", suffix=".txt")
            os.close(fd)
            args.extend(["--headless", "--progress-file", self._progress_path])
        args.extend(["--baseimage", baseimage])
        for f in dataset_files: args.extend(["--dataset", f])
        args.extend(["--descriptor", str(_s("descriptor", "SIFT"))])
        matcher = str(_s("matcher", "FLANNBASED"))
        if matcher == "BRUTEFORCE_FL2": matcher = "BRUTEFORCE_SL2"
        args.extend(["--matcher", matcher])
        args.append("--subsampling=" + str(int(_s("subsampling", DEFAULT_SUB))))
        try:    rot = int(_s("rotation", 0))
        except (TypeError, ValueError): rot = 0
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

    # ---- headless runs (developer mode only) -------------------------------
    def _headless_requested(self):
        return (not _dist_mode()
                and str(_s("dev_headless", "false")).lower() == "true")

    def _run_active(self):
        return bool(getattr(self, "_headless", None))

    def _begin_headless(self):
        """The toolkit is running without a window: reopen the settings
        dialog greyed out, with the progress and a Cancel button."""
        self._headless = {"pct": 0, "text": "Starting...", "seen": False,
                          "result": None, "result_text": "", "pos": 0,
                          "cancelled": False}
        self._progress_timer = QtCore.QTimer()
        self._progress_timer.setInterval(400)
        self._progress_timer.timeout.connect(self._poll_progress)
        self._progress_timer.start()
        self.run()                      # opens the dialog in its running state

    def _poll_progress(self):
        st = getattr(self, "_headless", None)
        path = getattr(self, "_progress_path", None)
        if not st or not path:
            return
        try:
            # bytes, so the position is exact whatever the line endings
            with open(path, "rb") as f:
                f.seek(st["pos"])
                data = f.read()
        except OSError:
            return
        # only consume whole lines; a half-written one waits
        cut = data.rfind(b"\n")
        if cut < 0:
            return
        st["pos"] += cut + 1
        chunk = data[:cut + 1].decode("utf-8", errors="replace")
        for line in _parse_progress_lines(chunk, st):
            _log("[headless] " + line)
        dlg = getattr(self, "_dlg", None)
        if dlg is not None:
            try:
                dlg.set_progress(st["pct"], st["text"])
            except Exception as _exc:
                _ignored(_exc)

    def _stop_headless(self):
        st = getattr(self, "_headless", None)
        if not st:
            return
        st["cancelled"] = True
        st["text"] = "Cancelling..."
        try:
            if self.proc is not None:
                self.proc.kill()
        except Exception as _exc:
            _ignored(_exc)

    def _end_headless(self, exit_code):
        """Last read of the progress file, then report and release the
        dialog. Returns the final state."""
        try:
            self._progress_timer.stop()
        except Exception as _exc:
            _ignored(_exc)
        self._poll_progress()
        st = self._headless or {}
        self._headless = None
        try:
            # a last line without a newline still counts
            with open(self._progress_path, "rb") as f:
                f.seek(st.get("pos", 0))
                rest = f.read().decode("utf-8", errors="replace")
            for line in _parse_progress_lines(rest + "\n", st):
                _log("[headless] " + line)
        except Exception as _exc:
            _ignored(_exc)
        try:
            os.remove(self._progress_path)
        except Exception as _exc:
            _ignored(_exc)
        self._progress_path = None
        dlg = getattr(self, "_dlg", None)
        if dlg is not None:
            try:
                dlg.set_running(False)
            except Exception as _exc:
                _ignored(_exc)
        return st

    def _report_headless(self, st, exit_code, imported):
        bar = None
        try:
            bar = self.iface.messageBar()
        except Exception as _exc:
            _ignored(_exc)
        buf = self._buffer.decode("utf-8", errors="replace") if self._buffer else ""
        if st.get("cancelled"):
            text, level = "Run cancelled.", LVL_WARN
        elif exit_code == 0 and st.get("result") != "FAIL":
            text = "Run finished: %d result(s) imported." % imported
            if st.get("result_text"):
                text += " " + st["result_text"]
            level = LVL_INFO
        elif not st.get("seen") and ("unrecognized arguments" in buf
                                     or exit_code == 2):
            text = ("The linked toolkit does not support headless runs yet "
                    "(it needs a build that accepts --headless and "
                    "--progress-file). Untick 'Run headless' to use its window.")
            level = LVL_CRIT
        else:
            text = "Run failed (exit code %s)." % exit_code
            if st.get("result_text"):
                text += " " + st["result_text"]
            elif st.get("text"):
                text += " Last step: " + st["text"]
            level = LVL_CRIT
        _log("Headless run: " + text, level)
        if bar is not None:
            try:
                bar.pushMessage("AutoGR Bridge", text, level=level,
                                duration=0 if level == LVL_CRIT else 8)
            except Exception as _exc:
                _ignored(_exc)
        dlg = getattr(self, "_dlg", None)
        if dlg is not None:
            try:
                dlg.run_text.setText(text)
            except Exception as _exc:
                _ignored(_exc)

    def _start_overlay(self, iface, image_path):
        """Open the on-map overlay session (non-modal), then reopen the
        settings dialog when it closes (applying the rotation if requested)."""
        if not image_path or not os.path.exists(image_path):
            QtWidgets.QMessageBox.information(
                self.iface.mainWindow(), "AutoGR Bridge",
                "The selected dataset image could not be found.")
            QtCore.QTimer.singleShot(0, self.run)
            return
        # tear down any previous session first, so repeated opens can never
        # stack leftover overlay items on the canvas
        prev = getattr(self, "_overlay_session", None)
        if prev is not None:
            try:
                prev.close()
            except Exception as _exc:
                _ignored(_exc)
            self._overlay_session = None
        try:
            rot = int(_s("rotation", 0))
        except Exception:
            rot = 0
        try:
            sess = OverlaySession(iface, image_path, rot, self.iface.mainWindow())
        except Exception as e:
            import traceback
            _log("Overlay error:\n" + traceback.format_exc(), LVL_CRIT)
            QtWidgets.QMessageBox.critical(
                self.iface.mainWindow(), "AutoGR Bridge",
                "Could not start the map overlay:\n" + str(e))
            QtCore.QTimer.singleShot(0, self.run)
            return
        self._overlay_session = sess   # keep a reference alive

        def _on_finished(_result):
            if sess.applied_angle is not None:
                _set("rotation", int(sess.applied_angle))
            self._overlay_session = None
            QtCore.QTimer.singleShot(0, self.run)   # back to the settings dialog

        sess.finished.connect(_on_finished)
        sess.show()
        sess.raise_()

    def run(self):
        # Non-modal dialog: QGIS stays usable (change layers, layer order, pan,
        # zoom...) while the bridge is open. If it is already open, just raise it.
        try:
            from qgis.utils import iface
            existing = getattr(self, "_dlg", None)
            if existing is not None:
                try:
                    existing.show(); existing.raise_(); existing.activateWindow()
                    return
                except Exception:
                    self._dlg = None
            dlg = SettingsDialog(iface.mainWindow())
            dlg.setModal(False)
            self._dlg = dlg
            dlg.finished.connect(lambda res, d=dlg: self._on_dialog_finished(res, d))
            dlg.on_stop_run = self._stop_headless
            st = getattr(self, "_headless", None)
            if st:
                dlg.set_running(True, st.get("pct", 0), st.get("text", ""))
            dlg.show(); dlg.raise_(); dlg.activateWindow()
        except Exception as e:
            import traceback
            _log("Unhandled error in run():\n" + traceback.format_exc(), LVL_CRIT)
            try:
                QtWidgets.QMessageBox.critical(
                    self.iface.mainWindow(), "AutoGR Bridge",
                    "An unexpected error occurred:\n" + str(e))
            except Exception as _exc:
                _ignored(_exc)

    def _on_dialog_finished(self, res, dlg):
        """Handle the non-modal dialog closing: launch, overlay, or nothing."""
        from qgis.utils import iface
        self._dlg = None
        try:
            if res == SettingsDialog.OVERLAY_RESULT:
                self._start_overlay(iface, getattr(dlg, "_overlay_image", None))
                return
            if res != QDialog_Accepted:
                return
            self._launch_from_dialog(dlg)
        except Exception as e:
            import traceback
            _log("Error after dialog close:\n" + traceback.format_exc(), LVL_CRIT)
            try:
                QtWidgets.QMessageBox.critical(
                    self.iface.mainWindow(), "AutoGR Bridge",
                    "An unexpected error occurred:\n" + str(e))
            except Exception as _exc:
                _ignored(_exc)

    def _launch_from_dialog(self, dlg):
        if self._run_active():
            QtWidgets.QMessageBox.information(
                self.iface.mainWindow(), "AutoGR Bridge",
                "A run is still in progress.")
            return
        self._progress_path = None
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
            if getattr(self, "_progress_path", None):
                try:
                    os.remove(self._progress_path)
                except Exception as _exc:
                    _ignored(_exc)
                self._progress_path = None
            return
        if getattr(self, "_progress_path", None):
            self._begin_headless()

    def _on_tool_finished(self, exit_code, exit_status, dlg):
        headless_state = None
        if self._run_active():
            headless_state = self._end_headless(exit_code)
        if headless_state is None and exit_code != 0:
            buf  = self._buffer.decode("utf-8", errors="replace") if self._buffer else "(no output)"
            tail = "\n".join(buf.splitlines()[-60:])
            QtWidgets.QMessageBox.critical(
                self.iface.mainWindow(), "AutoGR Bridge",
                "AutoGR exited with errors.\n\nLast output:\n" + tail)
        n = 0
        cancelled = bool(headless_state and headless_state.get("cancelled"))
        if str(_s("auto_import", "true")).lower() != "false" and not cancelled:
            try:
                n = self._import_results_for_this_run(str(_s("output", "")).strip())
                _log("Imported " + str(n) + " rasters from this run.")
            except Exception as e:
                _log("Import error: " + str(e), LVL_CRIT)
        if headless_state is not None:
            self._report_headless(headless_state, exit_code, n)
        try:
            # snapshot folders made for this run (there can be several)
            _purge_temp_canvas_dirs()
        except Exception as e:
            _log("Cleanup error: " + str(e), LVL_WARN)
        self._buffer = bytearray()


__all__ = ["AutoGRBridgePlugin", "SettingsDialog"]

classFactory = lambda iface: AutoGRBridgePlugin(iface)

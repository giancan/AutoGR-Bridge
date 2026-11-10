# -*- coding: utf-8 -*-
def classFactory(iface):
    try:
        from . import autogr_bridge as m
        if hasattr(m, "AutoGRBridgePlugin"):
            return m.AutoGRBridgePlugin(iface)
        if hasattr(m, "classFactory"):
            return m.classFactory(iface)
        raise ImportError("AutoGRBridgePlugin symbol not found in autogr_bridge")
    except Exception:
        try:
            from qgis.core import QgsMessageLog, Qgis
            import traceback
            QgsMessageLog.logMessage("Init error:\n" + traceback.format_exc(),
                                     "AutoGR Bridge", Qgis.Critical)
        except Exception:
            pass
        raise

__version__ = "6.1"

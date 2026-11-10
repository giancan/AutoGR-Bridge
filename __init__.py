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
        except Exception as log_error:
            # the message log itself is unavailable: the Python console is
            # the last place left to say why the plugin did not load
            print("AutoGR Bridge: could not log the start-up error:", log_error)
        raise


__version__ = "7.0.0"

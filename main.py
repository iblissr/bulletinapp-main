"""Point d'entrée."""
from __future__ import annotations

import logging
import os
import sys

from qtpy.QtCore import Qt
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import QApplication, QMessageBox

from app import theme
from app.splash import show_splash


def main() -> int:
    # High-DPI scaling
    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Bulletin")
    app.setOrganizationName("Lycée Saint Joseph")
    app.setStyle("Fusion")

    splash = show_splash()
    splash.set_progress(5, "Initialisation de l'interface…")

    # Permettre de passer le chemin de la base en argument (legacy)
    db_path = None
    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    # Application du thème Material 3 (light par défaut).

    # Application du thème Material 3 (light par défaut).
    splash.set_progress(10, "Chargement du thème…")
    theme.apply(theme.LIGHT)

    splash.set_progress(15, "Détection des classes…")

    from app.db import Database
    from app.main_window import MainWindow
    from app.screen_utils import get_scale
    from app.workspace import discover_classes, find_bulletin_root, prettify_class_name
    from app.wizards.class_wizard import run_wizard

    # Résolution de la base initiale :
    # 1. Chemin explicite passé en argument → on l'utilise
    # 2. Classes détectées dans BULLETIN/ → DB neutre (data/bulletin.db),
    #    aucune classe pré-sélectionnée ; l'utilisateur clique sur une
    #    card dans l'accueil pour ouvrir une classe.
    # 3. Aucune classe → on propose l'assistant de création
    # 4. Assistant annulé → DB par défaut ``data/bulletin.db`` (legacy)
    classes = discover_classes()
    if db_path:
        splash.set_progress(25, "Ouverture de la base…")
        db = Database(db_path)
    elif classes:
        splash.set_progress(25, f"{len(classes)} classe(s) détectée(s)")
        db = Database(None)
    else:
        splash.set_progress(25, "Aucune classe — assistant…")
        draft = run_wizard(None)
        if draft is None:
            db = Database(None)
        else:
            classes = discover_classes()
            first = classes[0]
            db = Database(str(first.db_path))

    splash.set_progress(50, "Construction de l'interface…")
    win = MainWindow(db)
    splash.set_progress(70, "Synchronisation…")
    win._refresh_sidebar_classes()
    splash.set_progress(85, "Affichage du tableau de bord…")
    win._show_home()

    # Sur petit écran : maximisé par défaut
    scale = get_scale()
    if scale.is_small:
        win.showMaximized()
    else:
        win.show()

    # Backup automatique au démarrage (rotation 7)
    splash.set_progress(95, "Sauvegarde…")
    try:
        dest = db.backup(keep=7)
        if dest:
            log = logging.getLogger(__name__)
            log.info("Backup créé : %s", dest)
    except Exception:  # noqa: BLE001
        pass

    splash.set_progress(100, "Prêt !")
    splash.close()

    rc = app.exec()
    try:
        db.close()
    except Exception:  # noqa: BLE001
        pass
    return rc


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    sys.exit(main())

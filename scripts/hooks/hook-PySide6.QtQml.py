from pathlib import Path, PurePath

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)

# PyInstaller's stock QtQml hook collects every installed QML module. The
# PySide6 Addons wheel includes WebEngine, 3D, charts, and other capabilities
# Beacon neither imports nor permits in its desktop runtime. Collect only the
# native modules referenced by Main.qml.
qml_root = Path(pyside6_library_info.location["QmlImportsPath"]).resolve()
qml_destination = PurePath(pyside6_library_info.qt_rel_dir) / "qml"


def destination_for(source: Path) -> str:
    relative = source.relative_to(qml_root)
    if source.is_file():
        relative = relative.parent
    return str(qml_destination / relative)


module_roots = (
    qml_root / "QtQml",
    qml_root / "QtQml" / "Models",
    qml_root / "QtQml" / "WorkerScript",
    qml_root / "QtQuick",
    qml_root / "QtQuick" / "Controls",
    qml_root / "QtQuick" / "Layouts",
    qml_root / "QtQuick" / "NativeStyle",
    qml_root / "QtQuick" / "Templates",
    qml_root / "QtQuick" / "Window",
    qml_root / "QtMultimedia",
)
processed_qmldirs = set()
for module_root in module_roots:
    for qmldir in sorted(module_root.rglob("qmldir")):
        if qmldir in processed_qmldirs:
            continue
        if module_root.name in {"QtQml", "QtQuick"} and qmldir.parent != module_root:
            continue
        processed_qmldirs.add(qmldir)
        plugin_binaries, plugin_datas = pyside6_library_info._process_qml_plugin(
            qmldir
        )
        binaries.extend(
            (str(source), destination_for(source))
            for source in plugin_binaries
        )
        datas.extend(
            (str(source), destination_for(source))
            for source in plugin_datas
        )

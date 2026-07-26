import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia
import QtQuick.Dialogs
import QtQuick.Window

ApplicationWindow {
    id: root
    visible: true
    width: 1360
    height: 840
    minimumWidth: 1080
    minimumHeight: 700
    title: "ATLAS Beacon"
    color: ink

    property color ink: "#0B1015"
    property color shell: "#10171E"
    property color panel: "#161F28"
    property color panelRaised: "#1C2731"
    property color line: "#2A3742"
    property color bone: "#ECE8DF"
    property color muted: "#95A1AA"
    property color atlas: "#4A8C91"
    property color atlasBright: "#64AEB1"
    property color brass: "#C39A58"
    property color jade: "#6BAA82"
    property color ember: "#C5665A"
    property bool previewOpen: previewDialog.visible
    property bool beaconDockExpanded: false

    font.family: "Segoe UI"

    function formatPlayback(milliseconds) {
        var seconds = Math.max(0, Math.floor(milliseconds / 1000))
        var minutes = Math.floor(seconds / 60)
        var remainder = seconds % 60
        return minutes + ":" + (remainder < 10 ? "0" : "") + remainder
    }

    function openSelectedPreview() {
        if (backend.selectedAsset.id === undefined)
            return
        backend.prepareSelectedPreview()
        previewDialog.resetGeometry()
        previewDialog.show()
        previewDialog.raise()
        previewDialog.requestActivate()
    }

    function currentBeaconContext() {
        var viewLabel = backend.currentView === "overview" ? "Overview"
                      : backend.currentView === "library" ? "Library"
                      : backend.currentView === "operations" ? "Operations"
                      : "System"
        if (backend.currentView === "library"
                && backend.selectedAsset.id !== undefined) {
            return viewLabel + " · "
                    + (backend.selectedAsset.filename || "selected asset")
                    + " · " + (backend.selectedAsset.atlas_uri || "")
        }
        return viewLabel
    }

    component NavButton: Button {
        id: navControl
        property string viewKey
        property string indexLabel
        property string caption
        implicitHeight: 50
        leftPadding: 16
        rightPadding: 12
        hoverEnabled: true
        onClicked: backend.setCurrentView(viewKey)
        contentItem: RowLayout {
            spacing: 14
            Text {
                text: navControl.indexLabel
                color: backend.currentView === navControl.viewKey ? root.brass : root.muted
                font.family: "Cascadia Mono"
                font.pixelSize: 11
                font.letterSpacing: 1.3
                Layout.preferredWidth: 24
            }
            Text {
                text: navControl.caption
                color: backend.currentView === navControl.viewKey ? root.bone : root.muted
                font.pixelSize: 14
                font.weight: backend.currentView === navControl.viewKey ? Font.DemiBold : Font.Normal
                Layout.fillWidth: true
            }
            Rectangle {
                visible: backend.currentView === navControl.viewKey
                width: 5
                height: 5
                radius: 3
                color: root.atlasBright
            }
        }
        background: Rectangle {
            radius: 7
            color: backend.currentView === navControl.viewKey
                   ? Qt.rgba(0.29, 0.55, 0.57, 0.16)
                   : navControl.hovered ? Qt.rgba(1, 1, 1, 0.035) : "transparent"
            border.color: backend.currentView === navControl.viewKey
                          ? Qt.rgba(0.39, 0.68, 0.69, 0.24) : "transparent"
        }
    }

    component MetricCard: Rectangle {
        id: metric
        property string eyebrow
        property string value
        property string note
        property color accentColor: root.atlasBright
        implicitHeight: 120
        radius: 10
        color: root.panel
        border.color: root.line
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 6
            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: metric.eyebrow.toUpperCase()
                    color: root.muted
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.4
                    Layout.fillWidth: true
                }
                Rectangle {
                    width: 7
                    height: 7
                    radius: 4
                    color: metric.accentColor
                }
            }
            Text {
                text: metric.value
                color: root.bone
                font.pixelSize: 28
                font.weight: Font.DemiBold
            }
            Text {
                text: metric.note
                color: root.muted
                font.pixelSize: 11
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
        }
    }

    component PanelTitle: ColumnLayout {
        id: titleBlock
        property string eyebrow
        property string title
        spacing: 3
        Text {
            text: titleBlock.eyebrow.toUpperCase()
            color: root.brass
            font.pixelSize: 10
            font.weight: Font.DemiBold
            font.letterSpacing: 1.5
        }
        Text {
            text: titleBlock.title
            color: root.bone
            font.family: "Georgia"
            font.pixelSize: 22
        }
    }

    component PrimaryButton: Button {
        id: primary
        property bool quiet: false
        focusPolicy: Qt.TabFocus
        implicitHeight: 38
        leftPadding: 16
        rightPadding: 16
        hoverEnabled: true
        contentItem: Text {
            text: primary.text
            color: !primary.enabled ? root.muted
                 : primary.quiet ? root.bone : root.ink
            font.pixelSize: 12
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 6
            color: !primary.enabled
                   ? Qt.rgba(1, 1, 1, 0.025)
                   : primary.quiet
                   ? (primary.hovered ? root.panelRaised : "transparent")
                   : (primary.hovered ? "#76BFC1" : root.atlasBright)
            border.color: primary.quiet ? root.line : "transparent"
        }
    }

    component GroundedResultCard: Rectangle {
        id: resultCard
        property string assetId
        property string displayTitle
        property string filename
        property string path
        property string atlasUri
        property string reason
        property string availabilityLabel
        property string sizeLabel
        property string thumbnailUrl
        property bool available: false
        implicitHeight: 78
        radius: 7
        color: root.shell
        border.color: root.atlas
        RowLayout {
            anchors.fill: parent
            anchors.margins: 9
            spacing: 10
            Rectangle {
                Layout.preferredWidth: 54
                Layout.fillHeight: true
                radius: 5
                color: root.ink
                border.color: root.line
                clip: true
                Image {
                    anchors.fill: parent
                    source: resultCard.thumbnailUrl
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                    visible: resultCard.thumbnailUrl.length > 0
                }
                Text {
                    anchors.centerIn: parent
                    visible: resultCard.thumbnailUrl.length === 0
                    text: "ATLAS"
                    color: root.brass
                    font.family: "Cascadia Mono"
                    font.pixelSize: 7
                    font.weight: Font.DemiBold
                }
            }
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                Text {
                    Layout.fillWidth: true
                    text: resultCard.displayTitle || resultCard.filename
                    color: root.bone
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    text: resultCard.path
                    color: root.muted
                    font.family: "Cascadia Mono"
                    font.pixelSize: 8
                    elide: Text.ElideMiddle
                }
                Text {
                    Layout.fillWidth: true
                    text: resultCard.reason
                    color: root.atlasBright
                    font.pixelSize: 8
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    text: resultCard.atlasUri + "  ·  " + resultCard.sizeLabel
                    color: resultCard.available ? root.jade : root.brass
                    font.family: "Cascadia Mono"
                    font.pixelSize: 7
                    elide: Text.ElideRight
                }
            }
            PrimaryButton {
                text: "Inspect"
                quiet: true
                onClicked: backend.inspectBeaconResult(resultCard.assetId)
            }
        }
    }

    component IntakeProgress: Rectangle {
        id: intakeProgress
        property real value: 0
        implicitHeight: 7
        radius: 4
        color: root.ink
        border.color: root.line
        clip: true
        Rectangle {
            anchors.left: parent.left
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: Math.max(0, Math.min(parent.width, parent.width * intakeProgress.value))
            radius: 4
            color: root.atlasBright
            visible: intakeProgress.value > 0
        }
    }

    component DetailLine: RowLayout {
        id: detailLine
        property string label
        property string value
        property bool mono: false
        spacing: 14
        Text {
            text: detailLine.label.toUpperCase()
            color: root.muted
            font.pixelSize: 9
            font.weight: Font.DemiBold
            font.letterSpacing: 1.1
            Layout.preferredWidth: 104
        }
        Text {
            text: detailLine.value
            color: root.bone
            font.family: detailLine.mono ? "Cascadia Mono" : "Segoe UI"
            font.pixelSize: detailLine.mono ? 10 : 12
            wrapMode: Text.WrapAnywhere
            Layout.fillWidth: true
        }
    }

    component EditorField: ColumnLayout {
        id: editorField
        property string label
        property string placeholder
        property alias text: editorInput.text
        spacing: 5
        Text {
            text: editorField.label.toUpperCase()
            color: root.muted
            font.pixelSize: 8
            font.weight: Font.DemiBold
            font.letterSpacing: 1.0
        }
        TextField {
            id: editorInput
            Layout.fillWidth: true
            implicitHeight: 40
            placeholderText: editorField.placeholder
            color: root.bone
            placeholderTextColor: root.muted
            selectionColor: root.atlas
            selectByMouse: true
            leftPadding: 12
            rightPadding: 12
            background: Rectangle {
                radius: 7
                color: root.ink
                border.color: editorInput.activeFocus ? root.atlasBright : root.line
            }
        }
    }

    component EditorArea: ColumnLayout {
        id: editorArea
        property string label
        property string placeholder
        property int preferredHeight: 92
        property alias text: editorText.text
        spacing: 5
        Text {
            text: editorArea.label.toUpperCase()
            color: root.muted
            font.pixelSize: 8
            font.weight: Font.DemiBold
            font.letterSpacing: 1.0
        }
        ScrollView {
            Layout.fillWidth: true
            Layout.preferredHeight: editorArea.preferredHeight
            clip: true
            TextArea {
                id: editorText
                placeholderText: editorArea.placeholder
                color: root.bone
                placeholderTextColor: root.muted
                selectionColor: root.atlas
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                leftPadding: 12
                rightPadding: 12
                topPadding: 10
                bottomPadding: 10
                background: Rectangle {
                    radius: 7
                    color: root.ink
                    border.color: editorText.activeFocus ? root.atlasBright : root.line
                }
            }
        }
    }

    Shortcut {
        sequence: "Ctrl+R"
        onActivated: backend.refresh()
    }
    Timer {
        interval: 5000
        running: root.visible
        repeat: true
        onTriggered: backend.refreshIfChanged()
    }
    Shortcut {
        sequence: "Ctrl+F"
        onActivated: {
            backend.setCurrentView("library")
            searchField.forceActiveFocus()
            searchField.selectAll()
        }
    }
    Shortcut {
        sequence: "Escape"
        onActivated: backend.clearStatus()
    }
    Shortcut {
        sequence: "Space"
        context: Qt.ApplicationShortcut
        autoRepeat: false
        enabled: previewDialog.visible
                 || (backend.selectedAsset.id !== undefined
                     && !searchField.activeFocus
                     && !beaconReplyField.activeFocus
                     && !shellBeaconComposer.activeFocus
                     && !newRequestSubject.activeFocus
                     && !newRequestBody.activeFocus
                     && !newIntakeRoot.activeFocus
                     && !newIntakeLimit.activeFocus
                     && !newRequestDialog.visible
                     && !newIntakeDialog.visible
                     && !metadataDialog.visible
                     && !moveDialog.visible)
        onActivated: {
            if (previewDialog.visible)
                previewDialog.close()
            else
                root.openSelectedPreview()
        }
    }
    Shortcut {
        sequence: "Up"
        context: Qt.ApplicationShortcut
        autoRepeat: true
        enabled: backend.currentView === "library"
                 && !previewDialog.visible
                 && !searchField.activeFocus
                 && !beaconReplyField.activeFocus
                 && !shellBeaconComposer.activeFocus
                 && !newRequestSubject.activeFocus
                 && !newRequestBody.activeFocus
                 && !newIntakeRoot.activeFocus
                 && !newIntakeLimit.activeFocus
        onActivated: backend.navigateLibraryAsset(-1)
    }
    Shortcut {
        sequence: "Down"
        context: Qt.ApplicationShortcut
        autoRepeat: true
        enabled: backend.currentView === "library"
                 && !previewDialog.visible
                 && !searchField.activeFocus
                 && !beaconReplyField.activeFocus
                 && !shellBeaconComposer.activeFocus
                 && !newRequestSubject.activeFocus
                 && !newRequestBody.activeFocus
                 && !newIntakeRoot.activeFocus
                 && !newIntakeLimit.activeFocus
        onActivated: backend.navigateLibraryAsset(1)
    }
    Shortcut {
        sequences: ["Left", "Up"]
        context: Qt.ApplicationShortcut
        autoRepeat: true
        enabled: previewDialog.visible
        onActivated: {
            backend.navigateLibraryAsset(-1)
            backend.prepareSelectedPreview()
        }
    }
    Shortcut {
        sequences: ["Right", "Down"]
        context: Qt.ApplicationShortcut
        autoRepeat: true
        enabled: previewDialog.visible
        onActivated: {
            backend.navigateLibraryAsset(1)
            backend.prepareSelectedPreview()
        }
    }

    Dialog {
        id: backupDialog
        modal: true
        anchors.centerIn: Overlay.overlay
        width: 520
        padding: 0
        closePolicy: Popup.CloseOnEscape
        background: Rectangle {
            radius: 12
            color: root.panelRaised
            border.color: root.line
        }
        contentItem: ColumnLayout {
            spacing: 0
            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 26
                spacing: 10
                Text {
                    text: "Create verified recovery copy?"
                    color: root.bone
                    font.family: "Georgia"
                    font.pixelSize: 23
                }
                Text {
                    text: "Beacon will make an online SQLite backup, run an integrity check, calculate its SHA-256, and only then place it in the backup folder."
                    color: root.muted
                    font.pixelSize: 12
                    lineHeight: 1.35
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 52
                    radius: 7
                    color: root.ink
                    border.color: root.line
                    Text {
                        anchors.fill: parent
                        anchors.margins: 12
                        text: backend.backupDirectory
                        color: root.bone
                        font.family: "Cascadia Mono"
                        font.pixelSize: 10
                        wrapMode: Text.WrapAnywhere
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: root.line
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 18
                spacing: 10
                Item { Layout.fillWidth: true }
                PrimaryButton {
                    text: "Cancel"
                    quiet: true
                    onClicked: backupDialog.close()
                }
                PrimaryButton {
                    text: "Create & verify"
                    enabled: !backend.busy
                    onClicked: {
                        backupDialog.close()
                        backend.createBackup()
                    }
                }
            }
        }
    }

    Dialog {
        id: localAnalysisDialog
        objectName: "localAnalysisDialog"
        modal: true
        anchors.centerIn: Overlay.overlay
        width: Math.min(root.width - 80, 690)
        padding: 0
        closePolicy: Popup.CloseOnEscape
        onOpened: backend.refreshAnalysisReadiness()
        background: Rectangle {
            radius: 12
            color: root.panelRaised
            border.color: root.line
        }
        contentItem: ColumnLayout {
            spacing: 0
            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 26
                spacing: 13
                PanelTitle {
                    eyebrow: "Beacon analysis"
                    title: "Analyze the local catalog"
                }
                Text {
                    Layout.fillWidth: true
                    text: "Create checksum-bound rich metadata with models running on this PC. Beacon fills AI-owned editable fields and preserves human corrections; originals are never changed."
                    color: root.muted
                    font.pixelSize: 12
                    lineHeight: 1.4
                    wrapMode: Text.WordWrap
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 66
                    radius: 7
                    color: root.ink
                    border.color: backend.analysisReadiness.runtimeAvailable
                                  ? root.jade : root.brass
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 11
                        Rectangle {
                            width: 8
                            height: 8
                            radius: 4
                            color: backend.analysisReadiness.runtimeAvailable
                                   ? root.jade : root.brass
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 3
                            Text {
                                text: backend.analysisReadiness.runtimeLabel
                                      || "Checking local runtime…"
                                color: root.bone
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                            }
                            Text {
                                Layout.fillWidth: true
                                text: backend.analysisReadiness.runtimeDetail || ""
                                color: root.muted
                                font.pixelSize: 9
                                elide: Text.ElideRight
                            }
                        }
                        PrimaryButton {
                            text: "Check again"
                            quiet: true
                            onClicked: backend.refreshAnalysisReadiness()
                        }
                    }
                }
                GridLayout {
                    Layout.fillWidth: true
                    columns: 4
                    columnSpacing: 10
                    MetricCard {
                        Layout.fillWidth: true
                        eyebrow: includeAnalyzedAssets.checked ? "Reanalysis scope" : "Unanalyzed"
                        value: includeAnalyzedAssets.checked
                               ? (backend.analysisReadiness.allAssetsLabel || "0")
                               : (backend.analysisReadiness.assetsLabel || "0")
                        note: includeAnalyzedAssets.checked
                              ? (backend.analysisReadiness.allBytesLabel || "0 B")
                              : (backend.analysisReadiness.bytesLabel || "0 B")
                        accentColor: root.atlasBright
                    }
                    MetricCard {
                        Layout.fillWidth: true
                        eyebrow: "Visual"
                        value: includeAnalyzedAssets.checked
                               ? (backend.analysisReadiness.allVisualLabel || "0")
                               : (backend.analysisReadiness.visualLabel || "0")
                        note: "Images or video"
                        accentColor: root.atlasBright
                    }
                    MetricCard {
                        Layout.fillWidth: true
                        eyebrow: "Audio"
                        value: includeAnalyzedAssets.checked
                               ? (backend.analysisReadiness.allAudioLabel || "0")
                               : (backend.analysisReadiness.audioLabel || "0")
                        note: "Speech + acoustic context"
                        accentColor: root.brass
                    }
                    MetricCard {
                        Layout.fillWidth: true
                        eyebrow: "Other"
                        value: includeAnalyzedAssets.checked
                               ? (backend.analysisReadiness.allOtherLabel || "0")
                               : (backend.analysisReadiness.otherLabel || "0")
                        note: "Bounded context"
                        accentColor: root.brass
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    Text {
                        text: "LOCAL MODEL"
                        color: root.muted
                        font.pixelSize: 8
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.0
                    }
                    ComboBox {
                        id: localAnalysisModel
                        objectName: "localAnalysisModel"
                        Layout.fillWidth: true
                        implicitHeight: 42
                        model: backend.analysisReadiness.models || []
                        enabled: backend.analysisReadiness.runtimeAvailable
                                 && count > 0
                    }
                }
                CheckBox {
                    id: includeAnalyzedAssets
                    text: "Reanalyze every catalog asset, including existing candidates"
                    checked: false
                    enabled: !backend.busy
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 58
                    radius: 7
                    color: Qt.rgba(0.29, 0.55, 0.57, 0.10)
                    border.color: Qt.rgba(0.39, 0.68, 0.69, 0.24)
                    Text {
                        anchors.fill: parent
                        anchors.margins: 11
                        text: "LOCAL ONLY  ·  No cloud fallback. Beacon uses six video samples and local speech plus acoustic context. Candidate confidence, limitations, and rich stock metadata remain reviewable."
                        color: root.bone
                        font.pixelSize: 9
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 18
                spacing: 10
                Text {
                    text: "AI FILLS EDITABLE METADATA"
                    color: root.brass
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.0
                }
                Item { Layout.fillWidth: true }
                PrimaryButton {
                    text: "Cancel"
                    quiet: true
                    onClicked: localAnalysisDialog.close()
                }
                PrimaryButton {
                    objectName: "startLocalAnalysisButton"
                    text: "Start local analysis"
                    enabled: !backend.busy
                             && (includeAnalyzedAssets.checked
                                 ? backend.analysisReadiness.canReanalyze === true
                                 : backend.analysisReadiness.canStart === true)
                             && localAnalysisModel.currentText.length > 0
                    onClicked: {
                        backend.startLocalCatalogAnalysis(
                            localAnalysisModel.currentText,
                            includeAnalyzedAssets.checked
                        )
                        localAnalysisDialog.close()
                    }
                }
            }
        }
    }

    Dialog {
        id: newIntakeDialog
        objectName: "newIntakeDialog"
        modal: true
        anchors.centerIn: Overlay.overlay
        width: Math.min(root.width - 80, 650)
        padding: 0
        closePolicy: Popup.CloseOnEscape
        onOpened: {
            newIntakeRoot.text = backend.defaultIntakeRoot
            newIntakeLimit.text = "25"
            newIntakeRoot.forceActiveFocus()
        }
        background: Rectangle {
            radius: 12
            color: root.panelRaised
            border.color: root.line
        }
        contentItem: ColumnLayout {
            spacing: 0
            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 26
                spacing: 13
                PanelTitle {
                    eyebrow: "Archive intake"
                    title: "Prepare a recursive catalog job"
                }
                Text {
                    Layout.fillWidth: true
                    text: "Beacon will make a durable snapshot of regular files below this approved folder. Creating the job does not start it, move a file, or change an original."
                    color: root.muted
                    font.pixelSize: 12
                    lineHeight: 1.4
                    wrapMode: Text.WordWrap
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 62
                    radius: 7
                    color: root.ink
                    border.color: root.line
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: "MANUAL BATCH"
                                color: root.brass
                                font.pixelSize: 8
                                font.weight: Font.DemiBold
                                font.letterSpacing: 1.0
                            }
                            Text {
                                text: "Choose exact files or recursively include one Inbox folder."
                                color: root.muted
                                font.pixelSize: 10
                            }
                        }
                        PrimaryButton {
                            text: "Choose files…"
                            quiet: true
                            onClicked: selectedIntakeFiles.open()
                        }
                        PrimaryButton {
                            text: "Choose folderâ€¦"
                            quiet: true
                            onClicked: selectedIntakeFolder.open()
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    Text {
                        text: "APPROVED SOURCE FOLDER"
                        color: root.muted
                        font.pixelSize: 8
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.0
                    }
                    TextField {
                        id: newIntakeRoot
                        objectName: "newIntakeRoot"
                        Layout.fillWidth: true
                        implicitHeight: 42
                        color: root.bone
                        placeholderTextColor: root.muted
                        selectionColor: root.atlas
                        selectByMouse: true
                        font.family: "Cascadia Mono"
                        font.pixelSize: 11
                        leftPadding: 13
                        rightPadding: 13
                        background: Rectangle {
                            radius: 7
                            color: root.ink
                            border.color: newIntakeRoot.activeFocus
                                          ? root.atlasBright : root.line
                        }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 14
                    ColumnLayout {
                        Layout.preferredWidth: 190
                        spacing: 5
                        Text {
                            text: "MAXIMUM FILES"
                            color: root.muted
                            font.pixelSize: 8
                            font.weight: Font.DemiBold
                            font.letterSpacing: 1.0
                        }
                        TextField {
                            id: newIntakeLimit
                            objectName: "newIntakeLimit"
                            Layout.fillWidth: true
                            implicitHeight: 42
                            text: "25"
                            placeholderText: "Blank = all files"
                            color: root.bone
                            placeholderTextColor: root.muted
                            selectionColor: root.atlas
                            selectByMouse: true
                            inputMethodHints: Qt.ImhDigitsOnly
                            validator: IntValidator { bottom: 1; top: 100000 }
                            leftPadding: 13
                            rightPadding: 13
                            background: Rectangle {
                                radius: 7
                                color: root.ink
                                border.color: newIntakeLimit.activeFocus
                                              ? root.atlasBright : root.line
                            }
                        }
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 64
                        Layout.alignment: Qt.AlignBottom
                        radius: 7
                        color: root.ink
                        border.color: root.line
                        Text {
                            anchors.fill: parent
                            anchors.margins: 11
                            text: "Start with 25 for a representative proof. Leave the limit blank only when you intend to snapshot every discovered file."
                            color: root.muted
                            font.pixelSize: 10
                            lineHeight: 1.3
                            wrapMode: Text.WordWrap
                            verticalAlignment: Text.AlignVCenter
                        }
                    }
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 48
                    radius: 7
                    color: Qt.rgba(0.29, 0.55, 0.57, 0.10)
                    border.color: Qt.rgba(0.39, 0.68, 0.69, 0.24)
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 11
                        Rectangle {
                            width: 7
                            height: 7
                            radius: 4
                            color: root.atlasBright
                        }
                        Text {
                            Layout.fillWidth: true
                            text: "CATALOG ONLY  ·  Resume, cancel, retry, and crash recovery are recorded in the local database."
                            color: root.bone
                            font.pixelSize: 9
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 18
                spacing: 10
                Text {
                    text: "APPROVED ROOT ONLY"
                    color: root.brass
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.0
                }
                Item { Layout.fillWidth: true }
                PrimaryButton {
                    text: "Cancel"
                    quiet: true
                    onClicked: newIntakeDialog.close()
                }
                PrimaryButton {
                    text: "Create snapshot"
                    enabled: !backend.busy
                             && newIntakeRoot.text.trim().length > 0
                             && (newIntakeLimit.text.length === 0
                                 || newIntakeLimit.acceptableInput)
                    onClicked: {
                        backend.createIntakeJob(
                            newIntakeRoot.text,
                            newIntakeLimit.text
                        )
                        newIntakeDialog.close()
                    }
                }
            }
        }
    }

    FileDialog {
        id: selectedIntakeFiles
        title: "Choose files for this Beacon intake"
        fileMode: FileDialog.OpenFiles
        currentFolder: "file:///J:/Inbox"
        onAccepted: {
            backend.createSelectedIntakeJob(selectedFiles)
            newIntakeDialog.close()
        }
    }

    FolderDialog {
        id: selectedIntakeFolder
        title: "Choose a folder for this Beacon intake"
        currentFolder: "file:///J:/Inbox"
        onAccepted: {
            backend.createSelectedIntakeFolder(
                selectedFolder,
                newIntakeLimit.text
            )
            newIntakeDialog.close()
        }
    }

    Dialog {
        id: newRequestDialog
        modal: true
        anchors.centerIn: Overlay.overlay
        width: Math.min(root.width - 80, 640)
        padding: 0
        closePolicy: Popup.CloseOnEscape
        onOpened: {
            newRequestSubject.text = ""
            newRequestBody.text = ""
            newRequestSubject.forceActiveFocus()
        }
        background: Rectangle {
            radius: 12
            color: root.panelRaised
            border.color: root.line
        }
        contentItem: ColumnLayout {
            spacing: 0
            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 26
                spacing: 12
                PanelTitle {
                    eyebrow: "Beacon desk"
                    title: "Start a new conversation"
                }
                Text {
                    Layout.fillWidth: true
                    text: "Ask for analysis, request context, or clarify protocol. The message is saved locally for Beacon; it does not authorize a file operation."
                    color: root.muted
                    font.pixelSize: 12
                    lineHeight: 1.35
                    wrapMode: Text.WordWrap
                }
                TextField {
                    id: newRequestSubject
                    Layout.fillWidth: true
                    implicitHeight: 42
                    placeholderText: "Subject"
                    color: root.bone
                    placeholderTextColor: root.muted
                    selectionColor: root.atlas
                    selectByMouse: true
                    leftPadding: 13
                    rightPadding: 13
                    maximumLength: 160
                    background: Rectangle {
                        radius: 7
                        color: root.ink
                        border.color: newRequestSubject.activeFocus
                                      ? root.atlasBright : root.line
                    }
                }
                ScrollView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 180
                    clip: true
                    TextArea {
                        id: newRequestBody
                        placeholderText: "What would you like Beacon to help with?"
                        color: root.bone
                        placeholderTextColor: root.muted
                        selectionColor: root.atlas
                        selectByMouse: true
                        wrapMode: TextEdit.Wrap
                        leftPadding: 13
                        rightPadding: 13
                        topPadding: 12
                        bottomPadding: 12
                        background: Rectangle {
                            radius: 7
                            color: root.ink
                            border.color: newRequestBody.activeFocus
                                          ? root.atlasBright : root.line
                        }
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                height: 1
                color: root.line
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 18
                spacing: 10
                Text {
                    text: "SAVED LOCALLY"
                    color: root.jade
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.1
                }
                Item { Layout.fillWidth: true }
                PrimaryButton {
                    text: "Cancel"
                    quiet: true
                    onClicked: newRequestDialog.close()
                }
                PrimaryButton {
                    text: "Save for Beacon"
                    enabled: newRequestSubject.text.trim().length > 0
                             && newRequestBody.text.trim().length > 0
                             && newRequestBody.text.length <= 8000
                    onClicked: {
                        backend.createBeaconThread(
                            newRequestSubject.text,
                            newRequestBody.text
                        )
                        newRequestDialog.close()
                    }
                }
            }
        }
    }

    Dialog {
        id: metadataDialog
        objectName: "metadataDialog"
        modal: true
        anchors.centerIn: Overlay.overlay
        width: Math.min(root.width - 64, 820)
        height: Math.min(root.height - 48, 760)
        padding: 0
        closePolicy: Popup.CloseOnEscape
        onOpened: {
            var metadata = backend.selectedAsset.catalogMetadata || {}
            metadataTitle.text = metadata.display_title || ""
            metadataCategory.text = metadata.media_category || ""
            metadataDescription.text = metadata.description || ""
            metadataTags.text = metadata.tagsText || ""
            metadataPeople.text = metadata.peopleText || ""
            metadataDate.text = metadata.event_date || ""
            metadataPlace.text = metadata.place || ""
            metadataClient.text = metadata.client || ""
            metadataProject.text = metadata.project || ""
            metadataRights.text = metadata.rights || ""
            metadataNotes.text = metadata.notes || ""
            metadataOrganization.text = metadata.organization_path || ""
            metadataTitle.forceActiveFocus()
        }
        background: Rectangle {
            radius: 12
            color: root.panelRaised
            border.color: root.line
        }
        contentItem: ColumnLayout {
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 22
                PanelTitle {
                    eyebrow: "Editable catalog record"
                    title: "Asset metadata"
                }
                Item { Layout.fillWidth: true }
                Text {
                    text: "REVISION "
                          + String((backend.selectedAsset.catalogMetadata || {}).revision || 0)
                    color: root.jade
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.0
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
            ScrollView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                contentWidth: availableWidth
                clip: true
                ColumnLayout {
                    width: parent.width
                    spacing: 12
                    anchors.margins: 22
                    GridLayout {
                        Layout.fillWidth: true
                        columns: width >= 650 ? 2 : 1
                        columnSpacing: 12
                        rowSpacing: 12
                        EditorField {
                            id: metadataTitle
                            Layout.fillWidth: true
                            label: "Display title"
                            placeholder: "A human-readable title"
                        }
                        EditorField {
                            id: metadataCategory
                            Layout.fillWidth: true
                            label: "Media category"
                            placeholder: "Portrait, campaign video, music asset…"
                        }
                        EditorField {
                            id: metadataProject
                            Layout.fillWidth: true
                            label: "Project"
                            placeholder: "Project or collection"
                        }
                        EditorField {
                            id: metadataClient
                            Layout.fillWidth: true
                            label: "Client"
                            placeholder: "Direct or end client"
                        }
                        EditorField {
                            id: metadataDate
                            Layout.fillWidth: true
                            label: "Date or time context"
                            placeholder: "Exact or approximate"
                        }
                        EditorField {
                            id: metadataPlace
                            Layout.fillWidth: true
                            label: "Place"
                            placeholder: "City, venue, or setting"
                        }
                    }
                    EditorArea {
                        id: metadataDescription
                        Layout.fillWidth: true
                        label: "Description"
                        placeholder: "What this asset contains and why it matters"
                        preferredHeight: 108
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: width >= 650 ? 2 : 1
                        columnSpacing: 12
                        rowSpacing: 12
                        EditorArea {
                            id: metadataTags
                            Layout.fillWidth: true
                            label: "Tags · one per line"
                            placeholder: "campaign\nportrait\nreference"
                        }
                        EditorArea {
                            id: metadataPeople
                            Layout.fillWidth: true
                            label: "People · one per line"
                            placeholder: "Preferred name"
                        }
                    }
                    EditorArea {
                        id: metadataRights
                        Layout.fillWidth: true
                        label: "Rights and restrictions"
                        placeholder: "Ownership, retention, sharing, or publication limits"
                    }
                    EditorArea {
                        id: metadataNotes
                        Layout.fillWidth: true
                        label: "Notes"
                        placeholder: "Additional human context"
                    }
                    EditorField {
                        id: metadataOrganization
                        Layout.fillWidth: true
                        label: "Final organization directory"
                        placeholder: "J:\\Library\\…, J:\\Assets\\…, or J:\\Projects\\…"
                    }
                    Rectangle {
                        Layout.fillWidth: true
                        implicitHeight: 48
                        radius: 7
                        color: root.shell
                        border.color: root.line
                        Text {
                            anchors.fill: parent
                            anchors.margins: 11
                            text: "Verified technical facts remain locked. Saving here creates a new editable metadata revision and never writes into the source media."
                            color: root.muted
                            font.pixelSize: 10
                            lineHeight: 1.3
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 16
                Item { Layout.fillWidth: true }
                PrimaryButton {
                    text: "Cancel"
                    quiet: true
                    onClicked: metadataDialog.close()
                }
                PrimaryButton {
                    text: "Save revision"
                    onClicked: {
                        backend.saveSelectedAssetMetadata({
                            "display_title": metadataTitle.text,
                            "description": metadataDescription.text,
                            "media_category": metadataCategory.text,
                            "tagsText": metadataTags.text,
                            "peopleText": metadataPeople.text,
                            "event_date": metadataDate.text,
                            "place": metadataPlace.text,
                            "client": metadataClient.text,
                            "project": metadataProject.text,
                            "rights": metadataRights.text,
                            "notes": metadataNotes.text,
                            "organization_path": metadataOrganization.text
                        })
                        metadataDialog.close()
                    }
                }
            }
        }
    }

    Dialog {
        id: moveDialog
        objectName: "moveDialog"
        modal: true
        anchors.centerIn: Overlay.overlay
        width: Math.min(root.width - 80, 680)
        padding: 0
        closePolicy: Popup.CloseOnEscape
        onOpened: {
            moveSource.text = backend.selectedAsset.primary_path || ""
            moveDestination.text =
                (backend.selectedAsset.catalogMetadata || {}).organization_path || ""
        }
        background: Rectangle {
            radius: 12
            color: root.panelRaised
            border.color: root.line
        }
        contentItem: ColumnLayout {
            spacing: 0
            ColumnLayout {
                Layout.fillWidth: true
                Layout.margins: 24
                spacing: 12
                PanelTitle {
                    eyebrow: "Checksum-verified operation"
                    title: "Move cataloged file"
                }
                Text {
                    Layout.fillWidth: true
                    text: "Beacon will re-hash the selected observed location, move it without overwriting another file, verify the destination hash, and then update the catalog. A failure is recorded and rolled back when possible."
                    color: root.muted
                    font.pixelSize: 11
                    lineHeight: 1.35
                    wrapMode: Text.WordWrap
                }
                EditorField {
                    id: moveSource
                    Layout.fillWidth: true
                    label: "Exact observed source"
                    placeholder: "Select one observed location"
                }
                EditorField {
                    id: moveDestination
                    Layout.fillWidth: true
                    label: "Approved destination directory"
                    placeholder: "J:\\Library\\…, J:\\Assets\\…, or J:\\Projects\\…"
                }
                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 52
                    radius: 7
                    color: Qt.rgba(0.76, 0.60, 0.35, 0.10)
                    border.color: Qt.rgba(0.76, 0.60, 0.35, 0.28)
                    Text {
                        anchors.fill: parent
                        anchors.margins: 11
                        text: "The source filename is preserved. Identical destinations and duplicate locations are never silently merged or deleted."
                        color: root.brass
                        font.pixelSize: 10
                        lineHeight: 1.3
                        wrapMode: Text.WordWrap
                    }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: 16
                Item { Layout.fillWidth: true }
                PrimaryButton {
                    text: "Cancel"
                    quiet: true
                    onClicked: moveDialog.close()
                }
                PrimaryButton {
                    text: "Verify & move"
                    enabled: !backend.busy
                             && moveSource.text.trim().length > 0
                             && moveDestination.text.trim().length > 0
                    onClicked: {
                        backend.moveSelectedAsset(
                            moveSource.text,
                            moveDestination.text
                        )
                        moveDialog.close()
                    }
                }
            }
        }
    }

    Window {
        id: previewDialog
        objectName: "previewWindow"
        transientParent: root
        modality: Qt.NonModal
        flags: Qt.Dialog
               | Qt.WindowTitleHint
               | Qt.WindowSystemMenuHint
               | Qt.WindowMinMaxButtonsHint
               | Qt.WindowCloseButtonHint
        visible: false
        title: backend.selectedAsset.filename
               ? "Preview · " + backend.selectedAsset.filename
               : "ATLAS Beacon Preview"
        color: root.panel
        minimumWidth: 640
        minimumHeight: 440

        property string previewKind: backend.selectedAsset.previewKind || "file"
        property bool playable: previewKind === "audio" || previewKind === "video"
        property int pendingResumePosition: 0
        readonly property int defaultPreviewWidth: Math.min(
            Math.max(640, root.width - 72), 1080
        )
        readonly property int defaultPreviewHeight: Math.min(
            Math.max(440, root.height - 64), 720
        )

        function resetGeometry() {
            width = defaultPreviewWidth
            height = defaultPreviewHeight
            x = root.x + Math.round((root.width - width) / 2)
            y = root.y + Math.round((root.height - height) / 2)
        }

        onVisibleChanged: {
            if (visible) {
                if (playable && backend.selectedAsset.previewAvailable) {
                    pendingResumePosition = 0
                    previewPlayer.source = backend.selectedAsset.previewUrl
                    previewPlayer.play()
                }
            } else {
                previewPlayer.stop()
                previewPlayer.source = ""
                if (backend.currentView === "library")
                    libraryAssetList.forceActiveFocus()
            }
        }

        Shortcut {
            sequence: "Escape"
            context: Qt.WindowShortcut
            onActivated: previewDialog.close()
        }

        Connections {
            target: backend
            function onSelectedAssetChanged() {
                if (previewDialog.visible
                        && previewDialog.playable
                        && backend.selectedAsset.previewAvailable) {
                    var nextSource = backend.selectedAsset.previewUrl || ""
                    if (previewPlayer.source.toString() !== nextSource) {
                        previewDialog.pendingResumePosition =
                                previewPlayer.position
                        previewPlayer.source = nextSource
                        previewPlayer.play()
                    } else if (previewPlayer.playbackState
                               !== MediaPlayer.PlayingState) {
                        previewPlayer.play()
                    }
                }
            }
        }

        MediaPlayer {
            id: previewPlayer
            audioOutput: AudioOutput {
                volume: 0.82
                muted: previewMuted
            }
            videoOutput: previewVideo
            onMediaStatusChanged: {
                if ((mediaStatus === MediaPlayer.LoadedMedia
                        || mediaStatus === MediaPlayer.BufferedMedia)
                        && previewDialog.pendingResumePosition > 0) {
                    setPosition(previewDialog.pendingResumePosition)
                    previewDialog.pendingResumePosition = 0
                }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 66
                color: root.panelRaised
                radius: 12
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 20
                    anchors.rightMargin: 14
                    spacing: 12
                    Rectangle {
                        width: 8
                        height: 8
                        radius: 4
                        color: root.atlasBright
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            text: backend.selectedAsset.filename || "Preview"
                            color: root.bone
                            font.family: "Georgia"
                            font.pixelSize: 20
                            elide: Text.ElideMiddle
                            Layout.fillWidth: true
                        }
                        Text {
                            text: "TEMPORARY PREVIEW  ·  SOURCE REMAINS READ-ONLY"
                            color: root.muted
                            font.pixelSize: 8
                            font.weight: Font.DemiBold
                            font.letterSpacing: 1.2
                        }
                    }
                    PrimaryButton {
                        text: "Close  ·  Space"
                        quiet: true
                        onClicked: previewDialog.close()
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: 16
                radius: 9
                color: root.ink
                border.color: root.line
                clip: true

                Image {
                    anchors.fill: parent
                    anchors.margins: 18
                    visible: previewDialog.previewKind === "image"
                             && backend.selectedAsset.previewAvailable
                    source: previewDialog.visible
                            ? (backend.selectedAsset.previewUrl || "") : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: false
                }

                VideoOutput {
                    id: previewVideo
                    anchors.fill: parent
                    anchors.margins: 12
                    visible: previewDialog.previewKind === "video"
                    fillMode: VideoOutput.PreserveAspectFit
                }

                Image {
                    z: 2
                    anchors.fill: parent
                    anchors.margins: 12
                    visible: previewDialog.previewKind === "video"
                             && backend.selectedAsset.previewAvailable
                             && previewPlayer.position <= 0
                    source: previewDialog.visible
                            ? (backend.selectedAsset.thumbnailUrl || "") : ""
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    cache: true
                }

                BusyIndicator {
                    z: 3
                    anchors.centerIn: parent
                    running: previewDialog.previewKind === "video"
                             && backend.selectedAsset.previewAvailable
                             && (
                                 previewPlayer.mediaStatus
                                     === MediaPlayer.LoadingMedia
                                 || previewPlayer.mediaStatus
                                     === MediaPlayer.BufferingMedia
                                 || previewPlayer.mediaStatus
                                     === MediaPlayer.StalledMedia
                             )
                    visible: running
                }

                ScrollView {
                    id: audioPreviewScroll
                    anchors.fill: parent
                    anchors.margins: 18
                    visible: previewDialog.previewKind === "audio"
                    clip: true
                    contentWidth: availableWidth
                    ColumnLayout {
                        width: audioPreviewScroll.availableWidth
                        spacing: 14
                        Image {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.fillWidth: true
                            Layout.maximumWidth: 760
                            Layout.preferredHeight: 240
                            source: backend.selectedAsset.thumbnailUrl || ""
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            cache: false
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                Layout.fillWidth: true
                                text: "AUDIO WAVEFORM & TRANSCRIPT"
                                color: root.brass
                                font.pixelSize: 10
                                font.weight: Font.DemiBold
                                font.letterSpacing: 1.4
                            }
                            Text {
                                text: (backend.selectedAsset.transcript || {}).languageLabel || ""
                                color: root.muted
                                font.pixelSize: 9
                            }
                        }
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.max(
                                180, previewTranscript.implicitHeight + 28
                            )
                            radius: 8
                            color: root.shell
                            border.color: root.line
                            Text {
                                id: previewTranscript
                                anchors.left: parent.left
                                anchors.right: parent.right
                                anchors.top: parent.top
                                anchors.margins: 14
                                text: (backend.selectedAsset.transcript || {}).text
                                      || "No stored transcript is available yet."
                                color: root.bone
                                font.pixelSize: 12
                                lineHeight: 1.45
                                wrapMode: Text.WordWrap
                                textFormat: Text.PlainText
                            }
                        }
                    }
                }

                ColumnLayout {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 80, 640)
                    spacing: 15
                    visible: previewDialog.previewKind === "file"
                             && backend.selectedAsset.previewAvailable
                    Rectangle {
                        Layout.alignment: Qt.AlignHCenter
                        width: 68
                        height: 68
                        radius: 12
                        color: Qt.rgba(0.29, 0.55, 0.57, 0.14)
                        border.color: root.line
                        Text {
                            anchors.centerIn: parent
                            text: (backend.selectedAsset.kindLabel || "File")
                                  .substring(0, 2).toUpperCase()
                            color: root.atlasBright
                            font.family: "Cascadia Mono"
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Safe metadata preview"
                        color: root.bone
                        font.family: "Georgia"
                        font.pixelSize: 23
                        horizontalAlignment: Text.AlignHCenter
                    }
                    Text {
                        Layout.fillWidth: true
                        text: "Beacon does not render this format directly. The file has not been opened in an editor or changed."
                        color: root.muted
                        font.pixelSize: 12
                        lineHeight: 1.4
                        wrapMode: Text.WordWrap
                        horizontalAlignment: Text.AlignHCenter
                    }
                    DetailLine {
                        Layout.fillWidth: true
                        label: "Type"
                        value: backend.selectedAsset.kindLabel || "File"
                    }
                    DetailLine {
                        Layout.fillWidth: true
                        label: "Size"
                        value: backend.selectedAsset.sizeLabel || "0 B"
                    }
                    DetailLine {
                        Layout.fillWidth: true
                        label: "Location"
                        value: backend.selectedAsset.primary_path || "Unavailable"
                        mono: true
                    }
                }

                ScrollView {
                    anchors.fill: parent
                    anchors.margins: 18
                    visible: previewDialog.previewKind === "text"
                             && backend.selectedAsset.previewAvailable
                    clip: true
                    TextArea {
                        text: backend.selectedAsset.textPreview || ""
                        textFormat: TextEdit.PlainText
                        readOnly: true
                        selectByMouse: true
                        wrapMode: TextEdit.NoWrap
                        color: root.bone
                        selectionColor: root.atlas
                        selectedTextColor: root.bone
                        font.family: "Cascadia Mono"
                        font.pixelSize: 12
                        leftPadding: 10
                        rightPadding: 10
                        topPadding: 10
                        bottomPadding: 10
                        background: Rectangle {
                            color: "transparent"
                        }
                    }
                }

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 8
                    visible: !backend.selectedAsset.previewAvailable
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: backend.selectedAsset.previewPreparing
                              ? "Preparing compatible preview"
                              : "Preview unavailable"
                        color: root.bone
                        font.family: "Georgia"
                        font.pixelSize: 22
                    }
                    BusyIndicator {
                        Layout.alignment: Qt.AlignHCenter
                        running: backend.selectedAsset.previewPreparing || false
                        visible: running
                    }
                    Text {
                        text: backend.selectedAsset.previewError
                              || backend.selectedAsset.previewNote
                              || "Beacon can no longer read the observed location."
                        color: root.muted
                        font.pixelSize: 12
                        wrapMode: Text.WordWrap
                        horizontalAlignment: Text.AlignHCenter
                        Layout.maximumWidth: 520
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                implicitHeight: previewDialog.playable ? 66 : 48
                color: root.panelRaised
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18
                    anchors.rightMargin: 18
                    spacing: 12
                    PrimaryButton {
                        visible: previewDialog.playable
                        enabled: backend.selectedAsset.previewAvailable
                        text: previewPlayer.playbackState === MediaPlayer.PlayingState
                              ? "Pause" : "Play"
                        onClicked: {
                            if (previewPlayer.playbackState === MediaPlayer.PlayingState)
                                previewPlayer.pause()
                            else
                                previewPlayer.play()
                        }
                    }
                    Text {
                        visible: previewDialog.playable
                        text: root.formatPlayback(previewPlayer.position)
                        color: root.muted
                        font.family: "Cascadia Mono"
                        font.pixelSize: 10
                    }
                    Slider {
                        visible: previewDialog.playable
                        enabled: previewPlayer.seekable
                        Layout.fillWidth: true
                        from: 0
                        to: Math.max(1, previewPlayer.duration)
                        value: previewPlayer.position
                        onMoved: previewPlayer.setPosition(value)
                    }
                    Text {
                        visible: previewDialog.playable
                        text: root.formatPlayback(previewPlayer.duration)
                        color: root.muted
                        font.family: "Cascadia Mono"
                        font.pixelSize: 10
                    }
                    Text {
                        visible: !previewDialog.playable
                        text: previewDialog.previewKind === "text"
                              ? (backend.selectedAsset.textPreviewLabel || "Plain text")
                                + "  ·  Press Space or Escape to close."
                              : "Press Space or Escape to return to the library."
                        color: root.muted
                        font.pixelSize: 10
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Text {
                        visible: previewPlayer.error !== MediaPlayer.NoError
                        text: previewPlayer.errorString
                        color: root.ember
                        font.pixelSize: 9
                        elide: Text.ElideRight
                        Layout.preferredWidth: 220
                    }
                }
            }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: 230
            Layout.fillHeight: true
            color: root.ink
            border.color: root.line

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 76
                    spacing: 12
                    Image {
                        source: "assets/beacon.svg"
                        sourceSize.width: 40
                        sourceSize.height: 40
                        Layout.preferredWidth: 40
                        Layout.preferredHeight: 40
                    }
                    ColumnLayout {
                        spacing: -1
                        Text {
                            text: "ATLAS"
                            color: root.bone
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                            font.letterSpacing: 2.4
                        }
                        Text {
                            text: "BEACON"
                            color: root.brass
                            font.pixelSize: 9
                            font.weight: Font.DemiBold
                            font.letterSpacing: 2.0
                        }
                    }
                }

                Text {
                    text: "ARCHIVE"
                    color: root.muted
                    font.pixelSize: 9
                    font.weight: Font.DemiBold
                    font.letterSpacing: 1.6
                    Layout.leftMargin: 12
                    Layout.bottomMargin: 8
                }
                NavButton { viewKey: "overview"; indexLabel: "01"; caption: "Overview"; Layout.fillWidth: true }
                NavButton { viewKey: "library"; indexLabel: "02"; caption: "Library"; Layout.fillWidth: true }
                NavButton { viewKey: "operations"; indexLabel: "03"; caption: "Operations"; Layout.fillWidth: true }
                NavButton { viewKey: "system"; indexLabel: "04"; caption: "System"; Layout.fillWidth: true }

                Item { Layout.fillHeight: true }

                Rectangle {
                    Layout.fillWidth: true
                    implicitHeight: 86
                    radius: 8
                    color: root.shell
                    border.color: root.line
                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 13
                        spacing: 5
                        RowLayout {
                            Rectangle {
                                width: 7
                                height: 7
                                radius: 4
                                color: backend.databaseHealth.state === "healthy" ? root.jade : root.ember
                            }
                            Text {
                                text: backend.databaseHealth.state === "healthy" ? "LOCAL · HEALTHY" : "LOCAL · ATTENTION"
                                color: root.bone
                                font.pixelSize: 9
                                font.weight: Font.DemiBold
                                font.letterSpacing: 1.0
                            }
                        }
                        Text {
                            text: "No cloud connection\nNo production watcher"
                            color: root.muted
                            font.pixelSize: 10
                            lineHeight: 1.25
                        }
                    }
                }
                Text {
                    text: "Beacon " + backend.applicationVersion
                    color: root.muted
                    font.family: "Cascadia Mono"
                    font.pixelSize: 9
                    Layout.topMargin: 12
                    Layout.bottomMargin: 2
                    Layout.alignment: Qt.AlignHCenter
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: root.shell

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 66
                    color: root.shell
                    border.color: root.line
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 28
                        anchors.rightMargin: 26
                        spacing: 16
                        ColumnLayout {
                            spacing: 0
                            Text {
                                text: backend.currentView === "overview" ? "Archive overview"
                                      : backend.currentView === "library" ? "Asset library"
                                      : backend.currentView === "operations" ? "Operation ledger"
                                      : "System & recovery"
                                color: root.bone
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                            }
                            Text {
                                text: "Refreshed " + backend.lastRefresh
                                color: root.muted
                                font.pixelSize: 10
                            }
                        }
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            implicitWidth: statusHeader.implicitWidth + 22
                            implicitHeight: 28
                            radius: 14
                            color: Qt.rgba(0.42, 0.67, 0.51, 0.12)
                            border.color: Qt.rgba(0.42, 0.67, 0.51, 0.35)
                            Text {
                                id: statusHeader
                                anchors.centerIn: parent
                                text: backend.databaseHealth.stateLabel || "Checking…"
                                color: backend.databaseHealth.state === "healthy" ? root.jade : root.ember
                                font.pixelSize: 10
                                font.weight: Font.DemiBold
                            }
                        }
                        PrimaryButton {
                            text: "Refresh"
                            quiet: true
                            onClicked: backend.refresh()
                        }
                    }
                }

                Rectangle {
                    visible: backend.statusMessage.length > 0
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? 38 : 0
                    color: backend.statusKind === "error" ? Qt.rgba(0.77, 0.40, 0.35, 0.18)
                         : backend.statusKind === "success" ? Qt.rgba(0.42, 0.67, 0.51, 0.16)
                         : Qt.rgba(0.39, 0.68, 0.69, 0.14)
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 28
                        anchors.rightMargin: 22
                        Text {
                            text: backend.statusMessage
                            color: root.bone
                            font.pixelSize: 11
                            elide: Text.ElideRight
                            Layout.fillWidth: true
                        }
                        ToolButton {
                            text: "×"
                            onClicked: backend.clearStatus()
                            contentItem: Text {
                                text: "×"
                                color: root.muted
                                font.pixelSize: 18
                                horizontalAlignment: Text.AlignHCenter
                            }
                            background: Item {}
                        }
                    }
                }

                StackLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    currentIndex: backend.currentView === "overview" ? 0
                                  : backend.currentView === "library" ? 1
                                  : backend.currentView === "operations" ? 2 : 3

                    // Overview
                    Item {
                        ScrollView {
                            anchors.fill: parent
                            clip: true
                            contentWidth: availableWidth
                            ColumnLayout {
                                width: parent.width
                                spacing: 18
                                anchors.margins: 26
                                GridLayout {
                                    Layout.fillWidth: true
                                    columns: 4
                                    columnSpacing: 12
                                    MetricCard {
                                        Layout.fillWidth: true
                                        eyebrow: "Cataloged assets"
                                        value: backend.summary.assetsLabel || "0"
                                        note: (backend.summary.locationsLabel || "0") + " observed locations"
                                        accentColor: root.atlasBright
                                    }
                                    MetricCard {
                                        Layout.fillWidth: true
                                        eyebrow: "Indexed volume"
                                        value: backend.summary.storageLabel || "0 B"
                                        note: "Metadata only · originals untouched"
                                        accentColor: root.brass
                                    }
                                    MetricCard {
                                        Layout.fillWidth: true
                                        eyebrow: "Duplicate groups"
                                        value: backend.summary.duplicatesLabel || "0"
                                        note: "Same content, multiple locations"
                                        accentColor: root.atlasBright
                                    }
                                    MetricCard {
                                        Layout.fillWidth: true
                                        eyebrow: "Current failures"
                                        value: backend.summary.failuresLabel || "0"
                                        note: backend.summary.failures > 0
                                              ? "Latest intake and analysis jobs"
                                              : "No retryable failures"
                                        accentColor: backend.summary.failures > 0 ? root.ember : root.jade
                                    }
                                }

                                Rectangle {
                                    id: intakeCard
                                    objectName: "intakeCard"
                                    Layout.fillWidth: true
                                    Layout.preferredHeight:
                                        backend.analysisReadiness.analysisHasJob === true
                                        ? 540 : 472
                                    radius: 10
                                    color: root.panel
                                    border.color: root.line
                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 18
                                        spacing: 12
                                        RowLayout {
                                            Layout.fillWidth: true
                                            PanelTitle {
                                                eyebrow: "Archive intake"
                                                title: "Catalog operations"
                                            }
                                            Item { Layout.fillWidth: true }
                                            Text {
                                                text: (backend.intakeSummary.activeLabel || "0")
                                                      + " ACTIVE  ·  "
                                                      + (backend.intakeSummary.failedLabel || "0")
                                                      + " FAILED FILES"
                                                color: backend.intakeSummary.failed > 0
                                                       ? root.ember : root.muted
                                                font.pixelSize: 9
                                                font.weight: Font.DemiBold
                                                font.letterSpacing: 0.9
                                            }
                                            PrimaryButton {
                                                objectName: "analyzeCatalogButton"
                                                text: "Analyze catalog"
                                                quiet: true
                                                enabled: !backend.busy
                                                onClicked: localAnalysisDialog.open()
                                            }
                                            PrimaryButton {
                                                objectName: "cancelAnalysisButton"
                                                text: "Cancel analysis"
                                                quiet: true
                                                visible: backend.analysisReadiness.analysisCanCancel === true
                                                enabled: backend.analysisReadiness.analysisCanCancel === true
                                                onClicked: backend.cancelLocalCatalogAnalysis()
                                            }
                                            PrimaryButton {
                                                objectName: "newIntakeButton"
                                                text: "New intake"
                                                enabled: !backend.busy
                                                onClicked: newIntakeDialog.open()
                                            }
                                        }
                                        Rectangle {
                                            Layout.fillWidth: true
                                            implicitHeight: 42
                                            radius: 7
                                            color: root.shell
                                            border.color: root.line
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 13
                                                anchors.rightMargin: 13
                                                spacing: 10
                                                Rectangle {
                                                    width: 7
                                                    height: 7
                                                    radius: 4
                                                    color: backend.selectedIntakeJob.state === "running"
                                                           ? root.jade : root.atlasBright
                                                }
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: "Durable, recursive, file-by-file cataloging. Originals remain in place; a job can resume without repeating completed files."
                                                    color: root.muted
                                                    font.pixelSize: 10
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Layout.fillHeight: true
                                            spacing: 12
                                            Rectangle {
                                                Layout.preferredWidth: 390
                                                Layout.fillHeight: true
                                                radius: 8
                                                color: root.shell
                                                border.color: root.line
                                                ListView {
                                                    id: intakeJobList
                                                    anchors.fill: parent
                                                    anchors.margins: 8
                                                    clip: true
                                                    spacing: 7
                                                    model: backend.intakeJobs
                                                    delegate: Rectangle {
                                                        required property string jobId
                                                        required property string sourceRoot
                                                        required property string state
                                                        required property string stateLabel
                                                        required property real progress
                                                        required property string progressLabel
                                                        required property string countLabel
                                                        required property string updatedLabel
                                                        width: ListView.view.width
                                                        height: 92
                                                        radius: 7
                                                        color: backend.selectedIntakeJob.id === jobId
                                                               ? Qt.rgba(0.29, 0.55, 0.57, 0.18)
                                                               : intakeHover.containsMouse
                                                                 ? root.panelRaised : root.panel
                                                        border.color: backend.selectedIntakeJob.id === jobId
                                                                      ? root.atlas : root.line
                                                        MouseArea {
                                                            id: intakeHover
                                                            anchors.fill: parent
                                                            hoverEnabled: true
                                                            onClicked: backend.selectIntakeJob(jobId)
                                                        }
                                                        ColumnLayout {
                                                            anchors.fill: parent
                                                            anchors.margins: 10
                                                            spacing: 3
                                                            RowLayout {
                                                                Layout.fillWidth: true
                                                                Text {
                                                                    Layout.fillWidth: true
                                                                    text: sourceRoot
                                                                    color: root.bone
                                                                    font.family: "Cascadia Mono"
                                                                    font.pixelSize: 10
                                                                    elide: Text.ElideMiddle
                                                                }
                                                                Text {
                                                                    text: stateLabel.toUpperCase()
                                                                    color: state === "complete" ? root.jade
                                                                         : state === "failed" || state === "partial"
                                                                           ? root.ember
                                                                           : state === "running" ? root.atlasBright
                                                                           : root.brass
                                                                    font.pixelSize: 8
                                                                    font.weight: Font.DemiBold
                                                                    font.letterSpacing: 0.8
                                                                }
                                                            }
                                                            IntakeProgress {
                                                                Layout.fillWidth: true
                                                                value: progress
                                                            }
                                                            RowLayout {
                                                                Layout.fillWidth: true
                                                                Text {
                                                                    Layout.fillWidth: true
                                                                    text: countLabel
                                                                    color: root.muted
                                                                    font.pixelSize: 9
                                                                    elide: Text.ElideRight
                                                                }
                                                                Text {
                                                                    text: progressLabel
                                                                    color: root.bone
                                                                    font.family: "Cascadia Mono"
                                                                    font.pixelSize: 9
                                                                }
                                                            }
                                                            Text {
                                                                text: updatedLabel
                                                                color: root.muted
                                                                font.pixelSize: 8
                                                            }
                                                        }
                                                    }
                                                    Text {
                                                        anchors.centerIn: parent
                                                        width: Math.min(270, parent.width - 30)
                                                        visible: parent.count === 0
                                                        text: "No intake jobs yet. Create a bounded snapshot when you are ready to test a folder."
                                                        color: root.muted
                                                        font.pixelSize: 11
                                                        lineHeight: 1.35
                                                        wrapMode: Text.WordWrap
                                                        horizontalAlignment: Text.AlignHCenter
                                                    }
                                                }
                                            }
                                            Rectangle {
                                                Layout.fillWidth: true
                                                Layout.fillHeight: true
                                                radius: 8
                                                color: root.shell
                                                border.color: root.line
                                                ColumnLayout {
                                                    anchors.fill: parent
                                                    anchors.margins: 14
                                                    spacing: 9
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        ColumnLayout {
                                                            Layout.fillWidth: true
                                                            spacing: 2
                                                            Text {
                                                                Layout.fillWidth: true
                                                                text: backend.selectedIntakeJob.id
                                                                      ? backend.selectedIntakeJob.stateLabel
                                                                        + " intake"
                                                                      : "Select an intake job"
                                                                color: root.bone
                                                                font.family: "Georgia"
                                                                font.pixelSize: 19
                                                                elide: Text.ElideRight
                                                            }
                                                            Text {
                                                                text: backend.selectedIntakeJob.id
                                                                      ? (backend.selectedIntakeJob.modeLabel || "CATALOG ONLY")
                                                                        + "  ·  "
                                                                        + (backend.selectedIntakeJob.itemLimitLabel || "")
                                                                      : "RESTARTABLE LOCAL OPERATION"
                                                                color: root.brass
                                                                font.pixelSize: 8
                                                                font.weight: Font.DemiBold
                                                                font.letterSpacing: 1.0
                                                            }
                                                        }
                                                        Text {
                                                            text: backend.selectedIntakeJob.progressLabel || "0%"
                                                            color: root.atlasBright
                                                            font.family: "Cascadia Mono"
                                                            font.pixelSize: 22
                                                            font.weight: Font.DemiBold
                                                        }
                                                    }
                                                    Text {
                                                        Layout.fillWidth: true
                                                        text: backend.selectedIntakeJob.sourceRoot
                                                              || "Create a job to snapshot an approved intake folder."
                                                        color: root.bone
                                                        font.family: "Cascadia Mono"
                                                        font.pixelSize: 10
                                                        elide: Text.ElideMiddle
                                                    }
                                                    IntakeProgress {
                                                        Layout.fillWidth: true
                                                        value: backend.selectedIntakeJob.progress || 0
                                                    }
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        Text {
                                                            Layout.fillWidth: true
                                                            text: backend.selectedIntakeJob.countLabel
                                                                  || "No snapshot selected"
                                                            color: root.muted
                                                            font.pixelSize: 10
                                                        }
                                                        Text {
                                                            text: backend.selectedIntakeJob.sizeLabel || ""
                                                            color: root.muted
                                                            font.family: "Cascadia Mono"
                                                            font.pixelSize: 9
                                                        }
                                                    }
                                                    Rectangle {
                                                        Layout.fillWidth: true
                                                        height: 1
                                                        color: root.line
                                                        visible: backend.analysisReadiness.analysisHasJob === true
                                                    }
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        visible: backend.analysisReadiness.analysisHasJob === true
                                                        Text {
                                                            Layout.fillWidth: true
                                                            text: "CATALOG ANALYSIS  ·  "
                                                                  + (backend.analysisReadiness.analysisStateLabel || "Not started")
                                                            color: root.brass
                                                            font.pixelSize: 8
                                                            font.weight: Font.DemiBold
                                                            font.letterSpacing: 0.9
                                                        }
                                                        Text {
                                                            text: backend.analysisReadiness.analysisProgressLabel || "0%"
                                                            color: root.atlasBright
                                                            font.family: "Cascadia Mono"
                                                            font.pixelSize: 14
                                                            font.weight: Font.DemiBold
                                                        }
                                                    }
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        visible: backend.analysisReadiness.analysisHasJob === true
                                                                 && (backend.analysisReadiness.analysisCanCancel === true
                                                                     || backend.analysisReadiness.analysisCanRetry === true)
                                                        PrimaryButton {
                                                            text: "Cancel analysis"
                                                            quiet: true
                                                            visible: backend.analysisReadiness.analysisCanCancel === true
                                                            enabled: visible
                                                            onClicked: backend.cancelLocalCatalogAnalysis()
                                                        }
                                                        PrimaryButton {
                                                            objectName: "retryAnalysisFailuresButton"
                                                            text: "Retry analysis failures"
                                                            quiet: true
                                                            visible: backend.analysisReadiness.analysisCanRetry === true
                                                            enabled: visible && !backend.busy
                                                            onClicked: backend.retryLocalCatalogAnalysisFailures()
                                                        }
                                                        Item { Layout.fillWidth: true }
                                                    }
                                                    IntakeProgress {
                                                        Layout.fillWidth: true
                                                        visible: backend.analysisReadiness.analysisHasJob === true
                                                        value: backend.analysisReadiness.analysisProgress || 0
                                                    }
                                                    Text {
                                                        objectName: "analysisStageLine"
                                                        Layout.fillWidth: true
                                                        visible: backend.analysisReadiness.analysisHasJob === true
                                                        text: backend.analysisReadiness.analysisStageLabel
                                                              || "ANALYSIS NOT STARTED"
                                                        color: backend.analysisReadiness.analysisStageActive
                                                               ? root.atlasBright : root.muted
                                                        font.family: "Cascadia Mono"
                                                        font.pixelSize: 9
                                                        font.weight: Font.DemiBold
                                                        font.letterSpacing: 0.7
                                                        elide: Text.ElideMiddle
                                                    }
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        visible: backend.analysisReadiness.analysisHasJob === true
                                                        Text {
                                                            Layout.fillWidth: true
                                                            text: backend.analysisReadiness.analysisCountLabel || ""
                                                            color: root.muted
                                                            font.pixelSize: 10
                                                        }
                                                        Text {
                                                            text: backend.analysisReadiness.analysisFailedLabel || ""
                                                            color: root.muted
                                                            font.pixelSize: 9
                                                        }
                                                    }
                                                    Rectangle {
                                                        Layout.fillWidth: true
                                                        implicitHeight: 48
                                                        radius: 7
                                                        color: root.ink
                                                        border.color: root.line
                                                        Text {
                                                            anchors.fill: parent
                                                            anchors.margins: 10
                                                            text: backend.selectedIntakeJob.currentPath
                                                                  ? "CURRENT  ·  "
                                                                    + backend.selectedIntakeJob.currentPath
                                                                  : backend.selectedIntakeJob.failureSummary
                                                                    ? backend.selectedIntakeJob.failureSummary
                                                                    : "Waiting for an action. Completed files will not be repeated."
                                                            color: backend.selectedIntakeJob.failureSummary
                                                                   ? root.ember : root.muted
                                                            font.family: "Cascadia Mono"
                                                            font.pixelSize: 9
                                                            elide: Text.ElideMiddle
                                                            verticalAlignment: Text.AlignVCenter
                                                        }
                                                    }
                                                    Item { Layout.fillHeight: true }
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        Layout.minimumHeight: 38
                                                        Layout.bottomMargin: 2
                                                        spacing: 8
                                                        PrimaryButton {
                                                            text: backend.selectedIntakeJob.state === "paused"
                                                                  || backend.selectedIntakeJob.state === "cancelled"
                                                                  ? "Resume" : "Start"
                                                            enabled: !backend.busy
                                                                     && backend.selectedIntakeJob.canStart === true
                                                            onClicked: backend.startSelectedIntakeJob()
                                                        }
                                                        PrimaryButton {
                                                            text: "Cancel"
                                                            quiet: true
                                                            enabled: backend.selectedIntakeJob.canCancel === true
                                                            onClicked: backend.cancelSelectedIntakeJob()
                                                        }
                                                        PrimaryButton {
                                                            text: "Retry failures"
                                                            quiet: true
                                                            enabled: !backend.busy
                                                                     && backend.selectedIntakeJob.canRetry === true
                                                            onClicked: backend.retrySelectedIntakeJob()
                                                        }
                                                        Item { Layout.fillWidth: true }
                                                        Text {
                                                            text: backend.selectedIntakeJob.snapshotSha256
                                                                  ? "SNAPSHOT  "
                                                                    + backend.selectedIntakeJob.snapshotSha256.substring(0, 12)
                                                                  : ""
                                                            color: root.muted
                                                            font.family: "Cascadia Mono"
                                                            font.pixelSize: 8
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }

                                Rectangle {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 548
                                    radius: 10
                                    color: root.panel
                                    border.color: root.line
                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 18
                                        spacing: 12
                                        RowLayout {
                                            Layout.fillWidth: true
                                            PanelTitle {
                                                eyebrow: "Beacon desk"
                                                title: "Open conversations"
                                            }
                                            Item { Layout.fillWidth: true }
                                            ColumnLayout {
                                                spacing: 2
                                                Text {
                                                    Layout.alignment: Qt.AlignRight
                                                    text: (backend.beaconDeskSummary.awaitingLabel || "0")
                                                          + " WAITING FOR YOU  ·  "
                                                          + (backend.beaconDeskSummary.queuedLabel || "0")
                                                          + " QUEUED"
                                                    color: root.muted
                                                    font.pixelSize: 9
                                                    font.weight: Font.DemiBold
                                                    font.letterSpacing: 0.8
                                                }
                                                Text {
                                                    Layout.alignment: Qt.AlignRight
                                                    text: backend.beaconDeskSummary.connectionLabel
                                                          || "SAVED LOCALLY"
                                                    color: root.jade
                                                    font.pixelSize: 9
                                                    font.weight: Font.DemiBold
                                                    font.letterSpacing: 1.1
                                                }
                                            }
                                            PrimaryButton {
                                                text: "New request"
                                                onClicked: newRequestDialog.open()
                                            }
                                        }
                                        Rectangle {
                                            Layout.fillWidth: true
                                            implicitHeight: 42
                                            radius: 7
                                            color: root.shell
                                            border.color: root.line
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 13
                                                anchors.rightMargin: 13
                                                spacing: 10
                                                Rectangle {
                                                    width: 7
                                                    height: 7
                                                    radius: 4
                                                    color: root.brass
                                                }
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: "Messages persist in this catalog. Beacon reviews queued replies during an analysis session; the app does not pretend a worker is continuously online."
                                                    color: root.muted
                                                    font.pixelSize: 10
                                                    elide: Text.ElideRight
                                                }
                                            }
                                        }
                                        RowLayout {
                                            Layout.fillWidth: true
                                            Layout.fillHeight: true
                                            spacing: 12
                                            Rectangle {
                                                Layout.preferredWidth: 392
                                                Layout.fillHeight: true
                                                radius: 8
                                                color: root.shell
                                                border.color: root.line
                                                ListView {
                                                    id: beaconThreadList
                                                    anchors.fill: parent
                                                    anchors.margins: 8
                                                    clip: true
                                                    spacing: 7
                                                    model: backend.beaconThreads
                                                    delegate: Rectangle {
                                                        required property string threadId
                                                        required property string subject
                                                        required property string kindLabel
                                                        required property string priority
                                                        required property string state
                                                        required property string stateLabel
                                                        required property string preview
                                                        required property string updatedLabel
                                                        required property bool requiresApproval
                                                        width: ListView.view.width
                                                        height: 96
                                                        radius: 7
                                                        color: backend.selectedBeaconThread.id === threadId
                                                               ? Qt.rgba(0.29, 0.55, 0.57, 0.18)
                                                               : beaconThreadHover.containsMouse
                                                                 ? root.panelRaised : root.panel
                                                        border.color: backend.selectedBeaconThread.id === threadId
                                                                      ? root.atlas : root.line
                                                        MouseArea {
                                                            id: beaconThreadHover
                                                            anchors.fill: parent
                                                            hoverEnabled: true
                                                            onClicked: backend.selectBeaconThread(threadId)
                                                        }
                                                        ColumnLayout {
                                                            anchors.fill: parent
                                                            anchors.margins: 10
                                                            spacing: 3
                                                            RowLayout {
                                                                Layout.fillWidth: true
                                                                Text {
                                                                    text: kindLabel.toUpperCase()
                                                                    color: requiresApproval
                                                                           ? root.brass : root.atlasBright
                                                                    font.pixelSize: 8
                                                                    font.weight: Font.DemiBold
                                                                    font.letterSpacing: 1.0
                                                                }
                                                                Item { Layout.fillWidth: true }
                                                                Rectangle {
                                                                    width: 6
                                                                    height: 6
                                                                    radius: 3
                                                                    color: state === "awaiting_human"
                                                                           ? root.brass : root.atlasBright
                                                                }
                                                                Text {
                                                                    text: stateLabel.toUpperCase()
                                                                    color: root.muted
                                                                    font.pixelSize: 8
                                                                    font.weight: Font.DemiBold
                                                                }
                                                            }
                                                            Text {
                                                                Layout.fillWidth: true
                                                                text: subject
                                                                color: root.bone
                                                                font.pixelSize: 12
                                                                font.weight: Font.DemiBold
                                                                elide: Text.ElideRight
                                                            }
                                                            Text {
                                                                Layout.fillWidth: true
                                                                text: preview
                                                                color: root.muted
                                                                font.pixelSize: 9
                                                                elide: Text.ElideRight
                                                            }
                                                            Text {
                                                                text: updatedLabel
                                                                color: root.muted
                                                                font.pixelSize: 8
                                                            }
                                                        }
                                                    }
                                                    Text {
                                                        anchors.centerIn: parent
                                                        width: Math.min(260, parent.width - 30)
                                                        visible: parent.count === 0
                                                        text: "No open conversations. Start a new request whenever you need Beacon."
                                                        color: root.muted
                                                        font.pixelSize: 11
                                                        lineHeight: 1.35
                                                        wrapMode: Text.WordWrap
                                                        horizontalAlignment: Text.AlignHCenter
                                                    }
                                                }
                                            }
                                            Rectangle {
                                                Layout.fillWidth: true
                                                Layout.fillHeight: true
                                                radius: 8
                                                color: root.shell
                                                border.color: root.line
                                                ColumnLayout {
                                                    anchors.fill: parent
                                                    anchors.margins: 14
                                                    spacing: 10
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        ColumnLayout {
                                                            Layout.fillWidth: true
                                                            spacing: 2
                                                            Text {
                                                                Layout.fillWidth: true
                                                                text: backend.selectedBeaconThread.subject
                                                                      || "Select a conversation"
                                                                color: root.bone
                                                                font.family: "Georgia"
                                                                font.pixelSize: 18
                                                                elide: Text.ElideRight
                                                            }
                                                            Text {
                                                                text: backend.selectedBeaconThread.id
                                                                      ? (backend.selectedBeaconThread.kindLabel || "Conversation").toUpperCase()
                                                                        + "  ·  "
                                                                        + (backend.selectedBeaconThread.stateLabel || "")
                                                                      : "BEACON DESK"
                                                                color: backend.selectedBeaconThread.state === "awaiting_human"
                                                                       ? root.brass : root.muted
                                                                font.pixelSize: 8
                                                                font.weight: Font.DemiBold
                                                                font.letterSpacing: 1.0
                                                            }
                                                        }
                                                        PrimaryButton {
                                                            visible: backend.selectedBeaconThread.id !== undefined
                                                            text: "Resolve"
                                                            quiet: true
                                                            onClicked: backend.resolveBeaconThread()
                                                        }
                                                    }
                                                    Rectangle {
                                                        visible: backend.selectedBeaconThread.requiresApproval === true
                                                        Layout.fillWidth: true
                                                        implicitHeight: visible ? 38 : 0
                                                        radius: 6
                                                        color: Qt.rgba(0.76, 0.60, 0.35, 0.10)
                                                        border.color: Qt.rgba(0.76, 0.60, 0.35, 0.28)
                                                        Text {
                                                            anchors.fill: parent
                                                            anchors.margins: 10
                                                            text: "APPROVAL REQUEST  ·  Your reply records guidance only; it cannot move or change files."
                                                            color: root.brass
                                                            font.pixelSize: 9
                                                            font.weight: Font.DemiBold
                                                            elide: Text.ElideRight
                                                        }
                                                    }
                                                    ListView {
                                                        id: beaconMessageList
                                                        Layout.fillWidth: true
                                                        Layout.fillHeight: true
                                                        clip: true
                                                        spacing: 8
                                                        model: backend.beaconMessages
                                                        onCountChanged: positionViewAtEnd()
                                                        delegate: Rectangle {
                                                            required property string author
                                                            required property string authorLabel
                                                            required property string body
                                                            required property string timeLabel
                                                            required property var resultCards
                                                            width: ListView.view.width
                                                            height: messageColumn.implicitHeight + 20
                                                            radius: 7
                                                            color: author === "human"
                                                                   ? Qt.rgba(0.29, 0.55, 0.57, 0.14)
                                                                   : root.panel
                                                            border.color: root.line
                                                            ColumnLayout {
                                                                id: messageColumn
                                                                anchors.fill: parent
                                                                anchors.margins: 10
                                                                spacing: 4
                                                                RowLayout {
                                                                    Layout.fillWidth: true
                                                                    Text {
                                                                        text: authorLabel
                                                                        color: author === "human"
                                                                               ? root.atlasBright : root.brass
                                                                        font.pixelSize: 8
                                                                        font.weight: Font.DemiBold
                                                                        font.letterSpacing: 1.0
                                                                    }
                                                                    Item { Layout.fillWidth: true }
                                                                    Text {
                                                                        text: timeLabel
                                                                        color: root.muted
                                                                        font.pixelSize: 8
                                                                    }
                                                                }
                                                                Text {
                                                                    id: messageBody
                                                                    Layout.fillWidth: true
                                                                    text: body
                                                                    color: root.bone
                                                                    font.pixelSize: 11
                                                                    lineHeight: 1.35
                                                                    wrapMode: Text.WordWrap
                                                                }
                                                                Repeater {
                                                                    model: resultCards || []
                                                                    delegate: GroundedResultCard {
                                                                        required property var modelData
                                                                        Layout.fillWidth: true
                                                                        assetId: modelData.assetId
                                                                        displayTitle: modelData.displayTitle
                                                                        filename: modelData.filename
                                                                        path: modelData.path
                                                                        atlasUri: modelData.atlasUri
                                                                        reason: modelData.reason
                                                                        availabilityLabel: modelData.availabilityLabel
                                                                        sizeLabel: modelData.sizeLabel
                                                                        thumbnailUrl: modelData.thumbnailUrl
                                                                        available: modelData.available
                                                                    }
                                                                }
                                                            }
                                                        }
                                                    }
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        Layout.preferredHeight: 72
                                                        Layout.minimumHeight: 72
                                                        Layout.maximumHeight: 72
                                                        Layout.fillHeight: false
                                                        spacing: 8
                                                        ScrollView {
                                                            Layout.fillWidth: true
                                                            Layout.preferredHeight: 72
                                                            Layout.minimumHeight: 72
                                                            Layout.maximumHeight: 72
                                                            clip: true
                                                            TextArea {
                                                                id: beaconReplyField
                                                                objectName: "beaconReplyField"
                                                                enabled: backend.selectedBeaconThread.id !== undefined
                                                                placeholderText: backend.selectedBeaconThread.id !== undefined
                                                                                 ? "Reply in plain English…"
                                                                                 : "Select a conversation to reply"
                                                                color: root.bone
                                                                placeholderTextColor: root.muted
                                                                selectionColor: root.atlas
                                                                selectByMouse: true
                                                                wrapMode: TextEdit.Wrap
                                                                leftPadding: 11
                                                                rightPadding: 11
                                                                topPadding: 9
                                                                bottomPadding: 9
                                                                background: Rectangle {
                                                                    radius: 7
                                                                    color: root.ink
                                                                    border.color: beaconReplyField.activeFocus
                                                                                  ? root.atlasBright : root.line
                                                                }
                                                            }
                                                        }
                                                        PrimaryButton {
                                                            Layout.alignment: Qt.AlignBottom
                                                            text: "Send reply"
                                                            enabled: backend.selectedBeaconThread.id !== undefined
                                                                     && beaconReplyField.text.trim().length > 0
                                                                     && beaconReplyField.text.length <= 8000
                                                            onClicked: {
                                                                backend.replyToBeaconThread(beaconReplyField.text)
                                                                beaconReplyField.text = ""
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }

                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 430
                                    spacing: 14
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        radius: 10
                                        color: root.panel
                                        border.color: root.line
                                        ColumnLayout {
                                            anchors.fill: parent
                                            anchors.margins: 18
                                            spacing: 12
                                            RowLayout {
                                                Layout.fillWidth: true
                                                PanelTitle { eyebrow: "Collection"; title: "Recently observed" }
                                                Item { Layout.fillWidth: true }
                                                PrimaryButton {
                                                    text: "Open library"
                                                    quiet: true
                                                    onClicked: backend.setCurrentView("library")
                                                }
                                            }
                                            ListView {
                                                Layout.fillWidth: true
                                                Layout.fillHeight: true
                                                clip: true
                                                spacing: 7
                                                model: backend.assets
                                                delegate: Rectangle {
                                                    required property string assetId
                                                    required property string filename
                                                    required property string displayTitle
                                                    required property string kindLabel
                                                    required property string sizeLabel
                                                    required property string path
                                                    required property string thumbnailUrl
                                                    width: ListView.view.width
                                                    height: 58
                                                    radius: 7
                                                    color: overviewHover.containsMouse ? root.panelRaised : root.shell
                                                    border.color: root.line
                                                    MouseArea {
                                                        id: overviewHover
                                                        anchors.fill: parent
                                                        hoverEnabled: true
                                                        onClicked: {
                                                            backend.selectAsset(assetId)
                                                            backend.setCurrentView("library")
                                                        }
                                                    }
                                                    RowLayout {
                                                        anchors.fill: parent
                                                        anchors.margins: 11
                                                        spacing: 12
                                                        Rectangle {
                                                            clip: true
                                                            width: 34
                                                            height: 34
                                                            radius: 6
                                                            color: Qt.rgba(0.29, 0.55, 0.57, 0.15)
                                                            Image {
                                                                anchors.fill: parent
                                                                source: thumbnailUrl
                                                                visible: thumbnailUrl.length > 0
                                                                fillMode: Image.PreserveAspectCrop
                                                                asynchronous: true
                                                            }
                                                            Text {
                                                                anchors.centerIn: parent
                                                                visible: thumbnailUrl.length === 0
                                                                text: kindLabel.substring(0, 2).toUpperCase()
                                                                color: root.atlasBright
                                                                font.family: "Cascadia Mono"
                                                                font.pixelSize: 9
                                                                font.weight: Font.DemiBold
                                                            }
                                                        }
                                                        ColumnLayout {
                                                            Layout.fillWidth: true
                                                            spacing: 1
                                                            Text {
                                                                text: displayTitle
                                                                color: root.bone
                                                                font.pixelSize: 12
                                                                font.weight: Font.DemiBold
                                                                elide: Text.ElideRight
                                                                Layout.fillWidth: true
                                                            }
                                                            Text {
                                                                text: path
                                                                color: root.muted
                                                                font.family: "Cascadia Mono"
                                                                font.pixelSize: 9
                                                                elide: Text.ElideMiddle
                                                                Layout.fillWidth: true
                                                            }
                                                        }
                                                        Text {
                                                            text: sizeLabel
                                                            color: root.muted
                                                            font.pixelSize: 10
                                                        }
                                                    }
                                                }
                                                Text {
                                                    anchors.centerIn: parent
                                                    visible: parent.count === 0
                                                    text: "The catalog is ready for a synthetic fixture."
                                                    color: root.muted
                                                    font.pixelSize: 12
                                                }
                                            }
                                        }
                                    }
                                    Rectangle {
                                        Layout.preferredWidth: 360
                                        Layout.fillHeight: true
                                        radius: 10
                                        color: root.panel
                                        border.color: root.line
                                        ColumnLayout {
                                            anchors.fill: parent
                                            anchors.margins: 18
                                            spacing: 12
                                            PanelTitle { eyebrow: "Audit"; title: "Latest signals" }
                                            ListView {
                                                Layout.fillWidth: true
                                                Layout.fillHeight: true
                                                clip: true
                                                spacing: 12
                                                model: backend.events
                                                delegate: RowLayout {
                                                    required property string state
                                                    required property string message
                                                    required property string timeLabel
                                                    width: ListView.view.width
                                                    spacing: 10
                                                    Rectangle {
                                                        width: 7
                                                        height: 7
                                                        radius: 4
                                                        color: state === "failed" ? root.ember : root.jade
                                                        Layout.alignment: Qt.AlignTop
                                                        Layout.topMargin: 5
                                                    }
                                                    ColumnLayout {
                                                        Layout.fillWidth: true
                                                        spacing: 2
                                                        Text {
                                                            text: message
                                                            color: root.bone
                                                            font.pixelSize: 11
                                                            wrapMode: Text.WordWrap
                                                            Layout.fillWidth: true
                                                        }
                                                        Text {
                                                            text: timeLabel
                                                            color: root.muted
                                                            font.pixelSize: 9
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Library
                    Item {
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 24
                            spacing: 14
                            Rectangle {
                                Layout.preferredWidth: 520
                                Layout.fillHeight: true
                                radius: 10
                                color: root.panel
                                border.color: root.line
                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 16
                                    spacing: 12
                                    RowLayout {
                                        Layout.fillWidth: true
                                        PanelTitle { eyebrow: "Permanent record"; title: "Asset library" }
                                        Item { Layout.fillWidth: true }
                                        Text {
                                            text: (backend.catalogLabel || "Catalog").toUpperCase()
                                                  + "  ·  "
                                                  + (backend.summary.assetsLabel || "0")
                                                  + " ASSETS"
                                            color: root.muted
                                            font.pixelSize: 9
                                            font.letterSpacing: 1.0
                                        }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8
                                        PrimaryButton {
                                            text: "Recents"
                                            quiet: backend.libraryMode !== "recents"
                                            onClicked: backend.setLibraryMode("recents")
                                        }
                                        PrimaryButton {
                                            text: "Explorer"
                                            quiet: backend.libraryMode !== "explorer"
                                            onClicked: backend.setLibraryMode("explorer")
                                        }
                                        Item { Layout.fillWidth: true }
                                        Text {
                                            text: "TYPE"
                                            color: root.muted
                                            font.pixelSize: 8
                                            font.letterSpacing: 1.0
                                        }
                                        ComboBox {
                                            id: libraryTypeFilter
                                            Layout.preferredWidth: 116
                                            implicitHeight: 34
                                            model: ["All", "Photos", "RAW", "Video", "Audio", "Other"]
                                            currentIndex: {
                                                var values = ["all", "photo", "raw", "video", "audio", "other"]
                                                return Math.max(0, values.indexOf(backend.libraryFileType))
                                            }
                                            onActivated: {
                                                var values = ["all", "photo", "raw", "video", "audio", "other"]
                                                backend.setLibraryFileType(values[currentIndex])
                                            }
                                        }
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        visible: backend.libraryMode === "explorer"
                                        spacing: 7
                                        RowLayout {
                                            Layout.fillWidth: true
                                            PrimaryButton {
                                                text: "Up"
                                                quiet: true
                                                enabled: backend.libraryPath.toLowerCase() !== "j:\\"
                                                onClicked: backend.libraryFolderUp()
                                            }
                                            Text {
                                                Layout.fillWidth: true
                                                text: backend.libraryPath
                                                color: root.atlasBright
                                                font.family: "Cascadia Mono"
                                                font.pixelSize: 9
                                                elide: Text.ElideMiddle
                                            }
                                            CheckBox {
                                                text: "Show hidden files"
                                                checked: backend.showHiddenLibraryFiles
                                                onClicked: backend.setShowHiddenLibraryFiles(checked)
                                            }
                                        }
                                        ListView {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: Math.min(contentHeight, 148)
                                            visible: count > 0
                                            clip: true
                                            spacing: 5
                                            model: backend.libraryFolders
                                            boundsBehavior: Flickable.StopAtBounds
                                            ScrollBar.vertical: ScrollBar {
                                                policy: ScrollBar.AsNeeded
                                            }
                                            delegate: Rectangle {
                                                required property string folderName
                                                required property string folderPath
                                                required property string countLabel
                                                width: ListView.view.width
                                                height: 34
                                                radius: 6
                                                color: folderMouse.containsMouse ? root.panelRaised : root.shell
                                                border.color: root.line
                                                Text {
                                                    anchors.left: parent.left
                                                    anchors.leftMargin: 11
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    text: "▸  " + folderName
                                                    color: root.bone
                                                    font.pixelSize: 10
                                                }
                                                Text {
                                                    anchors.right: parent.right
                                                    anchors.rightMargin: 11
                                                    anchors.verticalCenter: parent.verticalCenter
                                                    text: countLabel
                                                    color: root.muted
                                                    font.pixelSize: 9
                                                }
                                                MouseArea {
                                                    id: folderMouse
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                    onClicked: backend.openLibraryFolder(folderPath)
                                                }
                                            }
                                        }
                                    }
                                    TextField {
                                        id: searchField
                                        Layout.fillWidth: true
                                        implicitHeight: 42
                                        leftPadding: 14
                                        rightPadding: 14
                                        placeholderText: "Search filename, path, checksum, or ATLAS ID"
                                        color: root.bone
                                        placeholderTextColor: root.muted
                                        selectionColor: root.atlas
                                        selectByMouse: true
                                        font.pixelSize: 11
                                        background: Rectangle {
                                            radius: 7
                                            color: root.ink
                                            border.color: searchField.activeFocus ? root.atlasBright : root.line
                                        }
                                        Timer {
                                            id: searchTimer
                                            interval: 220
                                            repeat: false
                                            onTriggered: backend.setSearchQuery(searchField.text)
                                        }
                                        onTextEdited: searchTimer.restart()
                                    }
                                    ListView {
                                        id: libraryAssetList
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        clip: true
                                        spacing: 7
                                        model: backend.assets
                                        boundsBehavior: Flickable.StopAtBounds
                                        ScrollBar.vertical: ScrollBar {
                                            policy: ScrollBar.AlwaysOn
                                        }
                                        function syncSelectedIndex() {
                                            var selectedId = backend.selectedAsset.id || ""
                                            for (var row = 0; row < count; row++) {
                                                if (model.get(row).assetId === selectedId) {
                                                    currentIndex = row
                                                    positionViewAtIndex(
                                                        row, ListView.Contain
                                                    )
                                                    return
                                                }
                                            }
                                        }
                                        Component.onCompleted: syncSelectedIndex()
                                        Connections {
                                            target: backend
                                            function onSelectedAssetChanged() {
                                                libraryAssetList.syncSelectedIndex()
                                            }
                                        }
                                        delegate: Rectangle {
                                            required property int index
                                            required property string assetId
                                            required property string filename
                                            required property string displayTitle
                                            required property string kindLabel
                                            required property string sizeLabel
                                            required property string metaLine
                                            required property string path
                                            required property string thumbnailUrl
                                            required property bool analyzed
                                            required property string statusLabel
                                            width: ListView.view.width
                                            height: 78
                                            radius: 8
                                            color: backend.selectedAsset.id === assetId
                                                   ? Qt.rgba(0.29, 0.55, 0.57, 0.17)
                                                   : assetHover.containsMouse ? root.panelRaised : root.shell
                                            border.color: backend.selectedAsset.id === assetId
                                                          ? Qt.rgba(0.39, 0.68, 0.69, 0.45) : root.line
                                            Component.onCompleted: {
                                                if (thumbnailUrl.length === 0)
                                                    backend.prepareLibraryThumbnail(assetId)
                                            }
                                            Rectangle {
                                                z: 2
                                                anchors.top: parent.top
                                                anchors.bottom: parent.bottom
                                                anchors.right: parent.right
                                                width: 6
                                                radius: 3
                                                color: analyzed ? root.atlasBright : root.brass
                                                opacity: 0.95
                                                ToolTip.visible: statusHover.containsMouse
                                                ToolTip.text: statusLabel
                                                MouseArea {
                                                    id: statusHover
                                                    anchors.fill: parent
                                                    hoverEnabled: true
                                                }
                                            }
                                            MouseArea {
                                                id: assetHover
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                onClicked: {
                                                    libraryAssetList.currentIndex = index
                                                    backend.selectAsset(assetId)
                                                    assetHover.forceActiveFocus()
                                                }
                                            }
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.margins: 12
                                                spacing: 12
                                                Rectangle {
                                                    clip: true
                                                    width: 42
                                                    height: 42
                                                    radius: 7
                                                    color: root.ink
                                                    border.color: root.line
                                                    Image {
                                                        anchors.fill: parent
                                                        source: thumbnailUrl
                                                        visible: thumbnailUrl.length > 0
                                                        fillMode: Image.PreserveAspectCrop
                                                        asynchronous: true
                                                    }
                                                    Text {
                                                        anchors.centerIn: parent
                                                        visible: thumbnailUrl.length === 0
                                                        text: kindLabel.substring(0, 2).toUpperCase()
                                                        color: root.atlasBright
                                                        font.family: "Cascadia Mono"
                                                        font.pixelSize: 10
                                                        font.weight: Font.DemiBold
                                                    }
                                                }
                                                ColumnLayout {
                                                    Layout.fillWidth: true
                                                    spacing: 2
                                                    RowLayout {
                                                        Layout.fillWidth: true
                                                        Text {
                                                            text: displayTitle
                                                            color: root.bone
                                                            font.pixelSize: 12
                                                            font.weight: Font.DemiBold
                                                            elide: Text.ElideRight
                                                            Layout.fillWidth: true
                                                        }
                                                        Text {
                                                            text: sizeLabel
                                                            color: root.muted
                                                            font.pixelSize: 9
                                                        }
                                                    }
                                                    Text {
                                                        text: filename
                                                              + (metaLine.length > 0
                                                                 ? "  ·  " + metaLine : "")
                                                        color: root.brass
                                                        font.pixelSize: 9
                                                        elide: Text.ElideRight
                                                        Layout.fillWidth: true
                                                    }
                                                    Text {
                                                        text: path
                                                        color: root.muted
                                                        font.family: "Cascadia Mono"
                                                        font.pixelSize: 8
                                                        elide: Text.ElideMiddle
                                                        Layout.fillWidth: true
                                                    }
                                                }
                                            }
                                        }
                                        Text {
                                            anchors.centerIn: parent
                                            visible: parent.count === 0
                                            text: backend.searchQuery.length > 0 ? "No assets match this search." : "No assets cataloged yet."
                                            color: root.muted
                                            font.pixelSize: 12
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                radius: 10
                                color: root.panel
                                border.color: root.line
                                Flickable {
                                    id: assetDetailScroll
                                    anchors.fill: parent
                                    anchors.margins: 1
                                    clip: true
                                    property real availableWidth: width - 12
                                    contentWidth: availableWidth
                                    contentHeight: assetDetailColumn.implicitHeight
                                    boundsBehavior: Flickable.StopAtBounds
                                    flickableDirection: Flickable.VerticalFlick
                                    ScrollBar.vertical: ScrollBar {
                                        policy: ScrollBar.AlwaysOn
                                    }
                                    ColumnLayout {
                                        id: assetDetailColumn
                                        width: assetDetailScroll.availableWidth
                                        spacing: 0
                                        visible: backend.selectedAsset.id !== undefined
                                        Rectangle {
                                            Layout.fillWidth: true
                                            implicitHeight: 178
                                            color: root.panelRaised
                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.margins: 22
                                                spacing: 18
                                                ColumnLayout {
                                                    Layout.fillWidth: true
                                                    Layout.fillHeight: true
                                                    spacing: 7
                                                    Text {
                                                        text: (backend.selectedAsset.kindLabel || "File").toUpperCase()
                                                        color: root.brass
                                                        font.pixelSize: 9
                                                        font.weight: Font.DemiBold
                                                        font.letterSpacing: 1.4
                                                    }
                                                    Text {
                                                        text: backend.selectedAsset.displayTitle || ""
                                                        color: root.bone
                                                        font.family: "Georgia"
                                                        font.pixelSize: 25
                                                        elide: Text.ElideMiddle
                                                        Layout.fillWidth: true
                                                    }
                                                    Text {
                                                        text: backend.selectedAsset.atlas_uri || ""
                                                        color: root.atlasBright
                                                        font.family: "Cascadia Mono"
                                                        font.pixelSize: 10
                                                        elide: Text.ElideMiddle
                                                        Layout.fillWidth: true
                                                    }
                                                    RowLayout {
                                                        spacing: 8
                                                        PrimaryButton {
                                                            text: "Copy ID"
                                                            quiet: true
                                                            onClicked: backend.copyText(backend.selectedAsset.atlas_uri || "")
                                                        }
                                                        PrimaryButton {
                                                            text: "Location"
                                                            quiet: true
                                                            onClicked: backend.openFolder(backend.selectedAsset.primary_path || "")
                                                        }
                                                        PrimaryButton {
                                                            objectName: "detailPreviewButton"
                                                            text: "Preview"
                                                            onClicked: root.openSelectedPreview()
                                                        }
                                                    }
                                                }
                                                ColumnLayout {
                                                    Layout.preferredWidth: assetDetailScroll.availableWidth >= 620 ? 166 : 126
                                                    Layout.fillHeight: true
                                                    spacing: 7
                                                    Rectangle {
                                                        Layout.alignment: Qt.AlignRight
                                                        implicitWidth: indexedLabel.implicitWidth + 18
                                                        implicitHeight: 24
                                                        radius: 12
                                                        color: Qt.rgba(0.42, 0.67, 0.51, 0.12)
                                                        Text {
                                                            id: indexedLabel
                                                            anchors.centerIn: parent
                                                            text: "CATALOGED"
                                                            color: root.jade
                                                            font.pixelSize: 8
                                                            font.weight: Font.DemiBold
                                                            font.letterSpacing: 1.0
                                                        }
                                                    }
                                                    Rectangle {
                                                        Layout.fillWidth: true
                                                        Layout.fillHeight: true
                                                        radius: 9
                                                        color: root.ink
                                                        border.color: root.line
                                                        clip: true
                                                        Image {
                                                            anchors.fill: parent
                                                            source: backend.selectedAsset.thumbnailUrl || ""
                                                            visible: source.toString().length > 0
                                                            fillMode: Image.PreserveAspectCrop
                                                            asynchronous: true
                                                            cache: false
                                                        }
                                                        Column {
                                                            anchors.centerIn: parent
                                                            spacing: 4
                                                            visible: (backend.selectedAsset.thumbnailUrl || "").length === 0
                                                            Text {
                                                                anchors.horizontalCenter: parent.horizontalCenter
                                                                text: backend.selectedAsset.extensionLabel || "FILE"
                                                                color: root.atlasBright
                                                                font.family: "Cascadia Mono"
                                                                font.pixelSize: 18
                                                                font.weight: Font.DemiBold
                                                            }
                                                            Text {
                                                                anchors.horizontalCenter: parent.horizontalCenter
                                                                text: (backend.selectedAsset.previewKind || "file").toUpperCase()
                                                                color: root.muted
                                                                font.pixelSize: 8
                                                                font.weight: Font.DemiBold
                                                                font.letterSpacing: 1.2
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                        }
                                        ColumnLayout {
                                            Layout.fillWidth: true
                                            Layout.margins: 22
                                            spacing: 20
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 10
                                                Text {
                                                    text: "IDENTITY & PROVENANCE"
                                                    color: root.brass
                                                    font.pixelSize: 9
                                                    font.weight: Font.DemiBold
                                                    font.letterSpacing: 1.4
                                                }
                                                DetailLine { label: "Current path"; value: backend.selectedAsset.primary_path || "Unavailable"; mono: true }
                                                DetailLine { label: "SHA-256"; value: backend.selectedAsset.sha256 || ""; mono: true }
                                                DetailLine { label: "Observed"; value: backend.selectedAsset.lastSeenLabel || "" }
                                                DetailLine { label: "Locations"; value: String(backend.selectedAsset.location_count || 0) }
                                            }
                                            Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
                                            GridLayout {
                                                Layout.fillWidth: true
                                                columns: width >= 560 ? 2 : 1
                                                columnSpacing: 24
                                                rowSpacing: 12
                                                DetailLine { Layout.fillWidth: true; label: "Type"; value: backend.selectedAsset.kindLabel || "File" }
                                                DetailLine { Layout.fillWidth: true; label: "Size"; value: backend.selectedAsset.sizeLabel || "0 B" }
                                                DetailLine { Layout.fillWidth: true; label: "Codec"; value: backend.selectedAsset.codecLabel || "Not reported" }
                                                DetailLine { Layout.fillWidth: true; label: "Duration"; value: backend.selectedAsset.durationLabel || "Not reported" }
                                                DetailLine { Layout.fillWidth: true; label: "Dimensions"; value: backend.selectedAsset.dimensionsLabel || "Not reported" }
                                                DetailLine { Layout.fillWidth: true; label: "Created"; value: backend.selectedAsset.createdLabel || "" }
                                            }
                                            Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 10
                                                visible: ((backend.selectedAsset.musicAnalysis || {}).status || "").length > 0
                                                Text {
                                                    text: "MUSIC INTELLIGENCE"
                                                    color: root.brass
                                                    font.pixelSize: 9
                                                    font.weight: Font.DemiBold
                                                    font.letterSpacing: 1.4
                                                }
                                                GridLayout {
                                                    Layout.fillWidth: true
                                                    columns: width >= 560 ? 2 : 1
                                                    columnSpacing: 24
                                                    rowSpacing: 9
                                                    DetailLine {
                                                        Layout.fillWidth: true
                                                        label: "Music confidence"
                                                        value: (backend.selectedAsset.musicAnalysis || {}).confidenceLabel || ""
                                                    }
                                                    DetailLine {
                                                        Layout.fillWidth: true
                                                        label: "Tempo"
                                                        value: (backend.selectedAsset.musicAnalysis || {}).bpmLabel || ""
                                                    }
                                                    DetailLine {
                                                        Layout.fillWidth: true
                                                        label: "Estimated key"
                                                        value: (backend.selectedAsset.musicAnalysis || {}).keyLabel || ""
                                                    }
                                                    DetailLine {
                                                        Layout.fillWidth: true
                                                        label: "Pitch range"
                                                        value: (backend.selectedAsset.musicAnalysis || {}).pitchRangeLabel || "Not transcribed"
                                                    }
                                                }
                                                DetailLine {
                                                    Layout.fillWidth: true
                                                    label: "Chord path"
                                                    value: (backend.selectedAsset.musicAnalysis || {}).chordsLabel || "No stable chord sequence"
                                                }
                                                DetailLine {
                                                    Layout.fillWidth: true
                                                    label: "Prominent notes"
                                                    value: (backend.selectedAsset.musicAnalysis || {}).notesLabel || "Not transcribed"
                                                }
                                                DetailLine {
                                                    Layout.fillWidth: true
                                                    label: "Separated stems"
                                                    value: (backend.selectedAsset.musicAnalysis || {}).stemsLabel || "Not generated"
                                                }
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: "Local estimates · "
                                                          + ((backend.selectedAsset.musicAnalysis || {}).worker_version || "")
                                                          + " · Verified "
                                                          + ((backend.selectedAsset.musicAnalysis || {}).verifiedLabel || "")
                                                    color: root.muted
                                                    font.pixelSize: 8
                                                    wrapMode: Text.WordWrap
                                                }
                                            }
                                            Rectangle {
                                                Layout.fillWidth: true
                                                height: 1
                                                color: root.line
                                                visible: ((backend.selectedAsset.musicAnalysis || {}).status || "").length > 0
                                            }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 10
                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    Text {
                                                        Layout.fillWidth: true
                                                        text: "EDITABLE CATALOG METADATA"
                                                        color: root.brass
                                                        font.pixelSize: 9
                                                        font.weight: Font.DemiBold
                                                        font.letterSpacing: 1.4
                                                    }
                                                    Text {
                                                        text: "REV "
                                                              + String((backend.selectedAsset.catalogMetadata || {}).revision || 0)
                                                        color: root.muted
                                                        font.pixelSize: 8
                                                        font.weight: Font.DemiBold
                                                    }
                                                    PrimaryButton {
                                                        text: "Edit metadata"
                                                        quiet: true
                                                        onClicked: metadataDialog.open()
                                                    }
                                                    PrimaryButton {
                                                        text: "Move file"
                                                        enabled: ((backend.selectedAsset.catalogMetadata || {}).organization_path || "").length > 0
                                                        onClicked: moveDialog.open()
                                                    }
                                                }
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: (backend.selectedAsset.catalogMetadata || {}).description
                                                          || "No editable description yet."
                                                    color: root.bone
                                                    font.pixelSize: 12
                                                    lineHeight: 1.35
                                                    wrapMode: Text.WordWrap
                                                }
                                                GridLayout {
                                                    Layout.fillWidth: true
                                                    columns: width >= 560 ? 2 : 1
                                                    columnSpacing: 24
                                                    rowSpacing: 9
                                                    DetailLine {
                                                        Layout.fillWidth: true
                                                        label: "Title"
                                                        value: (backend.selectedAsset.catalogMetadata || {}).display_title || "Not set"
                                                    }
                                                    DetailLine {
                                                        Layout.fillWidth: true
                                                        label: "Category"
                                                        value: (backend.selectedAsset.catalogMetadata || {}).media_category || "Not set"
                                                    }
                                                    DetailLine {
                                                        Layout.fillWidth: true
                                                        label: "Project"
                                                        value: (backend.selectedAsset.catalogMetadata || {}).project || "Not set"
                                                    }
                                                    DetailLine {
                                                        Layout.fillWidth: true
                                                        label: "Client"
                                                        value: (backend.selectedAsset.catalogMetadata || {}).client || "Not set"
                                                    }
                                                    DetailLine {
                                                        Layout.fillWidth: true
                                                        label: "Date"
                                                        value: (backend.selectedAsset.catalogMetadata || {}).event_date || "Not set"
                                                    }
                                                    DetailLine {
                                                        Layout.fillWidth: true
                                                        label: "Place"
                                                        value: (backend.selectedAsset.catalogMetadata || {}).place || "Not set"
                                                    }
                                                }
                                                DetailLine {
                                                    Layout.fillWidth: true
                                                    label: "People"
                                                    value: ((backend.selectedAsset.catalogMetadata || {}).people || []).join(" · ") || "Not set"
                                                }
                                                DetailLine {
                                                    Layout.fillWidth: true
                                                    label: "Tags"
                                                    value: ((backend.selectedAsset.catalogMetadata || {}).tags || []).join(" · ") || "Not set"
                                                }
                                                DetailLine {
                                                    Layout.fillWidth: true
                                                    label: "Rights"
                                                    value: (backend.selectedAsset.catalogMetadata || {}).rights || "Not set"
                                                }
                                                DetailLine {
                                                    Layout.fillWidth: true
                                                    label: "Destination"
                                                    value: (backend.selectedAsset.catalogMetadata || {}).organization_path || "Beacon will place after confident analysis"
                                                    mono: true
                                                }
                                                DetailLine {
                                                    Layout.fillWidth: true
                                                    visible: (backend.selectedAsset.moves || []).length > 0
                                                    label: "Last move"
                                                    value: (backend.selectedAsset.moves || []).length > 0
                                                           ? backend.selectedAsset.moves[0].state.toUpperCase()
                                                             + " · "
                                                             + backend.selectedAsset.moves[0].destination_path
                                                           : ""
                                                    mono: true
                                                }
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: "Updated "
                                                          + ((backend.selectedAsset.catalogMetadata || {}).updatedLabel || "Not edited yet")
                                                          + "  ·  Context stays editable; verified technical facts stay locked."
                                                    color: root.muted
                                                    font.pixelSize: 9
                                                    wrapMode: Text.WordWrap
                                                }
                                            }
                                            Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 10
                                                visible: backend.selectedAsset.analysisCandidate
                                                         && backend.selectedAsset.analysisCandidate.id
                                                         && backend.selectedAsset.analysisCandidate.id.length > 0
                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    Text {
                                                        text: "BEACON ANALYSIS"
                                                        color: root.brass
                                                        font.pixelSize: 9
                                                        font.weight: Font.DemiBold
                                                        font.letterSpacing: 1.4
                                                        Layout.fillWidth: true
                                                    }
                                                    Rectangle {
                                                        implicitWidth: analysisStateLabel.implicitWidth + 18
                                                        implicitHeight: 24
                                                        radius: 12
                                                        color: Qt.rgba(0.76, 0.60, 0.35, 0.12)
                                                        border.color: Qt.rgba(0.76, 0.60, 0.35, 0.28)
                                                        Text {
                                                            id: analysisStateLabel
                                                            anchors.centerIn: parent
                                                            text: backend.selectedAsset.analysisCandidate.reviewStateLabel || "CANDIDATE"
                                                            color: root.brass
                                                            font.pixelSize: 8
                                                            font.weight: Font.DemiBold
                                                            font.letterSpacing: 1.0
                                                        }
                                                    }
                                                }
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: backend.selectedAsset.analysisCandidate.executionLabel || ""
                                                    color: (backend.selectedAsset.analysisCandidate.executionLabel || "").indexOf("EXTERNAL") >= 0
                                                           ? root.ember : root.jade
                                                    font.pixelSize: 8
                                                    font.weight: Font.DemiBold
                                                    font.letterSpacing: 1.0
                                                    wrapMode: Text.WordWrap
                                                }
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: backend.selectedAsset.analysisCandidate.title || ""
                                                    color: root.bone
                                                    font.family: "Georgia"
                                                    font.pixelSize: 20
                                                    wrapMode: Text.WordWrap
                                                }
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: backend.selectedAsset.analysisCandidate.description || ""
                                                    color: root.bone
                                                    font.pixelSize: 12
                                                    lineHeight: 1.35
                                                    wrapMode: Text.WordWrap
                                                }
                                                GridLayout {
                                                    Layout.fillWidth: true
                                                    columns: width >= 560 ? 2 : 1
                                                    columnSpacing: 24
                                                    rowSpacing: 8
                                                    DetailLine {
                                                        Layout.fillWidth: true
                                                        label: "Category"
                                                        value: backend.selectedAsset.analysisCandidate.mediaCategory || "Unclassified"
                                                    }
                                                    DetailLine {
                                                        Layout.fillWidth: true
                                                        label: "Confidence"
                                                        value: backend.selectedAsset.analysisCandidate.confidenceLabel || "Not reported"
                                                    }
                                                }
                                                ColumnLayout {
                                                    Layout.fillWidth: true
                                                    spacing: 4
                                                    Text {
                                                        text: "CANDIDATE TAGS"
                                                        color: root.muted
                                                        font.pixelSize: 8
                                                        font.weight: Font.DemiBold
                                                        font.letterSpacing: 1.1
                                                    }
                                                    Text {
                                                        Layout.fillWidth: true
                                                        text: backend.selectedAsset.analysisCandidate.tagsLabel || "No tags proposed"
                                                        color: root.atlasBright
                                                        font.pixelSize: 11
                                                        wrapMode: Text.WordWrap
                                                    }
                                                }
                                                Rectangle {
                                                    Layout.fillWidth: true
                                                    implicitHeight: analysisSuggestionColumn.implicitHeight + 20
                                                    radius: 7
                                                    color: root.shell
                                                    border.color: root.line
                                                    ColumnLayout {
                                                        id: analysisSuggestionColumn
                                                        anchors.left: parent.left
                                                        anchors.right: parent.right
                                                        anchors.verticalCenter: parent.verticalCenter
                                                        anchors.leftMargin: 12
                                                        anchors.rightMargin: 12
                                                        spacing: 4
                                                        Text {
                                                            text: "ORGANIZATION SUGGESTION · APPROVAL REQUIRED"
                                                            color: root.brass
                                                            font.pixelSize: 8
                                                            font.weight: Font.DemiBold
                                                            font.letterSpacing: 1.0
                                                        }
                                                        Text {
                                                            Layout.fillWidth: true
                                                            text: backend.selectedAsset.analysisCandidate.organizationSuggestion || "No organization change proposed."
                                                            color: root.bone
                                                            font.pixelSize: 11
                                                            wrapMode: Text.WordWrap
                                                        }
                                                    }
                                                }
                                                DetailLine {
                                                    Layout.fillWidth: true
                                                    label: "Privacy"
                                                    value: backend.selectedAsset.analysisCandidate.privacyLabel || "Not reported"
                                                }
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: (backend.selectedAsset.analysisCandidate.analyzerLabel || "Beacon")
                                                          + "  ·  "
                                                          + (backend.selectedAsset.analysisCandidate.executionLabel || "")
                                                          + "  ·  "
                                                          + (backend.selectedAsset.analysisCandidate.createdLabel || "")
                                                    color: root.muted
                                                    font.family: "Cascadia Mono"
                                                    font.pixelSize: 8
                                                    wrapMode: Text.WrapAnywhere
                                                }
                                            }
                                            Rectangle {
                                                Layout.fillWidth: true
                                                height: 1
                                                color: root.line
                                                visible: backend.selectedAsset.analysisCandidate
                                                         && backend.selectedAsset.analysisCandidate.id
                                                         && backend.selectedAsset.analysisCandidate.id.length > 0
                                            }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 10
                                                Text {
                                                    text: "OBSERVED LOCATIONS"
                                                    color: root.brass
                                                    font.pixelSize: 9
                                                    font.weight: Font.DemiBold
                                                    font.letterSpacing: 1.4
                                                }
                                                Repeater {
                                                    model: backend.selectedAsset.locations || []
                                                    delegate: Rectangle {
                                                        required property var modelData
                                                        Layout.fillWidth: true
                                                        implicitHeight: 58
                                                        radius: 7
                                                        color: root.shell
                                                        border.color: root.line
                                                        ColumnLayout {
                                                            anchors.fill: parent
                                                            anchors.margins: 10
                                                            spacing: 2
                                                            Text {
                                                                text: modelData.path || ""
                                                                color: root.bone
                                                                font.family: "Cascadia Mono"
                                                                font.pixelSize: 9
                                                                elide: Text.ElideMiddle
                                                                Layout.fillWidth: true
                                                            }
                                                            Text {
                                                                text: "Observed " + (modelData.observedLabel || "")
                                                                color: root.muted
                                                                font.pixelSize: 9
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                            Rectangle { Layout.fillWidth: true; height: 1; color: root.line }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 10
                                                visible: ((backend.selectedAsset.transcript || {}).text || "").length > 0
                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    Text {
                                                        Layout.fillWidth: true
                                                        text: "FULL TRANSCRIPTION"
                                                        color: root.brass
                                                        font.pixelSize: 9
                                                        font.weight: Font.DemiBold
                                                        font.letterSpacing: 1.4
                                                    }
                                                    Text {
                                                        text: (backend.selectedAsset.transcript || {}).languageLabel || ""
                                                        color: root.muted
                                                        font.pixelSize: 8
                                                    }
                                                }
                                                Rectangle {
                                                    Layout.fillWidth: true
                                                    Layout.preferredHeight: detailTranscript.implicitHeight + 28
                                                    radius: 7
                                                    color: root.shell
                                                    border.color: root.line
                                                    Text {
                                                        id: detailTranscript
                                                        anchors.left: parent.left
                                                        anchors.right: parent.right
                                                        anchors.top: parent.top
                                                        anchors.margins: 14
                                                        text: (backend.selectedAsset.transcript || {}).text || ""
                                                        color: root.bone
                                                        font.pixelSize: 11
                                                        lineHeight: 1.45
                                                        wrapMode: Text.WordWrap
                                                        textFormat: Text.PlainText
                                                    }
                                                }
                                                Text {
                                                    Layout.fillWidth: true
                                                    text: ((backend.selectedAsset.transcript || {}).generatorLabel || "")
                                                          + "  ·  Verified "
                                                          + ((backend.selectedAsset.transcript || {}).verifiedLabel || "")
                                                    color: root.muted
                                                    font.family: "Cascadia Mono"
                                                    font.pixelSize: 8
                                                    wrapMode: Text.WrapAnywhere
                                                }
                                            }
                                        }
                                    }
                                    Text {
                                        anchors.centerIn: parent
                                        visible: backend.selectedAsset.id === undefined
                                        text: "Select an asset to inspect its permanent record."
                                        color: root.muted
                                        font.pixelSize: 12
                                    }
                                }
                            }
                        }
                    }

                    // Operations
                    Item {
                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 24
                            spacing: 14
                            RowLayout {
                                Layout.fillWidth: true
                                PanelTitle { eyebrow: "Immutable evidence"; title: "Operation ledger" }
                                Item { Layout.fillWidth: true }
                                Text {
                                    text: "NEWEST FIRST"
                                    color: root.muted
                                    font.pixelSize: 9
                                    font.letterSpacing: 1.2
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                radius: 10
                                color: root.panel
                                border.color: root.line
                                ListView {
                                    anchors.fill: parent
                                    anchors.margins: 16
                                    clip: true
                                    spacing: 8
                                    model: backend.events
                                    delegate: Rectangle {
                                        required property string kind
                                        required property string state
                                        required property string message
                                        required property string timeLabel
                                        required property string location
                                        required property string assetId
                                        width: ListView.view.width
                                        height: location.length > 0 ? 76 : 62
                                        radius: 8
                                        color: root.shell
                                        border.color: root.line
                                        RowLayout {
                                            anchors.fill: parent
                                            anchors.margins: 12
                                            spacing: 13
                                            Rectangle {
                                                width: 36
                                                height: 36
                                                radius: 18
                                                color: state === "failed"
                                                       ? Qt.rgba(0.77, 0.40, 0.35, 0.14)
                                                       : Qt.rgba(0.42, 0.67, 0.51, 0.14)
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: state === "failed" ? "!" : "✓"
                                                    color: state === "failed" ? root.ember : root.jade
                                                    font.pixelSize: 14
                                                    font.weight: Font.Bold
                                                }
                                            }
                                            ColumnLayout {
                                                Layout.fillWidth: true
                                                spacing: 2
                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    Text {
                                                        text: kind.toUpperCase()
                                                        color: root.brass
                                                        font.pixelSize: 9
                                                        font.weight: Font.DemiBold
                                                        font.letterSpacing: 1.1
                                                    }
                                                    Text {
                                                        text: message
                                                        color: root.bone
                                                        font.pixelSize: 11
                                                        font.weight: Font.DemiBold
                                                        Layout.fillWidth: true
                                                        elide: Text.ElideRight
                                                    }
                                                }
                                                Text {
                                                    visible: location.length > 0
                                                    text: location
                                                    color: root.muted
                                                    font.family: "Cascadia Mono"
                                                    font.pixelSize: 9
                                                    elide: Text.ElideMiddle
                                                    Layout.fillWidth: true
                                                }
                                                Text {
                                                    text: timeLabel
                                                    color: root.muted
                                                    font.pixelSize: 9
                                                }
                                            }
                                            Text {
                                                text: state.toUpperCase()
                                                color: state === "failed" ? root.ember : root.jade
                                                font.pixelSize: 9
                                                font.weight: Font.DemiBold
                                                font.letterSpacing: 1.0
                                            }
                                        }
                                    }
                                    Text {
                                        anchors.centerIn: parent
                                        visible: parent.count === 0
                                        text: "No operations have been recorded."
                                        color: root.muted
                                        font.pixelSize: 12
                                    }
                                }
                            }
                        }
                    }

                    // System
                    Item {
                        ScrollView {
                            anchors.fill: parent
                            clip: true
                            contentWidth: availableWidth
                            ColumnLayout {
                                width: parent.width
                                anchors.margins: 26
                                spacing: 16
                                RowLayout {
                                    Layout.fillWidth: true
                                    PanelTitle { eyebrow: "Local foundations"; title: "System & recovery" }
                                    Item { Layout.fillWidth: true }
                                    Rectangle {
                                        implicitWidth: 124
                                        implicitHeight: 32
                                        radius: 16
                                        color: Qt.rgba(0.42, 0.67, 0.51, 0.12)
                                        Text {
                                            anchors.centerIn: parent
                                            text: "READ-ONLY CORE"
                                            color: root.jade
                                            font.pixelSize: 9
                                            font.weight: Font.DemiBold
                                            font.letterSpacing: 1.0
                                        }
                                    }
                                }
                                RowLayout {
                                    Layout.fillWidth: true
                                    Layout.preferredHeight: 245
                                    spacing: 14
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        radius: 10
                                        color: root.panel
                                        border.color: root.line
                                        ColumnLayout {
                                            anchors.fill: parent
                                            anchors.margins: 20
                                            spacing: 12
                                            RowLayout {
                                                PanelTitle { eyebrow: "Catalog authority"; title: "SQLite health" }
                                                Item { Layout.fillWidth: true }
                                                Rectangle {
                                                    width: 12
                                                    height: 12
                                                    radius: 6
                                                    color: backend.databaseHealth.state === "healthy" ? root.jade : root.ember
                                                }
                                            }
                                            Text {
                                                text: backend.databaseHealth.stateLabel || "Checking…"
                                                color: backend.databaseHealth.state === "healthy" ? root.jade : root.ember
                                                font.pixelSize: 20
                                                font.weight: Font.DemiBold
                                            }
                                            DetailLine { label: "Integrity"; value: backend.databaseHealth.integrity || "unknown"; mono: true }
                                            DetailLine { label: "Foreign keys"; value: String(backend.databaseHealth.foreign_key_errors || 0) + " errors" }
                                            DetailLine { label: "Database"; value: backend.databaseHealth.sizeLabel || "0 B" }
                                            RowLayout {
                                                Item { Layout.fillWidth: true }
                                                PrimaryButton {
                                                    text: "Open runtime folder"
                                                    quiet: true
                                                    onClicked: backend.openFolder(backend.databasePath)
                                                }
                                            }
                                        }
                                    }
                                    Rectangle {
                                        Layout.preferredWidth: 430
                                        Layout.fillHeight: true
                                        radius: 10
                                        color: root.panel
                                        border.color: root.line
                                        ColumnLayout {
                                            anchors.fill: parent
                                            anchors.margins: 20
                                            spacing: 12
                                            PanelTitle { eyebrow: "Recoverability"; title: "Verified backup" }
                                            Text {
                                                text: "Create a point-in-time copy without stopping Beacon. The copy is integrity-checked and hashed before it is reported complete."
                                                color: root.muted
                                                font.pixelSize: 11
                                                lineHeight: 1.35
                                                wrapMode: Text.WordWrap
                                                Layout.fillWidth: true
                                            }
                                            Rectangle {
                                                Layout.fillWidth: true
                                                implicitHeight: 52
                                                radius: 7
                                                color: root.ink
                                                border.color: root.line
                                                Text {
                                                    anchors.fill: parent
                                                    anchors.margins: 10
                                                    text: backend.backupDirectory
                                                    color: root.bone
                                                    font.family: "Cascadia Mono"
                                                    font.pixelSize: 9
                                                    wrapMode: Text.WrapAnywhere
                                                    verticalAlignment: Text.AlignVCenter
                                                }
                                            }
                                            Item { Layout.fillHeight: true }
                                            RowLayout {
                                                Layout.fillWidth: true
                                                Text {
                                                    text: backend.busy ? "Verification in progress…" : "Explicit confirmation required"
                                                    color: backend.busy ? root.brass : root.muted
                                                    font.pixelSize: 9
                                                    Layout.fillWidth: true
                                                }
                                                PrimaryButton {
                                                    text: backend.busy ? "Working…" : "Create backup"
                                                    enabled: !backend.busy
                                                    onClicked: backupDialog.open()
                                                }
                                            }
                                        }
                                    }
                                }
                                Rectangle {
                                    Layout.fillWidth: true
                                    implicitHeight: 260
                                    radius: 10
                                    color: root.panel
                                    border.color: root.line
                                    ColumnLayout {
                                        anchors.fill: parent
                                        anchors.margins: 18
                                        spacing: 12
                                        RowLayout {
                                            Layout.fillWidth: true
                                            PanelTitle { eyebrow: "Recovery points"; title: "Local backup history" }
                                            Item { Layout.fillWidth: true }
                                            PrimaryButton {
                                                text: "Open backup folder"
                                                quiet: true
                                                onClicked: backend.openFolder(backend.backupDirectory)
                                            }
                                        }
                                        ListView {
                                            Layout.fillWidth: true
                                            Layout.fillHeight: true
                                            clip: true
                                            spacing: 7
                                            model: backend.backups
                                            delegate: Rectangle {
                                                required property string name
                                                required property string path
                                                required property string sizeLabel
                                                required property string timeLabel
                                                width: ListView.view.width
                                                height: 54
                                                radius: 7
                                                color: root.shell
                                                border.color: root.line
                                                RowLayout {
                                                    anchors.fill: parent
                                                    anchors.margins: 11
                                                    spacing: 12
                                                    Rectangle {
                                                        width: 8
                                                        height: 8
                                                        radius: 4
                                                        color: root.jade
                                                    }
                                                    ColumnLayout {
                                                        Layout.fillWidth: true
                                                        spacing: 1
                                                        Text {
                                                            text: name
                                                            color: root.bone
                                                            font.family: "Cascadia Mono"
                                                            font.pixelSize: 10
                                                        }
                                                        Text {
                                                            text: timeLabel
                                                            color: root.muted
                                                            font.pixelSize: 9
                                                        }
                                                    }
                                                    Text {
                                                        text: sizeLabel
                                                        color: root.muted
                                                        font.pixelSize: 10
                                                    }
                                                }
                                            }
                                            Text {
                                                anchors.centerIn: parent
                                                visible: parent.count === 0
                                                text: "No verified recovery copies yet."
                                                color: root.muted
                                                font.pixelSize: 12
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    Rectangle {
        id: beaconShellDock
        objectName: "beaconShellDock"
        z: 20
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.leftMargin: 246
        anchors.rightMargin: 16
        anchors.bottomMargin: 14
        height: root.beaconDockExpanded ? Math.min(310, root.height * 0.38) : 58
        radius: 11
        color: root.panelRaised
        border.color: root.beaconDockExpanded ? root.atlas : root.line
        clip: true

        Behavior on height {
            NumberAnimation { duration: 130; easing.type: Easing.OutCubic }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 10
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                spacing: 10
                Image {
                    source: "assets/beacon.svg"
                    sourceSize.width: 28
                    sourceSize.height: 28
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Text {
                        Layout.fillWidth: true
                        text: backend.selectedBeaconThread.subject
                              || "Beacon conversation"
                        color: root.bone
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: (backend.beaconDeskSummary.connectionLabel
                               || "SAVED LOCALLY")
                              + "  ·  "
                              + (backend.selectedBeaconThread.stateLabel
                                 || "NO OPEN THREAD")
                        color: root.muted
                        font.family: "Cascadia Mono"
                        font.pixelSize: 8
                        font.letterSpacing: 0.7
                        elide: Text.ElideRight
                    }
                }
                Text {
                    visible: root.beaconDockExpanded
                    text: backend.beaconDeskSummary.workerStateLabel
                          || "LOCAL MODEL OFFLINE"
                    color: backend.beaconDeskSummary.workerCanRun
                           ? root.jade : root.brass
                    font.family: "Cascadia Mono"
                    font.pixelSize: 8
                    font.weight: Font.DemiBold
                }
                PrimaryButton {
                    visible: root.beaconDockExpanded
                    text: backend.conversationWorkerRunning
                          ? "Beacon working…" : "Run Beacon"
                    quiet: true
                    enabled: backend.beaconDeskSummary.workerCanRun === true
                    onClicked: backend.runBeaconConversationWorker(
                        backend.analysisReadiness.defaultModel || ""
                    )
                }
                PrimaryButton {
                    visible: root.beaconDockExpanded
                    text: "New conversation"
                    quiet: true
                    onClicked: newRequestDialog.open()
                }
                PrimaryButton {
                    text: root.beaconDockExpanded ? "Collapse" : "Open Beacon"
                    quiet: true
                    onClicked: root.beaconDockExpanded = !root.beaconDockExpanded
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: root.beaconDockExpanded
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: beaconShellDock.width * 0.56
                    Layout.minimumWidth: 300
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    radius: 7
                    color: root.ink
                    border.color: root.line
                    ListView {
                        id: shellBeaconMessages
                        objectName: "shellBeaconMessages"
                        anchors.fill: parent
                        anchors.margins: 8
                        clip: true
                        spacing: 6
                        model: backend.beaconMessages
                        delegate: ColumnLayout {
                            required property string author
                            required property string authorLabel
                            required property string body
                            required property string timeLabel
                            required property var resultCards
                            width: ListView.view.width
                            spacing: 2
                            RowLayout {
                                Layout.fillWidth: true
                                Text {
                                    text: authorLabel
                                    color: author === "human"
                                           ? root.atlasBright : root.brass
                                    font.pixelSize: 8
                                    font.weight: Font.DemiBold
                                }
                                Item { Layout.fillWidth: true }
                                Text {
                                    text: timeLabel
                                    color: root.muted
                                    font.pixelSize: 7
                                }
                            }
                            Text {
                                Layout.fillWidth: true
                                text: body
                                color: root.bone
                                font.pixelSize: 10
                                lineHeight: 1.25
                                wrapMode: Text.WordWrap
                            }
                            Repeater {
                                model: resultCards || []
                                delegate: GroundedResultCard {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    assetId: modelData.assetId
                                    displayTitle: modelData.displayTitle
                                    filename: modelData.filename
                                    path: modelData.path
                                    atlasUri: modelData.atlasUri
                                    reason: modelData.reason
                                    availabilityLabel: modelData.availabilityLabel
                                    sizeLabel: modelData.sizeLabel
                                    thumbnailUrl: modelData.thumbnailUrl
                                    available: modelData.available
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.topMargin: 3
                                height: 1
                                color: root.line
                            }
                        }
                        Text {
                            anchors.centerIn: parent
                            visible: parent.count === 0
                            text: "Start a local conversation with Beacon."
                            color: root.muted
                            font.pixelSize: 10
                        }
                    }
                }

                ColumnLayout {
                    Layout.preferredWidth: Math.min(430, beaconShellDock.width * 0.4)
                    Layout.minimumWidth: 300
                    Layout.fillHeight: true
                    spacing: 7
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: "CONTEXT  ·  " + root.currentBeaconContext()
                            color: root.muted
                            font.family: "Cascadia Mono"
                            font.pixelSize: 8
                            elide: Text.ElideMiddle
                        }
                        PrimaryButton {
                            text: "Attach"
                            quiet: true
                            enabled: backend.selectedBeaconThread.id !== undefined
                            onClicked: {
                                var insertion = "[Context attached explicitly: "
                                                + root.currentBeaconContext()
                                                + "]\n"
                                shellBeaconComposer.insert(
                                    shellBeaconComposer.cursorPosition,
                                    insertion
                                )
                                shellBeaconComposer.forceActiveFocus()
                            }
                        }
                    }
                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        TextArea {
                            id: shellBeaconComposer
                            objectName: "shellBeaconComposer"
                            enabled: backend.selectedBeaconThread.id !== undefined
                            placeholderText: backend.selectedBeaconThread.id !== undefined
                                             ? "Reply in this saved local conversation…"
                                             : "Create a conversation to begin"
                            color: root.bone
                            placeholderTextColor: root.muted
                            selectionColor: root.atlas
                            selectByMouse: true
                            wrapMode: TextEdit.Wrap
                            leftPadding: 10
                            rightPadding: 10
                            topPadding: 9
                            bottomPadding: 9
                            background: Rectangle {
                                radius: 7
                                color: root.shell
                                border.color: shellBeaconComposer.activeFocus
                                              ? root.atlasBright : root.line
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: "Replies queue for Beacon; no file action is implied."
                            color: root.muted
                            font.pixelSize: 8
                            elide: Text.ElideRight
                        }
                        PrimaryButton {
                            text: "Save reply"
                            enabled: backend.selectedBeaconThread.id !== undefined
                                     && shellBeaconComposer.text.trim().length > 0
                                     && shellBeaconComposer.text.length <= 8000
                            onClicked: {
                                backend.replyToBeaconThread(
                                    shellBeaconComposer.text
                                )
                                shellBeaconComposer.text = ""
                            }
                        }
                    }
                }
            }
        }
    }
}

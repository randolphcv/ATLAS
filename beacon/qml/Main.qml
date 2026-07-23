import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtMultimedia

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
        previewDialog.open()
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
        implicitHeight: 38
        leftPadding: 16
        rightPadding: 16
        hoverEnabled: true
        contentItem: Text {
            text: primary.text
            color: primary.quiet ? root.bone : root.ink
            font.pixelSize: 12
            font.weight: Font.DemiBold
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            radius: 6
            color: primary.quiet
                   ? (primary.hovered ? root.panelRaised : "transparent")
                   : (primary.hovered ? "#76BFC1" : root.atlasBright)
            border.color: primary.quiet ? root.line : "transparent"
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
        enabled: previewDialog.visible
                 || (backend.currentView === "library"
                     && backend.selectedAsset.id !== undefined
                     && !searchField.activeFocus)
        onActivated: {
            if (previewDialog.visible)
                previewDialog.close()
            else
                root.openSelectedPreview()
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
        id: previewDialog
        modal: true
        anchors.centerIn: Overlay.overlay
        width: Math.min(root.width - 72, 1080)
        height: Math.min(root.height - 64, 720)
        padding: 0
        closePolicy: Popup.CloseOnEscape

        property string previewKind: backend.selectedAsset.previewKind || "file"
        property bool playable: previewKind === "audio" || previewKind === "video"

        onOpened: {
            if (playable && backend.selectedAsset.previewAvailable) {
                previewPlayer.source = backend.selectedAsset.previewUrl
                previewPlayer.play()
            }
        }
        onClosed: {
            previewPlayer.stop()
            previewPlayer.source = ""
            previewVideo.clearOutput()
        }

        background: Rectangle {
            radius: 12
            color: root.panel
            border.color: root.line
        }

        MediaPlayer {
            id: previewPlayer
            audioOutput: AudioOutput {
                volume: 0.82
                muted: previewMuted
            }
            videoOutput: previewVideo
        }

        contentItem: ColumnLayout {
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

                ColumnLayout {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 80, 720)
                    spacing: 18
                    visible: previewDialog.previewKind === "audio"
                    Image {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: Math.min(640, parent.width)
                        Layout.preferredHeight: 260
                        source: backend.selectedAsset.thumbnailUrl || ""
                        fillMode: Image.PreserveAspectFit
                        asynchronous: true
                        cache: false
                    }
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "AUDIO PREVIEW"
                        color: root.brass
                        font.pixelSize: 10
                        font.weight: Font.DemiBold
                        font.letterSpacing: 1.7
                    }
                }

                ColumnLayout {
                    anchors.centerIn: parent
                    width: Math.min(parent.width - 80, 640)
                    spacing: 15
                    visible: previewDialog.previewKind === "file"
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

                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 8
                    visible: !backend.selectedAsset.previewAvailable
                    Text {
                        Layout.alignment: Qt.AlignHCenter
                        text: "Preview unavailable"
                        color: root.bone
                        font.family: "Georgia"
                        font.pixelSize: 22
                    }
                    Text {
                        text: "Beacon can no longer read the observed location."
                        color: root.muted
                        font.pixelSize: 12
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
                        text: "Press Space or Escape to return to the library."
                        color: root.muted
                        font.pixelSize: 10
                        Layout.fillWidth: true
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
                                        eyebrow: "Failed operations"
                                        value: backend.summary.failuresLabel || "0"
                                        note: backend.summary.failures > 0 ? "Review the operation ledger" : "No recorded failures"
                                        accentColor: backend.summary.failures > 0 ? root.ember : root.jade
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
                                                                text: filename
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
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        clip: true
                                        spacing: 7
                                        model: backend.assets
                                        delegate: Rectangle {
                                            required property string assetId
                                            required property string filename
                                            required property string kindLabel
                                            required property string sizeLabel
                                            required property string metaLine
                                            required property string path
                                            required property string thumbnailUrl
                                            width: ListView.view.width
                                            height: 78
                                            radius: 8
                                            color: backend.selectedAsset.id === assetId
                                                   ? Qt.rgba(0.29, 0.55, 0.57, 0.17)
                                                   : assetHover.containsMouse ? root.panelRaised : root.shell
                                            border.color: backend.selectedAsset.id === assetId
                                                          ? Qt.rgba(0.39, 0.68, 0.69, 0.45) : root.line
                                            MouseArea {
                                                id: assetHover
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                onClicked: {
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
                                                            text: filename
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
                                                        text: metaLine
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
                                ScrollView {
                                    id: assetDetailScroll
                                    anchors.fill: parent
                                    anchors.margins: 1
                                    clip: true
                                    contentWidth: availableWidth
                                    ColumnLayout {
                                        width: assetDetailScroll.availableWidth
                                        spacing: 0
                                        visible: backend.selectedAsset.id !== undefined
                                        Rectangle {
                                            Layout.fillWidth: true
                                            implicitHeight: 158
                                            color: root.panelRaised
                                            ColumnLayout {
                                                anchors.fill: parent
                                                anchors.margins: 22
                                                spacing: 7
                                                RowLayout {
                                                    Layout.fillWidth: true
                                                    Text {
                                                        text: (backend.selectedAsset.kindLabel || "File").toUpperCase()
                                                        color: root.brass
                                                        font.pixelSize: 9
                                                        font.weight: Font.DemiBold
                                                        font.letterSpacing: 1.4
                                                        Layout.fillWidth: true
                                                    }
                                                    Rectangle {
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
                                                }
                                                Text {
                                                    text: backend.selectedAsset.filename || ""
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
                                                        text: "Preview"
                                                        onClicked: root.openSelectedPreview()
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
}

import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Controls 2.15
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasmoid

/**
 * Ruflo OS AI Activity Center — Plasma 6 Widget
 *
 * Shows current AI task status, recent actions, and controls.
 * Appears as a panel widget in the top bar or as a standalone plasmoid.
 */
PlasmoidItem {
    id: root

    preferredRepresentation: compactRepresentation

    property bool isConnected: false
    property string currentTask: "Idle"
    property int pendingApprovals: 0

    compactRepresentation: Item {
        Layout.minimumWidth: row.implicitWidth + PlasmaCore.Units.smallSpacing * 2
        Layout.preferredHeight: PlasmaCore.Units.gridUnit * 1.6

        RowLayout {
            id: row
            anchors.centerIn: parent
            spacing: PlasmaCore.Units.smallSpacing

            // AI status indicator
            Rectangle {
                width: 8
                height: 8
                radius: 4
                color: root.isConnected ? "#4ade80" : "#6b7280"

                SequentialAnimation on opacity {
                    running: root.currentTask !== "Idle"
                    loops: Animation.Infinite
                    NumberAnimation { to: 0.4; duration: 800; easing.type: Easing.InOutQuad }
                    NumberAnimation { to: 1.0; duration: 800; easing.type: Easing.InOutQuad }
                }
            }

            Text {
                text: "AI"
                color: PlasmaCore.Theme.textColor
                font.pixelSize: PlasmaCore.Units.gridUnit * 0.85
                font.weight: Font.DemiBold
            }

            // Pending approvals badge
            Rectangle {
                visible: root.pendingApprovals > 0
                width: badge.implicitWidth + PlasmaCore.Units.smallSpacing * 2
                height: PlasmaCore.Units.gridUnit * 0.9
                radius: height / 2
                color: "#ef4444"

                Text {
                    id: badge
                    anchors.centerIn: parent
                    text: root.pendingApprovals.toString()
                    color: "white"
                    font.pixelSize: PlasmaCore.Units.gridUnit * 0.65
                    font.weight: Font.Bold
                }
            }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: root.expanded = !root.expanded
        }
    }

    fullRepresentation: Item {
        Layout.preferredWidth: PlasmaCore.Units.gridUnit * 22
        Layout.preferredHeight: PlasmaCore.Units.gridUnit * 28

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: PlasmaCore.Units.gridUnit

            // Header
            Text {
                text: "AI Activity Center"
                font.pixelSize: PlasmaCore.Units.gridUnit * 1.2
                font.weight: Font.Bold
                color: PlasmaCore.Theme.textColor
            }

            // Connection status
            RowLayout {
                Rectangle {
                    width: 10; height: 10; radius: 5
                    color: root.isConnected ? "#4ade80" : "#ef4444"
                }
                Text {
                    text: root.isConnected ? "Connected to Control Plane" : "Disconnected"
                    color: PlasmaCore.Theme.disabledTextColor
                    font.pixelSize: PlasmaCore.Units.gridUnit * 0.8
                }
            }

            // Current task
            Rectangle {
                Layout.fillWidth: true
                height: PlasmaCore.Units.gridUnit * 4
                radius: PlasmaCore.Units.gridUnit * 0.5
                color: Qt.rgba(PlasmaCore.Theme.backgroundColor.r,
                              PlasmaCore.Theme.backgroundColor.g,
                              PlasmaCore.Theme.backgroundColor.b, 0.6)
                border.color: Qt.rgba(PlasmaCore.Theme.textColor.r,
                                     PlasmaCore.Theme.textColor.g,
                                     PlasmaCore.Theme.textColor.b, 0.1)

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: PlasmaCore.Units.smallSpacing * 2

                    Text {
                        text: "Current Task"
                        font.pixelSize: PlasmaCore.Units.gridUnit * 0.7
                        color: PlasmaCore.Theme.disabledTextColor
                        font.weight: Font.DemiBold
                        text.toUpperCase: true
                    }
                    Text {
                        text: root.currentTask
                        font.pixelSize: PlasmaCore.Units.gridUnit * 0.85
                        color: PlasmaCore.Theme.textColor
                        elide: Text.ElideRight
                        Layout.fillWidth: true
                    }
                }
            }

            // Kill switch button
            Button {
                Layout.fillWidth: true
                text: "⬛ Emergency Stop"
                highlighted: true
                onClicked: {
                    // POST to control plane cancel endpoint
                    console.log("Emergency stop triggered")
                }
            }

            // Spacer
            Item { Layout.fillHeight: true }

            // Footer
            Text {
                text: "Ruflo OS v0.1.0"
                font.pixelSize: PlasmaCore.Units.gridUnit * 0.65
                color: PlasmaCore.Theme.disabledTextColor
                Layout.alignment: Qt.AlignHCenter
            }
        }
    }

    Timer {
        interval: 5000
        running: true
        repeat: true
        onTriggered: {
            // Poll control plane for status updates
            // In production: WebSocket connection
        }
    }
}

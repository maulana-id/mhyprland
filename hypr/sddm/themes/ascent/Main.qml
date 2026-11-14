// Ascent — themed SDDM greeter for the Hyprland desktop.
// Generated palette: theme.js (theme-switch apply).
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "theme.js" as Theme

Rectangle {
    id: root
    width: Screen.width
    height: Screen.height
    color: Theme.bg
    focus: true

    function attemptLogin() {
        if (userField.text.length === 0) {
            userField.forceActiveFocus();
            return;
        }
        errorLabel.text = "";
        sddm.login(userField.text, passwordField.text, sessionBox.currentIndex);
    }

    Image {
        id: wallpaper
        anchors.fill: parent
        source: Theme.background
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        opacity: 0.50
    }

    Rectangle {
        anchors.fill: parent
        color: Theme.bg
        opacity: 0.52
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(0, 0, 0, 0.20) }
            GradientStop { position: 0.55; color: Qt.rgba(0, 0, 0, 0.28) }
            GradientStop { position: 1.0; color: Qt.rgba(0, 0, 0, 0.58) }
        }
    }

    Column {
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.margins: Math.round(root.width * 0.035)
        spacing: 3

        Text {
            text: "ASCENT"
            color: Theme.accent
            font.family: Theme.fontDisplay
            font.pixelSize: Math.max(16, Math.round(root.height * 0.029))
            font.bold: true
            font.letterSpacing: 5
        }

        Text {
            text: "HYPRLAND  /  SESSION"
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: Math.max(8, Math.round(root.height * 0.013))
            font.letterSpacing: 2
        }
    }

    Column {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: Math.round(root.width * 0.035)
        spacing: 1

        Text {
            id: clock
            anchors.right: parent.right
            color: Theme.fg
            font.family: Theme.fontDisplay
            font.pixelSize: Math.max(20, Math.round(root.height * 0.040))
            font.bold: true
            text: Qt.formatDateTime(new Date(), "HH:mm")
        }

        Text {
            id: date
            anchors.right: parent.right
            color: Theme.muted
            font.family: Theme.fontFamily
            font.pixelSize: Math.max(8, Math.round(root.height * 0.014))
            text: Qt.formatDateTime(new Date(), "dddd, dd MMMM yyyy")
        }
    }

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: {
            clock.text = Qt.formatDateTime(new Date(), "HH:mm");
            date.text = Qt.formatDateTime(new Date(), "dddd, dd MMMM yyyy");
        }
    }

    Rectangle {
        id: card
        anchors.centerIn: parent
        width: Math.min(root.width * 0.46, 500)
        height: Math.min(root.height * 0.62, 430)
        color: Theme.panel
        radius: 18
        border.width: 1
        border.color: Theme.border

        Rectangle {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.right: parent.right
            height: 3
            radius: 2
            color: Theme.accent
            opacity: 0.9
        }

        Column {
            id: form
            anchors.fill: parent
            anchors.margins: 28
            spacing: 8

            Text {
                text: "Welcome back"
                color: Theme.fg
                font.family: Theme.fontDisplay
                font.pixelSize: 25
                font.bold: true
            }

            Text {
                text: sddm.hostName + "  ·  " + (sessionBox.currentIndex >= 0 ? "Hyprland" : "Session")
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: 10
                font.letterSpacing: 1
            }

            Item { width: 1; height: 4 }

            Text {
                text: "USERNAME"
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: 9
                font.bold: true
                font.letterSpacing: 2
            }

            TextField {
                id: userField
                width: parent.width
                height: 42
                text: userModel.lastUser
                placeholderText: "username"
                placeholderTextColor: Theme.muted
                color: Theme.fg
                selectionColor: Theme.accent
                selectedTextColor: Theme.onAccent
                font.family: Theme.fontFamily
                font.pixelSize: 13
                leftPadding: 12
                rightPadding: 12
                selectByMouse: true
                background: Rectangle {
                    color: Theme.input
                    radius: 10
                    border.width: 1
                    border.color: userField.activeFocus ? Theme.accent : Theme.border
                }
                onAccepted: passwordField.forceActiveFocus()
            }

            Text {
                text: "PASSWORD"
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: 9
                font.bold: true
                font.letterSpacing: 2
            }

            TextField {
                id: passwordField
                width: parent.width
                height: 42
                echoMode: TextInput.Password
                placeholderText: "password"
                placeholderTextColor: Theme.muted
                color: Theme.fg
                selectionColor: Theme.accent
                selectedTextColor: Theme.onAccent
                font.family: Theme.fontFamily
                font.pixelSize: 13
                leftPadding: 12
                rightPadding: 12
                selectByMouse: true
                background: Rectangle {
                    color: Theme.input
                    radius: 10
                    border.width: 1
                    border.color: passwordField.activeFocus ? Theme.accent : Theme.border
                }
                onAccepted: root.attemptLogin()
            }

            Text {
                id: errorLabel
                width: parent.width
                height: 16
                color: Theme.red
                font.family: Theme.fontFamily
                font.pixelSize: 10
                text: ""
                opacity: text.length > 0 ? 1 : 0
            }

            Text {
                text: "SESSION"
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: 9
                font.bold: true
                font.letterSpacing: 2
            }

            ComboBox {
                id: sessionBox
                width: parent.width
                height: 38
                model: sessionModel
                textRole: "name"
                currentIndex: sessionModel.lastIndex
                font.family: Theme.fontFamily
                font.pixelSize: 12
                leftPadding: 12
                rightPadding: 30

                contentItem: Text {
                    leftPadding: 12
                    rightPadding: 30
                    text: sessionBox.displayText
                    color: Theme.fg
                    font: sessionBox.font
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }

                indicator: Text {
                    x: sessionBox.width - width - 12
                    y: (sessionBox.height - height) / 2
                    text: "⌄"
                    color: Theme.muted
                    font.pixelSize: 15
                }

                background: Rectangle {
                    color: Theme.input
                    radius: 10
                    border.width: 1
                    border.color: sessionBox.activeFocus ? Theme.accent : Theme.border
                }

                delegate: ItemDelegate {
                    id: sessionDelegate
                    width: sessionBox.width
                    contentItem: Text {
                        text: model.name
                        color: Theme.fg
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        verticalAlignment: Text.AlignVCenter
                    }
                    background: Rectangle {
                        color: sessionDelegate.highlighted ? Theme.surfaceAlt : "transparent"
                        radius: 6
                    }
                    highlighted: sessionBox.highlightedIndex === index
                }

                popup: Popup {
                    y: sessionBox.height
                    width: sessionBox.width
                    padding: 4
                    background: Rectangle {
                        color: Theme.surface
                        border.color: Theme.border
                        border.width: 1
                        radius: 10
                    }
                    contentItem: ListView {
                        clip: true
                        implicitHeight: contentHeight
                        model: sessionBox.popup.visible ? sessionBox.delegateModel : null
                        currentIndex: sessionBox.highlightedIndex
                    }
                }
            }

            Button {
                id: loginButton
                width: parent.width
                height: 44
                text: "Unlock session"
                enabled: userField.text.length > 0
                onClicked: root.attemptLogin()
                background: Rectangle {
                    color: loginButton.enabled ? (loginButton.down ? Theme.accentAlt : Theme.accent) : Theme.surfaceAlt
                    radius: 10
                }
                contentItem: Text {
                    text: loginButton.text
                    color: loginButton.enabled ? Theme.onAccent : Theme.muted
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                    font.bold: true
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                }
            }
        }
    }

    Row {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Math.round(root.height * 0.045)
        spacing: 8

        Button {
            id: powerButton
            text: "Power"
            flat: true
            onClicked: sddm.powerOff()
            background: Rectangle { color: "transparent"; radius: 8 }
            contentItem: Text {
                text: powerButton.text
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: 10
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }

        Button {
            id: rebootButton
            text: "Reboot"
            flat: true
            onClicked: sddm.reboot()
            background: Rectangle { color: "transparent"; radius: 8 }
            contentItem: Text {
                text: rebootButton.text
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: 10
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }

        Button {
            id: suspendButton
            text: "Suspend"
            flat: true
            visible: sddm.canSuspend
            onClicked: sddm.suspend()
            background: Rectangle { color: "transparent"; radius: 8 }
            contentItem: Text {
                text: suspendButton.text
                color: Theme.muted
                font.family: Theme.fontFamily
                font.pixelSize: 10
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            errorLabel.text = "Authentication failed";
            passwordField.text = "";
            passwordField.forceActiveFocus();
        }
    }

    Component.onCompleted: {
        if (userField.text.length === 0)
            userField.forceActiveFocus();
        else
            passwordField.forceActiveFocus();
    }
}

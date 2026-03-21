import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1440
    height: 900
    minimumWidth: 1200
    minimumHeight: 750
    title: "AMCS — Autonomous Multi-Sensor Command System"
    visible: true
    color: "#0D1B2A"

    // ── Colour palette ────────────────────────────────────────────
    readonly property color c_bg:       "#0D1B2A"
    readonly property color c_panel:    "#142235"
    readonly property color c_card:     "#1A2F45"
    readonly property color c_border:   "#2471A3"
    readonly property color c_text:     "#DCE8F0"
    readonly property color c_dim:      "#7899AA"
    readonly property color c_uav:      "#C8E6C9"
    readonly property color c_ugv:      "#A5D6A7"
    readonly property color c_pvo:      "#EF9A9A"
    readonly property color c_gg:       "#CE93D8"
    readonly property color c_sensor:   "#FFF9C4"
    readonly property color c_alarm:    "#FFCDD2"
    readonly property color c_warn:     "#FFE082"
    readonly property color c_active:   "#4CAF50"
    readonly property color c_standby:  "#78909C"
    readonly property color c_armed:    "#EF5350"
    readonly property color c_deploy:   "#FF9800"
    readonly property color c_accent:   "#2196F3"

    // ── Live clock ────────────────────────────────────────────────
    property string currentTime: "--:--:--"
    property string currentDate: "----/--/--"
    property int    pulsePhase:  0

    Timer {
        interval: 1000; running: true; repeat: true
        onTriggered: {
            var d = new Date()
            root.currentTime = d.getHours()  .toString().padStart(2,"0") + ":" +
                               d.getMinutes().toString().padStart(2,"0") + ":" +
                               d.getSeconds().toString().padStart(2,"0")
            root.currentDate = d.getFullYear() + "-" +
                               (d.getMonth()+1).toString().padStart(2,"0") + "-" +
                               d.getDate()     .toString().padStart(2,"0")
        }
        Component.onCompleted: triggered()
    }

    Timer {
        interval: 600; running: true; repeat: true
        onTriggered: {
            root.pulsePhase = (root.pulsePhase + 1) % 2
            mapCanvas.requestPaint()
        }
    }

    // ── Root layout ───────────────────────────────────────────────
    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ── TOP BAR ──────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 56
            color: "#0A1622"
            border.color: root.c_border; border.width: 1

            RowLayout {
                anchors { fill: parent; leftMargin: 16; rightMargin: 16 }
                spacing: 0

                // Title
                Column {
                    spacing: 1
                    Text { text: "AMCS"; color: root.c_accent
                           font { pixelSize: 20; bold: true; family: "Liberation Sans" } }
                    Text { text: "Autonomous Multi-Sensor Command System"
                           color: root.c_dim; font.pixelSize: 10 }
                }

                Item { Layout.fillWidth: true }

                // Mission info (centre)
                Row {
                    spacing: 24
                    TopChip { label: "MISSION";  value: "MSN-2026-003" }
                    TopChip { label: "ZONE";     value: "ZONE-BRAVO" }
                    TopChip { label: "STATUS";   value: "● ACTIVE";
                               valueColor: root.c_active }
                    TopChip { label: "CORRIDOR"; value: "42.817–42.843°N / 20.166–20.534°E" }
                }

                Item { Layout.fillWidth: true }

                // Clock + operator (right)
                Column {
                    spacing: 2
                    Text { text: root.currentTime; color: "#FFFFFF"
                           font { pixelSize: 18; bold: true; family: "monospace" } }
                    Text { text: root.currentDate + "  |  jovic.m  [L3]"
                           color: root.c_dim; font.pixelSize: 10 }
                }
            }
        }

        // ── MAIN 3-COLUMN ─────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // ── LEFT PANEL: device list ───────────────────────────
            Rectangle {
                width: 220
                Layout.fillHeight: true
                color: root.c_panel
                border.color: "#1E3550"; border.width: 1

                ScrollView {
                    anchors.fill: parent
                    clip: true
                    contentWidth: availableWidth

                    ColumnLayout {
                        width: 220
                        spacing: 0

                        // ── Vehicles ──────────────────────────────
                        SectionHeader { title: "AUTONOMOUS VEHICLES" }

                        DeviceCard {
                            name: "UAV-ALPHA-001"; role: "PVO DRONE"
                            statusText: "DEPLOYED"; statusColor: root.c_active
                            accentColor: root.c_uav; battery: 78.5
                            detail1: "Alt: 150 m  |  Hdg: 270°"
                            detail2: "Speed: 65 km/h  |  Radar+Cam"
                        }
                        DeviceCard {
                            name: "UGV-BRAVO-002"; role: "GROUND INTERCEPT"
                            statusText: "DEPLOYING"; statusColor: root.c_deploy
                            accentColor: root.c_ugv; battery: 92.3
                            detail1: "Speed: 25 km/h  |  Rugged"
                            detail2: "Radar+Cam  |  Intercept ACT-001"
                        }

                        // ── Air Defence ───────────────────────────
                        SectionHeader { title: "AIR DEFENCE  (PVO x4)" }

                        WeaponCard { sysId: "PVO-ALPHA-01"; position: "NW corner"
                                     armed: true;  ammo: 8;  range: "SHORT" }
                        WeaponCard { sysId: "PVO-ALPHA-02"; position: "NE corner"
                                     armed: true;  ammo: 8;  range: "SHORT" }
                        WeaponCard { sysId: "PVO-BETA-03";  position: "SW corner"
                                     armed: false; ammo: 4;  range: "MEDIUM" }
                        WeaponCard { sysId: "PVO-BETA-04";  position: "SE corner"
                                     armed: false; ammo: 4;  range: "MEDIUM" }

                        // ── Ground Systems ────────────────────────
                        SectionHeader { title: "GROUND SYSTEMS  (GG x3)" }

                        WeaponCard { sysId: "GG-ZETA-01"; position: "South-W"
                                     armed: true;  ammo: 12; range: "3 km" }
                        WeaponCard { sysId: "GG-ZETA-02"; position: "South-C"
                                     armed: true;  ammo: 12; range: "3 km" }
                        WeaponCard { sysId: "GG-ZETA-03"; position: "South-E"
                                     armed: false; ammo: 10; range: "3 km" }

                        // ── Field Sensors ─────────────────────────
                        SectionHeader { title: "FIELD SENSORS" }

                        SensorCard { sensorType: "ACOUSTIC"; count: "x3"
                                     detail: "W / C / E  ~10 km apart"
                                     conf: 0.93; accentColor: root.c_sensor }
                        SensorCard { sensorType: "SEISMIC"; count: "x3"
                                     detail: "Staggered between acoustic"
                                     conf: 0.87; accentColor: root.c_warn }

                        Item { height: 10 }
                    }
                }
            }

            // ── CENTER: battlefield map ───────────────────────────
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true

                // Map header overlay
                Rectangle {
                    anchors { top: parent.top; left: parent.left; right: parent.right }
                    height: 28; z: 10
                    color: "transparent"
                    RowLayout {
                        anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
                        Text { text: "BATTLEFIELD MAP  —  ZONE-BRAVO  (30 × 3 km corridor)"
                               color: root.c_dim; font { pixelSize: 10; family: "monospace" } }
                        Item { Layout.fillWidth: true }
                        Text { text: "Center: 42.830°N / 20.350°E   |   Proj: WGS-84"
                               color: root.c_dim; font { pixelSize: 10; family: "monospace" } }
                    }
                }

                Canvas {
                    id: mapCanvas
                    anchors { fill: parent; topMargin: 28 }

                    // Coordinate bounds (display area, slightly larger than corridor)
                    property real lonMin: 20.12
                    property real lonMax: 20.57
                    property real latMin: 42.808
                    property real latMax: 42.856

                    // ── Coordinate helpers ────────────────────────
                    function lonToX(lon) {
                        return (lon - lonMin) / (lonMax - lonMin) * width
                    }
                    function latToY(lat) {
                        return (1.0 - (lat - latMin) / (latMax - latMin)) * height
                    }

                    // ── Drawing helpers ───────────────────────────
                    function lbl(ctx, text, x, y, color) {
                        ctx.font = "bold 9px sans-serif"
                        ctx.fillStyle = "rgba(0,0,0,0.55)"
                        ctx.fillText(text, x+1, y+1)
                        ctx.fillStyle = color
                        ctx.fillText(text, x, y)
                    }

                    function drawGrid(ctx) {
                        ctx.strokeStyle = "rgba(36, 113, 163, 0.18)"
                        ctx.lineWidth = 0.8
                        var lon = 20.15
                        while (lon <= lonMax) {
                            var gx = lonToX(lon)
                            ctx.beginPath(); ctx.moveTo(gx, 0); ctx.lineTo(gx, height); ctx.stroke()
                            lon = Math.round((lon + 0.05) * 1000) / 1000
                        }
                        var lat = 42.810
                        while (lat <= latMax) {
                            var gy = latToY(lat)
                            ctx.beginPath(); ctx.moveTo(0, gy); ctx.lineTo(width, gy); ctx.stroke()
                            lat = Math.round((lat + 0.005) * 10000) / 10000
                        }
                    }

                    function drawCoordLabels(ctx) {
                        ctx.font = "8px monospace"
                        ctx.fillStyle = "rgba(120,153,170,0.65)"
                        var lon = 20.15
                        while (lon <= lonMax - 0.01) {
                            var lx = lonToX(lon)
                            if (lx > 20 && lx < width - 20)
                                ctx.fillText(lon.toFixed(2), lx - 12, height - 6)
                            lon = Math.round((lon + 0.05) * 1000) / 1000
                        }
                        var lat = 42.810
                        while (lat <= latMax - 0.003) {
                            var ly = latToY(lat)
                            if (ly > 12 && ly < height - 12)
                                ctx.fillText(lat.toFixed(3), 4, ly + 3)
                            lat = Math.round((lat + 0.005) * 10000) / 10000
                        }
                    }

                    function drawCorridor(ctx) {
                        var x0 = lonToX(20.166), y0 = latToY(42.843)
                        var x1 = lonToX(20.534), y1 = latToY(42.817)
                        ctx.fillStyle = "rgba(15, 33, 51, 0.9)"
                        ctx.fillRect(x0, y0, x1-x0, y1-y0)
                        ctx.setLineDash([6, 4])
                        ctx.strokeStyle = "rgba(36, 113, 163, 0.7)"
                        ctx.lineWidth = 1.5
                        ctx.strokeRect(x0, y0, x1-x0, y1-y0)
                        ctx.setLineDash([])
                        lbl(ctx, "ZONE-BRAVO", x0+6, y0+12, "#5B8DB8")
                    }

                    function drawUAV(ctx, lat, lon, label) {
                        var x = lonToX(lon), y = latToY(lat), r = 9
                        ctx.lineWidth = 2
                        ctx.strokeStyle = "#81C784"
                        ctx.beginPath(); ctx.moveTo(x-r, y-r); ctx.lineTo(x+r, y+r); ctx.stroke()
                        ctx.beginPath(); ctx.moveTo(x+r, y-r); ctx.lineTo(x-r, y+r); ctx.stroke()
                        var pp = [[x-r,y-r],[x+r,y-r],[x-r,y+r],[x+r,y+r]]
                        for (var i = 0; i < pp.length; i++) {
                            ctx.beginPath(); ctx.arc(pp[i][0], pp[i][1], 4, 0, Math.PI*2)
                            ctx.fillStyle = "#C8E6C9"
                            ctx.strokeStyle = "#4CAF50"; ctx.lineWidth = 1.5
                            ctx.fill(); ctx.stroke()
                        }
                        ctx.beginPath(); ctx.arc(x, y, 4, 0, Math.PI*2)
                        ctx.fillStyle = "#FFFFFF"; ctx.fill()
                        lbl(ctx, label, x+14, y+4, "#C8E6C9")
                    }

                    function drawUGV(ctx, lat, lon, label) {
                        var x = lonToX(lon), y = latToY(lat)
                        var w = 20, h = 14
                        ctx.fillStyle = "#A5D6A7"
                        ctx.strokeStyle = "#388E3C"; ctx.lineWidth = 2
                        ctx.beginPath(); ctx.rect(x-w/2, y-h/2, w, h); ctx.fill(); ctx.stroke()
                        ctx.fillStyle = "#2E7D32"
                        ctx.fillRect(x-w/2-4, y-h/2+2, 5, h-4)
                        ctx.fillRect(x+w/2-1, y-h/2+2, 5, h-4)
                        ctx.beginPath(); ctx.arc(x, y, 3, 0, Math.PI*2)
                        ctx.fillStyle = "#FFFFFF"; ctx.fill()
                        lbl(ctx, label, x+16, y+4, "#A5D6A7")
                    }

                    function drawAcoustic(ctx, lat, lon, label) {
                        var x = lonToX(lon), y = latToY(lat)
                        for (var i = 2; i >= 1; i--) {
                            ctx.beginPath(); ctx.arc(x, y, 6 + i*5, -Math.PI*0.6, Math.PI*0.6)
                            ctx.strokeStyle = "rgba(249,168,37,0.3)"; ctx.lineWidth = 1.5; ctx.stroke()
                        }
                        ctx.beginPath(); ctx.arc(x, y, 6, 0, Math.PI*2)
                        ctx.fillStyle = "#FFF9C4"; ctx.strokeStyle = "#F9A825"; ctx.lineWidth = 2
                        ctx.fill(); ctx.stroke()
                        lbl(ctx, label, x+10, y+4, "#FFF9C4")
                    }

                    function drawSeismic(ctx, lat, lon, label) {
                        var x = lonToX(lon), y = latToY(lat), r = 7
                        ctx.save()
                        ctx.translate(x, y); ctx.rotate(Math.PI/4)
                        ctx.fillStyle = "#FFE082"; ctx.strokeStyle = "#F57F17"; ctx.lineWidth = 2
                        ctx.beginPath(); ctx.rect(-r*0.75, -r*0.75, r*1.5, r*1.5)
                        ctx.fill(); ctx.stroke()
                        ctx.restore()
                        lbl(ctx, label, x+10, y+4, "#FFE082")
                    }

                    function drawPVO(ctx, lat, lon, label, armed) {
                        var x = lonToX(lon), y = latToY(lat), r = 9
                        ctx.beginPath()
                        for (var i = 0; i < 6; i++) {
                            var a = Math.PI/6 + i * Math.PI/3
                            if (i===0) ctx.moveTo(x+r*Math.cos(a), y+r*Math.sin(a))
                            else       ctx.lineTo(x+r*Math.cos(a), y+r*Math.sin(a))
                        }
                        ctx.closePath()
                        ctx.fillStyle   = armed ? "#EF9A9A" : "#546E7A"
                        ctx.strokeStyle = armed ? "#C62828" : "#37474F"
                        ctx.lineWidth = 2; ctx.fill(); ctx.stroke()
                        ctx.fillStyle = "#FFFFFF"
                        ctx.beginPath()
                        ctx.moveTo(x, y-4); ctx.lineTo(x-3, y+3); ctx.lineTo(x+3, y+3)
                        ctx.closePath(); ctx.fill()
                        lbl(ctx, label, x+13, y+4, armed ? "#EF9A9A" : "#90A4AE")
                    }

                    function drawGG(ctx, lat, lon, label, armed) {
                        var x = lonToX(lon), y = latToY(lat), r = 8
                        ctx.fillStyle   = armed ? "#CE93D8" : "#546E7A"
                        ctx.strokeStyle = armed ? "#6A1B9A" : "#37474F"
                        ctx.lineWidth = 2
                        ctx.beginPath(); ctx.rect(x-r, y-r, r*2, r*2); ctx.fill(); ctx.stroke()
                        ctx.fillStyle = "#FFFFFF"
                        ctx.beginPath()
                        ctx.moveTo(x, y+4); ctx.lineTo(x-3, y-3); ctx.lineTo(x+3, y-3)
                        ctx.closePath(); ctx.fill()
                        lbl(ctx, label, x+13, y+4, armed ? "#CE93D8" : "#90A4AE")
                    }

                    function drawTarget(ctx, lat, lon) {
                        var x = lonToX(lon), y = latToY(lat)
                        var pulse = root.pulsePhase
                        ctx.beginPath(); ctx.arc(x, y, 10 + pulse*5, 0, Math.PI*2)
                        ctx.strokeStyle = "rgba(244,67,54," + (pulse ? "0.8" : "0.35") + ")"
                        ctx.lineWidth = 1.5; ctx.stroke()
                        ctx.beginPath(); ctx.arc(x, y, 5, 0, Math.PI*2)
                        ctx.fillStyle = "#F44336"; ctx.fill()
                        ctx.strokeStyle = "#FFFFFF"; ctx.lineWidth = 1.5
                        ctx.beginPath(); ctx.moveTo(x-3,y-3); ctx.lineTo(x+3,y+3); ctx.stroke()
                        ctx.beginPath(); ctx.moveTo(x+3,y-3); ctx.lineTo(x-3,y+3); ctx.stroke()
                        lbl(ctx, "TGT-001", x+14, y, "#F44336")
                    }

                    function drawIntercept(ctx, lat, lon) {
                        var x = lonToX(lon), y = latToY(lat)
                        ctx.strokeStyle = "#FF9800"; ctx.lineWidth = 1.5
                        ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI*2); ctx.stroke()
                        ctx.beginPath(); ctx.moveTo(x-14,y); ctx.lineTo(x+14,y); ctx.stroke()
                        ctx.beginPath(); ctx.moveTo(x,y-14); ctx.lineTo(x,y+14); ctx.stroke()
                        lbl(ctx, "INTERCEPT", x+14, y-8, "#FF9800")
                    }

                    function drawTrajectory(ctx, lat1, lon1, lat2, lon2) {
                        var x1=lonToX(lon1),y1=latToY(lat1),x2=lonToX(lon2),y2=latToY(lat2)
                        ctx.setLineDash([5, 4])
                        ctx.strokeStyle = "#F44336"; ctx.lineWidth = 1.5
                        ctx.beginPath(); ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke()
                        ctx.setLineDash([])
                        var ang = Math.atan2(y2-y1, x2-x1)
                        ctx.fillStyle = "#F44336"
                        ctx.beginPath()
                        ctx.moveTo(x2, y2)
                        ctx.lineTo(x2-10*Math.cos(ang-0.4), y2-10*Math.sin(ang-0.4))
                        ctx.lineTo(x2-10*Math.cos(ang+0.4), y2-10*Math.sin(ang+0.4))
                        ctx.closePath(); ctx.fill()
                    }

                    function drawLegend(ctx) {
                        var lx = width - 160, ly = 16, ls = 16, sp = 18
                        ctx.fillStyle = "rgba(13,27,42,0.85)"
                        ctx.fillRect(lx-8, ly-8, 158, 9*sp+8)
                        ctx.strokeStyle = "#2471A3"; ctx.lineWidth = 1
                        ctx.strokeRect(lx-8, ly-8, 158, 9*sp+8)
                        ctx.font = "bold 9px sans-serif"
                        ctx.fillStyle = "#7899AA"; ctx.fillText("LEGEND", lx, ly+3)
                        ly += sp
                        var items = [
                            ["UAV (PVO drone)",    "#C8E6C9"],
                            ["UGV (intercept)",    "#A5D6A7"],
                            ["Acoustic sensor",    "#FFF9C4"],
                            ["Seismic sensor",     "#FFE082"],
                            ["PVO sys (ARMED)",    "#EF9A9A"],
                            ["PVO sys (STANDBY)",  "#546E7A"],
                            ["GG sys (ARMED)",     "#CE93D8"],
                            ["Target (TGT-001)",   "#F44336"]
                        ]
                        for (var i = 0; i < items.length; i++) {
                            ctx.beginPath(); ctx.arc(lx+6, ly, 5, 0, Math.PI*2)
                            ctx.fillStyle = items[i][1]; ctx.fill()
                            ctx.fillStyle = "#C8D8E4"
                            ctx.fillText(items[i][0], lx+15, ly+3)
                            ly += sp
                        }
                    }

                    function drawScaleBar(ctx) {
                        // 5 km scale bar
                        var km5_deg = 5 / 81.74   // degrees lon for 5 km at lat 42.83
                        var barW = km5_deg / (lonMax - lonMin) * width
                        var bx = 50, by = height - 24
                        ctx.fillStyle = "#FFFFFF"; ctx.fillRect(bx, by, barW, 4)
                        ctx.fillRect(bx + barW, by, barW, 4)
                        ctx.fillStyle = "#7899AA"
                        ctx.font = "8px monospace"
                        ctx.fillText("0", bx-4, by+14)
                        ctx.fillText("5 km", bx+barW-8, by+14)
                        ctx.fillText("10 km", bx+barW*2-10, by+14)
                    }

                    function drawNorth(ctx) {
                        var nx = width - 30, ny = 40
                        ctx.strokeStyle = "#5B8DB8"; ctx.lineWidth = 1.5
                        ctx.beginPath(); ctx.moveTo(nx,ny+10); ctx.lineTo(nx,ny-10); ctx.stroke()
                        ctx.fillStyle = "#90CAF9"
                        ctx.beginPath(); ctx.moveTo(nx,ny-14); ctx.lineTo(nx-4,ny-4); ctx.lineTo(nx+4,ny-4); ctx.closePath(); ctx.fill()
                        ctx.font = "bold 9px sans-serif"; ctx.fillStyle = "#90CAF9"
                        ctx.fillText("N", nx-4, ny-18)
                    }

                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.clearRect(0, 0, width, height)

                        // Background
                        ctx.fillStyle = "#08111C"
                        ctx.fillRect(0, 0, width, height)

                        drawGrid(ctx)
                        drawCoordLabels(ctx)
                        drawCorridor(ctx)

                        // Standalone field sensors
                        drawAcoustic(ctx, 42.824, 20.195, "ACO-W")
                        drawAcoustic(ctx, 42.833, 20.350, "ACO-C")
                        drawAcoustic(ctx, 42.821, 20.500, "ACO-E")

                        drawSeismic(ctx, 42.831, 20.225, "SEI-W")
                        drawSeismic(ctx, 42.818, 20.370, "SEI-C")
                        drawSeismic(ctx, 42.829, 20.485, "SEI-E")

                        // PVO systems — corners
                        drawPVO(ctx, 42.840, 20.180, "PVO-01", true)
                        drawPVO(ctx, 42.839, 20.525, "PVO-02", true)
                        drawPVO(ctx, 42.817, 20.185, "PVO-03", false)
                        drawPVO(ctx, 42.816, 20.520, "PVO-04", false)

                        // GG systems — south edge
                        drawGG(ctx, 42.819, 20.225, "GG-01", true)
                        drawGG(ctx, 42.818, 20.352, "GG-02", true)
                        drawGG(ctx, 42.820, 20.478, "GG-03", false)

                        // Vehicles
                        drawUAV(ctx, 42.832, 20.358, "UAV-ALPHA")
                        drawUGV(ctx, 42.826, 20.342, "UGV-BRAVO")

                        // Target + intercept + trajectory
                        drawTrajectory(ctx, 42.829, 20.363, 42.827, 20.355)
                        drawIntercept(ctx, 42.827, 20.355)
                        drawTarget(ctx, 42.829, 20.363)

                        drawLegend(ctx)
                        drawScaleBar(ctx)
                        drawNorth(ctx)
                    }
                }
            }

            // ── RIGHT PANEL: alarms / tracks / actions ────────────
            Rectangle {
                width: 280
                Layout.fillHeight: true
                color: root.c_panel
                border.color: "#1E3550"; border.width: 1

                ScrollView {
                    anchors.fill: parent
                    clip: true
                    contentWidth: availableWidth

                    ColumnLayout {
                        width: 280
                        spacing: 0

                        SectionHeader { title: "ACTIVE ALARMS" }

                        // Alarm card
                        Rectangle {
                            width: 260; height: 110
                            Layout.alignment: Qt.AlignHCenter
                            color: "#2C1515"
                            border.color: root.c_pvo; border.width: 2
                            radius: 4
                            ColumnLayout {
                                anchors { fill: parent; margins: 8 }
                                spacing: 3
                                Row {
                                    spacing: 6
                                    Rectangle { width: 8; height: 8; radius: 4
                                                color: root.c_armed; anchors.verticalCenter: parent.verticalCenter
                                                visible: root.pulsePhase === 0 }
                                    Text { text: "ALM-20260321-001"; color: root.c_alarm
                                           font { bold: true; pixelSize: 11 } }
                                }
                                InfoRow { k: "Level";       v: "HIGH";              vc: root.c_armed }
                                InfoRow { k: "Status";      v: "OPERATOR_APPROVED"; vc: "#90CAF9" }
                                InfoRow { k: "Target";      v: "GROUND_VEHICLE";    vc: root.c_text }
                                InfoRow { k: "Confidence";  v: "93%";               vc: root.c_active }
                                InfoRow { k: "Location";    v: "42.829°N  20.363°E"; vc: root.c_text }
                                InfoRow { k: "Time";        v: "14:32:00 UTC";      vc: root.c_dim }
                            }
                        }

                        Item { height: 4 }

                        SectionHeader { title: "ACTIVE TRACK" }

                        Rectangle {
                            width: 260; height: 90
                            Layout.alignment: Qt.AlignHCenter
                            color: root.c_card; border.color: "#7B1FA2"; border.width: 1; radius: 4
                            ColumnLayout {
                                anchors { fill: parent; margins: 8 }
                                spacing: 3
                                Text { text: "TRK-20260321-001"; color: "#CE93D8"
                                       font { bold: true; pixelSize: 11 } }
                                InfoRow { k: "Position";   v: "42.829°N  20.363°E"; vc: root.c_text }
                                InfoRow { k: "Velocity";   v: "15 km/h";            vc: root.c_text }
                                InfoRow { k: "Heading";    v: "200°";               vc: root.c_text }
                                InfoRow { k: "Confidence"; v: "93%";                vc: root.c_active }
                            }
                        }

                        Item { height: 4 }

                        SectionHeader { title: "TRAJECTORY" }

                        Rectangle {
                            width: 260; height: 72
                            Layout.alignment: Qt.AlignHCenter
                            color: root.c_card; border.color: "#9E9E9E"; border.width: 1; radius: 4
                            ColumnLayout {
                                anchors { fill: parent; margins: 8 }
                                spacing: 3
                                Text { text: "TRAJ-20260321-001"; color: root.c_dim
                                       font { bold: true; pixelSize: 11 } }
                                InfoRow { k: "Intercept"; v: "42.827°N  20.355°E"; vc: "#FF9800" }
                                InfoRow { k: "Est. ETA";  v: "14:35:00 UTC";       vc: root.c_text }
                            }
                        }

                        Item { height: 4 }

                        SectionHeader { title: "DEFENCE ACTION" }

                        Rectangle {
                            width: 260; height: 108
                            Layout.alignment: Qt.AlignHCenter
                            color: "#1A1A2E"; border.color: root.c_deploy; border.width: 2; radius: 4
                            ColumnLayout {
                                anchors { fill: parent; margins: 8 }
                                spacing: 3
                                Text { text: "ACT-20260321-001"; color: root.c_warn
                                       font { bold: true; pixelSize: 11 } }
                                InfoRow { k: "Type";      v: "INTERCEPT";          vc: root.c_warn }
                                InfoRow { k: "Status";    v: "DEPLOYING";          vc: root.c_deploy }
                                InfoRow { k: "Target";    v: "TGT-001";            vc: root.c_text }
                                InfoRow { k: "System";    v: "UGV-BRAVO-002";      vc: root.c_ugv }
                                InfoRow { k: "Pos";       v: "42.827°N  20.355°E"; vc: root.c_text }
                                InfoRow { k: "Approved";  v: "jovic.m  [OP-0042]"; vc: root.c_dim }
                            }
                        }

                        Item { height: 4 }

                        SectionHeader { title: "SENSOR CONFIDENCE" }

                        ConfBar { label: "Acoustic  (x3)"; value: 0.93; barColor: root.c_sensor }
                        ConfBar { label: "Seismic   (x3)"; value: 0.87; barColor: root.c_warn }
                        ConfBar { label: "Radar  UAV/UGV"; value: 0.95; barColor: "#80CBC4" }
                        ConfBar { label: "Camera UAV/UGV"; value: 0.89; barColor: "#80DEEA" }
                        ConfBar { label: "Fused  output";  value: 0.93; barColor: root.c_uav }

                        Item { height: 10 }
                    }
                }
            }
        }

        // ── BOTTOM ACTION BAR ─────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 54
            color: "#0A1622"
            border.color: root.c_border; border.width: 1

            RowLayout {
                anchors { fill: parent; leftMargin: 16; rightMargin: 16 }
                spacing: 12

                Text {
                    text: "● MISSION ACTIVE  |  ALM-001: HIGH  |  ACT-001: DEPLOYING"
                    color: root.c_active; font { pixelSize: 11; bold: true }
                }

                Item { Layout.fillWidth: true }

                // Approve
                Rectangle {
                    width: 150; height: 32; radius: 4
                    color: hov.containsMouse ? "#1B5E20" : "#2E7D32"
                    border.color: "#4CAF50"; border.width: 1
                    Text { anchors.centerIn: parent; text: "✔  APPROVE ACTION"
                           color: "#FFFFFF"; font { bold: true; pixelSize: 11 } }
                    HoverHandler { id: hov }
                    TapHandler { onTapped: console.log("APPROVE ACTION clicked") }
                }

                // Deny
                Rectangle {
                    width: 140; height: 32; radius: 4
                    color: hovD.containsMouse ? "#B71C1C" : "#C62828"
                    border.color: "#EF5350"; border.width: 1
                    Text { anchors.centerIn: parent; text: "✘  DENY ACTION"
                           color: "#FFFFFF"; font { bold: true; pixelSize: 11 } }
                    HoverHandler { id: hovD }
                    TapHandler { onTapped: console.log("DENY ACTION clicked") }
                }

                Rectangle { width: 1; height: 28; color: root.c_border; opacity: 0.5 }

                // Standby All
                Rectangle {
                    width: 130; height: 32; radius: 4
                    color: hovS.containsMouse ? "#1565C0" : "#1976D2"
                    border.color: "#42A5F5"; border.width: 1
                    Text { anchors.centerIn: parent; text: "⏸  STANDBY ALL"
                           color: "#FFFFFF"; font { bold: true; pixelSize: 11 } }
                    HoverHandler { id: hovS }
                    TapHandler { onTapped: console.log("STANDBY ALL clicked") }
                }

                // Abort Mission
                Rectangle {
                    width: 148; height: 32; radius: 4
                    color: hovA.containsMouse ? "#4A1942" : "#6A1B9A"
                    border.color: "#CE93D8"; border.width: 1
                    Text { anchors.centerIn: parent; text: "⏹  ABORT MISSION"
                           color: "#FFFFFF"; font { bold: true; pixelSize: 11 } }
                    HoverHandler { id: hovA }
                    TapHandler { onTapped: console.log("ABORT MISSION clicked") }
                }
            }
        }
    }

    // ── Reusable inline components ─────────────────────────────────

    component TopChip: Item {
        property string label:      ""
        property string value:      ""
        property color  valueColor: root.c_text
        implicitWidth: col.implicitWidth
        implicitHeight: 40
        Column {
            id: col; spacing: 1; anchors.centerIn: parent
            Text { text: label; color: root.c_dim;  font.pixelSize: 9;  anchors.horizontalCenter: parent.horizontalCenter }
            Text { text: value; color: valueColor;  font { bold: true; pixelSize: 12; family: "Liberation Sans" } }
        }
    }

    component SectionHeader: Item {
        property string title: ""
        Layout.fillWidth: true
        height: 26
        Rectangle {
            anchors.fill: parent; color: "#0F1E30"
            border.color: "#1E3550"; border.width: 0
            Rectangle { width: parent.width; height: 1; color: "#1E3550"; anchors.bottom: parent.bottom }
        }
        Text { text: title; color: root.c_dim; font { pixelSize: 9; bold: true }
               anchors { left: parent.left; leftMargin: 10; verticalCenter: parent.verticalCenter } }
    }

    component DeviceCard: Item {
        property string name:        ""
        property string role:        ""
        property string statusText:  ""
        property color  statusColor: root.c_active
        property color  accentColor: root.c_uav
        property real   battery:     100
        property string detail1:     ""
        property string detail2:     ""
        Layout.fillWidth: true
        height: 82

        Rectangle {
            anchors { fill: parent; margins: 5 }
            color: root.c_card; radius: 4
            border.color: accentColor; border.width: 1

            ColumnLayout {
                anchors { fill: parent; margins: 7 }
                spacing: 3

                RowLayout {
                    spacing: 6
                    Rectangle { width: 8; height: 8; radius: 2; color: accentColor }
                    Text { text: name; color: accentColor; font { bold: true; pixelSize: 11 } }
                    Item { Layout.fillWidth: true }
                    Text { text: statusText; color: statusColor; font { bold: true; pixelSize: 10 } }
                }

                Text { text: role; color: root.c_dim; font.pixelSize: 9 }

                RowLayout {
                    spacing: 4
                    Text { text: "BAT"; color: root.c_dim; font.pixelSize: 9; width: 24 }
                    Rectangle {
                        width: 100; height: 7; color: "#1A2F45"; radius: 3; clip: true
                        Rectangle {
                            width: parent.width * battery / 100; height: parent.height; radius: 3
                            color: battery > 50 ? root.c_active : battery > 25 ? root.c_warn : root.c_armed
                        }
                    }
                    Text { text: battery + "%"; color: root.c_text; font.pixelSize: 9 }
                }

                Text { text: detail1; color: root.c_dim; font.pixelSize: 9 }
                Text { text: detail2; color: root.c_dim; font.pixelSize: 9 }
            }
        }
    }

    component WeaponCard: Item {
        property string sysId:    ""
        property string position: ""
        property bool   armed:    false
        property int    ammo:     0
        property string range:    ""
        Layout.fillWidth: true
        height: 52

        Rectangle {
            anchors { fill: parent; margins: 5 }
            color: root.c_card; radius: 4
            border.color: armed ? root.c_armed : root.c_standby; border.width: 1

            RowLayout {
                anchors { fill: parent; leftMargin: 8; rightMargin: 8; topMargin: 6; bottomMargin: 6 }
                spacing: 6

                Rectangle { width: 8; height: 8; radius: 2
                             color: armed ? root.c_armed : root.c_standby }

                Column {
                    spacing: 2
                    Text { text: sysId; color: armed ? root.c_pvo : root.c_gg
                           font { bold: true; pixelSize: 10 } }
                    Text { text: position + "  |  rng: " + range
                           color: root.c_dim; font.pixelSize: 9 }
                }

                Item { Layout.fillWidth: true }

                Column {
                    spacing: 2
                    Text { text: armed ? "ARMED" : "STANDBY"
                           color: armed ? root.c_armed : root.c_standby
                           font { bold: true; pixelSize: 9 } }
                    Text { text: "ammo: " + ammo; color: root.c_dim; font.pixelSize: 9 }
                }
            }
        }
    }

    component SensorCard: Item {
        property string sensorType: ""
        property string count:      ""
        property string detail:     ""
        property real   conf:       0.0
        property color  accentColor: root.c_sensor
        Layout.fillWidth: true
        height: 58

        Rectangle {
            anchors { fill: parent; margins: 5 }
            color: root.c_card; radius: 4
            border.color: accentColor; border.width: 1

            ColumnLayout {
                anchors { fill: parent; margins: 7 }
                spacing: 4

                RowLayout {
                    spacing: 6
                    Rectangle { width: 8; height: 8; radius: 4; color: accentColor }
                    Text { text: sensorType + "  " + count; color: accentColor
                           font { bold: true; pixelSize: 10 } }
                    Item { Layout.fillWidth: true }
                    Text { text: "● ACTIVE"; color: root.c_active; font { bold: true; pixelSize: 9 } }
                }

                Text { text: detail; color: root.c_dim; font.pixelSize: 9 }

                RowLayout {
                    spacing: 4
                    Text { text: "CONF"; color: root.c_dim; font.pixelSize: 9; width: 30 }
                    Rectangle {
                        width: 90; height: 6; color: "#1A2F45"; radius: 3; clip: true
                        Rectangle { width: parent.width * conf; height: parent.height; radius: 3; color: accentColor }
                    }
                    Text { text: Math.round(conf*100) + "%"; color: root.c_text; font.pixelSize: 9 }
                }
            }
        }
    }

    component InfoRow: Item {
        property string k:  ""
        property string v:  ""
        property color  vc: root.c_text
        Layout.fillWidth: true
        height: 14
        RowLayout {
            anchors.fill: parent
            spacing: 4
            Text { text: k + ":"; color: root.c_dim; font.pixelSize: 9; width: 68 }
            Text { text: v;       color: vc;          font { pixelSize: 9; bold: true }
                   Layout.fillWidth: true; elide: Text.ElideRight }
        }
    }

    component ConfBar: Item {
        property string label:    ""
        property real   value:    0
        property color  barColor: root.c_active
        Layout.fillWidth: true
        height: 30

        RowLayout {
            anchors { fill: parent; leftMargin: 10; rightMargin: 10 }
            spacing: 6
            Text { text: label; color: root.c_dim; font.pixelSize: 9; width: 110 }
            Rectangle {
                Layout.fillWidth: true; height: 8; radius: 3; color: "#1A2F45"; clip: true
                Rectangle {
                    width: parent.width * value; height: parent.height; radius: 3; color: barColor
                }
            }
            Text { text: Math.round(value*100) + "%"; color: root.c_text
                   font.pixelSize: 9; width: 30; horizontalAlignment: Text.AlignRight }
        }
    }
}

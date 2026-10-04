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

    // ── Live simulation data ───────────────────────────────────────────
    property var  uavsData:     []
    property var  ugvsData:     []
    property var  acousticData: []
    property var  seismicData:  []
    property var  trackData:    []
    property var  laydownData:  null
    property int  threatLevel:  0
    property real simTime:      0.0
    property int  timeScale:       1
    property var  zoneData:        null
    property var  targetsData:     []
    property var  engagementsData: []
    property var  eventsData:      []
    property var  linkData:        null
    property bool autoRoe:         false
    property bool showTruth:       true
    property bool editMode:        false
    property string editTool:      "ugv"
    property var  editMsg:         null
    property var  scenarioNames:   []
    property var  drivData:        null
    property var  pvoData:         null
    property var  catalogData:     null       // systems catalog (sim/systems.py)
    property var  perfData:        null       // sim process: effective speed, step time
    property var  backendData:     null
    property var  terrainData:     null       // 3D terrain (sim/terrain.py)
    property var  borderData:      null       // Serbia border / administrative line (sim/territory.py)
    property var  readinessData:   null       // phase CALM / ALERT / ATTACK, interception lines
    property bool show3D:          false
    property bool used3D:          false      // 3D scene stays loaded once opened
    onShow3DChanged: if (show3D) used3D = true
    property real driveOpacity:    0.35       // DRIVE layer opacity (2D and 3D)
    // DRIVE grid upscaled with smooth interpolation (cells blend instead of blocks)
    readonly property string drivSmoothUrl: drivData && drivData.ready && drivData.url
                                            ? terrainProvider.smooth(drivData.url) : ""
    property var  placeSystem:     ({ pvo: "STRELA_10M3", radar: "RPS42", gg: "ALAS" })
    property alias map2d:          mapCanvas
    property var  statsData:       ({kills: 0, baseHits: 0, assaults: 0})
    property var  enemyRoute:      null
    property var  detectionsData:  []
    property bool showDrive:       false
    function uavById(id) {
        for (var i = 0; i < uavsData.length; i++) if (uavsData[i].deviceId === id) return uavsData[i]
        return null
    }
    function convoyVehicles() { return laydownData && laydownData.convoy ? laydownData.convoy.vehicles : 0 }
    function convoyEscorts()  { return laydownData && laydownData.convoy ? laydownData.convoy.escortDrones : 0 }
    function convoyAviation() { return laydownData && laydownData.convoy ? laydownData.convoy.aviation : 0 }
    function countAirborne() {
        var n = 0
        for (var i = 0; i < uavsData.length; i++) if (uavsData[i].airborne) n++
        return n
    }

    // ── Kill-chain state derived from engagements ─────────────────
    readonly property var pendingEng: {
        for (var i = 0; i < engagementsData.length; i++)
            if (engagementsData[i].state === "PROPOSED") return engagementsData[i]
        return null
    }
    function countEng(state) {
        var n = 0
        for (var i = 0; i < engagementsData.length; i++)
            if (engagementsData[i].state === state) n++
        return n
    }
    function countIdentity(ident) {
        var n = 0
        for (var i = 0; i < trackData.length; i++)
            if (trackData[i].identity === ident && trackData[i].engState !== "NEUTRALIZED") n++
        return n
    }
    function trackColor(t) {
        return t.engState === "NEUTRALIZED" ? "#9E9E9E" : identityColor(t.identity)
    }
    function identityColor(ident) {
        return ident === "HOSTILE" ? "#F44336" : ident === "SUSPECT" ? "#FF9800" :
               ident === "NEUTRAL" ? "#4FC3F7" : "#FFEB3B"
    }
    function engStateColor(st) {
        return st === "PROPOSED" ? "#FFB300" : st === "APPROVED" ? "#FF9800" :
               st === "ENGAGING" ? "#EF5350" : st === "NEUTRALIZED" ? "#66BB6A" :
               st === "DENIED" ? "#90A4AE" : "#B0BEC5"
    }
    function siteStatus(p) {
        if (p.destroyed) return "DESTROYED"
        if (p.reloading) return "RELOADING"
        if (p.ammo <= 0 && p.gunBursts <= 0) return p.reserve > 0 ? "RELOADING" : "EMPTY"
        if (p.inFlight > 0) return "ENGAGING"
        return p.readyIn > 0 ? "cycle " + p.readyIn.toFixed(0) + " s" : "READY"
    }
    readonly property bool prereqTrack:    trackData.length > 0
    readonly property bool prereqHostile:  countIdentity("HOSTILE") > 0
    readonly property bool prereqPending:  pendingEng !== null
    readonly property bool prereqEffector: pendingEng !== null && pendingEng.effector !== ""
    readonly property bool missionReady:   prereqPending && prereqEffector

    Connections {
        target: simBus
        function onTimeUpdated(t)        { root.simTime = t }
        function onUavsUpdated(data)     { root.uavsData = data }
        function onUgvsUpdated(data)     { root.ugvsData = data }
        function onEditModeChanged(on)   { root.editMode = on; mapCanvas.requestPaint() }
        function onEditResult(r)         { root.editMsg = r }
        function onScenariosUpdated(n)   { root.scenarioNames = n }
        function onDrivabilityUpdated(d) { root.drivData = d; mapCanvas.requestPaint() }
        function onPvoUpdated(d)         { root.pvoData = d }
        function onStatsUpdated(d)       { root.statsData = d }
        function onEnemyRouteUpdated(d)  { root.enemyRoute = d }
        function onDetectionsUpdated(d)  { root.detectionsData = d }
        function onAcousticUpdated(data) { root.acousticData = data }
        function onSeismicUpdated(data)  { root.seismicData  = data }
        function onTracksUpdated(data)   { root.trackData = data }
        function onThreatUpdated(level)  { root.threatLevel = level }
        function onTargetsUpdated(data)  { root.targetsData = data; mapCanvas.requestPaint() }
        function onZoneUpdated(data)     { root.zoneData = data; mapCanvas.requestPaint() }
        function onLaydownUpdated(data) {
            var first = root.laydownData === null
            root.laydownData = data
            if (first) {
                mapCanvas.mapCenterLat = data.mapCenter.lat
                mapCanvas.mapCenterLon = data.mapCenter.lon
                mapCanvas.tileZoom     = data.mapCenter.zoom
            }
            mapCanvas.requestPaint()
        }
        function onEngagementsUpdated(data) { root.engagementsData = data }
        function onEventsUpdated(data)   { root.eventsData = data }
        function onLinkUpdated(data)     { root.linkData = data }
        function onAutoRoeChanged(on)    { root.autoRoe = on }
        function onCatalogUpdated(d)     { root.catalogData = d; root.placeSystem = d.defaults }
        function onPerfUpdated(d)        { root.perfData = d }
        function onBackendUpdated(d)     { root.backendData = d }
        function onBorderUpdated(d)      { root.borderData = d; mapCanvas.requestPaint() }
        function onReadinessUpdated(d)   { root.readinessData = d }
    }
    Connections {
        target: terrainProvider
        function onTerrainUpdated(d)     { root.terrainData = d }
    }


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
                    TopChip { label: "PHASE"
                               value: !root.readinessData || !root.readinessData.border ? "● ACTIVE"
                                      : root.readinessData.war ? "● WAR" + (root.readinessData.warT !== null && root.readinessData.warT !== undefined
                                                                        ? "  T+" + root.readinessData.warT.toFixed(0) + " s" : "")
                                      : root.readinessData.phase === "ALERT" ? "● ALERT — lines manned" : "● CALM"
                               valueColor: !root.readinessData ? root.c_active
                                           : root.readinessData.war ? root.c_armed
                                           : root.readinessData.phase === "ALERT" ? root.c_deploy : root.c_active }
                    TopChip { label: "T+";
                               value: root.simTime.toFixed(1) + " s"
                               valueColor: root.c_warn }

                    // ── Simulation speed buttons ────────────────────
                    Row {
                        spacing: 3
                        anchors.verticalCenter: parent.verticalCenter
                        Repeater {
                            model: [1, 2, 5, 10, 20, 50]
                            Rectangle {
                                width: 28; height: 20; radius: 3
                                color:        root.timeScale === modelData ? root.c_accent : "#0F2133"
                                border.color: root.timeScale === modelData ? "#64B5F6"   : root.c_border
                                border.width: 1
                                Text { anchors.centerIn: parent
                                       text: modelData + "×"
                                       color: root.timeScale === modelData ? "#FFFFFF" : root.c_dim
                                       font { pixelSize: 9; bold: true } }
                                HoverHandler { id: spHov }
                                TapHandler {
                                    onTapped: {
                                        root.timeScale = modelData
                                        simBus.setTimeScale(modelData)
                                    }
                                }
                            }
                        }
                    }
                    TopChip { label: "SIM";
                               value: root.backendData && !root.backendData.alive ? "DOWN" :
                                      root.perfData ? root.perfData.effective.toFixed(1) + "×  " +
                                                      root.perfData.stepMs.toFixed(1) + " ms  1/" +
                                                      root.perfData.displayEvery : "…"
                               valueColor: root.backendData && !root.backendData.alive ? root.c_armed :
                                           root.perfData && root.perfData.effective < root.timeScale * 0.8 ? root.c_deploy
                                                                                                           : root.c_active }
                    TopChip { label: "THREAT";
                               value: ["NONE","LOW","MEDIUM","HIGH"][root.threatLevel] || "NONE"
                               valueColor: root.threatLevel >= 3 ? root.c_armed :
                                           root.threatLevel >= 2 ? root.c_deploy :
                                           root.threatLevel >= 1 ? root.c_warn  : root.c_dim }
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

                        Repeater {
                            model: root.uavsData
                            DeviceCard {
                                badge: "air_friend_uav"
                                name: modelData.deviceId
                                role: "INTERCEPTOR  |  " + modelData.mode
                                accentColor: root.c_uav
                                statusText: modelData.expended ? "EXPENDED" : modelData.airborne ? "AIRBORNE" : "IDLE @ BASE"
                                statusColor: modelData.expended ? root.c_standby : modelData.mode === "INTERCEPT" ? root.c_armed
                                           : modelData.airborne ? root.c_deploy : root.c_standby
                                battery: modelData.batteryPct
                                detail1: modelData.airborne ?
                                    ("Alt: " + modelData.altitudeM.toFixed(0) + " m  |  " +
                                     (modelData.speedMs * 3.6).toFixed(0) + " km/h  |  Hdg " + modelData.headingDeg.toFixed(0) + "°")
                                    : "On the pad, charging"
                                detail2: modelData.assignedTrack ? "▶ INTERCEPT " + modelData.assignedTrack
                                         : modelData.mode === "PATROL" ? (modelData.station ? "Patrol orbit on the interception line"
                                                                                            : "Patrol over base (on call)") : ""
                                actionLabel: modelData.assignedTrack ? ""
                                             : modelData.mode === "IDLE" ? "▲ LAUNCH"
                                             : (modelData.mode === "PATROL" || modelData.mode === "LAUNCHING") ? "▼ RECALL" : ""
                                onAction: modelData.mode === "IDLE" ? simBus.launchInterceptor(modelData.deviceId)
                                                                    : simBus.recallInterceptor(modelData.deviceId)
                            }
                        }
                        Repeater {
                            model: root.ugvsData
                            DeviceCard {
                                badge: "gnd_friend_ugv"
                                name: modelData.deviceId
                                role: "JAMMER + CHARGES  |  " + (modelData.jamming ? "JAMMING " + modelData.assignedTrack
                                      : modelData.assignedTrack ? (modelData.weapon === "CHARGE" ? "FIRE → " : "→ ") + modelData.assignedTrack
                                      : "STANDBY")
                                accentColor: root.c_ugv
                                statusText: modelData.destroyed ? "DESTROYED" : modelData.status
                                statusColor: modelData.destroyed ? root.c_armed
                                             : modelData.status === "DEPLOYED" ? root.c_active : root.c_deploy
                                battery: modelData.batteryPct
                                detail1: "Spd: " + modelData.speedKmh.toFixed(0) + " km/h  |  " + modelData.terrain +
                                         "  |  charges " + modelData.charges + "/" + modelData.maxCharges
                                detail2: (modelData.station ? "Line position  |  " : "") + "Route: " + modelData.routeSource
                            }
                        }

                        // ── Air Defence ───────────────────────────
                        SectionHeader {
                            title: "AIR DEFENCE  (PVO x" + (root.pvoData ? root.pvoData.sites.length : 0) + ")  —  " +
                                   (root.pvoData && root.pvoData.enabled ? "AUTO" : "HOLD FIRE")
                        }

                        Repeater {
                            model: root.pvoData ? root.pvoData.sites : []
                            WeaponCard {
                                badge: modelData.gunRangeM > 0 ? "site_pvo_gun" : "site_pvo_sam"
                                sysId: modelData.id + "  " + modelData.name
                                position: root.siteStatus(modelData) + "  |  kills " + modelData.kills
                                armed: !modelData.destroyed && root.pvoData.enabled && (modelData.ammo + modelData.reserve + modelData.gunBursts) > 0
                                ammo: modelData.ammo + "+" + modelData.reserve +
                                      (modelData.gunRangeM > 0 ? "  gun " + modelData.gunBursts : "")
                                range: (modelData.minRangeM / 1000).toFixed(1) + "–" + (modelData.rangeM / 1000).toFixed(0) + " km"
                            }
                        }

                        SectionHeader { title: "GROUND SYSTEMS  (GG x" + (root.pvoData ? root.pvoData.gg.length : 0) + ")  —  " +
                                               (root.pvoData && root.pvoData.ggEnabled ? "WEAPONS FREE" : "HOLD (AUTO-ROE off)") }

                        Repeater {
                            model: root.pvoData ? root.pvoData.gg : []
                            WeaponCard {
                                badge: "site_ssm"
                                sysId: modelData.id + "  " + modelData.name
                                position: root.siteStatus(modelData) + "  |  kills " + modelData.kills
                                armed: !modelData.destroyed && root.pvoData.ggEnabled && modelData.ammo > 0
                                ammo: modelData.ammo
                                range: (modelData.rangeM / 1000).toFixed(0) + " km"
                            }
                        }

                        // ── Field Sensors ─────────────────────────
                        SectionHeader { title: "FIELD SENSORS" }

                        SensorCard { sensorType: "ACOUSTIC"
                                     count: "x" + (root.laydownData ? root.laydownData.acoustic.length : 0)
                                     detail: "Air 10 km / ground 2–3 km, bearing only"
                                     conf: root.acousticData.length > 0 ? Math.max.apply(null, root.acousticData.map(function(a) { return a.confidence })) : 0
                                     accentColor: root.c_sensor }
                        SensorCard { sensorType: "SEISMIC"
                                     count: "x" + (root.laydownData ? root.laydownData.seismic.length : 0)
                                     detail: "Ground vehicles 5–10 km, bearing"
                                     conf: root.seismicData.length > 0 ? Math.max.apply(null, root.seismicData.map(function(a) { return a.confidence })) : 0
                                     accentColor: root.c_warn }
                        SectionHeader { title: "RADARS  (x" + (root.laydownData ? root.laydownData.radars.length : 0) + ")" }
                        Repeater {
                            model: root.laydownData ? root.laydownData.radars : []
                            WeaponCard {
                                badge: "site_radar"
                                sysId: modelData.label + "  " + (modelData.systemName || "")
                                position: modelData.lat.toFixed(4) + "°N " + modelData.lon.toFixed(4) + "°E"
                                armed: true
                                ammo: "—"
                                range: (modelData.rangeM / 1000).toFixed(0) + " km vs −15 dBsm"
                            }
                        }

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
                        Text { text: "C-UAS MAP  —  " + (root.laydownData ? root.laydownData.name + "  —  " : "") +
                                     (root.zoneData ? root.zoneData.zoneId + " / " + root.zoneData.asset.id : "")
                               color: root.c_dim; font { pixelSize: 10; family: "monospace" } }
                        Item { Layout.fillWidth: true }

                        Text {
                            visible: root.drivData !== null && (root.showDrive || root.drivData.status.indexOf("loading") === 0)
                            text: root.drivData ? "drivability: " + root.drivData.status : ""
                            color: root.drivData && root.drivData.ready ? root.c_active : root.c_warn
                            font { pixelSize: 9; family: "monospace" }
                            Layout.maximumWidth: 360; elide: Text.ElideRight
                        }
                        Text { visible: root.showDrive; text: "α"; color: root.c_dim; font.pixelSize: 10 }
                        Slider {
                            visible: root.showDrive
                            from: 0.1; to: 1.0; stepSize: 0.05
                            value: root.driveOpacity
                            implicitWidth: 80; implicitHeight: 18
                            onMoved: { root.driveOpacity = value; mapCanvas.requestPaint() }
                        }
                        Rectangle {
                            width: 36; height: 18; radius: 3
                            color: root.show3D ? "#00838F" : "#1E3550"
                            border.color: root.show3D ? "#4DD0E1" : "#2E4560"
                            Text { anchors.centerIn: parent; text: "3D"
                                   color: "#FFFFFF"; font { pixelSize: 9; bold: true } }
                            TapHandler { onTapped: root.show3D = !root.show3D }
                        }
                        Rectangle {
                            width: 50; height: 18; radius: 3
                            color: root.showTruth ? "#6D4C41" : "#1E3550"
                            border.color: root.showTruth ? "#BCAAA4" : "#2E4560"
                            Text { anchors.centerIn: parent; text: "TRUTH"
                                   color: "#FFFFFF"; font { pixelSize: 9; bold: true } }
                            TapHandler { onTapped: { root.showTruth = !root.showTruth; mapCanvas.requestPaint() } }
                        }
                        Rectangle {
                            width: 50; height: 18; radius: 3
                            color: root.showDrive ? "#2E7D32" : "#1E3550"
                            border.color: root.showDrive ? "#66BB6A" : "#2E4560"
                            Text { anchors.centerIn: parent; text: "DRIVE"
                                   color: "#FFFFFF"; font { pixelSize: 9; bold: true } }
                            TapHandler {
                                onTapped: {
                                    root.showDrive = !root.showDrive
                                    if (root.showDrive && (!root.drivData || !root.drivData.ready))
                                        simBus.loadDrivability(false)
                                    mapCanvas.requestPaint()
                                }
                            }
                        }

                        // Map type toggle buttons
                        Repeater {
                            model: ["SAT", "TOPO", "OSM"]
                            Rectangle {
                                required property string modelData
                                property string mapKey: modelData === "SAT" ? "satellite" : modelData.toLowerCase()
                                width: 36; height: 18; radius: 3
                                color: mapCanvas.mapType === mapKey ? root.c_accent : "#1E3550"
                                border.color: mapCanvas.mapType === mapKey ? root.c_accent : "#2E4560"
                                Text { anchors.centerIn: parent; text: modelData
                                       color: "#FFFFFF"; font { pixelSize: 9; bold: true } }
                                TapHandler {
                                    onTapped: {
                                        mapCanvas.mapType = parent.mapKey
                                        mapCanvas.requestPaint()
                                    }
                                }
                            }
                        }

                        Text { text: "  " + mapCanvas.mapCenterLat.toFixed(4) + "°N  " +
                                         mapCanvas.mapCenterLon.toFixed(4) + "°E  z" + mapCanvas.tileZoom
                               color: root.c_dim; font { pixelSize: 10; family: "monospace" } }
                    }
                }

                // ── Scenario editor toolbar (edit mode) ───────────────
                Rectangle {
                    id: editBar
                    visible: root.editMode
                    z: 20
                    anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 8 }
                    height: 96; radius: 5
                    color: "#E60D1B2A"; border.color: root.c_deploy; border.width: 1

                    ColumnLayout {
                        anchors { fill: parent; margins: 8 }
                        spacing: 5
                        RowLayout {
                            spacing: 4
                            Text { text: "✎ EDIT"; color: root.c_deploy; font { bold: true; pixelSize: 11 } }
                            Repeater {
                                model: [
                                    { key: "move",     label: "✥ MOVE" },
                                    { key: "base",     label: "◆ BASE" },
                                    { key: "ugv",      label: "▣ UGV" },
                                    { key: "pvo",      label: "◈ PVO" },
                                    { key: "gg",       label: "▼ GG" },
                                    { key: "radar",    label: "▲ RADAR" },
                                    { key: "acoustic", label: "◉ ACOUSTIC" },
                                    { key: "seismic",  label: "≈ SEISMIC" },
                                    { key: "delete",   label: "✘ DELETE" },
                                ]
                                ActionButton {
                                    width: 72; height: 22
                                    label: modelData.label
                                    base: root.editTool === modelData.key ? "#1976D2" : "#1E3550"
                                    edge: root.editTool === modelData.key ? "#90CAF9" : "#2E4560"
                                    onClicked: {
                                        if (root.editTool === "move" && modelData.key !== "move") simBus.cancelMove()
                                        root.editTool = modelData.key
                                        mapCanvas.requestPaint()
                                    }
                                }
                            }
                            ComboBox {
                                id: sysPick
                                readonly property var items: root.catalogData && root.catalogData.byKind[root.editTool]
                                                             ? root.catalogData.byKind[root.editTool] : []
                                visible: items.length > 0
                                Layout.preferredWidth: 230; implicitHeight: 22
                                font.pixelSize: 10
                                model: items.map(function(s) { return s.name + "  (" + (s.rangeM / 1000).toFixed(0) + " km)" })
                                currentIndex: items.findIndex(function(s) { return s.code === root.placeSystem[root.editTool] })
                                onActivated: function(i) {
                                    var ps = Object.assign({}, root.placeSystem)
                                    ps[root.editTool] = items[i].code
                                    root.placeSystem = ps
                                    simBus.setPlaceSystem(root.editTool, items[i].code)
                                }
                            }
                            Item { Layout.fillWidth: true }
                            ActionButton { width: 70; height: 22; label: "▶ RUN"; base: "#2E7D32"; edge: "#66BB6A"
                                           onClicked: simBus.setEditMode(false) }
                        }
                        RowLayout {
                            spacing: 6
                            Text { text: "Zone"; color: root.c_dim; font.pixelSize: 10 }
                            ActionButton { width: 22; height: 22; label: "−"; base: "#1E3550"; edge: "#2E4560"
                                           onClicked: simBus.setZoneRadius(root.laydownData.zoneRadiusM - 250) }
                            Text { text: root.laydownData ? (root.laydownData.zoneRadiusM / 1000).toFixed(2) + " km" : ""
                                   color: root.c_text; font { pixelSize: 10; bold: true } }
                            ActionButton { width: 22; height: 22; label: "+"; base: "#1E3550"; edge: "#2E4560"
                                           onClicked: simBus.setZoneRadius(root.laydownData.zoneRadiusM + 250) }
                            Rectangle { width: 1; height: 20; color: root.c_border }
                            Text { text: "Interceptors"; color: root.c_dim; font.pixelSize: 10 }
                            ActionButton { width: 22; height: 22; label: "−"; base: "#1E3550"; edge: "#2E4560"
                                           onClicked: simBus.setInterceptors(root.laydownData.interceptors - 1) }
                            Text { text: root.laydownData ? root.laydownData.interceptors : ""
                                   color: root.c_text; font { pixelSize: 10; bold: true } }
                            ActionButton { width: 22; height: 22; label: "+"; base: "#1E3550"; edge: "#2E4560"
                                           onClicked: simBus.setInterceptors(root.laydownData.interceptors + 1) }
                            Rectangle { width: 1; height: 20; color: root.c_border }
                            Text { text: "Trucks"; color: root.c_dim; font.pixelSize: 10 }
                            ActionButton { width: 20; height: 22; label: "−"; base: "#1E3550"; edge: "#2E4560"
                                           onClicked: simBus.setConvoy(root.convoyVehicles() - 1, root.convoyEscorts(), root.convoyAviation()) }
                            Text { text: root.convoyVehicles(); color: "#FF8A80"; font { pixelSize: 10; bold: true } }
                            ActionButton { width: 20; height: 22; label: "+"; base: "#1E3550"; edge: "#2E4560"
                                           onClicked: simBus.setConvoy(root.convoyVehicles() + 1, root.convoyEscorts(), root.convoyAviation()) }
                            Text { text: "UAV"; color: root.c_dim; font.pixelSize: 10 }
                            ActionButton { width: 20; height: 22; label: "−"; base: "#1E3550"; edge: "#2E4560"
                                           onClicked: simBus.setConvoy(root.convoyVehicles(), root.convoyEscorts() - 5, root.convoyAviation()) }
                            Text { text: root.convoyEscorts(); color: "#FF8A80"; font { pixelSize: 10; bold: true } }
                            ActionButton { width: 20; height: 22; label: "+"; base: "#1E3550"; edge: "#2E4560"
                                           onClicked: simBus.setConvoy(root.convoyVehicles(), root.convoyEscorts() + 5, root.convoyAviation()) }
                            Text { text: "Helo"; color: root.c_dim; font.pixelSize: 10 }
                            ActionButton { width: 20; height: 22; label: "−"; base: "#1E3550"; edge: "#2E4560"
                                           onClicked: simBus.setConvoy(root.convoyVehicles(), root.convoyEscorts(), root.convoyAviation() - 1) }
                            Text { text: root.convoyAviation(); color: "#FF8A80"; font { pixelSize: 10; bold: true } }
                            ActionButton { width: 20; height: 22; label: "+"; base: "#1E3550"; edge: "#2E4560"
                                           onClicked: simBus.setConvoy(root.convoyVehicles(), root.convoyEscorts(), root.convoyAviation() + 1) }
                            Rectangle { width: 1; height: 20; color: root.c_border }
                            TextField {
                                id: scenarioName
                                Layout.preferredWidth: 110; implicitHeight: 24
                                placeholderText: "scenario name"
                                text: root.laydownData ? root.laydownData.name : ""
                                font.pixelSize: 10; color: root.c_text
                                background: Rectangle { color: "#0F2133"; border.color: root.c_border; radius: 3 }
                            }
                            ActionButton { width: 64; height: 22; label: "💾 SAVE"; base: "#1565C0"; edge: "#42A5F5"
                                           onClicked: simBus.saveScenario(scenarioName.text) }
                            ComboBox {
                                id: scenarioPick
                                Layout.fillWidth: true; implicitHeight: 24
                                model: root.scenarioNames
                                font.pixelSize: 10
                            }
                            ActionButton { width: 64; height: 22; label: "📂 LOAD"; base: "#1565C0"; edge: "#42A5F5"
                                           onClicked: if (scenarioPick.currentText) simBus.loadScenario(scenarioPick.currentText) }
                        }
                        Text {
                            Layout.fillWidth: true
                            elide: Text.ElideRight
                            text: root.editMsg ? root.editMsg.message
                                  : (root.editTool === "move" ? "MOVE: click an item to pick it, then click its new position."
                                     : "Click on the map to place the selected item. UGVs only on drivable terrain inside the artemides area.")
                            color: root.editMsg ? (root.editMsg.ok ? root.c_active : "#FF8A80") : root.c_dim
                            font.pixelSize: 10
                        }
                    }
                }

                // Base map tiles in their own canvas: repainted only on pan / zoom /
                // map type, not on every simulation frame
                Canvas {
                    id: tileCanvas
                    anchors { fill: parent; topMargin: 28 }
                    onImageLoaded: requestPaint()
                    onWidthChanged: requestPaint()
                    onHeightChanged: requestPaint()
                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.fillStyle = "#1A2A3A"
                        ctx.fillRect(0, 0, width, height)
                        mapCanvas.drawTiles(ctx, tileCanvas)
                    }
                    Connections {
                        target: tileCache
                        function onTileReady(url) { tileCanvas.requestPaint() }
                    }
                    Connections {
                        target: mapCanvas
                        function onMapCenterLatChanged() { tileCanvas.requestPaint() }
                        function onMapCenterLonChanged() { tileCanvas.requestPaint() }
                        function onTileZoomChanged()     { tileCanvas.requestPaint() }
                        function onMapTypeChanged()      { tileCanvas.requestPaint() }
                    }
                }

                // 3D terrain view (Map3D.qml) — created on first use
                Loader {
                    id: map3d
                    anchors { fill: parent; topMargin: 28 }
                    z: 5
                    active: root.show3D || root.used3D
                    visible: root.show3D
                    source: "Map3D.qml"
                    onLoaded: item.dash = root
                }

                // ── NATO symbols (APP-6, symbols/*.svg) as sharp Image items ──
                Item {
                    id: symLayer
                    anchors { fill: parent; topMargin: 28 }
                    z: 1
                    visible: !root.show3D
                    clip: true
                    readonly property var ld: root.laydownData
                    readonly property var uavsUp: root.uavsData.filter(function(u) { return u.airborne })
                    readonly property var truth: root.showTruth ? root.targetsData : []
                    readonly property var pvoSites: root.pvoData ? root.pvoData.sites : []
                    readonly property var ggSites: root.pvoData ? root.pvoData.gg : []

                    Repeater {
                        model: symLayer.ld ? symLayer.ld.acoustic.length : 0
                        MapIcon {
                            required property int index
                            readonly property var d: symLayer.ld.acoustic[index] || ({})
                            icon: root.acousticData.length > index && root.acousticData[index].detected ? "acoustic_suspect" : "acoustic_friend"
                            lat: d.lat || 0; lon: d.lon || 0; size: 20
                            tip: (d.label || "") + "  acoustic array"
                        }
                    }
                    Repeater {
                        model: symLayer.ld ? symLayer.ld.seismic.length : 0
                        MapIcon {
                            required property int index
                            readonly property var d: symLayer.ld.seismic[index] || ({})
                            icon: root.seismicData.length > index && root.seismicData[index].detected ? "seismic_suspect" : "seismic_friend"
                            lat: d.lat || 0; lon: d.lon || 0; size: 20
                            tip: (d.label || "") + "  seismic array"
                        }
                    }
                    Repeater {
                        model: symLayer.ld ? symLayer.ld.radars.length : 0
                        MapIcon {
                            required property int index
                            readonly property var d: symLayer.ld.radars[index] || ({})
                            icon: "radar_friend"; lat: d.lat || 0; lon: d.lon || 0; size: 26
                            tip: (d.label || "") + "  " + (d.systemName || "") + "  " + ((d.rangeM || 0) / 1000).toFixed(0) + " km"
                        }
                    }
                    Repeater {
                        model: symLayer.pvoSites.length
                        MapIcon {
                            required property int index
                            readonly property var d: symLayer.pvoSites[index] || ({})
                            icon: (d.gunRangeM > 0 ? "spaag" : "sam") + (d.destroyed ? "_dead" : "_friend")
                            lat: d.lat || 0; lon: d.lon || 0; size: 28
                            tip: (d.id || "") + "  " + (d.name || "") + "  ammo " + d.ammo + "+" + d.reserve +
                                 (d.gunRangeM > 0 ? "  gun " + d.gunBursts : "") + "  " + root.siteStatus(d)
                            opacity: root.pvoData && root.pvoData.enabled && (d.ammo + d.reserve + d.gunBursts) > 0 ? 1.0 : 0.45
                        }
                    }
                    Repeater {
                        model: symLayer.ggSites.length
                        MapIcon {
                            required property int index
                            readonly property var d: symLayer.ggSites[index] || ({})
                            icon: d.destroyed ? "ssm_dead" : "ssm_friend"; lat: d.lat || 0; lon: d.lon || 0; size: 28
                            tip: (d.id || "") + "  " + (d.name || "") + "  ammo " + d.ammo
                            opacity: root.pvoData && root.pvoData.ggEnabled && d.ammo > 0 ? 1.0 : 0.45
                        }
                    }
                    Repeater {
                        model: root.ugvsData.length
                        MapIcon {
                            required property int index
                            readonly property var d: root.ugvsData[index] || ({})
                            icon: d.destroyed ? "ugv_dead" : "ugv_friend"; lat: d.lat || 0; lon: d.lon || 0; size: 28
                            heading: d.headingDeg || 0
                            tip: (d.deviceId || "") + "  " + (d.status || "") + "  " + (d.speedKmh || 0) + " km/h  charges " + d.charges
                        }
                    }
                    Repeater {
                        model: symLayer.uavsUp.length
                        MapIcon {
                            required property int index
                            readonly property var d: symLayer.uavsUp[index] || ({})
                            icon: "quad_friend"; lat: d.lat || 0; lon: d.lon || 0; size: 26
                            heading: d.headingDeg || 0
                            tip: (d.deviceId || "") + "  " + (d.mode || "") + "  " + Math.round(d.altitudeM || 0) + " m"
                        }
                    }
                    Repeater {
                        model: symLayer.truth.length
                        MapIcon {
                            required property int index
                            readonly property var d: symLayer.truth[index] || ({})
                            readonly property bool dead: d.state === "DESTROYED" || d.state === "LANDED" || d.state === "DISABLED"
                            visible: d.state !== "PENDING"
                            icon: mapCanvas.iconShape(d.domain, d.cls) + (dead ? "_dead" : d.hostile ? "_hostile" : "_neutral")
                            lat: d.lat || 0; lon: d.lon || 0; size: 16
                            tip: "TRUTH " + (d.id || "") + "  " + (d.state || "")
                            opacity: dead ? 0.25 : 0.55
                        }
                    }
                    Repeater {
                        model: root.trackData.length
                        MapIcon {
                            required property int index
                            readonly property var d: root.trackData[index] || ({})
                            icon: d.trackId ? mapCanvas.trackIcon(d) : ""
                            lat: d.lat || 0; lon: d.lon || 0; size: d.domain === "GROUND" ? 26 : 28
                            heading: d.headingDeg || 0
                            tip: (d.trackId || "") + "  " + (d.identity || "") + "  " + Math.round((d.speedMs || 0) * 3.6) + " km/h" +
                                 (d.domain === "GROUND" ? "  vehicle" : "  " + Math.round(d.altitudeM || 0) + " m") +
                                 (d.objClass && d.objClass !== "UNKNOWN" ? "  " + d.objClass : "") +
                                 (d.engState ? "  " + d.engState : "")
                            opacity: d.engState === "NEUTRALIZED" ? 0.5 : (d.status === "COASTING" ? 0.65 : 1.0)
                        }
                    }

                    // Legend (APP-6) — top right
                    Rectangle {
                        anchors { right: parent.right; top: parent.top; margins: 10 }
                        width: legendCol.implicitWidth + 20; height: legendCol.implicitHeight + 16
                        radius: 4
                        color: "#D90D1B2A"; border.color: root.c_border
                        Column {
                            id: legendCol
                            anchors { left: parent.left; top: parent.top; margins: 8; leftMargin: 10 }
                            spacing: 3
                            Text { text: "LEGEND"; color: root.c_dim; font { pixelSize: 9; bold: true } }
                            Repeater {
                                model: [
                                    ["quad_friend",    "Own interceptor UAV"],
                                    ["ugv_friend",     "Own UGV (jammer)"],
                                    ["quad_hostile",   "Hostile UAV"],
                                    ["wing_hostile",   "Hostile fixed-wing UAV"],
                                    ["helo_hostile",   "Hostile attack helo"],
                                    ["truck_hostile",  "Hostile vehicle"],
                                    ["quad_suspect",   "Suspect track"],
                                    ["quad_neutral",   "Neutral track"],
                                    ["quad_unknown",   "Unknown track"],
                                    ["sam_friend",     "PVO missile"],
                                    ["spaag_friend",   "PVO gun-missile"],
                                    ["ssm_friend",     "GG (ALAS)"],
                                    ["radar_friend",   "Radar"],
                                    ["acoustic_friend", "Acoustic array"],
                                    ["seismic_friend", "Seismic array"],
                                    ["sam_dead",       "Destroyed"]
                                ]
                                Row {
                                    required property var modelData
                                    spacing: 6
                                    Item {
                                        width: 22; height: 20
                                        Image {
                                            anchors.centerIn: parent
                                            source: symbolsInfo.icons + modelData[0] + ".svg"
                                            sourceSize: Qt.size(20, 20)
                                            smooth: true
                                        }
                                    }
                                    Text { text: modelData[1]; color: "#C8D8E4"; font.pixelSize: 10
                                           anchors.verticalCenter: parent.verticalCenter }
                                }
                            }
                        }
                    }
                }

                Canvas {
                    objectName: "mapCanvas"
                    id: mapCanvas
                    anchors { fill: parent; topMargin: 28 }

                    // ── Map tile configuration ────────────────────────
                    property real   mapCenterLat: 42.27442     // replaced by laydown on start
                    property real   mapCenterLon: 21.606345
                    property int    tileZoom:     12      // wider view: ~28 m/px at this lat
                    property int    tileSize:     256
                    property string mapType:      "satellite"  // satellite | topo | osm

                    onImageLoaded: requestPaint()

                    // ── Web Mercator tile helpers ─────────────────────
                    function _lonToTf(lon) {
                        return (lon + 180) / 360 * Math.pow(2, tileZoom)
                    }
                    function _latToTf(lat) {
                        var r = lat * Math.PI / 180
                        return (1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2
                               * Math.pow(2, tileZoom)
                    }

                    // ── Screen coordinate helpers ─────────────────────
                    function lonToX(lon) {
                        return (_lonToTf(lon) - _lonToTf(mapCenterLon)) * tileSize + width  / 2
                    }
                    function latToY(lat) {
                        return (_latToTf(lat) - _latToTf(mapCenterLat)) * tileSize + height / 2
                    }

                    // ── Inverse projection (pixel → geo) ──────────────
                    function xToLon(px) {
                        var tf = (px - width / 2) / tileSize + _lonToTf(mapCenterLon)
                        return tf / Math.pow(2, tileZoom) * 360 - 180
                    }
                    function yToLat(py) {
                        var tf = (py - height / 2) / tileSize + _latToTf(mapCenterLat)
                        return tileFloatToLat(tf)
                    }
                    function tileFloatToLat(tf) {
                        var n = Math.PI * (1 - 2 * tf / Math.pow(2, tileZoom))
                        return 180 / Math.PI * Math.atan(Math.sinh(n))
                    }

                    // ── Mouse wheel — zoom toward cursor ──────────────
                    // 2D input is off while the 3D view covers the map — otherwise these
                    // handlers (underneath) steal the 3D view's drags
                    WheelHandler {
                        enabled: !root.show3D
                        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
                        onWheel: function(event) {
                            var steps   = event.angleDelta.y > 0 ? 1 : -1
                            var newZoom = Math.max(8, Math.min(18, mapCanvas.tileZoom + steps))
                            if (newZoom === mapCanvas.tileZoom) { event.accepted = true; return }

                            // Geographic point under cursor (computed in OLD zoom)
                            var px   = event.x
                            var py   = event.y
                            var lon0 = mapCanvas.xToLon(px)
                            var lat0 = mapCanvas.yToLat(py)

                            mapCanvas.tileZoom = newZoom   // switch zoom

                            // Re-centre so (lon0, lat0) stays under cursor in new zoom
                            var newTfX = mapCanvas._lonToTf(lon0) - (px - mapCanvas.width  / 2) / mapCanvas.tileSize
                            var newTfY = mapCanvas._latToTf(lat0) - (py - mapCanvas.height / 2) / mapCanvas.tileSize
                            mapCanvas.mapCenterLon = newTfX / Math.pow(2, newZoom) * 360 - 180
                            mapCanvas.mapCenterLat = mapCanvas.tileFloatToLat(newTfY)

                            mapCanvas.requestPaint()
                            event.accepted = true
                        }
                    }

                    // ── Editor: click places the selected item ───────
                    TapHandler {
                        enabled: root.editMode && !root.show3D
                        onTapped: function(eventPoint, button) {
                            simBus.editPlace(root.editTool,
                                             mapCanvas.yToLat(eventPoint.position.y),
                                             mapCanvas.xToLon(eventPoint.position.x))
                        }
                    }

                    // ── Drag handler — pan ────────────────────────────
                    DragHandler {
                        id: panHandler
                        enabled: !root.show3D
                        property real anchorLon: 0
                        property real anchorLat: 0

                        onActiveChanged: {
                            if (active) {
                                anchorLon = mapCanvas.xToLon(centroid.pressPosition.x)
                                anchorLat = mapCanvas.yToLat(centroid.pressPosition.y)
                            }
                        }
                        onCentroidChanged: {
                            if (!active) return
                            var cx = centroid.position.x
                            var cy = centroid.position.y
                            var z  = mapCanvas.tileZoom
                            var ts = mapCanvas.tileSize

                            var newTfX = mapCanvas._lonToTf(anchorLon) - (cx - mapCanvas.width  / 2) / ts
                            var newTfY = mapCanvas._latToTf(anchorLat) - (cy - mapCanvas.height / 2) / ts
                            mapCanvas.mapCenterLon = newTfX / Math.pow(2, z) * 360 - 180
                            mapCanvas.mapCenterLat = mapCanvas.tileFloatToLat(newTfY)
                            mapCanvas.requestPaint()
                        }
                        cursorShape: active ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                    }
                    function lbl(ctx, text, x, y, color) {
                        ctx.font = "bold 9px sans-serif"
                        ctx.fillStyle = "rgba(0,0,0,0.75)"
                        ctx.fillText(text, x+1, y+1)
                        ctx.fillStyle = color
                        ctx.fillText(text, x, y)
                    }

                    // ── Tile URL ──────────────────────────────────────
                    // Tiles come from the Python tile cache (sim/tiles.py): a local file URL, or ""
                    // while it downloads — tileCache.tileReady repaints when it arrives
                    function tileUrl(tx, ty, z) {
                        return tileCache.url(mapType, z, tx, ty)
                    }

                    // ── Draw map tiles ────────────────────────────────
                    function drawTiles(ctx, cv) {
                        var cTX  = _lonToTf(mapCenterLon)
                        var cTY  = _latToTf(mapCenterLat)
                        var nX   = Math.ceil(width  / (2 * tileSize)) + 1
                        var nY   = Math.ceil(height / (2 * tileSize)) + 1
                        var maxT = Math.pow(2, tileZoom) - 1

                        for (var ty = Math.floor(cTY) - nY; ty <= Math.floor(cTY) + nY; ty++) {
                            for (var tx = Math.floor(cTX) - nX; tx <= Math.floor(cTX) + nX; tx++) {
                                if (tx < 0 || ty < 0 || tx > maxT || ty > maxT) continue
                                var url = tileUrl(tx, ty, tileZoom)
                                var px  = (tx - cTX) * tileSize + width  / 2
                                var py  = (ty - cTY) * tileSize + height / 2
                                if (url === "") continue
                                if (cv.isImageLoaded(url))
                                    ctx.drawImage(url, px, py, tileSize, tileSize)
                                else
                                    cv.loadImage(url)
                            }
                        }
                    }

                    // NATO symbols are QML Image items (symLayer below), not canvas
                    // bitmaps: an SVG rendered at its on-screen size stays sharp
                    // Plain map icon (icons/<shape>_<colour>.svg) for a track / truth object
                    function iconColour(identity) {
                        return identity === "HOSTILE" ? "hostile" : identity === "SUSPECT" ? "suspect"
                             : identity === "NEUTRAL" ? "neutral" : "unknown"
                    }
                    function iconShape(domain, cls) {
                        return domain === "GROUND" ? "truck" : cls === "ATTACK_HELICOPTER" ? "helo"
                             : cls === "UAV_FIXED_WING" ? "wing" : "quad"
                    }
                    function trackIcon(t) {
                        return iconShape(t.domain, t.objClass) + "_" +
                               (t.engState === "NEUTRALIZED" ? "dead" : iconColour(t.identity))
                    }
                    function trackSymbol(t) {
                        var id = t.identity
                        if (t.domain === "GROUND")
                            return id === "HOSTILE" ? "gnd_hostile_truck" : id === "SUSPECT" ? "gnd_suspect_truck" : "gnd_unknown"
                        if (id === "HOSTILE") return t.objClass === "ATTACK_HELICOPTER" ? "air_hostile_helo" : "air_hostile_uav"
                        if (id === "SUSPECT") return "air_suspect_uav"
                        if (id === "NEUTRAL") return "air_neutral_uav"
                        return "air_unknown"
                    }

                    function drawAcoustic(ctx, lat, lon, label, detected) {
                        var x = lonToX(lon), y = latToY(lat)
                        if (detected) {
                            ctx.beginPath(); ctx.arc(x, y, 14, 0, Math.PI*2)
                            ctx.strokeStyle = "rgba(255,213,79,0.8)"; ctx.lineWidth = 2.5; ctx.stroke()
                        }
                    }

                    // ── Acoustic bearing line (detection cue) ──────────
                    function drawAcousticBearing(ctx, lat, lon, bearingDeg) {
                        // Draw a dashed yellow ray 4 km along the bearing
                        var end = _geoMove(lat, lon, bearingDeg, 4000)
                        var x0 = lonToX(lon), y0 = latToY(lat)
                        var x1 = lonToX(end.lon), y1 = latToY(end.lat)
                        ctx.save()
                        ctx.setLineDash([6, 5])
                        ctx.strokeStyle = "rgba(255, 213, 79, 0.75)"
                        ctx.lineWidth = 1.5
                        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke()
                        // Arrow tip
                        ctx.setLineDash([])
                        var ang = Math.atan2(y1 - y0, x1 - x0)
                        ctx.fillStyle = "rgba(255, 213, 79, 0.75)"
                        ctx.beginPath()
                        ctx.moveTo(x1, y1)
                        ctx.lineTo(x1 - 9*Math.cos(ang-0.4), y1 - 9*Math.sin(ang-0.4))
                        ctx.lineTo(x1 - 9*Math.cos(ang+0.4), y1 - 9*Math.sin(ang+0.4))
                        ctx.closePath(); ctx.fill()
                        ctx.restore()
                    }

                    function drawSeismic(ctx, lat, lon, label, detected) {
                        var x = lonToX(lon), y = latToY(lat)
                        if (detected) {
                            ctx.beginPath(); ctx.arc(x, y, 14, 0, Math.PI*2)
                            ctx.strokeStyle = "rgba(255,152,0,0.85)"; ctx.lineWidth = 2.5; ctx.stroke()
                        }
                    }

                    // ── Geo move helper (WGS-84) ─────────────────────
                    function _geoMove(lat, lon, headingDeg, distM) {
                        var R   = 6371000
                        var d   = distM / R
                        var h   = headingDeg * Math.PI / 180
                        var p1  = lat * Math.PI / 180
                        var l1  = lon * Math.PI / 180
                        var p2  = Math.asin(Math.sin(p1)*Math.cos(d) + Math.cos(p1)*Math.sin(d)*Math.cos(h))
                        var l2  = l1 + Math.atan2(Math.sin(h)*Math.sin(d)*Math.cos(p1),
                                                   Math.cos(d) - Math.sin(p1)*Math.sin(p2))
                        return { lat: p2 * 180 / Math.PI, lon: l2 * 180 / Math.PI }
                    }

                    // ── Predicted route (replacing single-point diamond) ──
                    function drawPredictedRoute(ctx, lat, lon, headingDeg, speedMs, conf) {
                        var STEP_S  = 30     // sample every 30 s
                        var TOTAL_S = 300    // 5 minutes ahead
                        var CONE_ANG = 12    // ± degrees heading uncertainty

                        // Build centre-line and two cone edges
                        var centre = [], left = [], right = []
                        var la = lat, lo = lon
                        var laL = lat, loL = lon
                        var laR = lat, loR = lon
                        centre.push({lat: la, lon: lo, t: 0})
                        left  .push({lat: la, lon: lo, t: 0})
                        right .push({lat: la, lon: lo, t: 0})

                        for (var t = STEP_S; t <= TOTAL_S; t += STEP_S) {
                            var dist = speedMs * STEP_S
                            var c = _geoMove(la, lo, headingDeg, dist)
                            var l = _geoMove(laL, loL, headingDeg - CONE_ANG, dist * 1.02)
                            var r = _geoMove(laR, loR, headingDeg + CONE_ANG, dist * 1.02)
                            la = c.lat; lo = c.lon
                            laL = l.lat; loL = l.lon
                            laR = r.lat; loR = r.lon
                            centre.push({lat: la, lon: lo, t: t})
                            left  .push({lat: l.lat, lon: l.lon, t: t})
                            right .push({lat: r.lat, lon: r.lon, t: t})
                        }

                        // ── Uncertainty cone fill ────────────────────
                        ctx.beginPath()
                        ctx.moveTo(lonToX(centre[0].lon), latToY(centre[0].lat))
                        for (var i = 1; i < right.length; i++)
                            ctx.lineTo(lonToX(right[i].lon), latToY(right[i].lat))
                        for (var i = left.length - 1; i >= 0; i--)
                            ctx.lineTo(lonToX(left[i].lon), latToY(left[i].lat))
                        ctx.closePath()
                        ctx.fillStyle = "rgba(255, 152, 0, 0.08)"
                        ctx.fill()

                        // ── Cone boundary lines ──────────────────────
                        ctx.setLineDash([3, 5])
                        ctx.strokeStyle = "rgba(255,152,0,0.30)"; ctx.lineWidth = 1
                        ctx.beginPath()
                        ctx.moveTo(lonToX(left[0].lon), latToY(left[0].lat))
                        for (var i = 1; i < left.length; i++)
                            ctx.lineTo(lonToX(left[i].lon), latToY(left[i].lat))
                        ctx.stroke()
                        ctx.beginPath()
                        ctx.moveTo(lonToX(right[0].lon), latToY(right[0].lat))
                        for (var i = 1; i < right.length; i++)
                            ctx.lineTo(lonToX(right[i].lon), latToY(right[i].lat))
                        ctx.stroke()

                        // ── Centre predicted path ────────────────────
                        ctx.setLineDash([6, 4])
                        ctx.strokeStyle = "rgba(255,152,0,0.85)"; ctx.lineWidth = 2
                        ctx.beginPath()
                        ctx.moveTo(lonToX(centre[0].lon), latToY(centre[0].lat))
                        for (var i = 1; i < centre.length; i++)
                            ctx.lineTo(lonToX(centre[i].lon), latToY(centre[i].lat))
                        ctx.stroke()
                        ctx.setLineDash([])

                        // ── Arrow at end of prediction ───────────────
                        var n  = centre.length - 1
                        var ax = lonToX(centre[n].lon),   ay = latToY(centre[n].lat)
                        var bx = lonToX(centre[n-1].lon), by = latToY(centre[n-1].lat)
                        var ang = Math.atan2(ay - by, ax - bx)
                        ctx.fillStyle = "rgba(255,152,0,0.85)"
                        ctx.beginPath()
                        ctx.moveTo(ax, ay)
                        ctx.lineTo(ax - 11*Math.cos(ang-0.38), ay - 11*Math.sin(ang-0.38))
                        ctx.lineTo(ax - 11*Math.cos(ang+0.38), ay - 11*Math.sin(ang+0.38))
                        ctx.closePath(); ctx.fill()

                        // ── Time markers every 60 s ──────────────────
                        for (var i = 1; i < centre.length; i++) {
                            if (centre[i].t % 60 !== 0) continue
                            var mx = lonToX(centre[i].lon), my = latToY(centre[i].lat)
                            ctx.beginPath(); ctx.arc(mx, my, 4, 0, Math.PI*2)
                            ctx.fillStyle = "#FF9800"; ctx.fill()
                        }

                        // ── Current estimated position (diamond) ─────
                        var px = lonToX(lon), py = latToY(lat)
                        var r  = 8
                        ctx.save(); ctx.translate(px, py); ctx.rotate(Math.PI/4)
                        ctx.fillStyle   = "rgba(255,152,0,0.85)"
                        ctx.strokeStyle = "#FFCC00"; ctx.lineWidth = 2
                        ctx.beginPath(); ctx.rect(-r*0.7, -r*0.7, r*1.4, r*1.4)
                        ctx.fill(); ctx.stroke()
                        ctx.restore()
                        ctx.beginPath(); ctx.arc(px, py, 12 + conf*5, 0, Math.PI*2)
                        ctx.strokeStyle = "rgba(255,152,0,0.35)"; ctx.lineWidth = 1.5; ctx.stroke()
                    }

                    function drawPVO(ctx, lat, lon, label, armed, gun) {
                        var x = lonToX(lon), y = latToY(lat)
                    }

                    function drawGG(ctx, lat, lon, label, armed) {
                        var x = lonToX(lon), y = latToY(lat)
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
                    }

                    function drawIntercept(ctx, lat, lon) {
                        var x = lonToX(lon), y = latToY(lat)
                        ctx.strokeStyle = "#FF9800"; ctx.lineWidth = 1.5
                        ctx.beginPath(); ctx.arc(x, y, 10, 0, Math.PI*2); ctx.stroke()
                        ctx.beginPath(); ctx.moveTo(x-14,y); ctx.lineTo(x+14,y); ctx.stroke()
                        ctx.beginPath(); ctx.moveTo(x,y-14); ctx.lineTo(x,y+14); ctx.stroke()
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

                    // ── C-UAS overlays ────────────────────────────────
                    function metresToPx(lat, m) {
                        var lon2 = mapCenterLon + m / (111320 * Math.cos(lat * Math.PI / 180))
                        return lonToX(lon2) - lonToX(mapCenterLon)
                    }

                    function drawZone(ctx) {
                        var z = root.zoneData
                        if (!z) return
                        var a = z.asset
                        var ax = lonToX(a.lon), ay = latToY(a.lat)
                        // Warning buffer (approximate ring)
                        var rBuf = metresToPx(a.lat, 2200 + z.bufferM)
                        ctx.setLineDash([6, 5])
                        ctx.strokeStyle = "rgba(255,183,77,0.8)"; ctx.lineWidth = 1.2
                        ctx.beginPath(); ctx.arc(ax, ay, rBuf, 0, Math.PI*2); ctx.stroke()
                        ctx.setLineDash([])
                        // Restricted zone polygon
                        var v = z.vertices
                        ctx.beginPath()
                        ctx.moveTo(lonToX(v[0].lon), latToY(v[0].lat))
                        for (var i = 1; i < v.length; i++) ctx.lineTo(lonToX(v[i].lon), latToY(v[i].lat))
                        ctx.closePath()
                        var breach = false
                        for (var t = 0; t < root.trackData.length; t++)
                            if (root.trackData[t].insideZone && root.trackData[t].identity === "HOSTILE"
                                    && root.trackData[t].engState !== "NEUTRALIZED") breach = true
                        ctx.fillStyle = breach ? (root.pulsePhase ? "rgba(244,67,54,0.22)" : "rgba(244,67,54,0.12)")
                                               : "rgba(239,83,80,0.10)"
                        ctx.fill()
                        ctx.strokeStyle = "#EF5350"; ctx.lineWidth = 2; ctx.stroke()
                        lbl(ctx, z.zoneId + (breach ? "  ■ BREACH" : "  RESTRICTED"),
                            lonToX(v[0].lon) + 6, latToY(v[0].lat) - 6, breach ? "#FF5252" : "#EF9A9A")
                        // Protected asset
                        ctx.fillStyle = "#FFD54F"; ctx.strokeStyle = "#000000"; ctx.lineWidth = 1
                        ctx.beginPath()
                        ctx.moveTo(ax, ay-8); ctx.lineTo(ax+7, ay); ctx.lineTo(ax, ay+8); ctx.lineTo(ax-7, ay)
                        ctx.closePath(); ctx.fill(); ctx.stroke()
                    }

                    // Serbia border / administrative line (Natural Earth 1:10m)
                    function drawBorder(ctx) {
                        var b = root.borderData
                        if (!b || !b.lines) return
                        for (var i = 0; i < b.lines.length; i++) {
                            var ln = b.lines[i]
                            ctx.beginPath()
                            for (var k = 0; k < ln.length; k++) {
                                var x = lonToX(ln[k].lon), y = latToY(ln[k].lat)
                                if (k === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
                            }
                            ctx.setLineDash([]); ctx.lineWidth = 4; ctx.strokeStyle = "rgba(0,0,0,0.55)"; ctx.stroke()
                            ctx.setLineDash([10, 6]); ctx.lineWidth = 2; ctx.strokeStyle = "rgba(255,82,82,0.95)"; ctx.stroke()
                        }
                        ctx.setLineDash([])
                    }

                    // Readiness: alert ring, threat axes and the manned interception lines
                    function drawReadiness(ctx) {
                        var r = root.readinessData, ld = root.laydownData
                        if (!r || !r.border || !ld || r.phase === "CALM") return
                        var bx = lonToX(ld.base.lon), by = latToY(ld.base.lat)
                        ctx.setLineDash([3, 7]); ctx.lineWidth = 1
                        ctx.strokeStyle = r.war ? "rgba(255,82,82,0.45)" : "rgba(255,152,0,0.5)"
                        ctx.beginPath(); ctx.arc(bx, by, metresToPx(ld.base.lat, r.alertRangeM), 0, Math.PI*2); ctx.stroke()
                        for (var i = 0; i < r.axes.length; i++) {
                            var e = _geoMove(ld.base.lat, ld.base.lon, r.axes[i], r.alertRangeM)
                            ctx.setLineDash([12, 6]); ctx.lineWidth = 2; ctx.strokeStyle = "rgba(255,152,0,0.75)"
                            ctx.beginPath(); ctx.moveTo(bx, by); ctx.lineTo(lonToX(e.lon), latToY(e.lat)); ctx.stroke()
                        }
                        ctx.setLineDash([])
                        // UAV patrol orbits and UGV blocking positions
                        for (var u = 0; u < r.uavStations.length; u++) {
                            var su = r.uavStations[u]
                            ctx.strokeStyle = "rgba(41,182,246,0.85)"; ctx.lineWidth = 1.5; ctx.setLineDash([4, 4])
                            ctx.beginPath(); ctx.arc(lonToX(su.lon), latToY(su.lat), Math.max(6, metresToPx(su.lat, 300)), 0, Math.PI*2); ctx.stroke()
                        }
                        for (var g = 0; g < r.ugvStations.length; g++) {
                            var sg = r.ugvStations[g], gx = lonToX(sg.lon), gy = latToY(sg.lat)
                            ctx.setLineDash([]); ctx.strokeStyle = "rgba(41,182,246,0.9)"; ctx.lineWidth = 2
                            ctx.strokeRect(gx - 9, gy - 9, 18, 18)
                        }
                    }

                    function drawGroundArea(ctx, bb) {
                        if (!bb) return
                        var x0 = lonToX(bb.lonMin), y0 = latToY(bb.latMax)
                        var x1 = lonToX(bb.lonMax), y1 = latToY(bb.latMin)
                        ctx.setLineDash([3, 4])
                        ctx.strokeStyle = "rgba(165,214,167,0.55)"; ctx.lineWidth = 1
                        ctx.strokeRect(x0, y0, x1 - x0, y1 - y0)
                        ctx.setLineDash([])
                        lbl(ctx, "artemides-trax terrain (UGV routable)", x0 + 6, y1 - 6, "#A5D6A7")
                    }

                    // Sensor coverage: radar 30 km / acoustic 10 km rings (full detail in edit mode)
                    function drawCoverage(ctx) {
                        var ld = root.laydownData
                        if (!ld) return
                        for (var i = 0; i < ld.radars.length; i++) {
                            var r = ld.radars[i]
                            var x = lonToX(r.lon), y = latToY(r.lat)
                            ctx.setLineDash([2, 6])
                            ctx.strokeStyle = "rgba(128,203,196," + (root.editMode ? "0.8" : "0.4") + ")"; ctx.lineWidth = 1
                            ctx.beginPath(); ctx.arc(x, y, metresToPx(r.lat, r.rangeM), 0, Math.PI*2); ctx.stroke()
                            ctx.setLineDash([])
                        }
                        if (!root.editMode) return
                        // Edit mode: acoustic 10 km (air) + 2.5 km (ground), seismic ~8 km (ground)
                        for (var k = 0; k < ld.acoustic.length; k++) {
                            var a = ld.acoustic[k]
                            var ax = lonToX(a.lon), ay = latToY(a.lat)
                            ctx.setLineDash([3, 6])
                            ctx.strokeStyle = "rgba(255,249,196,0.30)"; ctx.lineWidth = 1
                            ctx.beginPath(); ctx.arc(ax, ay, metresToPx(a.lat, a.rangeM), 0, Math.PI*2); ctx.stroke()
                            ctx.setLineDash([1, 3])
                            ctx.strokeStyle = "rgba(255,249,196,0.55)"
                            ctx.beginPath(); ctx.arc(ax, ay, metresToPx(a.lat, a.groundRangeM), 0, Math.PI*2); ctx.stroke()
                        }
                        for (var q = 0; q < ld.seismic.length; q++) {
                            var sq = ld.seismic[q]
                            ctx.setLineDash([6, 6])
                            ctx.strokeStyle = "rgba(255,152,0,0.35)"; ctx.lineWidth = 1
                            ctx.beginPath(); ctx.arc(lonToX(sq.lon), latToY(sq.lat), metresToPx(sq.lat, sq.rangeM), 0, Math.PI*2); ctx.stroke()
                        }
                        ctx.setLineDash([])
                    }

                    // Translucent detection sectors (15° per bearing, merged per sensor),
                    // fading with range.  One sensor alone is barely visible; the target
                    // stands out only where the sectors of several sensors overlap.
                    function drawDetections(ctx) {
                        var dets = root.detectionsData
                        for (var i = 0; i < dets.length; i++) {
                            var d = dets[i]
                            var x = lonToX(d.lon), y = latToY(d.lat)
                            var r = metresToPx(d.lat, d.rangeM)
                            var a0 = (d.fromDeg - 90) * Math.PI / 180      // compass → canvas angle
                            var a1 = (d.toDeg - 90) * Math.PI / 180
                            var g = ctx.createRadialGradient(x, y, 0, x, y, r)
                            if (d.kind === "SEISMIC") {
                                g.addColorStop(0.0, "rgba(255,152,0,0.10)")
                                g.addColorStop(1.0, "rgba(255,152,0,0.015)")
                            } else {
                                g.addColorStop(0.0, "rgba(255,241,118,0.08)")
                                g.addColorStop(1.0, "rgba(255,241,118,0.01)")
                            }
                            ctx.fillStyle = g
                            ctx.beginPath(); ctx.moveTo(x, y); ctx.arc(x, y, r, a0, a1); ctx.closePath()
                            ctx.fill()
                        }
                    }

                    function drawDrivability(ctx) {
                        var d = root.drivData
                        var url = root.drivSmoothUrl
                        if (!d || !d.ready || !url) return
                        if (!isImageLoaded(url)) { loadImage(url); return }
                        var x0 = lonToX(d.bbox.lonMin), y0 = latToY(d.bbox.latMax)
                        var x1 = lonToX(d.bbox.lonMax), y1 = latToY(d.bbox.latMin)
                        ctx.globalAlpha = root.driveOpacity
                        ctx.drawImage(url, x0, y0, x1 - x0, y1 - y0)
                        ctx.globalAlpha = 1.0
                    }

                    function drawDriveLegend(ctx) {
                        var d = root.drivData
                        if (!d || !d.ready) return
                        var lx = 12, ly = 14, sp = 15, h = (d.legend.length + 2) * sp + 6
                        ctx.fillStyle = "rgba(13,27,42,0.85)"; ctx.fillRect(lx - 6, ly - 10, 150, h)
                        ctx.font = "bold 9px sans-serif"; ctx.fillStyle = "#7899AA"
                        ctx.fillText("UGV DRIVABILITY", lx, ly + 2)
                        for (var i = 0; i < d.legend.length; i++) {
                            var it = d.legend[i]
                            ctx.fillStyle = it.color; ctx.fillRect(lx, ly + (i+1)*sp - 6, 12, 9)
                            ctx.fillStyle = "#C8D8E4"
                            ctx.fillText(it.label + (it.kmh > 0 ? "  " + it.kmh + " km/h" : "  impassable"), lx + 18, ly + (i+1)*sp + 2)
                        }
                        ctx.fillStyle = "#90A4AE"
                        ctx.fillText("no data  " + d.unknownKmh + " km/h", lx + 18, ly + (d.legend.length+1)*sp + 2)
                    }

                    function drawTrack(ctx, t) {
                        var x = lonToX(t.lon), y = latToY(t.lat)
                        var col = root.trackColor(t)
                        // 1σ uncertainty ellipse (circular approx.)
                        var rs = Math.max(3, metresToPx(t.lat, t.sigmaM))
                        ctx.strokeStyle = col; ctx.globalAlpha = 0.35; ctx.lineWidth = 1
                        ctx.beginPath(); ctx.arc(x, y, rs, 0, Math.PI*2); ctx.stroke()
                        ctx.globalAlpha = 1.0
                        // 60 s velocity leader
                        var p = _geoMove(t.lat, t.lon, t.headingDeg, t.speedMs * 60)
                        ctx.strokeStyle = col; ctx.lineWidth = 1.5
                        ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(lonToX(p.lon), latToY(p.lat)); ctx.stroke()
                        // NATO track symbol (APP-6): frame = identity, icon = platform;
                        // neutralised tracks fade out
                        var dead = t.engState === "NEUTRALIZED"
                        if (t.engState === "ENGAGING") {
                            ctx.strokeStyle = root.pulsePhase ? "#FF1744" : "#FF8A80"; ctx.lineWidth = 2
                            ctx.beginPath(); ctx.arc(x, y, 20, 0, Math.PI*2); ctx.stroke()
                        }
                    }

                    function drawTruth(ctx, g) {
                        var x = lonToX(g.lon), y = latToY(g.lat)
                        var dead = g.state === "DESTROYED" || g.state === "LANDED" || g.state === "DISABLED"
                        if (dead) {
                            ctx.strokeStyle = "rgba(200,200,200,0.7)"; ctx.lineWidth = 1.5
                            ctx.beginPath(); ctx.moveTo(x-6,y-6); ctx.lineTo(x+6,y+6); ctx.stroke()
                            ctx.beginPath(); ctx.moveTo(x+6,y-6); ctx.lineTo(x-6,y+6); ctx.stroke()
                        }
                    }

                    // Enemy convoy's planned road route — ground truth, never shown to the C2 picture
                    function drawEnemyRoute(ctx) {
                        var r = root.enemyRoute
                        if (!r || r.route.length < 2) return
                        ctx.setLineDash([2, 4]); ctx.strokeStyle = "rgba(255,82,82,0.7)"; ctx.lineWidth = 1.5
                        ctx.beginPath(); ctx.moveTo(lonToX(r.route[0].lon), latToY(r.route[0].lat))
                        for (var i = 1; i < r.route.length; i++) ctx.lineTo(lonToX(r.route[i].lon), latToY(r.route[i].lat))
                        ctx.stroke(); ctx.setLineDash([])
                        var e = r.route[r.route.length - 1]
                        lbl(ctx, "ENEMY ROUTE (truth) — " + r.source, lonToX(e.lon) + 6, latToY(e.lat) + 20, "#FF8A80")
                    }

                    function drawPvoSite(ctx, p) {
                        var x = lonToX(p.lon), y = latToY(p.lat)
                        var live = root.pvoData.enabled && p.ammo > 0
                        ctx.setLineDash([4, 6])
                        ctx.strokeStyle = live ? "rgba(239,154,154,0.45)" : "rgba(120,144,156,0.3)"; ctx.lineWidth = 1
                        ctx.beginPath(); ctx.arc(x, y, metresToPx(p.lat, p.rangeM), 0, Math.PI*2); ctx.stroke()
                        ctx.setLineDash([])
                        drawPVO(ctx, p.lat, p.lon, p.id + "  " + p.system + "  " + p.ammo + "+" + p.reserve +
                                (p.readyIn > 0 ? "  ⟳" + p.readyIn.toFixed(0) + "s" : ""), live, p.gunRangeM > 0)
                        if (p.lastShot) drawShot(ctx, p.lat, p.lon, p.lastShot, "#FF9800")
                    }

                    function drawGgSite(ctx, g) {
                        var x = lonToX(g.lon), y = latToY(g.lat)
                        var live = root.pvoData.ggEnabled && g.ammo > 0
                        ctx.setLineDash([2, 8])
                        ctx.strokeStyle = live ? "rgba(206,147,216,0.45)" : "rgba(120,144,156,0.25)"; ctx.lineWidth = 1
                        ctx.beginPath(); ctx.arc(x, y, metresToPx(g.lat, g.rangeM), 0, Math.PI*2); ctx.stroke()
                        ctx.setLineDash([])
                        drawGG(ctx, g.lat, g.lon, g.id + "  " + g.system + "  " + g.ammo, live)
                        if (g.lastShot) drawShot(ctx, g.lat, g.lon, g.lastShot, "#CE93D8")
                    }

                    // Munitions in flight: dashed line launcher → aim point, time to impact
                    function drawMunitions(ctx) {
                        var ms = root.pvoData ? root.pvoData.munitions : []
                        for (var i = 0; i < ms.length; i++) {
                            var m = ms[i]
                            var x0 = lonToX(m.slon), y0 = latToY(m.slat), x1 = lonToX(m.lon), y1 = latToY(m.lat)
                            ctx.setLineDash([6, 4])
                            ctx.strokeStyle = m.weapon === "GUN" ? "#FFE082" : "#FF7043"; ctx.lineWidth = 1.5
                            ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke()
                            ctx.setLineDash([])
                        }
                    }

                    // Flash a firing line for a few seconds after a shot
                    function drawShot(ctx, lat, lon, shot, color) {
                        var age = root.simTime - shot.t
                        if (age < 0 || age > 4) return
                        var x0 = lonToX(lon), y0 = latToY(lat), x1 = lonToX(shot.lon), y1 = latToY(shot.lat)
                        ctx.globalAlpha = 1.0 - age / 4
                        ctx.strokeStyle = color; ctx.lineWidth = 2
                        ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke()
                        ctx.fillStyle = shot.hit ? "#FF5252" : "#B0BEC5"
                        ctx.beginPath(); ctx.arc(x1, y1, shot.hit ? 9 : 5, 0, Math.PI*2); ctx.fill()
                        ctx.globalAlpha = 1.0
                    }

                    function drawJamBeam(ctx, lat, lon, aimLat, aimLon) {
                        var x = lonToX(lon), y = latToY(lat)
                        var r = metresToPx(lat, 2000)
                        var ang = Math.atan2(latToY(aimLat) - y, lonToX(aimLon) - x)
                        var half = 30 * Math.PI / 180
                        ctx.fillStyle = root.pulsePhase ? "rgba(206,147,216,0.30)" : "rgba(206,147,216,0.18)"
                        ctx.beginPath(); ctx.moveTo(x, y); ctx.arc(x, y, r, ang - half, ang + half); ctx.closePath()
                        ctx.fill()
                        ctx.strokeStyle = "#CE93D8"; ctx.lineWidth = 1; ctx.stroke()
                    }

                    function drawRoute(ctx, lat, lon, route) {
                        if (!route || route.length === 0) return
                        ctx.setLineDash([4, 3])
                        ctx.strokeStyle = "#A5D6A7"; ctx.lineWidth = 2
                        ctx.beginPath(); ctx.moveTo(lonToX(lon), latToY(lat))
                        for (var i = 0; i < route.length; i++) ctx.lineTo(lonToX(route[i].lon), latToY(route[i].lat))
                        ctx.stroke(); ctx.setLineDash([])
                        var last = route[route.length - 1]
                        ctx.fillStyle = "#A5D6A7"
                        ctx.beginPath(); ctx.arc(lonToX(last.lon), latToY(last.lat), 3, 0, Math.PI*2); ctx.fill()
                    }

                    function drawScaleBar(ctx) {
                        // Derive bar width from projection (5 km east of centre)
                        var lon2 = mapCenterLon + 5.0 / (111.32 * Math.cos(mapCenterLat * Math.PI / 180))
                        var barW = lonToX(lon2) - lonToX(mapCenterLon)
                        var bx = 50, by = height - 24
                        ctx.fillStyle = "#FFFFFF"; ctx.fillRect(bx,        by, barW, 4)
                        ctx.fillStyle = "#555555"; ctx.fillRect(bx + barW, by, barW, 4)
                        ctx.font = "8px monospace"; ctx.fillStyle = "#E0E0E0"
                        ctx.fillText("0",     bx - 4,       by + 14)
                        ctx.fillText("5 km",  bx + barW - 8, by + 14)
                        ctx.fillText("10 km", bx + barW*2-10, by + 14)
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
                        if (root.showDrive || (root.editMode && root.editTool === "ugv"))
                            drawDrivability(ctx)
                        drawCoverage(ctx)
                        drawBorder(ctx)
                        drawZone(ctx)
                        drawReadiness(ctx)

                        var ld = root.laydownData
                        if (ld) {
                            drawGroundArea(ctx, ld.groundBbox)

                            // Bearing detections: faint 15° wedges — only where several
                            // sensors agree does the overlap stand out
                            drawDetections(ctx)

                            // Acoustic — highlight when detecting
                            var aco = root.acousticData
                            for (var ai = 0; ai < ld.acoustic.length; ai++) {
                                var as = ld.acoustic[ai]
                                drawAcoustic(ctx, as.lat, as.lon, as.label, aco.length > ai && aco[ai].detected)
                            }

                            // Seismic — highlight when actively detecting
                            var sei = root.seismicData
                            for (var si = 0; si < ld.seismic.length; si++)
                                drawSeismic(ctx, ld.seismic[si].lat, ld.seismic[si].lon, ld.seismic[si].label,
                                            sei.length > si && sei[si].detected)

                            // PVO / GG systems (fixed)
                            if (root.pvoData)
                                for (var pi = 0; pi < root.pvoData.sites.length; pi++)
                                    drawPvoSite(ctx, root.pvoData.sites[pi])
                            if (root.pvoData) {
                                for (var gi2 = 0; gi2 < root.pvoData.gg.length; gi2++)
                                    drawGgSite(ctx, root.pvoData.gg[gi2])
                                drawMunitions(ctx)
                            }
                        }

                        // UGV route (artemides-trax A* or straight-line fallback)
                        for (var ri = 0; ri < root.ugvsData.length; ri++) {
                            var gv = root.ugvsData[ri]
                            if (gv.route.length > 0) drawRoute(ctx, gv.lat, gv.lon, gv.route)
                        }

                        // Vehicles — live positions from simBus
                        for (var gj = 0; gj < root.ugvsData.length; gj++) {
                            var g = root.ugvsData[gj]
                            if (g.jamming && g.jamAim) drawJamBeam(ctx, g.lat, g.lon, g.jamAim.lat, g.jamAim.lon)
                            if (g.lastShot) drawShot(ctx, g.lat, g.lon, g.lastShot, "#FFEB3B")
                        }
                        // UGV / interceptor symbols themselves are Image items (symLayer)

                        // Ground truth (debug overlay — not visible to the C2 chain)
                        if (root.showTruth) {
                            drawEnemyRoute(ctx)
                            for (var gi = 0; gi < root.targetsData.length; gi++)
                                drawTruth(ctx, root.targetsData[gi])
                        }

                        // Engagement geometry: interceptor → predicted intercept point
                        for (var ei = 0; ei < root.engagementsData.length; ei++) {
                            var e = root.engagementsData[ei]
                            var iu = root.uavById(e.effector)
                            if (e.state === "ENGAGING" && e.kind === "INTERCEPTOR" && iu && iu.airborne
                                    && e.aimLat !== null && e.aimLat !== undefined) {
                                drawTrajectory(ctx, iu.lat, iu.lon, e.aimLat, e.aimLon)
                                drawIntercept(ctx, e.aimLat, e.aimLon)
                            }
                        }

                        // Fused tracks — Kalman estimates with 60 s velocity leader
                        for (var ti = 0; ti < root.trackData.length; ti++)
                            drawTrack(ctx, root.trackData[ti])
                        if (root.trackData.length > 0 && root.trackData[0].identity === "HOSTILE"
                                && root.trackData[0].engState !== "NEUTRALIZED") {
                            var trk = root.trackData[0]
                            drawPredictedRoute(ctx, trk.lat, trk.lon, trk.headingDeg, trk.speedMs, trk.confidence)
                        }

                        // MOVE: highlight the picked item
                        if (root.editMode && root.editTool === "move" && root.editMsg && root.editMsg.picked) {
                            var pk = root.editMsg.picked
                            var px = lonToX(pk.lon), py = latToY(pk.lat)
                            ctx.strokeStyle = root.pulsePhase ? "#FFEB3B" : "#FFA000"; ctx.lineWidth = 3
                            ctx.beginPath(); ctx.arc(px, py, 16 + root.pulsePhase * 4, 0, Math.PI*2); ctx.stroke()
                            lbl(ctx, "MOVE " + pk.label + " → click new position", px + 20, py - 14, "#FFEB3B")
                        }

                        if (root.showDrive || (root.editMode && root.editTool === "ugv")) drawDriveLegend(ctx)
                        drawScaleBar(ctx)
                        drawNorth(ctx)
                    }
                }
            }

            // ── RIGHT PANEL: alarms / tracks / actions ────────────
            Rectangle {
                width: 330
                Layout.fillHeight: true
                color: root.c_panel
                border.color: "#1E3550"; border.width: 1

                ScrollView {
                    anchors.fill: parent
                    clip: true
                    contentWidth: availableWidth

                    ColumnLayout {
                        width: 330
                        spacing: 0

                        SectionHeader { title: "THREAT PICTURE" }

                        Rectangle {
                            width: 310; height: 62
                            Layout.alignment: Qt.AlignHCenter
                            color: root.threatLevel >= 3 ? "#2C1515" : root.c_card
                            border.color: root.threatLevel >= 3 ? root.c_pvo : "#37474F"
                            border.width: root.threatLevel >= 3 ? 2 : 1; radius: 4
                            GridLayout {
                                anchors { fill: parent; margins: 8 }
                                columns: 5; rowSpacing: 2; columnSpacing: 4
                                Repeater {
                                    model: [
                                        { k: "HOSTILE", v: root.countIdentity("HOSTILE"), c: "#F44336" },
                                        { k: "SUSPECT", v: root.countIdentity("SUSPECT"), c: "#FF9800" },
                                        { k: "NEUTRAL", v: root.countIdentity("NEUTRAL"), c: "#4FC3F7" },
                                        { k: "KILLS",   v: root.statsData.kills,          c: "#66BB6A" },
                                        { k: "OWN LOST", v: root.statsData.ownLosses || 0,
                                          c: (root.statsData.ownLosses || 0) > 0 ? "#FFB74D" : "#78909C" },
                                        { k: "BASE HITS", v: root.statsData.baseHits + (root.statsData.assaults ? "+" + root.statsData.assaults : ""),
                                          c: root.statsData.baseHits + root.statsData.assaults > 0 ? "#FF5252" : "#78909C" },
                                    ]
                                    Column {
                                        Layout.fillWidth: true
                                        Text { text: modelData.v; color: modelData.c
                                               font { pixelSize: 18; bold: true }
                                               anchors.horizontalCenter: parent.horizontalCenter }
                                        Text { text: modelData.k; color: root.c_dim; font.pixelSize: 8
                                               anchors.horizontalCenter: parent.horizontalCenter }
                                    }
                                }
                            }
                        }

                        Item { height: 4 }

                        SectionHeader { title: "TRACKS  (" + root.trackData.length + ")" }

                        Text {
                            visible: root.trackData.length === 0
                            Layout.leftMargin: 12
                            text: "No confirmed tracks"
                            color: root.c_dim; font.pixelSize: 10
                        }

                        Repeater {
                            model: root.trackData
                            Rectangle {
                                width: 310; height: 70
                                Layout.alignment: Qt.AlignHCenter
                                color: root.c_card; radius: 4
                                border.color: root.trackColor(modelData)
                                border.width: modelData.identity === "HOSTILE" && modelData.engState !== "NEUTRALIZED" ? 2 : 1
                                ColumnLayout {
                                    anchors { fill: parent; margins: 6 }
                                    spacing: 1
                                    RowLayout {
                                        Image { source: symbolsInfo.base + mapCanvas.trackSymbol(modelData) + ".svg"
                                                sourceSize.height: 18; smooth: true
                                                opacity: modelData.engState === "NEUTRALIZED" ? 0.4 : 1.0 }
                                        Text { text: modelData.trackId; color: root.trackColor(modelData)
                                               font { bold: true; pixelSize: 11 } }
                                        Text { text: modelData.identity + " / " + modelData.threatLevel
                                               color: root.trackColor(modelData); font.pixelSize: 9 }
                                        Item { Layout.fillWidth: true }
                                        Text { text: modelData.status; color: root.c_dim; font.pixelSize: 8 }
                                    }
                                    InfoRow { k: "Kinematics"
                                              v: (modelData.speedMs*3.6).toFixed(0) + " km/h  " +
                                                 modelData.headingDeg.toFixed(0) + "°  " +
                                                 modelData.altitudeM.toFixed(0) + " m  ±" + modelData.sigmaM.toFixed(0) + " m" }
                                    InfoRow { k: "Assessment"; v: modelData.reason
                                              vc: modelData.insideZone ? root.c_armed : root.c_text }
                                    InfoRow { k: "Sensors"
                                              v: modelData.sources.length + " · " + modelData.sources.join(", ") +
                                                 (modelData.objClass !== "UNKNOWN" ? "  [" + modelData.objClass + "]" : "")
                                              vc: root.c_dim }
                                }
                            }
                        }

                        Item { height: 4 }

                        SectionHeader { title: "ENGAGEMENTS  —  " + (root.autoRoe ? "AUTO-ROE (zone)" : "OPERATOR APPROVAL") }

                        Text {
                            visible: root.engagementsData.length === 0
                            Layout.leftMargin: 12
                            text: "No engagements"
                            color: root.c_dim; font.pixelSize: 10
                        }

                        Repeater {
                            model: root.engagementsData.slice(0, 6)
                            Rectangle {
                                width: 310; height: modelData.active ? 84 : 58
                                Layout.alignment: Qt.AlignHCenter
                                color: modelData.state === "PROPOSED" ? "#2A2410" : "#1A1A2E"
                                border.color: root.engStateColor(modelData.state)
                                border.width: modelData.active ? 2 : 1; radius: 4
                                ColumnLayout {
                                    anchors { fill: parent; margins: 6 }
                                    spacing: 1
                                    RowLayout {
                                        Text { text: modelData.engId + " → " + modelData.trackId; color: root.c_warn
                                               font { bold: true; pixelSize: 11 } }
                                        Item { Layout.fillWidth: true }
                                        Text { text: modelData.state; color: root.engStateColor(modelData.state)
                                               font { bold: true; pixelSize: 10 } }
                                    }
                                    InfoRow { k: modelData.state === "PROPOSED" ? "Recommend" : "Effector"
                                              v: (modelData.effector || "none available") +
                                                 (modelData.kind ? "  (" + modelData.kind + ")" : "") +
                                                 (typeof modelData.tGo === "number" && modelData.active ? "  t-go " + modelData.tGo.toFixed(0) + " s" : "")
                                              vc: modelData.effector ? root.c_text : root.c_armed }
                                    InfoRow { visible: !modelData.active || modelData.approvedBy !== ""
                                              k: modelData.active ? "Approved" : "Result"
                                              v: modelData.active ? modelData.approvedBy : modelData.result + "  @T+" + modelData.endedT
                                              vc: root.c_dim }
                                    Row {
                                        visible: modelData.active
                                        spacing: 6
                                        ActionButton {
                                            visible: modelData.state === "PROPOSED"
                                            label: "✔ ENGAGE"; base: "#2E7D32"; edge: "#4CAF50"
                                            enabled: modelData.effector !== ""
                                            onClicked: simBus.approveEngagement(modelData.engId)
                                        }
                                        ActionButton {
                                            visible: modelData.state === "PROPOSED"
                                            label: "✘ DENY"; base: "#C62828"; edge: "#EF5350"
                                            onClicked: simBus.denyEngagement(modelData.engId)
                                        }
                                        ActionButton {
                                            visible: modelData.state === "APPROVED" || modelData.state === "ENGAGING"
                                            label: "⏹ ABORT"; base: "#6A1B9A"; edge: "#CE93D8"
                                            onClicked: simBus.abortEngagement(modelData.engId)
                                        }
                                    }
                                }
                            }
                        }

                        Item { height: 4 }

                        SectionHeader { title: "EVENT LOG" }

                        Rectangle {
                            width: 310; height: 150
                            Layout.alignment: Qt.AlignHCenter
                            color: "#0A1622"; border.color: "#1E3550"; radius: 4
                            clip: true
                            Column {
                                anchors { fill: parent; margins: 6 }
                                spacing: 2
                                Repeater {
                                    model: root.eventsData.slice(0, 11)
                                    Text {
                                        width: 298
                                        elide: Text.ElideRight
                                        text: "T+" + modelData.t.toFixed(0) + "  " + modelData.text
                                        color: modelData.level === "KILL" ? "#66BB6A" :
                                               modelData.level === "ALERT" ? "#FF8A80" :
                                               modelData.level === "WARN" ? root.c_warn : root.c_dim
                                        font { pixelSize: 9; family: "monospace" }
                                    }
                                }
                            }
                        }

                        Item { height: 4 }

                        SectionHeader { title: "ARTEMIDES-TRAX LINK" }

                        Rectangle {
                            width: 310; height: 78
                            Layout.alignment: Qt.AlignHCenter
                            color: root.c_card; radius: 4
                            border.color: !root.linkData || !root.linkData.enabled ? "#37474F"
                                          : root.linkData.errors > 0 && root.linkData.ok === 0 ? root.c_armed : root.c_active
                            ColumnLayout {
                                anchors { fill: parent; margins: 6 }
                                spacing: 1
                                InfoRow { k: "Status"
                                          v: !root.linkData || !root.linkData.enabled ? "OFFLINE (ARTEMIDES_URL not set)"
                                             : (root.linkData.user ? "CONNECTED as " + root.linkData.user
                                                : root.linkData.ok > 0 ? "CONNECTED (guest)" : "CONNECTING…")
                                          vc: root.linkData && root.linkData.enabled ? root.c_active : root.c_dim }
                                InfoRow { k: "Drivability"; v: root.drivData ? root.drivData.status : "--" }
                                InfoRow { k: "Publish"
                                          v: root.linkData ? ("telemetry " + (root.linkData.telemetry ? "ON" : "off") +
                                                              " · threats " + (root.linkData.publishThreats ? "ON" : "off")) : "--"
                                          vc: root.c_dim }
                                InfoRow { k: "Calls"
                                          v: root.linkData ? (root.linkData.ok + " ok · " + root.linkData.errors + " err" +
                                                              (root.linkData.last_error ? " · " + root.linkData.last_error : "")) : "--"
                                          vc: root.linkData && root.linkData.errors > 0 ? root.c_warn : root.c_dim }
                            }
                        }

                        Item { height: 4 }

                        SectionHeader { title: "SENSOR CONFIDENCE" }

                        ConfBar { label: "Acoustic"
                                   value: root.acousticData.length > 0 ?
                                       Math.max(root.acousticData[0].confidence,
                                                root.acousticData.length>1 ? root.acousticData[1].confidence : 0,
                                                root.acousticData.length>2 ? root.acousticData[2].confidence : 0) : 0.0
                                   barColor: root.c_sensor }
                        ConfBar { label: "Seismic"
                                   value: root.seismicData.length > 0 ?
                                       Math.max(root.seismicData[0].confidence,
                                                root.seismicData.length>1 ? root.seismicData[1].confidence : 0,
                                                root.seismicData.length>2 ? root.seismicData[2].confidence : 0) : 0.0
                                   barColor: root.c_warn }
                        ConfBar { label: "Fused  output"
                                   value: root.trackData.length > 0 ? root.trackData[0].confidence : 0.0
                                   barColor: root.c_uav }

                        Item { height: 10 }
                    }
                }
            }
        }

        // ── BOTTOM ACTION BAR ─────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            height: 72
            color: "#0A1622"
            border.color: root.c_border; border.width: 1

            RowLayout {
                anchors { fill: parent; leftMargin: 16; rightMargin: 16 }
                spacing: 12

                Text {
                    text: "● C-UAS ACTIVE  |  TRACKS " + root.trackData.length +
                          "  |  HOSTILE " + root.countIdentity("HOSTILE") +
                          "  |  ENGAGING " + root.countEng("ENGAGING") +
                          "  |  NEUTRALIZED " + root.countEng("NEUTRALIZED") +
                          "  |  UAV airborne " + root.countAirborne() + "/" + root.uavsData.length
                    color: root.threatLevel >= 3 ? "#FF8A80" : root.c_active
                    font { pixelSize: 11; bold: true }
                    Layout.fillWidth: true
                    elide: Text.ElideRight
                }

                // Engage most urgent proposed engagement
                Column {
                    spacing: 4
                    Rectangle {
                        width: 170; height: 32; radius: 4
                        color: hov.containsMouse && root.missionReady ? "#1B5E20" : "#2E7D32"
                        opacity: root.missionReady ? 1.0 : 0.4
                        border.color: "#4CAF50"; border.width: 1
                        Text { anchors.centerIn: parent
                               text: root.pendingEng ? "✔  ENGAGE " + root.pendingEng.trackId : "✔  ENGAGE"
                               color: "#FFFFFF"; font { bold: true; pixelSize: 11 } }
                        HoverHandler { id: hov }
                        TapHandler {
                            onTapped: if (root.missionReady) simBus.approveEngagement(root.pendingEng.engId)
                        }
                    }
                    Grid {
                        columns: 2; columnSpacing: 10; rowSpacing: 1
                        Repeater {
                            model: [
                                { label: "Confirmed track",       ok: root.prereqTrack },
                                { label: "Declared HOSTILE",      ok: root.prereqHostile },
                                { label: "Engagement proposed",   ok: root.prereqPending },
                                { label: "Effector available",    ok: root.prereqEffector },
                            ]
                            Row {
                                spacing: 4
                                Text {
                                    text: modelData.ok ? "●" : "○"
                                    color: modelData.ok ? root.c_active : root.c_dim
                                    font { pixelSize: 8; bold: true }
                                }
                                Text {
                                    text: modelData.label
                                    color: modelData.ok ? root.c_text : root.c_dim
                                    font.pixelSize: 8
                                }
                            }
                        }
                    }
                }

                // Deny
                Rectangle {
                    width: 90; height: 32; radius: 4
                    opacity: root.pendingEng ? 1.0 : 0.4
                    color: hovD.containsMouse ? "#B71C1C" : "#C62828"
                    border.color: "#EF5350"; border.width: 1
                    Text { anchors.centerIn: parent; text: "✘  DENY"
                           color: "#FFFFFF"; font { bold: true; pixelSize: 11 } }
                    HoverHandler { id: hovD }
                    TapHandler { onTapped: if (root.pendingEng) simBus.denyEngagement(root.pendingEng.engId) }
                }

                Rectangle { width: 1; height: 28; color: root.c_border; opacity: 0.5 }

                // Auto-ROE toggle — weapons free inside the restricted zone
                Rectangle {
                    width: 136; height: 32; radius: 4
                    color: root.autoRoe ? (hovS.containsMouse ? "#E65100" : "#EF6C00")
                                        : (hovS.containsMouse ? "#1565C0" : "#1976D2")
                    border.color: root.autoRoe ? "#FFB74D" : "#42A5F5"; border.width: 1
                    Text { anchors.centerIn: parent
                           text: root.autoRoe ? "⚠  AUTO-ROE: ON" : "👤  AUTO-ROE: OFF"
                           color: "#FFFFFF"; font { bold: true; pixelSize: 11 } }
                    HoverHandler { id: hovS }
                    TapHandler { onTapped: simBus.setAutoRoe(!root.autoRoe) }
                }

                // PVO weapons free / hold fire
                Rectangle {
                    width: 110; height: 32; radius: 4
                    property bool on: root.pvoData ? root.pvoData.enabled : true
                    color: on ? "#B71C1C" : "#37474F"
                    border.color: on ? "#EF9A9A" : "#78909C"; border.width: 1
                    Text { anchors.centerIn: parent; text: parent.on ? "PVO: AUTO" : "PVO: HOLD"
                           color: "#FFFFFF"; font { bold: true; pixelSize: 11 } }
                    TapHandler { onTapped: simBus.setPvoEnabled(!parent.on) }
                }

                // Abort all
                Rectangle {
                    width: 110; height: 32; radius: 4
                    color: hovA.containsMouse ? "#4A1942" : "#6A1B9A"
                    border.color: "#CE93D8"; border.width: 1
                    Text { anchors.centerIn: parent; text: "⏹  ABORT ALL"
                           color: "#FFFFFF"; font { bold: true; pixelSize: 11 } }
                    HoverHandler { id: hovA }
                    TapHandler { onTapped: simBus.abortAll() }
                }

                // Scenario editor
                Rectangle {
                    width: 84; height: 32; radius: 4
                    color: root.editMode ? "#E65100" : (hovE.containsMouse ? "#37474F" : "#263238")
                    border.color: root.editMode ? "#FFB74D" : "#78909C"; border.width: 1
                    Text { anchors.centerIn: parent; text: root.editMode ? "✎ EDITING" : "✎  EDIT"
                           color: "#FFFFFF"; font { bold: true; pixelSize: 11 } }
                    HoverHandler { id: hovE }
                    TapHandler { onTapped: simBus.setEditMode(!root.editMode) }
                }

                // Restart scenario
                Rectangle {
                    width: 84; height: 32; radius: 4
                    color: hovR.containsMouse ? "#37474F" : "#263238"
                    border.color: "#78909C"; border.width: 1
                    Text { anchors.centerIn: parent; text: "↺  RESET"
                           color: "#FFFFFF"; font { bold: true; pixelSize: 11 } }
                    HoverHandler { id: hovR }
                    TapHandler { onTapped: simBus.reset() }
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
        property string actionLabel: ""
        property string badge:       ""        // NATO symbol (symbols/<badge>.svg)
        signal action()
        Layout.fillWidth: true
        height: 96

        Rectangle {
            anchors { fill: parent; margins: 5 }
            color: root.c_card; radius: 4
            border.color: accentColor; border.width: 1

            ColumnLayout {
                anchors { fill: parent; margins: 7 }
                spacing: 3

                RowLayout {
                    spacing: 6
                    Rectangle { visible: badge === ""; width: 8; height: 8; radius: 2; color: accentColor }
                    Image { visible: badge !== ""; source: badge ? symbolsInfo.base + badge + ".svg" : ""
                            sourceSize.height: 18; smooth: true }
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
                RowLayout {
                    Layout.fillWidth: true
                    Text { text: detail2; color: root.c_dim; font.pixelSize: 9
                           Layout.fillWidth: true; elide: Text.ElideRight }
                    ActionButton {
                        visible: actionLabel !== ""
                        width: 64; height: 16
                        label: actionLabel
                        base: actionLabel.indexOf("LAUNCH") >= 0 ? "#2E7D32" : "#455A64"
                        edge: actionLabel.indexOf("LAUNCH") >= 0 ? "#66BB6A" : "#90A4AE"
                        onClicked: action()
                    }
                }
            }
        }
    }

    // A plain map icon (icons/<shape>_<colour>.svg) centred on lat/lon, rotated to
    // the heading; details on hover — names and badges live in the side lists
    component MapIcon: Image {
        property string icon: ""
        property real lat: 0
        property real lon: 0
        property real size: 26
        property real heading: 0
        property string tip: ""
        source: icon ? symbolsInfo.icons + icon + ".svg" : ""
        width: size; height: size
        sourceSize: Qt.size(Math.ceil(size), Math.ceil(size))
        x: mapCanvas.lonToX(lon) - size / 2
        y: mapCanvas.latToY(lat) - size / 2
        rotation: heading
        smooth: true
        antialiasing: true
        HoverHandler { id: iconHover }
        ToolTip.visible: iconHover.hovered && tip !== ""
        ToolTip.text: tip
        ToolTip.delay: 200
    }

    component WeaponCard: Item {
        property string badge:    ""            // NATO symbol (symbols/<badge>.svg)
        property string sysId:    ""
        property string position: ""
        property bool   armed:    false
        property string ammo:     ""
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

                Rectangle { visible: badge === ""; width: 8; height: 8; radius: 2
                             color: armed ? root.c_armed : root.c_standby }
                Image { visible: badge !== ""; source: badge ? symbolsInfo.base + badge + ".svg" : ""
                        sourceSize.height: 20; smooth: true; opacity: armed ? 1.0 : 0.5 }

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

    component ActionButton: Rectangle {
        property string label: ""
        property color  base:  "#2E7D32"
        property color  edge:  "#4CAF50"
        signal clicked()
        width: 92; height: 22; radius: 3
        opacity: enabled ? 1.0 : 0.4
        color: abHov.containsMouse && enabled ? Qt.darker(base, 1.3) : base
        border.color: edge; border.width: 1
        Text { anchors.centerIn: parent; text: parent.label
               color: "#FFFFFF"; font { bold: true; pixelSize: 10 } }
        HoverHandler { id: abHov }
        TapHandler { onTapped: if (parent.enabled) parent.clicked() }
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


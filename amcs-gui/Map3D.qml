// 3D terrain view of the C-UAS picture: elevation mesh with satellite imagery
// (sim/terrain.py), the DRIVE layer draped on the terrain, platforms as 3D
// models (quadcopter / fixed-wing UAV, attack helicopter, truck, UGV, PVO and
// ALAS launchers, radar, sensors) at their real height, each with its NATO
// symbol above it, and translucent PVO engagement domes.  Linked to the 2D
// map: it opens on the 2D map centre; ◎ FROM 2D / TO 2D sync the two views.
import QtQuick
import QtQuick3D
import QtQuick.Controls

Item {
    id: v3
    clip: true                              // symbols of off-screen objects must not spill over the dashboard
    property var dash                       // AMCSDashboard root (data + map)
    property var terr: dash ? dash.terrainData : null
    readonly property bool ready: terr !== null && terr !== undefined && terr.ready === true
    property real exaggeration: 1.5
    property bool showSymbols: false        // NATO badges live in the lists; SYM shows them here too
    property string borderUrl: ""           // border / administrative line draped on the terrain
    property string driveUrl: ""            // DRIVE layer re-mapped onto the terrain box
    readonly property bool live: ready && visible        // hidden 3D view does no per-frame work
    readonly property real kLon: ready ? 111320 * Math.cos(terr.centerLat * Math.PI / 180) : 1
    // bumped when the camera moves so screen-space symbols re-project
    property int camTick: 0
    // Data arrays.  Repeaters take the *count* as model and read element
    // [index], so a new frame updates the existing 3D objects instead of
    // destroying and re-creating every delegate (≈150 ms per frame otherwise).
    readonly property var tracksA: live ? dash.trackData : []
    readonly property var pvoA:    live && dash.pvoData ? dash.pvoData.sites : []
    readonly property var ggA:     live && dash.pvoData ? dash.pvoData.gg : []
    readonly property var sitesA:  pvoA.concat(ggA)
    readonly property var radarA:  ready && dash.laydownData ? dash.laydownData.radars : []
    readonly property var sensorA: ready && dash.laydownData ? dash.laydownData.acoustic.concat(dash.laydownData.seismic) : []
    readonly property var ugvA:    live ? dash.ugvsData : []
    readonly property var uavA:    live ? dash.uavsData.filter(function(u) { return u.airborne }) : []
    readonly property var truthA:  live && dash.showTruth ? dash.targetsData.filter(function(t) {
                                       return t.state !== "DESTROYED" && t.state !== "EXITED" }) : []
    readonly property var none:    ({ lat: 0, lon: 0, altitudeM: 0, altM: 0, rangeM: 0, headingDeg: 0,
                                      ammo: 0, identity: "", domain: "AIR", trackId: "", id: "", name: "",
                                      objClass: "", cls: "", gunRangeM: 0, system: "" })

    // model size grows with camera distance so platforms stay readable
    readonly property real mk: Math.max(1.0, cam.z / 9000)

    function toX(lon) { return (lon - terr.centerLon) * kLon }
    function toZ(lat) { return -(lat - terr.centerLat) * 111320 }
    function toLat(z) { return terr.centerLat - z / 111320 }
    function toLon(x) { return terr.centerLon + x / kLon }
    function groundM(lat, lon) {
        if (!ready) return 0
        var b = terr.bbox
        var c = Math.max(0, Math.min(terr.cols - 1.001, (lon - b.lonMin) / (b.lonMax - b.lonMin) * (terr.cols - 1)))
        var r = Math.max(0, Math.min(terr.rows - 1.001, (b.latMax - lat) / (b.latMax - b.latMin) * (terr.rows - 1)))
        var c0 = Math.floor(c), r0 = Math.floor(r), ac = c - c0, ar = r - r0
        var h = terr.heights, n = terr.cols
        var top = h[r0 * n + c0] * (1 - ac) + h[r0 * n + c0 + 1] * ac
        var bot = h[(r0 + 1) * n + c0] * (1 - ac) + h[(r0 + 1) * n + c0 + 1] * ac
        return top * (1 - ar) + bot * ar
    }
    function groundY(lat, lon) { return (groundM(lat, lon) - terr.minM) * exaggeration }
    function altY(lat, lon, altM) { return groundY(lat, lon) + Math.max(0, altM) * exaggeration }
    function pos(lat, lon, altM) { return Qt.vector3d(toX(lon), altY(lat, lon, altM), toZ(lat)) }

    function identityColor(id) {
        return id === "HOSTILE" ? "#E53935" : id === "SUSPECT" ? "#FFB300" :
               id === "NEUTRAL" ? "#4FC3F7" : "#E0E0E0"
    }
    // Which 3D model a track / truth object gets
    function shapeOf(domain, cls) {
        if (domain === "GROUND") return "truck"
        if (cls === "ATTACK_HELICOPTER") return "helo"
        if (cls === "UAV_FIXED_WING") return "wing"
        return "quad"
    }
    function symUrl(name) { return symbolsInfo.base + name + ".svg" }

    // ── camera: orbit around `origin` (a point on the ground) ───────────
    // Zoom and pan scale with the camera distance, so they feel the same
    // from 300 m to 60 km (a fixed step per wheel click / pixel does not).
    property real yaw: 0            // degrees, 0 = looking north
    property real pitch: -38        // degrees below the horizon
    function clamp(v, a, b) { return Math.max(a, Math.min(b, v)) }
    function zoomBy(f) { cam.z = clamp(cam.z * f, 250, 70000) }
    function lookAt(x, z) {
        if (!ready) return
        var h = terr.widthM / 2
        x = clamp(x, -h, h); z = clamp(z, -h, h)
        origin.position = Qt.vector3d(x, groundY(toLat(z), toLon(x)), z)
    }
    function panBy(dx, dy) {
        // metres per screen pixel at the orbit point; screen-down → move forward on the ground
        var mpp = cam.z * 2 * Math.tan(cam.fieldOfView * Math.PI / 360) / Math.max(1, view.height)
        var a = yaw * Math.PI / 180
        var fwd = mpp / Math.max(0.3, Math.sin(-pitch * Math.PI / 180))
        lookAt(origin.position.x - Math.cos(a) * dx * mpp - Math.sin(a) * dy * fwd,
               origin.position.z + Math.sin(a) * dx * mpp - Math.cos(a) * dy * fwd)
    }
    function resetView() { yaw = 0; pitch = -38; cam.z = 16000; syncFrom2D() }

    function load() {
        if (!dash || !dash.laydownData) return
        terrainProvider.load(dash.laydownData.base.lat, dash.laydownData.base.lon, 12000)
    }
    function updateDrape() {
        var d = drivData
        driveUrl = ready && d && d.ready && d.url ? terrainProvider.drape(d.url, d.bbox) : ""
    }
    // Look at the point the 2D map is centred on
    function syncFrom2D() {
        if (!ready) return
        var m = dash.map2d
        lookAt(toX(m.mapCenterLon), toZ(m.mapCenterLat))
    }
    function syncTo2D() {
        if (!ready) return
        dash.map2d.mapCenterLat = toLat(origin.position.z)
        dash.map2d.mapCenterLon = toLon(origin.position.x)
        dash.map2d.requestPaint()
    }

    onDashChanged: load()
    onExaggerationChanged: terrainMesh.exaggeration = exaggeration
    onReadyChanged: if (ready) { syncFrom2D(); updateDrape(); updateBorder() }
    Component.onCompleted: { load(); if (ready) { syncFrom2D(); updateDrape(); updateBorder() } }
    readonly property var drivData: dash ? dash.drivData : null
    onDrivDataChanged: updateDrape()
    readonly property var borderData: dash ? dash.borderData : null
    onBorderDataChanged: updateBorder()
    function updateBorder() {
        borderUrl = ready && borderData && borderData.lines.length ? terrainProvider.drapeLines(borderData.lines) : ""
    }

    // ── 3D models built from primitives, nose to −z (north), ~1 unit = 1 m ──
    component Paint: PrincipledMaterial { roughness: 0.55; metalness: 0.15 }

    component QuadDrone: Node {
        property color tint: "#E53935"
        Model { source: "#Cube"; scale: Qt.vector3d(0.5, 0.2, 0.5); materials: Paint { baseColor: tint } }
        Model { source: "#Cube"; eulerRotation.y: 45; scale: Qt.vector3d(1.5, 0.06, 0.1)
                materials: Paint { baseColor: "#263238" } }
        Model { source: "#Cube"; eulerRotation.y: -45; scale: Qt.vector3d(1.5, 0.06, 0.1)
                materials: Paint { baseColor: "#263238" } }
        Repeater3D {
            model: 4
            delegate: Model {
                required property int index
                source: "#Cylinder"
                position: Qt.vector3d(53 * (index % 2 ? 1 : -1), 9, 53 * (index < 2 ? 1 : -1))
                scale: Qt.vector3d(0.44, 0.02, 0.44)
                materials: PrincipledMaterial { baseColor: "#CFD8DC"; opacity: 0.6
                                                alphaMode: PrincipledMaterial.Blend }
            }
        }
    }
    component FixedWing: Node {
        property color tint: "#E53935"
        Model { source: "#Cylinder"; eulerRotation.x: 90; scale: Qt.vector3d(0.16, 1.3, 0.16)
                materials: Paint { baseColor: tint } }
        Model { source: "#Cube"; z: -8; scale: Qt.vector3d(2.0, 0.05, 0.32); materials: Paint { baseColor: tint } }
        Model { source: "#Cube"; z: 56; scale: Qt.vector3d(0.75, 0.04, 0.18); materials: Paint { baseColor: tint } }
        Model { source: "#Cube"; z: 56; y: 13; scale: Qt.vector3d(0.04, 0.28, 0.18); materials: Paint { baseColor: tint } }
    }
    component Helicopter: Node {
        property color tint: "#8D6E63"
        Model { source: "#Sphere"; scale: Qt.vector3d(0.42, 0.42, 0.9); materials: Paint { baseColor: tint } }
        Model { source: "#Sphere"; z: -32; y: 8; scale: Qt.vector3d(0.26, 0.22, 0.3)        // canopy
                materials: Paint { baseColor: "#263238"; metalness: 0.6; roughness: 0.2 } }
        Model { source: "#Cylinder"; eulerRotation.x: 90; z: 80; y: 6; scale: Qt.vector3d(0.08, 1.0, 0.08)
                materials: Paint { baseColor: tint } }
        Model { source: "#Cube"; z: 128; y: 20; scale: Qt.vector3d(0.04, 0.38, 0.16); materials: Paint { baseColor: tint } }
        Model { source: "#Cube"; y: -4; scale: Qt.vector3d(1.0, 0.04, 0.14); materials: Paint { baseColor: "#37474F" } }   // stub wings
        Model { source: "#Cylinder"; y: 30; scale: Qt.vector3d(1.7, 0.01, 1.7)                                             // rotor disc
                materials: PrincipledMaterial { baseColor: "#ECEFF1"; opacity: 0.3; alphaMode: PrincipledMaterial.Blend
                                                cullMode: Material.NoCulling } }
        Model { source: "#Cube"; y: 31; scale: Qt.vector3d(1.7, 0.02, 0.07); materials: Paint { baseColor: "#212121" } }
        Model { source: "#Cube"; y: 31; eulerRotation.y: 90; scale: Qt.vector3d(1.7, 0.02, 0.07); materials: Paint { baseColor: "#212121" } }
    }
    component Truck: Node {
        property color tint: "#6D4C41"
        Model { source: "#Cube"; z: -40; y: 26; scale: Qt.vector3d(0.46, 0.4, 0.32); materials: Paint { baseColor: Qt.darker(tint, 1.3) } }
        Model { source: "#Cube"; z: 14; y: 30; scale: Qt.vector3d(0.5, 0.46, 0.78); materials: Paint { baseColor: tint } }
        Repeater3D {
            model: 6
            delegate: Model {
                required property int index
                source: "#Cylinder"
                eulerRotation.z: 90
                position: Qt.vector3d(index % 2 ? 25 : -25, 9, [-40, 4, 38][Math.floor(index / 2)])
                scale: Qt.vector3d(0.18, 0.1, 0.18)
                materials: Paint { baseColor: "#212121" }
            }
        }
    }
    component Ugv: Node {
        id: ugvRoot
        property color tint: "#558B2F"
        property bool jamming: false
        Model { source: "#Cube"; y: 20; scale: Qt.vector3d(0.52, 0.22, 0.82); materials: Paint { baseColor: tint } }
        Model { source: "#Cube"; x: -32; y: 11; scale: Qt.vector3d(0.14, 0.22, 0.9); materials: Paint { baseColor: "#263238" } }
        Model { source: "#Cube"; x: 32; y: 11; scale: Qt.vector3d(0.14, 0.22, 0.9); materials: Paint { baseColor: "#263238" } }
        Model { source: "#Cylinder"; y: 52; z: 10; scale: Qt.vector3d(0.04, 0.6, 0.04); materials: Paint { baseColor: "#B0BEC5" } }
        Model { source: "#Cube"; y: 40; z: -20; scale: Qt.vector3d(0.32, 0.22, 0.05)        // directional jammer panel
                materials: Paint { baseColor: ugvRoot.jamming ? "#FFEB3B" : "#CFD8DC"
                                   emissiveFactor: ugvRoot.jamming ? Qt.vector3d(1, 0.9, 0.2) : Qt.vector3d(0, 0, 0) } }
    }
    component Launcher: Node {
        id: lr
        property color tint: "#4E6B3A"
        property int tubes: 4
        property real elev: 35
        property bool gun: false
        property bool box: false            // ALAS: box launcher instead of round tubes
        property bool armed: true
        Model { source: "#Cube"; y: 18; scale: Qt.vector3d(0.6, 0.24, 1.1); materials: Paint { baseColor: tint } }
        Model { source: "#Cube"; x: -34; y: 9; scale: Qt.vector3d(0.12, 0.18, 1.1); materials: Paint { baseColor: "#263238" } }
        Model { source: "#Cube"; x: 34; y: 9; scale: Qt.vector3d(0.12, 0.18, 1.1); materials: Paint { baseColor: "#263238" } }
        Node {
            y: 40; z: 10
            Model { source: "#Cube"; scale: Qt.vector3d(0.42, 0.18, 0.42); materials: Paint { baseColor: Qt.darker(tint, 1.15) } }
            Repeater3D {
                model: lr.box ? 1 : lr.tubes
                delegate: Model {
                    required property int index
                    source: lr.box ? "#Cube" : "#Cylinder"
                    eulerRotation.x: -(90 - lr.elev)
                    position: Qt.vector3d(lr.box ? 0 : (index - (lr.tubes - 1) / 2) * 13, 22, -8)
                    scale: lr.box ? Qt.vector3d(0.42, 0.75, 0.22) : Qt.vector3d(0.09, 0.8, 0.09)
                    materials: Paint { baseColor: lr.armed ? "#ECEFF1" : "#607D8B" }
                }
            }
            Model {
                visible: lr.gun
                source: "#Cylinder"
                eulerRotation.x: -(90 - 20)
                position: Qt.vector3d(0, 14, -40)
                scale: Qt.vector3d(0.05, 0.9, 0.05)
                materials: Paint { baseColor: "#212121" }
            }
        }
    }
    component Radar: Node {
        Model { source: "#Cube"; y: 12; scale: Qt.vector3d(0.5, 0.2, 0.8); materials: Paint { baseColor: "#4E6B3A" } }
        Model { source: "#Cylinder"; y: 60; scale: Qt.vector3d(0.06, 0.9, 0.06); materials: Paint { baseColor: "#90A4AE" } }
        Model { source: "#Cube"; y: 110; eulerRotation.x: -15; scale: Qt.vector3d(0.8, 0.5, 0.05)
                materials: Paint { baseColor: "#ECEFF1" } }
    }
    component Sensor: Node {
        property bool detected: false
        Model { source: "#Cone"; scale: Qt.vector3d(0.25, 0.4, 0.25); materials: Paint { baseColor: "#5D4037" } }
        Model { source: "#Sphere"; y: 45; scale: Qt.vector3d(0.22, 0.22, 0.22)
                materials: Paint { baseColor: detected ? "#FFD54F" : "#FFF9C4"
                                   emissiveFactor: detected ? Qt.vector3d(1, 0.8, 0.2) : Qt.vector3d(0, 0, 0) } }
    }
    component Base: Node {
        Model { source: "#Cube"; y: 25; scale: Qt.vector3d(1.6, 0.5, 0.9); materials: Paint { baseColor: "#8D9440" } }
        Model { source: "#Cube"; x: 130; y: 18; scale: Qt.vector3d(0.8, 0.36, 0.8); materials: Paint { baseColor: "#7E8B3C" } }
        Model { source: "#Cylinder"; x: -120; y: 70; scale: Qt.vector3d(0.05, 1.4, 0.05); materials: Paint { baseColor: "#B0BEC5" } }
        Model { source: "#Cube"; x: -100; y: 128; scale: Qt.vector3d(0.4, 0.22, 0.02)
                materials: Paint { baseColor: "#FFD54F"; emissiveFactor: Qt.vector3d(0.8, 0.6, 0.1) } }
    }

    Component { id: quadC;  QuadDrone  { tint: parent ? parent.tint : "#E0E0E0" } }
    Component { id: wingC;  FixedWing  { tint: parent ? parent.tint : "#E0E0E0" } }
    Component { id: heloC;  Helicopter { tint: parent ? Qt.darker(parent.tint, 1.4) : "#9E9E9E" } }
    Component { id: truckC; Truck      { tint: parent ? Qt.darker(parent.tint, 1.6) : "#9E9E9E" } }
    function shapeComponent(shape) {
        return shape === "wing" ? wingC : shape === "helo" ? heloC : shape === "truck" ? truckC : quadC
    }

    Rectangle { anchors.fill: parent; color: "#0D1B2A" }

    View3D {
        id: view
        anchors.fill: parent
        camera: cam
        environment: SceneEnvironment {
            clearColor: "#0D1B2A"
            backgroundMode: SceneEnvironment.Color
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
        }

        Node {
            id: origin
            objectName: "origin3d"
            eulerRotation: Qt.vector3d(v3.pitch, v3.yaw, 0)
            onPositionChanged: v3.camTick++
            onRotationChanged: v3.camTick++
            PerspectiveCamera {
                id: cam
                objectName: "cam3d"
                z: 16000
                clipNear: 20; clipFar: 150000
                fieldOfView: 45
                onZChanged: v3.camTick++
            }
        }

        DirectionalLight { eulerRotation.x: -55; eulerRotation.y: -35; brightness: 1.15 }
        DirectionalLight { eulerRotation.x: -85; eulerRotation.y: 120; brightness: 0.45 }

        // ── terrain + DRIVE layer draped on it ───────────────────────────
        Model {
            id: terrainModel
            visible: v3.ready
            pickable: true
            geometry: terrainMesh
            materials: PrincipledMaterial {
                baseColorMap: Texture { source: v3.ready ? v3.terr.textureUrl : "" }
                roughness: 1.0; metalness: 0.0
                cullMode: Material.NoCulling
            }
        }
        Model {
            visible: v3.ready && v3.driveUrl !== "" && v3.dash.showDrive
            geometry: terrainMesh
            y: 8 * v3.exaggeration
            materials: PrincipledMaterial {
                baseColorMap: Texture { source: v3.driveUrl; generateMipmaps: true
                                        minFilter: Texture.Linear; magFilter: Texture.Linear
                                        mipFilter: Texture.Linear }
                lighting: PrincipledMaterial.NoLighting
                alphaMode: PrincipledMaterial.Blend
                opacity: v3.dash.driveOpacity
                cullMode: Material.NoCulling
            }
        }

        Model {
            visible: v3.ready && v3.borderUrl !== ""
            geometry: terrainMesh
            y: 12 * v3.exaggeration
            materials: PrincipledMaterial {
                baseColorMap: Texture { source: v3.borderUrl; generateMipmaps: true
                                        minFilter: Texture.Linear; magFilter: Texture.Linear; mipFilter: Texture.Linear }
                lighting: PrincipledMaterial.NoLighting
                alphaMode: PrincipledMaterial.Blend
                cullMode: Material.NoCulling
            }
        }

        // ── restricted zone (translucent column) + base ──────────────────
        Model {
            visible: v3.ready && v3.dash.laydownData !== null
            source: "#Cylinder"
            property var ld: v3.dash.laydownData
            position: ld && v3.ready ? v3.pos(ld.base.lat, ld.base.lon, 0).plus(Qt.vector3d(0, 300 * v3.exaggeration, 0)) : Qt.vector3d(0, 0, 0)
            scale: ld ? Qt.vector3d(ld.zoneRadiusM / 50, 6 * v3.exaggeration, ld.zoneRadiusM / 50) : Qt.vector3d(1, 1, 1)
            opacity: 0.10
            materials: PrincipledMaterial { baseColor: "#FFB300"; lighting: PrincipledMaterial.NoLighting
                                            alphaMode: PrincipledMaterial.Blend; cullMode: Material.NoCulling
                                            depthDrawMode: Material.NeverDepthDraw }
        }
        Base {
            visible: v3.ready && v3.dash.laydownData !== null
            property var b: v3.dash.laydownData ? v3.dash.laydownData.base : null
            position: b && v3.ready ? v3.pos(b.lat, b.lon, 0) : Qt.vector3d(0, 0, 0)
            scale: Qt.vector3d(v3.mk, v3.mk, v3.mk)
        }

        // ── PVO sites: launcher + engagement dome ────────────────────────
        Repeater3D {
            model: v3.pvoA.length
            delegate: Node {
                required property int index
                readonly property var d: v3.pvoA[index] || v3.none
                position: v3.pos(d.lat, d.lon, 0)
                Launcher {
                    scale: Qt.vector3d(v3.mk, v3.mk, v3.mk)
                    gun: d.gunRangeM > 0
                    tubes: d.system === "PANTSIR_S1" ? 6 : d.system === "STRELA_10M3" ? 4 : 2
                    armed: (d.ammo + d.reserve) > 0
                }
                Model {
                    source: "#Sphere"
                    scale: Qt.vector3d(d.rangeM / 50, d.rangeM / 50 * v3.exaggeration, d.rangeM / 50)
                    opacity: 0.06
                    materials: PrincipledMaterial { baseColor: "#EF9A9A"; lighting: PrincipledMaterial.NoLighting
                                                    alphaMode: PrincipledMaterial.Blend; cullMode: Material.NoCulling
                                                    depthDrawMode: Material.NeverDepthDraw }
                }
            }
        }
        // GG (ALAS) launchers, radars, field sensors
        Repeater3D {
            model: v3.ggA.length
            delegate: Launcher {
                required property int index
                readonly property var d: v3.ggA[index] || v3.none
                position: v3.pos(d.lat, d.lon, 0)
                scale: Qt.vector3d(v3.mk, v3.mk, v3.mk)
                tint: "#5D5A3A"; box: true; elev: 25; armed: d.ammo > 0
            }
        }
        Repeater3D {
            model: v3.radarA.length
            delegate: Radar {
                required property int index
                readonly property var d: v3.radarA[index] || v3.none
                position: v3.pos(d.lat, d.lon, 0)
                scale: Qt.vector3d(v3.mk, v3.mk, v3.mk)
            }
        }
        Repeater3D {
            model: v3.sensorA.length
            delegate: Sensor {
                required property int index
                readonly property var d: v3.sensorA[index] || v3.none
                position: v3.pos(d.lat, d.lon, 0)
                scale: Qt.vector3d(v3.mk, v3.mk, v3.mk)
            }
        }

        // ── own platforms ────────────────────────────────────────────────
        Repeater3D {
            model: v3.ugvA.length
            delegate: Ugv {
                required property int index
                readonly property var d: v3.ugvA[index] || v3.none
                position: v3.pos(d.lat, d.lon, 0)
                eulerRotation.y: -d.headingDeg
                scale: Qt.vector3d(v3.mk, v3.mk, v3.mk)
                jamming: d.jamming === true
                tint: d.destroyed ? "#5F6368" : "#558B2F"
            }
        }
        Repeater3D {
            model: v3.uavA.length
            delegate: QuadDrone {
                required property int index
                readonly property var d: v3.uavA[index] || v3.none
                position: v3.pos(d.lat, d.lon, d.altitudeM)
                eulerRotation.y: -d.headingDeg
                scale: Qt.vector3d(v3.mk, v3.mk, v3.mk)
                tint: "#29B6F6"
            }
        }

        // ── fused tracks: model at altitude (identity colour) + drop line ─
        Repeater3D {
            model: v3.tracksA.length
            delegate: Node {
                id: trk
                required property int index
                readonly property var d: v3.tracksA[index] || v3.none
                readonly property string shape: v3.shapeOf(d.domain, d.objClass)
                readonly property color tint: d.engState === "NEUTRALIZED" ? "#757575" : v3.identityColor(d.identity)
                readonly property real gy: v3.groundY(d.lat, d.lon)
                readonly property real ay: d.domain === "GROUND" ? gy : v3.altY(d.lat, d.lon, d.altitudeM)
                position: Qt.vector3d(v3.toX(d.lon), 0, v3.toZ(d.lat))
                Loader3D {
                    property color tint: trk.tint
                    y: trk.ay
                    eulerRotation.y: -trk.d.headingDeg
                    scale: Qt.vector3d(v3.mk, v3.mk, v3.mk)
                    sourceComponent: v3.shapeComponent(trk.shape)
                }
                Model {
                    visible: trk.d.domain !== "GROUND"
                    source: "#Cylinder"
                    y: (trk.gy + trk.ay) / 2
                    scale: Qt.vector3d(0.05 * v3.mk, Math.max(0.01, (trk.ay - trk.gy) / 100), 0.05 * v3.mk)
                    opacity: 0.6
                    materials: PrincipledMaterial { baseColor: trk.tint; lighting: PrincipledMaterial.NoLighting
                                                    alphaMode: PrincipledMaterial.Blend }
                }
            }
        }

        // ── ground truth (TRUTH overlay): faint models ───────────────────
        Repeater3D {
            model: v3.truthA.length
            delegate: Node {
                required property int index
                readonly property var d: v3.truthA[index] || v3.none
                readonly property string shape: v3.shapeOf(d.domain, d.cls)
                position: v3.pos(d.lat, d.lon, d.domain === "GROUND" ? 0 : d.altM)
                scale: Qt.vector3d(0.55 * v3.mk, 0.55 * v3.mk, 0.55 * v3.mk)
                opacity: 0.45
                Loader3D {
                    property color tint: "#BDBDBD"
                    sourceComponent: v3.shapeComponent(parent.shape)
                }
            }
        }
    }

    // ── mouse / trackpad navigation ──────────────────────────────────────
    //   left-drag: orbit · right/middle-drag or shift+left-drag: pan
    //   wheel / two-finger scroll / pinch: zoom · double-click: look here
    Item {
        id: nav
        anchors.fill: parent
        property real yaw0: 0
        property real pitch0: 0
        property bool panAtPress: false
        // modifiers as they were at the press (a drag activates on the first move)
        PointHandler {
            acceptedButtons: Qt.LeftButton
            onActiveChanged: if (active)
                nav.panAtPress = (point.modifiers & (Qt.ShiftModifier | Qt.ControlModifier | Qt.MetaModifier)) !== 0
        }
        // Left button: orbit; with Shift (or ⌘) held at the press: pan.
        // The mode is fixed at the press, so releasing Shift mid-drag is harmless.
        DragHandler {
            id: leftDrag
            target: null
            acceptedButtons: Qt.LeftButton
            dragThreshold: 2
            property bool panMode: false
            property point prev: Qt.point(0, 0)
            onActiveChanged: if (active) {
                panMode = nav.panAtPress ||
                          (centroid.modifiers & (Qt.ShiftModifier | Qt.ControlModifier | Qt.MetaModifier)) !== 0
                nav.yaw0 = v3.yaw; nav.pitch0 = v3.pitch
                prev = Qt.point(0, 0)
            }
            onTranslationChanged: if (active) {
                if (panMode) {
                    v3.panBy(translation.x - prev.x, translation.y - prev.y)
                    prev = Qt.point(translation.x, translation.y)
                } else {
                    v3.yaw = nav.yaw0 - translation.x * 0.3
                    v3.pitch = v3.clamp(nav.pitch0 - translation.y * 0.25, -89, -6)
                }
            }
        }
        DragHandler {
            id: panDrag
            target: null
            acceptedButtons: Qt.RightButton | Qt.MiddleButton
            dragThreshold: 2
            property point prev: Qt.point(0, 0)
            onActiveChanged: prev = Qt.point(0, 0)
            onTranslationChanged: if (active) {
                v3.panBy(translation.x - prev.x, translation.y - prev.y)
                prev = Qt.point(translation.x, translation.y)
            }
        }
        WheelHandler {
            acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
            onWheel: function(ev) {
                var d = ev.pixelDelta.y !== 0 ? ev.pixelDelta.y * 2.5 : ev.angleDelta.y
                v3.zoomBy(Math.pow(0.9985, d))          // one wheel notch (120) ≈ 16 %
            }
        }
        PinchHandler {
            target: null
            property real z0: 0
            onActiveChanged: if (active) z0 = cam.z
            onActiveScaleChanged: if (active) v3.zoomBy((z0 / Math.max(0.05, activeScale)) / cam.z)
        }
        TapHandler {
            acceptedButtons: Qt.LeftButton
            onDoubleTapped: function(ep) {
                var hit = view.pick(ep.position.x, ep.position.y)
                if (hit.objectHit === terrainModel)
                    v3.lookAt(hit.scenePosition.x, hit.scenePosition.z)
            }
        }
    }

    // ── NATO symbols above the 3D objects (same SVGs as the 2D map) ──────
    component SymbolTag: Item {
        id: tag
        property vector3d at
        property string sym: ""
        property string label: ""
        property color labelColor: "#FFFFFF"
        property real dim: 1.0
        readonly property vector3d sp: { v3.camTick; return view.mapFrom3DScene(at) }
        visible: v3.showSymbols && sym !== "" && sp.z > 0 && sp.x > -50 && sp.x < v3.width + 50 &&
                 sp.y > -10 && sp.y < v3.height + 40
        x: sp.x; y: sp.y
        opacity: dim
        Image {
            id: symImg
            source: tag.sym ? v3.symUrl(tag.sym) : ""
            sourceSize.height: 30
            x: -width / 2; y: -height - 6
            smooth: true
        }
        // names live in the side lists; hover shows what the symbol is
        HoverHandler { id: tagHover; target: symImg }
        ToolTip.visible: tagHover.hovered && tag.label !== ""
        ToolTip.text: tag.label
        ToolTip.delay: 200
    }
    Repeater {
        model: v3.tracksA.length
        SymbolTag {
            required property int index
            readonly property var d: v3.tracksA[index] || v3.none
            at: v3.pos(d.lat, d.lon, d.domain === "GROUND" ? 60 : d.altitudeM + 60)
            sym: d.trackId ? v3.dash.map2d.trackSymbol(d) : ""
            label: d.trackId + (d.engState ? " " + d.engState : "")
            labelColor: v3.identityColor(d.identity)
            dim: d.engState === "NEUTRALIZED" ? 0.4 : 1.0
        }
    }
    Repeater {
        model: v3.sitesA.length
        SymbolTag {
            required property int index
            readonly property var d: v3.sitesA[index] || v3.none
            at: v3.pos(d.lat, d.lon, 160)
            sym: d.system === "ALAS" ? "site_ssm" : d.gunRangeM > 0 ? "site_pvo_gun" : "site_pvo_sam"
            label: d.id + "  " + d.name
            labelColor: d.system === "ALAS" ? "#CE93D8" : "#EF9A9A"
        }
    }
    Repeater {
        model: v3.uavA.length
        SymbolTag {
            required property int index
            readonly property var d: v3.uavA[index] || v3.none
            at: v3.pos(d.lat, d.lon, d.altitudeM + 60)
            sym: "air_friend_uav"
            label: d.deviceId || ""
            labelColor: "#B3E5FC"
        }
    }
    Repeater {
        model: v3.ugvA.length
        SymbolTag {
            required property int index
            readonly property var d: v3.ugvA[index] || v3.none
            at: v3.pos(d.lat, d.lon, 90)
            sym: "gnd_friend_ugv"
            label: d.deviceId || ""
            labelColor: "#B3E5FC"
        }
    }
    Repeater {
        model: v3.radarA.length
        SymbolTag {
            required property int index
            readonly property var d: v3.radarA[index] || v3.none
            at: v3.pos(d.lat, d.lon, 200)
            sym: "site_radar"
            label: (d.label || "") + "  " + (d.systemName || "")
            labelColor: "#80CBC4"
        }
    }

    // ── HUD ──────────────────────────────────────────────────────────────
    Column {
        anchors { left: parent.left; top: parent.top; margins: 10 }
        spacing: 4
        Text {
            text: !v3.terr ? "3D terrain: waiting…" :
                  v3.ready ? "3D TERRAIN  " + Math.round(v3.terr.minM) + "–" + Math.round(v3.terr.maxM) +
                             " m ASL  ·  ±" + (v3.terr.widthM / 2000).toFixed(0) + " km  ·  height ×" + v3.exaggeration.toFixed(1) +
                             (v3.dash.showDrive ? (v3.driveUrl ? "  ·  DRIVE " + Math.round(v3.dash.driveOpacity * 100) + " %"
                                                               : "  ·  DRIVE not loaded") : "")
                           : "3D terrain: " + v3.terr.status
            color: v3.ready ? "#90CAF9" : "#FFE082"
            font { pixelSize: 10; family: "Menlo"; bold: true }
            style: Text.Outline; styleColor: "#000000"
        }
        Text {
            text: "drag: orbit · right-drag / shift+drag: pan · wheel / pinch: zoom · double-click: look here"
            color: "#7899AA"; font.pixelSize: 9
            style: Text.Outline; styleColor: "#000000"
        }
    }
    Row {
        anchors { right: parent.right; top: parent.top; margins: 10 }
        spacing: 4
        Repeater {
            model: [
                { label: "h ×1",   act: function() { v3.exaggeration = 1.0 } },
                { label: "h ×1.5", act: function() { v3.exaggeration = 1.5 } },
                { label: "h ×3",   act: function() { v3.exaggeration = 3.0 } },
                { label: "SYM",    act: function() { v3.showSymbols = !v3.showSymbols } },
                { label: "⟲ RESET", act: function() { v3.resetView() } },
                { label: "◎ FROM 2D", act: function() { v3.syncFrom2D() } },
                { label: "◎ TO 2D",   act: function() { v3.syncTo2D() } },
            ]
            Rectangle {
                required property var modelData
                width: lblT.implicitWidth + 14; height: 20; radius: 3
                color: modelData.label === "SYM" && v3.showSymbols ? "#CC1565C0" : "#CC1E3550"
                border.color: "#2E4560"
                Text { id: lblT; anchors.centerIn: parent; text: modelData.label
                       color: "#FFFFFF"; font { pixelSize: 9; bold: true } }
                TapHandler { onTapped: modelData.act() }
            }
        }
    }
    Text {
        anchors { right: parent.right; bottom: parent.bottom; margins: 6 }
        text: "Imagery © Esri World Imagery · Elevation: AWS Terrain Tiles (SRTM) · Symbols: APP-6 via milsymbol"
        color: "#99FFFFFF"; font.pixelSize: 8
        style: Text.Outline; styleColor: "#000000"
    }
}

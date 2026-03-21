# Autonomous Multi-Sensor Command System for Unmanned Battle Zones

**Predmet:** Projektovanje softvera
**Studijski program:** Master studije — Softversko inzenjerstvo
**Akademska godina:** 2025/2026
**Autor:** [Ime i Prezime]
**Datum:** Mart 2026

---

# I. UVOD

## 1.1 Opis problema

Savremeno borbeno okruzenje karakterise izuzetna dinamicnost, heterogenost prijetnji i neophodnost donosenja odluka u realnom vremenu. Uvođenje autonomnih sistema — UAV i UGV — omogucava operativan pristup opasnim terenima bez izlaganja ljudskog osoblja, ali generisu ogromne kolicine heterogenih senzorskih podataka koje je tesko integrirati u realnom vremenu.

**Kljucni problemi:**
- Fragmentiranost podataka: svaki senzor (akustika, seizmika, radar, LiDAR, kamera) daje parcijalni pogled
- Latencija: obrada na centralnom serveru uvodi kasnjenja
- Identifikacija meta: potreba za AI/ML modelima koji pouzdano identifikuju prijetnje
- Procjena trajektorije: pracenje mete i predvidanje pozicije za presretanje
- Odluka operatera: covjek-u-petlji princip (operator approve/deny)

## 1.2 Cilj sistema — 3 kontrolera

**Controller 1 — Sensor Detection & Pre-Processing:**
Senzori (akustika, seizmika, radar, LiDAR, kamera) detektuju aktivnost u monitoriranim zonama. Edge procesor vrsi preliminarnu obradu. Sistem prati kretanje UGV/UAV jedinica.

**Controller 2 — Sensor Fusion & Alarm System:**
Fuzija pre-procesiranih senzorskih podataka (Kalman filter). AI/ML model identifikuje metu i procjenjuje prijetnju. Procjena trajektorije i proracun tacke presretanja. Generisanje alarma za operatera.

**Controller 3 — Operator Decision (Approve/Deny):**
Operater pregleda alarm i podatke o meti. Odobrenje ili odbacivanje akcije. Aktivacija odbrambenog sistema (wakeup, deploy). Feedback — pogodak: misija zavrsena, promasaj: novi ciklus.

### Quality Attributes

| Atribut | Zahtjev |
|---------|---------|
| Latencija | < 200ms od detekcije do prikaza operateru |
| Raspolozivost | 99.9% uptime |
| Skalabilnost | 50+ simultanih UAV/UGV jedinica |
| Pouzdanost | Automatski failover |

## 1.3 Scope

**U scopu:** Softverska arhitektura (3 kontrolera), UML modelovanje, obrada senzorskih podataka, AI/ML identifikacija, procjena trajektorije, sistem alarma, odbrambena koordinacija, operator decision s feedback petljom.

**Van scopa:** Firmware za UAV/UGV, fizicki hardver, ML model trening, UI implementacija, administratorski panel.

---

# II. UML DIJAGRAMI

## 2.1 Use Case Diagram

### Akteri

| Akter | Opis |
|-------|------|
| **Operator** | Vojni operater koji prati zonu, pregleda alarme, odobrava ili odbacuje odbrambene akcije i procjenjuje rezultate |

### Use Case-ovi

| ID | Naziv | Kontroler |
|----|-------|-----------|
| UC01 | Detect Activity (Acoustic, Seismic, Radar, LiDAR, Camera) | Controller 1 |
| UC02 | Pre-Process Sensor Data | Controller 1 |
| UC03 | Monitor Zone (UGV/UAV Heading) | Controller 1 |
| UC04 | Fuse Pre-Processed Sensor Data | Controller 2 |
| UC05 | AI Target Identification | Controller 2 |
| UC06 | Estimate Target Trajectory | Controller 2 |
| UC07 | Generate Alarm (Threat Detected) | Controller 2 |
| UC08 | Review Alarm & Target Data | Controller 3 |
| UC09 | Approve / Deny Action | Controller 3 |
| UC10 | Activate Defence System (Wakeup) | Controller 3 |
| UC11 | Deploy UGV/UAV to Intercept Position | Controller 3 |
| UC12 | Assess Action Feedback (Hit/Miss) | Controller 3 |

### Tok sistema

1. Senzori detektuju aktivnost (akustika, seizmika, radar, LiDAR, kamera)
2. Edge procesor pre-procesira podatke
3. UGV/UAV heading monitoring
4. Sensor Fusion + AI identifikacija mete (confidence > 0.85)
5. Procjena trajektorije i tacke presretanja
6. Alarm za operatera
7. Operater odobrava ili odbacuje akciju
8. Odbrambeni sistem wakeup - get ready mode
9. UGV/UAV vozi/leti do pozicije presretanja
10. Meta u dometu - operater potvrdjuje angazovanje
11. Pogodak: misija zavrsena | Promasaj: ponovni proracun trajektorije

> **Dijagram:** diagrams/01_use_case/use_case.puml

---

## 2.2 Class Diagram

Sistem je modelovan kroz klase organizovane u 7 paketa:

**User Management:** Operator

**Command & Control:** CommandCenter, Command, MissionController

**Autonomous Vehicles:** Device (abstract), UAV, UGV

**Sensor Layer:** Sensor (abstract), AcousticSensor, SeismicSensor, RadarSensor, LiDARSensor, CameraSensor, SensorFusionEngine

**Threat Detection & Tracking:** ThreatDetectionModule, TargetTracker, TrajectoryEstimator

**Defence System:** DefenceController, AlarmSystem, DefenceAction, ActionFeedback

**Infrastructure:** EncryptionService, AuditLog

### Kljucne relacije

| Tip | Opis |
|-----|------|
| Nasljedivanje | UAV, UGV nasljeduju Device |
| Nasljedivanje | 5 senzorskih klasa nasljeduju Sensor |
| Agregacija | Device agregira Sensor (1 uredaj, vise senzora) |
| Asocijacija | SensorFusionEngine -> ThreatDetectionModule -> TargetTracker -> TrajectoryEstimator |
| Asocijacija | AlarmSystem -> DefenceController -> DefenceAction -> ActionFeedback |
| Asocijacija | Operator odobrava/odbacuje DefenceAction |
| Zavisnost | ActionFeedback -> TrajectoryEstimator (trigger za ponovni proracun) |

> **Dijagram:** diagrams/02_class/class_diagram.puml

---

## 2.3 Sequence Diagrams

### Scenario 1: Detekcija aktivnosti i pre-procesiranje (Controller 1)

Svi senzori paralelno prikupljaju podatke. Edge procesor filtrira sum i detektuje aktivnost. Akusticki i seizmicki senzori pruZaju rano otkrivanje prije vizuelne potvrde. Pre-procesirana data se salje na Controller 2.

> **Dijagram:** diagrams/03_sequence/seq_sensor_detection.puml

---

### Scenario 2: Fuzija senzora i identifikacija mete (Controller 2)

SensorFusionEngine prima pre-procesirane podatke, primjenjuje Kalman filter i spaja detekcije. ThreatDetection AI/ML model identifikuje metu (confidence > 0.85). TargetTracker inicijalizuje pracenje. TrajectoryEstimator procjenjuje trajektoriju i tacku presretanja. AlarmSystem generise alarm.

> **Dijagram:** diagrams/03_sequence/seq_sensor_fusion.puml

---

### Scenario 3: Odluka operatera i odbrambena akcija (Controller 3)

Operater prima alarm i pregleda podatke o meti. Donosi odluku APPROVE ili DENY. Odobrenje aktivira DefenceController (wakeup, get ready). Sistem bira UGV/UAV i salje ga na poziciju presretanja. Realno-vremensko azuriranje trajektorije. Kad meta dode u domet — dvostepena potvrda operatera — angazovanje.

> **Dijagram:** diagrams/03_sequence/seq_operator_decision.puml

---

### Scenario 4: Feedback petlja — Pogodak / Promasaj

ActionFeedback evaluira rezultat. Pogodak: alarm razrjesan, uredaj povucen, misija zavrsena. Promasaj: TargetTracker azurira podatke, TrajectoryEstimator ponovni proracun (prilagodeni Kalman), nova prijedjena akcija za operatera, ciklus se ponavlja.

> **Dijagram:** diagrams/03_sequence/seq_feedback_loop.puml

---

## 2.4 Activity Diagrams

### Proces 1: Kompletni tok misije

Swim lanes: Controller 1: Sensor Detection | Controller 2: Sensor Fusion | Controller 3: Operator Decision | Audit Log

Kompletni tok od detekcije do feedback-a. Controller 1 detektuje aktivnost, Controller 2 fuzionise i identifikuje metu, Controller 3 operator decide pa deploy. Feedback petlja: pogodak -> zavrseno, promasaj -> ponovni proracun.

> **Dijagram:** diagrams/04_activity/act_mission_workflow.puml

---

### Proces 2: Defence action feedback (Hit / Miss)

Swim lanes: Defence Controller | Target Tracking | Operator | Alarm System | Audit Log

Detaljan tok nakon odbrambene akcije. Pogodak: zatvaranje pracenja, razrjesavanje alarma, povlacenje uredaja. Promasaj: azuriranje pracenja, ponovni proracun, nova akcija. Gubitak mete: TARGET_LOST status.

> **Dijagram:** diagrams/04_activity/act_defence_feedback.puml

---

## 2.5 State Machine Diagrams

### Odbrambeni sistem (Defence System States)

```
[*] -> Monitoring -> ActivityDetected -> TargetConfirmed -> AlarmGenerated
-> DefenceReady (Wakeup -> GetReady -> Deploying)
-> InRange -> Engaged -> MissionAccomplished / Recalculating
```

- Monitoring: kontinuirani nadzor
- ActivityDetected: senzori detektovali, pre-processing, fusion, identifikacija
- TargetConfirmed: AI potvrdio (confidence > 0.85)
- AlarmGenerated: alarm kreiran, ceka odluku operatera
- DefenceReady: wakeup, get ready, deploying
- InRange: uredaj u dometu, ceka finalnu potvrdu
- Engaged: akcija u toku
- MissionAccomplished: pogodak, povlacenje
- Recalculating: promasaj, povratak na AlarmGenerated

> **Dijagram:** diagrams/05_state_machine/sm_defence_system.puml

---

### Device Connection States

```
[*] -> Offline -> Connecting -> Online -> Transmitting / Idle
     LostSignal -> Connecting (retry, max 5)
     Error -> Offline
```

> **Dijagram:** diagrams/05_state_machine/sm_connection_states.puml

---

## 2.6 Component Diagram

| Sloj | Komponente |
|------|------------|
| Presentation Layer | Operator Dashboard UI, Map Viewer, Alarm Console |
| Application Layer | API Gateway, Command Service, Mission Controller, Alarm Service, Defence Controller |
| Processing Layer | Sensor Fusion Engine, Threat Detection, Target Tracking, Trajectory Estimator, AI/ML Engine |
| Device Layer | UAV/UGV Adapters, Device Registry, Edge Processor |
| Infrastructure Layer | Encryption Service, Audit Log, PostgreSQL, TimescaleDB, MongoDB |

> **Dijagram:** diagrams/06_component/component_diagram.puml

---

## 2.7 Deployment Diagram

**Command Center HQ:**

| Cvor | Sadrzaj |
|------|---------|
| Operator Workstation | Dashboard, Alarm Console, Map Viewer |
| Application Server (Docker) | API Gateway, Command/Mission/Alarm/Defence servisi |
| Data Server | PostgreSQL, TimescaleDB, MongoDB |
| AI Processing Server (GPU) | Fusion, Threat Detector, Tracker, Trajectory Estimator |

**Field Operations:**

| Cvor | Sadrzaj |
|------|---------|
| UAV (ARM Embedded Linux) | ROS2, Camera/Radar/LiDAR/Acoustic, Edge Processor (ONNX) |
| UGV (x86 Embedded Linux) | ROS2, Sensor Array/Seismic, Edge Processor (ONNX) |

Komunikacija: HTTPS/WSS (TLS 1.3), gRPC (mTLS), Encrypted Radio (AES-256-GCM).

> **Dijagram:** diagrams/deployment/deployment_diagram.puml

---

## 2.8 Package Diagram

| Paket | Opis |
|-------|------|
| amcs.presentation | UI: dashboard, alarms, map, trajectory overlay |
| amcs.api | API gateway, controllers, DTO |
| amcs.domain | Domenski model: command, devices, sensors, users |
| amcs.processing | Fuzija, detekcija, tracking, trajectory estimation |
| amcs.defence | Defence controller, alarm, actions, feedback |
| amcs.infrastructure | Persistencija, encryption, audit logging |

Zavisnosti: presentation -> api -> domain -> processing -> infrastructure, defence -> processing/domain/infrastructure

> **Dijagram:** diagrams/package/package_diagram.puml

---

## 2.9 Object Diagram

Runtime snapshot — aktivna misija MSN-2026-003 s odbrambenom akcijom u toku:

| Objekat | Tip | Kljucni atributi |
|---------|-----|------------------|
| uav_alpha | UAV | TRANSMITTING, altitude=120m, battery=78.5% |
| ugv_bravo | UGV | DEPLOYING, speed=25km/h, battery=92.3% |
| cam_01 | CameraSensor | 1080p, 30fps, nightVision=true |
| radar_01 | RadarSensor | range=5000m, 77GHz |
| lidar_01 | LiDARSensor | 100K points/sec |
| acoustic_01 | AcousticSensor | 20Hz-20kHz |
| alarm_001 | Alarm | HIGH, OPERATOR_APPROVED, confidence=93% |
| action_001 | DefenceAction | INTERCEPT, DEPLOYING |
| track_001 | Track | velocity=15m/s, heading=180 |
| trajectory_001 | Trajectory | interceptPoint, ETA=14:35:00Z |
| op_jovic | Operator | clearanceLevel=3, ZONE-BRAVO |
| mission_03 | MissionController | ACTIVE |

> **Dijagram:** diagrams/object/object_diagram.puml

---

# III. ZAKLJUCAK

## 3.1 Arhitekturne odluke

Sistem je organizovan oko 3 kontrolera s jasnom separacijom briga: detekcija, obrada i odluka. Edge Computing na UAV/UGV smanjuje bandwidth za ~80%. AI/ML identifikacija meta s ONNX Runtime na edge i GPU serveru. Feedback petlja (promasaj -> ponovni proracun) za iterativni odbrambeni odgovor. Covjek-u-petlji princip s dvostepenom potvrdom operatera.

## 3.2 Buduce aktivnosti

- Backend implementacija (Python/FastAPI, gRPC)
- CI/CD pipeline (napredni alati)
- ML modeli za fuziju i identifikaciju (inteligentni sistemi)
- ROS2 + PoC simulacija (strucna praksa)
- Zavrsni rad: integracija i evaluacija

## 3.3 Literatura

1. Gamma et al. Design Patterns. Addison-Wesley, 1994.
2. Fowler. UML Distilled. 3rd ed., Addison-Wesley, 2003.
3. Bass, Clements, Kazman. Software Architecture in Practice. 3rd ed., 2012.
4. Mahler et al. Multi-Sensor Fusion for Autonomous Vehicle Perception. IEEE ITS, 2021.
5. OMG UML Specification v2.5.1, 2017.

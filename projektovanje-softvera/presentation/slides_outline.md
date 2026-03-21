# PowerPoint Presentation Outline
# Autonomous Multi-Sensor Command System for Unmanned Battle Zones

**Predmet:** Projektovanje softvera
**Broj slajdova:** 14

---

## Slajd 1 - Naslovna strana
- **Naslov:** Autonomous Multi-Sensor Command System for Unmanned Battle Zones
- **Podnaslov:** Projektovanje softvera — Softverska arhitektura i UML modelovanje
- **Autor:** [Ime i Prezime] | Mart 2026

---

## Slajd 2 - Problem i motivacija
- **Naslov:** Zasto AMCS?
- 5 tipova senzora: akustika, seizmika, radar, LiDAR, kamera
- Klasicni sistemi: fragmentirani podaci, visoka latencija, nekoordinisan odgovor
- Potreba: real-time detekcija + AI identifikacija + koordinisan odbrambeni odgovor

---

## Slajd 3 - 3 kontrolera
- **Naslov:** AMCS — 3 kontrolera za kompletan tok misije
- Controller 1: Sensor Detection & Pre-Processing (5 senzora + edge)
- Controller 2: Sensor Fusion & Alarm (AI identifikacija + trajektorija + alarm)
- Controller 3: Operator Decision Approve/Deny (covjek-u-petlji + feedback)
- Quality Attributes: latencija < 200ms, uptime 99.9%, 50+ uredaja

---

## Slajd 4 - Use Case Diagram
- **Naslov:** 12 use case-ova u 3 kontrolera
- 1 akter: Operator
- UC01-UC03: detekcija | UC04-UC07: fuzija+alarm | UC08-UC12: odluka+feedback
- Feedback petlja: UC12 -> UC06 (miss -> recalculate)
- Insert: diagrams/01_use_case/use_case.puml

---

## Slajd 5 - Class Diagram
- **Naslov:** Domenski model — 7 paketa
- User Management: Operator
- Sensor Layer: 5 senzorskih klasa + SensorFusionEngine
- Threat/Tracking: ThreatDetectionModule, TargetTracker, TrajectoryEstimator
- Defence System: DefenceController, AlarmSystem, DefenceAction, ActionFeedback
- Insert: diagrams/02_class/class_diagram.puml

---

## Slajd 6 - Sequence: Sensor Detection (Controller 1)
- **Naslov:** Detekcija aktivnosti — 5 senzora paralelno
- Tok: Acoustic+Seismic+Radar+LiDAR+Camera -> Edge Processor -> Controller 2
- Akusticki/seizmicki senzori: rano otkrivanje, edge smanjuje bandwidth ~80%
- Insert: diagrams/03_sequence/seq_sensor_detection.puml

---

## Slajd 7 - Sequence: Sensor Fusion (Controller 2)
- **Naslov:** Od fuzije do alarma — AI identifikacija mete
- Tok: Fusion (Kalman) -> AI Inference -> Target Tracking -> Trajectory -> Alarm
- Confidence prag: 0.85, proracun tacke presretanja
- Insert: diagrams/03_sequence/seq_sensor_fusion.puml

---

## Slajd 8 - Sequence: Operator Decision (Controller 3)
- **Naslov:** Dvostepena potvrda operatera
- Tok: Alarm -> Review -> Approve -> Wakeup -> Deploy -> In Range -> Confirm -> Engage
- Dvostepena potvrda: approve + confirm engagement (covjek-u-petlji)
- Insert: diagrams/03_sequence/seq_operator_decision.puml

---

## Slajd 9 - Sequence: Feedback Loop
- **Naslov:** Pogodak ili promasaj — feedback petlja
- Hit: Mission Accomplished | Miss: Recalculate -> New Trajectory -> Re-approve
- Kalman korekcija pri promasaju, iterativni ciklus do neutralizacije
- Insert: diagrams/03_sequence/seq_feedback_loop.puml

---

## Slajd 10 - Activity: Mission Workflow
- **Naslov:** Kompletan tok misije — od detekcije do feedback-a
- Swim lanes: Controller 1 | Controller 2 | Controller 3 | Audit Log
- Decision points: approve/deny, hit/miss
- Insert: diagrams/04_activity/act_mission_workflow.puml

---

## Slajd 11 - State Machine: Defence System & Connection
- **Naslov:** Stanja kljucnih objekata sistema
- Lijeva strana: Defence System (Monitoring -> Activity -> Target -> Alarm -> Deploy -> Engage -> Hit/Miss)
- Desna strana: Device Connection (Offline -> Connecting -> Online -> Transmitting)
- Insert: sm_defence_system.puml + sm_connection_states.puml

---

## Slajd 12 - Component Diagram
- **Naslov:** Arhitektura komponenti — 5 slojeva
- Presentation -> Application -> Processing -> Device -> Infrastructure
- Defence Controller Service kao kljucni servis, Edge Processor u Device Layer
- Insert: diagrams/06_component/component_diagram.puml

---

## Slajd 13 - Deployment + Package + Object
- **Naslov:** Infrastruktura, organizacija koda i runtime
- HQ: App Server, Data Server, AI GPU Server
- Field: UAV (5 senzora + edge) + UGV (4 senzora + edge)
- Object: aktivna misija MSN-2026-003 s odbrambenom akcijom u toku

---

## Slajd 14 - Zakljucak
- **Naslov:** Postignuto i sledeci koraci
- 3-kontroler arhitektura: Detection -> Fusion -> Decision
- Kompletna feedback petlja (hit/miss -> recalculate)
- 5 senzora, AI/ML identifikacija, trajectory estimation, covjek-u-petlji
- Naredni koraci: backend, ML modeli, CI/CD, ROS2 simulacija

---

## Napomene
- Trajanje: 15-20 minuta
- Format: 16:9, tamna tema (tamno plava + siva + narandzasta)
- Fontovi: Roboto / Montserrat
- Dijagrami: eksportovati iz PlantUML kao SVG
- .vpp fajl: kreirati u Visual Paradigm

# Projektovanje Softvera — AMCS

**Predmet:** Projektovanje softvera
**Tema projekta:** Autonomous Multi-Sensor Command System for Unmanned Battle Zones (Army)
**Nivo:** Master studije — Softversko inženjerstvo

---

## O projektu

Ovaj folder pokriva isporuke za predmet **Projektovanje softvera**. Fokus je na softverskoj arhitekturi sistema za autonomno upravljanje borbenom zonom kroz UML modelovanje i dokumentaciju.

Sistem je organizovan kroz **3 kontrolera**:
1. **Controller 1 - Sensor Detection & Pre-Processing:** Detekcija aktivnosti (akustika, seizmika, radar, LiDAR, kamera) i edge pre-procesiranje
2. **Controller 2 - Sensor Fusion & Alarm System:** Fuzija podataka, AI identifikacija meta, procjena trajektorije, generisanje alarma
3. **Controller 3 - Operator Decision (Approve/Deny):** Operater pregleda, odobrava/odbacuje akciju, feedback petlja (hit/miss)

---

## Struktura foldera

```
projektovanje-softvera/
|-- README.md
|
|-- docs/
|   |-- AMCS_Projektovanje_Softvera.md
|
|-- diagrams/
|   |-- 01_use_case/
|   |   |-- use_case.puml
|   |-- 02_class/
|   |   |-- class_diagram.puml
|   |-- 03_sequence/
|   |   |-- seq_sensor_detection.puml
|   |   |-- seq_sensor_fusion.puml
|   |   |-- seq_operator_decision.puml
|   |   |-- seq_feedback_loop.puml
|   |-- 04_activity/
|   |   |-- act_mission_workflow.puml
|   |   |-- act_defence_feedback.puml
|   |-- 05_state_machine/
|   |   |-- sm_defence_system.puml
|   |   |-- sm_connection_states.puml
|   |-- 06_component/
|   |   |-- component_diagram.puml
|   |-- deployment/
|   |   |-- deployment_diagram.puml
|   |-- package/
|   |   |-- package_diagram.puml
|   |-- object/
|       |-- object_diagram.puml
|
|-- presentation/
    |-- slides_outline.md
```

---

## Isporuke

| # | Artifact | Format | Status |
|---|----------|--------|--------|
| 1 | Dokument sa UML dijagramima | Markdown | done |
| 2 | Use Case Diagram (12 UC, 3 kontrolera) | PlantUML .puml | done |
| 3 | Class Diagram (7 paketa) | PlantUML .puml | done |
| 4 | Sequence Diagrams (4 scenarija) | PlantUML .puml | done |
| 5 | Activity Diagrams (2 procesa) | PlantUML .puml | done |
| 6 | State Machine Diagrams (2 objekta) | PlantUML .puml | done |
| 7 | Component Diagram | PlantUML .puml | done |
| 8 | Deployment Diagram | PlantUML .puml | done |
| 9 | Package Diagram | PlantUML .puml | done |
| 10 | Object Diagram | PlantUML .puml | done |
| 11 | PowerPoint outline | Markdown outline | done |
| 12 | Visual Paradigm .vpp fajl | Export iz VP | TODO |

---

## Kako renderovati dijagrame

### Opcija 1 - VS Code
Instaliraj ekstenziju PlantUML (jebbs.plantuml), zatim Alt+D za preview.

### Opcija 2 - Online
Idi na https://www.plantuml.com/plantuml/uml/ i zalijepi sadrzaj .puml fajla.

### Opcija 3 - CLI (lokalno)
```bash
java -jar plantuml.jar diagrams/**/*.puml
```

---

## UML Dijagrami - pregled

| Dijagram | Fajl | Opis |
|----------|------|------|
| Use Case | 01_use_case/use_case.puml | 1 akter (Operator), 12 use case-ova, 3 kontrolera |
| Class | 02_class/class_diagram.puml | 7 paketa, 5 senzora, defence system, feedback petlja |
| Seq: Sensor Detection | 03_sequence/seq_sensor_detection.puml | Controller 1: 5 senzora + edge pre-processing |
| Seq: Sensor Fusion | 03_sequence/seq_sensor_fusion.puml | Controller 2: Fusion + AI + trajectory + alarm |
| Seq: Operator Decision | 03_sequence/seq_operator_decision.puml | Controller 3: Approve/Deny + deploy + engage |
| Seq: Feedback Loop | 03_sequence/seq_feedback_loop.puml | Hit/Miss - recalculate - re-approve |
| Activity: Mission | 04_activity/act_mission_workflow.puml | Kompletni tok misije (3 kontrolera) |
| Activity: Feedback | 04_activity/act_defence_feedback.puml | Defence action feedback (hit/miss) |
| State: Defence | 05_state_machine/sm_defence_system.puml | Stanja odbrambenog sistema |
| State: Connection | 05_state_machine/sm_connection_states.puml | Stanja konekcije uredaja |
| Component | 06_component/component_diagram.puml | 5-slojna arhitektura komponenti |
| Deployment | deployment/deployment_diagram.puml | Fizicka infrastruktura (HQ + Field) |
| Package | package/package_diagram.puml | 7 paketa sa zavisnostima |
| Object | object/object_diagram.puml | Runtime instance misije MSN-2026-003 |

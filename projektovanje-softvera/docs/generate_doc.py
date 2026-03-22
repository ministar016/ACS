from docx import Document
from docx.shared import Pt, RGBColor, Inches, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "ispit.docx")

doc = Document()

# ── Page margins ──────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Cm(2.5)
    section.bottom_margin = Cm(2.5)
    section.left_margin   = Cm(3)
    section.right_margin  = Cm(2)

# ── Style helpers ─────────────────────────────────────────────
def style_heading(para, level=1):
    run = para.runs[0] if para.runs else para.add_run(para.text)
    sizes = {1: 18, 2: 15, 3: 13}
    colors = {1: RGBColor(0x1A, 0x2F, 0x45),
              2: RGBColor(0x2E, 0x4E, 0x6E),
              3: RGBColor(0x2C, 0x5F, 0x8B)}
    run.bold = True
    run.font.size = Pt(sizes.get(level, 13))
    run.font.color.rgb = colors.get(level, RGBColor(0, 0, 0))

def add_heading(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if p.runs:
        p.runs[0].font.color.rgb = {
            1: RGBColor(0x1A, 0x2F, 0x45),
            2: RGBColor(0x1A, 0x52, 0x76),
            3: RGBColor(0x1F, 0x61, 0x8D),
        }.get(level, RGBColor(0,0,0))
        p.runs[0].font.size = Pt({1:18, 2:15, 3:13}.get(level, 12))
    return p

def add_para(doc, text, bold=False, italic=False, size=11, space_after=6):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    run = p.add_run(text)
    run.bold = bold
    run.italic = italic
    run.font.size = Pt(size)
    return p

def add_bullet(doc, text, size=11):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_after = Pt(3)
    run = p.add_run(text)
    run.font.size = Pt(size)
    return p

def add_table(doc, headers, rows, col_widths=None):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = 'Table Grid'
    # header row
    hdr = table.rows[0]
    for i, h in enumerate(headers):
        cell = hdr.cells[i]
        cell.text = h
        cell.paragraphs[0].runs[0].bold = True
        cell.paragraphs[0].runs[0].font.size = Pt(10)
        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement('w:shd')
        shd.set(qn('w:val'), 'clear')
        shd.set(qn('w:color'), 'auto')
        shd.set(qn('w:fill'), '2471A3')
        tcPr.append(shd)
        for run in cell.paragraphs[0].runs:
            run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
    # data rows
    for ri, row_data in enumerate(rows):
        row = table.rows[ri + 1]
        for ci, val in enumerate(row_data):
            cell = row.cells[ci]
            cell.text = str(val)
            cell.paragraphs[0].runs[0].font.size = Pt(10)
            if ri % 2 == 0:
                tc = cell._tc
                tcPr = tc.get_or_add_tcPr()
                shd = OxmlElement('w:shd')
                shd.set(qn('w:val'), 'clear')
                shd.set(qn('w:color'), 'auto')
                shd.set(qn('w:fill'), 'EAF4FB')
                tcPr.append(shd)
    if col_widths:
        for row in table.rows:
            for i, cell in enumerate(row.cells):
                if i < len(col_widths):
                    cell.width = Cm(col_widths[i])
    return table

def page_break(doc):
    doc.add_page_break()

PNG_DIR = os.path.join(os.path.dirname(__file__), "..", "diagrams", "png")

def add_diagram_image(doc, filename, width_cm=15, caption=None):
    img_path = os.path.join(PNG_DIR, filename)
    if os.path.exists(img_path):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run()
        run.add_picture(img_path, width=Cm(width_cm))
        if caption:
            cap = doc.add_paragraph(caption)
            cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
            cap.paragraph_format.space_after = Pt(6)
            if cap.runs:
                cap.runs[0].font.size = Pt(9)
                cap.runs[0].italic = True

# ══════════════════════════════════════════════════════════════
# NASLOVNICA
# ══════════════════════════════════════════════════════════════
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(60)
run = p.add_run("AUTONOMOUS MULTI-SENSOR COMMAND SYSTEM")
run.bold = True
run.font.size = Pt(20)
run.font.color.rgb = RGBColor(0x1A, 0x2F, 0x45)

p2 = doc.add_paragraph()
p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
run2 = p2.add_run("For Unmanned Battle Zones")
run2.font.size = Pt(15)
run2.italic = True
run2.font.color.rgb = RGBColor(0x2E, 0x4E, 0x6E)

doc.add_paragraph()
meta = [
    ("Predmet:", "Projektovanje softvera"),
    ("Studijski program:", "Master studije — Softversko inzenjerstvo"),
    ("Akademska godina:", "2025/2026"),
    ("Datum:", "Mart 2026"),
]
for label, val in meta:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = p.add_run(f"{label} ")
    r1.bold = True
    r1.font.size = Pt(11)
    r2 = p.add_run(val)
    r2.font.size = Pt(11)

page_break(doc)

# ══════════════════════════════════════════════════════════════
# I. UVOD
# ══════════════════════════════════════════════════════════════
add_heading(doc, "I. UVOD", level=1)

add_heading(doc, "1.1 Opis problema", level=2)
add_para(doc,
    "Savremeno borbeno okruzenje karakterise izuzetna dinamicnost, heterogenost prijetnji i "
    "neophodnost donosenja odluka u realnom vremenu. Uvodjenje autonomnih sistema — UAV (bespilotne "
    "letjelice) i UGV (bespilotna kopnena vozila) — omogucava operativan pristup opasnim terenima "
    "bez izlaganja ljudskog osoblja, ali ovi sistemi generisu ogromne kolicine heterogenih senzorskih "
    "podataka koje je tesko integrisati u realnom vremenu i na osnovu kojih treba donositi pouzdane "
    "odluke u vremenski kriticnim situacijama.")

add_para(doc, "Kljucni problemi koje sistem mora rijesiti:", bold=True)
bullets_problemi = [
    "Fragmentiranost podataka: svaki senzor (akustika, seizmika, radar, LiDAR, kamera) daje parcijalni pogled na situaciju na terenu",
    "Latencija: obrada podataka na centralnom serveru uvodi kasnjenja koja mogu biti kriticna u borbenim uslovima",
    "Identifikacija meta: potreba za AI/ML modelima koji pouzdano identifikuju prijetnje uz minimalan broj laznih uzbuna",
    "Procjena trajektorije: pracenje mete u realnom vremenu i predvidjanje pozicije za presretanje",
    "Odluka operatera: zastita principa covjek-u-petlji (Human-in-the-Loop) — operator mora odobriti svaku odbrambenu akciju",
]
for b in bullets_problemi:
    add_bullet(doc, b)

add_heading(doc, "1.2 Cilj sistema — 3 kontrolera", level=2)
add_para(doc,
    "Autonomous Multi-Sensor Command System (AMCS) projektovan je kao troslojna arhitektura "
    "temeljena na tri medjusobno povezana kontrolera, od kojih svaki ima jasno definisanu odgovornost:")

add_para(doc, "Controller 1 — Sensor Detection & Pre-Processing", bold=True)
add_para(doc,
    "Senzori (akustika, seizmika, radar, LiDAR, kamera) detektuju aktivnost u monitoriranim zonama. "
    "Edge procesor vrsi preliminarnu obradu i filtriranje suma direktno na UAV/UGV platformama, "
    "cime se smanjuje propusni opseg prema centralnom serveru za oko 80%. Sistem prati kretanje "
    "UGV/UAV jedinica i salje pre-procesirane podatke na Controller 2.")

add_para(doc, "Controller 2 — Sensor Fusion & Alarm System", bold=True)
add_para(doc,
    "SensorFusionEngine prima pre-procesirane podatke i primjenjuje Kalman filter za fuziju "
    "heterogenih detekcija. AI/ML model (ThreatDetectionModule) identifikuje metu i procjenjuje "
    "nivo prijetnje. TargetTracker inicijalizuje i odrzava pracenje mete. TrajectoryEstimator "
    "procjenjuje trajektoriju i tacku presretanja. AlarmSystem generise alarm za operatera "
    "kada je pouzdan identifikovana meta (confidence > 0.85).")

add_para(doc, "Controller 3 — Operator Decision (Approve/Deny)", bold=True)
add_para(doc,
    "Operater pregleda alarm i podatke o meti, te donosi odluku APPROVE ili DENY. Odobrenje "
    "aktivira DefenceController (wakeup, get-ready, deploy). Sistem bira optimalni UAV/UGV, "
    "salje ga na poziciju presretanja uz realno-vremensko azuriranje trajektorije. Kad meta "
    "udje u domet, dvostepena potvrda operatera aktivira angazovanje. Feedback petlja evaluira "
    "rezultat: pogodak zatvara misiju, promasaj pokrece ponovni proracun trajektorije.")

add_heading(doc, "1.3 Scope", level=2)
add_para(doc, "U scopu sistema:", bold=True)
in_scope = [
    "Softverska arhitektura zasnovana na 3 kontrolera",
    "UML modelovanje kompletnog sistema (10 dijagram tipova)",
    "Obrada i fuzija heterogenih senzorskih podataka",
    "AI/ML identifikacija i klasifikacija prijetnji",
    "Procjena trajektorije i tacke presretanja (Kalman filter)",
    "Sistem alarma i upravljanje odbrambenim odgovorom",
    "Koordinacija autonomnih vozila (UAV/UGV) za presretanje",
    "Operator decision interface s feedback petljom",
]
for item in in_scope:
    add_bullet(doc, item)

add_para(doc, "Van scopa:", bold=True)
out_scope = [
    "Firmware za UAV/UGV hardver",
    "Fizicki hardver i elektronika senzora",
    "ML model trening (pretpostavljamo pre-trenirane modele)",
    "Implementacija korisnickog interfejsa (UI)",
    "Administratorski panel i upravljanje korisnicima",
]
for item in out_scope:
    add_bullet(doc, item)

add_para(doc, "Quality Attributes:", bold=True)
add_table(doc,
    ["Atribut", "Zahtjev"],
    [
        ["Latencija", "< 200ms od detekcije do prikaza operateru"],
        ["Raspolozivost", "99.9% uptime (manje od 8.7h godisnjeg downtime-a)"],
        ["Skalabilnost", "50+ simultanih UAV/UGV jedinica"],
        ["Pouzdanost", "Automatski failover, redundantne komunikacione putanje"],
        ["Sigurnost", "AES-256-GCM enkripcija, mTLS, audit logging"],
    ],
    col_widths=[5, 11]
)

page_break(doc)

# ══════════════════════════════════════════════════════════════
# II. UML DIJAGRAMI
# ══════════════════════════════════════════════════════════════
add_heading(doc, "II. UML DIJAGRAMI", level=1)

# ── 2.1 Use Case ──────────────────────────────────────────────
add_heading(doc, "2.1 Use Case Diagram", level=2)
add_para(doc,
    "Use Case dijagram prikazuje funkcionalne zahtjeve sistema iz perspektive aktera. "
    "Identifikovana su tri glavna aktera i 12 use case-ova rasporedjenih po kontrolerima.")

add_heading(doc, "Akteri", level=3)
add_table(doc,
    ["Akter", "Opis"],
    [
        ["Operator", "Vojni operater koji prati zonu, pregleda alarme, odobrava ili odbacuje odbrambene akcije i procjenjuje rezultate"],
        ["Admin", "Sistemski administrator odgovoran za konfiguraciju sistema, upravljanje korisnickim nalozima i pracenje sistemskog zdravlja"],
        ["Security Analyst", "Analiticar sigurnosti koji pregledava audit logove, analizira obrasce prijetnji i optimizuje pravila detekcije"],
    ],
    col_widths=[4, 12]
)

doc.add_paragraph()
add_heading(doc, "Use Case-ovi", level=3)
add_table(doc,
    ["ID", "Naziv", "Akter", "Kontroler"],
    [
        ["UC01", "Detect Activity (Acoustic, Seismic, Radar, LiDAR, Camera)", "Sistem", "Controller 1"],
        ["UC02", "Pre-Process Sensor Data", "Sistem", "Controller 1"],
        ["UC03", "Monitor Zone (UGV/UAV Heading)", "Operator", "Controller 1"],
        ["UC04", "Fuse Pre-Processed Sensor Data", "Sistem", "Controller 2"],
        ["UC05", "AI Target Identification", "Sistem", "Controller 2"],
        ["UC06", "Estimate Target Trajectory", "Sistem", "Controller 2"],
        ["UC07", "Generate Alarm (Threat Detected)", "Sistem", "Controller 2"],
        ["UC08", "Review Alarm & Target Data", "Operator", "Controller 3"],
        ["UC09", "Approve / Deny Action", "Operator", "Controller 3"],
        ["UC10", "Activate Defence System (Wakeup)", "Sistem", "Controller 3"],
        ["UC11", "Deploy UGV/UAV to Intercept Position", "Sistem", "Controller 3"],
        ["UC12", "Assess Action Feedback (Hit/Miss)", "Operator", "Controller 3"],
    ],
    col_widths=[1.5, 7, 3, 4]
)

doc.add_paragraph()
add_para(doc, "Tok sistema (sekvencijalni redosljed):", bold=True)
tok_sistema = [
    "Senzori detektuju aktivnost (akustika, seizmika, radar, LiDAR, kamera)",
    "Edge procesor pre-procesira podatke i filtrira sum",
    "UGV/UAV heading monitoring — pracenje pozicija autonomnih vozila",
    "Sensor Fusion + AI identifikacija mete (confidence > 0.85)",
    "Procjena trajektorije i tacke presretanja",
    "Alarm generisan — operater prima obavjestenje",
    "Operater odobrava ili odbacuje akciju (APPROVE/DENY)",
    "Odbrambeni sistem wakeup — ulazak u Get Ready mod",
    "UGV/UAV vozi/leti do pozicije presretanja",
    "Meta u dometu — operater potvrdjuje angazovanje",
    "Pogodak: misija zavrsena | Promasaj: ponovni proracun trajektorije",
]
for i, item in enumerate(tok_sistema, 1):
    p = doc.add_paragraph(style='List Number')
    p.paragraph_format.space_after = Pt(3)
    run = p.add_run(item)
    run.font.size = Pt(11)

doc.add_paragraph()
add_diagram_image(doc, "use_case.png", width_cm=14,
                  caption="Slika 1: Use Case Diagram — AMCS (UC01–UC12)")

page_break(doc)

# ── 2.2 Class Diagram ─────────────────────────────────────────
add_heading(doc, "2.2 Class Diagram", level=2)
add_para(doc,
    "Class dijagram modeluje staticki strukturni pogled na sistem. Sistem je organizovan u "
    "7 paketa koji sadrze ukupno 20 klasa sa svim atributima, metodama i medjusobnim relacijama.")

add_heading(doc, "Paketi i klase", level=3)
paketi = [
    ("User Management", ["Operator"]),
    ("Command & Control", ["CommandCenter", "Command", "MissionController"]),
    ("Autonomous Vehicles", ["Device (abstract)", "UAV", "UGV"]),
    ("Sensor Layer", ["Sensor (abstract)", "AcousticSensor", "SeismicSensor", "RadarSensor", "LiDARSensor", "CameraSensor", "SensorFusionEngine"]),
    ("Threat Detection & Tracking", ["ThreatDetectionModule", "TargetTracker", "TrajectoryEstimator"]),
    ("Defence System", ["DefenceController", "AlarmSystem", "DefenceAction", "ActionFeedback"]),
    ("Infrastructure", ["EncryptionService", "AuditLog"]),
]
add_table(doc,
    ["Paket", "Klase"],
    [[p, ", ".join(c)] for p, c in paketi],
    col_widths=[5, 11]
)

doc.add_paragraph()
add_heading(doc, "Kljucne klase — atributi i metode", level=3)
klase_detalji = [
    ("Operator", 
     "operatorId: String, username: String, assignedZone: String, clearanceLevel: Integer, lastLogin: DateTime",
     "login(credentials): AuthToken, logout(): void, monitorZone(): ZoneStatus, reviewAlarm(alarm): AlarmDetails, approveAction(action): Boolean, denyAction(action): Boolean, assessFeedback(feedback): Decision"),
    ("Device (abstract)",
     "deviceId: String, type: DeviceType, role: DeviceRole, status: DeviceStatus, location: GeoCoordinate, batteryLevel: Float",
     "connect(): Boolean, disconnect(): void, sendTelemetry(): TelemetryData, receiveCommand(cmd): void"),
    ("UAV",
     "altitude: Float, speed: Float, heading: Float",
     "takeOff(altitude): void, land(): void, setWaypoints(waypoints): void, flyToInterceptPosition(pos): void"),
    ("UGV",
     "terrainMode: TerrainMode, speed: Float, obstacleDetected: Boolean",
     "navigate(destination): void, stop(): void, driveToInterceptPosition(pos): void"),
    ("SensorFusionEngine",
     "sensors: List<Sensor>, fusionAlgorithm: FusionAlgorithm",
     "fuseData(dataSet): FusedData, detectAnomalies(data): FusedData, applyKalmanFilter(data): SensorData"),
    ("ThreatDetectionModule",
     "rules: List<DetectionRule>, mlModel: ThreatModel",
     "analyzeData(data): List<Threat>, classifyThreat(threat): ThreatLevel, identifyTarget(data): TargetIdentification"),
    ("TrajectoryEstimator",
     "kalmanFilter: KalmanFilter",
     "estimateTrajectory(track): Trajectory, predictInterceptPoint(traj): GeoCoordinate, recalculateTrajectory(track, feedback): Trajectory"),
    ("DefenceController",
     "status: DefenceStatus, assignedDevices: List<Device>",
     "wakeup(): void, getReady(target): void, deployToIntercept(device, position): void, executeAction(action): ActionResult, standDown(): void"),
]
add_table(doc,
    ["Klasa", "Atributi", "Metode"],
    klase_detalji,
    col_widths=[3.5, 6.5, 6]
)

doc.add_paragraph()
add_heading(doc, "Relacije", level=3)
add_table(doc,
    ["Tip relacije", "Opis"],
    [
        ["Nasljedivanje (extends)", "UAV, UGV nasljeduju apstraktnu klasu Device"],
        ["Nasljedivanje (extends)", "AcousticSensor, SeismicSensor, RadarSensor, LiDARSensor, CameraSensor nasljeduju apstraktnu klasu Sensor"],
        ["Agregacija (1..*)", "Device agregira Sensor — jedan uredaj moze imati vise senzora"],
        ["Asocijacija (->)", "SensorFusionEngine → ThreatDetectionModule → TargetTracker → TrajectoryEstimator"],
        ["Asocijacija (->)", "AlarmSystem → DefenceController → DefenceAction → ActionFeedback"],
        ["Asocijacija (->)", "Operator odobrava/odbacuje DefenceAction (dvostepena autorizacija)"],
        ["Zavisnost (..>)", "ActionFeedback → TrajectoryEstimator (promasaj trigguje ponovni proracun)"],
        ["Koristenje", "EncryptionService koriste Command i CommandCenter za enkripciju komunikacije"],
        ["Koristenje", "AuditLog koriste svi servisi za belezenje kriticnih dogadjaja"],
    ],
    col_widths=[4.5, 11.5]
)

doc.add_paragraph()
add_diagram_image(doc, "class_diagram.png", width_cm=15,
                  caption="Slika 2: Class Diagram — AMCS (20 klasa, 7 paketa)")

page_break(doc)

# ── 2.3 Sequence Diagrams ─────────────────────────────────────
add_heading(doc, "2.3 Sequence Diagrams", level=2)
add_para(doc,
    "Sequence dijagrami modeluju dinamicke interakcije izmedju objekata u sistemu tokom kljucnih scenarija. "
    "Definisana su 4 glavna scenarija koji pokrivaju kompletan zivotni ciklus prijetnje.")

for i, (title, desc, actors, steps) in enumerate([
    (
        "Scenario 1: Detekcija aktivnosti i pre-procesiranje (Controller 1)",
        "Ovaj scenario opisuje paralelno prikupljanje podataka sa svih senzora, "
        "edge pre-procesiranje na UAV/UGV platformi i slanje na centralni server.",
        ["AcousticSensor", "SeismicSensor", "RadarSensor", "LiDARSensor", "CameraSensor", "EdgeProcessor", "Controller2"],
        [
            "AcousticSensor i SeismicSensor detektuju signal (rano otkrivanje — zvuk/vibracije)",
            "RadarSensor mjeri udaljenost i velocitet mete",
            "LiDARSensor generise 3D point cloud okoline",
            "CameraSensor hvata video frame i vrsi detekciju objekata",
            "EdgeProcessor prima raw podatke od svih senzora paralelno",
            "EdgeProcessor filtrira sum, normalizuje podatke i vrsi prvu klasifikaciju",
            "EdgeProcessor salje pre-procesirane SensorData pakete Controller2",
        ]
    ),
    (
        "Scenario 2: Fuzija senzora i identifikacija mete (Controller 2)",
        "Ovaj scenario opisuje primjenu Kalman filtera, AI/ML identifikaciju i generisanje alarma.",
        ["SensorFusionEngine", "ThreatDetectionModule", "TargetTracker", "TrajectoryEstimator", "AlarmSystem", "Operator"],
        [
            "SensorFusionEngine prima pre-procesirane pakete od Controller1",
            "Primjena Kalman filtera za fuziju heterogenih mjerenja",
            "Detekcija anomalija i agregacija detekcija u jedinstveni FusedData objekat",
            "ThreatDetectionModule analizira FusedData koristeci ML model",
            "Identifikacija mete — ako confidence > 0.85, klasifikacija prijetnje",
            "TargetTracker inicijalizuje track objekat za pracenje mete",
            "TrajectoryEstimator procjenjuje trajektoriju i izracunava tacku presretanja",
            "AlarmSystem generise Alarm objekat (HIGH priority) i salje obavjestenje operateru",
        ]
    ),
    (
        "Scenario 3: Odluka operatera i odbrambena akcija (Controller 3)",
        "Ovaj scenario opisuje pregled alarma, donošenje odluke i koordinaciju odbrambene akcije.",
        ["Operator", "AlarmSystem", "DefenceController", "MissionController", "UAV/UGV", "TrajectoryEstimator"],
        [
            "Operator prima alarm i ucitava detalje o meti (lokacija, brzina, heading, threat level)",
            "Operator pregleda procijenjenu trajektoriju i tacku presretanja na Map Viewer-u",
            "Operator donosi odluku: APPROVE ili DENY",
            "Kod APPROVE: DefenceController prima nalog za aktivaciju",
            "DefenceController: wakeup() → getReady(target) → selectOptimalDevice()",
            "MissionController dodjeljuje UAV/UGV i generise misiju presretanja",
            "UAV/UGV prima waypoints i krece prema poziciji presretanja",
            "TrajectoryEstimator kontinuirano azurira procjenu dok se uredaj priblizava",
            "Kad meta udje u domet — drugi confirmation od operatera za angazovanje",
            "DefenceController salje executeAction() komandu — angazovanje",
        ]
    ),
    (
        "Scenario 4: Feedback petlja — Pogodak / Promasaj",
        "Ovaj scenario opisuje evaluaciju rezultata akcije i feedback petlju za iterativni odbrambeni odgovor.",
        ["ActionFeedback", "TargetTracker", "TrajectoryEstimator", "AlarmSystem", "DefenceController", "AuditLog"],
        [
            "ActionFeedback prima rezultat angazovanja od senzora na terenu",
            "POGODAK (HIT): TargetTracker.lostTrack() — pracenje zatvoreno",
            "POGODAK: AlarmSystem.resolveAlarm() — alarm razrjesen",
            "POGODAK: DefenceController.standDown() — uredaj povucen, misija zavrsena",
            "POGODAK: AuditLog belezi MISSION_ACCOMPLISHED s vremenskim pecat",
            "PROMASAJ (MISS): ActionFeedback trigguije TrajectoryEstimator.recalculate()",
            "PROMASAJ: TargetTracker.updateTrack() — azuriranje podataka o meti",
            "PROMASAJ: TrajectoryEstimator primjenjuje prilagodjeni Kalman s novim podacima",
            "PROMASAJ: Nova DefenceAction predlozena operateru — ciklus se ponavlja",
            "GUBITAK METE: TargetTracker.lostTrack() — status TARGET_LOST, alarm suspendovan",
        ]
    ),
], 1):
    add_heading(doc, title, level=3)
    add_para(doc, desc)
    add_para(doc, "Ucesnici: " + ", ".join(actors), italic=True, size=10)
    for step in steps:
        add_bullet(doc, step)
    _seq_imgs = [
        ("seq_sensor_detection.png", "Slika 3: Sekvencijalni dijagram 1 — Detekcija aktivnosti (Controller 1)"),
        ("seq_sensor_fusion.png",    "Slika 4: Sekvencijalni dijagram 2 — Fuzija senzora i identifikacija mete (Controller 2)"),
        ("seq_operator_decision.png","Slika 5: Sekvencijalni dijagram 3 — Odluka operatera i odbrambena akcija (Controller 3)"),
        ("seq_feedback_loop.png",    "Slika 6: Sekvencijalni dijagram 4 — Feedback petlja (Hit / Miss)"),
    ]
    add_diagram_image(doc, _seq_imgs[i-1][0], width_cm=14, caption=_seq_imgs[i-1][1])
    if i < 4:
        doc.add_paragraph()

page_break(doc)

# ── 2.4 Activity Diagrams ─────────────────────────────────────
add_heading(doc, "2.4 Activity Diagrams", level=2)
add_para(doc,
    "Activity dijagrami modeluju tok kontrole i podataka kroz procese sistema. "
    "Koriste swim lanes za jasno prikazivanje odgovornosti svake komponente.")

add_heading(doc, "Proces 1: Kompletni tok misije (Mission Workflow)", level=3)
add_para(doc, "Swim lanes: Controller 1: Sensor Detection | Controller 2: Sensor Fusion | Controller 3: Operator Decision | Audit Log")
doc.add_paragraph()
add_table(doc,
    ["Swim Lane", "Aktivnosti"],
    [
        ["Controller 1\n(Sensor Detection)", "Start → Detect Activity → Pre-Process Data → Monitor Zone → [Fork] → Send to Controller 2"],
        ["Controller 2\n(Sensor Fusion)", "Receive Data → Apply Kalman Filter → AI Identify Target → [Decision: confidence > 0.85?] → YES: Estimate Trajectory → Generate Alarm | NO: Continue monitoring"],
        ["Controller 3\n(Operator Decision)", "Receive Alarm → Review Target Data → [Decision: APPROVE/DENY] → APPROVE: Wakeup Defence → Deploy → In Range? → Engage | DENY: Log & Resume"],
        ["Audit Log", "Log Detection Event → Log Alarm Generated → Log Operator Decision → Log Action Result → [Decision: HIT/MISS] → HIT: Log Mission Complete | MISS: Log Recalculate"],
    ],
    col_widths=[4, 12]
)

add_diagram_image(doc, "act_mission_workflow.png", width_cm=14,
                  caption="Slika 7: Activity Diagram 1 — Kompletan tok misije (swim lanes: 4 kontrolera)")

doc.add_paragraph()
add_heading(doc, "Proces 2: Defence Action Feedback (Hit / Miss)", level=3)
add_para(doc, "Swim lanes: Defence Controller | Target Tracking | Operator | Alarm System | Audit Log")
doc.add_paragraph()
add_table(doc,
    ["Swim Lane", "Aktivnosti"],
    [
        ["Defence Controller", "Execute Action → Receive Feedback → [HIT/MISS/LOST?] → HIT: StandDown | MISS: Recalculate Order | LOST: Suspend"],
        ["Target Tracking", "Update Track → [HIT: Close Track] | [MISS: Recompute Trajectory + Kalman Update] | [LOST: Mark TARGET_LOST → Deactivate Tracking]"],
        ["Operator", "Receive Result Notification → [HIT: Review Summary → Confirm Complete] | [MISS: Review New Proposal → Approve/Deny] | [LOST: Acknowledge]"],
        ["Alarm System", "[HIT: Resolve Alarm → Archive] | [MISS: Update Alarm Status → Re-alert Operator] | [LOST: Suspend Alarm]"],
        ["Audit Log", "Log Feedback Result → Log Track Status Change → Log Alarm Resolution → Log Operator Acknowledgement"],
    ],
    col_widths=[4, 12]
)

add_diagram_image(doc, "act_defence_feedback.png", width_cm=14,
                  caption="Slika 8: Activity Diagram 2 — Defence Action Feedback (Hit / Miss)")

page_break(doc)

# ── 2.5 State Machine ─────────────────────────────────────────
add_heading(doc, "2.5 State Machine Diagrams", level=2)
add_para(doc,
    "State Machine dijagrami modeluju zivotni ciklus kljucnih objekata u sistemu "
    "prikazujuci sva moguca stanja i tranzicije izmedju njih.")

add_heading(doc, "State Machine 1: Odbrambeni sistem (Defence System States)", level=3)
add_para(doc, "Ovaj dijagram modeluje stanja kompletnog odbrambenog sistema od prvog signala do zavrsetka misije.")
add_para(doc, "Stanja i tranzicije:", bold=True)
defence_states = [
    ("Monitoring", "Kontinuirani nadzor zone. Senzori aktivni, sistem u stand-by.", "ActivityDetected signal → prelaz u ActivityDetected"),
    ("ActivityDetected", "Senzori detektovali signal, pre-processing i fuzija u toku.", "AI confidence > 0.85 → TargetConfirmed | confidence <= 0.85 → vracanje na Monitoring"),
    ("TargetConfirmed", "AI potvrdio metu, generisanje internih podataka o prijetnji.", "Automatski → AlarmGenerated"),
    ("AlarmGenerated", "Alarm kreiran i proslijedjen operateru. Ceka se odluka.", "Operator.APPROVE → DefenceReady | Operator.DENY → Monitoring"),
    ("DefenceReady", "Kompozitno stanje: Wakeup → GetReady → Deploying. Sistem se aktivira.", "Uredaj na poziciji → InRange | Timeout/Abort → StandDown"),
    ("InRange", "UAV/UGV u dometu mete. Ceka se finalna potvrda operatera.", "Operator.CONFIRM → Engaged | Operator.ABORT → StandDown"),
    ("Engaged", "Akcija angazovanja u toku.", "HIT → MissionAccomplished | MISS → Recalculating | TARGET_LOST → StandDown"),
    ("MissionAccomplished", "Pogodak potvrddjen. Uredaj se povlaci, alarm razrjesen.", "→ Monitoring (reset)"),
    ("Recalculating", "Promasaj. Nova trajektorija se racuna, nova akcija predlozena.", "New trajectory ready → AlarmGenerated (novi ciklus)"),
]
add_table(doc,
    ["Stanje", "Opis", "Tranzicije"],
    defence_states,
    col_widths=[3.5, 6, 6.5]
)

add_diagram_image(doc, "sm_defence_system.png", width_cm=14,
                  caption="Slika 9: State Machine Diagram 1 — Defence System States")

doc.add_paragraph()
add_heading(doc, "State Machine 2: Device Connection States", level=3)
add_para(doc, "Ovaj dijagram modeluje zivotni ciklus konekcije UAV/UGV uredjaja prema centralnom sistemu.")
connection_states = [
    ("Offline", "Uredaj iskljucen ili nema napajanja.", "PowerOn / ConnectRequest → Connecting"),
    ("Connecting", "Pokusaj uspostavljanja konekcije (max 5 pokusaja).", "Success → Online | Failure (max retries) → Error"),
    ("Online", "Konekcija uspostavljena. Uredaj registrovan u sistemu.", "Receive Command → Transmitting | No activity (timeout) → Idle"),
    ("Idle", "Konekcija aktivna ali nema transfera podataka.", "Activity → Transmitting | LostSignal → Connecting (retry)"),
    ("Transmitting", "Aktivni transfer — slanje telemetrije ili primanje komandi.", "Transfer complete → Online | LostSignal → Connecting"),
    ("Error", "Kriticna greska u komunikaciji.", "Reset → Offline | Auto-recover → Connecting"),
],
add_table(doc,
    ["Stanje", "Opis", "Tranzicije"],
    connection_states[0],
    col_widths=[3, 7, 6]
)

add_diagram_image(doc, "sm_connection_states.png", width_cm=14,
                  caption="Slika 10: State Machine Diagram 2 — Device Connection States (UAV/UGV)")

page_break(doc)

# ── 2.6 Component Diagram ─────────────────────────────────────
add_heading(doc, "2.6 Component Diagram", level=2)
add_para(doc,
    "Component dijagram prikazuje arhitekturu sistema kao skup komponenti sa eksplicitnim interfejsima "
    "i zavisnostima. Sistem je organizovan u 5 horizontalnih slojeva.")

add_table(doc,
    ["Sloj", "Komponente", "Interfejsi"],
    [
        ["Presentation Layer", "Operator Dashboard UI, Real-Time Map Viewer, Alarm Console", "REST/WebSocket (HTTPS/TLS 1.3)"],
        ["Application Layer", "API Gateway (nginx), Command & Control Service, Mission Controller Service, Alarm Service, Defence Controller Service", "REST API, WebSocket, gRPC"],
        ["Processing Layer", "Sensor Fusion Engine, Threat Detection Module, Target Tracking Service, Trajectory Estimator, AI/ML Inference Engine (ONNX)", "gRPC (mTLS), Internal Message Bus"],
        ["Device Layer", "UAV Communication Adapter, UGV Communication Adapter, Device Registry, Edge Processor", "Encrypted Radio (AES-256-GCM), Device Protocol"],
        ["Infrastructure Layer", "Encryption Service, Audit Log Service, PostgreSQL (Mission DB), TimescaleDB (Sensor Data), MongoDB (Audit DB)", "JDBC/TCP, Internal API"],
    ],
    col_widths=[3.5, 8, 4.5]
)

doc.add_paragraph()
add_heading(doc, "Kljucni interfejsi", level=3)
add_table(doc,
    ["Interfejs", "Protokol", "Namjena"],
    [
        ["REST / WebSocket", "HTTPS (TLS 1.3) — Port 443", "Presentation ↔ Application Layer komunikacija"],
        ["gRPC", "mTLS — Port 50051", "Application ↔ Processing Layer komunikacija"],
        ["Device Protocol", "AES-256-GCM Encrypted Radio", "Application ↔ Field Device komunikacija"],
        ["Database", "JDBC/TCP — interni network", "Application/Processing ↔ Infrastructure"],
        ["Message Bus", "Async internal pub/sub", "Interna komunikacija izmedju Processing servisa"],
    ],
    col_widths=[3.5, 5, 7.5]
)

add_diagram_image(doc, "component_diagram.png", width_cm=14,
                  caption="Slika 11: Component Diagram — AMCS System Architecture (5 slojeva)")

page_break(doc)

# ── 2.7 Deployment Diagram ────────────────────────────────────
add_heading(doc, "2.7 Deployment Diagram", level=2)
add_para(doc,
    "Deployment dijagram prikazuje fizicku arhitekturu sistema — raspodjelu softverskih "
    "artefakata po hardverskim cvorovima i komunikacione veze izmedju njih.")

add_heading(doc, "Command Center HQ (Sigurni objekat)", level=3)
add_table(doc,
    ["Cvor", "OS/Platforma", "Artefakti"],
    [
        ["Operator Workstation", "Linux PC", "Operator Dashboard (React Browser App), Alarm Console, Map Viewer"],
        ["Application Server", "Linux — Docker Compose", "API Gateway (nginx), Command & Control Service (FastAPI), Mission Controller Service (FastAPI), Alarm Service (FastAPI), Defence Controller Service (FastAPI), Encryption Service (Python)"],
        ["Data Server", "Linux", "PostgreSQL (Mission DB), TimescaleDB (Sensor Time-Series), MongoDB (Audit Logs)"],
        ["AI Processing Server", "Linux — GPU (CUDA)", "Sensor Fusion Engine (Python/NumPy), Threat Detector (ONNX Runtime), Target Tracker (Python/SciPy), Trajectory Estimator (Python/SciPy)"],
    ],
    col_widths=[3.5, 3.5, 9]
)

doc.add_paragraph()
add_heading(doc, "Field Operations Zone", level=3)
add_table(doc,
    ["Cvor", "OS/Platforma", "Artefakti"],
    [
        ["UAV Unit", "Embedded Linux — ARM", "UAV Firmware (ROS2 Node), Camera Driver (OpenCV), Radar Driver (Custom C++), LiDAR Driver (ROS2 PointCloud2), Acoustic Sensor Driver, Edge Processor (ONNX Runtime int8)"],
        ["UGV Unit", "Embedded Linux — x86", "UGV Firmware (ROS2 Node), Sensor Array Driver (ROS2), Seismic Sensor Driver, Edge Processor (ONNX Runtime int8)"],
    ],
    col_widths=[3.5, 3.5, 9]
)

doc.add_paragraph()
add_heading(doc, "Komunikacioni linkovi", level=3)
add_table(doc,
    ["Izvor", "Odrediste", "Protokol"],
    [
        ["Operator Workstation", "Application Server", "HTTPS / WSS (TLS 1.3 — Port 443)"],
        ["Application Server", "Data Server", "JDBC / TCP (interni network)"],
        ["Application Server", "AI Processing Server", "gRPC (mTLS)"],
        ["AI Processing Server", "Data Server", "JDBC / TCP (interni network)"],
        ["UAV/UGV", "Application Server", "Encrypted Radio Link (AES-256-GCM)"],
    ],
    col_widths=[4.5, 4.5, 7]
)

add_diagram_image(doc, "deployment_diagram.png", width_cm=14,
                  caption="Slika 12: Deployment Diagram — AMCS Physical Architecture (HQ + Field Zone)")

page_break(doc)

# ── 2.8 Package Diagram ───────────────────────────────────────
add_heading(doc, "2.8 Package Diagram", level=2)
add_para(doc,
    "Package dijagram prikazuje organizaciju sistema u module/pakete i zavisnosti izmedju njih. "
    "Sistem je organizovan po principu Layered Architecture s jasnom hijerarhijom zavisnosti.")

add_table(doc,
    ["Paket", "Puni naziv", "Sadrzaj", "Zavisnosti"],
    [
        ["presentation", "amcs.presentation", "Operator Dashboard, Alarm Console, Map Viewer, Trajectory Overlay UI", "→ amcs.api"],
        ["api", "amcs.api", "API Gateway, REST Controllers, WebSocket Handlers, DTO klase, Request/Response modeli", "→ amcs.domain"],
        ["domain", "amcs.domain", "Command, Device (UAV/UGV), Sensor, User (Operator), Mission, Alarm — domenski entiteti", "→ amcs.processing, amcs.infrastructure"],
        ["processing", "amcs.processing", "SensorFusionEngine, ThreatDetectionModule, TargetTracker, TrajectoryEstimator, AI/ML Engine", "→ amcs.infrastructure"],
        ["defence", "amcs.defence", "DefenceController, AlarmSystem, DefenceAction, ActionFeedback — odbrambena logika", "→ amcs.processing, amcs.domain, amcs.infrastructure"],
        ["infrastructure", "amcs.infrastructure", "Persistence (PostgreSQL, TimescaleDB, MongoDB), EncryptionService, AuditLog, Repository interfejsi", "– (leaf paket)"],
    ],
    col_widths=[2.5, 3.5, 6, 4]
)

doc.add_paragraph()
add_para(doc, "Hijerarhija zavisnosti (odgore prema dolje):", bold=True)
add_para(doc,
    "amcs.presentation → amcs.api → amcs.domain → amcs.processing → amcs.infrastructure\n"
    "amcs.defence → amcs.processing / amcs.domain / amcs.infrastructure",
    size=10)
add_para(doc,
    "Princip koji se potuje: visi slojevi zavise od nizih, ali nizi slojevi nikada ne zavise "
    "od visih (Dependency Inversion Principle). Krozni zavisnosti su eksplicitno zabranjene.")

add_diagram_image(doc, "package_diagram.png", width_cm=14,
                  caption="Slika 13: Package Diagram — AMCS Module Organization (<<import>> / <<access>>)")

page_break(doc)

# ── 2.9 Object Diagram ────────────────────────────────────────
add_heading(doc, "2.9 Object Diagram", level=2)
add_para(doc,
    "Object dijagram prikazuje konkretan runtime snapshot sistema tokom aktivne misije MSN-2026-003. "
    "Prikazane su instance klasa s konkretnim vrijednostima atributa u trenutku odbrambene akcije.")

add_heading(doc, "Kontekst snimka: Aktivna misija MSN-2026-003", level=3)
add_para(doc,
    "Vremenski peckt: 2026-03-21 14:34:12Z. Status: Odbrambena akcija u toku — UAV Alpha "
    "i UGV Bravo deploying prema tacki presretanja. Alarm odobren od Operatera Jovic.",
    italic=True, size=10)

add_table(doc,
    ["Instanca", "Klasa", "Kljucni atributi"],
    [
        ["uav_alpha", "UAV", "deviceId='UAV-001', status=TRANSMITTING, altitude=120m, speed=85km/h, battery=78.5%"],
        ["ugv_bravo", "UGV", "deviceId='UGV-001', status=DEPLOYING, speed=25km/h, terrainMode=OFF_ROAD, battery=92.3%"],
        ["cam_01", "CameraSensor", "sensorId='CAM-001', resolution=1080p, fps=30, nightVision=true, mountedOn=uav_alpha"],
        ["radar_01", "RadarSensor", "sensorId='RAD-001', range=5000m, frequency=77GHz, mountedOn=uav_alpha"],
        ["lidar_01", "LiDARSensor", "sensorId='LDR-001', pointsPerSecond=100K, range=200m, mountedOn=ugv_bravo"],
        ["acoustic_01", "AcousticSensor", "sensorId='ACU-001', frequencyRange=20Hz-20kHz, isStandalone=true"],
        ["alarm_001", "Alarm", "alarmId='ALM-001', level=HIGH, status=OPERATOR_APPROVED, confidence=93%, targetId='TGT-001'"],
        ["action_001", "DefenceAction", "actionId='ACT-001', type=INTERCEPT, status=DEPLOYING, assignedDevices=[uav_alpha, ugv_bravo]"],
        ["track_001", "Track", "trackId='TRK-001', velocity=15m/s, heading=180°, lastUpdate=14:34:10Z"],
        ["trajectory_001", "Trajectory", "interceptPoint=GeoCoord(44.123, 20.456), ETA=14:35:00Z, confidence=0.91"],
        ["op_jovic", "Operator", "username='jovic', clearanceLevel=3, assignedZone='ZONE-BRAVO', lastLogin=14:00:00Z"],
        ["mission_03", "MissionController", "missionId='MSN-2026-003', status=ACTIVE, startTime=14:30:00Z, assignedDevices=[uav_alpha, ugv_bravo]"],
    ],
    col_widths=[3, 3.5, 9.5]
)

add_diagram_image(doc, "object_diagram.png", width_cm=15,
                  caption="Slika 14: Object Diagram — Runtime snapshot, aktivna misija MSN-2026-003")

page_break(doc)

# ══════════════════════════════════════════════════════════════
# III. ZAKLJUCAK
# ══════════════════════════════════════════════════════════════
add_heading(doc, "III. ZAKLJUCAK", level=1)

add_heading(doc, "3.1 Arhitekturne odluke", level=2)
add_para(doc,
    "AMCS je projektovan kao socijabilna, bezbjedna i skalabilna softverska arhitektura "
    "namijenjena za kriticne borbene sisteme. Kljucne arhitekturne odluke su:")

arhitekturne_odluke = [
    ("Troslojna separacija briga (3 kontrolera)",
     "Jasna podjela izmedju detekcije, obrade i odlucivanja eliminise ogranicenja monolitnih sistema i olaksava nezavisni razvoj i testiranje."),
    ("Edge Computing na UAV/UGV",
     "ONNX Runtime na ARM/x86 embedded Linux smanjuje bandwidth prema centralnom serveru za ~80% i osigurava rad i pri privremenom gubitku konekcije."),
    ("AI/ML identifikacija meta",
     "ONNX Runtime za inference na edge i GPU server za kompleksnu analizu. Prag pouzdanosti od 0.85 balansira sensitivnost i specificnost."),
    ("Feedback petlja (promasaj → ponovni proracun)",
     "Adaptivni Kalman filter koji prima feedback iz akcionih rezultata omogucava iterativni odbrambeni odgovor bez ponovnog pokretanja cijelog procesa."),
    ("Covjek-u-petlji (Human-in-the-Loop)",
     "Dvostepena potvrda operatera (approve inicijalna akcija + confirm engagement) osigurava eticki i pravni framework autonomnih borbenih sistema."),
    ("End-to-end enkripcija",
     "TLS 1.3 za web komunikaciju, mTLS za servis-servis komunikaciju, AES-256-GCM za radio linkove eliminisu rizik od presretanja i manipulacije komandama."),
]
for naslov, opis in arhitekturne_odluke:
    add_para(doc, naslov, bold=True, size=11)
    add_para(doc, opis, size=11, space_after=4)

add_heading(doc, "3.2 Postignuti ciljevi i quality attributes", level=2)
add_table(doc,
    ["Quality Attribute", "Zahtjev", "Postignuto rijesenje"],
    [
        ["Latencija", "< 200ms", "Edge processing, in-memory Kalman, gRPC umjesto REST za interni processing"],
        ["Raspolozivost", "99.9% uptime", "Docker, automatski failover, redundantne komunikacione putanje"],
        ["Skalabilnost", "50+ uredjaja", "Adapter pattern za device layer, stateless processing servisi, TimescaleDB"],
        ["Pouzdanost", "Auomatski failover", "State machine za konekciju (retry logic), track loss handling"],
        ["Sigurnost", "End-to-end", "AES-256-GCM, TLS 1.3, mTLS, audit logging, role-based access (clearanceLevel)"],
    ],
    col_widths=[3.5, 2.5, 10]
)

add_heading(doc, "3.3 Buduce aktivnosti", level=2)
buduce = [
    "Backend implementacija — Python/FastAPI, gRPC servisi, Docker Compose orkestracija",
    "CI/CD pipeline — GitHub Actions, automated testing, container registry",
    "ML modeli za fuziju i identifikaciju — PyTorch trening, ONNX export, kvantizacija za edge",
    "ROS2 + PoC simulacija — Gazebo simulator, virtuelni UAV/UGV sa senzorskim driverima",
    "Zavrsni rad: integracija kompletnog sistema, evaluacija latencije i pouzdanosti na simuliranom scenariju",
]
for b in buduce:
    add_bullet(doc, b)

add_heading(doc, "3.4 Literatura", level=2)
literature = [
    "Gamma, E., Helm, R., Johnson, R., Vlissides, J. Design Patterns: Elements of Reusable Object-Oriented Software. Addison-Wesley, 1994.",
    "Fowler, M. UML Distilled: A Brief Guide to the Standard Object Modeling Language. 3rd ed., Addison-Wesley, 2003.",
    "Bass, L., Clements, P., Kazman, R. Software Architecture in Practice. 3rd ed., Addison-Wesley, 2012.",
    "Mahler, R., et al. Multi-Sensor Fusion for Autonomous Vehicle Perception. IEEE Transactions on Intelligent Transportation Systems, 2021.",
    "OMG. UML Specification v2.5.1. Object Management Group, 2017.",
    "Welch, G., Bishop, G. An Introduction to the Kalman Filter. University of North Carolina, 2006.",
    "Thrun, S., Burgard, W., Fox, D. Probabilistic Robotics. MIT Press, 2005.",
]
for i, ref in enumerate(literature, 1):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(3)
    run = p.add_run(f"[{i}] {ref}")
    run.font.size = Pt(10)

# ── Save ──────────────────────────────────────────────────────
doc.save(OUTPUT_PATH)
print(f"Dokument sacuvan: {OUTPUT_PATH}")

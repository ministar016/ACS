#!/usr/bin/env python3
"""Convert Serbian ijekavica to ekavica in a .docx document."""

from docx import Document
import re
import shutil

# Ijekavica → Ekavica word mapping
WORD_MAP = {
    # prijetnja → pretnja
    'prijetnji': 'pretnji',
    'prijetnje': 'pretnje',
    'prijetnja': 'pretnja',
    
    # obavještenje → obaveštenje
    'obavještenje': 'obaveštenje',
    
    # bezbjedna → bezbedna
    'bezbjedna': 'bezbedna',
    
    # riješenje → rešenje, riješiti → rešiti
    'riješenje': 'rešenje',
    'riješiti': 'rešiti',
    
    # namijenjena → namenjena
    'namijenjena': 'namenjena',
    
    # razrješen → razrešen
    'razrješen': 'razrešen',
    
    # proslijeđen → prosleđen
    'proslijeđen': 'prosleđen',
    
    # letjelice → letelice
    'letjelice': 'letelice',
    
    # procjena → procena, procjenjuje → procenjuje
    'procjena': 'procena',
    'procjenu': 'procenu',
    'procjenjuje': 'procenjuje',
    'procijenjenu': 'procenjenu',
    
    # primjenjuje → primenjuje, primjena → primena
    'primjenjuje': 'primenjuje',
    'primjenu': 'primenu',
    'primjena': 'primena',
    
    # mjeri → meri, mjerenja → merenja
    'mjeri': 'meri',
    'mjerenja': 'merenja',
    
    # korištenje → korišćenje
    'korištenje': 'korišćenje',
    
    # namjena → namena
    'namjena': 'namena',
    
    # umjesto → umesto
    'umjesto': 'umesto',
    
    # vrijednostima → vrednostima
    'vrijednostima': 'vrednostima',
    
    # redosljed → redosled
    'redosljed': 'redosled',
    
    # udaljenost → udaljenost (stays the same - not ije/je related)
    # Actually: udaljenost is the same in ekavica
    
    # hijerarhija → hijerarhija (Greek origin, stays the same)
    
    # temeljena → zasnovana? No, temeljena stays
    
    # cijelog → celog
    'cijelog': 'celog',
    
    # zahtjev → zahtev, zahtjeve → zahteve
    'zahtjev': 'zahtev',
    'zahtjeve': 'zahteve',
    
    # predviđanje → predviđanje (stays — đ is already correct)
    
    # čovjek → čovek
    'čovjek': 'čovek',
    
    # donošenje stays (not ijekavica)
    
    # uvođenje stays (not ijekavica)
    
    # potuje → poštuje (this was a typo in original — "potuje" should be "poštuje")
    'potuje': 'poštuje',
    
    # trigguije → trigguje (typo fix)
    'trigguije': 'trigguje',
    
    # objekat stays (same in both)
    
    # Additional ije→e conversions from the word list
    # nasljeđivanje → nasleđivanje
    'nasljeđivanje': 'nasleđivanje',
    'nasljeđuju': 'nasleđuju',
    
    # dodjeljuje → dodeljuje  
    'dodjeljuje': 'dodeljuje',
    
    # podjela → podela
    'podjela': 'podela',
    
    # raspodjelu → raspodelu
    'raspodjelu': 'raspodelu',
    
    # kašnjenja stays (not ije related)
    
    # vibracije stays
    
    # interakcije stays (Latin origin)
    
    # detekcije stays
    
    # relacije stays
    
    # tranzicije stays
    
    # komunikacije stays
    
    # manipulacije stays
    
    # presretanje stays
}


def apply_case(original, replacement):
    """Preserve the case pattern of the original word."""
    if original.isupper():
        return replacement.upper()
    if original[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def replace_words(text):
    """Replace words in text using WORD_MAP, preserving case."""
    def replacer(match):
        word = match.group(0)
        lower = word.lower()
        if lower in WORD_MAP:
            return apply_case(word, WORD_MAP[lower])
        return word
    return re.sub(r'[a-zA-ZšđžćčŠĐŽĆČ]+', replacer, text)


def process_runs(paragraphs):
    """Process all runs in a list of paragraphs."""
    for paragraph in paragraphs:
        for run in paragraph.runs:
            new_text = replace_words(run.text)
            if new_text != run.text:
                run.text = new_text


def main():
    input_path = 'projektovanje-softvera/docs/ispit.docx'
    
    doc = Document(input_path)
    
    # Process paragraphs
    process_runs(doc.paragraphs)
    
    # Process tables
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                process_runs(cell.paragraphs)
    
    # Process headers and footers
    for section in doc.sections:
        if section.header:
            process_runs(section.header.paragraphs)
        if section.footer:
            process_runs(section.footer.paragraphs)
    
    doc.save(input_path)
    print(f"Dokument sačuvan: {input_path}")
    
    # Verify
    doc2 = Document(input_path)
    all_text = []
    for p in doc2.paragraphs:
        all_text.append(p.text)
    for t in doc2.tables:
        for r in t.rows:
            for c in r.cells:
                all_text.append(c.text)
    full = ' '.join(all_text)
    
    checks_present = ['pretnji', 'obaveštenje', 'bezbedna', 'rešenje', 'namenjena',
                      'razrešen', 'prosleđen', 'letelice', 'procenu', 'procenjuje',
                      'primenjuje', 'merenja', 'čovek', 'zahtev', 'celog',
                      'nasleđivanje', 'dodeljuje', 'podela']
    checks_absent = ['prijetnji', 'obavještenje', 'bezbjedna', 'riješenje', 'namijenjena',
                     'razrješen', 'proslijeđen', 'letjelice', 'procjenu', 'procjenjuje',
                     'primjenjuje', 'mjerenja', 'čovjek', 'zahtjev', 'cijelog',
                     'nasljeđivanje', 'dodjeljuje', 'podjela']
    
    print("\nProvera konverzije (ekavski oblici):")
    for w in checks_present:
        found = w in full or w.capitalize() in full
        print(f"  {'✓' if found else '✗'} {w}")
    
    print("\nProvera da ijekavski oblici više ne postoje:")
    for w in checks_absent:
        found = w in full or w.capitalize() in full
        print(f"  {'✓ uklonjeno' if not found else '✗ OSTALO'} {w}")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Seed initial wiki pages for the pharma intelligence knowledge base.
Creates one Markdown wiki page per drug, indication, and company.
Run once: python src/seed_wiki.py
"""
import os, json, subprocess, sys

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ijunshkmqdqhdeivcjze.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

def supa_upsert(table, data):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    r = subprocess.run([
        "curl", "-s", "-X", "POST",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: resolution=merge-duplicates,return=minimal",
        url, "-d", json.dumps(data)
    ], capture_output=True, text=True, timeout=30)
    if r.returncode != 0 or (r.stdout and '"error"' in r.stdout):
        print(f"  ERROR: {r.stdout[:200]}")
        return False
    return True

DRUGS = [
    # (id, name, company, class, indications, status, notes)
    ("drug_rinvoq",     "Rinvoq (upadacitinib)",     "AbbVie",       "JAK1 inhibitor",  "RA, PsA, UC, CD, AS, AD",  "Approved",  "BBW for serious infections, malignancy, MACE, thrombosis. AbbVie's key growth driver replacing Humira."),
    ("drug_skyrizi",    "Skyrizi (risankizumab)",     "AbbVie",       "IL-23 inhibitor", "Psoriasis, PsA, CD, UC",    "Approved",  "AbbVie's highest-growth asset. IL-23 p19 selective. Strong durability profile."),
    ("drug_humira",     "Humira (adalimumab)",        "AbbVie",       "TNF inhibitor",   "RA, PsA, CD, UC, AS",       "Approved",  "LOE in 2023 USA. Biosimilar competition (Hadlima, Cyltezo, Hyrimoz). AbbVie offsetting with Rinvoq/Skyrizi."),
    ("drug_stelara",    "Stelara (ustekinumab)",      "J&J Janssen",  "IL-12/23 inhibitor","CD, UC, Psoriasis, PsA", "Approved",  "LOE 2023. Biosimilars entering (Selarsdi, Wezlana). J&J pivoting to Tremfya."),
    ("drug_tremfya",    "Tremfya (guselkumab)",       "J&J Janssen",  "IL-23 inhibitor", "Psoriasis, PsA",            "Approved",  "Differentiated by maintained response after withdrawal in some patients."),
    ("drug_cosentyx",   "Cosentyx (secukinumab)",     "Novartis",     "IL-17A inhibitor","Psoriasis, PsA, AS, nr-axSpA","Approved","Pioneer IL-17A. Strong in PsA/AS. Competition from Taltz (IL-17A/F)."),
    ("drug_taltz",      "Taltz (ixekizumab)",         "Eli Lilly",    "IL-17A inhibitor","Psoriasis, PsA, AS",        "Approved",  "IL-17A selective. Strong radiographic progression data in PsA."),
    ("drug_sotyktu",    "Sotyktu (deucravacitinib)",  "BMS",          "TYK2 inhibitor",  "Psoriasis, PsA, SLE",       "Approved",  "First-in-class oral TYK2 inhibitor. Allosteric mechanism avoids JAK BBW. Growing in Psoriasis."),
    ("drug_bimzelx",    "Bimzelx (bimekizumab)",      "UCB",          "IL-17A/F inhibitor","Psoriasis, PsA, AS",     "Approved",  "Dual IL-17A/F blockade. Strong PASI 90/100 rates. UCB's key asset."),
    ("drug_omvoh",      "Omvoh (mirikizumab)",        "Eli Lilly",    "IL-23 inhibitor", "UC, CD",                    "Approved",  "Approved UC 2023, CD filing underway. Competes with Stelara/Skyrizi in IBD."),
    ("drug_entyvio",    "Entyvio (vedolizumab)",      "Takeda",       "a4b7 integrin inhibitor","UC, CD",            "Approved",  "Gut-selective. Strong safety profile. SC formulation approved. Key IBD asset."),
    ("drug_zeposia",    "Zeposia (ozanimod)",         "BMS",          "S1P receptor modulator","UC, RMS",            "Approved",  "Oral S1P1/5 modulator. UC approved 2021. Modest UC penetration so far."),
    ("drug_kevzara",    "Kevzara (sarilumab)",        "Sanofi",       "IL-6R inhibitor", "RA",                        "Approved",  "Competes with Actemra. Used in RA patients failing TNF."),
    ("drug_duvakitug",  "Duvakitug",                  "Sanofi/Teva",  "TL1A inhibitor",  "UC, CD",                    "Phase 3",   "Anti-TL1A antibody. Phase 3 ongoing in IBD. TL1A is emerging hot mechanism with Merck's tulisokibart."),
    ("drug_tulisokibart","Tulisokibart (MK-7240)",    "Merck",        "TL1A inhibitor",  "UC, CD",                    "Phase 3",   "Anti-TL1A. Key competitor to duvakitug. Phase 3 IBD results expected 2025-2026."),
    ("drug_alumis",     "Alumis (envudeucitinib)",    "Alumis",       "TYK2 inhibitor",  "Psoriasis, SLE",            "Phase 3",   "Next-gen oral TYK2. Competes with Sotyktu. Phase 3 in Psoriasis. Potential acquisition target."),
    ("drug_otezla",     "Otezla (apremilast)",        "Amgen",        "PDE4 inhibitor",  "Psoriasis, PsA, BD",        "Approved",  "Oral. Modest efficacy vs biologics. Useful in mild-moderate or biologic-naive patients."),
    ("drug_orencia",    "Orencia (abatacept)",        "BMS",          "CTLA4-Ig",        "RA, PsA, pJIA",             "Approved",  "T-cell co-stimulation blocker. IV and SC. Niche in seronegative RA and some PsA."),
    ("drug_actemra",    "Actemra (tocilizumab)",      "Roche",        "IL-6R inhibitor", "RA, GCA, sJIA, CAR-T CRS", "Approved",  "Pioneer IL-6 blocker. IV and SC. Also used in cytokine storm (COVID, CAR-T)."),
    ("drug_enbrel",     "Enbrel (etanercept)",        "Amgen/Pfizer", "TNF receptor fusion","RA, PsA, Psoriasis, AS","Approved",  "Original TNF inhibitor. Biosimilar competition. Declining in favour of newer mechanisms."),
    ("drug_jyseleca",   "Jyseleca (filgotinib)",      "Gilead/Galapagos","JAK1 inhibitor","RA, UC",                  "Approved",  "EU approved RA/UC. Not approved in USA (FDA declined). JAK1-selective."),
    ("drug_spevigo",    "Spevigo (spesolimab)",       "Boehringer Ingelheim","IL-36R inhibitor","GPP",               "Approved",  "First-in-class IL-36R inhibitor for generalised pustular psoriasis (GPP). Niche indication."),
]

INDICATIONS = [
    ("ind_ra",         "Rheumatoid Arthritis (RA)",
     """## Rheumatoid Arthritis (RA)

**Disease**: Chronic autoimmune joint disease affecting ~1% of adults. Synovial inflammation -> cartilage/bone destruction.

**Key mechanisms targeted**: TNF, IL-6, JAK (JAK1), CTLA4, CD20, IL-17

**Treatment landscape**:
- 1st line: MTX + conventional DMARDs
- 2nd line: TNF inhibitors (Enbrel, Humira, Cosentyx, Remicade) -- now with biosimilar competition
- Advanced: JAK inhibitors (Rinvoq, Olumiant, Jyseleca), IL-6 (Actemra, Kevzara)

**Key companies/drugs**: AbbVie (Rinvoq, Humira), Eli Lilly (Olumiant), Sanofi (Kevzara), Roche (Actemra), BMS (Orencia), Gilead (Jyseleca)

**Competitive dynamics**:
- Humira biosimilars eroding TNF market share
- Rinvoq gaining RA market share (AbbVie guidance: $5B+ peak sales)
- JAK inhibitor class label warnings (BBW) added 2021 -- post-ORAL Surveillance
- Cardiovascular and malignancy risk monitoring required for all JAKi

**Key trials to watch**: AbbVie SELECT program (Rinvoq), Lilly BALANCE studies (baricitinib)
"""),
    ("ind_psoriasis",  "Psoriasis & Psoriatic Arthritis (PsA)",
     """## Psoriasis & Psoriatic Arthritis (PsA)

**Disease**: Psoriasis = chronic skin inflammation (plaques). PsA = inflammatory arthritis in ~30% of psoriasis patients.

**Key mechanisms**: IL-17A/F, IL-23/p19, IL-12/23, TYK2, TNF, JAK

**Treatment landscape (Psoriasis)**:
- Biologics dominate moderate-severe: IL-17 (Cosentyx, Taltz, Bimzelx), IL-23 (Skyrizi, Tremfya, Ilumya)
- Oral: Otezla (PDE4), Sotyktu (TYK2), Alumis (TYK2, Phase 3)
- PASI 90/100 now the efficacy bar

**Treatment landscape (PsA)**:
- TNF still used, IL-17 (Cosentyx, Taltz, Bimzelx) strong
- IL-23 (Skyrizi, Tremfya) growing
- JAK (Rinvoq) approved for PsA

**Key companies**: AbbVie, Novartis, UCB, Eli Lilly, J&J, BMS, Alumis

**Competitive dynamics**:
- IL-23 vs IL-17 head-to-head data increasingly important
- TYK2 oral competition heating up (Sotyktu vs Alumis)
- Bimzelx (IL-17A/F dual) differentiated by dual blockade
"""),
    ("ind_crohns",     "Crohn's Disease (CD)",
     """## Crohn's Disease (CD)

**Disease**: Transmural IBD affecting any GI segment. Relapsing-remitting. High unmet need.

**Key mechanisms**: TNF, IL-12/23, a4b7 integrin, TL1A, JAK, S1P

**Treatment landscape**:
- Biologics: Entyvio (integrin), Stelara (IL-12/23), Skyrizi (IL-23) -- Skyrizi fastest growing
- TNF: Humira, Remicade (biosimilar competition)
- Emerging: TL1A antibodies (duvakitug, tulisokibart) -- hot mechanism 2024-2026

**Key companies**: AbbVie (Skyrizi, Humira), Takeda (Entyvio), J&J (Stelara-> biosimilar), Eli Lilly (Omvoh CD filing), Sanofi (duvakitug), Merck (tulisokibart)

**Competitive dynamics**:
- Skyrizi (AbbVie) approved CD 2023 -- growing rapidly, taking share from Stelara
- Stelara LOE = major opportunity for competitors
- TL1A readouts in 2025-2026 could reshape IBD treatment paradigm
- Omvoh (Lilly) filed for CD -- adds IL-23 competitor
"""),
    ("ind_uc",         "Ulcerative Colitis (UC)",
     """## Ulcerative Colitis (UC)

**Disease**: Mucosal IBD limited to colon. Extends from rectum proximally. ~900K patients USA.

**Key mechanisms**: TNF, IL-23, a4b7, TL1A, JAK1, S1P1, IL-36R

**Treatment landscape**:
- Biologics: Entyvio (1st-line preferred in UC), Stelara, Skyrizi, Omvoh
- Oral: Xeljanz (JAK), Zeposia (S1P), Rinvoq (JAK1)
- Emerging: TL1A (duvakitug, tulisokibart)

**Key companies**: Takeda (Entyvio), AbbVie (Skyrizi, Rinvoq), J&J (Stelara), Eli Lilly (Omvoh, Rinvoq), BMS (Zeposia), Sanofi (duvakitug), Merck (tulisokibart)

**Competitive dynamics**:
- Entyvio is most prescribed UC biologic -- SC formulation strengthening position
- Skyrizi approved UC 2024, growing fast
- Omvoh carved niche with strong remission data
- TL1A class data in UC expected 2025 from both Sanofi/Teva and Merck
- Rinvoq approved UC -- oral option for moderate-severe disease
"""),
]

COMPANIES = [
    ("co_abbvie",   "AbbVie",
     """## AbbVie

**Key immunology assets**: Rinvoq (upadacitinib, JAK1), Skyrizi (risankizumab, IL-23), Humira (adalimumab, TNF)

**Strategy**: Humira LOE mitigation via Rinvoq + Skyrizi. Combined $21B+ peak sales guided by management.

**Pipeline highlights**:
- ABBV-CLS-484 (PD-1/LAG3, oncology)
- Lutikizumab (IL-1a/b) in HS
- Navitoclax combinations (oncology)

**Competitive position**: Dominant in RA (Rinvoq) and IBD/Psoriasis (Skyrizi). Watching JAK class label risk.

**Recent news**: [Updated by wiki_updater as articles arrive]
"""),
    ("co_bms",      "Bristol-Myers Squibb (BMS)",
     """## Bristol-Myers Squibb (BMS)

**Key immunology assets**: Sotyktu (deucravacitinib, TYK2), Zeposia (ozanimod, S1P), Orencia (abatacept, CTLA4)

**Strategy**: TYK2 allosteric mechanism (Sotyktu) avoids JAK BBW -- key differentiator vs JAK inhibitors.

**Pipeline highlights**:
- Sotyktu expanding into SLE, PsA
- BMS-986325 (TL1A) -- early stage
- Milvexian (Factor XIa, CVD)

**Competitive position**: Sotyktu growing in Psoriasis market. Zeposia niche in UC. Orencia declining in RA.

**Recent news**: [Updated by wiki_updater as articles arrive]
"""),
    ("co_ucb",      "UCB",
     """## UCB

**Key immunology assets**: Bimzelx (bimekizumab, IL-17A/F), Cimzia (certolizumab, TNF), Evenity (bone)

**Strategy**: Bimzelx differentiation via dual IL-17A/F blockade. Strong PASI 90/100 data vs Cosentyx/Taltz.

**Pipeline highlights**:
- Bimzelx expanding: PsA, AS, nr-axSpA approvals underway
- UCB7858 (anti-IL-17C) in psoriasis

**Competitive position**: Bimzelx is UCB's primary immunology growth driver. Competes directly with Cosentyx (Novartis) and Taltz (Lilly).

**Recent news**: [Updated by wiki_updater as articles arrive]
"""),
    ("co_lilly",    "Eli Lilly",
     """## Eli Lilly

**Key immunology assets**: Taltz (ixekizumab, IL-17A), Omvoh (mirikizumab, IL-23), Rinvoq (co-promoted, JAK1), Olumiant (baricitinib, JAK)

**Strategy**: Strong IBD presence with Omvoh. Taltz defending psoriasis position. GLP-1 success (Mounjaro/Zepbound) funds immunology investment.

**Pipeline highlights**:
- Omvoh CD filing submitted
- LY3537982 (KRAS G12C, oncology)
- Lepodisiran (Lp(a))

**Competitive position**: Omvoh carving UC/CD niche. Taltz under pressure from IL-17A/F dual (Bimzelx) and IL-23 class.

**Recent news**: [Updated by wiki_updater as articles arrive]
"""),
    ("co_sanofi",   "Sanofi",
     """## Sanofi

**Key immunology assets**: Dupixent (dupilumab, IL-4/13), Kevzara (sarilumab, IL-6R), Duvakitug (TL1A, Phase 3)

**Strategy**: Dupixent is flagship asset (atopy). Duvakitug (acquired with Teva deal) is key IBD bet. Kevzara niche in RA.

**Pipeline highlights**:
- Duvakitug Phase 3 UC/CD -- TL1A mechanism
- Tolebrutinib (BTK, MS)
- Dupixent label expansions (COPD, etc.)

**Competitive position**: Duvakitug competing directly with Merck's tulisokibart in TL1A race for IBD.

**Recent news**: [Updated by wiki_updater as articles arrive]
"""),
    ("co_takeda",   "Takeda",
     """## Takeda

**Key immunology assets**: Entyvio (vedolizumab, a4b7 integrin), TAK-279 (TYK2, Phase 3)

**Strategy**: Entyvio is cornerstone UC/CD biologic -- defending with SC formulation. TAK-279 (zasocitinib) is next-gen oral TYK2 for psoriasis.

**Pipeline highlights**:
- TAK-279 (zasocitinib) Phase 3 psoriasis -- competes with Sotyktu, Alumis
- Entyvio SC maintaining IBD market leadership

**Competitive position**: Entyvio faces Skyrizi and Omvoh pressure in IBD. TAK-279 could open new revenue in psoriasis.

**Recent news**: [Updated by wiki_updater as articles arrive]
"""),
    ("co_jj",       "J&J (Janssen)",
     """## J&J (Janssen)

**Key immunology assets**: Tremfya (guselkumab, IL-23), Stelara (ustekinumab, IL-12/23 -- LOE), Simponi (golimumab, TNF)

**Strategy**: Tremfya is growth driver post-Stelara LOE. Nipocalimab (FcRn) pipeline for autoimmune diseases.

**Pipeline highlights**:
- Nipocalimab (FcRn) -- MG, FNAIT, autoimmune
- Icotrokinra (IL-17C, psoriasis)
- Tremfya expanding indications

**Competitive position**: Stelara biosimilar pressure since 2023. Tremfya competing with Skyrizi in Psoriasis/PsA.

**Recent news**: [Updated by wiki_updater as articles arrive]
"""),
    ("co_merck",    "Merck (MSD)",
     """## Merck (MSD)

**Key immunology assets**: Tulisokibart/MK-7240 (TL1A, Phase 3)

**Strategy**: Tulisokibart is Merck's major IBD bet -- competing with Sanofi/Teva duvakitug in TL1A race.

**Pipeline highlights**:
- Tulisokibart Phase 3 UC and CD -- results expected 2025-2026
- MK-1654 (RSV mAb)
- Clesrovimab (RSV prevention)

**Competitive position**: Keytruda dominates oncology. Tulisokibart could open significant IBD revenue if Phase 3 succeeds.

**Recent news**: [Updated by wiki_updater as articles arrive]
"""),
]

def seed_drugs():
    print(f"\nSeeding {len(DRUGS)} drug wiki pages...")
    for drug_id, name, company, drug_class, indications, status, notes in DRUGS:
        content = f"""## {name}

**Company**: {company}
**Class**: {drug_class}
**Indications**: {indications}
**Status**: {status}

### Overview
{notes}

### Clinical Profile
*[Updated automatically as press releases arrive]*

### Recent Developments
*[Updated by wiki_updater]*

### Competitive Context
*[Updated by wiki_updater]*
"""
        row = {
            "id": drug_id,
            "entity_type": "drug",
            "entity_name": name,
            "content": content,
        }
        ok = supa_upsert("wiki_pages", row)
        print(f"  {'OK' if ok else 'FAIL'} {name}")

def seed_indications():
    print(f"\nSeeding {len(INDICATIONS)} indication wiki pages...")
    for ind_id, name, content in INDICATIONS:
        row = {
            "id": ind_id,
            "entity_type": "indication",
            "entity_name": name,
            "content": content,
        }
        ok = supa_upsert("wiki_pages", row)
        print(f"  {'OK' if ok else 'FAIL'} {name}")

def seed_companies():
    print(f"\nSeeding {len(COMPANIES)} company wiki pages...")
    for co_id, name, content in COMPANIES:
        row = {
            "id": co_id,
            "entity_type": "company",
            "entity_name": name,
            "content": content,
        }
        ok = supa_upsert("wiki_pages", row)
        print(f"  {'OK' if ok else 'FAIL'} {name}")

def main():
    if not SUPABASE_KEY:
        print("ERROR: SUPABASE_KEY not set")
        sys.exit(1)
    print("=== Seeding Pharma Wiki Pages ===")
    seed_drugs()
    seed_indications()
    seed_companies()
    print("\nDone! Run embed_articles.py to generate embeddings.")

if __name__ == "__main__":
    main()

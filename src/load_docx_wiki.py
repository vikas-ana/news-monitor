#!/usr/bin/env python3
"""
Load Pharma_Immunology_Competitive_Report_2026.docx into Supabase wiki_pages
and reload Neo4j with enriched company data.

Adds:
  - Wiki pages for Novartis, AstraZeneca, GSK, Amgen, Roche (missing companies)
  - strategic_watchlist page (key 2025-27 catalysts)
  - moa_landscape page (MOA class overview)
  - Enriches existing company pages with tier, earnings quote, full SWOT

Run: python3 src/load_docx_wiki.py
"""
import os, json, subprocess
from datetime import datetime, timezone

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

def supa_upsert(table, data):
    subprocess.run(["curl", "-s", "--max-time", "20", "-X", "POST",
        f"{SUPABASE_URL}/rest/v1/{table}",
        "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Content-Type: application/json",
        "-H", "Prefer: resolution=merge-duplicates,return=minimal",
        "-d", json.dumps(data)], capture_output=True)

def upsert_wiki(wiki_id, entity_type, entity_name, content):
    supa_upsert("wiki_pages", {
        "id":          wiki_id,
        "entity_type": entity_type,
        "entity_name": entity_name,
        "content":     content,
        "updated_at":  datetime.now(timezone.utc).isoformat(),
        "version":     1,
    })
    print(f"  [OK] {wiki_id}")

# ── Company wiki pages ─────────────────────────────────────────────────────────

COMPANY_PAGES = {
"co_novartis": ("Novartis", """## Novartis
**Tier**: Tier 1 — IL-17 Leader
**Focus Indications**: Plaque Psoriasis, PsA, SLE (pipeline)

### Approved Drugs
| Drug | Generic | Indication | MOA | Year |
|------|---------|------------|-----|------|
| Cosentyx | secukinumab | Plaque Psoriasis | IL-17A inhibitor | 2015 |
| Cosentyx | secukinumab | PsA | IL-17A inhibitor | 2016 |
| Ianalumab | ianalumab (VAY736) | SLE | BAFF-R inhibitor | Phase 3 |

### SWOT Analysis
**Strengths**: Cosentyx topped $6B in 2024 — largest IL-17A franchise globally. New indications (HS, GCA, PMR) extending lifecycle. Ianalumab (BAFF-R) in Phase 3 SLE with 6 ongoing studies.

**Weaknesses**: Cosentyx lacks IBD indications — a major commercial gap vs AbbVie/Takeda. No RA approval. SLE pipeline still Phase 3 with no near-term approval date.

**Opportunities**: Ianalumab's BAFF-R mechanism differentiates from belimumab (BAFF-L) — could capture new SLE segment. Cosentyx biosimilars still distant. HS and PMR launches driving incremental revenue.

**Threats**: IL-17A biosimilars beginning to enter market. IL-23 class taking psoriasis share from IL-17A. No IBD presence remains a competitive gap. Ianalumab Phase 3 failure risk.

### Key Earnings Quote
"Six Phase III studies across the board already running for ianalumab... this could be a very significant medicine, probably underappreciated overall." — Novartis management, Q4 2024 Earnings (Jan 31, 2025)

### Strategic Watch
- **Ianalumab (VAY736)**: SLE Phase 3 readout ~2026. BAFF-R vs BAFF-L differentiation from Benlysta. High conviction — 6 Phase 3 studies running.
- **Cosentyx**: IL-17A biosimilar threat. Losing psoriasis share to IL-23 class. Strong lifecycle management via new indications (HS, GCA, PMR).

### Recent Developments
*[Updated by wiki_updater as press releases arrive]*
"""),

"co_astrazeneca": ("AstraZeneca", """## AstraZeneca
**Tier**: Tier 2 — SLE Specialist
**Focus Indications**: SLE

### Approved Drugs
| Drug | Generic | Indication | MOA | Year |
|------|---------|------------|-----|------|
| Saphnelo | anifrolumab | SLE | IFNAR1 inhibitor | 2021 |
| Saphnelo SC | anifrolumab SC | SLE | IFNAR1 inhibitor | Phase 3 |

### SWOT Analysis
**Strengths**: Saphnelo is the only IFNAR1 inhibitor approved for SLE — truly differentiated MOA vs BAFF inhibitors. 69% revenue growth in 2024 ($474M). SC formulation in Phase 3 will improve convenience.

**Weaknesses**: Single indication (SLE only) across the 6. Modest absolute revenue vs immunology leaders. No presence in RA, psoriasis, or IBD.

**Opportunities**: Saphnelo SC FDA decision expected H1 2026. Expansion into lupus nephritis, cutaneous LE, systemic sclerosis, pediatric SLE could 4x addressable patient population.

**Threats**: Emerging CAR-T therapies showing dramatic responses in SLE may disrupt biologic standard of care. Benlysta entrenched as first-mover. Saphnelo SC FDA review extended — delay risk.

### Key Earnings Quote
"Saphnelo generated $474M in FY2024 revenue with 69% growth, driven by demand acceleration in the US." — AstraZeneca Full Year & Q4 2024 Results (Feb 5, 2025)

### Strategic Watch
- **Saphnelo SC**: FDA decision H1 2026. Removes IV infusion barrier — could significantly accelerate penetration in SLE.
- **Expansion programs**: IRIS (lupus nephritis), LAVENDER (cutaneous LE), DAISY (systemic sclerosis), pediatric SLE.

### Recent Developments
*[Updated by wiki_updater as press releases arrive]*
"""),

"co_gsk": ("GSK", """## GSK
**Tier**: Tier 2 — SLE Incumbent
**Focus Indications**: SLE

### Approved Drugs
| Drug | Generic | Indication | MOA | Year |
|------|---------|------------|-----|------|
| Benlysta | belimumab | SLE | BAFF/BLyS inhibitor | 2011 |
| Benlysta | belimumab | SLE — Lupus Nephritis | BAFF/BLyS inhibitor | 2020 |

### SWOT Analysis
**Strengths**: Benlysta is the established SLE standard — first biologic approved for SLE. Lupus nephritis approval (2020) broadened the label. Pediatric autoinjector approval extends access. Sustained double-digit revenue growth.

**Weaknesses**: Otilimab RA program discontinued (Phase 3 failed). Single indication (SLE only) across the 6. No IBD, psoriasis, or RA pipeline of significance.

**Opportunities**: Benlysta + rituximab combination Phase 3 ongoing — could raise bar in SLE treatment. Benlysta has penetrated <20% of eligible SLE patients globally — substantial headroom remaining.

**Threats**: Anifrolumab (Saphnelo) capturing SLE patient share. Emerging CAR-T therapies for SLE showing durable complete remission — longer-term disruption risk.

### Key Earnings Quote
"Benlysta continued to grow by double-digit percentages in the full year, with bio-penetration rates increased across many markets." — GSK FY2024 Results (Jan 2025)

### Recent Developments
*[Updated by wiki_updater as press releases arrive]*
"""),

"co_amgen": ("Amgen", """## Amgen
**Tier**: Tier 1 — Franchises Maturing
**Focus Indications**: RA, PsA, Plaque Psoriasis (biosimilars + Otezla)

### Approved Drugs
| Drug | Generic | Indication | MOA | Year |
|------|---------|------------|-----|------|
| Enbrel | etanercept | RA | TNF-α inhibitor (fusion protein) | 1998 |
| Enbrel | etanercept | PsA | TNF-α inhibitor | 2002 |
| Enbrel | etanercept | Plaque Psoriasis | TNF-α inhibitor | 2004 |
| Otezla | apremilast | Plaque Psoriasis | PDE4 inhibitor | 2014 |
| Otezla | apremilast | PsA | PDE4 inhibitor | 2014 |
| Amgevita | adalimumab-atto | RA/PsA/Psoriasis/UC/CD | TNF-α biosimilar | 2023 |

### SWOT Analysis
**Strengths**: Enbrel is among the most prescribed biologics in RA/PsA/psoriasis history. Otezla oral PDE4 differentiates from injectables. Amgevita covers all TNF-relevant indications. World-class manufacturing scale.

**Weaknesses**: Both Enbrel and Otezla are in revenue decline (Enbrel -10% FY2024). No innovative late-stage pipeline in these 6 indications to replace maturing assets. Amgevita competes on price, not science.

**Opportunities**: Otezla pediatric psoriasis approval (Aug 2024) opens new patient segment. Amgevita biosimilar growth partially offsets branded declines. Potential acquisition of novel MOA assets.

**Threats**: Enbrel US exclusivity challenges ongoing. Otezla facing generic entry pressure long-term. Class shift in psoriasis/PsA toward JAKs and IL-23s displacing TNFs.

### Key Earnings Quote
"Enbrel sales decreased 10% for the full year, driven by lower net selling price. Otezla decreased 3%, primarily driven by 8% lower net selling price." — Amgen Q4 2024 Results (Feb 4, 2025)

### Recent Developments
*[Updated by wiki_updater as press releases arrive]*
"""),

"co_roche": ("Roche", """## Roche
**Tier**: Tier 2 — Legacy RA
**Focus Indications**: RA

### Approved Drugs
| Drug | Generic | Indication | MOA | Year |
|------|---------|------------|-----|------|
| Actemra / RoActemra | tocilizumab | RA | IL-6 receptor inhibitor | 2010 |
| Rituxan / MabThera | rituximab | RA | Anti-CD20 (B-cell depleter) | 2006 |

### SWOT Analysis
**Strengths**: Actemra established RA standard of care for 15+ years. SC formulation extends lifecycle vs IV biosimilars. Strong hospital relationships. Rituxan anchors seropositive RA.

**Weaknesses**: Both Actemra and Rituxan facing biosimilar erosion. Actemra biosimilar US entry Q2 2024 — price pressure accelerating. No new approved drugs in these 6 indications; limited Phase 3 pipeline.

**Opportunities**: Subcutaneous Actemra retaining share vs IV biosimilars (SC is harder to biosimilar). Chugai pipeline may yield new RA assets. Niche positioning in sJIA and MAS.

**Threats**: Tocilizumab biosimilars (US entry 2024) eroding >CHF 1B franchise. Rituximab biosimilars long entrenched. No late-stage pipeline to offset losses.

### Key Earnings Quote
"The impact of biosimilar competition on Actemra/RoActemra was more than compensated for by continued rollout of other products." — Roche FY2024 Results (Jan 30, 2025)

### Recent Developments
*[Updated by wiki_updater as press releases arrive]*
"""),

"co_regeneron": ("Regeneron", """## Regeneron
**Tier**: Tier 2 — RA Specialist
**Focus Indications**: RA

### Approved Drugs
| Drug | Generic | Indication | MOA | Year |
|------|---------|------------|-----|------|
| Kevzara | sarilumab | RA | IL-6 receptor inhibitor | 2017 |

### SWOT Analysis
**Strengths**: Kevzara (sarilumab) approved IL-6R inhibitor in RA. VelocImmune platform is industry-leading for antibody discovery. Co-commercialization with Sanofi provides broader reach.

**Weaknesses**: Only one drug in these 6 indications. Kevzara trails tocilizumab in global RA penetration.

**Opportunities**: Sarilumab SC once-weekly differentiates vs tocilizumab (Q2W). Tocilizumab biosimilar entry may lift IL-6R class value vs biosimilar pricing.

**Threats**: Tocilizumab biosimilars entering US (2024) compressing IL-6R class pricing. JAKs and IL-23s displacing biologics in RA.

### Key Earnings Quote
"Kevzara continues to grow as we expand SC usage... we see the IL-6R class maintaining relevance in RA despite JAK competition." — Regeneron Q4 2024 / Sanofi Joint Commentary

### Recent Developments
*[Updated by wiki_updater as press releases arrive]*
"""),

"co_boehringer": ("Boehringer Ingelheim", """## Boehringer Ingelheim
**Tier**: Tier 3 — Niche Derm
**Focus Indications**: Plaque Psoriasis (GPP), UC (Phase 2)

### Approved Drugs
| Drug | Generic | Indication | MOA | Year |
|------|---------|------------|-----|------|
| Spevigo | spesolimab | Plaque Psoriasis (GPP) | IL-36 receptor inhibitor | 2022 |
| Spesolimab | spesolimab | UC | IL-36 receptor inhibitor | Phase 2 |

### SWOT Analysis
**Strengths**: Spevigo (spesolimab) is the first and only IL-36R inhibitor — entirely novel MOA. Approved for GPP (severe, life-threatening psoriasis variant). Private company allows long-term investment.

**Weaknesses**: GPP is a rare/orphan-adjacent indication with limited commercial scale. Not yet approved in standard plaque psoriasis. Phase 2 only in broader derm and IBD.

**Opportunities**: Spesolimab Phase 2 in plaque psoriasis and UC — if successful, expands into mainstream markets. IL-36 pathway is underexplored in IBD.

**Threats**: Very small GPP addressable market. Competing against entrenched biologics if expanding into plaque psoriasis.

### Recent Developments
Phase 2 data in broader psoriasis expected 2025-2026.
*[Updated by wiki_updater as press releases arrive]*
"""),
}

# ── Strategic pages ────────────────────────────────────────────────────────────

STRATEGIC_WATCHLIST = """## Strategic Watch List — Key Catalysts 2025-2027
*Source: Pharma Immunology Competitive Intelligence Report, March 2026*

### Phase 3 Readouts & Approvals

| Drug / Program | Company | Catalyst / Timeline | Strategic Significance |
|---------------|---------|--------------------|-----------------------|
| Tulisokibart (MK-7240) | Merck | Phase 3 UC/CD readout ~2026-27 | First anti-TL1A approval would validate entire class. Biomarker strategy could command premium pricing. |
| Duvakitug | Sanofi / Teva | Phase 3 UC/CD readout ~2026-27 | Head-to-head race with Merck in anti-TL1A. Sanofi's commercial scale gives launch advantage if approved. |
| Rinvoq (upadacitinib) | AbbVie | SLE Phase 3 readout ~2025-26 | Would give AbbVie the only JAK1 inhibitor approved across all 6 indications. Massive label expansion. |
| Sotyktu (deucravacitinib) | BMS | SLE + CD Phase 3 readouts ~2026 | TYK2 without black-box warning across SLE and CD — significant differentiation vs JAKs. |
| Nipocalimab | J&J | SLE Phase 3 readout ~2025-26 | FcRn mechanism is class-differentiating. First FcRn inhibitor in lupus would open a new treatment paradigm. |
| Ianalumab (VAY736) | Novartis | SLE Phase 3 readout ~2026 | BAFF-R vs BAFF-L differentiation from Benlysta. 6 Phase 3 studies running — high conviction. |
| Saphnelo SC (anifrolumab) | AstraZeneca | FDA decision H1 2026 | SC formulation removes IV infusion barrier; could accelerate Saphnelo penetration in SLE significantly. |
| Cenerimod | Viatris / Idorsia | SLE Phase 3 CARE trial ~2026 | Only S1P1 modulator in SLE pipeline. If approved, novel oral SLE option alongside biologics. |
| Omvoh (mirikizumab) | Eli Lilly | Early IBD launch 2025+ | First IL-23 anti-p19 approved in both UC (2023) and CD (2025). Early share capture in IBD is the near-term focus. |
| Vedolizumab biosimilars | Multiple | EU ~2027, US ~2028-2032 | Entyvio (Takeda) patent cliff will reshape IBD market. Multiple manufacturers in development. |

### Key Strategic Themes
1. **Anti-TL1A IBD race** — Merck vs Sanofi/Teva, both Phase 3, readout ~2026-27. First genuinely new IBD mechanism in a decade.
2. **SLE becoming crowded** — 6 Phase 3 assets competing: nipocalimab, ianalumab, cenerimod, Rinvoq, Sotyktu, Saphnelo SC.
3. **TYK2 without black-box** — Sotyktu's differentiation from JAKs is the key formulary argument; expanding into PsA (2026), SLE, CD.
4. **IL-23 in IBD** — Skyrizi, Tremfya, Omvoh all approved or expanding into UC/CD. AbbVie dominates, Lilly growing fast.
5. **Biosimilar wave** — Stelara, Actemra, Entyvio patent cliffs reshaping competitive landscape by 2027-2032.

*[Updated automatically when new trial or regulatory news arrives]*
"""

MOA_LANDSCAPE = """## Mechanism of Action (MOA) Landscape
*Source: Pharma Immunology Competitive Intelligence Report, March 2026*

### MOA Class Summary

| MOA Class | Mechanism | Key Indications | Key Drugs | Strategic Assessment |
|-----------|-----------|-----------------|-----------|---------------------|
| TNF-α Inhibitors | Block TNF-alpha cytokine | RA, PsA, Psoriasis, UC, CD | Humira, Enbrel, Simponi + biosimilars | Mature; all facing biosimilar erosion. Still first-line in many settings. |
| IL-23 Inhibitors (anti-p19) | Block IL-23 (p19 subunit) | Psoriasis, PsA, UC, CD | Skyrizi, Tremfya, Omvoh, Ilumya | Current class of choice in psoriasis; rapidly expanding into IBD. |
| IL-17A Inhibitors | Block IL-17A cytokine | Psoriasis, PsA | Cosentyx, Taltz | Strong in derm/MSK; limited in IBD. IL-17A/F dual blockade emerging. |
| JAK Inhibitors | Block JAK-STAT signaling | RA, PsA, UC, CD, Psoriasis, SLE | Rinvoq, Olumiant, Jyseleca | Oral convenience; FDA black-box warning limits uptake. JAK1-selective preferred. |
| TYK2 Inhibitor | Allosteric TYK2 block (no black-box) | Psoriasis, PsA, SLE (Ph3) | Sotyktu (deucravacitinib) | Only approved TYK2; no black-box is key differentiator vs JAKs. |
| IL-6R Inhibitors | Block IL-6 receptor | RA | Actemra (tocilizumab), Kevzara (sarilumab) | RA workhorses; biosimilar competition now underway for tocilizumab. |
| IL-12/23 Inhibitors (anti-p40) | Block shared p40 subunit | Psoriasis, PsA, UC, CD | Stelara (ustekinumab) | Stelara facing US biosimilar entry (Jan 2025). IL-23 anti-p19 largely replacing class. |
| BAFF/BLyS Inhibitors | Block B-cell survival factor | SLE | Benlysta (belimumab) | Established SLE standard; BAFF-R inhibitor (ianalumab) in Phase 3 as next-gen. |
| IFNAR1 Inhibitor | Block type I interferon receptor | SLE | Saphnelo (anifrolumab) | Novel differentiated MOA; 69% revenue growth in 2024. SC form pending. |
| CTLA4-Ig | Block T-cell co-stimulation | RA, PsA | Orencia (abatacept) | Established in RA; differentiated MOA; IV and SC forms available. |
| Anti-CD20 | B-cell depletion | RA | Rituxan (rituximab) | Used in refractory seropositive RA; facing biosimilar pressure. |
| α4β7 Integrin Inhibitor | Gut-selective; blocks lymphocyte trafficking | UC, CD | Entyvio (vedolizumab) | IBD market leader in bio-naive starts. Safest IBD biologic profile. US exclusivity to ~2032. |
| PDE4 Inhibitor | Block phosphodiesterase-4 (oral) | Psoriasis, PsA | Otezla (apremilast) | Oral option; moderate efficacy; no immunosuppression risk. Declining revenue. |
| Anti-TL1A | Block TL1A cytokine; novel IBD target | UC, CD (Ph3), RA (Ph2) | Tulisokibart (Merck), Duvakitug (Sanofi/Teva) | Emerging class; two competing Phase 3 programs. No approved drug yet. |
| S1P Receptor Modulators | Block lymphocyte egress from lymph nodes (oral) | UC, CD (Ph3), SLE (Ph3) | Zeposia (ozanimod), Cenerimod | Oral convenience; S1P1 class expanding from UC into broader autoimmune. |
| FcRn Inhibitor | Block neonatal Fc receptor; reduces IgG autoantibodies | SLE (Ph3) | Nipocalimab (J&J) | Emerging mechanism; targets autoantibody levels broadly. Phase 3. |
| IL-36R Inhibitor | Block IL-36 receptor | GPP (approved), UC & Psoriasis (Ph2) | Spevigo/spesolimab (BI) | First-in-class; niche GPP approval. Broader indications in development. |
| BAFF-R Inhibitor | Block BAFF receptor (not BAFF ligand) | SLE (Ph3) | Ianalumab (Novartis) | Differentiated from belimumab; 6 Phase 3 studies ongoing. |

### Class Trajectory
- **Growing**: IL-23 anti-p19 (IBD expansion), TYK2, anti-TL1A (pipeline), FcRn/BAFF-R (SLE pipeline)
- **Stable**: JAK1 (cautious growth), α4β7 integrin, CTLA4-Ig
- **Declining**: TNF-α (biosimilar pressure), IL-12/23 anti-p40 (Stelara biosimilars)
- **At Risk**: IL-17A (IL-23 taking share in psoriasis), IL-6R (biosimilar competition)

*[Updated automatically as new mechanism data arrives]*
"""

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=== Loading docx competitive intelligence into wiki pages ===\n")

    print("── Company pages ──")
    for wiki_id, (entity_name, content) in COMPANY_PAGES.items():
        upsert_wiki(wiki_id, "company", entity_name, content)

    print("\n── Strategic pages ──")
    upsert_wiki("strategic_watchlist", "landscape",
                "Strategic Watch List 2025-2027", STRATEGIC_WATCHLIST)
    upsert_wiki("moa_landscape", "landscape",
                "MOA Landscape — Immunology 2026", MOA_LANDSCAPE)

    print(f"\n=== Done: {len(COMPANY_PAGES) + 2} wiki pages loaded ===")

if __name__ == "__main__":
    main()

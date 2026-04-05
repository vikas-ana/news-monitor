// ============================================================
// News Monitor — Neo4j Knowledge Graph Schema
// Run in Neo4j AuraDB Browser or via bolt driver
// ============================================================

// Constraints (unique nodes)
CREATE CONSTRAINT company_name IF NOT EXISTS FOR (c:Company) REQUIRE c.name IS UNIQUE;
CREATE CONSTRAINT drug_name IF NOT EXISTS FOR (d:Drug) REQUIRE d.name IS UNIQUE;
CREATE CONSTRAINT indication_name IF NOT EXISTS FOR (i:Indication) REQUIRE i.name IS UNIQUE;
CREATE CONSTRAINT moa_name IF NOT EXISTS FOR (m:MOA) REQUIRE m.name IS UNIQUE;

// Core Indications
MERGE (i1:Indication {name: 'Rheumatoid Arthritis', abbrev: 'RA', category: 'Autoimmune'})
MERGE (i2:Indication {name: 'Plaque Psoriasis', abbrev: 'PsO', category: 'Autoimmune'})
MERGE (i3:Indication {name: "Crohn's Disease", abbrev: 'CD', category: 'IBD'})
MERGE (i4:Indication {name: 'Ulcerative Colitis', abbrev: 'UC', category: 'IBD'});

// MOA nodes
MERGE (:MOA {name: 'TNF-α inhibitor'})
MERGE (:MOA {name: 'JAK1 inhibitor'})
MERGE (:MOA {name: 'JAK1/2 inhibitor'})
MERGE (:MOA {name: 'IL-23 inhibitor (anti-p19)'})
MERGE (:MOA {name: 'IL-12/23 inhibitor'})
MERGE (:MOA {name: 'IL-17A inhibitor'})
MERGE (:MOA {name: 'IL-6 receptor inhibitor'})
MERGE (:MOA {name: 'TYK2 inhibitor'})
MERGE (:MOA {name: 'Anti-TL1A monoclonal antibody'})
MERGE (:MOA {name: 'α4β7 integrin inhibitor'})
MERGE (:MOA {name: 'S1P1/5 receptor modulator'})
MERGE (:MOA {name: 'CTLA4-Ig'})
MERGE (:MOA {name: 'PDE4 inhibitor'});

// Companies
MERGE (:Company {name: 'AbbVie', hq: 'USA'})
MERGE (:Company {name: 'J&J (Janssen)', hq: 'USA'})
MERGE (:Company {name: 'Roche', hq: 'Switzerland'})
MERGE (:Company {name: 'Novartis', hq: 'Switzerland'})
MERGE (:Company {name: 'BMS', hq: 'USA'})
MERGE (:Company {name: 'Eli Lilly', hq: 'USA'})
MERGE (:Company {name: 'Sanofi', hq: 'France'})
MERGE (:Company {name: 'Amgen', hq: 'USA'})
MERGE (:Company {name: 'Takeda', hq: 'Japan'})
MERGE (:Company {name: 'Merck', hq: 'USA'})
MERGE (:Company {name: 'Gilead', hq: 'USA'})
MERGE (:Company {name: 'Boehringer Ingelheim', hq: 'Germany'});

// Key drugs with relationships — AbbVie
MERGE (d:Drug {name: 'Humira', generic: 'adalimumab'})
  WITH d MATCH (c:Company {name:'AbbVie'}), (m:MOA {name:'TNF-α inhibitor'})
  MERGE (c)-[:MARKETS]->(d) MERGE (d)-[:MECHANISM]->(m);

MERGE (d:Drug {name: 'Skyrizi', generic: 'risankizumab'})
  WITH d MATCH (c:Company {name:'AbbVie'}), (m:MOA {name:'IL-23 inhibitor (anti-p19)'})
  MERGE (c)-[:MARKETS]->(d) MERGE (d)-[:MECHANISM]->(m);

MERGE (d:Drug {name: 'Rinvoq', generic: 'upadacitinib'})
  WITH d MATCH (c:Company {name:'AbbVie'}), (m:MOA {name:'JAK1 inhibitor'})
  MERGE (c)-[:MARKETS]->(d) MERGE (d)-[:MECHANISM]->(m);

// J&J
MERGE (d:Drug {name: 'Stelara', generic: 'ustekinumab'})
  WITH d MATCH (c:Company {name:'J&J (Janssen)'}), (m:MOA {name:'IL-12/23 inhibitor'})
  MERGE (c)-[:MARKETS]->(d) MERGE (d)-[:MECHANISM]->(m);

MERGE (d:Drug {name: 'Tremfya', generic: 'guselkumab'})
  WITH d MATCH (c:Company {name:'J&J (Janssen)'}), (m:MOA {name:'IL-23 inhibitor (anti-p19)'})
  MERGE (c)-[:MARKETS]->(d) MERGE (d)-[:MECHANISM]->(m);

// Indications
MATCH (d:Drug {name:'Humira'}), (i:Indication {abbrev:'RA'}) MERGE (d)-[:APPROVED_FOR {year:'2002', status:'Approved'}]->(i);
MATCH (d:Drug {name:'Humira'}), (i:Indication {abbrev:'PsO'}) MERGE (d)-[:APPROVED_FOR {year:'2008', status:'Approved'}]->(i);
MATCH (d:Drug {name:'Humira'}), (i:Indication {abbrev:'CD'}) MERGE (d)-[:APPROVED_FOR {year:'2007', status:'Approved'}]->(i);
MATCH (d:Drug {name:'Humira'}), (i:Indication {abbrev:'UC'}) MERGE (d)-[:APPROVED_FOR {year:'2012', status:'Approved'}]->(i);
MATCH (d:Drug {name:'Skyrizi'}), (i:Indication {abbrev:'PsO'}) MERGE (d)-[:APPROVED_FOR {year:'2019', status:'Approved'}]->(i);
MATCH (d:Drug {name:'Skyrizi'}), (i:Indication {abbrev:'CD'}) MERGE (d)-[:APPROVED_FOR {year:'2022', status:'Approved'}]->(i);
MATCH (d:Drug {name:'Skyrizi'}), (i:Indication {abbrev:'UC'}) MERGE (d)-[:APPROVED_FOR {year:'2024', status:'Approved'}]->(i);
MATCH (d:Drug {name:'Rinvoq'}), (i:Indication {abbrev:'RA'}) MERGE (d)-[:APPROVED_FOR {year:'2019', status:'Approved'}]->(i);
MATCH (d:Drug {name:'Rinvoq'}), (i:Indication {abbrev:'UC'}) MERGE (d)-[:APPROVED_FOR {year:'2022', status:'Approved'}]->(i);
MATCH (d:Drug {name:'Rinvoq'}), (i:Indication {abbrev:'CD'}) MERGE (d)-[:APPROVED_FOR {year:'2023', status:'Approved'}]->(i);
MATCH (d:Drug {name:'Stelara'}), (i:Indication {abbrev:'PsO'}) MERGE (d)-[:APPROVED_FOR {year:'2009', status:'Approved'}]->(i);
MATCH (d:Drug {name:'Stelara'}), (i:Indication {abbrev:'CD'}) MERGE (d)-[:APPROVED_FOR {year:'2016', status:'Approved'}]->(i);
MATCH (d:Drug {name:'Stelara'}), (i:Indication {abbrev:'UC'}) MERGE (d)-[:APPROVED_FOR {year:'2019', status:'Approved'}]->(i);

// Competitor edges (same indication, same MOA class)
MATCH (d1:Drug {name:'Rinvoq'})-[:MECHANISM]->(m:MOA)<-[:MECHANISM]-(d2:Drug)
WHERE d1 <> d2
MERGE (d1)-[:COMPETES_WITH]->(d2);

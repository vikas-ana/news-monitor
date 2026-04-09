#!/usr/bin/env python3
"""
Load data from Supabase into Neo4j knowledge graph.
Uses official neo4j Python driver (Bolt protocol — works on AuraDB Free).
"""

import os, json, subprocess, sys, time

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
NEO4J_URI    = os.environ.get("NEO4J_URI", "neo4j+s://e56a592d.databases.neo4j.io")
NEO4J_USER   = os.environ["NEO4J_USER"]
NEO4J_PASS   = os.environ["NEO4J_PASS"]

def supabase_get(table, params=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}&limit=1000"
    r = subprocess.run(["curl", "-s", "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Accept: application/json", url],
        capture_output=True, text=True, timeout=30)
    try:    return json.loads(r.stdout)
    except: return []

def run_neo4j(driver, cypher, params=None):
    with driver.session() as s:
        s.run(cypher, parameters=params or {})

def batch(lst, n=50):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def load_drug_profiles(driver):
    print("\n── Loading drug profiles ──")
    rows = supabase_get("drug_profiles", "select=*")
    if not isinstance(rows, list): return 0
    loaded = 0
    for chunk in batch(rows):
        with driver.session() as s:
            for r in chunk:
                # Supabase columns: brand_name, generic_name, moa, status, indication, company
                drug = (r.get("brand_name") or r.get("generic_name") or "").strip()
                if not drug: continue
                moa_val  = (r.get("moa") or r.get("mechanism_of_action") or "").strip()
                phase_val = (r.get("status") or r.get("highest_phase") or "").strip()
                s.run("""
                    MERGE (d:Drug {name: $drug})
                    SET d.brand_name=$brand, d.generic_name=$generic,
                        d.highest_phase=$phase, d.mechanism_of_action=$moa,
                        d.updated_at=datetime()
                """, drug=drug, brand=r.get("brand_name",""),
                     generic=r.get("generic_name",""),
                     phase=phase_val, moa=moa_val)
                if r.get("company"):
                    s.run("""
                        MERGE (c:Company {name:$company})
                        WITH c MATCH (d:Drug {name:$drug}) MERGE (c)-[:DEVELOPS]->(d)
                    """, company=r["company"].strip(), drug=drug)
                if r.get("indication"):
                    s.run("""
                        MERGE (i:Indication {name:$ind})
                        WITH i MATCH (d:Drug {name:$drug}) MERGE (d)-[:TARGETS]->(i)
                    """, ind=r["indication"].strip(), drug=drug)
                if moa_val:
                    s.run("""
                        MERGE (m:MOA {name:$moa})
                        WITH m MATCH (d:Drug {name:$drug}) MERGE (d)-[:HAS_MECHANISM]->(m)
                    """, moa=moa_val, drug=drug)
                loaded += 1
    print(f"[OK] {loaded}/{len(rows)} drug profiles")
    return loaded

def load_swot(driver):
    print("\n── Loading SWOT intelligence ──")
    rows = supabase_get("swot_intel", "select=*")
    if not isinstance(rows, list): return 0
    loaded = 0
    with driver.session() as s:
        for r in rows:
            # Supabase swot_intel columns: company, category (strength/weakness/...),
            # detail, source_date.  SWOT is company-level, not drug-level.
            company = (r.get("company") or "").strip()
            swot    = (r.get("category") or r.get("swot_type") or "").strip()
            content = (r.get("detail") or r.get("content") or "").strip()
            if not company or not swot: continue
            key = f"{company}::{swot}::{content[:80]}"
            s.run("""
                MERGE (c:Company {name:$company})
                MERGE (e:SWOTEntry {key:$key})
                SET e.swot_type=$swot, e.content=$content,
                    e.company=$company, e.source_date=$src
                MERGE (c)-[:HAS_SWOT]->(e)
            """, company=company, key=key, swot=swot,
                 content=content[:500],
                 src=(r.get("source_date") or ""))
            loaded += 1
    print(f"[OK] {loaded}/{len(rows)} SWOT entries")
    return loaded

def load_articles(driver):
    print("\n── Loading processed articles ──")
    rows = supabase_get("articles",
        "select=id,catchy_title,raw_title,product_name,company,indication,"
        "category,relevance_score,article_date,url"
        "&processed_at=not.is.null&product_name=not.is.null")
    if not isinstance(rows, list): return 0
    loaded = 0
    with driver.session() as s:
        for r in rows:
            aid = str(r.get("id",""))
            if not aid: continue
            title = (r.get("catchy_title") or r.get("raw_title") or "")[:200]
            s.run("""
                MERGE (a:Article {article_id:$id})
                SET a.title=$title, a.category=$cat,
                    a.relevance_score=$score, a.article_date=$date, a.url=$url
            """, id=aid, title=title, cat=r.get("category",""),
                 score=r.get("relevance_score"), date=r.get("article_date",""),
                 url=r.get("url",""))
            if r.get("product_name"):
                s.run("""
                    MERGE (d:Drug {name:$drug})
                    WITH d MATCH (a:Article {article_id:$id}) MERGE (a)-[:MENTIONS]->(d)
                """, drug=r["product_name"].strip(), id=aid)
            if r.get("company"):
                s.run("""
                    MERGE (c:Company {name:$co})
                    WITH c MATCH (a:Article {article_id:$id}) MERGE (a)-[:PUBLISHED_BY]->(c)
                """, co=r["company"].strip(), id=aid)
            if r.get("indication"):
                s.run("""
                    MERGE (i:Indication {name:$ind})
                    WITH i MATCH (a:Article {article_id:$id}) MERGE (a)-[:COVERS]->(i)
                """, ind=r["indication"].strip(), id=aid)
            loaded += 1
    print(f"[OK] {loaded}/{len(rows)} articles")
    return loaded

def create_competition_edges(driver):
    print("\n── Creating competition edges ──")
    with driver.session() as s:
        s.run("""
            MATCH (d1:Drug)-[:TARGETS]->(i:Indication)<-[:TARGETS]-(d2:Drug)
            WHERE d1.name < d2.name
            MERGE (d1)-[:COMPETES_WITH]-(d2)
        """)
    print("[OK] Competition edges done")

def main():
    from neo4j import GraphDatabase
    print("=== Neo4j Knowledge Graph Loader ===")
    print(f"Connecting to {NEO4J_URI}")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    try:
        driver.verify_connectivity()
        print("[OK] Neo4j connected")
    except Exception as e:
        print(f"[FATAL] Cannot connect: {e}")
        sys.exit(1)

    d = load_drug_profiles(driver)
    s = load_swot(driver)
    a = load_articles(driver)
    create_competition_edges(driver)
    driver.close()
    print(f"\n=== Done: {d} drugs | {s} SWOT | {a} articles ===")

if __name__ == "__main__":
    main()

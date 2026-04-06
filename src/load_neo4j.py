#!/usr/bin/env python3
"""
Load data from Supabase into Neo4j knowledge graph.
Runs in GitHub Actions (no proxy restrictions).
Loads: drug_profiles, swot_intel, articles
"""

import os
import json
import subprocess
import sys
import time

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]
NEO4J_URI = os.environ.get("NEO4J_URI", "neo4j+s://e56a592d.databases.neo4j.io")
NEO4J_USER = os.environ["NEO4J_USER"]
NEO4J_PASS = os.environ["NEO4J_PASS"]
NEO4J_HTTP = NEO4J_URI.replace("neo4j+s://", "https://") + "/db/neo4j/tx/commit"

def supabase_get(table, params=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}?{params}&limit=1000"
    result = subprocess.run([
        "curl", "-s", "-H", f"apikey: {SUPABASE_KEY}",
        "-H", f"Authorization: Bearer {SUPABASE_KEY}",
        "-H", "Accept: application/json", url
    ], capture_output=True, text=True, timeout=30)
    try:
        return json.loads(result.stdout)
    except Exception as e:
        print(f"[WARN] Supabase parse error for {table}: {e}")
        return []

def neo4j_run(statements):
    payload = json.dumps({
        "statements": [{"statement": s["cypher"], "parameters": s.get("params", {})}
                       for s in statements]
    })
    result = subprocess.run([
        "curl", "-s", "-X", "POST",
        "-H", "Content-Type: application/json",
        "-H", "Accept: application/json",
        "-u", f"{NEO4J_USER}:{NEO4J_PASS}",
        NEO4J_HTTP,
        "-d", payload
    ], capture_output=True, text=True, timeout=60)
    try:
        data = json.loads(result.stdout)
        errors = data.get("errors", [])
        if errors:
            print(f"[NEO4J ERROR] {errors}")
            return False
        return True
    except Exception as e:
        print(f"[NEO4J PARSE ERROR] {e}\nRaw: {result.stdout[:500]}")
        return False

def batch(lst, size=25):
    for i in range(0, len(lst), size):
        yield lst[i:i+size]

def load_drug_profiles():
    print("\n── Loading drug profiles ──")
    rows = supabase_get("drug_profiles", "select=*")
    if not isinstance(rows, list):
        print(f"[ERROR] {rows}")
        return 0
    loaded = 0
    for chunk in batch(rows):
        stmts = []
        for r in chunk:
            drug = (r.get("drug_name") or "").strip()
            if not drug:
                continue
            company  = (r.get("company") or "").strip()
            indication = (r.get("indication") or "").strip()
            moa      = (r.get("mechanism_of_action") or "").strip()
            phase    = (r.get("highest_phase") or "").strip()
            brand    = (r.get("brand_name") or "").strip()
            stmts.append({"cypher": """
                MERGE (d:Drug {name: $drug})
                SET d.brand_name=$brand, d.highest_phase=$phase,
                    d.mechanism_of_action=$moa, d.updated_at=datetime()
            """, "params": {"drug":drug,"brand":brand,"phase":phase,"moa":moa}})
            if company:
                stmts.append({"cypher": """
                    MERGE (c:Company {name:$company})
                    WITH c MATCH (d:Drug {name:$drug}) MERGE (c)-[:DEVELOPS]->(d)
                """, "params": {"company":company,"drug":drug}})
            if indication:
                stmts.append({"cypher": """
                    MERGE (i:Indication {name:$indication})
                    WITH i MATCH (d:Drug {name:$drug}) MERGE (d)-[:TARGETS]->(i)
                """, "params": {"indication":indication,"drug":drug}})
            if moa:
                stmts.append({"cypher": """
                    MERGE (m:MOA {name:$moa})
                    WITH m MATCH (d:Drug {name:$drug}) MERGE (d)-[:HAS_MECHANISM]->(m)
                """, "params": {"moa":moa,"drug":drug}})
        if stmts and neo4j_run(stmts):
            loaded += len(chunk)
        time.sleep(0.5)
    print(f"[OK] {loaded}/{len(rows)} drug profiles loaded")
    return loaded

def load_swot():
    print("\n── Loading SWOT intelligence ──")
    rows = supabase_get("swot_intel", "select=*")
    if not isinstance(rows, list):
        print(f"[ERROR] {rows}")
        return 0
    loaded = 0
    for chunk in batch(rows):
        stmts = []
        for r in chunk:
            drug     = (r.get("drug_name") or "").strip()
            swot_type = (r.get("swot_type") or "").strip()
            content  = (r.get("content") or "").strip()
            company  = (r.get("company") or "").strip()
            if not drug or not swot_type:
                continue
            key = f"{drug}::{swot_type}::{content[:80]}"
            stmts.append({"cypher": """
                MERGE (d:Drug {name:$drug})
                MERGE (s:SWOTEntry {key:$key})
                SET s.swot_type=$swot_type, s.content=$content, s.company=$company
                MERGE (d)-[:HAS_SWOT]->(s)
            """, "params": {"drug":drug,"key":key,"swot_type":swot_type,
                            "content":content[:500],"company":company}})
        if stmts and neo4j_run(stmts):
            loaded += len(chunk)
        time.sleep(0.5)
    print(f"[OK] {loaded}/{len(rows)} SWOT entries loaded")
    return loaded

def load_articles():
    print("\n── Loading processed articles ──")
    rows = supabase_get("articles",
        "select=id,catchy_title,raw_title,product_name,company,indication,category,relevance_score,article_date,url"
        "&processed_at=not.is.null&product_name=not.is.null")
    if not isinstance(rows, list):
        print(f"[ERROR] {rows}")
        return 0
    loaded = 0
    for chunk in batch(rows, 20):
        stmts = []
        for r in chunk:
            art_id = str(r.get("id",""))
            title  = (r.get("catchy_title") or r.get("raw_title") or "")[:200]
            drug   = (r.get("product_name") or "").strip()
            company= (r.get("company") or "").strip()
            ind    = (r.get("indication") or "").strip()
            cat    = (r.get("category") or "").strip()
            score  = r.get("relevance_score")
            date   = r.get("article_date") or ""
            url    = r.get("url") or ""
            if not art_id:
                continue
            stmts.append({"cypher": """
                MERGE (a:Article {article_id:$id})
                SET a.title=$title, a.category=$cat,
                    a.relevance_score=$score, a.article_date=$date, a.url=$url
            """, "params": {"id":art_id,"title":title,"cat":cat,"score":score,"date":date,"url":url}})
            if drug:
                stmts.append({"cypher": """
                    MERGE (d:Drug {name:$drug})
                    WITH d MATCH (a:Article {article_id:$id}) MERGE (a)-[:MENTIONS]->(d)
                """, "params": {"drug":drug,"id":art_id}})
            if company:
                stmts.append({"cypher": """
                    MERGE (c:Company {name:$company})
                    WITH c MATCH (a:Article {article_id:$id}) MERGE (a)-[:PUBLISHED_BY]->(c)
                """, "params": {"company":company,"id":art_id}})
            if ind:
                stmts.append({"cypher": """
                    MERGE (i:Indication {name:$ind})
                    WITH i MATCH (a:Article {article_id:$id}) MERGE (a)-[:COVERS]->(i)
                """, "params": {"ind":ind,"id":art_id}})
        if stmts and neo4j_run(stmts):
            loaded += len(chunk)
        time.sleep(0.5)
    print(f"[OK] {loaded}/{len(rows)} articles loaded")
    return loaded

def create_competition_edges():
    print("\n── Creating competition edges ──")
    ok = neo4j_run([{"cypher": """
        MATCH (d1:Drug)-[:TARGETS]->(i:Indication)<-[:TARGETS]-(d2:Drug)
        WHERE d1.name < d2.name
        MERGE (d1)-[:COMPETES_WITH]-(d2)
    """}])
    print("[OK] Competition edges done" if ok else "[WARN] Competition edges failed")

def main():
    print("=== Neo4j Knowledge Graph Loader ===")
    print(f"Target: {NEO4J_HTTP}")
    ok = neo4j_run([{"cypher": "RETURN 1 AS ok"}])
    if not ok:
        print("[FATAL] Cannot connect to Neo4j. Check NEO4J_USER / NEO4J_PASS / NEO4J_URI.")
        sys.exit(1)
    print("[OK] Neo4j connected")
    d = load_drug_profiles()
    s = load_swot()
    a = load_articles()
    create_competition_edges()
    print(f"\n=== Summary: {d} drugs | {s} SWOT | {a} articles ===")

if __name__ == "__main__":
    main()

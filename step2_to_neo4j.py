"""
STEP 2: Enhance JSONs and insert into Neo4j
Run: python step2_to_neo4j.py
"""

import json, re, os, sys, pathlib, unicodedata
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j123")

JSON_DIR   = pathlib.Path("jsons")
OUTPUT_DIR = pathlib.Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

LEGAL_KEYWORDS_AR = [
    "عقوبة","غرامة","حبس","سجن","مصادرة","تعويض","ترخيص","تصريح",
    "تعريف","حظر","يحظر","يجوز","يلتزم","يُعاقب","مادة","إلغاء",
    "تعديل","إضافة","حقوق","واجبات","التزام","جريمة","محكمة","قاضي",
    "نيابة","استئناف","حكم","قرار","وزير","رئيس","تسجيل","شهادة",
    "رهن","ضمان","إشهار","أولوية","استيراد","تصدير","عبور","شحنة",
    "صناعي","تبريد","مرخص له","مشترك","مستهلك","كهربائية","مائية",
    "منشآت","حماية",
]

def normalize(text):
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_article_number(title):
    m = re.search(r"(\d+)", title)
    if m:
        return m.group(1)
    m2 = re.search(r"المادة\s+[-–]?\s*(.+)$", title)
    if m2:
        return m2.group(1).strip()
    return title

def extract_keywords(text):
    return list(dict.fromkeys(kw for kw in LEGAL_KEYWORDS_AR if kw in text))

def infer_law_type(text):
    if "تعديل" in text: return "amendment"
    if "إصدار" in text: return "promulgation"
    if "إلغاء" in text: return "repeal"
    return "original"

def build_law_id(file_stem, meta):
    num = meta.get("رقم", "")
    year_raw = meta.get("التاریخ", meta.get("التاريخ", ""))
    year_m = re.search(r"(\d{4})", year_raw)
    year = year_m.group(1) if year_m else "unknown"
    if not num:
        nm = re.search(r"(\d+)", file_stem)
        num = nm.group(1) if nm else file_stem
    return f"law_{num}_{year}"

def extract_references(preamble, body_text):
    all_text = " ".join(preamble) + " " + body_text
    law_pat = re.compile(r"قانون\s+رقم\s*\((\d+)\)\s*لسنة\s*(\d{4})")
    refs = list(dict.fromkeys(
        f"law_{m.group(1)}_{m.group(2)}" for m in law_pat.finditer(all_text)
    ))
    amends  = refs if ("يستبدل" in all_text or "بتعديل" in all_text) else []
    repeals = refs if ("يُلغى" in all_text or "يلغى" in all_text) else []
    return {"amends": amends, "repeals": repeals, "references": refs}

def enhance_law(data, file_stem):
    meta     = data.get("بطاقة_التشریع", {})
    preamble = data.get("دیباجة", [])
    law_id   = build_law_id(file_stem, meta)

    num = meta.get("رقم", "")
    year_raw = meta.get("التاریخ", meta.get("التاريخ", ""))
    year_m = re.search(r"(\d{4})", year_raw)
    year = year_m.group(1) if year_m else ""
    title = f"قانون رقم ({num}) لسنة {year}" if num and year else ""

    meta["_law_id"]   = law_id
    meta["_title"]    = title
    meta["_law_type"] = infer_law_type(title + " ".join(preamble))

    all_body = []
    for ch in data.get("فصول", []):
        for art in ch.get("مواد", []):
            all_body.extend(art.get("نص", []))
    for art in data.get("مواد", []):
        all_body.extend(art.get("نص", []))

    refs = extract_references(preamble, " ".join(all_body))
    meta["_amends"]     = refs["amends"]
    meta["_repeals"]    = refs["repeals"]
    meta["_references"] = refs["references"]

    def enrich_article(art, chapter_title=""):
        full_text = normalize(" ".join(art.get("نص", [])))
        art["full_text"]      = full_text
        art["article_number"] = extract_article_number(art.get("عنوان_المادة", ""))
        art["chapter_title"]  = chapter_title
        art["keywords"]       = extract_keywords(full_text)
        art["char_count"]     = len(full_text)
        art["embedding_text"] = (
            f"قانون: {title}\n"
            + (f"الفصل: {chapter_title}\n" if chapter_title else "")
            + f"المادة: {art.get('عنوان_المادة', '')}\n"
            + f"النص: {full_text}"
        )
        art["law_id"] = law_id
        return art

    for i, ch in enumerate(data.get("فصول", []), 1):
        ch["chapter_index"] = i
        for art in ch.get("مواد", []):
            enrich_article(art, ch.get("عنوان_الفصل", ""))
    for art in data.get("مواد", []):
        enrich_article(art, "")

    data["بطاقة_التشریع"] = meta
    return data

def e(s):
    """Escape string for Cypher."""
    if s is None: return ""
    return str(s).replace("\\","\\\\").replace("'","\\'").replace("\n"," ")

def law_to_cypher(data):
    meta    = data.get("بطاقة_التشریع", {})
    law_id  = e(meta.get("_law_id"))
    title   = e(meta.get("_title", ""))
    status  = e(meta.get("الحالة",""))
    pub     = e(meta.get("النشر",""))
    num     = e(meta.get("رقم",""))
    preamble= e(" ".join(data.get("دیباجة",[])))
    ltype   = e(meta.get("_law_type","original"))

    stmts = [
        "CREATE CONSTRAINT law_id IF NOT EXISTS FOR (l:Law) REQUIRE l.law_id IS UNIQUE;",
        "CREATE CONSTRAINT article_uid IF NOT EXISTS FOR (a:Article) REQUIRE a.uid IS UNIQUE;",
        "CREATE CONSTRAINT chapter_uid IF NOT EXISTS FOR (c:Chapter) REQUIRE c.uid IS UNIQUE;",
        f"""MERGE (l:Law {{law_id: '{law_id}'}})
SET l.title='{title}', l.law_type='{ltype}', l.status='{status}',
    l.pub_date='{pub}', l.number='{num}', l.preamble='{preamble}',
    l.updated_at=datetime();""",
    ]

    def add_article(art, ch_uid=None):
        uid     = f"{law_id}_art_{e(art.get('article_number',''))}"
        title_a = e(art.get("عنوان_المادة",""))
        ftxt    = e(art.get("full_text",""))
        etxt    = e(art.get("embedding_text",""))
        kws     = ",".join(f"'{e(k)}'" for k in art.get("keywords",[]))
        ch_t    = e(art.get("chapter_title",""))
        stmts.append(f"""MERGE (a:Article {{uid:'{uid}'}})
SET a.title='{title_a}', a.article_number='{e(art.get("article_number",""))}',
    a.full_text='{ftxt}', a.embedding_text='{etxt}',
    a.chapter_title='{ch_t}', a.keywords=[{kws}],
    a.char_count={art.get("char_count",0)}, a.law_id='{law_id}';""")
        if ch_uid:
            stmts.append(f"MATCH (ch:Chapter {{uid:'{ch_uid}'}}),(a:Article {{uid:'{uid}'}}) MERGE (ch)-[:HAS_ARTICLE]->(a);")
        else:
            stmts.append(f"MATCH (l:Law {{law_id:'{law_id}'}}),(a:Article {{uid:'{uid}'}}) MERGE (l)-[:HAS_ARTICLE]->(a);")

    for ch in data.get("فصول",[]):
        ch_uid = f"{law_id}_ch_{ch.get('chapter_index',0)}"
        ch_t   = e(ch.get("عنوان_الفصل",""))
        ch_i   = ch.get("chapter_index",0)
        stmts.append(f"""MERGE (ch:Chapter {{uid:'{ch_uid}'}})
SET ch.title='{ch_t}', ch.chapter_index={ch_i}, ch.law_id='{law_id}';""")
        stmts.append(f"MATCH (l:Law {{law_id:'{law_id}'}}),(ch:Chapter {{uid:'{ch_uid}'}}) MERGE (l)-[:HAS_CHAPTER]->(ch);")
        for art in ch.get("مواد",[]):
            add_article(art, ch_uid)

    for art in data.get("مواد",[]):
        add_article(art, None)

    for ref in meta.get("_amends",[]):
        stmts.append(f"MERGE (r:Law {{law_id:'{e(ref)}'}}); MATCH (l:Law {{law_id:'{law_id}'}}),(r:Law {{law_id:'{e(ref)}'}}) MERGE (l)-[:AMENDS]->(r);")
    for ref in meta.get("_repeals",[]):
        stmts.append(f"MERGE (r:Law {{law_id:'{e(ref)}'}}); MATCH (l:Law {{law_id:'{law_id}'}}),(r:Law {{law_id:'{e(ref)}'}}) MERGE (l)-[:REPEALS]->(r);")

    return stmts

def insert_to_neo4j(all_statements):
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("❌ Run: pip install neo4j")
        return False

    print(f"Connecting to {NEO4J_URI}...")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    total, errors = 0, 0
    try:
        with driver.session() as session:
            for stmt in all_statements:
                stmt = stmt.strip()
                if not stmt: continue
                # Split multiple statements separated by ;
                parts = [p.strip() for p in stmt.split(";") if p.strip()]
                for part in parts:
                    try:
                        session.run(part)
                        total += 1
                    except Exception as ex:
                        errors += 1
                        print(f"  ⚠️  {ex}")
    finally:
        driver.close()
    print(f"  ✅ {total} statements executed, {errors} errors")
    return errors == 0

def export_jsonl(all_laws):
    out = OUTPUT_DIR / "articles_for_embedding.jsonl"
    count = 0
    with open(out, "w", encoding="utf-8") as f:
        for data in all_laws:
            meta = data.get("بطاقة_التشریع",{})
            for ch in data.get("فصول",[]):
                for art in ch.get("مواد",[]):
                    f.write(json.dumps({
                        "law_id":         meta.get("_law_id",""),
                        "law_title":      meta.get("_title",""),
                        "chapter":        art.get("chapter_title",""),
                        "article_number": art.get("article_number",""),
                        "article_title":  art.get("عنوان_المادة",""),
                        "full_text":      art.get("full_text",""),
                        "embedding_text": art.get("embedding_text",""),
                        "keywords":       art.get("keywords",[]),
                    }, ensure_ascii=False) + "\n")
                    count += 1
            for art in data.get("مواد",[]):
                f.write(json.dumps({
                    "law_id":         meta.get("_law_id",""),
                    "law_title":      meta.get("_title",""),
                    "chapter":        "",
                    "article_number": art.get("article_number",""),
                    "article_title":  art.get("عنوان_المادة",""),
                    "full_text":      art.get("full_text",""),
                    "embedding_text": art.get("embedding_text",""),
                    "keywords":       art.get("keywords",[]),
                }, ensure_ascii=False) + "\n")
                count += 1
    print(f"  ✅ {count} articles → {out}")

def main():
    json_files = sorted(JSON_DIR.glob("output*.json"))
    if not json_files:
        print(f"❌ No JSON files in {JSON_DIR}/  — run step1 first!")
        sys.exit(1)

    all_laws, all_stmts = [], []

    for jf in json_files:
        print(f"\n📄 {jf.name}")
        with open(jf, encoding="utf-8") as fp:
            data = json.load(fp)

        data = enhance_law(data, jf.stem)
        meta = data["بطاقة_التشریع"]
        print(f"  law_id  : {meta['_law_id']}")
        print(f"  type    : {meta['_law_type']}")
        print(f"  amends  : {meta['_amends']}")

        # Save enhanced JSON
        enh = OUTPUT_DIR / f"enhanced_{jf.name}"
        with open(enh, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)

        stmts = law_to_cypher(data)

        # Save individual Cypher file
        cypher_path = OUTPUT_DIR / f"cypher_{jf.stem}.cypher"
        with open(cypher_path, "w", encoding="utf-8") as fp:
            fp.write("\n\n".join(stmts))
        print(f"  ✅ Cypher saved → {cypher_path}")

        all_laws.append(data)
        all_stmts.extend(stmts)

    # Save combined Cypher
    combined = OUTPUT_DIR / "all_laws.cypher"
    with open(combined, "w", encoding="utf-8") as f:
        f.write("\n\n".join(all_stmts))
    print(f"\n✅ Combined Cypher → {combined}  ({len(all_stmts)} statements)")

    # Export JSONL for embeddings
    export_jsonl(all_laws)

    # Insert into Neo4j
    print(f"\n🔌 Inserting into Neo4j...")
    insert_to_neo4j(all_stmts)

    print("\n✅ Done! Your graph is ready.")

if __name__ == "__main__":
    main()
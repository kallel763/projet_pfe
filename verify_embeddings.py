"""
Verify the quality of embeddings stored in Neo4j.
Run after step3_embeddings.py completes.
Requires: pip install numpy scikit-learn neo4j
"""

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from neo4j import GraphDatabase

# 🔹 Neo4j config (must match step3)
URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "neo4j123"

# 🔹 Model config (must match step3)
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EXPECTED_DIM = 384

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))


def load_articles():
    """Load articles with embeddings from Neo4j."""
    with driver.session() as session:
        results = session.run("""
            MATCH (a:Article)
            WHERE a.embedding IS NOT NULL
            RETURN a.uid AS uid,
                   a.law_id AS law_id,
                   a.article_number AS article_number,
                   a.embedding_text AS embedding_text,
                   a.embedding AS embedding
        """)
        return [record.data() for record in results]


def cosine_sim(a, b) -> float:
    a = np.array(a).reshape(1, -1)
    b = np.array(b).reshape(1, -1)
    return cosine_similarity(a, b)[0][0]


def check_embedding_quality(articles: list[dict]):
    print("=" * 60)
    print("📊 EMBEDDING QUALITY CHECK (from Neo4j)")
    print(f"🤖 Model : {MODEL_NAME}")
    print(f"📐 Expected dim : {EXPECTED_DIM}")
    print("=" * 60)

    if not articles:
        print("❌ No articles with embeddings found!")
        print("   Run step3_embeddings.py first!")
        return

    first_emb = articles[0].get("embedding")
    if not first_emb:
        print("❌ No 'embedding' field found. Run step3_embeddings.py first!")
        return

    print(f"\n✓ Total articles   : {len(articles)}")
    print(f"✓ Detected dim     : {len(first_emb)}")
    print(f"✓ Sample (first 5) : {[round(v, 6) for v in first_emb[:5]]}")

    embeddings_array = np.array([art["embedding"] for art in articles])
    print(f"✓ Embedding mean   : {embeddings_array.mean():.6f}")
    print(f"✓ Embedding std    : {embeddings_array.std():.6f}")

    # ── 1. Validity ───────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("1️⃣  EMBEDDING VALIDITY")
    print("=" * 60)
    valid = sum(
        1 for emb in embeddings_array
        if len(emb) > 0 and not np.isnan(emb).any() and not np.isinf(emb).any()
    )
    validity_pct = (valid / len(articles)) * 100
    print(f"   Valid : {valid}/{len(articles)} ({validity_pct:.2f}%)")

    # ── 2. Dimensionality ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("2️⃣  DIMENSIONALITY")
    print("=" * 60)
    dims = set(len(art["embedding"]) for art in articles)
    dim_ok = dims == {EXPECTED_DIM}
    print(f"   Expected : {EXPECTED_DIM}")
    print(f"   Found    : {dims}")
    print(f"   Status   : {'✅ Correct' if dim_ok else '❌ Mismatch!'}")
    dim_score = 100 if dim_ok else 0

    # ── 3. Normalization ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("3️⃣  NORMALIZATION  (should be ≈ 1.0 for best cosine similarity)")
    print("=" * 60)
    norms = np.linalg.norm(embeddings_array, axis=1)
    mean_norm = norms.mean()
    norm_ok = abs(mean_norm - 1.0) < 0.05
    print(f"   Mean norm : {mean_norm:.4f}  {'✅ Normalized' if norm_ok else '⚠️  Not normalized'}")
    print(f"   Std norm  : {norms.std():.4f}")

    # ── 4. Similarity Distribution ────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("4️⃣  SIMILARITY DISTRIBUTION (random sample of 50)")
    print("=" * 60)
    sample_n = min(50, len(articles))
    idx = np.random.choice(len(articles), sample_n, replace=False)
    sample_emb = embeddings_array[idx]
    sim_mat = cosine_similarity(sample_emb)
    np.fill_diagonal(sim_mat, np.nan)
    print(f"   Mean sim : {np.nanmean(sim_mat):.4f}")
    print(f"   Max sim  : {np.nanmax(sim_mat):.4f}")
    print(f"   Min sim  : {np.nanmin(sim_mat):.4f}")

    # ── 5. Intra-law clustering ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("5️⃣  SEMANTIC CLUSTERING  (same-law articles should be similar)")
    print("=" * 60)
    law_groups: dict[str, list[int]] = {}
    for i, art in enumerate(articles):
        law_groups.setdefault(art["law_id"], []).append(i)

    intra_sims = []
    for indices in law_groups.values():
        if len(indices) < 2:
            continue
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                intra_sims.append(cosine_sim(
                    embeddings_array[indices[a]],
                    embeddings_array[indices[b]]
                ))

    if intra_sims:
        print(f"   Laws found               : {len(law_groups)}")
        print(f"   Intra-law pairs          : {len(intra_sims)}")
        print(f"   Avg intra-law similarity : {np.mean(intra_sims):.4f}  (higher = better ✅)")
    else:
        print("   ⚠️  Only 1 law found — cannot measure clustering.")

    # ── 6. Semantic Similarity Demo ───────────────────────────────────────────
    print("\n" + "=" * 60)
    print("6️⃣  SEMANTIC SIMILARITY DEMO")
    print("=" * 60)
    test = articles[0]
    test_emb = np.array(test["embedding"])

    sims = []
    for i, art in enumerate(articles[1:], 1):
        s = cosine_sim(test_emb, art["embedding"])
        sims.append((i, art["law_id"], art["article_number"], s))
    sims.sort(key=lambda x: x[3], reverse=True)

    print(f"\n   Test  : {test['law_id']} — Article {test['article_number']}")
    print(f"   Text  : {(test.get('embedding_text') or '')[:100]}...\n")
    print("   Top 5 most similar articles:")
    for rank, (i, law_id, art_num, sim) in enumerate(sims[:5], 1):
        print(f"   {rank}. {law_id} — Article {art_num}  (similarity={sim:.4f})")
        print(f"      {(articles[i].get('embedding_text') or '')[:80]}...")

    # ── 7. Overall Score ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("7️⃣  OVERALL SCORE")
    print("=" * 60)
    overall = (validity_pct + dim_score) / 2
    print(f"   Validity    : {validity_pct:.1f}%")
    print(f"   Consistency : {dim_score:.1f}%")
    print(f"   Overall     : {overall:.1f}%")

    if overall >= 95:
        print("\n   ✅ EXCELLENT — Embeddings are high quality and ready!")
    elif overall >= 85:
        print("\n   ✅ GOOD — Embeddings are usable.")
    elif overall >= 70:
        print("\n   ⚠️  FAIR — Some issues detected, review errors in step3.")
    else:
        print("\n   ❌ POOR — Re-run step3_embeddings.py.")

    print("\n" + "=" * 60)
    print("✅ Verification complete!")
    print("=" * 60)


if __name__ == "__main__":
    articles = load_articles()
    check_embedding_quality(articles)
    driver.close()
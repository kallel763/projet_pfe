from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer

# 🔹 Neo4j config
URI = "bolt://localhost:7687"
USER = "neo4j"
PASSWORD = "neo4j123"

driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))

# 🔹 Load embedding model
model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


# 🔹 Step 1: Create vector index on Article nodes
def create_article_index(tx):
    query = """
    CREATE VECTOR INDEX article_embeddings IF NOT EXISTS
    FOR (a:Article)
    ON (a.embedding)
    OPTIONS {indexConfig: {
      `vector.dimensions`: 384,
      `vector.similarity_function`: 'cosine'
    }}
    """
    tx.run(query)


# 🔹 Step 2: Fetch articles that need embedding
def get_articles(tx):
    query = """
    MATCH (a:Article)
    WHERE a.embedding_text IS NOT NULL AND a.embedding IS NULL
    RETURN a.uid AS uid, a.title AS title, a.embedding_text AS text
    """
    result = tx.run(query)
    return [record.data() for record in result]


# 🔹 Step 3: Store embedding on article
def update_embedding(tx, uid, embedding):
    query = """
    MATCH (a:Article {uid: $uid})
    SET a.embedding = $embedding
    """
    tx.run(query, uid=uid, embedding=embedding)


# 🔹 Main
with driver.session() as session:
    # Create index
    session.execute_write(create_article_index)
    print("✅ Vector index 'article_embeddings' created.\n")

    # Fetch articles
    articles = session.execute_read(get_articles)
    print(f"📄 Found {len(articles)} articles to embed.\n")

    # Embed each article
    for i, article in enumerate(articles):
        embedding = model.encode(article["text"]).tolist()
        session.execute_write(update_embedding, article["uid"], embedding)

        if (i + 1) % 10 == 0 or (i + 1) == len(articles):
            print(f"  Embedded {i + 1}/{len(articles)}")

driver.close()

print("\n✅ All article embeddings updated successfully!")
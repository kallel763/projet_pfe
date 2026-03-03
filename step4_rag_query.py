from neo4j import GraphDatabase
from sentence_transformers import SentenceTransformer
import requests

# =============================
# CONFIGURATION
# =============================

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4j123"

OLLAMA_MODEL = "mistral"
OLLAMA_URL = "http://localhost:11434/api/generate"

VECTOR_INDEX_NAME = "article_embeddings"

# =============================
# INITIALISATION
# =============================

driver = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD)
)

embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


# =============================
# HELPER: Discover node properties
# =============================

def get_node_properties():
    """Check what properties exist on nodes with embeddings."""
    query = """
    MATCH (n)
    WHERE n.embedding IS NOT NULL
    RETURN keys(n) AS props
    LIMIT 1
    """
    with driver.session() as session:
        result = session.run(query)
        record = result.single()
        if record:
            return record["props"]
    return []


# =============================
# VECTOR SEARCH FUNCTION
# =============================

def search_similar_laws(question, top_k=5):
    question_embedding = embedding_model.encode(question).tolist()

    query = f"""
    CALL db.index.vector.queryNodes(
        '{VECTOR_INDEX_NAME}',
        $top_k,
        $embedding
    )
    YIELD node, score
    RETURN node.title AS title,
           node.full_text AS content,
           node.chapter_title AS chapter,
           node.law_id AS law_id,
           score
    """

    with driver.session() as session:
        results = session.run(
            query,
            top_k=top_k,
            embedding=question_embedding
        )
        return [record.data() for record in results]


# =============================
# LLM CALL (STRICT MODE)
# =============================

def ask_llm(prompt):
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0
            }
        }
    )
    return response.json()["response"]


# =============================
# RAG PIPELINE
# =============================

def rag_pipeline(question):
    print("\n🔎 Searching in Neo4j...\n")
    docs = search_similar_laws(question)

    if not docs:
        return "No relevant documents found in database."

    # Debug: show retrieved docs
    print("📄 Retrieved Documents:\n")
    for doc in docs:
        print(f"Title: {doc.get('title', 'N/A')}")
        print(f"Score: {doc.get('score', 'N/A')}")
        print(doc.get("content", "[No content]"))
        print("-----")

    # Filter out None content
    valid_docs = [doc for doc in docs if doc.get("content")]

    if not valid_docs:
        return "Documents were found but had no text content."

    context = "\n\n".join([doc["content"] for doc in valid_docs])

    prompt = f"""You are a strict legal assistant.

You MUST answer ONLY using the provided context.
Answer in the SAME LANGUAGE as the question.

If the answer is not explicitly written in the context,
respond exactly with:
"I don't know based on the provided database."

Do NOT use your own knowledge.
Do NOT make assumptions.
Do NOT add external information.

Context:
{context}

Question:
{question}

Answer:
"""

    print("\n🧠 Generating answer...\n")
    answer = ask_llm(prompt)
    return answer


# =============================
# MAIN
# =============================

if __name__ == "__main__":
    user_question = input("Enter your question: ")
    result = rag_pipeline(user_question)
    print("\n📌 Final Answer:\n")
    print(result)
    driver.close()
import os
import requests
import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sentence_transformers import SentenceTransformer
from openai import OpenAI
from app.config import settings


_embedding_model = None

def get_embedding_model() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        
        _embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    return _embedding_model


qdrant_client = QdrantClient(
    url=settings.QDRANT_CLUSTER_ENDPOINT,
    api_key=settings.QDRANT_API_KEY
)

COLLECTION_NAME = "financial_documents"

def init_qdrant_collection():
    """Initializes the Qdrant collection with appropriate index settings."""
    try:
        collections_response = qdrant_client.get_collections()
        existing_names = [col.name for col in collections_response.collections]
        
        if COLLECTION_NAME not in existing_names:
            qdrant_client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=qdrant_models.VectorParams(
                    size=384,  
                    distance=qdrant_models.Distance.COSINE
                )
            )
    except Exception as e:
        
        print(f"Warning: Failed to auto-initialize Qdrant collection: {e}")

#Call collection builder on import
init_qdrant_collection()

def chunk_text(text: str, chunk_size: int = 700, overlap: int = 150) -> List[str]:
    """
    Slices textual content semantically by prioritizing paragraph breaks
    and falls back to sentence splits if elements exceed the limit.
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current_chunk = []
    current_length = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        
        if len(para) > chunk_size:
            sentences = para.replace(". ", ".\n").split("\n")
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if current_length + len(sent) > chunk_size:
                    if current_chunk:
                        chunks.append(" ".join(current_chunk))
                    
                    current_chunk = current_chunk[-1:] if current_chunk else []
                    current_length = sum(len(s) for s in current_chunk)
                current_chunk.append(sent)
                current_length += len(sent)
        else:
            if current_length + len(para) > chunk_size:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = current_chunk[-1:] if len(current_chunk) > 1 else []
                current_length = sum(len(s) for s in current_chunk)
            current_chunk.append(para)
            current_length += len(para)

    if current_chunk:
        chunks.append(" ".join(current_chunk))
        
    return chunks

def index_document_content(
    document_id: str, 
    text_content: str, 
    metadata: Dict[str, Any]
) -> int:
    """
    Extracts, chunks, embeds, and uploads document chunks to Qdrant vector database.
    Returns the total number of ingested chunks.
    """
    chunks = chunk_text(text_content)
    if not chunks:
        return 0
        
    model = get_embedding_model()
    embeddings = model.encode(chunks, show_progress_bar=False)
    
    points = []
    for idx, (chunk_text_str, vector) in enumerate(zip(chunks, embeddings)):
        point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{document_id}_{idx}"))
        payload = {
            "chunk_id": point_id,
            "document_id": document_id,
            "text": chunk_text_str,
            "title": metadata.get("title", "Unknown"),
            "company_name": metadata.get("company_name", "Unknown"),
            "document_type": metadata.get("document_type", "Unknown")
        }
        points.append(
            qdrant_models.PointStruct(
                id=point_id,
                vector=vector.tolist(),
                payload=payload
            )
        )
        
    qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )
    return len(points)

def delete_document_content(document_id: str):
    """Purges all stored text chunk vectors belonging to a specific document ID from Qdrant."""
    qdrant_client.delete(
        collection_name=COLLECTION_NAME,
        points_selector=qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="document_id",
                    match=qdrant_models.MatchValue(value=document_id)
                )
            ]
        )
    )

def rerank_results(query: str, retrieved_points: List[Any], top_n: int = 5) -> List[Any]:
    """
    Reranks vector search results using NVIDIA's hosted reranking model
    with a robust fallback to original cosine similarity scores if API fails.
    """
    if not retrieved_points:
        return []
        
    if not settings.API_KEY:
        
        return retrieved_points[:top_n]
        
    headers = {
        "Authorization": f"Bearer {settings.API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    passages = [{"text": p.payload.get("text", "")} for p in retrieved_points]

    if not passages:
        return retrieved_points[:top_n]

    url = "https://ai.api.nvidia.com/v1/retrieval/nvidia/reranking"
    payload = {
        "model": "nvidia/llama-3.2-nv-rerankqa-1b-v2",
        "query": {"text": query},
        "passages": passages,
        "top_n": top_n
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=8)
        if response.status_code == 200:
            reranked_data = response.json()
            
            rankings = reranked_data.get("rankings", [])
            
            ordered_points = []
            for rank_item in rankings:
                idx = rank_item.get("index")
                if idx is not None and idx < len(retrieved_points):
                    point = retrieved_points[idx]
                    
                    point.score = rank_item.get("logit_score", point.score)
                    ordered_points.append(point)
            return ordered_points
    except Exception as e:
        print(f"Reranking API error, falling back to original database rank: {e}")
        
    return retrieved_points[:top_n]

def search_semantic_chunks(query: str, company_name: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Performs embedding-based vector search in Qdrant, applies company filters,
    runs reranking from Top 20 to Top 5, and yields formatted chunk dicts.
    """
    model = get_embedding_model()
    query_vector = model.encode(query, show_progress_bar=False).tolist()
    
    
    query_filter = None
    if company_name:
        query_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="company_name",
                    match=qdrant_models.MatchValue(value=company_name)
                )
            ]
        )
        
    
    search_results = qdrant_client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=20
    )
    
    
    final_points = rerank_results(query, search_results, top_n=5)
    
    formatted_chunks = []
    for p in final_points:
        formatted_chunks.append({
            "chunk_id": p.id,
            "document_id": p.payload.get("document_id"),
            "text": p.payload.get("text"),
            "score": p.score,
            "title": p.payload.get("title"),
            "company_name": p.payload.get("company_name"),
            "document_type": p.payload.get("document_type")
        })
        
    return formatted_chunks

def generate_financial_insight(query: str, context_chunks: List[Dict[str, Any]]) -> str:
    """
    Synthesizes a response using NVIDIA's hosted Llama 3.1 70B model,
    grounded firmly in the provided financial document chunks.
    """
    if not context_chunks:
        return "No relevant financial documents were found in the database matching your query. Please index or check database files."
        
    if not settings.API_KEY:
        return "NVIDIA NIM API key is missing. System was unable to connect to Llama 3.1 model to generate a response."
        
    
    context_str = ""
    for idx, chunk in enumerate(context_chunks):
        context_str += f"[{idx+1}] File: {chunk['title']} (Company: {chunk['company_name']}, Type: {chunk['document_type']})\nContent: {chunk['text']}\n\n"
        
    system_prompt = (
        "You are an expert financial analyst. Answer the user's question clearly, precisely, "
        "and analytically based ONLY on the provided financial documents context. "
        "Reference sources using bracketed numbers [1], [2], etc., corresponding to the documents. "
        "If the query cannot be answered using the provided context, state that clearly."
    )
    
    user_prompt = f"Context Documents:\n{context_str}\nQuestion: {query}\n\nFinancial Insight:"
    
    try:
        client = OpenAI(
            api_key=settings.API_KEY,
            base_url="https://integrate.api.nvidia.com/v1"
        )
        
        response = client.chat.completions.create(
            model="meta/llama-3.1-70b-instruct",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
            max_tokens=1024
        )
        
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Failed to synthesize answer due to LLM endpoint error: {e}"

def get_document_context_summary(document_id: str) -> Dict[str, Any]:
    """Retrieves document chunks matching a document ID and generates a short summary/preview."""
    try:
        scroll_results, _ = qdrant_client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=qdrant_models.Filter(
                must=[
                    qdrant_models.FieldCondition(
                        key="document_id",
                        match=qdrant_models.MatchValue(value=document_id)
                    )
                ]
            ),
            limit=50,
            with_payload=True,
            with_vectors=False
        )
        
        chunks_count = len(scroll_results)
        if chunks_count == 0:
            return {"document_id": document_id, "chunks_count": 0, "text_preview": "No indexed content found."}
            
        
        preview_text = " ".join([p.payload.get("text", "") for p in scroll_results[:2]])
        if len(preview_text) > 400:
            preview_text = preview_text[:397] + "..."
            
        return {
            "document_id": document_id,
            "chunks_count": chunks_count,
            "text_preview": preview_text
        }
    except Exception as e:
        return {"document_id": document_id, "chunks_count": 0, "text_preview": f"Error: {e}"}

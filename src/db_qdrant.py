from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
import os
from openai import AzureOpenAI
from dotenv import load_dotenv, find_dotenv
from langfuse import observe
from langfuse.decorators import langfuse_context
import hashlib

load_dotenv(find_dotenv())
qdrant = QdrantClient(
    host=os.getenv("QDRANT_HOST"),
    port=int(os.getenv("QDRANT_PORT")),
)

azure_client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_version=os.getenv("AZURE_OPENAI_API_VERSION")
)

@observe()
def embed_and_store(posts):
    """Create embeddings and store posts in Qdrant vector database."""
    langfuse_context.update_current_observation(
        input={"posts_count": len(posts)},
        metadata={"collection_name": "posts", "embedding_model": "text-embedding-3-large"}
    )
    
    try:
        embedded_count = 0
        skipped_count = 0
        total_tokens = 0
        
        for i, p in enumerate(posts):
            if not p["content"]:
                skipped_count += 1
                continue
                
            # Create embeddings with observability
            with langfuse_context.observation(name=f"create_embedding_{i+1}") as obs:
                obs.update(
                    input={"text_length": len(p["content"])},
                    metadata={"post_title": p.get("title", "No title")}
                )
                
                emb_response = azure_client.embeddings.create(
                    input=p["content"],
                    model="text-embedding-3-large"
                )
                
                emb = emb_response.data[0].embedding
                tokens_used = emb_response.usage.total_tokens
                total_tokens += tokens_used
                
                obs.update(
                    output={"embedding_dimension": len(emb), "tokens_used": tokens_used}
                )

            # Create unique ID based on content hash
            content_hash = hashlib.md5(p["content"].encode()).hexdigest()
            unique_id = f"{i}_{content_hash[:8]}"
            
            # Store in Qdrant
            with langfuse_context.observation(name=f"store_qdrant_{i+1}") as obs:
                obs.update(input={"point_id": unique_id, "vector_dim": len(emb)})
                
                qdrant.upsert(
                    collection_name="posts",
                    points=[PointStruct(id=unique_id, vector=emb, payload=p)]
                )
                
                obs.update(output={"status": "stored"})
                embedded_count += 1
        
        langfuse_context.update_current_observation(
            output={
                "embedded_count": embedded_count,
                "skipped_count": skipped_count,
                "total_tokens_used": total_tokens
            },
            metadata={
                "success_rate": embedded_count / len(posts) if posts else 0,
                "avg_tokens_per_post": total_tokens / embedded_count if embedded_count > 0 else 0
            }
        )
        
    except Exception as e:
        langfuse_context.update_current_observation(
            output={"error": str(e)},
            level="ERROR"
        )
        raise

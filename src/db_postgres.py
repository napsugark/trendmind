
import psycopg2
import os
from langfuse import observe
from langfuse.decorators import langfuse_context

@observe()
def connect_postgres():
    """Connect to PostgreSQL database with observability."""
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host=os.getenv("POSTGRES_HOST"),
            port=os.getenv("POSTGRES_PORT"),
        )
        
        langfuse_context.update_current_observation(
            output={"status": "connected"},
            metadata={
                "database": os.getenv("POSTGRES_DB"),
                "host": os.getenv("POSTGRES_HOST"),
                "port": os.getenv("POSTGRES_PORT")
            }
        )
        
        return conn
        
    except Exception as e:
        langfuse_context.update_current_observation(
            output={"error": str(e)},
            level="ERROR"
        )
        raise

@observe()
def insert_posts(conn, posts):
    """Insert posts into PostgreSQL with batch tracking."""
    langfuse_context.update_current_observation(
        input={"posts_count": len(posts)},
        metadata={"operation": "bulk_insert"}
    )
    
    try:
        cur = conn.cursor()
        inserted_count = 0
        
        for i, p in enumerate(posts):
            cur.execute("""
                INSERT INTO posts (source_url, title, content, published)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING;
            """, (p["source"], p["title"], p["content"], p["published"]))
            
            if cur.rowcount > 0:
                inserted_count += 1
        
        conn.commit()
        cur.close()
        
        langfuse_context.update_current_observation(
            output={
                "inserted_count": inserted_count,
                "duplicate_count": len(posts) - inserted_count
            },
            metadata={
                "success_rate": inserted_count / len(posts) if posts else 0
            }
        )
        
    except Exception as e:
        langfuse_context.update_current_observation(
            output={"error": str(e)},
            level="ERROR"
        )
        raise

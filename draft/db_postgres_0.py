
import psycopg2
import os
import time
from utils.logger import get_logger, log_performance, log_database_metrics

@log_performance
def connect_postgres():
    """Connect to PostgreSQL database with observability."""
    logger = get_logger("database")
    logger.info(f"Connecting to PostgreSQL database: {os.getenv('POSTGRES_DB')}")
    
    try:
        conn = psycopg2.connect(
            dbname=os.getenv("POSTGRES_DB"),
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            host=os.getenv("POSTGRES_HOST"),
            port=os.getenv("POSTGRES_PORT"),
        )
        
        logger.info("Successfully connected to PostgreSQL")
        
        return conn
        
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {str(e)}")
        raise

# @log_performance
# def insert_posts(conn, posts):
#     """Insert posts into PostgreSQL with batch tracking."""
#     logger = get_logger("database")
#     logger.info(f"Starting bulk insert of {len(posts)} posts")
    
#     start_time = time.time()
    
#     try:
#         cur = conn.cursor()
#         inserted_count = 0
        
#         for i, p in enumerate(posts):
#             cur.execute("""
#                 INSERT INTO posts (source_url, title, content, published)
#                 VALUES (%s, %s, %s, %s)
#                 ON CONFLICT DO NOTHING;
#             """, (p["source"], p["title"], p["content"], p["published"]))
            
#             if cur.rowcount > 0:
#                 inserted_count += 1
                
#         conn.commit()
#         cur.close()
        
#         execution_time = time.time() - start_time
#         duplicate_count = len(posts) - inserted_count
        
#         logger.info(f"Bulk insert completed: {inserted_count} inserted, {duplicate_count} duplicates")
        
#         # Log detailed metrics
#         log_database_metrics(
#             operation="insert",
#             records_processed=len(posts),
#             records_successful=inserted_count,
#             execution_time=execution_time
#         )
        
#     except Exception as e:
#         execution_time = time.time() - start_time
#         logger.error(f"Bulk insert failed after {execution_time:.2f}s: {str(e)}")
        
#         # Log failed operation metrics
#         log_database_metrics(
#             operation="insert_failed",
#             records_processed=len(posts),
#             records_successful=0,
#             execution_time=execution_time
#         )
#         raise
@log_performance
def insert_posts(conn, posts):
    """Create posts table if missing and insert posts into PostgreSQL with duplicate prevention."""
    logger = get_logger("database")
    logger.info(f"Starting bulk insert of {len(posts)} posts")
    
    start_time = time.time()
    
    try:
        cur = conn.cursor()
        
        # Create table if not exists
        cur.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                source_url TEXT NOT NULL,
                source_type VARCHAR NOT NULL,
                title TEXT,
                content TEXT NOT NULL,
                published TIMESTAMP NOT NULL,
                url TEXT,
                created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                UNIQUE (source_url, published)
            );
        """)
        conn.commit()
        
        inserted_count = 0
        
        for p in posts:
            cur.execute("""
                INSERT INTO posts (source_url, source_type, title, content, published, url)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_url, published) DO NOTHING;
            """, (
                p["source"],
                p.get("source_type", "unknown"),  # fallback if not provided
                p.get("title"),
                p["content"],
                p["published"],
                p.get("url")
            ))
            
            if cur.rowcount > 0:
                inserted_count += 1
                
        conn.commit()
        cur.close()
        
        execution_time = time.time() - start_time
        duplicate_count = len(posts) - inserted_count
        
        logger.info(f"Bulk insert completed: {inserted_count} inserted, {duplicate_count} duplicates")
        
        log_database_metrics(
            operation="insert",
            records_processed=len(posts),
            records_successful=inserted_count,
            execution_time=execution_time
        )
        
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Bulk insert failed after {execution_time:.2f}s: {str(e)}")
        
        log_database_metrics(
            operation="insert_failed",
            records_processed=len(posts),
            records_successful=0,
            execution_time=execution_time
        )
        raise

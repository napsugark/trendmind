import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import os
import time
from dotenv import load_dotenv
from backend.utils.logger import get_logger, log_performance, log_database_metrics

load_dotenv()

@log_performance
def connect_postgres():
    """Establish connection to PostgreSQL database."""
    logger = get_logger("database")
    
    db_host = os.getenv("DB_HOST", "localhost")
    db_name = os.getenv("DB_NAME", "ai_news_tracker")
    db_user = os.getenv("DB_USER", "postgres")
    
    logger.info(f"Connecting to PostgreSQL: {db_user}@{db_host}/{db_name}")
    
    try:
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=os.getenv("DB_PASSWORD"),
            cursor_factory=RealDictCursor
        )
        logger.info("Successfully connected to PostgreSQL database")
        return conn
        
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL: {str(e)}")
        raise


@log_performance
def get_existing_articles(source_url: str, 
                          start_date: datetime, 
                          end_date: datetime) -> List[Dict[str, Any]]:
    """
    Fetch existing articles from database for a given source and date range.
    
    Args:
        source_url: The source URL/handle
        start_date: Start of date range
        end_date: End of date range
        
    Returns:
        List of article dictionaries
    """
    logger = get_logger("database")
    logger.info(f"Fetching existing articles for {source_url} from {start_date} to {end_date}")
    
    start_time = time.time()
    
    try:
        conn = connect_postgres()
        cursor = conn.cursor()
        
        query = """
            SELECT 
                id,
                source_type,
                source_url,
                title,
                content,
                link,
                published_date,
                scraped_date
            FROM articles
            WHERE source_url = %s
            AND published_date BETWEEN %s AND %s
            ORDER BY published_date DESC
        """
        
        cursor.execute(query, (source_url, start_date, end_date))
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        execution_time = time.time() - start_time
        logger.info(f"Found {len(results)} existing articles in {execution_time:.2f}s")
        
        # Convert to list of dicts
        return [dict(row) for row in results]
        
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Failed to fetch existing articles after {execution_time:.2f}s: {str(e)}")
        raise

@log_performance
def article_exists(cursor, source_url: str, published_date: Optional[datetime]) -> bool:
    """
    Check if an article already exists in the database using a given cursor.
    """
    logger = get_logger("database")
    logger.debug(f"Checking article existence for {source_url} at {published_date}")
    
    try:
        query = """
            SELECT EXISTS(
                SELECT 1 FROM articles
                WHERE TRIM(source_url) = TRIM(%s)
                AND published_date = %s
            )
        """
        cursor.execute(query, (source_url, published_date))
        row = cursor.fetchone()

        if not row:
            logger.warning(f"No result returned for article_exists({source_url}, {published_date})")
            return False

        # Handle both tuple and dict results
        if isinstance(row, dict):
            exists = next(iter(row.values()))  # get first value from dict
        else:
            exists = row[0]

        exists = bool(exists)
        logger.debug(f"Article existence check result: {exists}")
        return exists

    except psycopg2.Error as db_err:
        logger.error(f"Database error in article_exists: {db_err.pgcode} - {db_err.pgerror}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in article_exists: {repr(e)}")
        return False


@log_performance
def insert_posts(
    articles: List[Dict[str, Any]],
    cursor: Optional[psycopg2.extensions.cursor] = None,
    conn: Optional[psycopg2.extensions.connection] = None
) -> int:
    """
    Insert multiple articles into the database.

    Args:
        articles: List of article dicts with keys:
            - source_type, source_url, title, content, link, published_date
        cursor: Optional existing DB cursor
        conn: Optional existing DB connection

    Returns:
        Number of articles inserted
    """
    logger = get_logger("database")
    if not articles:
        logger.info("No articles to insert")
        return 0

    logger.info(f"Starting bulk insert of {len(articles)} articles")
    start_time = time.time()

    # Open connection if not provided
    own_connection = False
    if cursor is None or conn is None:
        conn = connect_postgres()
        cursor = conn.cursor()
        own_connection = True

    query = """
        INSERT INTO articles (
            source_type, source_url, title, content, link, published_date
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (source_url, published_date) DO NOTHING
    """

    inserted = 0
    errors = 0

    for i, article in enumerate(articles):
        try:
            # Strip source_url to avoid whitespace issues
            source_url = article['source_url'].strip() if article.get('source_url') else None

            cursor.execute(query, (
                article['source_type'],
                source_url,
                article.get('title'),
                article['content'],
                article.get('link'),
                article['published_date']
            ))
            if cursor.rowcount > 0:
                inserted += 1
                logger.debug(f"Inserted article {i+1}: {article.get('title', 'No title')}")
            else:
                logger.debug(f"Duplicate article skipped {i+1}: {article.get('title', 'No title')}")

        except Exception as e:
            errors += 1
            logger.error(f"Error inserting article {i+1}: {e}")
            conn.rollback()
            continue

    # Commit only if we opened the connection
    if own_connection:
        conn.commit()
        cursor.close()
        conn.close()

    execution_time = time.time() - start_time
    duplicates = len(articles) - inserted - errors

    logger.info(f"Bulk insert completed: {inserted} inserted, {duplicates} duplicates, {errors} errors")

    # Log detailed metrics
    log_database_metrics(
        operation="insert_articles",
        records_processed=len(articles),
        records_successful=inserted,
        execution_time=execution_time
    )

    return inserted

@log_performance
def get_articles_for_processing(source_urls: List[str], 
                                days_back: int = 7) -> List[Dict[str, Any]]:
    """
    Get all articles from specified sources for processing (clustering/summarization).
    
    Args:
        source_urls: List of source URLs to fetch
        days_back: How many days back to fetch
        
    Returns:
        List of article dictionaries
    """
    logger = get_logger("database")
    logger.info(f"Fetching articles for processing from {len(source_urls)} sources (last {days_back} days)")
    
    start_time = time.time()
    
    try:
        conn = connect_postgres()
        cursor = conn.cursor()
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        logger.debug(f"Using cutoff date: {cutoff_date}")
        
        # Use ANY for matching multiple source URLs
        query = """
            SELECT 
                id,
                source_type,
                source_url,
                title,
                content,
                link,
                published_date,
                scraped_date
            FROM articles
            WHERE source_url = ANY(%s)
            AND published_date >= %s
            ORDER BY published_date DESC
        """
        
        cursor.execute(query, (source_urls, cutoff_date))
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        execution_time = time.time() - start_time
        logger.info(f"Retrieved {len(results)} articles for processing in {execution_time:.2f}s")
        
        # Log breakdown by source
        if results:
            source_counts = {}
            for row in results:
                source = row['source_url']
                source_counts[source] = source_counts.get(source, 0) + 1
            
            logger.debug("Articles per source:")
            for source, count in source_counts.items():
                logger.debug(f"  {source}: {count} articles")
        
        return [dict(row) for row in results]
        
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Failed to fetch articles for processing after {execution_time:.2f}s: {str(e)}")
        raise


@log_performance
def get_article_count_by_source(days_back: int = 7) -> Dict[str, int]:
    """
    Get count of articles per source for the specified time period.
    Useful for dashboard/stats.
    
    Returns:
        Dictionary mapping source_url to article count
    """
    logger = get_logger("database")
    logger.info(f"Getting article counts by source for last {days_back} days")
    
    start_time = time.time()
    
    try:
        conn = connect_postgres()
        cursor = conn.cursor()
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)
        
        query = """
            SELECT source_url, COUNT(*) as count
            FROM articles
            WHERE published_date >= %s
            GROUP BY source_url
            ORDER BY count DESC
        """
        
        cursor.execute(query, (cutoff_date,))
        results = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        execution_time = time.time() - start_time
        counts_dict = {row['source_url']: row['count'] for row in results}
        
        logger.info(f"Retrieved article counts for {len(counts_dict)} sources in {execution_time:.2f}s")
        
        # Log top sources
        if counts_dict:
            logger.debug("Top sources by article count:")
            for source, count in list(counts_dict.items())[:5]:
                logger.debug(f"  {source}: {count} articles")
        
        return counts_dict
        
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Failed to get article counts after {execution_time:.2f}s: {str(e)}")
        raise


@log_performance
def cleanup_old_articles(days_to_keep: int = 90):
    """
    Delete articles older than specified days.
    Run this periodically to manage database size.
    
    Args:
        days_to_keep: Keep articles from last N days
        
    Returns:
        Number of articles deleted
    """
    logger = get_logger("database")
    logger.info(f"Starting cleanup of articles older than {days_to_keep} days")
    
    start_time = time.time()
    
    try:
        conn = connect_postgres()
        cursor = conn.cursor()
        
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        logger.info(f"Deleting articles published before: {cutoff_date}")
        
        # First, count how many will be deleted
        count_query = "SELECT COUNT(*) FROM articles WHERE published_date < %s"
        cursor.execute(count_query, (cutoff_date,))
        count_to_delete = cursor.fetchone()[0]
        
        if count_to_delete == 0:
            logger.info("No old articles found to delete")
            cursor.close()
            conn.close()
            return 0
        
        logger.info(f"Found {count_to_delete} articles to delete")
        
        # Perform the deletion
        delete_query = """
            DELETE FROM articles
            WHERE published_date < %s
        """
        
        cursor.execute(delete_query, (cutoff_date,))
        deleted = cursor.rowcount
        
        conn.commit()
        cursor.close()
        conn.close()
        
        execution_time = time.time() - start_time
        logger.info(f"Cleanup completed: {deleted} articles deleted in {execution_time:.2f}s")
        
        # Log cleanup metrics
        log_database_metrics(
            operation="cleanup_old_articles",
            records_processed=count_to_delete,
            records_successful=deleted,
            execution_time=execution_time
        )
        
        return deleted
        
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Cleanup failed after {execution_time:.2f}s: {str(e)}")
        raise
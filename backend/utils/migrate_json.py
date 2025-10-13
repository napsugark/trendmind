import json
from pathlib import Path
from datetime import datetime
from src.db_postgres import insert_posts  

def migrate_json_to_db():
    """One-time migration of existing JSON files to database"""

    # if Path("data/blog_posts.json").exists():
    #     with open("data/blog_posts.json") as f:
    # if Path("data/substack_research.json").exists():
    #     with open("data/substack_research.json") as f:
    if Path("data/tweets.json").exists():
        with open("data/tweets.json") as f:
            posts = json.load(f)
        
        articles = [{
            # "source_type": "rss",
            # "source_type": "substack",
            "source_type": "twitter",
            "source_url": p["source"],
            "title": p["title"],
            "content": p["content"],
            "link": p.get("link"),  # if present
            "published_date": datetime.fromisoformat(p["published"])
        } for p in posts]

        inserted_count = insert_posts(articles)

        print(f"{inserted_count} articles inserted into the database.")
    else:
        print("blog_posts.json not found.")
        

if __name__ == "__main__":
    migrate_json_to_db()

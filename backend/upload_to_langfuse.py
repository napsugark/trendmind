#!/usr/bin/env python3
"""
Upload evaluation dataset to Langfuse via Python SDK
"""
import json
import sys
from langfuse import Langfuse

def upload_dataset_to_langfuse(langfuse_dataset_path: str):
    """Upload the Langfuse evaluation dataset to Langfuse"""
    
    # Initialize Langfuse client
    # Make sure LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set as environment variables
    langfuse = Langfuse()
    
    # Load the dataset
    with open(langfuse_dataset_path, 'r', encoding='utf-8') as f:
        dataset = json.load(f)
    
    print(f"Uploading dataset: {dataset['name']}")
    print(f"Items: {len(dataset['items'])}")
    
    try:
        # Create the dataset
        created_dataset = langfuse.create_dataset(
            name=dataset["name"],
            description=dataset["description"],
            metadata=dataset.get("metadata", {})
        )
        
        print(f"✅ Dataset created with ID: {created_dataset.id}")
        
        # Upload items in batches
        batch_size = 50
        items = dataset["items"]
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            print(f"Uploading batch {i//batch_size + 1}/{(len(items) + batch_size - 1)//batch_size}")
            
            for item in batch:
                langfuse.create_dataset_item(
                    dataset_id=created_dataset.id,
                    input=item["input"],
                    expected_output=item["expected_output"],
                    metadata=item.get("metadata", {})
                )
        
        print(f"✅ Successfully uploaded {len(items)} items to Langfuse!")
        print(f"Dataset URL: https://cloud.langfuse.com/project/[your-project]/datasets/{created_dataset.id}")
        
    except Exception as e:
        print(f"❌ Error uploading to Langfuse: {e}")
        return False
    
    return True


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python upload_to_langfuse.py <langfuse_dataset.json>")
        sys.exit(1)
    
    dataset_path = sys.argv[1]
    
    print("Make sure you have set these environment variables:")
    print("- LANGFUSE_PUBLIC_KEY")
    print("- LANGFUSE_SECRET_KEY")
    print("- LANGFUSE_HOST (optional, defaults to https://cloud.langfuse.com)")
    print()
    
    upload_dataset_to_langfuse(dataset_path)
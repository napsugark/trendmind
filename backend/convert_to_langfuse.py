#!/usr/bin/env python3
"""
Simple standalone script to convert test dataset to Langfuse evaluation format.
No dependencies required - just Python standard library.

Usage:
    python convert_to_langfuse.py <test_dataset.json>
"""

import json
import sys
from pathlib import Path


def convert_to_langfuse(test_dataset_path: str) -> str:
    """Convert test dataset to Langfuse evaluation format."""
    
    print(f"📁 Loading test dataset: {test_dataset_path}")
    
    # Load test dataset
    with open(test_dataset_path, 'r', encoding='utf-8') as f:
        test_dataset = json.load(f)
    
    # Generate output path
    output_path = test_dataset_path.replace('.json', '_langfuse.json')
    
    print(f"🔄 Converting {len(test_dataset['test_cases'])} test cases...")
    
    # Convert to Langfuse evaluation format
    langfuse_dataset = {
        "name": "ai_content_filter_evaluation",
        "description": "Evaluation dataset for AI content filtering accuracy",
        "metadata": test_dataset["metadata"],
        "items": []
    }
    
    for test_case in test_dataset["test_cases"]:
        langfuse_item = {
            "id": test_case["id"],
            "input": {
                "article": {
                    "title": test_case["input"]["title"],
                    "content": test_case["input"]["content"],
                    "source": test_case["input"]["source_url"]
                }
            },
            "expected_output": {
                "is_ai_relevant": test_case["ground_truth"]["is_ai_relevant"],
                "categories": test_case["ground_truth"]["ai_categories"],
                "confidence": test_case["ground_truth"]["confidence"]
            },
            "actual_output": {
                "classification": test_case["filtering_results"]["final_classification"],
                "passed_filter": test_case["filtering_results"]["passed_ai_filter"]
            },
            "metadata": {
                "source_type": test_case["input"]["source_type"],
                "published_date": test_case["input"]["published_date"],
                "article_id": test_case["article_id"]
            }
        }
        
        langfuse_dataset["items"].append(langfuse_item)
    
    # Save Langfuse dataset
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(langfuse_dataset, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Langfuse dataset saved: {output_path}")
    
    # Verify the dataset
    verify_dataset(output_path)
    
    return output_path


def verify_dataset(langfuse_path: str):
    """Verify the Langfuse dataset format."""
    
    print(f"\n🔍 Verifying dataset format...")
    
    with open(langfuse_path, 'r', encoding='utf-8') as f:
        dataset = json.load(f)
    
    # Count labeled items
    labeled_items = sum(1 for item in dataset["items"] 
                       if item["expected_output"]["is_ai_relevant"] is not None)
    
    total_items = len(dataset["items"])
    
    print(f"✅ Dataset verification complete!")
    print(f"   📊 Total items: {total_items}")
    print(f"   🏷️  Labeled items: {labeled_items}")
    print(f"   ❓ Unlabeled items: {total_items - labeled_items}")
    print(f"   📝 Dataset name: '{dataset['name']}'")
    
    if labeled_items == 0:
        print(f"\n⚠️  Warning: No items have ground truth labels!")
        print(f"   💡 You need to manually label some items before using for evaluation.")
        print(f"   📖 Edit the file and set 'is_ai_relevant': true/false for some items.")


def main():
    if len(sys.argv) != 2:
        print("Usage: python convert_to_langfuse.py <test_dataset.json>")
        print("\nExample:")
        print("  python convert_to_langfuse.py ../test_datasets/ai_filter_test_dataset_20251015_153658.json")
        sys.exit(1)
    
    test_dataset_path = sys.argv[1]
    
    if not Path(test_dataset_path).exists():
        print(f"❌ Error: File not found: {test_dataset_path}")
        sys.exit(1)
    
    try:
        output_path = convert_to_langfuse(test_dataset_path)
        print(f"\n🎉 Success! Langfuse dataset ready at: {output_path}")
        print(f"\n📋 Next steps:")
        print(f"   1. Manually label some articles by editing the Langfuse file")
        print(f"   2. Set 'is_ai_relevant': true/false for ground truth")
        print(f"   3. Upload to Langfuse for evaluation")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
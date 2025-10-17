#!/usr/bin/env python3
"""
Simple script to convert test dataset to Langfuse CSV format.
No dependencies required - runs standalone.
"""

import json
import csv
import sys
from pathlib import Path

def convert_to_langfuse_csv(test_dataset_path: str, output_path: str = None):
    """
    Convert test dataset JSON to Langfuse CSV format.
    
    Args:
        test_dataset_path: Path to the test dataset JSON file
        output_path: Optional custom output path for CSV
    """
    # Load test dataset
    print(f"Loading test dataset: {test_dataset_path}")
    with open(test_dataset_path, 'r', encoding='utf-8') as f:
        test_dataset = json.load(f)
    
    # Generate output path if not provided
    if not output_path:
        output_path = test_dataset_path.replace('.json', '_langfuse.csv')
    
    print(f"Converting to CSV format: {output_path}")
    
    # Prepare CSV data
    csv_data = []
    
    for test_case in test_dataset["test_cases"]:
        # Create input as JSON string (Langfuse expects this)
        input_data = {
            "title": test_case["input"]["title"],
            "content": test_case["input"]["content"],
            "source": test_case["input"]["source_url"]
        }
        
        # Create expected output as JSON string
        expected_output = {
            "is_ai_relevant": test_case["ground_truth"]["is_ai_relevant"],
            "categories": test_case["ground_truth"]["ai_categories"],
            "confidence": test_case["ground_truth"]["confidence"]
        }
        
        # Create metadata as JSON string
        metadata = {
            "source_type": test_case["input"]["source_type"],
            "published_date": test_case["input"]["published_date"],
            "article_id": test_case["article_id"],
            "actual_classification": test_case["filtering_results"]["final_classification"],
            "passed_filter": test_case["filtering_results"]["passed_ai_filter"]
        }
        
        csv_row = {
            "id": test_case["id"],
            "input": json.dumps(input_data, ensure_ascii=False),
            "expected_output": json.dumps(expected_output, ensure_ascii=False),
            "metadata": json.dumps(metadata, ensure_ascii=False)
        }
        
        csv_data.append(csv_row)
    
    # Write to CSV
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['id', 'input', 'expected_output', 'metadata']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for row in csv_data:
            writer.writerow(row)
    
    print(f"✅ CSV dataset created: {output_path}")
    print(f"   - Total items: {len(csv_data)}")
    
    # Count labeled items
    labeled_count = sum(1 for row in csv_data 
                       if json.loads(row['expected_output'])['is_ai_relevant'] is not None)
    print(f"   - Labeled items: {labeled_count}")
    print(f"   - Unlabeled items: {len(csv_data) - labeled_count}")
    
    if labeled_count == 0:
        print("⚠️  Warning: No items have ground truth labels")
        print("   You need to manually label some items before using for evaluation")
    
    return output_path

def main():
    if len(sys.argv) != 2:
        print("Usage: python convert_to_langfuse_csv.py <test_dataset.json>")
        print("Example: python convert_to_langfuse_csv.py ../test_datasets/ai_filter_test_dataset_20251015_153658.json")
        sys.exit(1)
    
    test_dataset_path = sys.argv[1]
    
    if not Path(test_dataset_path).exists():
        print(f"❌ File not found: {test_dataset_path}")
        sys.exit(1)
    
    try:
        csv_path = convert_to_langfuse_csv(test_dataset_path)
        print(f"\n🎉 Success! Upload this CSV file to Langfuse:")
        print(f"   {csv_path}")
        print(f"\nDataset info for Langfuse:")
        print(f"   Name: ai_content_filter_evaluation")
        print(f"   Description: Evaluation dataset for AI content filtering accuracy")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Utility script to identify and clean up corrupted DOCX files.
"""

import os
import glob
import zipfile
from pathlib import Path

def validate_docx_file(file_path):
    """
    Validate if a DOCX file is properly formatted by checking its ZIP structure.
    
    Parameters:
    file_path (str): Path to the DOCX file to validate.
    
    Returns:
    bool: True if file is valid, False otherwise.
    """
    try:
        with zipfile.ZipFile(file_path, 'r') as zip_file:
            # Check if it contains the essential DOCX files
            required_files = ['word/document.xml', '[Content_Types].xml']
            file_list = zip_file.namelist()
            
            for required_file in required_files:
                if required_file not in file_list:
                    print(f"Missing required file in DOCX: {required_file}")
                    return False
            
            return True
    except zipfile.BadZipFile:
        print(f"File is not a valid ZIP file (corrupted DOCX): {file_path}")
        return False
    except Exception as e:
        print(f"Error validating DOCX file {file_path}: {str(e)}")
        return False

def scan_for_corrupted_files(directory):
    """
    Scan a directory for corrupted DOCX files.
    
    Parameters:
    directory (str): Directory to scan for DOCX files.
    
    Returns:
    list: List of corrupted file paths.
    """
    corrupted_files = []
    docx_files = glob.glob(os.path.join(directory, "*.docx"))
    
    print(f"Scanning {len(docx_files)} DOCX files in {directory}...")
    
    for file_path in docx_files:
        if not validate_docx_file(file_path):
            corrupted_files.append(file_path)
            print(f"Found corrupted file: {file_path}")
        else:
            print(f"Valid file: {Path(file_path).name}")
    
    return corrupted_files

def main():
    """Main function to run the cleanup utility."""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    doc_load_dir = os.path.join(script_dir, "TempDocumentStore")
    
    print("DOCX File Validation Utility")
    print("=" * 40)
    
    if not os.path.exists(doc_load_dir):
        print(f"Directory not found: {doc_load_dir}")
        return
    
    # Scan for corrupted files
    corrupted_files = scan_for_corrupted_files(doc_load_dir)
    
    if not corrupted_files:
        print("\n✅ No corrupted files found!")
        return
    
    print(f"\n❌ Found {len(corrupted_files)} corrupted files:")
    for file_path in corrupted_files:
        print(f"  - {Path(file_path).name}")
    
    # Ask user if they want to remove corrupted files
    response = input("\nDo you want to remove these corrupted files? (y/N): ").strip().lower()
    
    if response in ['y', 'yes']:
        removed_count = 0
        for file_path in corrupted_files:
            try:
                os.remove(file_path)
                print(f"Removed: {Path(file_path).name}")
                removed_count += 1
            except Exception as e:
                print(f"Error removing {Path(file_path).name}: {str(e)}")
        
        print(f"\n✅ Successfully removed {removed_count} corrupted files.")
    else:
        print("\nNo files were removed.")

if __name__ == "__main__":
    main() 
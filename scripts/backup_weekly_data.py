#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly Backup Script for GeneralReviews and Dataset files
Creates timestamped copies every Sunday at 00:00
"""

import os
import shutil
from datetime import datetime
import json

# Source files
SOURCE_DIR = r"C:\n8n_Docker\Files"
SOURCE_FILES = [
    "GeneralReviews.json",
    "DatasetScr.json", 
    "DatasetScrBooking.json"
]

# Destination directory
BACKUP_DIR = r"C:\Users\admin\Documents\FlaskApp\data\BackupIssues"

def create_backup():
    """Create backup copies with date suffix in format DDMMYY"""
    
    # Ensure backup directory exists
    os.makedirs(BACKUP_DIR, exist_ok=True)
    
    # Get current date in DDMMYY format
    now = datetime.now()
    date_suffix = now.strftime("%d%m%y")
    
    print(f"Creating backup with date suffix: {date_suffix}")
    
    backup_created = False
    
    for filename in SOURCE_FILES:
        source_path = os.path.join(SOURCE_DIR, filename)
        
        # Check if source file exists
        if not os.path.exists(source_path):
            print(f"WARNING: Source file not found: {source_path}")
            continue
        
        # Create destination filename with date suffix
        # Example: DatasetScr.json -> DatasetScr021225.json
        name_without_ext = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[1]
        dest_filename = f"{name_without_ext}{date_suffix}{ext}"
        dest_path = os.path.join(BACKUP_DIR, dest_filename)
        
        # Check if backup already exists (prevent duplicates)
        if os.path.exists(dest_path):
            print(f"SKIP: Backup already exists: {dest_filename}")
            continue
        
        try:
            # Copy file
            shutil.copy2(source_path, dest_path)
            
            # Verify the backup is valid JSON
            with open(dest_path, 'r', encoding='utf-8') as f:
                json.load(f)
            
            file_size = os.path.getsize(dest_path)
            print(f"SUCCESS: Created {dest_filename} ({file_size:,} bytes)")
            backup_created = True
            
        except Exception as e:
            print(f"ERROR: Failed to backup {filename}: {e}")
            # Remove corrupted backup if it was created
            if os.path.exists(dest_path):
                os.remove(dest_path)
    
    if backup_created:
        print(f"\nBackup completed successfully at {now.strftime('%Y-%m-%d %H:%M:%S')}")
        return True
    else:
        print("\nNo new backups created (files already exist or sources missing)")
        return False

def list_backups():
    """List all existing backups"""
    if not os.path.exists(BACKUP_DIR):
        print("No backup directory found")
        return
    
    backups = [f for f in os.listdir(BACKUP_DIR) if f.endswith('.json')]
    
    if not backups:
        print("No backups found")
        return
    
    print(f"\nExisting backups in {BACKUP_DIR}:")
    backups.sort()
    for backup in backups:
        path = os.path.join(BACKUP_DIR, backup)
        size = os.path.getsize(path)
        mtime = datetime.fromtimestamp(os.path.getmtime(path))
        print(f"  {backup:40s} {size:10,} bytes  {mtime.strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    print("=" * 70)
    print("Weekly Data Backup Script")
    print("=" * 70)
    
    create_backup()
    list_backups()
    
    print("\n" + "=" * 70)

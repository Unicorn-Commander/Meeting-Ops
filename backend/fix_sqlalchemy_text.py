#!/usr/bin/env python3
"""
Fix all db.execute() calls to use text() wrapper for SQLAlchemy 2.0
"""

import os
import re

def fix_file(filepath):
    """Fix db.execute calls in a single file"""
    with open(filepath, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # Pattern to match db.execute with raw SQL strings
    patterns = [
        # Multi-line SQL with triple quotes
        (r'(db\.execute\()("""[\s\S]*?""")\)', r'\1text(\2))'),
        # Single-line SQL with double quotes
        (r'(db\.execute\()(".*?")\)', r'\1text(\2))'),
        # Single-line SQL with single quotes  
        (r'(db\.execute\()(\'.*?\')\)', r'\1text(\2))'),
        # cursor.execute patterns
        (r'(cursor\.execute\()("""[\s\S]*?""")', r'\1text(\2)'),
        (r'(cursor\.execute\()(".*?")', r'\1text(\2)'),
        (r'(cursor\.execute\()(\'.*?\')', r'\1text(\2)'),
    ]
    
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    # Don't double-wrap already wrapped text() calls
    content = re.sub(r'text\(text\(', 'text(', content)
    
    if content != original_content:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"✅ Fixed {filepath}")
        return True
    return False

def main():
    """Fix all Python files in services directory"""
    services_dir = "services"
    fixed_count = 0
    
    for filename in os.listdir(services_dir):
        if filename.endswith('.py'):
            filepath = os.path.join(services_dir, filename)
            if fix_file(filepath):
                fixed_count += 1
    
    # Also fix API files
    api_dir = "api"
    for filename in os.listdir(api_dir):
        if filename.endswith('.py'):
            filepath = os.path.join(api_dir, filename)
            if fix_file(filepath):
                fixed_count += 1
    
    print(f"\nFixed {fixed_count} files")

if __name__ == "__main__":
    main()
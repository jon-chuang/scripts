import os
import argparse
from pathlib import Path
import subprocess
import re
from collections import defaultdict

def get_git_tracked_files(directory, extensions):
    """Get list of tracked files in git repository."""
    try:
        original_dir = os.getcwd()
        os.chdir(directory)
        
        result = subprocess.run(['git', 'ls-files'], 
                              capture_output=True, 
                              text=True, 
                              check=True)
        
        files = result.stdout.splitlines()
        tracked_files = [f for f in files 
                        if any(f.endswith(ext) for ext in extensions)]
        
        os.chdir(original_dir)
        return tracked_files
    except subprocess.CalledProcessError:
        print("Error: Not a git repository or git not installed")
        return []
    except Exception as e:
        print(f"Error accessing git repository: {e}")
        return []

def get_git_blame_info(file_path):
    """Get line count information using git blame."""
    try:
        result = subprocess.run(['git', 'blame', '--line-porcelain', file_path],
                              capture_output=True,
                              text=True,
                              check=True)
        
        lines = result.stdout.split('\n')
        commit_counts = {}
        current_commit = None
        
        for line in lines:
            if line.startswith('author '):
                author = line.replace('author ', '', 1)
                if current_commit and author:
                    if author not in commit_counts:
                        commit_counts[author] = 0
                    commit_counts[author] += 1
            elif re.match(r'^[0-9a-f]{40}', line):
                current_commit = line.split()[0]
                
        return commit_counts
    except subprocess.CalledProcessError:
        print(f"Error: Unable to get blame info for {file_path}")
        return {}

def format_percentage(part, whole):
    """Format percentage with appropriate precision."""
    if whole == 0:
        return "0.0%"
    return f"{(part / whole) * 100:5.1f}%"

def print_table_row(values, widths, separators):
    """Print a row with given widths and separators."""
    row_parts = []
    for value, width, sep in zip(values, widths, separators):
        row_parts.append(f"{str(value):{width}}{sep}")
    print("".join(row_parts))

def build_directory_tree(tracked_files, blame_data):
    """Build a hierarchical directory tree with line counts."""
    tree = defaultdict(lambda: {'files': 0, 'lines': 0, 'subdirs': defaultdict(dict)})
    
    for file_path in tracked_files:
        parts = Path(file_path).parts
        current = tree
        
        # Aggregate statistics for each directory level
        file_lines = sum(blame_data[file_path].values())
        
        for i, part in enumerate(parts[:-1]):  # Exclude filename
            if 'subdirs' not in current:
                current['subdirs'] = defaultdict(dict)
            if part not in current['subdirs']:
                current['subdirs'][part] = {'files': 0, 'lines': 0, 'subdirs': defaultdict(dict)}
            
            current['subdirs'][part]['files'] += 1
            current['subdirs'][part]['lines'] += file_lines
            current = current['subdirs'][part]
    
    return tree

def print_directory_tree(tree, prefix="", is_last=True, total_lines=0):
    """Print the directory tree with line counts and percentages."""
    for dir_name, data in sorted(tree['subdirs'].items(), key=lambda x: x[1]['lines'], reverse=True):
        current_prefix = prefix + ("└── " if is_last else "├── ")
        next_prefix = prefix + ("    " if is_last else "│   ")
        
        # Print directory statistics
        lines = data['lines']
        percentage = format_percentage(lines, total_lines)
        if lines / total_lines > 0.01:
            print(f"{current_prefix}{dir_name}/")
            print(f"{next_prefix}└── {lines:,} lines ({percentage} of total) in {data['files']} files")
            
            # Recursively print subdirectories
            if 'subdirs' in data and data['subdirs']:
                print_directory_tree(data, next_prefix, is_last, total_lines)

def main():
    parser = argparse.ArgumentParser(description='Count lines of code in git repository')
    parser.add_argument('directory', nargs='?', default='.',
                      help='Git repository directory (default: current directory)')
    parser.add_argument('--extensions', nargs='+', 
                      default=['.py', '.js', '.java', '.cpp', '.c', '.h', '.hpp', 
                              '.cs', '.php', '.rb', '.tsx', '.jsx', '.ts', '.rs'],
                      help='File extensions to include (default: common programming languages)')
    args = parser.parse_args()

    directory = Path(args.directory).resolve()
    if not directory.exists():
        print(f"Error: Directory '{directory}' does not exist")
        return

    tracked_files = get_git_tracked_files(directory, args.extensions)
    
    if not tracked_files:
        print("No tracked code files found")
        return

    # Initialize statistics
    author_ext_stats = defaultdict(lambda: defaultdict(int))
    extension_stats = defaultdict(lambda: {'files': 0, 'lines': 0})
    author_stats = defaultdict(int)
    blame_data = {}
    total_lines = 0

    # Change to repository directory
    original_dir = os.getcwd()
    os.chdir(directory)

    # Collect blame data for all files
    for file_path in tracked_files:
        blame_info = get_git_blame_info(file_path)
        blame_data[file_path] = blame_info
        file_lines = sum(blame_info.values())
        total_lines += file_lines
        
        ext = os.path.splitext(file_path)[1]
        extension_stats[ext]['files'] += 1
        extension_stats[ext]['lines'] += file_lines
        
        for author, count in blame_info.items():
            author_stats[author] += count
            author_ext_stats[author][ext] += count

    # Build directory tree
    dir_tree = build_directory_tree(tracked_files, blame_data)

    os.chdir(original_dir)

    # Print results
    print(f"\nRepository Analysis")
    print(f"├── Total Lines: {total_lines:,}")
    print(f"└── Files Analyzed: {len(tracked_files):,}")

    # Print extension breakdown
    print("\nBreakdown by extension:")
    for ext, stats in sorted(extension_stats.items(), key=lambda x: x[1]['lines'], reverse=True):
        print_table_row(
            [ext, f"{stats['lines']:6d} lines in", f"{stats['files']:4d} files"],
            [8, 17, 10],
            [":", "", ""]
        )

    # Print author breakdown
    print("\nBreakdown by author:")
    for author, lines in sorted(author_stats.items(), key=lambda x: x[1], reverse=True):
        print_table_row(
            [f"{author:30}", f"{lines:6d} lines", f"({format_percentage(lines, total_lines)})"],
            [30, 12, 8],
            [":", "", ""]
        )


    # Print detailed tree for top 3 contributors
    print("\nDetailed extension breakdown for contributors:")
    top_authors = sorted(author_stats.items(), key=lambda x: x[1], reverse=True)
    
    for i, (author, total_lines_) in enumerate(top_authors, 1):
        is_last = i == len(top_authors)
        prefix = "└── " if is_last else "├── "
        
        # Author level
        print(f"{prefix}{author}")
        
        # Extension level
        ext_prefix = "    " if is_last else "│   "
        author_extensions = sorted(
            [(ext, lines) for ext, lines in author_ext_stats[author].items()],
            key=lambda x: x[1],
            reverse=True
        )
        
        for j, (ext, lines) in enumerate(author_extensions):
            is_last_ext = j == len(author_extensions) - 1
            ext_symbol = "└── " if is_last_ext else "├── "
            ext_total = extension_stats[ext]['lines']
            
            perc_ext = format_percentage(lines, ext_total)
            perc_author = format_percentage(lines, total_lines_)
            
            output = (
                f"{ext_prefix}{ext_symbol}{ext:<8}"  # Left-align extension with 8 spaces
                f"{lines:>8,} lines "                # Right-align line count with 8 spaces
                f"| {perc_author:>6} of Total"       # Right-align percentage with 6 spaces
                f"| {perc_ext:>6} of Extension "     # Right-align percentage with 6 spaces
            )
            print(output)

    # Print directory breakdown
    print("\nDirectory Breakdown:")
    print_directory_tree(dir_tree, total_lines=total_lines)

if __name__ == "__main__":
    main()
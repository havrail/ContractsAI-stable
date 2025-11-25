# Log Analyzer for ContractsAI
# Analyzes run logs and extracts key metrics

import re
from datetime import datetime
from collections import defaultdict

def analyze_log_file(log_content):
    """Analyze log file and extract statistics"""
    
    stats = {
        'restarts': 0,
        'keyboard_interrupts': 0,
        'errors': [],
        'warnings': [],
        'jobs': [],
        'status_polls': 0,
        'file_changes': [],
        'api_errors': []
    }
    
    lines = log_content.split('\n')
    
    for line in lines:
        # Count restarts
        if 'Started server process' in line:
            stats['restarts'] += 1
        
        # Track keyboard interrupts
        if 'KeyboardInterrupt' in line:
            stats['keyboard_interrupts'] += 1
        
        # Extract file changes causing reloads
        if 'WatchFiles detected changes' in line:
            match = re.search(r"changes in '([^']+)'", line)
            if match:
                stats['file_changes'].append(match.group(1))
        
        # Track jobs
        if 'Celery task' in line and 'dispatched for job' in line:
            match = re.search(r'job (\d+)', line)
            if match:
                stats['jobs'].append(int(match.group(1)))
        
        # Count status polls
        if 'GET /status/' in line:
            stats['status_polls'] += 1
        
        # Track API errors
        if 'HTTP/1.1" 404' in line or 'HTTP/1.1" 500' in line:
            stats['api_errors'].append(line.strip())
        
        # Track errors
        if '[ERROR]' in line:
            stats['errors'].append(line.strip())
        
        # Track warnings
        if '[WARNING]' in line:
            stats['warnings'].append(line.strip())
    
    return stats

def print_analysis(stats):
    """Print formatted analysis"""
    print("\n" + "="*60)
    print("📊 LOG ANALYSIS REPORT")
    print("="*60)
    
    print(f"\n🔄 Server Restarts: {stats['restarts']}")
    print(f"⌨️  Keyboard Interrupts: {stats['keyboard_interrupts']}")
    print(f"📊 Status Polls: {stats['status_polls']}")
    
    if stats['jobs']:
        print(f"\n✅ Jobs Processed: {len(set(stats['jobs']))}")
        print(f"   Job IDs: {sorted(set(stats['jobs']))}")
    
    if stats['file_changes']:
        print(f"\n📝 File Changes Detected ({len(stats['file_changes'])} times):")
        change_counts = defaultdict(int)
        for file in stats['file_changes']:
            change_counts[file] += 1
        for file, count in sorted(change_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"   {count}x - {file}")
    
    if stats['api_errors']:
        print(f"\n❌ API Errors ({len(stats['api_errors'])}):")
        for error in stats['api_errors'][:5]:  # Show first 5
            print(f"   {error}")
    
    if stats['errors']:
        print(f"\n🔴 Logged Errors ({len(stats['errors'])}):")
        for error in stats['errors'][:5]:  # Show first 5
            print(f"   {error}")
    
    if stats['warnings']:
        print(f"\n⚠️  Warnings ({len(stats['warnings'])}):")
        # Show unique warnings only
        unique_warnings = set(stats['warnings'])
        for warning in list(unique_warnings)[:5]:
            print(f"   {warning}")
    
    print("\n" + "="*60)
    print("\n💡 RECOMMENDATIONS:")
    
    if stats['restarts'] > 10:
        print("   • Too many restarts detected!")
        print("   • Use 'python run_prod.py' instead of 'run_dev.py'")
        print("   • This disables auto-reload for stable operation")
    
    if stats['keyboard_interrupts'] > 5:
        print("   • Multiple CTRL+C interrupts detected")
        print("   • Consider letting jobs finish before stopping")
    
    if stats['file_changes']:
        print("   • File changes triggered restarts during processing")
        print("   • Use production mode to avoid this")
    
    if len(stats['api_errors']) > 0:
        print("   • API errors detected - check routes and error handling")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python analyze_logs.py <log_file_or_paste_log_content>")
        print("\nOr paste your log content below and press CTRL+D (Linux/Mac) or CTRL+Z then Enter (Windows):")
        log_content = sys.stdin.read()
    else:
        with open(sys.argv[1], 'r', encoding='utf-8') as f:
            log_content = f.read()
    
    stats = analyze_log_file(log_content)
    print_analysis(stats)

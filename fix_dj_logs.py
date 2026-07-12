import re

with open('ui/dj.html', 'r') as f:
    content = f.read()

# 1. Add lastLoggedProgress to DJEngine constructor
# Find the constructor and add this.lastLoggedProgress = null;
constructor_pattern = r'(this\.waveformPeaks = new Map\(\);)'
constructor_replacement = r'\1\n            this.lastLoggedProgress = null;'
content = re.sub(constructor_pattern, constructor_replacement, content)

# 2. Modify _pollTask to only log if progress_text changes
# We need to wrap the log call in a check.
# The current line is: log(`[Seg #${segIndex}] ${task.progress_text}`, 'log-info');
# We want to change it to:
# if (this.lastLoggedProgress !== task.progress_text) {
#     log(`[Seg #${segIndex}] ${task.progress_text}`, 'log-info');
#     this.lastLoggedProgress = task.progress_text;
# }

old_log_line = "                                log(`[Seg #${segIndex}] ${task.progress_text}`, 'log-info');"
new_log_logic = """                                if (this.lastLoggedProgress !== task.progress_text) {
                                    log(`[Seg #${segIndex}] ${task.progress_text}`, 'log-info');
                                    this.lastLoggedProgress = task.progress_text;
                                }"""

content = content.replace(old_log_line, new_log_logic)

# 3. Reset lastLoggedProgress in start() or where generation begins.
# Let's find where generating is set to true and reset the progress tracker.
start_gen_pattern = r'(this\.generating = true;)'
start_gen_replacement = r'\1\n            this.lastLoggedProgress = null;'
content = re.sub(start_gen_pattern, start_gen_replacement, content)

with open('ui/dj.html', 'w') as f:
    f.write(content)

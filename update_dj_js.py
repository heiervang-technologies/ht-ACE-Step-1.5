import re

with open('ui/dj.html', 'r') as f:
    content = f.read()

# 1. Add genProgressWrap and genProgressBar to the dom object.
# Look for the dom = { ... } block.
dom_pattern = r'(const dom = \{)'
dom_replacement = r'\1\n    genProgressWrap: $('genProgressWrap'),\n    genProgressBar: $('genProgressBar'),'
content = re.sub(dom_pattern, dom_replacement, content)

# 2. Update _pollTask to update the progress bar.
# We need to replace the log line: log(`[Seg #${segIndex}] ${task.progress_text}`, 'log-info');
# with logic that updates the progress bar if it's a progress message.
# And also handle showing/hiding the progress wrap.

# Find the _pollTask function
_poll_task_pattern = r'(_pollTask\(taskId, segIndex\) \{.*?if \(task\.progress_text\) \{.*?log\(`\[Seg #\$\{segIndex\}\] \$\{task\.progress_text}\`, \'log-info\'\);.*?})'
# Note: The regex needs to be non-greedy and handle multiple lines.
# Since _pollTask is a single function, we can target it specifically.

# Instead of a complex regex, let's use a simpler replacement for the specific line.
# We'll search for the specific log call and replace it.
old_log_line = '                                log(`[Seg #${segIndex}] ${task.progress_text}`, \'log-info\');'
new_log_logic = '''                                if (task.progress_text) {
                                    // Update the global progress bar
                                    dom.genProgressWrap.style.display = 'block';
                                    
                                    // Try to extract percentage from progress_text (e.g., "Generating: 10%|...")
                                    const pctMatch = task.progress_text.match(/(\d+)%/);
                                    if (pctMatch) {
                                        dom.genProgressBar.style.width = pctMatch[1] + '%';
                                    }
                                    
                                    // Still log it, but maybe less aggressively or differently
                                    log(`[Seg #${segIndex}] ${task.progress_text}`, 'log-info');
                                }'''
# Wait, the old line was inside an 'if (task.progress_text) { ... }' block.
# Let's just replace the line inside that block.

content = content.replace(old_log_line, '                                // Progress updated via bar')

# Now we need to insert the logic to show the wrap and update the bar.
# Let's find the 'if (task.progress_text) {' line and insert after it.
search_if_progress = '                            if (task.progress_text) {'
replacement_if_progress = f'''                            if (task.progress_text) {{
                                dom.genProgressWrap.style.display = 'block';
                                const pctMatch = task.progress_text.match(/(\\d+)%/);
                                if (pctMatch) {{
                                    dom.genProgressBar.style.width = pctMatch[1] + '%';
                                }}
                                log(`[Seg #${segIndex}] ${task.progress_text}`, 'log-info');'''

content = content.replace(search_if_progress, replacement_if_progress)

# 3. Hide progress bar when starting or stopping.
# In start():
content = content.replace('setPipelineStage(\'generating\');', 'dom.genProgressBar.style.width = \'0%\';\n            setPipelineStage(\'generating\');')

# In stop():
content = content.replace('setPipelineStage(\'idle\');', 'dom.genProgressWrap.style.display = \'none\';\n            setPipelineStage(\'idle\');')

# Also in _pollTask error handling:
content = content.replace('reject(new Error(\'Task failed on server\'));', 'dom.genProgressWrap.style.display = \'none\';\n                                reject(new Error(\'Task failed on server\'));')

with open('ui/dj.html', 'w') as f:
    f.write(content)

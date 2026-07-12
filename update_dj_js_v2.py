import re

with open('ui/dj.html', 'r') as f:
    content = f.read()

# 1. Add genProgressWrap and genProgressBar to the dom object.
# The dom object is defined as const dom = { ... };
# We find the first closing brace of the dom object.
dom_start = content.find('const dom = {')
if dom_start != -1:
    # Find the closing brace of the dom object
    # It's the one that ends the block before the next major section.
    # We can look for the first '};' that follows the dom_start.
    dom_end = content.find('};', dom_start)
    if dom_end != -1:
        # Insert the new references before the closing brace.
        insertion = '\n    genProgressWrap: $(\'genProgressWrap\'),\n    genProgressBar: $(\'genProgressBar\'),'
        content = content[:dom_end] + insertion + content[dom_end:]

# 2. Update _pollTask to update the progress bar.
# The original line is:
#                                log(`[Seg #${segIndex}] ${task.progress_text}`, 'log-info');
old_log_line = "                                log(`[Seg #${segIndex}] ${task.progress_text}`, 'log-info');"
# We replace it with a comment or empty, because we'll insert the logic above it.
content = content.replace(old_log_line, "                                // Progress updated via bar")

# Now we find the 'if (task.progress_text) {' line and insert the logic.
search_if_progress = '                            if (task.progress_text) {'
replacement_if_progress = '''                            if (task.progress_text) {
                                dom.genProgressWrap.style.display = 'block';
                                const pctMatch = task.progress_text.match(/(\d+)%/);
                                if (pctMatch) {
                                    dom.genProgressBar.style.width = pctMatch[1] + '%';
                                }
                                log(`[Seg #${segIndex}] ${task.progress_text}`, 'log-info');'''

content = content.replace(search_if_progress, replacement_if_progress)

# 3. Manage progress bar visibility in state transitions.
# In start():
content = content.replace('setPipelineStage(\'generating\');', "dom.genProgressBar.style.width = '0%';\n            setPipelineStage('generating');")

# In stop():
content = content.replace('setPipelineStage(\'idle\');', "dom.genProgressWrap.style.display = 'none';\n            setPipelineStage('idle');")

# In _pollTask error:
content = content.replace('reject(new Error(\'Task failed on server\'));', "dom.genProgressWrap.style.display = 'none';\n                                reject(new Error('Task failed on server'));")

with open('ui/dj.html', 'w') as f:
    f.write(content)

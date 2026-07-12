import re

with open('ui/dj.html', 'r') as f:
    content = f.read()

# 1. Fix the corrupted nested divs around pipelineBadges
# The user tried to add a wrapper div using sed, but did it multiple times.
# We want exactly one wrapper: <div style="display: flex; flex-direction: column; gap: 8px;">
# followed by <div class="pipeline-badges" id="pipelineBadges">
pattern_wrap = 'display: flex; flex-direction: column; gap: 8px;"><div style="display: flex; flex-direction: column; gap: 8px;"'
while pattern_wrap in content:
    content = content.replace(pattern_wrap, 'display: flex; flex-direction: column; gap: 8px;"><div')

# 2. Insert the progress bar.
# We look for the end of the pipelineBadges div.
# The structure we want is:
# <div style="display: flex; flex-direction: column; gap: 8px;">
#     <div class="pipeline-badges" id="pipelineBadges">...</div>
#     <div id="genProgressWrap">...</div>
# </div>
# We use a non-greedy match to find the first closing div of pipelineBadges.
search_pattern = r'(<div style="display: flex; flex-direction: column; gap: 8px;"><div class="pipeline-badges" id="pipelineBadges">.*?</div>)'
replacement = r'\1<div id="genProgressWrap" style="display: none; margin-top: 8px;"><div style="font-size: 0.65rem; color: var(--muted); text-transform: uppercase; margin-bottom: 4px;">Generation Progress</div><div style="background: var(--border); height: 6px; border-radius: 3px; overflow: hidden;"><div id="genProgressBar" style="background: var(--accent); width: 0%; height: 100%; transition: width 0.3s ease;"></div></div></div>'

content = re.sub(search_pattern, replacement, content, flags=re.DOTALL)

with open('ui/dj.html', 'w') as f:
    f.write(content)

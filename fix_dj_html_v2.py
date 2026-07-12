import re

with open('ui/dj.html', 'r') as f:
    content = f.read()

# 1. Fix the corrupted nested divs around pipelineBadges.
# We want to find the block that starts with a div containing "pipeline-badges" 
# and clean up everything around it to restore the intended structure.

# We'll look for the "Pipeline" label and the following div structure.
# The goal is to have:
# <div style="display: flex; flex-direction: column; justify-content: center; gap: 6px;">
#     <div style="font-size: 0.65rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px;">Pipeline</div>
#     <div style="display: flex; flex-direction: column; gap: 8px;">
#         <div class="pipeline-badges" id="pipelineBadges">...</div>
#         <div id="genProgressWrap">...</div>
#     </div>
# </div>

# First, let's identify the start of the pipeline section.
pipeline_label = '<div style="font-size: 0.65rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px;">Pipeline</div>'
if pipeline_label in content:
    start_idx = content.find(pipeline_label)
    # Find the end of the container (the next closing div that matches the outer wrapper)
    # This is tricky with regex. Let's just find the start of the next section ("Visualizer").
    end_marker = '<!-- Visualizer -->'
    if end_marker in content:
        end_idx = content.find(end_marker)
        
        # The section between the label and the Visualizer marker
        section = content[start_idx:end_idx]
        
        # We want to replace the messy part with a clean version.
        # Let's just rebuild the whole pipeline block.
        
        # Extract the badges content
        badges_match = re.search(r'<div class="pipeline-badges" id="pipelineBadges">(.*?)</div>', section, re.DOTALL)
        if badges_match:
            badges_content = badges_match.group(1)
            
            clean_block = f'''
                <div style="font-size: 0.65rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px;">Pipeline</div>
                <div style="display: flex; flex-direction: column; gap: 8px;">
                    <div class="pipeline-badges" id="pipelineBadges">{badges_content}</div>
                    <div id="genProgressWrap" style="display: none; margin-top: 8px;">
                        <div style="font-size: 0.65rem; color: var(--muted); text-transform: uppercase; margin-bottom: 4px;">Generation Progress</div>
                        <div style="background: var(--border); height: 6px; border-radius: 3px; overflow: hidden;">
                            <div id="genProgressBar" style="background: var(--accent); width: 0%; height: 100%; transition: width 0.3s ease;"></div>
                        </div>
                    </div>
                </div>
            '''
            
            # Now we need to find the outer wrapper start.
            # It's usually <div style="display: flex; flex-direction: column; justify-content: center; gap: 6px;">
            # Let's look backwards from start_idx.
            wrapper_start = content.rfind('<div style="display: flex; flex-direction: column; justify-content: center; gap: 6px;">', 0, start_idx)
            if wrapper_start != -1:
                # We replace from wrapper_start to end_idx
                # But we need to be careful not to remove the wrapping div itself if we want to keep it.
                # Actually, let's just replace from wrapper_start to end_idx.
                
                new_section = f'''
                <div style="display: flex; flex-direction: column; justify-content: center; gap: 6px;">
                    {clean_block}
                </div>
                '''
                content = content[:wrapper_start] + new_section + content[end_idx:]

with open('ui/dj.html', 'w') as f:
    f.write(content)

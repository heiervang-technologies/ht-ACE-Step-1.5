import re

with open('ui/dj.html', 'r') as f:
    content = f.read()

# We'll rebuild the pipeline section from scratch to ensure it's clean.
# We find the outer wrapper that contains the "Pipeline" label.
pipeline_label = '<div style="font-size: 0.65rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px;">Pipeline</div>'
if pipeline_label in content:
    # Find the start of the wrapper div
    wrapper_start = content.rfind('<div style="display: flex; flex-direction: column; justify-content: center; gap: 6px;">', 0, content.find(pipeline_label))
    
    if wrapper_start != -1:
        # Find the end of the wrapper. 
        # We'll look for the first closing div that is followed by the Visualizer marker or another main section.
        # A safer way is to find the "Visualizer" marker and work backwards.
        end_marker = '<!-- Visualizer -->'
        if end_marker in content:
            end_idx = content.find(end_marker)
            
            # Extract the badges content from the existing HTML
            section_to_search = content[wrapper_start:end_idx]
            badges_match = re.search(r'<div class="pipeline-badges" id="pipelineBadges">(.*?)</div>', section_to_search, re.DOTALL)
            
            if badges_match:
                badges_content = badges_match.group(1)
                
                # Construct the clean replacement block
                clean_block = f'''
                <div style="display: flex; flex-direction: column; justify-content: center; gap: 6px;">
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
                </div>
                '''
                # Replace the messy section
                content = content[:wrapper_start] + clean_block + content[end_idx:]

with open('ui/dj.html', 'w') as f:
    f.write(content)

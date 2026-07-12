import re

with open('ui/dj.html', 'r') as f:
    content = f.read()

# Fix the corrupted layout around the pipeline section.
pipeline_label = '<div style="font-size: 0.65rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px;">Pipeline</div>'
end_marker = '<!-- Visualizer -->'

if pipeline_label in content and end_marker in content:
    start_idx = content.find(pipeline_label)
    end_idx = content.find(end_marker)
    
    # Find the start of the outer wrapper div.
    wrapper_start = content.rfind('<div style="display: flex; flex-direction: column; justify-content: center; gap: 6px;">', 0, start_idx)
    
    if wrapper_start != -1:
        section = content[wrapper_start:end_idx]
        badges_match = re.search(r'<div class="pipeline-badges" id="pipelineBadges">(.*?)</div>', section, re.DOTALL)
        if badges_match:
            badges_content = badges_match.group(1)
            
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
            content = content[:wrapper_start] + clean_block + content[end_idx:]

with open('ui/dj.html', 'w') as f:
    f.write(content)

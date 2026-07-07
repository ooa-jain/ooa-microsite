import os

html_to_insert = """
<div class="modal-overlay" id="aiDraftModal">
  <div class="modal-box" style="max-width: 600px;">
    <div class="modal-head">
      <h3><i class="fas fa-magic" style="color: var(--gold);"></i> AI Forms Draft Space</h3>
      <button class="modal-close" onclick="closeAiDraftModal()"><i class="fas fa-xmark"></i></button>
    </div>
    <div class="modal-body">
      <p style="font-size: 14px; color: var(--muted); margin-bottom: 20px;">Describe the form you need. Our AI will automatically generate the required fields, sections, and logic.</p>
      
      <div class="form-group" style="margin-bottom: 16px;">
        <label style="font-size: 13px; font-weight: 600; color: var(--navy); display: block; margin-bottom: 6px;">Prompt / Description <span style="color:red">*</span></label>
        <textarea id="aiDraftPrompt" rows="4" style="width: 100%; padding: 12px; border: 1px solid var(--border); border-radius: 8px; font-family: 'Inter', sans-serif; font-size: 13px;" placeholder="e.g. Create a student feedback form for the 'Leadership Development' event with questions about content quality, speaker effectiveness, and overall rating..."></textarea>
      </div>

      <div style="display: flex; gap: 12px; align-items: center; margin-bottom: 24px;">
        <span style="font-size: 12px; font-weight: 600; color: var(--navy);">Quick Start:</span>
        <button type="button" style="padding: 6px 12px; border-radius: 20px; border: 1px solid var(--border); background: var(--surface-2); font-size: 11px; cursor: pointer;" onclick="document.getElementById('aiDraftPrompt').value='Course Evaluation Survey'">Course Eval</button>
        <button type="button" style="padding: 6px 12px; border-radius: 20px; border: 1px solid var(--border); background: var(--surface-2); font-size: 11px; cursor: pointer;" onclick="document.getElementById('aiDraftPrompt').value='Faculty Leave Request'">Leave Request</button>
        <button type="button" style="padding: 6px 12px; border-radius: 20px; border: 1px solid var(--border); background: var(--surface-2); font-size: 11px; cursor: pointer;" onclick="document.getElementById('aiDraftPrompt').value='Event Registration Form'">Event Registration</button>
      </div>

      <div style="display: flex; justify-content: flex-end; gap: 12px;">
        <button type="button" class="btn" style="background: transparent; color: var(--muted); border: 1px solid var(--border);" onclick="closeAiDraftModal()">Cancel</button>
        <button type="button" class="btn btn-primary" onclick="generateAiForm()" id="aiDraftBtn"><i class="fas fa-wand-magic-sparkles"></i> Generate Form</button>
      </div>

      <div id="aiDraftResult" style="display: none; margin-top: 20px; padding: 16px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; color: #166534; font-size: 13px;">
        <i class="fas fa-circle-check"></i> <strong>Success!</strong> Your AI draft has been created and saved to your workspace. 
        <a href="#" style="color: #15803d; font-weight: 700; text-decoration: underline; margin-left: 8px;">View Draft</a>
      </div>
    </div>
  </div>
</div>
"""

js_to_insert = """
function openAiDraftModal() {
  document.getElementById('aiDraftModal').classList.add('show');
  document.getElementById('aiDraftPrompt').value = '';
  document.getElementById('aiDraftResult').style.display = 'none';
  const btn = document.getElementById('aiDraftBtn');
  btn.innerHTML = '<i class="fas fa-wand-magic-sparkles"></i> Generate Form';
  btn.disabled = false;
}
function closeAiDraftModal() {
  document.getElementById('aiDraftModal').classList.remove('show');
}
function generateAiForm() {
  const prompt = document.getElementById('aiDraftPrompt').value.trim();
  if(!prompt) { alert('Please enter a description for the form.'); return; }
  
  const btn = document.getElementById('aiDraftBtn');
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Generating...';
  
  setTimeout(() => {
    document.getElementById('aiDraftResult').style.display = 'block';
    btn.innerHTML = '<i class="fas fa-check"></i> Done';
  }, 1500);
}
"""

with open('templates/home.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out_lines = []
for i, line in enumerate(lines):
    out_lines.append(line)
    if '<!-- ============ MODALS ============ -->' in line:
        out_lines.append(html_to_insert)
    # the javascript can be added at the end of the file before </body> if we can't find <script> easily
    elif '</script>' in line and i > len(lines) - 20:
        # Instead, just add the JS to out_lines
        pass

# Append JS at the end
out_lines.append('<script>\n' + js_to_insert + '</script>\n')

with open('templates/home.html', 'w', encoding='utf-8') as f:
    f.writelines(out_lines)
print("Injected successfully.")

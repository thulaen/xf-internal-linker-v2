import os

txt = open('suggestion-detail-dialog.component.html', encoding='utf-8').read()

txt = txt.replace('        <div class="score-item">\n          <span class="score-name">Semantic</span>', '        <div class="score-item">\n          <span class="score-name">Passage Relevance</span>\n          <mat-progress-bar mode="determinate" [value]="scorePercent(detail.score_passage_relevance)" color="primary"></mat-progress-bar>\n          <span class="score-val">{{ (detail.score_passage_relevance * 100).toFixed(0) }}</span>\n        </div>\n        <div class="score-item">\n          <span class="score-name">Semantic</span>')

# Add the diagnostics section
diag_str = """
      <p class="meta-line">
        <mat-icon class="icon-sm">article</mat-icon>
        {{ passageRelevanceStateLabel() }}.
      </p>
      <p class="meta-line">
        {{ passageRelevanceSummary() }}
      </p>
      @if (detail.passage_relevance_diagnostics?.passage_relevance_state === 'computed') {
        <p class="meta-line">
          Best passage matched at index {{ detail.passage_relevance_diagnostics.best_passage_index }} 
          out of {{ detail.passage_relevance_diagnostics.passage_count }} passages.
        </p>
        <p class="meta-line">
          <em>"{{ detail.passage_relevance_diagnostics.best_passage_preview }}..."</em>
        </p>
      }
      
"""

idx = txt.find('@if (hasRareTermDiagnostics())')
if idx != -1:
    txt = txt[:idx] + diag_str + txt[idx:]

with open('suggestion-detail-dialog.component.html', 'w', encoding='utf-8') as f:
    f.write(txt)

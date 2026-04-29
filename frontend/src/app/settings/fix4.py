import os

txt = open('silo-settings.service.ts', encoding='utf-8').read()

interface_str = """export interface PassageRelevanceSettings {
  'passage_relevance.enabled': boolean;
  'passage_relevance.passage_words': number;
  'passage_relevance.passages_per_page_max': number;
  'passage_relevance.ranking_weight': number;
}

"""

if 'PassageRelevanceSettings' not in txt:
    idx = txt.find('export interface ValueModelSettings')
    if idx != -1:
        txt = txt[:idx] + interface_str + txt[idx:]

method_str = """  getPassageRelevanceSettings(): Observable<PassageRelevanceSettings> {
    return this.http.get<PassageRelevanceSettings>(`${this.apiUrl}settings/passage-relevance/`);
  }

  updatePassageRelevanceSettings(settings: Partial<PassageRelevanceSettings>): Observable<PassageRelevanceSettings> {
    return this.http.post<PassageRelevanceSettings>(`${this.apiUrl}settings/passage-relevance/`, settings);
  }

"""

if 'getPassageRelevanceSettings' not in txt:
    idx2 = txt.find('  getValueModelSettings(): Observable<ValueModelSettings>')
    if idx2 != -1:
        txt = txt[:idx2] + method_str + txt[idx2:]

with open('silo-settings.service.ts', 'w', encoding='utf-8') as f:
    f.write(txt)

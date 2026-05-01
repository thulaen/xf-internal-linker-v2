
txt = open('apps/api/urls.py').read()

txt = txt.replace('    path(\n        "settings/cooccurrence/",', '    path(\n        "settings/passage-relevance/",\n        __import__("apps.api.passage_relevance_views", fromlist=["PassageRelevanceSettingsView"]).PassageRelevanceSettingsView.as_view(),\n        name="passage-relevance-settings",\n    ),\n    path(\n        "settings/cooccurrence/",')

with open('apps/api/urls.py', 'w') as f:
    f.write(txt)

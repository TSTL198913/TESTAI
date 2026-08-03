import json
data = json.load(open('d:/workspace/TestAI/_ci_jobs.json', encoding='utf-8'))
for j in data.get('jobs', []):
    print(j['id'])

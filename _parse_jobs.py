import json
data = json.load(open('d:/workspace/TestAI/_ci_jobs.json', encoding='utf-8'))
for j in data.get('jobs', []):
    print(f"Job: {j['name']} | status={j['status']} | conclusion={j['conclusion']}")
    for s in j.get('steps', []):
        print(f"  {s['number']}. {s['name']}: {s['conclusion']}")

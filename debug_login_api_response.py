import requests

response = requests.post('http://localhost:8000/auth/login', json={'username': 'admin', 'password': 'password'})
print(f"Status: {response.status_code}")
print(f"Headers:")
for key, value in response.headers.items():
    print(f"  {key}: {value}")
print(f"\nResponse body: {response.text[:200]}...")
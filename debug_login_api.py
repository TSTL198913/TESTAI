import requests

response = requests.post('http://localhost:8000/auth/login', json={'username': 'admin', 'password': 'password'})
print(f"Status code: {response.status_code}")
print(f"Response: {response.text}")
print(f"Cookies: {response.cookies}")
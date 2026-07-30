import time
from playwright.sync_api import sync_playwright, expect

def test_simple_login():
    with sync_playwright() as p:
        browser = p.chromium.launch(
        headless=True,
        executable_path="C:\\Users\\18907\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe",
        args=["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
    )
        context = browser.new_context()
        page = context.new_page()
        
        print("Step 1: Navigate to login page")
        page.goto("http://localhost:3000/login", timeout=30000)
        print(f"Current URL: {page.url}")
        
        print("\nStep 2: Fill login form")
        page.fill('input[id="username"]', "admin")
        page.fill('input[id="password"]', "password")
        
        print("\nStep 3: Submit login")
        with page.expect_response("**/auth/login") as response_info:
            page.click('button[type="submit"]')
        
        response = response_info.value
        print(f"Login API Status: {response.status}")
        
        print("\nStep 4: Wait for redirect")
        try:
            page.wait_for_url("http://localhost:3000/", timeout=15000)
            print(f"Successfully redirected to: {page.url}")
        except Exception as e:
            print(f"Redirect failed: {e}")
            print(f"Current URL: {page.url}")
        
        print("\nStep 5: Check cookies")
        cookies = context.cookies()
        print(f"Number of cookies: {len(cookies)}")
        for cookie in cookies:
            print(f"  {cookie['name']}: {cookie['value'][:50]}...")
        
        print("\nStep 6: Check localStorage")
        local_storage = page.evaluate("() => localStorage.getItem('user')")
        print(f"localStorage user: {local_storage}")
        
        browser.close()

if __name__ == "__main__":
    test_simple_login()

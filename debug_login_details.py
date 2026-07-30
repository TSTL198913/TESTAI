from playwright.sync_api import sync_playwright

chrome_path = "C:\\Users\\18907\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=chrome_path)
    context = browser.new_context()
    page = context.new_page()
    
    page.goto("http://localhost:3000/login")
    
    page.fill('input[id="username"]', "admin")
    page.fill('input[id="password"]', "password")
    
    with page.expect_response("**/api/auth/login") as response_info:
        page.click('button[type="submit"]')
    
    response = response_info.value
    print(f"Login API Status: {response.status}")
    print(f"Login API Response: {response.text()}")
    
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    
    print(f"Current URL: {page.url}")
    
    cookies = context.cookies()
    print(f"\nCookies:")
    for cookie in cookies:
        print(f"  {cookie['name']}: {cookie['value'][:30]}... (HttpOnly: {cookie.get('httpOnly', False)})")
    
    local_storage = page.evaluate("() => ({user: localStorage.getItem('user'), token: localStorage.getItem('token')})")
    print(f"\nLocalStorage:")
    print(f"  user: {local_storage.get('user')}")
    print(f"  token: {local_storage.get('token')}")
    
    browser.close()
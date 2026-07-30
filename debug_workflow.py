from playwright.sync_api import sync_playwright

chrome_path = "C:\\Users\\18907\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=chrome_path)
    page = browser.new_page()
    
    page.goto("http://localhost:3000/login")
    page.fill('input[id="username"]', "admin")
    page.fill('input[id="password"]', "password")
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    print(f"After login URL: {page.url}")
    
    page.goto("http://localhost:3000/workflow")
    page.wait_for_load_state("networkidle")
    print(f"Workflow page URL: {page.url}")
    
    create_btn = page.locator('[data-testid="create-workflow-btn"]')
    print(f"Create button found: {create_btn.count() > 0}")
    
    if create_btn.count() == 0:
        print("Looking for alternative selectors...")
        buttons = page.locator("button")
        for i in range(buttons.count()):
            btn = buttons.nth(i)
            try:
                text = btn.inner_text()
                print(f"Button {i}: '{text}'")
            except:
                pass
    
    browser.close()
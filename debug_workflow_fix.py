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
    
    page.wait_for_timeout(3000)
    
    print(f"Workflow page URL: {page.url}")
    
    error_elements = page.locator('p:has-text("未检测到登录凭证")')
    print(f"Error message visible: {error_elements.count() > 0}")
    
    if error_elements.count() > 0:
        page.screenshot(path="error_page.png")
        print("Error page saved")
    
    create_btn = page.locator('[data-testid="create-workflow-btn"]')
    print(f"Create button found: {create_btn.count() > 0}")
    
    cards = page.locator('[data-testid*="workflow-card-"]')
    print(f"Workflow cards found: {cards.count()}")
    
    page.screenshot(path="workflow_page_after_fix.png")
    
    browser.close()
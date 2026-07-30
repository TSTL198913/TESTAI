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
    
    page.goto("http://localhost:3000/workflow")
    page.wait_for_load_state("networkidle")
    
    create_btn = page.locator('[data-testid="create-workflow-btn"]')
    create_btn.click()
    
    name_input = page.locator('[data-testid="workflow-name-input"]')
    workflow_name = "测试工作流_debug002"
    name_input.fill(workflow_name)
    
    submit_btn = page.locator('[data-testid="workflow-submit-btn"]')
    submit_btn.click()
    
    page.wait_for_timeout(2000)
    
    page.screenshot(path="after_submit.png")
    
    html = page.content()
    with open("page_content.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print("Saved screenshot and page content")
    
    all_divs = page.locator("div")
    print(f"\nTotal divs: {all_divs.count()}")
    
    data_testid_divs = page.locator('[data-testid]')
    print(f"Elements with data-testid: {data_testid_divs.count()}")
    
    for i in range(min(data_testid_divs.count(), 20)):
        el = data_testid_divs.nth(i)
        try:
            testid = el.get_attribute("data-testid")
            print(f"  data-testid='{testid}'")
        except:
            pass
    
    browser.close()
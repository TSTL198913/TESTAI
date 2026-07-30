from playwright.sync_api import sync_playwright
import os

chrome_path = "C:\\Users\\18907\\AppData\\Local\\Google\\Chrome\\Application\\chrome.exe"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, executable_path=chrome_path)
    page = browser.new_page()
    page.goto("http://localhost:3000/login")
    print(f"Initial URL: {page.url}")
    
    page.fill('input[id="username"]', "admin")
    page.fill('input[id="password"]', "password")
    page.click('button[type="submit"]')
    
    page.wait_for_load_state("networkidle")
    print(f"After login URL: {page.url}")
    
    browser.close()
import os

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
SECRET_KEY = "hardcoded_key_12345"

def process_user_expression():
    expr = input("请输入表达式: ")
    result = eval(expr)
    print(f"结果: {result}")

def run_system_command():
    cmd = input("请输入命令: ")
    os.system(cmd)

def main():
    print("测试程序")

if __name__ == "__main__":
    main()
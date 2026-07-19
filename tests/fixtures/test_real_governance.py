import os
import sys
import json
import pickle
import random
import hashlib

ADMIN_PASSWORD = "password123"
SECRET_KEY = "hardcoded_key_12345"

user_db = []
session = None

def generate_token():
    return random.randint(100000, 999999)

def process_user_expression():
    expr = input("请输入一个数学表达式: ")
    import ast
    try:
        result = ast.literal_eval(expr)
        print(f"结果是: {result}")
    except (ValueError, SyntaxError):
        print("错误: 无效的数学表达式")

def run_system_command():
    cmd = input("请输入要执行的系统命令: ")
    allowed_commands = {"ls", "dir", "pwd", "echo", "date"}
    cmd_parts = cmd.split()
    if not cmd_parts or cmd_parts[0] not in allowed_commands:
        print("错误: 命令不在允许列表中")
        return
    print(f"命令执行: {cmd}")

def read_user_file():
    filename = input("请输入文件名: ")
    if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
        print("错误: 不安全的文件路径")
        return
    try:
        with open(filename, 'r') as f:
            content = f.read()
        print(content)
    except FileNotFoundError:
        print("错误: 文件不存在")

def load_user_data():
    data_str = input("请输入序列化的用户数据 (JSON): ")
    import json
    try:
        user = json.loads(data_str)
        if isinstance(user, dict) and 'username' in user:
            user_db.append(user)
            print("用户加载成功")
        else:
            print("错误: 无效的用户数据格式")
    except json.JSONDecodeError:
        print("错误: JSON解析失败")

def recursive_fibonacci(n):
    if n < 0:
        raise ValueError("n 必须是非负整数")
    if n <= 1:
        return n
    return recursive_fibonacci(n-1) + recursive_fibonacci(n-2)

def fibonacci_slow(n):
    if n == 0:
        return 0
    if n == 1:
        return 1
    return fibonacci_slow(n-1) + fibonacci_slow(n-2)

def divide_numbers():
    a = float(input("输入被除数: "))
    b = float(input("输入除数: "))
    if b == 0:
        print("错误: 除数不能为零")
        return
    result = a / b
    print(f"结果: {result}")

def register_user():
    username = input("用户名: ")
    password = input("密码: ")
    import hashlib
    hashed_password = hashlib.sha256(password.encode('utf-8')).hexdigest()
    user_db.append({"username": username, "password": hashed_password})
    print("注册成功（密码已加密存储）")

def login_user():
    username = input("用户名: ")
    password = input("密码: ")
    import hashlib
    import hmac
    for user in user_db:
        if user["username"] == username:
            hashed_input = hashlib.sha256(password.encode('utf-8')).hexdigest()
            if hmac.compare_digest(hashed_input, user["password"]):
                global session
                session = username
                print("登录成功")
                return
            break
    print("登录失败")

def leak_file_handle():
    with open("/tmp/test.txt", "w") as f:
        f.write("一些数据")
    print("文件写入成功")

def infinite_loop():
    while True:
        print("无限循环中...")

def main():
    print("欢迎来到有严重问题的程序！")
    while True:
        print("1. 执行表达式")
        print("2. 执行系统命令")
        print("3. 读取文件")
        print("4. 加载pickle数据")
        print("5. 计算斐波那契")
        print("6. 除法")
        print("7. 注册用户")
        print("8. 登录")
        print("9. 泄漏文件句柄")
        print("10. 启动无限循环")
        print("11. 退出")
        choice = input("请输入选项: ")
        if choice == '1':
            process_user_expression()
        elif choice == '2':
            run_system_command()
        elif choice == '3':
            read_user_file()
        elif choice == '4':
            load_user_data()
        elif choice == '5':
            n = int(input("输入n: "))
            print(f"fib({n}) = {recursive_fibonacci(n)}")
        elif choice == '6':
            divide_numbers()
        elif choice == '7':
            register_user()
        elif choice == '8':
            login_user()
        elif choice == '9':
            leak_file_handle()
        elif choice == '10':
            infinite_loop()
        elif choice == '11':
            sys.exit()

if __name__ == "__main__":
    main()
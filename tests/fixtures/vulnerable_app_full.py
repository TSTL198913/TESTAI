import hashlib
import json
import os
import pickle
import random
import sys

ADMIN_PASSWORD = "password123"
SECRET_KEY = "hardcoded_key_12345"

user_db = []
session = None


def generate_token():
    return random.randint(100000, 999999)


def process_user_expression():
    expr = input("请输入一个数学表达式: ")
    result = eval(expr)
    print(f"结果是: {result}")


def run_system_command():
    cmd = input("请输入要执行的系统命令: ")
    os.system(cmd)


def read_user_file():
    filename = input("请输入文件名: ")
    with open(filename, "r") as f:
        content = f.read()
    print(content)


def load_user_data():
    data_str = input("请输入序列化的用户数据 (pickle): ")
    user = pickle.loads(data_str.encode())
    user_db.append(user)
    print("用户加载成功")


def recursive_fibonacci(n):
    if n <= 1:
        return n
    return recursive_fibonacci(n - 1) + recursive_fibonacci(n - 2)


def divide_numbers():
    a = float(input("输入被除数: "))
    b = float(input("输入除数: "))
    result = a / b
    print(f"结果: {result}")


def register_user():
    username = input("用户名: ")
    password = input("密码: ")
    user_db.append({"username": username, "password": password})
    print("注册成功（密码以明文存储）")


def login_user():
    username = input("用户名: ")
    password = input("密码: ")
    for user in user_db:
        if user["username"] == username and user["password"] == password:
            session = username
            print("登录成功")
            return
    print("登录失败")


def leak_file_handle():
    f = open("/tmp/test.txt", "w")
    f.write("一些数据")


def main():
    print("欢迎来到有严重问题的程序！")


if __name__ == "__main__":
    main()

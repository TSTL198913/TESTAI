import os
import subprocess
import shlex

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
SECRET_KEY = os.environ.get("SECRET_KEY", "default_secret_key_should_be_set_in_env")


def process_user_expression(expression):
    import ast

    try:
        return ast.literal_eval(expression)
    except (ValueError, SyntaxError):
        return None


def run_system_command():
    cmd_input = input("请输入命令: ")
    cmd_args = shlex.split(cmd_input)
    result = subprocess.run(cmd_args, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"命令执行失败: {result.stderr}")


def main():
    print("测试程序")


if __name__ == "__main__":
    main()

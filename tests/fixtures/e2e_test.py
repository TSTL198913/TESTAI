import os


def process_user_expression():
    expr = input("请输入表达式: ")
    import ast

    try:
        result = ast.literal_eval(expr)
        print(f"结果: {result}")
    except (ValueError, SyntaxError):
        print("错误: 无效表达式")


def run_system_command():
    cmd = input("请输入命令: ")
    os.system(cmd)


def main():
    print("测试程序")


if __name__ == "__main__":
    main()

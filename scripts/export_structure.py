import os
import argparse

# 默认需要忽略的目录和文件
DEFAULT_IGNORE = {
    "__pycache__",
    ".git",
    ".idea",
    ".venv",
    "venv",
    "env",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    ".DS_Store",
}

def generate_tree(
    start_path: str,
    ignore_patterns: set,
    prefix: str = "",
    output_lines: list = None,
    max_depth: int = 10,
    current_depth: int = 0,
):
    """
    递归生成目录树
    :param start_path: 当前遍历的路径
    :param ignore_patterns: 要忽略的文件/文件夹名集合
    :param prefix: 格式化前缀
    :param output_lines: 存放结果行的列表
    :param max_depth: 最大深度，防止无穷递归
    :param current_depth: 当前递归深度
    """
    if output_lines is None:
        output_lines = []
    if current_depth >= max_depth:
        return output_lines

    try:
        entries = sorted(os.listdir(start_path))
    except PermissionError:
        # 无权限访问的目录跳过
        return output_lines

    # 过滤忽略项
    entries = [e for e in entries if e not in ignore_patterns]

    for idx, entry in enumerate(entries):
        full_path = os.path.join(start_path, entry)
        is_last = idx == len(entries) - 1
        connector = "└── " if is_last else "├── "
        output_lines.append(f"{prefix}{connector}{entry}")

        if os.path.isdir(full_path):
            extension = "    " if is_last else "│   "
            generate_tree(
                full_path,
                ignore_patterns,
                prefix + extension,
                output_lines,
                max_depth,
                current_depth + 1,
            )
    return output_lines

def main():
    parser = argparse.ArgumentParser(description="导出项目目录结构，过滤无关文件夹")
    parser.add_argument("path", nargs="?", default=".", help="项目根路径，默认为当前目录")
    parser.add_argument("-o", "--output", default="structure.txt", help="输出文件路径，默认 structure.txt")
    parser.add_argument("--max-depth", type=int, default=10, help="最大遍历深度，默认 10")
    parser.add_argument("--show-console", action="store_true", help="同时打印到控制台")
    args = parser.parse_args()

    start_path = os.path.abspath(args.path)
    if not os.path.exists(start_path):
        print(f"路径不存在: {start_path}")
        return

    # 生成树
    lines = [os.path.basename(start_path) + "/"]
    generate_tree(start_path, DEFAULT_IGNORE, "", lines, max_depth=args.max_depth)
    tree_str = "\n".join(lines)

    # 写入文件
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(tree_str)
    print(f"结构已保存至: {os.path.abspath(args.output)}")

    # 可选控制台输出
    if args.show_console:
        print(tree_str)

if __name__ == "__main__":
    main()
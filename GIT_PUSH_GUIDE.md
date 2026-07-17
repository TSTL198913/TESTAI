# Git 推送指南 - 上传到 GitHub

## 一、准备工作

### 1.1 创建 GitHub 仓库

1. 登录 GitHub
2. 创建新仓库（选择 Public 或 Private）
3. 记录仓库 URL，格式：`https://github.com/<用户名>/<仓库名>.git`

### 1.2 配置认证方式（推荐使用 SSH）

**方式一：SSH Key（推荐）**

```bash
# 生成 SSH Key（如果尚未生成）
ssh-keygen -t ed25519 -C "your_email@example.com"

# 启动 SSH agent
eval "$(ssh-agent -s)"

# 添加 SSH Key
ssh-add ~/.ssh/id_ed25519

# 复制公钥到剪贴板
cat ~/.ssh/id_ed25519.pub
```

然后在 GitHub → Settings → SSH and GPG keys 添加公钥。

**方式二：Personal Access Token**

1. GitHub → Settings → Developer settings → Personal access tokens
2. 生成新 token，勾选 `repo` 权限
3. 推送时使用 token 作为密码

## 二、推送步骤

### 2.1 配置本地 Git

```bash
# 配置用户名和邮箱
git config user.name "Your Name"
git config user.email "your_email@example.com"
```

### 2.2 添加远程仓库

```bash
# 查看当前远程仓库
git remote -v

# 添加远程仓库（替换为你的仓库 URL）
# SSH方式（推荐）
git remote add origin git@github.com:<用户名>/<仓库名>.git

# 或 HTTPS 方式
git remote add origin https://github.com/<用户名>/<仓库名>.git
```

### 2.3 添加文件并提交

```bash
# 添加所有文件（.gitignore 会自动排除不需要的文件）
git add .

# 查看状态确认
git status

# 提交代码
git commit -m "feat: 初始化项目，包含完整CI/CD流程"
```

### 2.4 推送到 GitHub

```bash
# 推送到 main 分支
git push -u origin master

# 或推送到 main 分支（如果仓库默认分支是 main）
git push -u origin main
```

**如果提示分支不存在：**

```bash
# 重命名分支
git branch -M main

# 重新推送
git push -u origin main
```

## 三、验证

### 3.1 检查远程仓库

```bash
# 查看远程分支
git branch -r

# 拉取最新代码
git pull origin main
```

### 3.2 验证 CI/CD 流水线

1. 打开 GitHub 仓库页面
2. 点击 Actions 标签
3. 确认 CI/CD 流水线正在运行

## 四、后续工作流

### 4.1 创建开发分支

```bash
# 创建并切换到 develop 分支
git checkout -b develop

# 推送 develop 分支
git push -u origin develop
```

### 4.2 提交代码流程

```bash
# 切换到开发分支
git checkout develop

# 添加修改的文件
git add <文件路径>

# 提交
git commit -m "描述你的修改"

# 推送
git push origin develop
```

### 4.3 创建 Pull Request

1. 在 GitHub 上创建从 develop 到 main 的 Pull Request
2. 等待 CI/CD 流水线完成
3. 审查代码后合并

## 五、故障排除

### SSH 连接问题

```bash
# 测试 SSH 连接
ssh -T git@github.com

# 如果失败，检查 SSH agent
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
```

### 推送权限问题

```bash
# 检查远程仓库 URL
git remote -v

# 如果是 HTTPS 方式，确保使用正确的 token
git remote set-url origin https://<token>@github.com/<用户名>/<仓库名>.git
```

### 文件太大无法推送

```bash
# 检查大文件
git rev-list --objects --all | grep "$(git verify-pack -v .git/objects/pack/*.idx | sort -k 3 -n | tail -5 | awk '{print $1}')"

# 从历史中移除大文件
git filter-branch --force --index-filter 'git rm --cached --ignore-unmatch <大文件路径>' --prune-empty -- --all
```

## 六、注意事项

- **不要提交敏感信息**：`.env` 文件已在 `.gitignore` 中排除
- **提交前运行测试**：确保测试通过后再推送
- **使用描述性的提交信息**：遵循 Conventional Commits 规范
- **保护 main 分支**：在 GitHub 上设置分支保护规则
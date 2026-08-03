# SSL 证书目录

生产部署前必须在此目录放置以下文件：

- `fullchain.pem` — 证书链（含中间证书）
- `privkey.pem` — 私钥

## 获取方式

1. **Let's Encrypt（推荐，免费）**：
   ```bash
   certbot certonly --standalone -d your-domain.com
   # 证书路径: /etc/letsencrypt/live/your-domain.com/
   # 复制 fullchain.pem 和 privkey.pem 到此目录
   ```

2. **商业 CA**：购买证书后，将收到的证书文件重命名为 fullchain.pem，私钥重命名为 privkey.pem

3. **自签名（仅测试，不可生产）**：
   ```bash
   openssl req -x509 -newkey rsa:4096 -keyout privkey.pem -out fullchain.pem -days 365 -nodes
   ```

## 安全要求

- `privkey.pem` 权限必须为 600
- 证书有效期需监控，到期前续期
- 此目录已被 .dockerignore 排除，不会被构建进镜像

## 若暂不启用 HTTPS

在 `nginx.conf` 中注释掉 443 server 块，仅使用 HTTP(80)。

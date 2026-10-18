+++
title = "一次 GitHub Actions 部署翻车记录：rsync error code 23 背后的三个坑"
date = "2026-10-18T22:40:00+08:00"
slug = "rsync-code23-hugo-deploy"
categories = ["server"]
tags = ["rsync", "hugo", "github-actions", "部署", "宝塔", "运维"]
authors = ["dreamfly"]
draft = false
summary = "用 GitHub Actions + rsync 把 Hugo 静态站部署到宝塔 VPS，push 后 CI 报 rsync error code 23。本文复盘这次排障全过程：先澄清「rsync 并非全量重传」的误区，再挖出旧 WordPress 文件属主冲突、.user.ini 不可变、.well-known 证书续期目录三个坑，并给出最终修法。"
+++

把 Hugo 静态站用 GitHub Actions 自动构建、再通过 `rsync` 推到 VPS，是很多个人站点的标配部署姿势。流程简单、增量快、几乎零成本。但前两天我在这条链路上踩了个实实在在的坑——CI 绿了那么多次，突然就开始报 `rsync error code 23`，而且每次 `push` 都失败。

这篇文章把这次排障的完整过程记下来，顺手澄清一个关于 rsync 的常见误解。

## 一、现象：部署突然开始报错

工作流大致是这样：GitHub Actions 里 `hugo --gc --minify` 构建 → `pagefind` 建搜索索引 → `rsync -avzr --delete` 把 `public/` 同步到 VPS 的 `/www/wwwroot/80shihua`。

某次 push 后，rsync 阶段直接挂掉：

```
uploads/wp-content/uploads/2026/10/image-1-300x135.png
uploads/wp-content/uploads/2026/10/image-1-768x347.png
uploads/wp-content/uploads/2026/10/image-1.png
sent 448,598 bytes  received 1,454,534 bytes  102,872.00 bytes/sec
total size is 180,932,509  speedup is 95.07
rsync error: some files/attrs were not transferred (see previous errors) (code 23) at main.c(1356) [sender=3.2.7]
Error: Process completed with exit code 23.
```

由于部署步骤里加了 `set -e`，rsync 一失败，整个 job 就以 23 退出。

## 二、先澄清一个误解：rsync 是「全量重传」吗？

看到日志里 `total size is 180,932,509`（约 180MB），第一反应很容易以为：「完了，每次改一个文件都要把整个站重传一遍？」

**不是。** 看关键这两行：

- `sent 448,598 bytes` —— 这一次实际**发出去**的数据，约 438KB；
- `total size is 180,932,509` —— 这是 `public/` 全部文件的总大小，rsync 只是拿它来**做比对**（判断哪些文件变了），并不代表传了 180MB；
- `speedup is 95.07` —— 它跳过了约 95 倍的数据量，也就是只有 ~1/95 真正移动了。

rsync 的增量机制是：先在两端比较文件的大小和修改时间，只在必要时才传差异块。所以你改一篇文章，就只传那一篇。180MB 里绝大多数是旧 WordPress 迁移过来的媒体文件（`public/uploads` 占了 148MB），它们传过一次就再也不会动了，每次只是被 `stat()` 比对一下，很快。

> 所以「每次更新都要全部重传」这个担忧可以放下。真正的毛病在别处。

## 三、排查：那三个失败的文件

报错信息里紧挨着 `code 23` 打印出来的三个文件名，就是「没传成功」的文件：

```
uploads/wp-content/uploads/2026/10/image-1-300x135.png
uploads/wp-content/uploads/2026/10/image-1-768x347.png
uploads/wp-content/uploads/2026/10/image-1.png
```

`code 23 = 部分文件传输失败`。这三个文件是 WordPress 当年生成的原图 + 缩略图，路径还保留着 WP 的 `wp-content/uploads/` 结构（迁移时我把旧站媒体原样搬进了 `static/`，Hugo 构建时再拷到 `public/`）。

为什么偏偏这三张图传不过去？因为它们在 VPS 上的**属主不是部署账号**，而是旧 WordPress 运行时用户（典型如 `www-data`）。我的部署 SSH 用户不是这些文件的主人，于是在 `-a`（归档，保留属主/权限）加上 `--delete` 的模式下，rsync 既覆盖不了、也删不掉它们 → 这三个文件传输失败 → 撞上 `set -e` → job 失败。

## 四、坑一：.user.ini 不可变，连 root 都改不了

既然是属主问题，第一反应自然是上 VPS 手动归一化：

```bash
sudo chown -R dreamfly:dreamfly 80shihua
```

结果只有一行报错：

```
chown: changing ownership of '80shihua/.user.ini': Operation not permitted
```

其余文件（包括那三个 `image-1*.png`）都成功改属主了，唯独 `.user.ini` 改不动。这不是权限没给够，而是**宝塔（aaPanel）给每个站点目录下的 `.user.ini` 加了 `chattr +i`（immutable，不可变）属性**。它是 PHP 的 `open_basedir` 安全限制文件，被锁成不可变后，连 root 的 `chown`/`chmod`/`rm` 都动不了它。

这其实是**正常且期望的行为**，不用去强行解锁它——我们后面会让 rsync 主动避开它。

## 五、坑二：.well-known 目录不能删，否则 SSL 续期崩

手动 chown 之后，属主问题看似解决了，但还有第二个雷没排：rsync 带了 `--delete`，会尝试**删除目标目录里那些不在 `public/` 中的旧文件**。这里面有两个特殊文件/目录必须保住：

1. **`.user.ini`**：不可变，rsync 删它必然 `Operation not permitted` → 又是一个 `code 23`；
2. **`.well-known/`**：宝塔的 Let's Encrypt 证书用 `80shihua/.well-known/acme-challenge/` 做 HTTP-01 验证来自动续期。一旦被 `--delete` 清掉，将来 SSL 证书自动续期就会失败，站点某天突然变「不安全」。

所以正确的做法不是去删/解锁它们，而是**在 rsync 里显式排除**这两个路径，让同步永远不去碰它们。

## 六、最终修法：归一化属主 + 排除关键目录

部署工作流最终改成三步：

**1. 提前准备好 SSH 私钥**（原来私钥是在 rsync 步骤里才写的，会导致前面的权限步骤跑的时候密钥还不存在，已拆出来）：

```yaml
- name: Prepare SSH key
  run: |
    mkdir -p ~/.ssh
    printf '%s\n' "${{ secrets.SSH_KEY }}" > ~/.ssh/deploy_key
    chmod 600 ~/.ssh/deploy_key
    ssh-keyscan -p 99 -H "${{ secrets.SSH_HOST }}" >> ~/.ssh/known_hosts 2>/dev/null || true
    if [ -z "${{ secrets.SSH_HOST }}" ] || [ -z "${{ secrets.SSH_USER }}" ] || [ -z "${{ secrets.DEPLOY_PATH }}" ]; then
      echo "::error::SSH_HOST / SSH_USER / DEPLOY_PATH 未设置"
      exit 1
    fi
```

**2. 部署前 SSH 进 VPS，把远端目录属主/权限归一化**（best-effort，失败不阻断后续）：

```yaml
- name: Normalize remote perms (best-effort)
  run: |
    ssh -p 99 -i ~/.ssh/deploy_key -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      "${{ secrets.SSH_USER }}@${{ secrets.SSH_HOST }}" \
      "sudo chown -R \$(whoami) '${{ secrets.DEPLOY_PATH }}' 2>/dev/null || chown -R \$(whoami) '${{ secrets.DEPLOY_PATH }}' 2>/dev/null; chmod -R u+rwX '${{ secrets.DEPLOY_PATH }}' 2>/dev/null" \
      || true
```

> 注意：CI 里的 `chown` 要真正生效，部署 SSH 用户必须是 root 或配了免密 sudo。否则这步会静默失效——最稳的还是上 VPS 以 root 手动跑一次 `chown -R 部署用户: /www/wwwroot/80shihua` 一次性修正。

**3. rsync 加两个 `--exclude`，避开不可变文件和证书续期目录**：

```yaml
- name: Deploy via rsync over SSH
  run: |
    set -e
    rsync -avzr --delete \
      --exclude='.user.ini' \
      --exclude='.well-known/' \
      -e "ssh -p 99 -i ~/.ssh/deploy_key -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null" \
      public/ "${{ secrets.SSH_USER }}@${{ secrets.SSH_HOST }}:${{ secrets.DEPLOY_PATH }}/"
```

改完提交、推送，这次 Actions 顺利跑通。旧的 `index.php`、`wp-admin/`、`wp-includes/` 等 WordPress 残留被 `--delete` 清掉，对纯静态站来说是预期内的清理，无碍。

## 七、经验清单

1. **rsync 是增量的**，看日志别被 `total size` 吓到，盯 `sent` 才是真实传输量。
2. **`code 23` 多半是远端权限/属主冲突**：目标目录里残留了其他用户（如 `www-data`）拥有的文件，部署账号覆盖/删除不了。
3. **宝塔站点的 `.user.ini` 是 immutable**，别试图 `chown` 它，让 rsync 用 `--exclude` 绕开。
4. **永远 `--exclude='.well-known/'`**，否则哪天 HTTPS 证书悄悄续期失败，排查起来要命。
5. **密钥/凭证的准备步骤要排在真正使用它之前**，否则会出现「上一步还没准备好，下一步就用」的时序 bug。
6. 部署账号最好直接是 root 或配免密 sudo，远端属主归一化才能稳定自愈。

排障的本质，往往不是工具不会用，而是「以为干净的目录其实还躺着上一个时代的残留」。把属主理顺、把不该碰的路径排除掉，rsync 就又变回了那个安静又高效的增量同步器。

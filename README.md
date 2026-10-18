# 80shihua.com → Hugo 迁移方案（已验证）

> 实测已通过：842 篇文章 + 14 个页面成功迁移到本地 Hugo，所有 URL 与线上 1:1 对齐。

## 一、线上 WordPress 结构（已实测）
站点固定链接基址设为 `archives`，因此文章/分类/标签/作者 URL 都带 `/archives/` 前缀：

| 类型 | WordPress URL | Hugo 还原方式 |
|---|---|---|
| 文章 | `/archives/{id}/`（自定义 `%post_id%`） | `permalinks.posts = "/archives/:slug/"`，slug=数字ID |
| 分类 | `/archives/category/{slug}/` | `permalinks.categories = "/archives/category/:slug/"` |
| 标签 | `/archives/tag/{slug}/` | `permalinks.tags = "/archives/tag/:slug/"` |
| 作者 | `/archives/author/{slug}/` | `permalinks.authors = "/archives/author/:slug/"` |
| 页面 | `/{slug}/`（页面不受 archives 基址影响） | `content/{slug}.md` → `/{slug}/` |
| 分页 | `/page/2/`、`/archives/category/x/page/2/` | `paginatePath = "page"`（Hugo 默认） |

**关键踩坑（已解决）**：
1. Hugo taxonomy 的 permalink 键要用**复数**（`categories`/`tags`/`authors`），单数 `category` 不生效（v0.168 实测）。
2. front matter 里 taxonomy 也要用**复数键**（`authors = [...]`），单数 `author` 会被忽略、术语不生成。
3. WP REST API 返回的中文 slug 是**百分号编码**（`%e4%b8%aa...`）。直接用作术语 slug 会导致整页不生成；脚本里用 `urllib.parse.unquote` 解码为原始中文，让 Hugo 自行编码，语义与 WP 一致。
4. **不要**为分类/标签/作者手写 `content/categories/{slug}/_index.md`，否则会被 Hugo 当成 section 同时生成默认 `/categories/{slug}/` 造成重复页。交给 taxonomy 自动生成 + permalink 即可。

## 二、本地工程结构
```
80shihua-hugo/
├── config.toml          # taxonomy + 精确 permalinks
├── migrate.py           # WP REST API → Hugo 内容（stdlib，无需 pip）
├── hugo_bin/hugo.exe    # 已下载的 Hugo v0.168 extended（仅本地验证用，可不纳入版本库）
├── content/
│   ├── posts/{id}.md    # 842 篇，slug=数字ID，正文保留原始 HTML
│   └── {slug}.md        # 14 个独立页面
├── layouts/             # 最小化模板（baseof / index / single / list / terms）
└── public/              # hugo 构建产物（静态站）
```

## 三、迁移步骤
```bash
# 1. 拉取并生成内容（需能访问 www.80shihua.com）
python migrate.py
#    → content/posts/*.md + content/*.md（页面）

# 2. 本地预览
hugo server -D
#    访问 http://localhost:1313/ ，文章地址应为 /archives/3445/ 等

# 3. 构建静态产物
hugo --gc
#    → public/
```

> Hugo 二进制：本机未预装，已下载 `hugo_extended_0.168.0_windows-amd64` 到 `hugo_bin/`。正式环境用 `scoop install hugo-extended` 或官网安装包即可。

## 四、上线部署
- `public/` 是纯静态站，可托管 Cloudflare Pages / Vercel / Nginx / 任意对象存储。
- 域名沿用 `www.80shihua.com`，在 DNS 或 Cloudflare 指向新静态主机。
- 旧 WP 站点先保留作备份，确认无误后再切 DNS。

## 五、URL 一致性兜底
- permalinks 已对齐，绝大多数链接与线上字节级一致。
- **已知细微差异**：中文路径 Hugo 编码为大写 `%E4%B8%AA...`，WP 原站为小写 `%e4%b8%aa...`；浏览器/搜索引擎视为等价，无 SEO 影响。若需逐字节一致，可在 `hugo` 构建后加一步后处理（把 `public/archives/**` 下目录名中的 `%XX` 转小写）或用 CDN/Server 规则统一规范化。
- 每篇文章 front matter 保留 `original_link`，可脚本比对校验。

## 六、迁移后增强（可选）
- **评论**：WP 评论不迁移，接 Giscus / Disqus / Utterances（改 `layouts/_default/single.html`）。
- **搜索**：静态站用 Pagefind（构建后索引，零后端）。
- **图片**：正文图片目前仍指向 `www.80shihua.com` 原域名。可后续批量下载到 `static/uploads/` 并改写链接，实现完全自托管。
- **RSS / sitemap**：Hugo 原生输出 `index.xml`、`sitemap.xml`。
- **SEO / AI 索引（已落地）**：
  - `layouts/partials/seo.html` 统一输出：canonical、robots 抓取指令、Open Graph、Twitter Card，以及 JSON-LD 结构化数据（首页 WebSite / 文章 BlogPosting / 列表 CollectionPage）。
  - `static/robots.txt`：允许抓取并指向 `sitemap.xml`。
  - `llms.txt`（根目录，由 `config/_default/config.toml` 的 `[outputFormats.llms]` + `layouts/_default/index.llms.txt` 生成）：面向大模型的站点索引，含分类、最新 50 篇与 sitemap/RSS 指引，便于 AI 助手检索引用。
  - `<head>` 内通过 `<link rel="alternate" type="text/plain" href="/llms.txt">` 主动暴露给 AI 爬虫。
- **模板美化**：当前为最小可用模板，可按设计稿替换 `layouts/`。

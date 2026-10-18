#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量去除 uncategorized，并按内容归入相关分类/标签。
   映射由人工（AI）逐篇阅读正文后判定。幂等：仅改写 categories/tags 行。
   用法：
     python tools/apply_uncat.py --dry-run    # 仅打印将要写入的 cats/tags
     python tools/apply_uncat.py              # 实际改写
   回退：git checkout -- content/ 即可还原全部改动。
"""
import os, re, glob, sys, json

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# slug -> (分类列表, 标签列表)，均已小写以贴合现有分类命名
REMAP = {
    "1006": (["php"], ["支付", "支付宝", "博客"]),
    "1009": (["essay"], ["音乐", "网易云音乐", "回忆"]),
    "1011": (["javascript"], ["iframe", "z-index", "浏览器兼容", "ie"]),
    "1014": (["javascript"], ["跨域", "图片", "canvas"]),
    "1019": (["server"], ["防盗链", "图片", "服务器"]),
    "1023": (["php"], ["php", "guid", "uuid"]),
    "1024": (["interface"], ["api", "网易", "天气", "接口"]),
    "1043": (["linux"], ["linux", "npm", "nodejs"]),
    "1064": (["essay"], ["程序员", "励志", "转载"]),
    "107": (["ecshop"], ["ecshop"]),
    "1070": (["essay"], ["天涯", "互联网", "转载"]),
    "1071": (["essay"], ["法律", "司考", "趣闻"]),
    "1079": (["server"], ["架构", "微博", "分布式"]),
    "1101": (["reprint"], ["北漂", "程序员", "感悟"]),
    "1107": (["javascript"], ["微信", "图片", "位置", "exif"]),
    "1108": (["javascript"], ["正则", "引擎", "原理"]),
    "1110": (["version"], ["git", "linux", "服务器"]),
    "1113": (["reprint"], ["工程师文化", "转载", "coolshell"]),
    "1132": (["php"], ["搜索", "站内搜索"]),
    "1158": (["interface"], ["api", "音乐", "百度", "酷狗"]),
    "1160": (["php"], ["qq", "php", "接口"]),
    "1173": (["game"], ["游戏", "制作人"]),
    "1198": (["php"], ["php", "常量", "类"]),
    "1210": (["php"], ["微信", "公众号", "接口", "微信公众号开发"]),
    "1215": (["essay"], ["面试", "阿里", "求职"]),
    "1219": (["essay"], ["故事", "感悟"]),
    "1224": (["javascript"], ["微信", "分享", "js"]),
    "1251": (["javascript"], ["js", "focus", "焦点"]),
    "1296": (["python"], ["python", "scrapy", "爬虫", "错误"]),
    "1298": (["python"], ["python", "scrapy", "爬虫"]),
    "1303": (["linux"], ["linux", "开机启动", "shell"]),
    "1315": (["php", "dedecms"], ["dedecms", "织梦", "调用"]),
    "1333": (["php"], ["php", "性能", "in_array"]),
    "1343": (["linux"], ["mac", "homebrew", "开发环境"]),
    "1370": (["linux"], ["iptables", "nat", "端口映射", "转发"]),
    "1416": (["javascript"], ["性能", "前端", "yslow", "优化"]),
    "1423": (["mysql"], ["mysql", "日期", "统计"]),
    "1439": (["javascript"], ["js", "全屏"]),
    "1470": (["php"], ["php", "遍历", "文件夹"]),
    "1475": (["linux"], ["linux", "php", "fileinfo", "扩展"]),
    "1535": (["interface"], ["api", "网易", "新闻", "接口"]),
    "1543": (["essay"], ["随笔", "感悟"]),
    "1574": (["javascript"], ["sublime", "压缩", "js", "css"]),
    "1599": (["c_cplus"], ["c++", "g++", "vscode", "环境配置"]),
    "1619": (["server"], ["乱码", "编码", "服务器"]),
    "1623": (["version"], ["git", "初始化"]),
    "1634": (["movie_review"], ["动漫", "影评", "萤火之森"]),
    "1698": (["php"], ["支付", "幂等性", "接口"]),
    "1705": (["essay"], ["运营", "创业", "转载"]),
    "1708": (["seo"], ["seo", "关键词", "优化"]),
    "1721": (["php", "essay"], ["安全", "挂马", "php"]),
    "1851": (["javascript"], ["js", "json"]),
    "1852": (["essay"], ["百度网盘", "下载", "工具"]),
    "1853": (["essay"], ["百度网盘", "下载", "js"]),
    "1857": (["essay"], ["ue", "用户体验", "网站优化"]),
    "1870": (["essay"], ["河南", "外交部", "资讯"]),
    "1875": (["javascript"], ["iframe", "安全", "x-frame-options"]),
    "1877": (["essay"], ["微信", "今日头条", "公众号", "资讯"]),
    "1878": (["essay"], ["小程序", "微信", "电子名片"]),
    "1880": (["php"], ["php", "thinkphp", "验证码", "bug"]),
    "1983": (["linux", "php"], ["php", "扩展", "ldd"]),
    "2031": (["php", "redis"], ["php", "redis"]),
    "2049": (["essay"], ["科技", "随笔"]),
    "2054": (["server"], ["挂马", "安全", "监测"]),
    "2062": (["go"], ["go", "web"]),
    "2120": (["php"], ["微信支付", "支付"]),
    "2289": (["php"], ["链式操作", "设计模式", "php"]),
    "26": (["javascript"], ["js", "prompt"]),
    "28": (["laugh_young"], ["段子", "搞笑", "寒潮"]),
    "323": (["essay"], ["散文", "文体"]),
    "327": (["beautiful_sentence"], ["丘吉尔", "名言", "励志"]),
    "423": (["php"], ["php", "mvc", "架构"]),
    "428": (["essay"], ["郎咸平", "视频", "分享"]),
    "445": (["javascript"], ["sublime", "snippet", "开发工具"]),
    "473": (["css"], ["css", "动画", "效果"]),
    "519": (["essay"], ["网盘", "秒传", "原理"]),
    "563": (["php"], ["wordpress", "gravatar", "优化"]),
    "592": (["javascript"], ["js", "评论", "劫持"]),
    "595": (["javascript"], ["jquery", "js", "选择器"]),
    "6": (["essay"], ["作者", "简介"]),
    "600": (["javascript"], ["js", "浏览器", "属性检测"]),
    "607": (["essay"], ["excel", "技巧", "办公"]),
    "614": (["beautiful_sentence"], ["名言", "名句", "励志"]),
    "621": (["javascript"], ["umeditor", "编辑器", "js"]),
    "623": (["linux"], ["nginx", "日志", "切割"]),
    "634": (["essay"], ["程序员", "职场", "感悟"]),
    "636": (["essay"], ["时间管理", "方法", "效率"]),
    "638": (["essay"], ["职场", "工资", "感悟"]),
    "644": (["thinkphp"], ["thinkphp", "mysql", "count"]),
    "646": (["essay"], ["编程", "习惯", "修养"]),
    "65": (["essay"], ["猫", "萌宠", "生活"]),
    "819": (["mysql"], ["mysql", "sql", "回车符"]),
    "822": (["java"], ["android", "jdk", "环境配置"]),
    "824": (["css"], ["css", "box-sizing", "盒模型"]),
    "847": (["game"], ["lol", "游戏", "控线"]),
    "852": (["html"], ["防盗链", "iframe", "安全"]),
    "854": (["game"], ["lol", "游戏", "天赋"]),
    "857": (["jquery"], ["百度分享", "分享", "jquery"]),
    "890": (["essay"], ["亚马逊", "职场", "互联网"]),
    "896": (["css"], ["css", "背景", "条纹"]),
    "902": (["essay"], ["程序员", "招聘", "漫画"]),
    "981": (["javascript"], ["jquery", "ajax", "上传"]),
    "983": (["php"], ["php", "base64", "图片"]),
    "995": (["mysql"], ["mysql", "mysqldump", "备份"]),
    "998": (["javascript"], ["分享", "api", "微信", "二维码"]),
}

CAT_RE = re.compile(r'^\s*categories\s*=\s*\[.*?\]\s*$', re.M)
TAG_RE = re.compile(r'^\s*tags\s*=\s*\[.*?\]\s*$', re.M)

def find_file(slug):
    hits = glob.glob(os.path.join(ROOT, "content", "**", slug + ".md"), recursive=True)
    return hits[0] if hits else None

def main():
    dry = "--dry-run" in sys.argv
    updated = 0
    missed = []
    for slug, (cats, tags) in REMAP.items():
        f = find_file(slug)
        if not f:
            missed.append(slug)
            continue
        txt = open(f, encoding="utf-8").read()
        cat_line = 'categories = [' + ', '.join('"%s"' % c for c in cats) + ']'
        tag_line = 'tags = [' + ', '.join('"%s"' % t for t in tags) + ']'
        if dry:
            print("%-6s -> cats=%s tags=%s" % (slug, cats, tags))
            continue
        new = CAT_RE.sub(cat_line, txt, count=1)
        new = TAG_RE.sub(tag_line, new, count=1)
        if new == txt:
            print("WARN 未替换(可能无 categories/tags 行):", slug, f)
        open(f, "w", encoding="utf-8").write(new)
        updated += 1
    if dry:
        print("\n[dry-run] 共 %d 篇待处理，缺失 %d 篇" % (len(REMAP), len(missed)))
    else:
        print("已更新 %d 篇，缺失 %d 篇: %s" % (updated, len(missed), missed))

if __name__ == "__main__":
    main()

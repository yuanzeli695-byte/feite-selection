/**
 * sellersprite_console_extract.js
 *
 * SellerSprite 关键词/榜单搜索页的辅助抓取脚本。员工用法:
 *
 *   1. 在 SellerSprite 里搜一个 keyword_seeds.md 里的种子(例如 "picture frame")
 *   2. 等结果加载完毕
 *   3. F12 打开开发者工具 → Console 标签
 *   4. 粘贴整段本脚本 → 回车
 *   5. 脚本会自动扫描当前页所有商品行,产出 12 列 TSV 到剪贴板
 *   6. 打开 candidate_meta_batch2.tsv,粘贴到表头下面
 *   7. 换下一个关键词,重复
 *
 * 输出列:
 *   asin  title  brand  price  rating  reviews  childSales  parentSales
 *   launchDate  variations  image  sourcePage
 *
 * 注意:
 *   - 因为 Claude 没见过 SellerSprite 的 DOM,本脚本用多种通用选择器兜底
 *   - 若某字段抓不到,输出为空字符串(TSV 里 \t\t 相邻),员工手工补齐
 *   - 输出会自动跳过标题占位符 skeleton 行
 *   - 每次跑会 console.table 显示预览,让员工检查再复制
 */
(function () {
  'use strict';

  var SEED = (function () {
    var el = document.querySelector('input[type="search"], input.search, [class*="search-input"] input');
    if (el && el.value) return el.value.trim();
    // 从 URL 猜
    var u = new URL(location.href);
    var q = u.searchParams.get('keyword') || u.searchParams.get('q') || u.searchParams.get('kw');
    return q || location.pathname.split('/').pop() || 'unknown_seed';
  })();

  function txt(el) {
    if (!el) return '';
    return (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
  }

  function attr(el, name) {
    return el && el.getAttribute(name) || '';
  }

  function normalizeAsin(s) {
    var m = String(s || '').toUpperCase().match(/\b(B0[A-Z0-9]{8})\b/);
    return m ? m[1] : '';
  }

  function parseNum(s) {
    if (s == null) return '';
    var m = String(s).replace(/[,$]/g, '').match(/-?\d+(\.\d+)?/);
    return m ? m[0] : '';
  }

  // 找候选行:SellerSprite 常见是 table tr 或卡片式 .product-item / [data-asin]
  function findRows() {
    var candidates = [];
    // 优先带 data-asin 的元素
    var tagged = document.querySelectorAll('[data-asin]');
    if (tagged.length >= 3) {
      tagged.forEach(function (n) { candidates.push(n); });
      return candidates;
    }
    // 表格 tr
    var trs = document.querySelectorAll('table tbody tr');
    if (trs.length >= 3) {
      trs.forEach(function (t) { if (t.querySelector('a')) candidates.push(t); });
      return candidates;
    }
    // 卡片 class 名启发
    var cards = document.querySelectorAll(
      '.product-card, .product-item, [class*="product-row"], [class*="listing-item"], [class*="ss-product"]'
    );
    if (cards.length >= 3) {
      cards.forEach(function (c) { candidates.push(c); });
      return candidates;
    }
    // 兜底: 找所有包含 amazon.com/dp/ 链接的父容器
    var links = document.querySelectorAll('a[href*="amazon.com/dp/"], a[href*="/dp/"]');
    links.forEach(function (a) {
      var row = a.closest('tr, li, div[class*="item"], div[class*="row"], div[class*="card"]');
      if (row && candidates.indexOf(row) < 0) candidates.push(row);
    });
    return candidates;
  }

  function extractRow(row) {
    // ASIN 优先从 data-asin, 其次从链接
    var asin = attr(row, 'data-asin') || '';
    if (!normalizeAsin(asin)) {
      var link = row.querySelector('a[href*="amazon.com/dp/"], a[href*="/dp/"]');
      if (link) asin = normalizeAsin(link.href);
    }
    if (!normalizeAsin(asin)) {
      var t = txt(row);
      asin = normalizeAsin(t);
    }
    asin = normalizeAsin(asin);
    if (!asin) return null;

    // 标题
    var title = '';
    var titleEl = row.querySelector(
      'a[href*="amazon.com/dp/"], a[href*="/dp/"], [class*="title"] a, [class*="name"] a, .title, .name'
    );
    if (titleEl) title = txt(titleEl);
    if (!title) {
      var img = row.querySelector('img[alt]');
      if (img) title = attr(img, 'alt');
    }

    // 品牌
    var brand = '';
    var brandEl = row.querySelector('[class*="brand"], [data-field="brand"]');
    if (brandEl) brand = txt(brandEl);

    // 价格
    var price = '';
    var priceEl = row.querySelector(
      '[class*="price"] :not([class*="original"]), [class*="price"], [data-field="price"]'
    );
    if (priceEl) price = parseNum(txt(priceEl));

    // 评分
    var rating = '';
    var ratingEl = row.querySelector('[class*="rating"], [class*="score"], [class*="star"]');
    if (ratingEl) {
      var rtxt = txt(ratingEl);
      var m = rtxt.match(/([1-5](?:\.\d)?)/);
      rating = m ? m[1] : '';
    }

    // 评论数
    var reviews = '';
    var reviewEl = row.querySelector('[class*="review"], [class*="comment"]');
    if (reviewEl) reviews = parseNum(txt(reviewEl));

    // 月销
    var childSales = '';
    var parentSales = '';
    var salesEls = row.querySelectorAll('[class*="sales"], [class*="volume"], [class*="monthly"]');
    if (salesEls.length >= 1) childSales = parseNum(txt(salesEls[0]));
    if (salesEls.length >= 2) parentSales = parseNum(txt(salesEls[1]));

    // 上架日期
    var launchDate = '';
    var launchEl = row.querySelector('[class*="launch"], [class*="publish"], [class*="onboard"], [class*="date"]');
    if (launchEl) {
      var lt = txt(launchEl);
      var dm = lt.match(/\d{4}[-/]\d{1,2}[-/]\d{1,2}/);
      launchDate = dm ? dm[0].replace(/\//g, '-') : '';
    }

    // 变体
    var variations = '';
    var varEl = row.querySelector('[class*="variant"], [class*="variation"], [class*="child-count"]');
    if (varEl) variations = parseNum(txt(varEl));

    // 图片
    var image = '';
    var imgEl = row.querySelector('img[src], img[data-src]');
    if (imgEl) image = attr(imgEl, 'src') || attr(imgEl, 'data-src');

    return {
      asin: asin,
      title: title,
      brand: brand,
      price: price,
      rating: rating,
      reviews: reviews,
      childSales: childSales,
      parentSales: parentSales,
      launchDate: launchDate,
      variations: variations,
      image: image,
      sourcePage: SEED,
    };
  }

  var rows = findRows();
  console.log('[ss-extract] found', rows.length, 'candidate rows for seed:', SEED);

  var extracted = [];
  rows.forEach(function (r) {
    var rec = extractRow(r);
    if (rec) extracted.push(rec);
  });
  console.log('[ss-extract] extracted', extracted.length, 'valid ASIN rows');

  if (!extracted.length) {
    console.warn('[ss-extract] nothing extracted; DOM 可能和脚本预期不一致');
    console.warn('  员工请截图当前页,发给 Claude 让他做精准适配版');
    return;
  }

  // 输出 TSV(不含表头 —— 员工文件里已有)
  var tsv = extracted.map(function (rec) {
    return [
      rec.asin, rec.title, rec.brand, rec.price, rec.rating, rec.reviews,
      rec.childSales, rec.parentSales, rec.launchDate, rec.variations,
      rec.image, rec.sourcePage,
    ].map(function (v) { return String(v).replace(/\t|\n|\r/g, ' '); }).join('\t');
  }).join('\n');

  console.table(extracted.slice(0, 5));
  console.log('[ss-extract] TSV preview (first 500 chars):\n' + tsv.slice(0, 500));

  // 复制到剪贴板
  var textarea = document.createElement('textarea');
  textarea.value = tsv;
  textarea.style.position = 'fixed';
  textarea.style.top = '-9999px';
  document.body.appendChild(textarea);
  textarea.select();
  var ok = false;
  try {
    ok = document.execCommand('copy');
  } catch (e) {}
  document.body.removeChild(textarea);

  if (ok) {
    console.log('[ss-extract] ✅ 已复制 ' + extracted.length + ' 行 TSV 到剪贴板,粘贴到 candidate_meta_batch2.tsv 表头下面');
  } else {
    console.log('[ss-extract] ⚠ 剪贴板复制失败,请手动复制上方 TSV preview 的完整版:');
    console.log('===COPY START===');
    console.log(tsv);
    console.log('===COPY END===');
  }
})();

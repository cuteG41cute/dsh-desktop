// dsh-manager：让「文件夹拖入」在 WebView 窗口里也能用。
//
// 产品的前端判断逻辑（dsh-client-ui-conversation）是：
//   const bridge = globalThis.__DSH_HOST_PATHS__;          // 桌面版注入的“文件→绝对路径”桥
//   if (bridge === undefined && 拖的是目录) return "只有桌面端支持添加文件夹";
//   const path = bridge?.pathFor(file) ?? "";
//   if (目录 && path === "") return "无法获取文件夹路径";
// 所以只要补上这个桥，文件夹就能像桌面版一样被识别。
//
// 浏览器拿不到真实绝对路径（Chromium 不暴露），这里给**相对当前工作区的名字**
// （例如 `报告素材`）：产品随后会 relativizeToCwd + 生成 `@报告素材/` 引用，
// 对“工作区里的文件夹”完全够用；工作区外的文件夹引用会落空，这点在文档里写明。
(function () {
  if (window.__dshHostPaths) return;
  window.__dshHostPaths = true;

  var dirNames = Object.create(null);   // name -> true（本次拖动里出现过的目录）
  var dirCount = Object.create(null);

  function remember(dataTransfer) {
    try {
      if (!dataTransfer || !dataTransfer.items) return;
      for (var i = 0; i < dataTransfer.items.length; i++) {
        var it = dataTransfer.items[i];
        if (!it || it.kind !== 'file' || typeof it.webkitGetAsEntry !== 'function') continue;
        var entry = null;
        try { entry = it.webkitGetAsEntry(); } catch (e) { entry = null; }
        if (!entry || !entry.isDirectory) continue;
        var name = entry.name || '';
        if (!name) continue;
        dirNames[name] = true;
        dirCount[name] = (dirCount[name] || 0) + 1;
      }
    } catch (e) {}
  }

  // 桥：只对“目录”返回路径；普通文件返回空串 → 保持原有的上传/附件逻辑
  window.__DSH_HOST_PATHS__ = {
    pathFor: function (file) {
      try {
        if (file && dirNames[file.name]) return String(file.name);
      } catch (e) {}
      return '';
    },
  };

  // 捕获阶段先记下这次拖动里哪些是目录（产品的 drop 处理在冒泡阶段读桥）
  document.addEventListener('dragenter', function (e) { remember(e.dataTransfer); }, true);
  document.addEventListener('dragover', function (e) { remember(e.dataTransfer); }, true);
  document.addEventListener('drop', function (e) {
    remember(e.dataTransfer);
    // 异步清空，确保产品同一次 drop 里读得到
    setTimeout(function () { dirNames = Object.create(null); dirCount = Object.create(null); }, 1500);
  }, true);
})();

# DSH 桌面版 v1.5.0 — 登录用内置浏览器打开，不再"关窗口"

## 修了什么

在 DSH WebUI 里点「登录」，原来会**整个程序退出**（用户原话：程序只是关闭了窗口）。
现在点「登录」会在**内置浏览器窗口**里打开 DeepSeek 授权页，对话窗口原地不动。

## 根因（可复现）

DSH 客户端的登录实现（`dsh-client-ui-settings-account/lib/client.js:999`）：

```js
this.popup = window.open("about:blank", "_blank");
if (this.popup) this.popup.opener = null;
...
if (this.popup && !this.popup.closed) this.popup.location.replace(authorizeUrl);
```

桌面版原来靠在 WebKit 的 `create` 信号里**自己返回一个 WebView** 来接住这个弹窗。
但 WebKitGTK 2.4x 在**没有 features 参数**的 `window.open('about:blank')` 上，
返回 WebView 会踩到引擎内部的断言：

```
optional:1179: const _Tp &std::optional<WebCore::WindowFeatures>::operator*() const
Assertion 'this->_M_is_engaged()' failed.
```

直接 `abort` —— 进程连同所有窗口一起消失。所以"点登录＝关窗口"。

最小复现器：`tools/host/vm-popup-probe.py` + `tools/host/vm-probe-popup.sh`
（一个 60 行的 GTK 宿主，稳定复现这条断言）。

## 怎么改的

1. **不再在 `create` 里返回 WebView**：`create` 一律返回 `None`（这次弹窗被拦，进程安全），
   只作为兜底把地址交给内置浏览器。
2. **注入脚本接管 `window.open`**（`POPUP_JS`）：立刻通知宿主开内置浏览器窗口，
   并返回一个**假窗口对象**，把 DSH 用到的接口都实现了：
   `location.replace/assign/href`、`closed`、`close()`、`opener`、`focus/postMessage`。
   宿主这边 `dsh-popup-open / dsh-popup-nav / dsh-popup-close` 三个消息负责
   开窗、导航、关窗；用户手动关掉窗口时回传 `__dshPopupClosed(id)`，让 `closed` 变真。
3. **内置浏览器窗口重新设计**：这台机器上 GTK 是 `GTK_CSD=0` 跑的，
   `Gtk.HeaderBar` 会被系统忽略（实测只剩一条系统标题栏，返回/刷新/地址全没了）。
   改成普通 `Gtk.Box` 自己画工具栏：后退 / 刷新 / 可选中地址 / 用系统浏览器打开 / 关闭；
   窗口尺寸取屏幕 88%，不再被 KWin 最大化铺满。
4. **主窗口防丢**：页面若用 `location.href` 自己跳去站外，主窗口会开一个内置浏览器接住该页，
   然后退回 DSH（不再把会话窗口顶掉）。
5. **启动器修了一处**：`PREFIX/app/node_modules/.../dsh/lib/bin.js` 现在会被找到
   （从菜单/图标启动时 PATH 里没有 dsh，原来会报"未找到 DeepSeek Harness"）。

## 验证

- 最小复现器：改前 `open -> NULL` + 断言 abort；改后无断言、进程存活。
- 真实 DSH 页面端到端（`tools/host/vm-test-login-e2e.sh`，自动点「登录」）：
  ```
  [dsh-desktop] 为页面打开窗口：about:blank
  [dsh-desktop] 内置窗口导航：https://platform.deepseek.com/dsh/authorize?authorize_id=…&theme=light
  ```
  截图里内置浏览器窗口正显示手机号/验证码 + 微信扫码的授权页，后面的对话窗口完好。
- 注入脚本自检（`dsh-desktop.py --selftest`）：
  `✓ 页面 window.open 走宿主内置浏览器（假窗口对象）`
  `✓ create 兜底不返回 WebView（避开 WebKitGTK 断言崩溃）`

## 安装

```bash
sudo dpkg -i dsh-manager_1.5.0_all.deb
```

装完重开桌面窗口即可（已在运行的旧窗口仍是旧代码）。

- 大小：3,899,510 字节
- sha256：`14a374a43a9863c47622b9304323163c6ce4f9452ee5ce86f6047c9b70c77ffd`

// Close the KWin debug console (opened by mistake) and focus the manager window.
for (const w of workspace.windowList()) {
    const cap = String(w.caption || "");
    const cls = String(w.resourceClass || "");
    if (cap.indexOf("\u8c03\u8bd5\u63a7\u5236\u53f0") >= 0) {
        print("closing debug console");
        w.closeWindow();
    }
    if (cls.indexOf("dsh-manager") >= 0) {
        print("focusing manager: " + cap);
        workspace.activeWindow = w;
    }
}
print("done");

using System;
using System.Text;
using System.Windows.Input;

namespace DshManager
{
    public partial class DshWebWindow
    {
        /// <summary>Ctrl+Shift+Alt+D：dump 右栏预览的 DOM（含内联样式），诊断缩放用。</summary>
        private void HookDomDumpHotkey()
        {
            try
            {
                PreviewKeyDown += async (_, e) =>
                {
                    if (e.Key == Key.D &&
                        Keyboard.Modifiers == (ModifierKeys.Control | ModifierKeys.Shift | ModifierKeys.Alt))
                    {
                        e.Handled = true;
                        var js = @"(function(){
  function info(el){
    if(!el) return null;
    var cs=getComputedStyle(el), r=el.getBoundingClientRect();
    return {tag:el.tagName,cls:(el.className||'').toString().slice(0,120),
      rect:[Math.round(r.x),Math.round(r.y),Math.round(r.width),Math.round(r.height)],
      styleAttr:(el.getAttribute('style')||'').slice(0,300),
      transform:cs.transform,overflow:cs.overflow,zoom:cs.zoom,w:cs.width,h:cs.height};
  }
  var imgs=[].slice.call(document.querySelectorAll('img')).map(function(el){
    var r=el.getBoundingClientRect(); return {el:el,area:r.width*r.height};
  }).sort(function(a,b){return b.area-a.area;});
  var big=imgs.length?imgs[0].el:null;
  var out={type:'dsh-dom-dump',badge:null,big:info(big),chain:[],
    badges:[].slice.call(document.querySelectorAll('[class*=dsh-pv],[id*=dsh-pv]')).slice(0,6)
      .map(function(e){return {tag:e.tagName,id:e.id,cls:(e.className||'').toString().slice(0,80),text:(e.textContent||'').slice(0,60)};})};
  if(big){ var el=big.parentElement;
    for(var i=0;el&&i<7;i++){ out.chain.push(info(el)); el=el.parentElement; } }
  window.chrome.webview.postMessage(JSON.stringify(out));
})();";
                        await Web.CoreWebView2.ExecuteScriptAsync(js);
                        Diag("dom dump requested");
                    }
                };
            }
            catch (Exception ex) { Diag("hotkey hook failed: " + ex.Message); }
        }
    }
}

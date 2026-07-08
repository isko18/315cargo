// JS-инъекции для WebView Pinduoduo.
//
// pddInterceptHookJs — перехватывает ответ order_list_v4 (fetch + XHR) и отдаёт
// тело в Flutter через handler 'pddOrders'. Инъекция AT_DOCUMENT_START.
//
// pddAutoSyncJs — сам проходит вкладки заказов + скроллит (грузит все страницы),
// чтобы PDD сделал order_list_v4 по всем активным заказам. Клиент не участвует.

const String pddInterceptHookJs = r"""
(function () {
  var TARGET = 'order_list_v4';
  function send(body) {
    try { window.flutter_inappwebview.callHandler('pddOrders', body); } catch (e) {}
  }
  var of = window.fetch;
  window.fetch = function () {
    var args = arguments;
    return of.apply(this, args).then(function (resp) {
      try {
        var u = (args[0] && args[0].url) || args[0];
        if (typeof u === 'string' && u.indexOf(TARGET) > -1) resp.clone().text().then(send);
      } catch (e) {}
      return resp;
    });
  };
  var oOpen = XMLHttpRequest.prototype.open;
  var oSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__u = u; return oOpen.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () {
    var self = this;
    this.addEventListener('load', function () {
      try { if (self.__u && self.__u.indexOf(TARGET) > -1) send(self.responseText); } catch (e) {}
    });
    return oSend.apply(this, arguments);
  };
})();
""";

const String pddAutoSyncJs = r"""
(function(tabs){
  var i = 0;
  function clickTab(t){
    var els = document.querySelectorAll('div,span,a,li');
    for (var k=0;k<els.length;k++){
      var el = els[k], txt = (el.textContent||'').trim();
      if (txt.indexOf(t)===0 && txt.length <= t.length+3 && el.offsetParent!==null){ el.click(); return true; }
    }
    return false;
  }
  function scroll(n, cb){
    var k=0;
    var iv=setInterval(function(){
      window.scrollTo(0, document.body.scrollHeight);
      window.dispatchEvent(new Event('scroll'));
      if(++k>=n){ clearInterval(iv); cb&&cb(); }
    }, 700);
  }
  function step(){
    if(i<tabs.length){ clickTab(tabs[i]); i++; setTimeout(function(){ scroll(4, step); }, 1200); }
  }
  step();
})(['待收货','待发货','全部']);
""";

(function () {
'use strict';
var D = JSON.parse(document.getElementById('dados').textContent);
var G = D.grafo;
var ABAS = ['geral', 'grafo', 'ondas', 'metricas', 'pendencias', 'repos'];
var NOME = {analise:'análise', assunto:'assunto', item:'item da análise', ponto:'ponto em aberto', er:'ER', et:'ET',
  er_req:'requisito da ER', et_req:'requisito da ET', esboco:'esboço', sql:'script de banco', onda:'onda', aceite:'aceite', tarefa:'tarefa', commit:'commit',
  execucao:'execução', mutante:'mutante', revisao:'revisão', pendencia:'pendência', decisao:'decisão', parecer:'parecer'};
var $ = function (id) { return document.getElementById(id); };

/* ------------------------------------------------------------------ abas e tema */
var iniciado = false;
function mostra(aba) {
  ABAS.forEach(function (a) {
    var s = $('aba-' + a), t = $('t-' + a), on = a === aba;
    s.classList.toggle('ativa', on);
    t.setAttribute('aria-selected', on ? 'true' : 'false');
    t.tabIndex = on ? 0 : -1;
  });
}
function rota() {
  var p = decodeURIComponent(location.hash.slice(1)).split('/');
  var aba = ABAS.indexOf(p[0]) >= 0 ? p[0] : 'geral';
  mostra(aba);
  if (aba === 'grafo') {
    iniciaGrafo();
    var id = p.slice(1).join('/');
    if (id && porId[id] && porId[id] !== sel) irPara(porId[id]);   // Voltar do navegador cai aqui com o nó anterior
  }
}
// cada nó visitado entra no histórico (sem disparar hashchange): Voltar volta ao anterior e o link é compartilhável
function marca(n) {
  var h = '#grafo/' + encodeURIComponent(n.id);
  if (location.hash !== h) { try { history.pushState(null, '', h); } catch (x) { location.hash = h; } }
}
window.addEventListener('hashchange', rota);
$('t-geral').parentNode.addEventListener('keydown', function (e) {
  var i = ABAS.indexOf((document.activeElement.id || '').slice(2));
  if (i < 0 || (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft')) return;
  var j = (i + (e.key === 'ArrowRight' ? 1 : ABAS.length - 1)) % ABAS.length;
  location.hash = ABAS[j]; $('t-' + ABAS[j]).focus();
});
document.addEventListener('click', function (e) {
  var t = e.target.closest && e.target.closest('[data-no]');
  if (t && !(e.target.closest('a[href]'))) location.hash = 'grafo/' + encodeURIComponent(t.getAttribute('data-no'));
});
$('tema').addEventListener('click', function () {
  var raiz = document.documentElement, atual = raiz.getAttribute('data-theme');
  var escuro = atual ? atual === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  raiz.setAttribute('data-theme', escuro ? 'light' : 'dark');
  try { localStorage.setItem('painel-tema', escuro ? 'light' : 'dark'); } catch (x) {}
  cores = null; sujo();
});

/* ------------------------------------------------------------------ dados do grafo */
var N = G.nos.map(function (a, i) {
  return {i: i, id: a[0], tipo: a[1], rotulo: a[2], detalhe: a[3], arquivo: a[4], lacunas: a[5], c: a[6], s: a[7], y0: a[8], f: a[9],
          x: 0, y: 0, fx: 0, fy: 0, vx: 0, vy: 0};
});
var porId = {};
N.forEach(function (n) { porId[n.id] = n; });
var E = G.arestas.map(function (a) { return {a: N[a[0]], b: N[a[1]], r: G.rotulos[a[2]]}; });
var viz = N.map(function () { return []; }), vizr = N.map(function () { return []; });
E.forEach(function (e) {
  viz[e.a.i].push(e.b); viz[e.b.i].push(e.a);
  vizr[e.a.i].push({n: e.b, r: e.r, saida: true}); vizr[e.b.i].push({n: e.a, r: e.r, saida: false});
});
var LINHA = G.linha, MAX = 48;

/* ------------------------------------------------------------------ estado da tela */
var ligado = {}, reveladas = {}, focoSet = null, isoSet = null, sel = null, quente = null, filtro = '', isolar = false;
var modo = 'fluxo', vis = [], realce = null;
var cv, cx, W = 0, H = 0, zoom = 1, ox = 0, oy = 0, calor = 0, livre = false, pendente = false, grade = {};
var cores = null, arrasta = null, ultimo = null, moveu = false, colunasVis = [], offFaixa = {};
Object.keys(NOME).forEach(function (t) { ligado[t] = G.recolhidos.indexOf(t) < 0; });

function css(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
function lerCores() {
  cores = {suave: css('--suave'), texto: css('--texto'), ruim: css('--ruim'), card: css('--card'), realce: css('--realce')};
  Object.keys(NOME).forEach(function (t) { cores[t] = css('--c-' + t) || '#888'; });
}
function visivel(n) { return (ligado[n.tipo] || reveladas[n.id]) && (!focoSet || focoSet[n.id]) && (!isoSet || isoSet[n.id]); }
// Isolar: só a cadeia do selecionado (origem → … → gerado) fica visível. Calcula com isoSet desligado para não se
// limitar ao que já estava isolado.
function defineIsolamento() {
  isoSet = null;
  $('isolar').setAttribute('aria-pressed', isolar ? 'true' : 'false');
  if (isolar && sel) {
    var a = traco(sel, 1), b = traco(sel, -1); isoSet = {}; isoSet[sel.id] = 1;
    Object.keys(a).concat(Object.keys(b)).forEach(function (k) { isoSet[k] = 1; });
  }
  livre = false; refiltra(); if (modo === 'forca') calor = 1;
  enquadra(); sujo();
}
function ocultos(n) { var k = 0; viz[n.i].forEach(function (v) { if (!visivel(v) && (!focoSet || focoSet[v.id]) && (!isoSet || isoSet[v.id])) k++; }); return k; }

/* ------------------------------------------------------------------ layout */
function refiltra() {
  vis = N.filter(visivel);
  empacota();
  if (modo === 'fluxo') vis.forEach(function (n) { n.x = n.fx; n.y = n.fy; });
  montaGrade();
}
// Fluxo: a ordem de cada coluna vem do Python (a do plano e dos documentos); aqui só se reempacota o que está
// visível, para o filtro e o foco não deixarem buraco nas colunas. As faixas secundárias (ER/ET; decisão/parecer)
// ficam lado a lado, no mesmo nível, quando as colunas visíveis não colidem; senão uma abaixo da outra.
var FOLGA = 44;      // cabe o título da faixa de baixo sem encostar na última linha da de cima
function empacota() {
  var grupos = {}, alt = {}, subs = {}, off = {}, colsDa = {};
  vis.forEach(function (n) { var k = n.c + ':' + n.f; (grupos[k] = grupos[k] || []).push(n); });
  Object.keys(grupos).forEach(function (k) {
    var g = grupos[k]; g.sort(function (a, b) { return a.y0 - b.y0; });
    var f = g[0].f, c = g[0].c;
    alt[f] = Math.max(alt[f] || 0, Math.min(g.length, MAX) * LINHA);
    subs[c] = Math.max(subs[c] || 1, Math.ceil(g.length / MAX));
    (colsDa[f] = colsDa[f] || {})[c] = 1;
  });
  var niveis = [];                                   // [{cols:{}, alt, off}] — faixa 0 sempre num nível só dela
  Object.keys(alt).map(Number).sort().forEach(function (f) {
    var nv = null;
    if (f > 0) nv = niveis.filter(function (x) { return x.f > 0 && !Object.keys(colsDa[f]).some(function (c) { return x.cols[c]; }); })[0];
    if (!nv) { nv = {f: f, cols: {}, alt: 0}; niveis.push(nv); }
    Object.keys(colsDa[f]).forEach(function (c) { nv.cols[c] = 1; });
    nv.alt = Math.max(nv.alt, alt[f]); nv.faixas = (nv.faixas || []).concat([f]);
  });
  var acum = 0;
  niveis.forEach(function (nv) { nv.faixas.forEach(function (f) { off[f] = acum; }); acum += nv.alt + FOLGA; });
  offFaixa = off;
  var x = 0, colx = {}; colunasVis = [];
  G.colunas.forEach(function (col) {
    if (!subs[col.c]) return;
    colx[col.c] = x; colunasVis.push({c: col.c, x: x, w: col.w, tipos: col.tipos, faixas: col.faixas || {0: col.tipos}});
    x += col.w * subs[col.c];
  });
  Object.keys(grupos).forEach(function (k) {
    var g = grupos[k], tot = g.length;
    g.forEach(function (n, i) {
      var col = G.colunas.filter(function (q) { return q.c === n.c; })[0], y;
      if (tot > MAX) y = (i % MAX) * LINHA;
      else y = tot === 1 ? (alt[n.f] - LINHA) / 2 : i * (alt[n.f] - LINHA) / (tot - 1);
      n.fx = colx[n.c] + Math.floor(i / MAX) * col.w; n.fy = off[n.f] + y;
    });
  });
}
function montaGrade() {
  grade = {};
  vis.forEach(function (n) { var k = Math.floor(n.x / 80) + ',' + Math.floor(n.y / 80); (grade[k] = grade[k] || []).push(n); });
}
function passo() {
  var i, j, a, b, dx, dy, d2, f, k, cx0, cy0, ci, lista;
  montaGrade();
  vis.forEach(function (a) {
    cx0 = Math.floor(a.x / 80); cy0 = Math.floor(a.y / 80);
    for (dx = -1; dx <= 1; dx++) for (dy = -1; dy <= 1; dy++) {
      lista = grade[(cx0 + dx) + ',' + (cy0 + dy)]; if (!lista) continue;
      for (j = 0; j < lista.length; j++) {
        b = lista[j]; if (b.i <= a.i) continue;
        var ex = a.x - b.x, ey = a.y - b.y; d2 = ex * ex + ey * ey + 1;
        if (d2 > 6400) continue; f = 1400 / d2;
        a.vx += ex * f; a.vy += ey * f; b.vx -= ex * f; b.vy -= ey * f;
      }
    }
  });
  E.forEach(function (e) {
    if (!visivel(e.a) || !visivel(e.b)) return;
    var ex = e.b.x - e.a.x, ey = e.b.y - e.a.y, d = Math.sqrt(ex * ex + ey * ey) + 0.01, m = (d - 70) * 0.012 / d;
    e.a.vx += ex * m; e.a.vy += ey * m; e.b.vx -= ex * m; e.b.vy -= ey * m;
  });
  vis.forEach(function (n) {
    n.vx -= n.x * 0.0015; n.vy -= n.y * 0.0015;
    if (n !== arrasta) { n.x += n.vx * calor; n.y += n.vy * calor; }
    n.vx *= 0.62; n.vy *= 0.62;
  });
  calor = calor * 0.985;
}
function enquadra() {
  if (!vis.length || !W) return;
  var x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
  vis.forEach(function (n) { x0 = Math.min(x0, n.x); x1 = Math.max(x1, n.x); y0 = Math.min(y0, n.y); y1 = Math.max(y1, n.y); });
  if (modo === 'fluxo') { x1 += 190; y0 -= 40; }        // o rótulo do último nó e os títulos das colunas
  zoom = Math.min(2, Math.max(0.1, 0.92 * Math.min(W / (x1 - x0 + 60), H / (y1 - y0 + 60))));
  ox = -zoom * (x0 + x1) / 2; oy = -zoom * (y0 + y1) / 2;
}
function mudaModo(m) {
  modo = m; $('lay-fluxo').setAttribute('aria-pressed', m === 'fluxo'); $('lay-forca').setAttribute('aria-pressed', m === 'forca');
  vis.forEach(function (n) { n.x = n.fx; n.y = n.fy; n.vx = n.vy = 0; });
  if (m === 'forca') vis.forEach(function (n) { n.x *= 0.45; n.y *= 0.45; });   // parte do fluxo, mais compacto
  calor = m === 'forca' ? 1 : 0; livre = false; montaGrade(); agenda();
}

/* ------------------------------------------------------------------ desenho (só quando algo muda) */
function sujo() { agenda(); }
function agenda() { if (!pendente) { pendente = true; requestAnimationFrame(quadro); } }
function quadro() {
  pendente = false;
  if (!iniciado) return;
  var anima = modo === 'forca' && calor > 0.04;
  if (anima) { passo(); if (!livre) enquadra(); }
  var deslizando = animaPasso();
  desenha();
  if (anima || deslizando) agenda();
}
function ajusta() {
  var g = cv.parentNode.parentNode;
  g.style.height = window.innerWidth > 760 ? Math.max(420, window.innerHeight - g.getBoundingClientRect().top - 16) + 'px' : '';
  var r = cv.getBoundingClientRect(), d = window.devicePixelRatio || 1;
  W = cv.width = Math.max(1, Math.round(r.width * d)); H = cv.height = Math.max(1, Math.round(r.height * d));
  if (!livre) enquadra();
  sujo();
}
function dpr() { return window.devicePixelRatio || 1; }
function mundo(px, py) { return [(px * dpr() - W / 2 - ox) / zoom, (py * dpr() - H / 2 - oy) / zoom]; }
function raio(n) { return n.tipo === 'analise' ? 11 : n.tipo === 'onda' ? 9 : n.tipo === 'assunto' ? 8 : 5.5; }
function traco(n, ate) {
  var ver = {}, fila = [n]; ver[n.id] = 1;
  while (fila.length) {
    var u = fila.pop();
    viz[u.i].forEach(function (v) {
      if (ver[v.id] || !visivel(v)) return;
      // anda só para um lado; do nó raiz também leva o vizinho da mesma coluna (a decisão fica ao lado do aceite)
      if ((ate > 0 ? v.c > u.c : v.c < u.c) || (u === n && v.c === u.c)) { ver[v.id] = 1; fila.push(v); }
    });
  }
  return ver;
}
function atualizaRealce() {
  var foco = sel || quente; realce = null;
  if (!foco) return;
  realce = {}; realce[foco.id] = 1;
  // selecionado: a cadeia inteira (do que o originou ao que gerou) fica viva; só o mouse em cima: os vizinhos diretos
  if (isoSet && foco === sel) { Object.keys(isoSet).forEach(function (k) { realce[k] = 1; }); }
  else if (foco === sel) { var a = traco(sel, 1), b = traco(sel, -1); Object.keys(a).concat(Object.keys(b)).forEach(function (k) { realce[k] = 1; }); }
  else viz[foco.i].forEach(function (v) { realce[v.id] = 1; });
}
function desenha() {
  if (!cores) lerCores();
  atualizaRealce();
  cx.setTransform(1, 0, 0, 1, 0, 0); cx.clearRect(0, 0, W, H);
  cx.translate(W / 2 + ox, H / 2 + oy); cx.scale(zoom, zoom);
  var vx0 = (-W / 2 - ox) / zoom - 40, vx1 = (W / 2 - ox) / zoom + 240, vy0 = (-H / 2 - oy) / zoom - 20, vy1 = (H / 2 - oy) / zoom + 20;
  var q = filtro.toLowerCase();
  // arestas em três lotes (normal, esmaecida, realçada): um traçado por lote, não um por aresta
  var lotes = [[0.5, cores.suave, []], [0.06, cores.suave, []], [0.9, cores.realce, []]];
  E.forEach(function (e) {
    if (!visivel(e.a) || !visivel(e.b)) return;
    if ((e.a.x < vx0 && e.b.x < vx0) || (e.a.x > vx1 && e.b.x > vx1) || (e.a.y < vy0 && e.b.y < vy0) || (e.a.y > vy1 && e.b.y > vy1)) return;
    lotes[!realce ? 0 : (realce[e.a.id] && realce[e.b.id] ? 2 : 1)][2].push(e);
  });
  cx.lineWidth = 1 / zoom;
  lotes.forEach(function (l) {
    if (!l[2].length) return;
    cx.globalAlpha = l[0]; cx.strokeStyle = l[1]; cx.beginPath();
    l[2].forEach(function (e) {
      cx.moveTo(e.a.x, e.a.y);
      if (modo === 'fluxo') { var m = (e.a.x + e.b.x) / 2; cx.bezierCurveTo(m, e.a.y, m, e.b.y, e.b.x, e.b.y); } else cx.lineTo(e.b.x, e.b.y);
    });
    cx.stroke();
  });
  // a relação (cobre, testa, mira…) escrita no meio da aresta realçada, enquanto são poucas para não virar ruído
  if (sel && lotes[2][2].length && lotes[2][2].length <= 80) {
    cx.globalAlpha = 0.95; cx.fillStyle = cores.realce; cx.font = (10 / zoom) + 'px system-ui'; cx.textAlign = 'center';
    lotes[2][2].forEach(function (e) {        // só as arestas do nó selecionado, e não quando a relação é o próprio tipo do alvo
      if ((e.a !== sel && e.b !== sel) || e.r === NOME[e.b.tipo] || e.r === e.b.tipo) return;
      cx.fillText(e.r, (e.a.x + e.b.x) / 2, (e.a.y + e.b.y) / 2 - 3 / zoom);
    });
    cx.textAlign = 'start';
  }
  // rótulos: em Fluxo, todo nó visível leva o seu enquanto couber uma linha por nó na tela (zoom × LINHA ≥ 9 px);
  // em Força, o selecionado, o do mouse, os realçados e as ondas sempre, os demais quando o zoom deixa
  var fonte = fontePx(), cabe = modo === 'fluxo' ? zoom * LINHA >= 9 : zoom > 0.75, rotulados = 0;
  vis.forEach(function (n) {
    if (n.x < vx0 || n.x > vx1 || n.y < vy0 || n.y > vy1) return;
    var casa = !q || (n.id + ' ' + n.rotulo + ' ' + n.detalhe).toLowerCase().indexOf(q) >= 0;
    var vivo = (!realce || realce[n.id]) && casa, r = raio(n);
    cx.globalAlpha = vivo ? 1 : 0.12;
    cx.beginPath(); cx.arc(n.x, n.y, r, 0, 6.2832); cx.fillStyle = cores[n.tipo]; cx.fill();
    if (n.lacunas.length) { cx.lineWidth = 2.2 / zoom; cx.strokeStyle = cores.ruim; cx.stroke(); }
    if (n === sel) { cx.lineWidth = 2 / zoom; cx.strokeStyle = cores.texto; cx.beginPath(); cx.arc(n.x, n.y, r + 3, 0, 6.2832); cx.stroke(); }
    var forte = n === sel || n === quente || n.tipo === 'onda' || n.tipo === 'analise' || (realce && realce[n.id]);
    var fimRotulo = n.x + r + 3;
    if (vivo && (forte || (cabe && (modo === 'fluxo' || rotulados < 450)))) {
      rotulados++; cx.fillStyle = cores.texto; cx.font = fonte + 'px system-ui';
      var larg = modo === 'fluxo' ? larguraColuna(n) - r - 14 : 160, txt = corta(n.rotulo, larg);
      cx.fillText(txt, fimRotulo, n.y + 4); fimRotulo += cx.measureText(txt).width + 4;
    }
    var oc = vivo ? ocultos(n) : 0;     // o +N vai na linha do rótulo, nunca em cima do nó: não se empilha na coluna densa
    if (oc) { cx.fillStyle = cores.suave; cx.font = (fonte * 0.9) + 'px system-ui'; cx.fillText('+' + oc, fimRotulo, n.y + 4); }
  });
  cx.globalAlpha = 1;
  if (modo === 'fluxo') titulos();
}
// tamanho da fonte dos rótulos, em unidades do mundo: 11 px na tela com zoom normal, nunca menos de 9 px na tela
function fontePx() { return Math.max(9 / zoom, Math.min(11 / zoom, 11)); }
// Um título por (coluna, faixa). O da faixa principal fica preso ao topo da tela (acompanha o pan e o zoom); o das
// outras faixas fica acima da própria faixa. Cortado com reticência quando não cabe na coluna.
function titulos() {
  var d = dpr(), font = 12 * d;
  cx.setTransform(1, 0, 0, 1, 0, 0); cx.globalAlpha = 0.92; cx.font = font + 'px system-ui'; cx.textBaseline = 'alphabetic';
  colunasVis.forEach(function (c, i) {
    var prox = colunasVis[i + 1];                            // o título pode ir até a coluna seguinte; a última, até a borda
    Object.keys(c.faixas).forEach(function (f) {
      if (offFaixa[f] === undefined) return;
      var nomes = c.faixas[f].filter(function (t) { return vis.some(function (n) { return n.tipo === t && n.c === c.c; }); })
        .map(function (t) { return NOME[t]; });
      if (!nomes.length) return;
      var sx = (c.x - 6) * zoom + W / 2 + ox, sy = (offFaixa[f] - (f === '0' ? 34 : 20)) * zoom + H / 2 + oy;
      var larg = prox ? (prox.x - c.x - 12) * zoom : W - sx - 8 * d;
      if (f === '0') sy = Math.max(sy, 16 * d);                // preso ao topo
      if (sx > W || sx + larg < 0 || sy < 0 || sy > H + font) return;
      var txt = cortaTela(nomes.join(' · '), larg);
      if (f === '0') { cx.fillStyle = cores.card; cx.fillRect(sx - 3 * d, sy - font, cx.measureText(txt).width + 6 * d, font + 4 * d); }
      cx.fillStyle = cores.suave; cx.fillText(txt, sx, sy);
    });
  });
  cx.globalAlpha = 1;
}
function larguraColuna(n) {
  for (var i = 0; i < colunasVis.length; i++) if (colunasVis[i].c === n.c) return colunasVis[i].w;
  return 230;
}
// corta pelo que cabe na largura (unidades do mundo), com reticência; mede uma vez e aproxima pela proporção
function corta(txt, maxw) {
  var w = cx.measureText(txt).width;
  if (w <= maxw) return txt;
  var k = Math.max(3, Math.floor(txt.length * maxw / w) - 1);
  while (k > 3 && cx.measureText(txt.slice(0, k) + '…').width > maxw) k--;
  return txt.slice(0, k) + '…';
}
var cortaTela = corta;     // o mesmo corte, com a fonte já em pixels de tela (o chamador troca a transformação)

/* ------------------------------------------------------------------ interação */
function acha(px, py) {
  var m = mundo(px, py), melhor = null, dm = Math.pow(14 / zoom, 2), gx = Math.floor(m[0] / 80), gy = Math.floor(m[1] / 80);
  for (var a = -1; a <= 1; a++) for (var b = -1; b <= 1; b++) {
    (grade[(gx + a) + ',' + (gy + b)] || []).forEach(function (n) {
      var d = Math.pow(n.x - m[0], 2) + Math.pow(n.y - m[1], 2); if (d < dm) { dm = d; melhor = n; }
    });
  }
  return melhor;
}
// Ir a um nó vindo de um vizinho, da busca, de uma lacuna ou de outra aba: o isolamento, se ligado, passa a ser a
// cadeia do nó novo (não cai); o foco só cai se o nó estiver fora dele; a tela desliza até o nó em vez de saltar.
function irPara(n) {
  reveladas[n.id] = 1;
  if (n.tipo === 'onda') { $('foco').value = n.id; defineFoco(n.id); }
  else if (focoSet && !focoSet[n.id]) { $('foco').value = ''; defineFoco(''); }
  escolhe(n); if (n.tipo !== 'onda' && !isolar) centraliza(n);
}
var anim = null;
function centraliza(n) {
  if (!n || !W) return;
  var z1 = Math.max(zoom, 0.8), alvo = [-n.x * z1, -n.y * z1];
  var rapido = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  livre = true;
  if (rapido || !iniciado) { zoom = z1; ox = alvo[0]; oy = alvo[1]; sujo(); return; }
  anim = {t0: performance.now(), z0: zoom, x0: ox, y0: oy, z1: z1, x1: alvo[0], y1: alvo[1]};
  agenda();
}
function animaPasso() {
  if (!anim) return false;
  var k = Math.min(1, (performance.now() - anim.t0) / 220), e = 1 - Math.pow(1 - k, 3);    // ease-out
  zoom = anim.z0 + (anim.z1 - anim.z0) * e; ox = anim.x0 + (anim.x1 - anim.x0) * e; oy = anim.y0 + (anim.y1 - anim.y0) * e;
  if (k >= 1) anim = null;
  return true;
}
function escolhe(n) {
  sel = n; livre = true;
  var d = $('detalhe'); d.textContent = '';
  var h = document.createElement('h3'); h.textContent = 'Selecionado'; d.appendChild(h);
  if (!n) {
    var v = document.createElement('span'); v.className = 'avi'; v.textContent = 'Clique num nó.'; d.appendChild(v);
    if (isoSet) defineIsolamento(); else sujo();
    return;
  }
  marca(n);
  var mudou = false;
  viz[n.i].forEach(function (v) { if (!ligado[v.tipo] && !reveladas[v.id]) { reveladas[v.id] = 1; mudou = true; } });
  if (isolar) { defineIsolamento(); mudou = false; }
  else if (mudou) { refiltra(); if (modo === 'forca') calor = Math.max(calor, 0.4); }
  var t = document.createElement('b'); t.textContent = n.rotulo; d.appendChild(t);
  var s = document.createElement('div'); s.className = 'avi'; s.textContent = NOME[n.tipo] + (n.arquivo ? ' · ' + n.arquivo : ''); d.appendChild(s);
  if (n.detalhe) { var p = document.createElement('p'); p.textContent = n.detalhe; d.appendChild(p); }
  n.lacunas.forEach(function (l) { var z = document.createElement('div'); z.className = 'lac'; z.textContent = '⚠ ' + l; d.appendChild(z); });
  // vizinhos por relação e sentido ("aceite ▸" é o que este nó aponta; "◂ cobre" é quem aponta para ele), com o texto
  var grupos = {}, ordem = [];
  vizr[n.i].forEach(function (v) {
    var k = v.saida ? v.r + ' ▸' : '◂ ' + v.r;
    if (!grupos[k]) { grupos[k] = []; ordem.push(k); }
    grupos[k].push(v.n);
  });
  ordem.forEach(function (k) {
    var h4 = document.createElement('h4'); h4.textContent = k + ' (' + grupos[k].length + ')'; d.appendChild(h4);
    var vz = document.createElement('div'); vz.className = 'vizinhos';
    grupos[k].forEach(function (v) {
      var b = document.createElement('button'); b.type = 'button'; b.setAttribute('data-no', v.id);   // o balão mostra o texto inteiro
      var bb = document.createElement('b'); bb.textContent = v.rotulo; b.appendChild(bb);
      if (v.detalhe && v.detalhe !== v.rotulo) b.appendChild(document.createTextNode(' — ' + v.detalhe.slice(0, 60) + (v.detalhe.length > 60 ? '…' : '')));
      b.addEventListener('click', function () { irPara(v); }); vz.appendChild(b);
    });
    d.appendChild(vz);
  });
  if (mudou) centraliza(n); else sujo();
}
function esconderDica() { quente = null; $('dica').hidden = true; }
// O balão com o texto inteiro do nó. A âncora é o ponto do cursor (no canvas: [x, y] da janela) ou o retângulo de
// um elemento da página (vizinho, achado, lacuna, card de onda, linha de tabela); fica preso à janela.
function mostraDica(n, ancora) {
  var d = $('dica'); d.textContent = '';
  var b = document.createElement('b'); b.textContent = n.rotulo; d.appendChild(b);
  var s = document.createElement('span'); s.className = 'avi'; s.textContent = NOME[n.tipo] + (n.arquivo ? ' · ' + n.arquivo : ''); d.appendChild(s);
  if (n.detalhe && n.detalhe !== n.rotulo) d.appendChild(document.createTextNode(n.detalhe));
  n.lacunas.forEach(function (l) { var z = document.createElement('span'); z.className = 'lac'; z.textContent = '⚠ ' + l; d.appendChild(z); });
  d.hidden = false;
  var vw = window.innerWidth, vh = window.innerHeight, w = d.offsetWidth, h = d.offsetHeight, x, y;
  if (ancora.length) {                                     // cursor
    x = ancora[0] + 14; y = ancora[1] + 14;
    if (x + w > vw - 4) x = Math.max(4, ancora[0] - w - 14);
    if (y + h > vh - 4) y = Math.max(4, Math.min(ancora[1] - h - 14, vh - h - 4));
  } else {                                                 // elemento: abaixo dele, ou acima se não couber
    x = Math.max(4, Math.min(ancora.left, vw - w - 4)); y = ancora.bottom + 6;
    if (y + h > vh - 4) y = Math.max(4, ancora.top - h - 6);
  }
  d.style.left = x + 'px'; d.style.top = y + 'px';
}
// Balão em qualquer item da página que aponte um nó (`data-no`), ao passar o mouse ou receber o foco do teclado.
var dicaDe = null;
function dicaElemento(e) {
  var t = e.target.closest && e.target.closest('[data-no]');
  if (!t || t.tagName === 'CANVAS') return;
  var n = porId[t.getAttribute('data-no')]; if (!n) return;
  dicaDe = t; mostraDica(n, t.getBoundingClientRect());
}
function somemDica(e) {
  if (dicaDe && (!e.relatedTarget || !dicaDe.contains(e.relatedTarget))) { dicaDe = null; $('dica').hidden = true; }
}
document.addEventListener('mouseover', dicaElemento);
document.addEventListener('focusin', dicaElemento);
document.addEventListener('mouseout', somemDica);
document.addEventListener('focusout', somemDica);
// rolar (o evento chega depois do mouseover, no quadro seguinte): o balão acompanha o elemento em vez de sumir
document.addEventListener('scroll', function () {
  if (!dicaDe) return;
  var n = porId[dicaDe.getAttribute('data-no')];
  if (n && !$('dica').hidden) mostraDica(n, dicaDe.getBoundingClientRect());
}, true);
function defineFoco(id) {
  focoSet = null;
  if (id && porId[id]) {
    focoSet = {}; focoSet[id] = 1;
    var fila = [[porId[id], 0]];
    while (fila.length) {
      var u = fila.shift(); if (u[1] >= 2 || (u[1] > 0 && u[0].tipo === 'decisao')) continue;   // a decisão é compartilhada: não leva a outras ondas
      viz[u[0].i].forEach(function (v) {
        if (focoSet[v.id] || (v.tipo === 'onda' && v.id !== id)) return;
        focoSet[v.id] = 1; fila.push([v, u[1] + 1]);
      });
    }
  }
  livre = false; refiltra(); if (modo === 'forca') { calor = 1; }
  enquadra(); sujo();
}
function iniciaGrafo() {
  if (iniciado) { ajusta(); return; }
  iniciado = true;
  cv = $('c'); cx = cv.getContext('2d');
  refiltra();
  var tp = $('tipos');
  Object.keys(NOME).filter(function (t) { return G.contagem[t]; }).forEach(function (t) {
    var l = document.createElement('label'); l.className = 't';
    var i = document.createElement('input'); i.type = 'checkbox'; i.checked = ligado[t];
    var c = document.createElement('i'); c.className = 'cor'; c.style.background = 'var(--c-' + t + ')';
    l.appendChild(i); l.appendChild(c); l.appendChild(document.createTextNode(NOME[t] + ' (' + G.contagem[t] + ')'));
    i.addEventListener('change', function () { ligado[t] = i.checked; livre = false; refiltra(); if (modo === 'forca') calor = 1; enquadra(); sujo(); });
    tp.appendChild(l);
  });
  var fo = $('foco');
  D.ondas.forEach(function (o) { var op = document.createElement('option'); op.value = 'onda:' + o.id; op.textContent = 'Onda ' + o.id + ' — ' + o.titulo.slice(0, 40); fo.appendChild(op); });
  // escolher a onda no seletor foca e seleciona o nó dela: a onda sai destacada, com a cadeia e o painel Selecionado
  fo.addEventListener('change', function () { defineFoco(fo.value); if (fo.value && porId[fo.value]) escolhe(porId[fo.value]); });
  $('lay-fluxo').addEventListener('click', function () { mudaModo('fluxo'); refiltra(); enquadra(); sujo(); });
  $('lay-forca').addEventListener('click', function () { mudaModo('forca'); });
  $('enquadrar').addEventListener('click', function () { livre = false; anim = null; enquadra(); sujo(); });
  $('isolar').addEventListener('click', function () { isolar = !isolar; defineIsolamento(); });
  // Esc: isolado, sai do isolamento e mantém a seleção; senão, limpa a seleção
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || /^(INPUT|SELECT|TEXTAREA)$/.test((document.activeElement || {}).tagName || '')) return;
    if (!$('aba-grafo').classList.contains('ativa')) return;
    esconderDica();
    if (isolar) { isolar = false; defineIsolamento(); }
    else if (sel) escolhe(null);
  });
  if (D.ativa && porId['onda:' + D.ativa]) { fo.value = 'onda:' + D.ativa; defineFoco(fo.value); escolhe(porId[fo.value]); }   // abre focado na onda em execução
  $('busca').addEventListener('input', function (e) {
    filtro = e.target.value; var ul = $('achados'); ul.textContent = '';
    if (filtro.length >= 2) {
      var q = filtro.toLowerCase(), k = 0;
      for (var i = 0; i < N.length && k < 12; i++) {
        var n = N[i];
        if ((n.id + ' ' + n.rotulo + ' ' + n.detalhe).toLowerCase().indexOf(q) >= 0) {
          k++; var li = document.createElement('li'), b = document.createElement('button');
          b.type = 'button'; b.textContent = n.rotulo.slice(0, 44) + ' · ' + NOME[n.tipo]; b.setAttribute('data-no', n.id);
          (function (nn) { b.addEventListener('click', function () { irPara(nn); }); })(n);
          li.appendChild(b); ul.appendChild(li);
        }
      }
    }
    sujo();
  });
  $('nlac').textContent = G.lacunas.length;
  var lc = $('lacunas'), gl = {}, gord = [];      // a mesma mensagem em N nós vira "N× mensagem" que abre a lista
  G.lacunas.forEach(function (l) { var k = l[2] + '|' + l[1]; if (!gl[k]) { gl[k] = {msg: l[1], aviso: l[2] === 'aviso', nos: []}; gord.push(k); } gl[k].nos.push(porId[l[0]]); });
  gord.sort(function (a, b) { return (gl[a].aviso - gl[b].aviso) || (gl[b].nos.length - gl[a].nos.length); });
  gord.forEach(function (k) {
    var g = gl[k], cls = g.aviso ? 'avi' : 'lac';
    function item(n, txt) {
      var d = document.createElement('div'); d.className = cls; d.textContent = txt;
      if (n) d.setAttribute('data-no', n.id);
      d.addEventListener('click', function () { if (n) irPara(n); }); return d;
    }
    if (g.nos.length === 1) { lc.appendChild(item(g.nos[0], (g.nos[0] ? g.nos[0].rotulo + ': ' : '') + g.msg)); return; }
    var det = document.createElement('details'), sum = document.createElement('summary');
    sum.className = cls; sum.textContent = g.nos.length + '× ' + g.msg; det.appendChild(sum);
    g.nos.forEach(function (n) { if (n) det.appendChild(item(n, n.rotulo)); });
    lc.appendChild(det);
  });
  cv.addEventListener('pointerdown', function (e) {
    cv.setPointerCapture(e.pointerId); cv.classList.add('pega'); esconderDica(); anim = null;
    arrasta = acha(e.offsetX, e.offsetY); ultimo = [e.offsetX, e.offsetY]; moveu = false;
  });
  cv.addEventListener('dblclick', function (e) {           // duplo clique no nó: isola a cadeia dele (ou desisola)
    var n = acha(e.offsetX, e.offsetY); if (!n) return;
    if (sel !== n) escolhe(n);
    isolar = !isolar; defineIsolamento();
  });
  cv.addEventListener('pointerleave', function () { if (quente) { esconderDica(); sujo(); } });
  cv.addEventListener('pointerup', function (e) {
    cv.classList.remove('pega');
    if (!moveu) escolhe(acha(e.offsetX, e.offsetY));
    arrasta = null; ultimo = null;
  });
  cv.addEventListener('pointermove', function (e) {
    if (ultimo) {
      var dx = e.offsetX - ultimo[0], dy = e.offsetY - ultimo[1];
      if (Math.abs(dx) + Math.abs(dy) > 3) moveu = true;
      if (moveu) {
        livre = true;
        if (arrasta) { var m = mundo(e.offsetX, e.offsetY); arrasta.x = m[0]; arrasta.y = m[1]; if (modo === 'forca') calor = Math.max(calor, 0.5); montaGrade(); }
        else { ox += dx * dpr(); oy += dy * dpr(); }
        ultimo = [e.offsetX, e.offsetY]; sujo();
      }
    } else {
      var n = acha(e.offsetX, e.offsetY);
      if (n !== quente) { quente = n; if (n) mostraDica(n, [e.clientX, e.clientY]); else $('dica').hidden = true; sujo(); }
      else if (n) mostraDica(n, [e.clientX, e.clientY]);
    }
  });
  cv.addEventListener('wheel', function (e) {
    e.preventDefault(); livre = true; esconderDica(); anim = null;
    var f = e.deltaY < 0 ? 1.12 : 0.89, m = mundo(e.offsetX, e.offsetY);
    zoom = Math.min(4, Math.max(0.1, zoom * f));
    ox = e.offsetX * dpr() - W / 2 - m[0] * zoom; oy = e.offsetY * dpr() - H / 2 - m[1] * zoom; sujo();
  }, {passive: false});
  window.addEventListener('resize', ajusta);
  ajusta();
}

rota();
})();

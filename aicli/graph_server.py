"""
graph_server.py — `aicli graph` local server
Serves the graph HTML + a /api/sessions endpoint that reads all session
JSON exports and the saved graph links from graph_links.json.
"""
import json
import glob
import threading
import webbrowser
import http.server
import urllib.parse
from pathlib import Path
from datetime import datetime


def _exports_dir() -> Path:
    try:
        from aicli.config import CONFIG_DIR
        cfg_file = CONFIG_DIR / "tui_exports.json"
        if cfg_file.exists():
            cfg = json.loads(cfg_file.read_text())
            p = Path(cfg.get("exports_dir", "")).expanduser()
            if p and str(p) != ".":
                p.mkdir(parents=True, exist_ok=True)
                return p
    except Exception:
        pass
    d = Path.home() / "Music" / "aicli" / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _graph_links_file() -> Path:
    return _exports_dir() / "graph_links.json"


def load_sessions_from_exports() -> list:
    """Read all session JSON files from exports, return node list."""
    d = _exports_dir()
    nodes = []
    seen_ids = set()
    # Prefer __latest.json files, fall back to all non-backup non-sync JSONs
    patterns = [str(d / "*__latest.json"), str(d / "*.json")]
    seen_files = set()
    for pattern in patterns:
        for fpath in sorted(glob.glob(pattern)):
            p = Path(fpath)
            if p.name.startswith("backup-") or p.name.startswith("_sync_"):
                continue
            if p.name == "graph_links.json":
                continue
            if p in seen_files:
                continue
            seen_files.add(p)
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                # Skip pure graph files
                if "nodes" in data and "links" in data and "messages" not in data:
                    continue
                sid = data.get("id", p.stem)
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)
                nodes.append({
                    "id":         sid,
                    "name":       data.get("name", p.stem),
                    "msgs":       len(data.get("messages", [])),
                    "session_id": data.get("id", ""),
                    "exported_at": data.get("exported_at", ""),
                    "summary":    (data.get("summary") or "")[:120],
                })
            except Exception:
                pass
    return nodes


def load_graph_links() -> list:
    f = _graph_links_file()
    try:
        return json.loads(f.read_text()).get("links", [])
    except Exception:
        return []


def save_graph_links(links: list) -> None:
    f = _graph_links_file()
    f.write_text(json.dumps({"links": links, "saved": datetime.now().isoformat()}, indent=2))


# ── HTML (embedded so no external files needed) ───────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>aicli graph</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600&family=Syne:wght@400;700;800&display=swap');
:root{--bg:#1a1b26;--bg-alt:#16213e;--bg-panel:#1e2030;--border:#2a2b3d;--accent:#7aa2f7;--green:#9ece6a;--amber:#e0af68;--red:#f7768e;--text:#c0caf5;--muted:#565f89;}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'JetBrains Mono',monospace;overflow:hidden;height:100vh;display:flex;flex-direction:column;}
header{display:flex;align-items:center;gap:12px;padding:8px 16px;background:#0f1117;border-bottom:1px solid var(--border);flex-shrink:0;}
header h1{font-family:'Syne',sans-serif;font-size:15px;font-weight:800;color:var(--accent);}
header .hint{font-size:11px;color:var(--muted);margin-left:auto;}
header button{background:var(--bg-panel);border:1px solid var(--border);color:var(--text);font-family:'JetBrains Mono',monospace;font-size:11px;padding:4px 10px;cursor:pointer;border-radius:3px;transition:all 0.15s;}
header button:hover{border-color:var(--accent);color:var(--accent);}
header button.active{border-color:var(--green);color:var(--green);}
#canvas{flex:1;position:relative;}
svg{width:100%;height:100%;}
.node circle{stroke-width:2;cursor:pointer;filter:drop-shadow(0 0 5px rgba(122,162,247,0.3));}
.node circle.base{fill:#1e2030;stroke:var(--accent);}
.node circle.selected{stroke:var(--amber);stroke-width:3;}
.node circle.linking{stroke:var(--green);stroke-width:3;animation:pulse 1s infinite;}
.node text{fill:var(--text);font-size:11px;font-family:'JetBrains Mono',monospace;pointer-events:none;text-anchor:middle;}
.node .sub{fill:var(--muted);font-size:9px;}
@keyframes pulse{0%,100%{stroke-opacity:1;}50%{stroke-opacity:0.3;}}
.link{stroke:var(--muted);stroke-opacity:0.45;stroke-width:1.5;fill:none;cursor:pointer;}
.link:hover{stroke:var(--red);stroke-opacity:1;}
.link.hl{stroke:var(--accent);stroke-opacity:0.9;}
#panel{position:absolute;right:0;top:0;bottom:0;width:270px;background:var(--bg-panel);border-left:1px solid var(--border);display:flex;flex-direction:column;transform:translateX(100%);transition:transform 0.2s;z-index:5;}
#panel.open{transform:translateX(0);}
#ph{padding:11px 14px;border-bottom:1px solid var(--border);font-family:'Syne',sans-serif;font-size:13px;font-weight:700;color:var(--accent);display:flex;justify-content:space-between;align-items:center;}
#ph button{background:none;border:none;color:var(--muted);cursor:pointer;font-size:14px;padding:2px 6px;}
#ph button:hover{color:var(--red);}
#pb{padding:12px 14px;flex:1;overflow-y:auto;}
#pb h3{font-size:11px;color:var(--amber);margin-bottom:7px;font-family:'Syne',sans-serif;}
#pb .f{margin-bottom:9px;}
#pb label{font-size:10px;color:var(--muted);display:block;margin-bottom:3px;}
#pb input,#pb textarea{width:100%;background:var(--bg);border:1px solid var(--border);color:var(--text);font-family:'JetBrains Mono',monospace;font-size:11px;padding:5px 7px;border-radius:3px;outline:none;}
#pb input:focus,#pb textarea:focus{border-color:var(--accent);}
#pb textarea{resize:vertical;min-height:50px;}
#pb ul{list-style:none;}
#pb ul li{padding:4px 7px;margin-bottom:3px;background:var(--bg);border:1px solid var(--border);border-radius:3px;font-size:11px;display:flex;justify-content:space-between;align-items:center;}
#pb ul li:hover{border-color:var(--accent);}
.del{color:var(--muted);cursor:pointer;font-size:13px;padding:0 3px;}
.del:hover{color:var(--red);}
.br{display:flex;gap:7px;margin-top:9px;}
.br button{flex:1;padding:6px;font-size:11px;cursor:pointer;font-family:'JetBrains Mono',monospace;border-radius:3px;border:1px solid var(--border);background:var(--bg);color:var(--text);transition:all 0.15s;}
.br button:hover{border-color:var(--accent);color:var(--accent);}
.br button.d:hover{border-color:var(--red);color:var(--red);}
.br button.p{border-color:var(--green);color:var(--green);}
#banner{position:absolute;top:10px;left:50%;transform:translateX(-50%);background:#1a2a10;border:1px solid var(--green);color:var(--green);font-size:12px;padding:6px 16px;border-radius:4px;display:none;z-index:20;}
#banner.on{display:block;}
#toast{position:fixed;bottom:18px;left:50%;transform:translateX(-50%);background:var(--bg-panel);border:1px solid var(--accent);color:var(--text);font-size:12px;padding:7px 16px;border-radius:4px;opacity:0;pointer-events:none;transition:opacity 0.2s;z-index:100;}
#toast.show{opacity:1;}
#stats{position:absolute;bottom:8px;left:12px;font-size:10px;color:var(--muted);pointer-events:none;}
#tag-bar{display:flex;align-items:center;gap:6px;padding:4px 16px;background:#0d0e13;border-bottom:1px solid var(--border);font-size:11px;flex-shrink:0;}
#tag-bar input{background:var(--bg-panel);border:1px solid var(--border);color:var(--text);font-family:'JetBrains Mono',monospace;font-size:11px;padding:3px 8px;border-radius:3px;outline:none;width:160px;}
#tag-bar input:focus{border-color:var(--accent);}
#tag-bar button{background:var(--bg-panel);border:1px solid var(--border);color:var(--text);font-size:11px;padding:3px 9px;cursor:pointer;border-radius:3px;}
#tag-bar button:hover{border-color:var(--accent);color:var(--accent);}
#tag-bar .tag-chip{background:var(--bg-msg);border:1px solid var(--accent);color:var(--accent);font-size:10px;padding:2px 7px;border-radius:10px;cursor:pointer;}
#tag-bar .tag-chip:hover{background:var(--accent);color:var(--bg);}
.node-tag{fill:var(--amber);font-size:9px;}
</style>
</head>
<body>
<header>
  <h1>◆ aicli graph</h1>
  <button onclick="loadFromServer()">↺ Reload sessions</button>
  <button onclick="addManual()">+ Node</button>
  <button id="blm" onclick="toggleLinkMode()">Link mode (L)</button>
  <button onclick="saveLinks()">Save links</button>
  <span class="hint">Drag=move · Click=select · Dbl-click=edit · Hover link=delete · L=link mode · Esc=cancel</span>
</header>
<div id="tag-bar">
  <span style="color:var(--muted)">🏷 Tags:</span>
  <input id="tag-filter-input" placeholder="filter by tag…" onkeydown="if(event.key==='Enter')filterByTag()">
  <button onclick="filterByTag()">Filter</button>
  <button onclick="clearTagFilter()" style="color:var(--muted)">Clear</button>
  <span id="tag-chips" style="display:flex;gap:4px;flex-wrap:wrap;"></span>
  <span id="filter-status" style="color:var(--muted);margin-left:8px;font-size:10px;"></span>
</div>
<div id="canvas">
  <svg id="svg">
    <defs>
      <marker id="arr" markerWidth="7" markerHeight="7" refX="20" refY="3" orient="auto">
        <path d="M0,0 L0,6 L7,3 z" fill="#565f89" opacity="0.7"/>
      </marker>
    </defs>
    <g id="lg"></g><g id="ng"></g>
  </svg>
  <div id="panel">
    <div id="ph"><span id="pt">Node</span><button onclick="closePanel()">✕</button></div>
    <div id="pb"></div>
  </div>
  <div id="banner">⬡ Link mode — click the TARGET node (Esc to cancel)</div>
  <div id="stats"></div>
</div>
<div id="toast"></div>
<script>
let G={nodes:[],links:[]},sim,linkMode=false,linkSrc=null,sel=null;
let W,H,svg,lg,ng;

function uid(){return Date.now().toString(36)+Math.random().toString(36).slice(2,5);}
function toast(m,t=2000){const e=document.getElementById('toast');e.textContent=m;e.classList.add('show');setTimeout(()=>e.classList.remove('show'),t);}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');}

function init(){
  svg=d3.select('#svg'); lg=d3.select('#lg'); ng=d3.select('#ng');
  const box=document.getElementById('canvas');
  W=box.clientWidth; H=box.clientHeight;
  const zoom=d3.zoom().scaleExtent([0.15,5]).on('zoom',e=>{lg.attr('transform',e.transform);ng.attr('transform',e.transform);});
  svg.call(zoom);
  sim=d3.forceSimulation()
    .force('link',d3.forceLink().id(d=>d.id).distance(140))
    .force('charge',d3.forceManyBody().strength(-400))
    .force('center',d3.forceCenter(W/2,H/2))
    .force('collide',d3.forceCollide(45));
  loadFromServer();
}

function loadFromServer(){
  fetch('/api/sessions').then(r=>r.json()).then(data=>{
    const existingIds=new Set(G.nodes.map(n=>n.id));
    let added=0;
    data.nodes.forEach(n=>{
      if(!existingIds.has(n.id)){
        n.x=W/2+(Math.random()-0.5)*400; n.y=H/2+(Math.random()-0.5)*400;
        G.nodes.push(n); added++;
      }
    });
    // Load saved links, replacing string refs with objects
    G.links=data.links.map(l=>({...l}));
    render();
    _refreshTagChips();
    if(_activeTagFilter) filterByTag();
    toast(added>0?`Loaded ${added} session(s)`:`${G.nodes.length} sessions (up to date)`);
  }).catch(e=>toast('Server error: '+e));
}

function render(){
  const link=lg.selectAll('.link').data(G.links,d=>d.id);
  link.exit().remove();
  const le=link.enter().append('line').attr('class','link')
    .attr('marker-end','url(#arr)')
    .on('mouseenter',(e,d)=>lg.selectAll('.link').classed('hl',l=>l.id===d.id))
    .on('mouseleave',()=>lg.selectAll('.link').classed('hl',false))
    .on('click',(e,d)=>{e.stopPropagation();if(confirm('Remove this link?')){removeLink(d);}});
  le.merge(link);

  const node=ng.selectAll('.node').data(G.nodes,d=>d.id);
  node.exit().remove();
  const ne=node.enter().append('g').attr('class','node').attr('id',d=>'n-'+d.id)
    .call(d3.drag().on('start',ds).on('drag',dd).on('end',de))
    .on('click',nc).on('dblclick',ndc);
  ne.append('circle').attr('class','base').attr('r',22);
  ne.append('text').attr('dy',-2);
  ne.append('text').attr('class','sub').attr('dy',12);
  ne.append('text').attr('class','node-tag').attr('dy',24);
  const nm=ne.merge(node);
  nm.select('text:not(.sub):not(.node-tag)').text(d=>(d.name||d.id).slice(0,13));
  nm.select('.sub').text(d=>d.msgs?d.msgs+'msg':'');
  nm.select('.node-tag').text(d=>(d.tags&&d.tags.length)?'#'+d.tags[0]:'');
  nm.select('circle').classed('selected',d=>sel&&d.id===sel.id).classed('linking',d=>linkSrc&&d.id===linkSrc.id);

  sim.nodes(G.nodes).on('tick',()=>{
    lg.selectAll('.link')
      .attr('x1',d=>d.source.x||0).attr('y1',d=>d.source.y||0)
      .attr('x2',d=>d.target.x||0).attr('y2',d=>d.target.y||0);
    nm.attr('transform',d=>`translate(${d.x||0},${d.y||0})`);
  });
  sim.force('link').links(G.links);
  sim.alpha(0.3).restart();
  document.getElementById('stats').textContent=`${G.nodes.length} nodes · ${G.links.length} links`;
}

function ds(e,d){if(!e.active)sim.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y;}
function dd(e,d){d.fx=e.x;d.fy=e.y;}
function de(e,d){if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}

function nc(e,d){
  e.stopPropagation();
  if(linkMode){
    if(!linkSrc){linkSrc=d;render();return;}
    if(linkSrc.id!==d.id){addLink(linkSrc,d);}
    linkSrc=null;toggleLinkMode();return;
  }
  sel=d;openPanel(d);render();
}
function ndc(e,d){e.stopPropagation();sel=d;openPanel(d);render();}

function openPanel(n){
  document.getElementById('panel').classList.add('open');
  document.getElementById('pt').textContent=n.name||n.id;
  const conns=G.links.filter(l=>(l.source.id||l.source)===n.id||(l.target.id||l.target)===n.id);
  document.getElementById('pb').innerHTML=`
    <h3>Session info</h3>
    <div class="f"><label>Name</label><input id="pn" value="${esc(n.name||'')}"></div>
    <div class="f"><label>Notes</label><textarea id="po" rows="2">${esc(n.notes||'')}</textarea></div>
    <div class="f"><label>Tags (comma separated)</label><input id="pt-tags" value="${esc((n.tags||[]).join(', '))}"></div>
    ${n.summary?`<div class="f"><label>Summary</label><textarea rows="2" readonly style="opacity:.6">${esc(n.summary)}</textarea></div>`:''}
    <div class="f"><label>Messages</label><input value="${n.msgs||0}" readonly style="opacity:.5"></div>
    <h3 style="margin-top:12px">Links (${conns.length})</h3>
    <ul id="pl"></ul>
    <div class="br">
      <button class="p" onclick="savePanelEdits('${n.id}')">Save</button>
      <button onclick="startLinkFrom('${n.id}')">+ Link</button>
      <button class="d" onclick="removeNode('${n.id}')">Delete</button>
    </div>`;
  const ul=document.getElementById('pl');
  conns.forEach(l=>{
    const oid=(l.source.id||l.source)===n.id?(l.target.id||l.target):(l.source.id||l.source);
    const o=G.nodes.find(x=>x.id===oid);
    const li=document.createElement('li');
    li.innerHTML=`<span>${esc(o?.name||oid)}</span><span class="del" onclick="removeLink({id:'${l.id}'})">✕</span>`;
    ul.appendChild(li);
  });
}
function closePanel(){document.getElementById('panel').classList.remove('open');sel=null;render();}
function savePanelEdits(id){
  const n=G.nodes.find(x=>x.id===id); if(!n)return;
  n.name=document.getElementById('pn').value.trim()||n.name;
  n.notes=document.getElementById('po').value;
  // Save tags — split comma/space separated
  const rawTags = (document.getElementById('pt-tags') ? document.getElementById('pt-tags').value : '');
  n.tags = rawTags.split(/[,\s]+/).map(t=>t.trim()).filter(Boolean);
  document.getElementById('pt').textContent=n.name;
  render();saveLinks();toast('Saved');
  _refreshTagChips();
}

function _allTags(){
  const s=new Set();
  G.nodes.forEach(n=>(n.tags||[]).forEach(t=>s.add(t)));
  return [...s].sort();
}

function _refreshTagChips(){
  const chips=document.getElementById('tag-chips');
  chips.innerHTML='';
  _allTags().forEach(tag=>{
    const c=document.createElement('span');
    c.className='tag-chip';c.textContent=tag;
    c.onclick=()=>{document.getElementById('tag-filter-input').value=tag;filterByTag();};
    chips.appendChild(c);
  });
}

let _activeTagFilter='';
function filterByTag(){
  const tag=document.getElementById('tag-filter-input').value.trim().toLowerCase();
  _activeTagFilter=tag;
  const status=document.getElementById('filter-status');
  if(!tag){clearTagFilter();return;}
  G.nodes.forEach(n=>{
    const el=document.getElementById('n-'+n.id);
    if(el){
      const match=(n.tags||[]).map(t=>t.toLowerCase()).includes(tag);
      el.style.opacity=match?'1':'0.18';
    }
  });
  const matches=G.nodes.filter(n=>(n.tags||[]).map(t=>t.toLowerCase()).includes(tag)).length;
  status.textContent=`${matches} node${matches!==1?'s':''} tagged "${tag}"`;
}

function clearTagFilter(){
  _activeTagFilter='';
  document.getElementById('tag-filter-input').value='';
  document.getElementById('filter-status').textContent='';
  G.nodes.forEach(n=>{const el=document.getElementById('n-'+n.id);if(el)el.style.opacity='1';});
}

function toggleLinkMode(){
  linkMode=!linkMode;
  document.getElementById('blm').classList.toggle('active',linkMode);
  document.getElementById('banner').classList.toggle('on',linkMode);
  if(!linkMode){linkSrc=null;render();}
}
function startLinkFrom(id){linkSrc=G.nodes.find(n=>n.id===id);toggleLinkMode();closePanel();}

function addLink(s,t){
  if(G.links.find(l=>(l.source.id||l.source)===s.id&&(l.target.id||l.target)===t.id)){toast('Already linked');return;}
  G.links.push({id:uid(),source:s.id,target:t.id});
  render();saveLinks();toast(`Linked: ${s.name||s.id} → ${t.name||t.id}`);
}
function removeLink(d){G.links=G.links.filter(l=>l.id!==d.id);render();saveLinks();toast('Link removed');}
function removeNode(id){
  G.nodes=G.nodes.filter(n=>n.id!==id);
  G.links=G.links.filter(l=>(l.source.id||l.source)!==id&&(l.target.id||l.target)!==id);
  closePanel();render();saveLinks();
}
function addManual(){
  const name=prompt('Node name:'); if(!name)return;
  G.nodes.push({id:uid(),name,x:W/2+(Math.random()-.5)*300,y:H/2+(Math.random()-.5)*300});
  render();saveLinks();
}
function saveLinks(){
  const links=G.links.map(l=>({id:l.id,source:l.source.id||l.source,target:l.target.id||l.target}));
  const names={};
  G.nodes.forEach(n=>{names[n.id]={name:n.name,notes:n.notes||''};});
  fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({links,names})})
    .then(r=>r.json()).then(()=>{}).catch(()=>{});
}

document.getElementById('svg').addEventListener('click',closePanel);
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){if(linkMode){toggleLinkMode();}else{closePanel();}}
  if(e.key==='l'&&document.activeElement.tagName!=='INPUT'&&document.activeElement.tagName!=='TEXTAREA'){toggleLinkMode();}
  if(e.key==='r'&&document.activeElement.tagName!=='INPUT'){loadFromServer();}
});
window.addEventListener('load',init);
window.addEventListener('resize',()=>{
  W=document.getElementById('canvas').clientWidth;
  H=document.getElementById('canvas').clientHeight;
  sim.force('center',d3.forceCenter(W/2,H/2)).alpha(0.1).restart();
});
</script>
</body>
</html>"""


# ── HTTP Server ───────────────────────────────────────────────────────────────

class GraphHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass  # silence default logging

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/" or path == "/index.html":
            self._respond(200, "text/html", HTML.encode())
        elif path == "/api/sessions":
            nodes = load_sessions_from_exports()
            links = load_graph_links()
            # Merge any saved node metadata (names/notes)
            meta_file = _exports_dir() / "graph_links.json"
            names = {}
            try:
                names = json.loads(meta_file.read_text()).get("names", {})
            except Exception:
                pass
            for n in nodes:
                if n["id"] in names:
                    n["name"]  = names[n["id"]].get("name", n["name"])
                    n["notes"] = names[n["id"]].get("notes", "")
                    n["tags"]  = names[n["id"]].get("tags", [])
                else:
                    n["tags"] = []
            body = json.dumps({"nodes": nodes, "links": links}).encode()
            self._respond(200, "application/json", body)
        else:
            self._respond(404, "text/plain", b"Not found")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/save":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length))
            links = body.get("links", [])
            names = body.get("names", {})
            # names dict now supports: {id: {name, notes, tags: []}}
            # tags are preserved as-is — client sends full node metadata
            f = _graph_links_file()
            existing = {}
            try:
                existing = json.loads(f.read_text())
            except Exception:
                pass
            existing["links"] = links
            existing["names"] = names
            existing["saved"] = datetime.now().isoformat()
            f.write_text(json.dumps(existing, indent=2))
            self._respond(200, "application/json", b'{"ok":true}')
        elif path == "/api/tags":
            # POST /api/tags — filter nodes by tag
            # Body: {"tag": "mytag"} → returns {nodes: [...]} matching tag
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            tag = body.get("tag", "").strip().lower()
            nodes = load_sessions_from_exports()
            meta_file = _exports_dir() / "graph_links.json"
            names = {}
            try:
                names = json.loads(meta_file.read_text()).get("names", {})
            except Exception:
                pass
            for n in nodes:
                if n["id"] in names:
                    n["name"]  = names[n["id"]].get("name", n["name"])
                    n["notes"] = names[n["id"]].get("notes", "")
                    n["tags"]  = names[n["id"]].get("tags", [])
                else:
                    n["tags"] = []
            if tag:
                nodes = [n for n in nodes if tag in [t.lower() for t in n.get("tags", [])]]
            result = json.dumps({"nodes": nodes, "tag": tag}).encode()
            self._respond(200, "application/json", result)
        else:
            self._respond(404, "text/plain", b"Not found")

    def _respond(self, code, ct, body):
        self.send_response(code)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


def _kill_existing(port: int) -> bool:
    """Kill any process already listening on port. Returns True if something was killed."""
    import subprocess, signal
    try:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        if not pids:
            return False
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
        import time; time.sleep(0.4)
        return True
    except FileNotFoundError:
        # lsof not available — try fuser
        try:
            subprocess.run(["fuser", "-k", f"{port}/tcp"],
                           capture_output=True)
            return True
        except FileNotFoundError:
            return False


class ReusableTCPServer(http.server.HTTPServer):
    """HTTPServer with allow_reuse_address=True so the port recycles immediately
    after Ctrl+C without waiting for TIME_WAIT to expire."""
    allow_reuse_address = True


def run_graph_server(port: int = 7337, open_browser: bool = True):
    exports = _exports_dir()

    # Kill any existing server on this port first
    if _kill_existing(port):
        print(f"\033[90m  ◆ Stopped existing server on :{port}\033[0m")

    print(f"\033[1m◆ aicli graph\033[0m  →  http://localhost:{port}")
    print(f"  Sessions from: {exports}")
    print(f"  Press Ctrl+C to stop\n")

    server = ReusableTCPServer(("localhost", port), GraphHandler)

    if open_browser:
        def _open():
            import time; time.sleep(0.5)
            webbrowser.open(f"http://localhost:{port}")
        threading.Thread(target=_open, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\033[90m  Graph server stopped.\033[0m")
    finally:
        server.server_close()

const $ = selector => document.querySelector(selector);
const state = { catalog: null, category: 'python', topic: '변수', generateCSV:false, counts: {쉬움:1, 보통:2, 어려움:1}, busy:false, job:null, timer:null, rendered:0 };
const el = (tag, text, cls) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = text; if(cls) node.className=cls; return node; };
function message(text){ $('#form-error').textContent=text; $('#form-error').hidden=!text; }
function total(){ return Object.values(state.counts).reduce((a,b)=>a+b,0); }
function update(){
  $('#total').textContent=total();
  $('#generate').disabled=state.busy || total()<1 || total()>10 || !state.catalog?.ready;
  if(total()>10) message('총 10문항까지 생성할 수 있습니다.'); else if(!state.busy) message('');
  if(state.category==='pythonlib'){
    $('#data-note').textContent=state.generateCSV?'100행의 가상 CSV를 함께 생성하고 해당 데이터를 활용하는 문제를 출제합니다.':'CSV 없이, 필요한 입력 데이터를 문제에 직접 제공하는 코딩 문제를 생성합니다.';
  }else{
    const topics=state.catalog?.categories.python.topics||[];
    const index=topics.indexOf(state.topic);
    const later=index>=0?topics.slice(index+1):[];
    $('#data-note').textContent=state.topic+'까지 배운 학생 기준으로 출제합니다.'+(later.length?' 이후 단원('+later.join(' · ')+')은 제외합니다.':' 이전 단원의 내용을 함께 사용할 수 있습니다.');
  }
}
function choice(text, selected, click){ const button=el('button',text,'choice'+(selected?' selected':'')); button.type='button'; button.setAttribute('aria-pressed',String(selected)); button.disabled=state.busy; button.onclick=click; return button; }
function renderChoices(){ const categories=$('#categories'); categories.replaceChildren(); for(const [key,item] of Object.entries(state.catalog.categories)){categories.append(choice(item.label,state.category===key,()=>{state.category=key;state.topic=item.topics[0];renderChoices();update();}));} const topics=$('#topics');topics.replaceChildren();for(const topic of state.catalog.categories[state.category].topics){topics.append(choice(topic,state.topic===topic,()=>{state.topic=topic;renderChoices();update();}));} $('#csv-settings').hidden=state.category!=='pythonlib'; const csv=$('#csv-choices');csv.replaceChildren();for(const [value,label] of [[false,'생성 안 함'],[true,'가상 CSV 생성']]){csv.append(choice(label,state.generateCSV===value,()=>{state.generateCSV=value;renderChoices();update();}));} }
function renderCounts(){ const target=$('#counts'); for(const [i,level] of ['쉬움','보통','어려움'].entries()){const row=el('div',undefined,'level-row');const label=el('label',undefined,'level-name');label.htmlFor='count-'+i;label.append(el('span','', 'dot '+['','medium','hard'][i]),document.createTextNode(level));const select=el('select');select.id='count-'+i;select.setAttribute('aria-label',level+' 문항 수');for(let n=0;n<=10;n++){const option=el('option',n+'개');option.value=n;select.append(option);}select.value=state.counts[level];select.onchange=()=>{state.counts[level]=Number(select.value);update();};row.append(label,select);target.append(row);} }
function inlineMarkdown(node,text){
  // Build DOM nodes rather than inserting model-generated HTML.
  const pattern=/(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^\s)]+\))/g;
  let position=0;
  for(const match of text.matchAll(pattern)){
    node.append(document.createTextNode(text.slice(position,match.index)));
    const token=match[0];
    if(token.startsWith('`')) node.append(el('code',token.slice(1,-1)));
    else if(token.startsWith('**')) node.append(el('strong',token.slice(2,-2)));
    else {
      const link=token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      let url;try{url=new URL(link[2],location.href);}catch{url=null;}
      if(url&&['http:','https:'].includes(url.protocol)){
        const a=el('a',link[1]);a.href=url.href;a.rel='noopener noreferrer';a.target='_blank';node.append(a);
      }else node.append(document.createTextNode(link[1]));
    }
    position=match.index+token.length;
  }
  node.append(document.createTextNode(text.slice(position)));
}
function markdown(text){
  const result=el('div',undefined,'text-block');
  const lines=String(text||'').split('\n');
  let list=null;
  for(let i=0;i<lines.length;i++){
    const line=lines[i];
    const fence=line.match(/^\s*(`{3,}|~{3,})(.*)$/);
    if(fence){
      list=null;const content=[];const marker=fence[1][0];const length=fence[1].length;
      while(++i<lines.length){
        if(new RegExp('^\\s*'+marker+'{'+length+',}\\s*$').test(lines[i]))break;
        content.push(lines[i]);
      }
      const pre=el('pre');pre.append(el('code',content.join('\n')));result.append(pre);continue;
    }
    if(!line.trim()){list=null;continue;}
    if(/^\s*(?:---+|\*\*\*+)\s*$/.test(line)){result.append(el('hr'));list=null;continue;}
    const heading=line.match(/^(#{1,6})\s+(.*)/);
    if(heading){const h=el('h'+heading[1].length);inlineMarkdown(h,heading[2]);result.append(h);list=null;continue;}
    const item=line.match(/^\s*(?:([-*+])|(\d+)\.)\s+(.*)/);
    if(item){
      const tag=item[2]?'ol':'ul';
      if(!list||list.tagName.toLowerCase()!==tag){list=el(tag);if(item[2])list.start=Number(item[2]);result.append(list);}
      const li=el('li');inlineMarkdown(li,item[3]);list.append(li);continue;
    }
    list=null;
    const node=el(line.startsWith('> ')?'blockquote':'p');
    inlineMarkdown(node,line.startsWith('> ')?line.slice(2):line);result.append(node);
  }
  return result;
}
function highlightedPython(text){
  const code=el('code');
  const pattern=/("""[\s\S]*?"""|'''[\s\S]*?'''|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|#[^\n]*|\b(?:False|None|True|and|as|assert|async|await|break|class|continue|def|del|elif|else|except|finally|for|from|global|if|import|in|is|lambda|nonlocal|not|or|pass|raise|return|try|while|with|yield)\b|\b\d+(?:\.\d+)?\b)/g;
  let position=0;
  for(const match of String(text).matchAll(pattern)){
    code.append(document.createTextNode(text.slice(position,match.index)));
    const token=match[0];const type=token.startsWith('#')?'comment':/^['"]/.test(token)?'string':/^\d/.test(token)?'number':'keyword';
    code.append(el('span',token,'syntax-'+type));position=match.index+token.length;
  }
  code.append(document.createTextNode(text.slice(position)));return code;
}
function notebookCell(type,content,source=content){
  const cell=el('section',undefined,'notebook-cell notebook-'+type);
  cell.setAttribute('aria-label',type==='code'?'Python 코드 셀':'마크다운 셀');
  const toolbar=el('div',undefined,'cell-toolbar');
  toolbar.append(el('span',type==='code'?'[ ]':'¶','cell-type-icon'),el('span',type==='code'?'코드 셀':'마크다운 셀'),el('span',type==='code'?'Python':'Markdown','cell-language'));
  {
    const label=type==='code'?'복사':'원문 복사';
    const copy=el('button',label,'cell-copy');copy.type='button';copy.setAttribute('aria-label',type==='code'?'정답 코드 복사':'마크다운 원문 복사');
    copy.onclick=async()=>{try{await navigator.clipboard.writeText(source);copy.textContent='복사됨';}catch{copy.textContent='복사 실패';}setTimeout(()=>copy.textContent=label,1500);};
    toolbar.append(copy);
  }
  cell.append(toolbar);
  if(type==='code'){
    const editor=el('div',undefined,'cell-editor');
    const gutter=el('pre',Array.from({length:String(content).split('\n').length},(_,i)=>i+1).join('\n'),'cell-line-numbers');
    gutter.setAttribute('aria-hidden','true');
    const pre=el('pre',undefined,'cell-source');pre.tabIndex=0;pre.setAttribute('aria-label','정답 코드 내용');pre.append(highlightedPython(content));
    editor.append(gutter,pre);cell.append(editor);
  }else{const body=el('div',undefined,'cell-markdown-body');body.append(content);cell.append(body);}
  return cell;
}
function details(label, content, open=false){const node=el('details');node.open=open;node.append(el('summary',label));const body=el('div');body.append(content);node.append(body);return node;}
function downloadURL(id,file){return '/api/jobs/'+id+'/download?file='+encodeURIComponent(file);}
function outputMarkdown(text){
  const runs=String(text).match(/`+/g)||[];
  const fence='`'.repeat(Math.max(3,...runs.map(run=>run.length+1)));
  return fence+'text\n'+text+'\n'+fence;
}
function referenceMarkdown(q){
  return '## 참고 해설\n\n'+q.explanation+'\n\n## 예상 출력 · 실행 미검증\n\n'+outputMarkdown(q.expected_output);
}
function questionCard(q,id){
  const card=el('article',undefined,'question');
  const title=el('div',undefined,'question-title');
  title.append(el('span',String(q.number).padStart(2,'0'),'question-number'));
  const heading=el('div');
  heading.append(el('h3',q.title),el('div',(q.concepts||[]).join(' · '),'question-meta'));
  title.append(heading,el('span',q.difficulty,'difficulty-badge'));card.append(title);
  const body=el('div',undefined,'question-body');
  const problem=markdown(q.problem_markdown);
  if(q.csv_file){const a=el('a','첨부 CSV 다운로드 ↓','secondary');a.href=downloadURL(id,q.csv_file);problem.append(a);}
  body.append(notebookCell('markdown',problem,q.problem_markdown),notebookCell('code',q.answer_code));
  const explanationSource=referenceMarkdown(q);
  body.append(details('참고 해설 및 예상 출력',notebookCell('markdown',markdown(explanationSource),explanationSource)));
  const guideSource=q.grading_guidelines_markdown||'이전에 생성된 문항에는 채점 가이드라인이 없습니다. 새로 생성한 문항부터 제공됩니다.';
  body.append(details('채점 기준 가이드라인 · 웹 전용',notebookCell('markdown',markdown(guideSource),guideSource)));
  body.append(el('div','Python 문법 검사 완료 · 정답 실행 및 예상 출력은 미검증','check-note'));
  card.append(body);return card;
}
function setBusy(value){state.busy=value;$('#generate').textContent=value?'문제 생성 중…':'문제 생성하기 ↗';document.querySelectorAll('#counts select').forEach(s=>s.disabled=value);renderChoices();update();}
async function jsonRequest(url,options){const response=await fetch(url,options);let data;try{data=await response.json();}catch{throw new Error('서버 응답을 읽을 수 없습니다. 서버가 실행 중인지 확인하세요.');}if(!response.ok)throw new Error(data.error||'요청에 실패했습니다.');return data;}
function showJob(job){const count=job.questions.length;$('#result-count').textContent=count;$('#progress-label').textContent=job.status==='running'?'문제를 생성하고 있습니다':job.status==='completed'?'생성 완료':'생성 결과 확인';const target=Object.values(job.selection.counts).reduce((a,b)=>a+b,0);$('#progress-count').textContent=count+' / '+target+'문항';$('#progress-bar').style.width=(job.status==='running'?Math.max(3,count/target*100):100)+'%';$('#progress-message').textContent=job.message;$('#empty').hidden=true;for(let i=state.rendered;i<count;i++)$('#question-list').append(questionCard(job.questions[i],job.id));state.rendered=count;$('#result-note').hidden=count===0;if(job.status!=='running'){setBusy(false);if(job.files?.instructor&&job.files?.student){$('#downloads').hidden=false;$('#instructor-download').href=downloadURL(job.id,job.files.instructor);$('#student-download').href=downloadURL(job.id,job.files.student);$('#zip-download').href='/api/jobs/'+job.id+'/archive';}if(job.status==='failed'||job.status==='partial'){message([job.message,...job.errors.map(e=>'문항 '+e.question+': '+(e.detail||e.error_type))].join('\n'));}localStorage.removeItem('activeQuestionJob');}}
async function poll(){try{const job=await jsonRequest('/api/jobs/'+state.job);showJob(job);if(job.status==='running')state.timer=setTimeout(poll,1200);}catch(error){setBusy(false);message(error.message+' 새로고침하면 진행 상황을 다시 확인합니다.');}}
$('#generate-form').onsubmit=async event=>{event.preventDefault();if(state.busy||total()<1||total()>10)return;message('');setBusy(true);try{const data=await jsonRequest('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({category:state.category,topic:state.topic,generate_csv:state.category==='pythonlib'&&state.generateCSV,counts:state.counts})});state.job=data.id;state.rendered=0;$('#question-list').replaceChildren();$('#downloads').hidden=true;$('#result-count').textContent='0';$('#result-note').hidden=true;$('#progress').hidden=false;$('#progress-label').textContent='생성 준비';$('#progress-message').textContent='선택한 조건으로 출제를 시작합니다.';$('#progress-bar').style.width='3%';$('#empty').hidden=true;localStorage.setItem('activeQuestionJob',state.job);await poll();}catch(error){setBusy(false);message(error.message);}};
async function init(){
  renderCounts();
  try {
    state.catalog=await jsonRequest('/api/catalog');
    $('#connection').textContent=state.catalog.demo?'데모 모드 · 고정 예제':state.catalog.ready?'API 연결 준비됨':'API 키 설정 필요';
    $('#connection').classList.toggle('warn',state.catalog.demo||!state.catalog.ready);
    renderChoices();update();
    if(!state.catalog.ready) message('서버 환경변수 또는 .env에 API 키를 설정한 뒤 서버를 다시 실행하세요.');
  } catch(error) {
    message(error.message);$('#generate').disabled=true;return;
  }
  const saved=localStorage.getItem('activeQuestionJob');
  if(!saved) return;
  try {
    const job=await jsonRequest('/api/jobs/'+saved);
    state.category=job.selection.category;state.topic=job.selection.topic;state.counts=job.selection.counts;state.job=saved;
    state.generateCSV=job.selection.generate_csv ?? (job.selection.topic==='pandas');
    ['쉬움','보통','어려움'].forEach((level,i)=>$('#count-'+i).value=state.counts[level]);
    setBusy(job.status==='running');$('#progress').hidden=false;await poll();
  } catch(error) {
    localStorage.removeItem('activeQuestionJob');setBusy(false);
    message('이전 생성 기록을 불러올 수 없습니다. 서버가 재시작되었다면 새로 생성해주세요.');
  }
}
init();

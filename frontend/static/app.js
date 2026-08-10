const $=id=>document.getElementById(id);
const money=value=>value==null?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',notation:'compact',maximumFractionDigits:1}).format(Number(value));
const number=value=>value==null?'—':new Intl.NumberFormat('en-US',{notation:'compact',maximumFractionDigits:1}).format(Number(value));
const percent=value=>value==null?'—':new Intl.NumberFormat('en-US',{style:'percent',maximumFractionDigits:1,signDisplay:'exceptZero'}).format(Number(value));
const escapeHtml=value=>{const node=document.createElement('div');node.textContent=String(value??'');return node.innerHTML};

function renderMarkdown(value){
  const inline=text=>escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/`([^`]+)`/g,'<code>$1</code>');
  const lines=String(value??'').replace(/\r\n?/g,'\n').split('\n'),html=[];
  const isPipeRow=line=>/^\s*\|.*\|\s*$/.test(line);
  const cells=line=>line.trim().replace(/^\||\|$/g,'').split('|').map(cell=>cell.trim());
  const isSeparator=row=>row.length>0&&row.every(cell=>/^:?-{3,}:?$/.test(cell));
  const alignment=cell=>cell.startsWith(':')&&cell.endsWith(':')?'align-center':cell.endsWith(':')?'align-right':cell.startsWith(':')?'align-left':'';
  let list=null;
  const closeList=()=>{if(list){html.push(`</${list}>`);list=null}};
  for(let index=0;index<lines.length;index++){
    const line=lines[index];
    if(isPipeRow(line)){
      const rows=[];
      let cursor=index;
      while(cursor<lines.length){
        if(isPipeRow(lines[cursor])){rows.push(lines[cursor]);cursor++;continue}
        if(!lines[cursor].trim()){
          let next=cursor;
          while(next<lines.length&&!lines[next].trim())next++;
          if(next<lines.length&&isPipeRow(lines[next])){cursor=next;continue}
        }
        break;
      }
      const parsed=rows.map(cells);
      if(parsed.length>=2&&isSeparator(parsed[1])){
        closeList();
        const aligns=parsed[1].map(alignment),width=parsed[0].length;
        const rowHtml=(row,tag)=>`<tr>${Array.from({length:width},(_,column)=>`<${tag} class="${aligns[column]||''}">${inline(row[column]||'')}</${tag}>`).join('')}</tr>`;
        html.push(`<div class="table-wrap"><table><thead>${rowHtml(parsed[0],'th')}</thead><tbody>${parsed.slice(2).map(row=>rowHtml(row,'td')).join('')}</tbody></table></div>`);
        index=cursor-1;
        continue;
      }
    }
    const heading=line.match(/^#{1,6}\s+(.+)$/);
    const ordered=line.match(/^\d+\.\s+(.+)$/);
    const unordered=line.match(/^[-*]\s+(.+)$/);
    if(heading){closeList();html.push(`<h4>${inline(heading[1])}</h4>`);continue}
    if(/^\s*---+\s*$/.test(line)){closeList();html.push('<hr>');continue}
    if(ordered||unordered){
      const type=ordered?'ol':'ul';
      if(list!==type){closeList();html.push(`<${type}>`);list=type}
      html.push(`<li>${inline((ordered||unordered)[1])}</li>`);continue
    }
    closeList();
    if(line.trim())html.push(`<p>${inline(line)}</p>`);
  }
  closeList();
  return html.join('');
}

async function jsonFetch(url,options){const response=await fetch(url,options);const data=await response.json();if(!response.ok||data.status==='error')throw new Error(data.message||'Request failed');return data}

function moverHtml(row){const value=Number(row.contribution);return `<div class="mover"><strong>${escapeHtml(row.display_product_name||row.product_key)}</strong><span class="${value>=0?'up':'down'}">${money(value)}</span><small>${escapeHtml(row.product_key)}</small></div>`}

let pendingApprovalToken=null;
function approvalArguments(value){
  try{return JSON.stringify(typeof value==='string'?JSON.parse(value):value,null,2)}catch{return String(value??'{}')}
}
function renderAgentResult(data){
  const conversation=$('conversation');
  if(data.approval_required){
    pendingApprovalToken=data.approval_token;
    const writes=(data.proposed_writes||[]).map(write=>`<div class="approval-tool"><strong>${escapeHtml(write.name)}</strong><pre>${escapeHtml(approvalArguments(write.arguments))}</pre></div>`).join('');
    conversation.insertAdjacentHTML('beforeend',`<div class="agent-message approval-message"><div class="avatar">AI</div><div class="agent-response"><strong>Write approval required</strong><p>Review the proposed governed operation before it changes Lakebase.</p>${writes}<div class="approval-controls"><button type="button" class="secondary" data-agent-approval="false">Cancel</button><button type="button" class="primary" data-agent-approval="true">Approve and continue</button></div></div></div>`);
    return;
  }
  pendingApprovalToken=null;
  conversation.insertAdjacentHTML('beforeend',`<div class="agent-message"><div class="avatar">AI</div><div class="agent-response"><strong>Agent conclusion</strong>${renderMarkdown(data.answer)}</div></div>`);
}

async function loadDashboard(){
  $('refresh').disabled=true;
  try{const query=new URLSearchParams({year:$('year').value});if($('quarter').value)query.set('quarter',$('quarter').value);if($('state').value)query.set('state',$('state').value);
    const data=await jsonFetch(`/api/dashboard?${query}`),k=data.kpis||{},y=data.yoy||{};
    $('totalReimbursement').textContent=money(k.total_reimbursement);$('prescriptions').textContent=number(k.prescriptions);$('units').textContent=number(k.units_reimbursed);$('rate').textContent=money(k.reimbursement_per_prescription);$('yoy').textContent=percent(y.reimbursement_change_percent);$('yoyAmount').textContent=`${money(y.reimbursement_change)} vs prior year`;
    $('positiveMovers').innerHTML=data.positive_movers.length?data.positive_movers.map(moverHtml).join(''):'<p class="empty">No positive YoY contributors in this scope.</p>';
    $('negativeMovers').innerHTML=data.negative_movers.length?data.negative_movers.map(moverHtml).join(''):'<p class="empty">No negative YoY contributors in this scope.</p>';
  }catch(error){$('positiveMovers').innerHTML=`<p class="empty">${escapeHtml(error.message)}</p>`}finally{$('refresh').disabled=false}}

async function ask(event){event.preventDefault();const input=$('question'),message=input.value.trim();if(!message)return;const conversation=$('conversation');conversation.insertAdjacentHTML('beforeend',`<div class="user-message"><div>${escapeHtml(message)}</div></div><div id="thinking" class="agent-message loading"><div class="avatar">AI</div><div>Investigating governed data and evidence…</div></div>`);conversation.scrollTop=conversation.scrollHeight;input.value='';
  try{const data=await jsonFetch('/api/agent',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message})});$('thinking').remove();renderAgentResult(data);await loadWorkspace()}catch(error){$('thinking').remove();conversation.insertAdjacentHTML('beforeend',`<div class="agent-message"><div class="avatar">!</div><div>${escapeHtml(error.message)}</div></div>`)}conversation.scrollTop=conversation.scrollHeight}

async function resolveApproval(approve,button){
  if(!pendingApprovalToken)return;
  const conversation=$('conversation'),token=pendingApprovalToken;
  document.querySelectorAll('[data-agent-approval]').forEach(control=>control.disabled=true);
  button.closest('.approval-message').classList.add(approve?'approved':'cancelled');
  conversation.insertAdjacentHTML('beforeend',`<div id="approvalThinking" class="agent-message loading"><div class="avatar">AI</div><div>${approve?'Executing the approved operation…':'Cancelling the proposed operation…'}</div></div>`);
  conversation.scrollTop=conversation.scrollHeight;
  try{
    const data=await jsonFetch('/api/agent/approval',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({approval_token:token,approve})});
    $('approvalThinking').remove();renderAgentResult(data);if(approve)await loadWorkspace();
  }catch(error){$('approvalThinking').remove();conversation.insertAdjacentHTML('beforeend',`<div class="agent-message"><div class="avatar">!</div><div>${escapeHtml(error.message)}</div></div>`)}
  conversation.scrollTop=conversation.scrollHeight;
}

function investigationHtml(row){return `<div class="record"><div class="record-head"><div><h3>${escapeHtml(row.title)}</h3><p>${escapeHtml(row.summary)}</p></div><span class="tag">${escapeHtml(row.status)}</span></div></div>`}
function actionHtml(row){return `<div class="record"><div class="record-head"><div><h3>${escapeHtml(row.action_text)}</h3><p>Due ${escapeHtml(row.due_date||'not set')}</p></div><span class="tag priority-${escapeHtml(row.priority)}">${escapeHtml(row.priority)}</span></div>${row.status==='open'?`<div class="action-controls"><button data-complete="${escapeHtml(row.action_id)}">Mark completed</button></div>`:`<span class="tag">${escapeHtml(row.status)}</span>`}</div>`}
function noteHtml(row){return `<div class="record note-record"><div class="record-head"><div><h3>${escapeHtml(row.investigation_title||'Investigation note')}</h3><p>${escapeHtml(row.note_text)}</p><small>${escapeHtml(row.author||'Agent-assisted note')}</small></div><span class="note-mark">N</span></div></div>`}
function collectionHtml(rows,error,renderer,empty){return error?`<p class="empty warning">${escapeHtml(error)}</p>`:rows.length?rows.map(renderer).join(''):`<p class="empty">${empty}</p>`}
async function loadWorkspace(){try{const data=await jsonFetch('/api/workspace'),errors=data.errors||{};$('investigations').innerHTML=collectionHtml(data.investigations,errors.investigations,investigationHtml,'No saved investigations yet.');$('actions').innerHTML=collectionHtml(data.actions,errors.actions,actionHtml,'No follow-up actions yet.');$('notes').innerHTML=collectionHtml(data.notes,errors.notes,noteHtml,'No analyst notes yet.');const select=$('noteInvestigation'),selected=select.value;select.innerHTML='<option value="">Choose an investigation</option>'+data.investigations.map(row=>`<option value="${escapeHtml(row.investigation_id)}">${escapeHtml(row.title)}</option>`).join('');if([...select.options].some(option=>option.value===selected))select.value=selected}catch(error){$('investigations').innerHTML=$('actions').innerHTML=$('notes').innerHTML=`<p class="empty">${escapeHtml(error.message)}</p>`}}

async function addControllerNote(event){event.preventDefault();const investigationId=$('noteInvestigation').value,noteText=$('noteText').value.trim(),button=event.submitter||event.currentTarget.querySelector('button[type="submit"]'),status=$('noteStatus');if(!investigationId||!noteText)return;button.disabled=true;status.textContent='Saving…';try{await jsonFetch(`/api/investigations/${encodeURIComponent(investigationId)}/notes`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({note_text:noteText})});$('noteText').value='';status.textContent='Note saved';await loadWorkspace()}catch(error){status.textContent=error.message}finally{button.disabled=false}}

document.addEventListener('click',async event=>{const approval=event.target.dataset.agentApproval;if(approval)await resolveApproval(approval==='true',event.target);const prompt=event.target.dataset.prompt;if(prompt)$('question').value=prompt;const id=event.target.dataset.complete;if(id){event.target.disabled=true;try{await jsonFetch(`/api/actions/${id}/complete`,{method:'POST'});await loadWorkspace()}catch(error){event.target.textContent=error.message}}});
$('agentForm').addEventListener('submit',ask);$('noteForm').addEventListener('submit',addControllerNote);$('refresh').addEventListener('click',loadDashboard);$('reloadWorkspace').addEventListener('click',loadWorkspace);loadDashboard();loadWorkspace();

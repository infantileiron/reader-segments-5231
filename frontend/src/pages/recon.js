import {state} from '../stores/session.js';import {esc} from '../utils/html.js';import {badge} from '../components/common/status.js';import {table} from '../components/common/table.js';import {select} from '../components/common/fields.js';
const RESULT={delivered:'送达',bounced:'退信'};
const STATUS={success:'成功',failed:'失败',pending:'待定'};
const STATE={pending:'待对账',settled:'已结算'};
function eligibility(h){if(h.status==='pending')return '不补发（待定）';if(h.chain_success)return '链上已成功，不再补发';if(h.resend_eligible)return '确认失败，可补发';if(h.pending_in_plan)return '已进入补发方案 #'+h.pending_in_plan+'，待其回执';return '确认失败，可补发'}
export function render(){
 const d=state.reconDetail,b=d?.batch,sum=b?.summary,diff=d?.difference;
 const approved=state.outreaches.filter(o=>o.status==='approved'&&o.parent_outreach_id===null);
 const selected=d||null;
 return `<div class="split"><section class="panel"><div class="result-head"><h2>回执对账，按时间还原每个人的送达历程</h2>${b?badge(STATE[b.state]||b.state):''}</div>
 <p class="notice">回执按渠道+流水号归档，按发生时间还原最终状态：迟到的退信会纠正先前的成功。同号异文与名单外回执隔离，不参与人数统计。成功、失败、待定三者合计必须等于冻结名单人数。</p>
 <h3>对账批次</h3>${table(['批次','方案','状态','冻结人数','成功','失败','待定','差额'],state.reconBatches.map(x=>[x.id,'#'+x.outreach_id,STATE[x.state]||x.state,x.summary.roster_size,x.summary.success,x.summary.failed,x.summary.pending,x.balance_ok?'0 ✓':'⚠ '+x.summary.balance]))}
 ${state.reconBatches.length?`<p>查看详情：${state.reconBatches.map(x=>`<button class="study" data-recon="${x.id}">#${x.id} 方案#${x.outreach_id} ${STATE[x.state]||x.state}</button>`).join('')}</p>`:'<p class="muted">选择已签核方案建立第一个对账批次。</p>'}
 ${selected?`<h3>批次 #${b.id} 差额核对</h3><div class="metrics"><div><strong>${sum.roster_size}</strong>冻结名单</div><div><strong>${sum.success}</strong>成功</div><div><strong>${sum.failed}</strong>失败</div><div><strong>${sum.pending}</strong>待定</div><div><strong>${sum.balance===0?'0':sum.balance}</strong>差额</div></div>
 <p class="notice">原始回执 ${diff.raw_receipts} 条 / 有效回执凭证 ${diff.accepted_receipts} 条；重复 ${diff.duplicated} 条只计数到达次数，不增加覆盖；隔离 ${diff.quarantined} 条。原始回执按会员去重会得到 ${diff.raw_members} 人，其中真正确认 ${diff.covered} 人、待定 ${diff.pending} 人；原始口径多计 ${diff.overcount} 人。</p>
 <h3>隔离回执 / 原因</h3>${table(['渠道','流水号','会员','发生时间','结果','隔离原因'],(d.quarantined||[]).map(q=>[q.channel,q.serial,q.member,q.occurred_at,RESULT[q.result]||q.result,q.reason]))}
 <h3>会员历程</h3>${table(['会员','最终状态','补发资格','发生时间','结果','渠道 · 流水号'],d.history.flatMap(h=>h.events.length?h.events.map((e,i)=>[i?'':h.member,i?'':(STATUS[h.status]||h.status),i?'':eligibility(h),e.occurred_at,RESULT[e.result]||e.result,e.channel+' · '+e.serial+(e.occurrences>1?' · 重复'+e.occurrences+'次':'')]):[[h.member,STATUS[h.status]||h.status,eligibility(h),'—','—','尚无有效回执']]))}
 <h3>补发方案</h3>${d.resends.length?d.resends.map(p=>`<article class="rec"><h3>补发方案 #${p.outreach_id} ${badge(p.status)}</h3><p>${p.members.length}位会员 · 来源批次 #${b.id}${p.already_successful.length?' · 其中已成功 '+esc(p.already_successful.join(' / ')):''}</p><p class="member-line">${p.members.map(esc).join(' / ')}</p></article>`).join(''):'<p class="muted">尚无补发方案。只有确认失败且整条链未成功的会员会进入补发；待定不补发。</p>'}`:''}</section>
 <aside class="side"><h2>建立批次</h2><form id="recon-create">${select('已签核方案','outreach_id',approved.map(o=>[o.id,'#'+o.id+' '+o.title+'（'+o.members.length+'人）']))}<label>对账说明<textarea name="note" rows="2" maxlength="1000" placeholder="例如：短信渠道 11/10 回执"></textarea></label><p>批次绑定签核时的冻结名单；同一方案只能建一个批次，补发沿用原批次。</p><button class="primary">建立待对账批次</button></form>
 <h2>回传与结算</h2><form id="recon-settle"><label>目标批次<select name="batch_id">${state.reconBatches.map(x=>`<option value="${x.id}" ${d&&d.batch.id===x.id?'selected':''}>#${x.id} 方案#${x.outreach_id} ${STATE[x.state]||x.state}</option>`).join('')}</select></label><label>回执明细（每行 渠道,流水号,会员,发生时间,结果）<textarea name="receipts" rows="8" placeholder="sms,S-1001,SL-001,2026-11-10T09:00:00Z,delivered&#10;sms,S-1002,SL-002,2026-11-10T09:30:00Z,bounced"></textarea></label><label>结算备注<textarea name="note" rows="2" maxlength="1000"></textarea></label><p>整批校验：任一行格式或时间错误则整批拒绝；同一渠道流水号出现异文会隔离，不按顺序猜测。中断后重跑同一批回执不会重复建补发。</p><button class="primary">校验并整批结算</button></form>
 <button id="recon-refresh">刷新批次</button></aside></div>`}

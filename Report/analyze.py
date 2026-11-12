"""Reproducible private CPHTest scan analysis; does not use or start PostgreSQL."""
import os,json,csv,hashlib,shutil,statistics,math,base64,html,zipfile
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
OUT=Path(__file__).resolve().parent
SOURCE=OUT/'raw'  # Archived input; regeneration requires no service or API credentials.
os.environ.setdefault('MPLCONFIGDIR',str(OUT/'.mpl-cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
RAW=OUT/'raw';RAW.mkdir(exist_ok=True)
records=[];checksums=[]
for source in sorted(SOURCE.glob('*.json')):
 content=source.read_bytes();target=RAW/source.name
 if not target.exists():target.write_bytes(content)
 assert target.read_bytes()==content
 data=json.loads(content);assert data['id']==source.stem
 records.append(data);checksums.append({'file':'raw/'+source.name,'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)})
records.sort(key=lambda r:(r['received_at'],r['id']))
assert len(records)==len({r['id'] for r in records})==len({r['payload']['event_id'] for r in records})
# Fixed offset is used here for this November session, avoiding optional Windows tzdata.
from datetime import timezone,timedelta
EASTERN=timezone(timedelta(hours=-5),'EST')
def local_time(r):return datetime.fromisoformat(r['received_at']).astimezone(EASTERN).isoformat()
assert {local_time(r)[:10] for r in records}=={'2026-11-11'}
assert len({r['payload']['performance']['hashes_checked'] for r in records})==1
attempts=[]
for index,r in enumerate(records,1):
 p=r['payload'];s=p.get('selected_comic') or {};results=p['results']
 assert len(results)==8 and [x['distance'] for x in results]==sorted(x['distance'] for x in results)
 assert len(p['search_hash'])==16
 if p['outcome']=='match':
  assert p['rank']==1+sum(x['distance']<s['distance'] for x in results)
  assert p['bits_off']==(int(p['search_hash'],16)^int(s['matched_cover']['cover_hash'],16)).bit_count()
  assert results[p['array_position']-1]['id']==s['id']
 else:assert p['outcome']=='no_match'
 h=p['client_timing']['hash_ms'];rt=p['client_timing']['api_round_trip_ms'];db=p['performance']['database_match_ms']
 assert all(math.isfinite(x) and x>=0 for x in [h,rt,db])
 attempts.append({'attempt_index':index,'record_id':r['id'],'event_id':p['event_id'],'received_at_utc':r['received_at'],'received_at_est':local_time(r),'outcome':p['outcome'],'search_hash':p['search_hash'],'selected_issue_id':s.get('id'),'selected_issue':s.get('issue'),'selected_variant_id':s.get('matched_cover',{}).get('variant_id'),'rank':p.get('rank'),'array_position':p.get('array_position'),'bits_off':p.get('bits_off'),'database_match_ms':db,'hash_ms':h,'api_round_trip_ms':rt,'hash_plus_api_ms':h+rt,'hashes_checked':p['performance']['hashes_checked']})
trials=[];pairs=[];i=0
while i<len(attempts):
 first=attempts[i];group=[first]
 if first['outcome']=='match':outcome='first_scan_success';i+=1
 else:
  if i+1>=len(attempts):raise ValueError('Incomplete final retry; manual review required')
  group.append(attempts[i+1]);outcome='second_scan_success' if group[1]['outcome']=='match' else 'failure_after_two';i+=2
 last=group[-1];ident=len(trials)+1
 trials.append({'trial_index':ident,'outcome':outcome,'attempt_count':len(group),'attempt_indices':','.join(str(a['attempt_index']) for a in group),'record_ids':','.join(a['record_id'] for a in group),'started_at_est':first['received_at_est'],'ended_at_est':last['received_at_est'],'issue_id':last['selected_issue_id'],'issue':last['selected_issue'],'rank':last['rank'] if last['outcome']=='match' else None,'bits_off':last['bits_off'],'database_match_ms_sum':sum(a['database_match_ms'] for a in group),'hash_ms_sum':sum(a['hash_ms'] for a in group),'api_round_trip_ms_sum':sum(a['api_round_trip_ms'] for a in group),'hash_plus_api_ms_sum':sum(a['hash_plus_api_ms'] for a in group)})
 for ordinal,a in enumerate(group,1):a.update(trial_index=ident,attempt_in_trial=ordinal)
 if len(group)==2:
  pairs.append({'trial_index':ident,'attempt_1':first['attempt_index'],'attempt_2':last['attempt_index'],'record_1':first['record_id'],'record_2':last['record_id'],'second_outcome':last['outcome'],'recovered_comic':last['selected_issue'],'hash_change_bits':(int(first['search_hash'],16)^int(last['search_hash'],16)).bit_count(),'seconds_between_notes':(datetime.fromisoformat(last['received_at_utc'])-datetime.fromisoformat(first['received_at_utc'])).total_seconds(),'grouping_basis':'chronological application of stated two-attempt policy; no explicit item/session ID logged'})
assert sum(t['attempt_count'] for t in trials)==len(records)
# Human identity annotations supplement the analysis without altering raw notes/outcomes.
confirmation_path=OUT/'confirmed-failed-identities.json'
confirmations=json.loads(confirmation_path.read_text(encoding='utf-8')) if confirmation_path.exists() else {}
for trial in trials:
    trial['identity_note']=''
    trial['cover_reference_status']='not independently established'
    trial['identity_source']='successful scan selection' if trial['outcome']!='failure_after_two' else 'not recorded'
    annotation=confirmations.get(str(trial['trial_index']))
    if annotation:
        assert trial['outcome']=='failure_after_two'
        trial['issue']=annotation['issue'];trial['issue_id']=annotation.get('issue_id')
        trial['identity_source']=annotation['source']
        trial['identity_note']=annotation.get('note','')
        trial['cover_reference_status']=annotation.get('coverage_status','not independently established')
# Exclusions apply after trial reconstruction, preserving original trial/attempt IDs.
exclusion_path=OUT/'excluded-trials.json'
exclusions=json.loads(exclusion_path.read_text(encoding='utf-8')) if exclusion_path.exists() else {}
all_trials=trials;all_attempts=attempts;all_pairs=pairs
for collection in [all_trials,all_attempts,all_pairs]:
    for row in collection:
        exclusion=exclusions.get(str(row['trial_index']))
        row['analysis_included']=not bool(exclusion)
        row['exclusion_reason']=exclusion['reason'] if exclusion else ''
trials=[t for t in all_trials if t['analysis_included']]
attempts=[a for a in all_attempts if a['analysis_included']]
pairs=[p for p in all_pairs if p['analysis_included']]
active_confirmation_count=sum(str(t['trial_index']) in confirmations for t in trials if t['outcome']=='failure_after_two')
counts=Counter(t['outcome'] for t in trials);N=len(trials);A=len(attempts);success=counts['first_scan_success']+counts['second_scan_success'];failed=counts['failure_after_two']
assert (A,N,success)==(167,138,127)
rank_counts=Counter(t['rank'] for t in trials if t['rank'] is not None)
metrics={'hash_ms':'Android Client Hash Processing','database_match_ms':'Postgres Hash Search','api_round_trip_ms':'API Round Trip','hash_plus_api_ms':'User Experience'}
def stats(values):return {'n':len(values),'min_ms':min(values),'max_ms':max(values),'mean_ms':statistics.mean(values),'median_ms':statistics.median(values)}
timing=[{'metric':label,**stats([a[key] for a in attempts])} for key,label in metrics.items()]
trial_timing=[{'metric':label,**stats([t[key+'_sum'] for t in trials])} for key,label in metrics.items()]
summary={'date_local':'2026-11-11','timezone':'America/New_York (EST, UTC-05:00 for this session)','start_local':local_time(records[0]),'end_local':local_time(records[-1]),'raw_notes':len(records),'included_attempts':A,'raw_comic_trials':len(all_trials),'matches':success,'no_match_attempts':sum(a['outcome']=='no_match' for a in attempts),'reconstructed_comic_trials':N,'first_scan_successes':counts['first_scan_success'],'second_scan_only_successes':counts['second_scan_success'],'failures_after_two':failed,'retried_comics':len(pairs),'first_scan_success_percent':100*counts['first_scan_success']/N,'success_within_two_percent':100*success/N,'failure_after_two_percent':100*failed/N,'retry_rescue_percent':100*counts['second_scan_success']/len(pairs),'rank_counts':{str(k):rank_counts[k] for k in range(1,9)},'rank1_percent_all_trials':100*rank_counts[1]/N,'rank1_percent_successful_trials':100*rank_counts[1]/success,'hashes_checked_per_attempt':40112,'distinct_selected_issue_ids':len({a['selected_issue_id'] for a in attempts if a['selected_issue_id'] is not None}),'timing_per_attempt_ms':timing,'timing_total_work_per_comic_ms':trial_timing,'pairing_limitation':'Trials are reconstructed solely from chronological records and the stated policy. Failure notes contain no intended comic/session ID; failed comic titles cannot be established from the notes. Assumes every attempt was recorded and the policy was followed without exceptions.','scope_limitation':'Descriptive results for this one session, not a randomized benchmark or a general accuracy estimate. No failed title is inferred from neighbors. No attempts/outliers are excluded.'}
summary['confirmed_failed_identities']=confirmations
summary['unidentified_failed_trials']=failed-active_confirmation_count
summary['excluded_trials']=exclusions
summary['excluded_attempts']=len(all_attempts)-A
summary['confirmed_included_failed_identities']=active_confirmation_count
summary['known_unrepresented_cover_trials']=[int(k) for k,v in confirmations.items() if v.get('coverage_status')=='exact_cover_not_in_metron']
summary['pairing_limitation']='Trials are reconstructed from chronological records and the stated policy. Failure notes contain no intended comic/session ID. Later user confirmations identify '+str(active_confirmation_count)+' included failed comics; '+str(failed-active_confirmation_count)+' remain unidentified. Assumes every attempt was recorded and the policy was followed without exceptions.'
summary['scope_limitation']='Descriptive results for this one session, not a randomized benchmark or general accuracy estimate. Only user-confirmed failed identities enter the report; sequence-based guesses remain separate. The user-requested coverage exclusion is documented; no timing outliers or other attempts are excluded.'
def write_json(name,value):(OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def write_csv(name,rows):
 with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
write_json('checksums.json',checksums);write_json('summary.json',summary)
write_csv('all-attempts-audit.csv',all_attempts);write_csv('all-comic-trials-audit.csv',all_trials);write_csv('all-retry-pairs-audit.csv',all_pairs)
write_csv('attempts.csv',attempts);write_csv('comic-trials.csv',trials);write_csv('retry-pair-audit.csv',pairs);write_csv('processing-times-per-attempt.csv',timing);write_csv('processing-work-per-comic.csv',trial_timing)
write_csv('outcomes.csv',[{'outcome':k,'comics':counts[k],'percent_of_included_comics':counts[k]*100/N} for k in ['first_scan_success','second_scan_success','failure_after_two']])
rank_rows=[]
for rank in range(1,9):
 rank_rows.append({'rank_or_failure':str(rank),'first_scan_success':sum(t['rank']==rank and t['outcome']=='first_scan_success' for t in trials),'retry_success':sum(t['rank']==rank and t['outcome']=='second_scan_success' for t in trials),'failures':0,'total':rank_counts[rank],'percent_all_comics':rank_counts[rank]*100/N})
rank_rows.append({'rank_or_failure':'Failure after two','first_scan_success':0,'retry_success':0,'failures':failed,'total':failed,'percent_all_comics':failed*100/N})
write_csv('rank-frequency.csv',rank_rows)
with (OUT/'raw-notes.jsonl').open('w',encoding='utf-8') as f:
 for r in records:f.write(json.dumps(r,ensure_ascii=False)+'\n')
# Standalone publication/export charts.
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'axes.spines.top':False,'axes.spines.right':False,'axes.titleweight':'bold','axes.axisbelow':True,'svg.fonttype':'none','pdf.fonttype':42})
first_color='#157F79';retry_color='#D49A25';failure_color='#B94B4B'
fig,(ax,bx)=plt.subplots(1,2,figsize=(15,5.8),gridspec_kw={'width_ratios':[1,1.6]})
vals=[counts['first_scan_success'],counts['second_scan_success'],failed]
bars=ax.bar(range(3),vals,color=[first_color,retry_color,failure_color],width=.62)
ax.set_xticks(range(3),['First-scan\nsuccess','Retry-only\nsuccess','Failed after\ntwo scans']);ax.set_ylabel('Comic trials');ax.set_title('Outcomes under the Two-Attempt Policy',loc='left',pad=25);ax.set_ylim(0,130);ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True));ax.grid(axis='y',alpha=.18)
for bar,v in zip(bars,vals):ax.text(bar.get_x()+bar.get_width()/2,v+3,f'{v}\n{v/N:.1%}',ha='center',va='bottom',fontsize=11)
ax.text(0,-.26,'Cumulative successes: 109 after one scan; 127 within two.',transform=ax.transAxes,fontsize=10)
x=np.arange(9);first=[r['first_scan_success'] for r in rank_rows];retry=[r['retry_success'] for r in rank_rows];fail=[r['failures'] for r in rank_rows]
bx.bar(x,first,color=first_color,label='First scan');bx.bar(x,retry,bottom=first,color=retry_color,label='Retry');bx.bar(x,fail,bottom=np.array(first)+np.array(retry),color=failure_color,label='Failure after two')
bx.set_xticks(x,[str(k) for k in range(1,9)]+['Failure']);bx.set_ylabel('Comic trials');bx.set_xlabel('Competition rank of selected result; failure counted once');bx.set_ylim(0,141);bx.grid(axis='y',alpha=.18);bx.set_title('Final Rank Frequency, Adjusted for Retries',loc='left',pad=25);bx.legend(frameon=False,loc='upper right',fontsize=10)
for pos,row in zip(x,rank_rows):bx.text(pos,row['total']+2,str(row['total']),ha='center',va='bottom')
fig.suptitle(f'CPHTest | {N} Eligible Comic Trials · {A} Scan Attempts · 40,112 Candidate Hashes',x=.06,ha='left',fontsize=15,y=.99)
fig.subplots_adjust(top=.81,bottom=.25,left=.06,right=.98,wspace=.24)
for suffix in ['png','svg','pdf']:fig.savefig(OUT/f'outcomes-and-ranks.{suffix}',dpi=190,facecolor='white')
plt.close(fig)
fig,axes=plt.subplots(4,1,figsize=(12,10))
rng=np.random.default_rng(41)
for ax,(key,label),color in zip(axes,list(metrics.items()),['#5773A6',first_color,retry_color,'#715C9E']):
 values=np.array([a[key] for a in attempts]);ax.scatter(values,rng.uniform(-.11,.11,len(values)),s=13,alpha=.38,color=color,linewidths=0)
 ax.axvline(np.median(values),color='#222222',lw=1.8,label='Median');ax.axvline(np.mean(values),color=color,lw=1.8,ls='--',label='Mean')
 ax.set_yticks([]);ax.set_ylim(-.18,.18);ax.set_title(f'{label} (n = {A})',loc='left',fontsize=12);ax.grid(axis='x',alpha=.2);ax.set_xlabel('Milliseconds');ax.spines['left'].set_visible(False)
 ax.legend(frameon=False,loc='upper right',ncol=2,fontsize=9)
fig.suptitle('Processing Times per Scan Attempt — Every Retry Included',x=.08,ha='left',fontsize=15)
fig.subplots_adjust(left=.08,right=.97,top=.9,bottom=.08,hspace=.9)
for suffix in ['png','svg','pdf']:fig.savefig(OUT/f'processing-times.{suffix}',dpi=190,facecolor='white')
plt.close(fig)
def table(rows,fields,labels):
 return '<table><thead><tr>'+''.join('<th>'+html.escape(l)+'</th>' for l in labels)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(f'{r[k]:.3f}' if isinstance(r[k],float) else str(r[k] if r[k] is not None else 'Unknown'))+'</td>' for k in fields)+'</tr>' for r in rows)+'</tbody></table>'
def embedded(name):return 'data:image/png;base64,'+base64.b64encode((OUT/name).read_bytes()).decode()
limitations=html.escape(summary['pairing_limitation'])
md=f'''# CPHTest scan analysis — November 11, 2026

Local Metron and PostgreSQL were stopped before extraction and remain stopped.
The archive contains {len(records)} original notes from November 11, {local_time(records[0])[11:19]}–{local_time(records[-1])[11:19]} EST.
The previously deleted November 9 test note is not included.

## Policy-adjusted comic outcomes

- Comic trials reconstructed: {N}
- First-scan successes: {counts['first_scan_success']} ({100*counts['first_scan_success']/N:.2f}%)
- Additional successes on second scan: {counts['second_scan_success']} ({100*counts['second_scan_success']/N:.2f}%)
- Cumulative successes within two scans: {success} ({100*success/N:.2f}%)
- Failures after both attempts: {failed} ({100*failed/N:.2f}%)
- Retried comics: {len(pairs)}; retry rescued {counts['second_scan_success']} ({100*counts['second_scan_success']/len(pairs):.1f}%).

{A} included attempts = 109 single-attempt trials + {len(pairs)} two-attempt trials.
The raw archive retains {len(records)} notes; trial 7 and its two attempts are excluded from results.
{summary['no_match_attempts']} included no-match attempts = {len(pairs)} first failures + {failed} failed retries.
Rank frequencies count each comic once, using its eventual successful rank or one final failure.
Final ranks: #1 = 122, #2 = 3, #3 = 2, #4–8 = 0, final failure = {failed}.
Rank #1 was {100*rank_counts[1]/success:.2f}% of successful comics and {100*rank_counts[1]/N:.2f}% of all trials.
Competition ranking honors ties (e.g. 1, 1, 3).

## Pairing assumptions and limitations

{summary['pairing_limitation']}
Of the {failed} included failed trials, {active_confirmation_count} titles were subsequently confirmed by the user; {failed-active_confirmation_count} remain unknown. Confirmed identities are stored separately from the raw notes. No unconfirmed sequence guesses are treated as known identities.
The full audit contains all {len(all_pairs)} inferred retry pairs, including the excluded trial; the results contain {len(pairs)} eligible pairs, their source record IDs, timestamps, and hash changes.
One pair (attempts 38–39, Monstress #55) changed by 20 hash bits; this is a review flag,
not evidence of a policy violation. No pair was excluded or regrouped using a hash threshold.

Every successful selected rank, array position, and bit distance validated against its result list.
There were no repeated event IDs or repeated selected issue IDs. All 169 records searched 40,112 hashes.
This is a descriptive analysis of one session, not a randomized accuracy estimate.

## Timing interpretation

All per-attempt statistics include the {A} eligible attempts, including failed first scans and failed retries; trial 7’s two attempts are excluded.
Postgres hash search is included in API round trip. Do not add those two measurements together.
User experience is the sum of Android client hash processing and API round trip; it excludes camera/corner editing,
user decision time, feedback submission time, and artwork loading. It is not full scan wall-clock latency.
`processing-work-per-comic.csv` sums the one or two measured attempts belonging to each inferred trial.
No timing outliers, first requests, or presumed cold/warm samples were removed; the sole trial exclusion is recorded in excluded-trials.json.

## Files

- `raw/`: byte-for-byte original notes, preserved independently of source records.
- `checksums.json`: SHA-256 checksums and byte sizes for the original notes.
- `raw-notes.jsonl`: combined chronological raw records.
- `attempts.csv`: included attempts, with original inferred trial/attempt ordinal.
- `all-attempts-audit.csv`, `all-comic-trials-audit.csv`, `all-retry-pairs-audit.csv`: full records with inclusion flags.
- `excluded-trials.json`: user-requested coverage exclusion and rationale.
- `comic-trials.csv`: one outcome per inferred comic trial.
- `retry-pair-audit.csv`: pairing audit and hash changes.
- `outcomes.csv`, `rank-frequency.csv`: chart data.
- `processing-times-per-attempt.csv`, `processing-work-per-comic.csv`: timing summaries.
- `summary.json`: machine-readable findings and limitations.
- PNG/SVG/PDF charts, self-contained `perceptual-hash-experiment-report.html`, and this reproducible script.
'''
md += "\n## Appendix: measurement definitions\n\nThese are elapsed wall-clock measurements, not CPU-only measurements. Waiting,\nI/O, scheduling delays, and garbage collection inside a measurement window are\nincluded. The processing order is:\n\nAndroid client hash processing → API request → Postgres hash search → API response.\nAPI round trip surrounds the request, database work, and response.\n\n### Android client hash processing\n\nStarts on Android immediately before dispatching hash work to `Dispatchers.Default`.\nEnds immediately after the hexadecimal hash string is produced, before bitmap\nrecycling and returning the finished result to the UI thread.\n\nIncludes waiting for the background task to start; reading the corrected JPEG's\ndimensions; reading and decoding the JPEG into an ARGB bitmap; allocating/copying\nthe pixel array; converting to grayscale; Lanczos resizing to 32 × 32; computing\nthe DCT; selecting the 8 × 8 coefficients; calculating the median; and forming\nthe 64-bit hexadecimal hash. First-use hash-object initialization, if any, is\ninside this window as well.\n\nExcludes camera capture, corner adjustment, perspective correction, preview,\nuser confirmation, bitmap recycling after the timestamp, and dispatch back to\nthe UI thread after the hash completes.\n\n### Postgres hash search\n\nStarts when PostgreSQL evaluates the materialized start-clock expression before\nscanning candidate hashes. Ends when the outer SQL result samples the elapsed\nclock after ranking and assembling the match records. This is the instrumented\nmatching portion of query execution, not the complete database request duration.\n\nIncludes reading valid issue and variant hashes; XOR/popcount Hamming distance\ncalculations; taking each comic's closest cover; ranking and selecting the top\neight distinct comics; retrieving winning cover hashes, URLs, and variant IDs;\ncounting hashes checked; SQL result assembly; and instrumentation overhead.\n\nExcludes SQL parsing/planning, opening a database connection, transport between\nDjango and PostgreSQL, authentication, the subsequent query for descriptive\nmetadata of the eight comics, and Django's response serialization.\n\n### API round trip\n\nStarts immediately before dispatching the API operation to `Dispatchers.IO`.\nEnds after it returns to the UI thread.\n\nIncludes client dispatch/queue waits; constructing and validating the request and\nheaders; acquiring a connection; DNS, TCP setup, and TLS negotiation when needed;\nrequest and response network travel; server request handling, authentication,\nthrottling, validation, database matching, the separate comic-metadata query,\nand response serialization; receiving the complete JSON body; Android JSON parsing\nand basic result-shape validation; response cleanup; and returning to the UI thread.\nConnection reuse may avoid DNS/connection/TLS setup on a particular request.\n\nExcludes building result cards, downloading/displaying cover artwork, human match\nselection, and feedback submission.\n\n### User experience\n\nDerived sum: **Android client hash processing + API round trip**.\n\nThis is not one continuously running timer and is not the complete human scan\nexperience. The gap between its component timers is excluded: bitmap recycling,\nreturning from the hash task, and updating the “Searching Metron…” UI. It also\nexcludes capture, corner adjustment/perspective correction, preview/confirmation,\nhuman decisions, result rendering, artwork loading, and feedback submission.\n\nPostgres hash search is already included in API round trip. Do not add it again.\nPer-comic processing-work totals sum these measurements over the one or two\nattempts reconstructed for that comic, without adding the human retry delay.\n"
(OUT/'README.md').write_text(md,encoding='utf-8')
timing_html=table(timing,['metric','min_ms','max_ms','mean_ms','median_ms'],['Measurement','Min (ms)','Max (ms)','Mean (ms)','Median (ms)'])
failed_rows=[t for t in trials if t['outcome']=='failure_after_two']
report=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>CPHTest — November 11 scan analysis</title><style>body{{font:16px/1.6 system-ui,sans-serif;color:#192732;max-width:1200px;margin:40px auto;padding:0 24px}}h1,h2{{line-height:1.25}}h2{{margin-top:36px}}p{{max-width:1000px}}img{{max-width:100%;height:auto}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}th,td{{padding:10px 12px;border-bottom:1px solid #dce1e5;text-align:right}}th:first-child,td:first-child{{text-align:left}}.lead{{font-size:20px}}.note{{border-left:4px solid #b4801c;background:#fcf7ea;padding:14px 18px}}small{{color:#475965}}@media print{{body{{margin:0;font-size:11pt}}img{{break-inside:avoid}}}}</style><h1>CPHTest scan analysis</h1><p>November 11, 2026 · 4:03–5:21 PM Eastern · 40,112 candidate hashes</p><p class="lead"><strong>{success} of {N} eligible comics matched within two attempts ({100*success/N:.2f}%).</strong> First scan: {counts['first_scan_success']}; retry rescue: {counts['second_scan_success']}; failed twice: {failed}.</p><p class="note"><strong>Retry grouping is reconstructed.</strong> {limitations} Original records are preserved; the <a href="retry-pair-audit.csv">pairing audit</a> makes every grouping reviewable.</p><h2>Outcomes and final ranks</h2><img src="{embedded('outcomes-and-ranks.png')}" alt="109 first-scan successes, 18 retry-only successes, {failed} failures; final rank counts 122 at rank 1, 3 at rank 2, 2 at rank 3, {failed} failures"><p>The {summary['no_match_attempts']} included no-match reports are <strong>not {summary['no_match_attempts']} failed comics</strong>: they represent {len(pairs)} failed first attempts plus {failed} failed retries. Every successful comic contributes only its final selected rank. The 18 retry successes were all rank #1. Among successful comics, 96.06% ranked first; among all {N} eligible trials, {100*rank_counts[1]/N:.2f}% ended with a rank-one match.</p><h2>Processing times</h2>{timing_html}<p><small>All {A} eligible attempts included. Postgres hash search is part of API round trip, so these are overlapping timings. User experience excludes capture/corner editing, human decisions, artwork loading, and feedback submission.</small></p><img src="{embedded('processing-times.png')}" alt="Distributions of Android client hash processing, Postgres hash search, API round trip, and User experience"><h2>Measured processing work per comic, including retries</h2>{table(trial_timing,['metric','n','min_ms','max_ms','mean_ms','median_ms'],['Summed work across 1–2 attempts','n','Min (ms)','Max (ms)','Mean (ms)','Median (ms)'])}<p>These totals sum measured work across each inferred comic trial; they do not include time spent recapturing or making decisions.</p><h2>Trials unsuccessful after two scans</h2><p>These {failed} eligible trials failed twice. Later user confirmation identifies {active_confirmation_count} of them; {failed-active_confirmation_count} remain unidentified. Identities were not recorded in the original failure notes. Catalog presence at scan time is not established by this identity confirmation.</p>{table(failed_rows,['trial_index','attempt_indices','issue','identity_source'],['Trial','Attempt indices','Comic (when confirmed)','Identity source'])}<h2>Validation and audit</h2><ul><li>No duplicate event IDs; all selected ranks, array positions, and Hamming distances validate.</li><li>All 169 searches examined exactly 40,112 cover hashes.</li><li>127 successful selections identify 127 distinct issue IDs.</li><li>The original notes are preserved byte-for-byte with SHA-256 checksums.</li><li>Timing includes all outliers and first requests; no warm/cold cache cause is inferred.</li></ul><p>Retry pairing is based on chronology and the supplied policy, not similarity or guessed titles. One pair changed by 20 hash bits and is flagged in the audit for review, without changing its grouping. This single-session result should not be treated as a general population accuracy estimate.</p><h2>Data and reproducibility</h2><p><a href="attempts.csv">All attempts</a> · <a href="comic-trials.csv">Comic trials</a> · <a href="retry-pair-audit.csv">Retry audit</a> · <a href="rank-frequency.csv">Rank data</a> · <a href="summary.json">Summary JSON</a> · <a href="README.md">Methodology</a></p><p>Original notes remain unchanged at the source. Local Metron and PostgreSQL remain stopped.</p></html>'''
confirmation_notes = [(c['issue'], c.get('note')) for c in confirmations.values() if c.get('note')]
if confirmation_notes:
    notes_html='<h3>Collection and cover-reference context supplied after scanning</h3><ul>'+''.join('<li><strong>'+html.escape(title)+'</strong>: '+html.escape(note)+'</li>' for title,note in confirmation_notes)+'</ul>'
    report=report.replace('<h2>Validation and audit</h2>', '<h2>Validation and audit</h2>'+notes_html)
exclusion_html='<h3>Excluded trial: unavailable reference cover</h3><p><strong>Trial 7 — Absolute Wonder Woman #12, unrepresented variant.</strong> The user confirmed this cover is not in Metron and requested its exclusion. Its original attempts 8 and 9 are omitted from outcome percentages, rank frequencies, per-attempt processing times, and per-comic processing totals. The raw notes remain unchanged. The eligible analysis therefore contains <strong>138 comics and 167 attempts</strong>, from an archive of 139 trials and 169 notes. This is a coverage-based exclusion, not a removed timing outlier.</p><p><a href="excluded-trials.json">Exclusion rationale</a> · <a href="all-comic-trials-audit.csv">All trials with inclusion flags</a> · <a href="all-attempts-audit.csv">All attempts with inclusion flags</a></p>'
report=report.replace('<h2>Validation and audit</h2>','<h2>Validation and audit</h2>'+exclusion_html)
md += '\n## Validation exclusion\n\nTrial 7 (Absolute Wonder Woman #12 variant) and original attempts 8 and 9 are excluded from all charts, outcome/rank statistics, and timing statistics because the user confirmed the cover was not represented in Metron. Raw notes are retained unchanged. Included sample: 138 comic trials and 167 attempts.\n'
(OUT/'README.md').write_text(md,encoding='utf-8')
report = report.replace('</html>', '<h2>Appendix: measurement definitions</h2><p>These are elapsed wall-clock measurements, not CPU-only measurements. Waiting, I/O, scheduling delays, and garbage collection inside a measurement window are included. The processing order is:</p><p>Android client hash processing → API request → Postgres hash search → API response. API round trip surrounds the request, database work, and response.</p><h3>Android client hash processing</h3><p>Starts on Android immediately before dispatching hash work to `Dispatchers.Default`. Ends immediately after the hexadecimal hash string is produced, before bitmap recycling and returning the finished result to the UI thread.</p><p>Includes waiting for the background task to start; reading the corrected JPEG&#x27;s dimensions; reading and decoding the JPEG into an ARGB bitmap; allocating/copying the pixel array; converting to grayscale; Lanczos resizing to 32 × 32; computing the DCT; selecting the 8 × 8 coefficients; calculating the median; and forming the 64-bit hexadecimal hash. First-use hash-object initialization, if any, is inside this window as well.</p><p>Excludes camera capture, corner adjustment, perspective correction, preview, user confirmation, bitmap recycling after the timestamp, and dispatch back to the UI thread after the hash completes.</p><h3>Postgres hash search</h3><p>Starts when PostgreSQL evaluates the materialized start-clock expression before scanning candidate hashes. Ends when the outer SQL result samples the elapsed clock after ranking and assembling the match records. This is the instrumented matching portion of query execution, not the complete database request duration.</p><p>Includes reading valid issue and variant hashes; XOR/popcount Hamming distance calculations; taking each comic&#x27;s closest cover; ranking and selecting the top eight distinct comics; retrieving winning cover hashes, URLs, and variant IDs; counting hashes checked; SQL result assembly; and instrumentation overhead.</p><p>Excludes SQL parsing/planning, opening a database connection, transport between Django and PostgreSQL, authentication, the subsequent query for descriptive metadata of the eight comics, and Django&#x27;s response serialization.</p><h3>API round trip</h3><p>Starts immediately before dispatching the API operation to `Dispatchers.IO`. Ends after it returns to the UI thread.</p><p>Includes client dispatch/queue waits; constructing and validating the request and headers; acquiring a connection; DNS, TCP setup, and TLS negotiation when needed; request and response network travel; server request handling, authentication, throttling, validation, database matching, the separate comic-metadata query, and response serialization; receiving the complete JSON body; Android JSON parsing and basic result-shape validation; response cleanup; and returning to the UI thread. Connection reuse may avoid DNS/connection/TLS setup on a particular request.</p><p>Excludes building result cards, downloading/displaying cover artwork, human match selection, and feedback submission.</p><h3>User experience</h3><p>Derived sum: **Android client hash processing + API round trip**.</p><p>This is not one continuously running timer and is not the complete human scan experience. The gap between its component timers is excluded: bitmap recycling, returning from the hash task, and updating the “Searching Metron…” UI. It also excludes capture, corner adjustment/perspective correction, preview/confirmation, human decisions, result rendering, artwork loading, and feedback submission.</p><p>Postgres hash search is already included in API round trip. Do not add it again. Per-comic processing-work totals sum these measurements over the one or two attempts reconstructed for that comic, without adding the human retry delay.</p>' + '</html>')
import re
# Editorial presentation changes remain reproducible alongside the analysis.
retry_note = re.search(r'<p class="note"><strong>Retry grouping is reconstructed\.</strong>.*?</p>', report).group(0)
report = report.replace(retry_note, '')
report = report.replace('<h2>Data and reproducibility</h2>', '<h2>Data and reproducibility</h2>' + retry_note)
report = report.replace('<h2>Outcomes and final ranks</h2>', '<h2>Methodology</h2><p>TBD.</p><h2>Results and Accuracy</h2>')
report = report.replace('Trials unsuccessful after two scans', 'Trials with Negative Outcomes')
minor_words = set('a an the and or but for nor as at by in of on per to up via with from under into'.split())
def title_case(value):
    words = value.split(' ')
    return ' '.join(word if word in ('API', 'CPHTest', 'TBD') else word.lower() if i and word.lower() in minor_words else word[:1].upper()+word[1:] for i, word in enumerate(words))
report = re.sub(r'(<h[1-6]>)(.*?)(</h[1-6]>)', lambda m: m[1]+title_case(m[2])+m[3], report)
report = report.replace('<title>CPHTest — November 11 scan analysis</title>', '<title>CPHTest — November 11 Scan Analysis</title>')
md = re.sub(r'^(#{1,6} )(.*)$', lambda m: m[1]+title_case(m[2]), md, flags=re.M)
md = md.replace('## Pairing Assumptions and Limitations', '## Methodology\n\nTBD.\n\n## Pairing Assumptions and Limitations')
(OUT/'README.md').write_text(md, encoding='utf-8')
methodology = (OUT/'methodology.html').read_text(encoding='utf-8')
# Embed the originals so the HTML remains portable; keep source copies in the bundle.
for photo in (OUT/'methodology-images').glob('*.jpg'):
    uri = 'data:image/jpeg;base64,' + base64.b64encode(photo.read_bytes()).decode('ascii')
    methodology = methodology.replace('methodology-images/'+html.escape(photo.name, quote=True), uri)
report = report.replace('<h2>Methodology</h2><p>TBD.</p>', '<h2>Methodology</h2>'+methodology)
report = report.replace('</style>', 'figure{margin:20px 0}figcaption{font-size:14px;color:#475965;line-height:1.45;margin-top:10px}.workflow-gallery{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px;align-items:start}.workflow-gallery figure{margin:0 0 18px}.workflow-gallery img{display:block;width:100%;height:auto}li{margin-bottom:8px}@media(max-width:760px){.workflow-gallery{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:480px){.workflow-gallery{grid-template-columns:1fr}}@media print{figure{break-inside:avoid}.workflow-gallery{grid-template-columns:repeat(3,minmax(0,1fr))}}</style>')
md = md.replace('## Methodology\n\nTBD.', '## Methodology\n\nSee methodology.html for the full tester-supplied methodology and captioned workflow/environment images, also embedded in perceptual-hash-experiment-report.html. Editorial corrections clarify the app name, bit distances, sample count, and perspective-correction sequence. The reported 21% compares issue counts rather than asserting a verified fraction of upstream cover hashes.')
(OUT/'README.md').write_text(md, encoding='utf-8')
lead_summary = re.search(r'<p class="lead">.*?</p>', report).group(0)
report = report.replace(lead_summary, '')
report = report.replace('<h2>Results and Accuracy</h2>', '<h2>Results and Accuracy</h2>'+lead_summary)
report = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', report)
report = re.sub(r'`([^`]+)`', r'<code>\1</code>', report)
(OUT/'perceptual-hash-experiment-report.html').write_text(report,encoding='utf-8')
# Verify archived originals again before packaging.
for item in checksums:assert hashlib.sha256((OUT/item['file']).read_bytes()).hexdigest()==item['sha256']
with zipfile.ZipFile(OUT/'cphtest-analysis-2026-11-11.zip','w',zipfile.ZIP_DEFLATED) as archive:
 for p in sorted(OUT.rglob('*')):
  if p.is_file() and '.mpl-cache' not in p.parts and p.suffix!='.zip':archive.write(p,p.relative_to(OUT))
print(json.dumps({k:v for k,v in summary.items() if k not in ['timing_per_attempt_ms','timing_total_work_per_comic_ms']},indent=2))
print('PER ATTEMPT',json.dumps(timing,indent=2));print('PER COMIC',json.dumps(trial_timing,indent=2))
print('OUTPUT',OUT)

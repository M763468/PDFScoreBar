/* Real GUI acceptance: pre-checkpoint history, four correction types, repeated resume.
 * No request/engine mocks. URL, private native-annotation PDF, evidence directory.
 */
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const [url, pdf, evidence] = process.argv.slice(2);
  fs.mkdirSync(evidence,{recursive:true});
  const browser = await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_PATH});
  const report={passed:false,errors:[],stages:{},chromium:browser.version()};
  try {
    const p=await browser.newPage({viewport:{width:1600,height:1100}});
    p.on('pageerror',e=>report.errors.push(e.message));
    const ready=async()=>p.waitForFunction(()=>currentPage && measures.length>0 && image.complete);
    const state=async()=>p.evaluate(async()=> (await (await fetch('/api/state')).json()));
    const save=async()=>{
      await p.locator('#saveBtn').click();
      await p.waitForFunction(()=>window.reviewCorrectionState.get().package.counts.pending===0&&!window.reviewCorrectionState.get().package.current_result);
    };
    const apply=async(name)=>{
      await p.locator('#applyBtn').click();
      await p.waitForFunction(()=>{
        const s=window.reviewCorrectionState.get();
        if(s?.package.status==='error') throw new Error(JSON.stringify(s.package.last_application));
        return s?.package.current_result;
      },null,{timeout:240000});
      report.stages[name]=(await state()).package.current_result;
      const href=await p.locator('#openResultBtn').getAttribute('href');
      const response=await p.request.get(new URL(href,p.url()).href);
      const bytes=await response.body();
      if(!response.ok()||bytes.subarray(0,5).toString()!=='%PDF-')throw new Error('Result PDF missing');
      fs.writeFileSync(path.join(evidence,name+'.pdf'),bytes);
      console.log('Applied',name);
    };
    const selectMeasure=async()=>{
      const point=await p.evaluate(()=>{
        const box=measures[0].bbox;
        const point=imgToCanvas({x:(box[0]+box[2])/2,y:(box[1]+box[3])/2});
        const r=canvas.getBoundingClientRect();
        return {x:r.left+point.x*r.width/canvas.width,y:r.top+point.y*r.height/canvas.height};
      });
      await p.mouse.click(point.x,point.y);
      await p.waitForFunction(()=>selectedMeasure===measures[0]);
    };
    for(const attempt of ['attempt_0001','attempt_0012']){
      await p.goto(url);await ready();
      await p.locator('#historyPanel').evaluate(e=>{e.open=true});
      await p.waitForFunction(()=>document.querySelector('#legacySelect').options.length===12,{timeout:60000});
      report.legacyCount=await p.locator('#legacySelect option').count();
      await p.locator('#legacySelect').selectOption(attempt);
      await p.locator('#legacyImportBtn').click();
      await p.waitForFunction(a=>[...document.querySelector('#checkpointSelect').options].some(o=>o.textContent.includes(a)),attempt,{timeout:60000});
      const cp=await p.locator('#checkpointSelect').inputValue();
      report[attempt]={checkpoint:cp,initial:(await state()).package.current_result};
      if(report[attempt].initial)throw new Error('Legacy import inherited success');
      await p.locator('#resumePdf').setInputFiles(pdf);
      await p.locator('#resumeBtn').click();
      await p.waitForURL('**/?session=s_*',{timeout:180000});await ready();
      report[attempt].url=p.url();
      report[attempt].restoredIdentity=(await state()).package.current_identity;
      await apply(attempt);
    }
    const parentUrl=p.url();report.parentUrl=parentUrl;
    await p.locator('#historyPanel').evaluate(e=>{e.open=true});
    await p.locator('#checkpointLabel').fill('before four correction cases');
    const cpCount=await p.locator('#checkpointSelect option').count();
    await p.locator('#checkpointBtn').click();
    await p.waitForFunction(n=>document.querySelector('#checkpointSelect').options.length>n,cpCount);
    report.olderCheckpoint=await p.locator('#checkpointSelect').inputValue();
    // MMR: first measure 1 -> 2, row 2 must change 8 -> 9 -> 8.
    await p.locator('#typeSelect').selectOption('mmr_measure_span');await selectMeasure();
    await p.locator('#measureSpanInput').fill('2');await p.locator('#addItemBtn').click();
    await save();await apply('mmr');
    await p.locator('#deleteItemBtn').click();await save();await apply('mmr_undo');
    // force_measure on an already-counted interval is deliberately idempotent.
    await p.locator('#typeSelect').selectOption('measure_construction');await selectMeasure();
    await p.locator('#addItemBtn').click();await save();await apply('measure');
    await p.locator('#deleteItemBtn').click();await save();await apply('measure_undo');
    // Remove the internal barline between the first two physical measures.
    await p.locator('#typeSelect').selectOption('barline_construction');
    const bar=await p.evaluate(()=>{
      const m=measures[0].bbox;
      const candidates=barlines.filter(b=>{const y=(b.bbox[1]+b.bbox[3])/2;return y>m[1]&&y<m[3]});
      candidates.sort((a,b)=>Math.abs((a.bbox[0]+a.bbox[2])/2-m[2])-Math.abs((b.bbox[0]+b.bbox[2])/2-m[2]));
      const b=candidates[0], point=imgToCanvas({x:(b.bbox[0]+b.bbox[2])/2,y:(b.bbox[1]+b.bbox[3])/2});
      const r=canvas.getBoundingClientRect();return {bbox:b.bbox,x:r.left+point.x*r.width/canvas.width,y:r.top+point.y*r.height/canvas.height};
    });report.barline=bar.bbox;
    await p.mouse.click(bar.x,bar.y);await p.waitForFunction(()=>selectedBarline!==null);
    await p.locator('#opSelect').selectOption('remove_barline');await p.locator('#addItemBtn').click();
    await save();await apply('barline');
    await p.locator('#deleteItemBtn').click();await save();await apply('barline_undo');
    // Boundary before row 2, via the visible after-row-1 operation.
    await p.locator('#typeSelect').selectOption('movement_boundary');
    await p.locator('#movementSystemInput').fill('1');
    await p.locator('#movementAfterBtn').click();
    await p.waitForFunction(()=>itemsForCurrentPage('movement_boundary').some(x=>x.system===1)&&window.reviewCorrectionState.get().package.counts.pending===0&&!window.reviewCorrectionState.get().package.current_result);
    await apply('movement');
    await p.locator('#deleteItemBtn').click();await save();await apply('movement_undo');
    // A real product result is annotated synthetically by the Python broker.
    const latest=report.stages.movement_undo;
    fs.writeFileSync(path.join(evidence,'ready-for-return.json'),JSON.stringify(latest));
    const returned=path.join(evidence,'synthetic-return.pdf');
    for(let i=0;i<240&&!fs.existsSync(returned);i++)await new Promise(r=>setTimeout(r,500));
    if(!fs.existsSync(returned))throw new Error('Synthetic re-export was not prepared');
    await p.locator('#historyPanel').evaluate(e=>{e.open=true});
    await p.waitForFunction(cp=>[...document.querySelector('#checkpointSelect').options].some(x=>x.value===cp),report.olderCheckpoint);
    await p.locator('#checkpointSelect').selectOption(report.olderCheckpoint);
    await p.locator('#resumePdf').setInputFiles(returned);await p.locator('#resumeBtn').click();
    await p.waitForURL(u=>u.href!==parentUrl&&u.searchParams.has('session'),{timeout:180000});await ready();
    report.secondUrl=p.url();report.secondIdentity=(await state()).package.current_identity;
    if((await state()).package.current_result)throw new Error('Repeated resume inherited applied status');
    await apply('second_resume');
    const rejected=await p.evaluate(async payload=>{
      const history=await (await fetch('/api/checkpoints')).json();
      const response=await fetch('/api/resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({checkpoint_id:history.checkpoints[0].id,pdf_base64:payload})});
      return response.status;
    },fs.readFileSync(path.join(evidence,'synthetic-reject.pdf')).toString('base64'));
    if(rejected!==400||(await state()).package.current_result.final_pdf_sha256!==report.stages.second_resume.final_pdf_sha256)throw new Error('Rejected return destroyed success');
    report.rejectedReturnPreservesSuccess=true;
    await p.reload();await ready();
    await p.waitForFunction(()=>window.reviewCorrectionState.get()?.package.current_result);
    await p.screenshot({path:path.join(evidence,'second-resume.png')});
    if(report.errors.length)throw new Error(report.errors.join('\n'));
    report.passed=true;
    console.log('Legacy1/12, four GUI save/apply/undo cases, second resume passed');
  }catch(e){report.failure=e.stack;throw e;}
  finally{fs.writeFileSync(path.join(evidence,'continuation-report.json'),JSON.stringify(report,null,2));await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
